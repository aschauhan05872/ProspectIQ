# Controlled Company Research Engine (Phase 4)

## Purpose

Phase 4 collects and structures **source-derived evidence** from a resolved company's website. It does **not** perform opportunity analysis, service mapping, outreach, pitch generation, or lead scoring.

```
Resolved company → RESEARCH_COMPANY job → controlled website fetch
→ research case + research pages → SOURCE_DERIVED evidence
```

Future phases (5+) may analyze this evidence with AI or rules. Phase 4 establishes a trustworthy, deterministic evidence layer first.

## Architecture

| Layer | Responsibility |
|-------|----------------|
| `domain/company_research.py` | Case/page entities, statuses, fact builder, fingerprints |
| `domain/research_plan.py` | Page classification, same-domain policy, bounded plan |
| `application/company_research.py` | Submit, execute job, fetch pages, upsert evidence |
| `infrastructure/html_links.py` | Same-domain link extraction from HTML |
| `infrastructure/http_fetch.py` | SSRF-safe HTTP (reused, not duplicated) |
| `infrastructure/company_research_runtime.py` | Service wiring |
| PostgreSQL tables | `company_research_cases`, `research_pages` |

## Page selection strategy

1. Start from the company's normalized website URL (homepage first).
2. Fetch homepage; extract same-domain anchor links.
3. Classify links deterministically by URL path, title, and anchor text.
4. Prioritize: HOME → ABOUT → PRODUCTS → SERVICES → SOLUTIONS → PLATFORM → TECHNOLOGY → CONTACT → CAREERS → NEWS → BLOG → OTHER.
5. Stop at `PROSPECTIQ_RESEARCH_MAX_PAGES_PER_COMPANY` (default **10**).
6. Respect `PROSPECTIQ_RESEARCH_MAX_TIME_SECONDS` (default **120s**).

No blind crawling. No web search. No LLM classification.

## Limits

| Setting | Default | Env var |
|---------|---------|---------|
| Max pages per company | 10 | `PROSPECTIQ_RESEARCH_MAX_PAGES_PER_COMPANY` |
| Max research time | 120s | `PROSPECTIQ_RESEARCH_MAX_TIME_SECONDS` |

## Security

Reuses `SafeHttpFetcher` with existing controls:

- HTTP/HTTPS only; no URL credentials
- Localhost, loopback, private IP, link-local, cloud metadata blocking
- DNS revalidation and redirect revalidation
- Timeouts, max response bytes, max redirects
- `trust_env` disabled

Same-domain policy: only URLs on the resolved company domain are fetched. External sites (LinkedIn, Facebook, X, YouTube, etc.) are never auto-crawled.

## Evidence model

Each successful page creates **one** `SOURCE_DERIVED` evidence item:

- `fact_kind`: `research_page_content`
- Fact text describes page content only (no sales interpretation)
- Provenance: `tenant_id`, `company_id`, `source_locator`, `source_class`, `collection_method`, `collected_at`, `content_hash`, `research_case_id`, `research_page_id`

Example fact: *"Company services page titled 'Services': Virtual consultations."*

## Retry behavior

| Failure | Page | Job |
|---------|------|-----|
| Timeout, DNS transient, 408, 429, 5xx | Failed page; may retry job if **zero** pages fetched | Retryable |
| Invalid URL, SSRF rejection, most 4xx, unsupported content | Permanent page failure | — |
| All pages failed | — | Case `FAILED` |
| Mixed success/failure | — | Case `COMPLETED` with `partial_failure` |

## Idempotency

- Job enqueue uses idempotency key `research_company:{case_id}`.
- Evidence deduplication: same `source_locator` + `content_hash` reuses existing evidence (no duplicate rows for unchanged content).
- Historical evidence is never deleted when content changes; new hash creates new evidence.

## APIs

| Method | Path | Response |
|--------|------|----------|
| POST | `/companies/{company_id}/research` | **202** — `research_case_id`, `job_id`, `status` |
| GET | `/companies/{company_id}/research` | Latest research case summary |
| GET | `/research/cases/{case_id}` | Research case by ID |

Companies without a valid website return **400** with `not_researchable` / `no_website`. The HTTP request does not block until research completes.

## Job lifecycle

1. API creates `company_research_cases` row (`queued`) and enqueues `RESEARCH_COMPANY`.
2. Worker claims job, sets case `running`.
3. Worker fetches bounded page set, persists `research_pages`, creates evidence.
4. Case completes (`completed` or `failed`).

## Phase 4 boundary

Phase 4 does **NOT**:

- Decide if the company is a good lead
- Detect opportunities or service needs
- Generate outreach or pitches
- Modify scoring, qualification, discovery, or `RESEARCH_LEAD` behavior

Those belong to later phases.
