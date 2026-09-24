# Company discovery (V0)

Discovery finds **candidate companies** that match an ICP-shaped request through a permitted search API, persists provenance, and enqueues the existing `FETCH_SOURCE` ingestion path. It does not score leads, scrape search-engine HTML, or touch LinkedIn.

## End-to-end flow

```text
POST /discovery/companies
        ↓
Validate / normalize ICP request
        ↓
Enqueue DISCOVER_COMPANIES (Postgres job, tenant-scoped idempotency key)
        ↓
Worker claims job
        ↓
CompanyDiscoveryProvider (configured adapter)
        ↓
DiscoveryCandidate rows + DISCOVERY_RECORD evidence
        ↓
CompanySourceIngestionService.submit() per valid website URL
        ↓
FETCH_SOURCE (permitted company/careers page)
        ↓
Company + CompanySource + source_derived Evidence
        ↓
DiscoveryCandidate.company_id updated (pipeline)
        ↓
RESEARCH_LEAD enqueued automatically (after fetch success)
        ↓
SignalDetectionService → LeadScoringService → qualification state
```

No manual API call is required between these internal stages. Discovery does not assign HOT/WARM/COLD or qualification; that happens only after source evidence and deterministic signal detection.

### Job dependencies

| Stage | Depends on | Enqueues next |
|---|---|---|
| `DISCOVER_COMPANIES` | — | `FETCH_SOURCE` per accepted candidate |
| `FETCH_SOURCE` | — | `RESEARCH_LEAD` on success only |
| `RESEARCH_LEAD` | successful `FETCH_SOURCE` for same company | — |

`RESEARCH_LEAD` is never enqueued while fetch is pending or after permanent fetch failure.

### Candidate lifecycle (`ingestion_status`)

| Status | Meaning |
|---|---|
| `discovered` | Candidate persisted; fetch not yet enqueued |
| `fetch_queued` | `FETCH_SOURCE` job created |
| `fetched` | Fetch succeeded; `company_id` and source evidence IDs stored |
| `fetch_failed` | Fetch failed permanently |
| `research_queued` | `RESEARCH_LEAD` job created |
| `researched` | Research completed; `lead_id` stored |
| `research_failed` | Research failed permanently |
| `skipped_*` | No URL, duplicate domain, or invalid URL |

Legacy values (`pending`, `enqueued`, `already_enqueued`) remain for backward compatibility.

### Fetch URL vs company identity

- **Domain deduplication** uses `identity_host` (e.g. `acme.test`).
- **Fetch submission** uses the provider’s normalized full URL (e.g. `https://acme.test/careers`) so careers/jobs paths can produce hiring evidence.
- **`normalized_website`** on the candidate remains the company origin (e.g. `https://acme.test`).

### Idempotency and retries

- Discovery jobs: `discover_companies:{request-hash}`
- Fetch jobs: existing `fetch_source:{normalized_url}`
- Research jobs: `research_lead:{company_id}:{evidence-fingerprint}` — fingerprint changes when evidence changes, allowing re-research after a new fetch
- Retryable fetch/research failures use the existing job backoff; duplicate workers cannot create duplicate companies, evidence, signals, or leads

### Tenant boundaries

Every job, candidate, company, evidence, signal, and lead remains tenant-scoped. Cross-tenant candidate association is rejected at pipeline transitions.

### Failure handling (pipeline)

| Failure | Candidate status | Next stage |
|---|---|---|
| Fetch retryable | unchanged | retry fetch; no research |
| Fetch permanent | `fetch_failed` | no research |
| Research retryable | unchanged | retry research |
| Research permanent | `research_failed` | evidence retained |

## Provider

V0 ships one configurable adapter:

| Setting | Purpose |
|---|---|
| `PROSPECTIQ_DISCOVERY_PROVIDER` | `none` (default) or `serpapi` |
| `PROSPECTIQ_SERPAPI_API_KEY` | SerpAPI credential |
| `PROSPECTIQ_DISCOVERY_MAX_CANDIDATES` | Hard cap per request/job |
| `PROSPECTIQ_DISCOVERY_PAGE_SIZE` | Provider page size |
| `PROSPECTIQ_DISCOVERY_MAX_PAGES` | Maximum provider pages per job |
| `PROSPECTIQ_DISCOVERY_TIMEOUT_SECONDS` | Provider HTTP timeout |

SerpAPI is used through its supported JSON API (`https://serpapi.com/search.json`), not by scraping Google HTML.

If the provider is unset or credentials are missing, API submit fails with a clear error. The unit test suite mocks provider HTTP and does not require live credentials.

## ICP mapping

The request follows the Lead Generation SOP intake shape:

- industry (one priority industry)
- countries / geographies
- employee range (11–1000)
- hiring requirement (query hint)
- optional keywords

Each field is labeled in code as:

| Status | Meaning |
|---|---|
| `matched` | Provider query uses this field |
| `not_verified` | May appear in query text; provider does not filter/verify it |
| `not_supported` | Not available from the initial provider |

Current SerpAPI support:

| Field | Support |
|---|---|
| Industry | matched (query terms) |
| Geography | matched (query terms) |
| Keywords | matched |
| Employee range | not_verified |
| Hiring required | not_verified |
| Headcount growth | not_supported |
| Company type | not_supported |

Candidates are **not rejected** merely because the provider cannot verify growth or company type.

## Provenance

Each candidate stores provider key, source locator, discovery timestamp, request snapshot, and field checks.

Discovery provenance evidence uses:

- `origin=discovery_record`
- `source_class=permitted_search_api`
- `fact_kind=discovery_candidate`

That is separate from website `source_derived` evidence created by `FETCH_SOURCE`.

## Deduplication

- Discovery jobs: idempotency key `discover_companies:{request-hash}`
- Candidates within a job: unique `(tenant_id, discovery_job_id, source_locator)`
- Same domain in one run: second hit is stored with `skipped_duplicate`; only one `FETCH_SOURCE` is enqueued
- Company identity after ingestion still uses existing host-based normalization (`identity_host`)

## API

```http
POST /discovery/companies
{
  "industry": "healthtech",
  "countries": ["USA"],
  "employee_min": 11,
  "employee_max": 1000,
  "hiring_required": true,
  "keywords": ["platform"],
  "limit": 20
}
```

```http
GET /discovery/companies/{job_id}
```

Responses include job status, normalized request, field-support metadata, candidates, ingestion status, and related fetch job IDs. Provider secrets are never returned.

## Failure handling

| Failure | Classification |
|---|---|
| Timeout / network | retryable |
| HTTP 429 / 5xx | retryable |
| Invalid/missing credentials | permanent |
| Malformed provider payload | permanent |
| Invalid ICP request | permanent (API 400) |

## Local run

```powershell
copy .env.example .env
# set PROSPECTIQ_DISCOVERY_PROVIDER=serpapi
# set PROSPECTIQ_SERPAPI_API_KEY=your-key
cd backend
alembic upgrade head
uvicorn prospectiq.api.main:app --reload
python -m prospectiq.worker.main
```

```http
POST /discovery/companies
{ "industry": "healthtech", "countries": ["USA"], "limit": 5 }
```

## What this does not do

No LinkedIn automation, search-engine HTML scraping, AI filtering, lead scoring, crawling, SaaS, MCP, dashboard, or outreach automation.
