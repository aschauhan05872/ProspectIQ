# WS6.2C — Discovery Strategy Review

**Document type:** Engineering validation / strategy review (read-only analysis)  
**Date:** 2026-09-23  
**Scope:** ProspectIQ V0 discovery pipeline as implemented in repository  
**Authoring mode:** Code inspection only — no live SerpAPI calls, no production changes

---

## 1. EXECUTIVE SUMMARY

### What discovery currently does

**FACT:** ProspectIQ discovery accepts an ICP-shaped `DiscoveryRequest`, enqueues a tenant-scoped `DISCOVER_COMPANIES` job, calls the configured `SerpApiDiscoveryProvider`, maps Google organic results to `ProviderDiscoveryHit` records, validates each hit via `validate_discovery_hit()`, persists `DiscoveryCandidate` rows plus `DISCOVERY_RECORD` evidence, and enqueues `FETCH_SOURCE` for accepted hits. Successful fetch triggers `RESEARCH_LEAD`, deterministic signal detection, and lead scoring.

**FACT:** Discovery does not score leads, detect buying signals, or assess external vendor opportunity. Those steps occur only after company-source ingestion and research.

### What it does correctly

**FACT:**
- Clean separation between discovery provenance (`EvidenceOrigin.DISCOVERY_RECORD`, `SourceClass.PERMITTED_SEARCH_API`) and website evidence (`EvidenceOrigin.SOURCE_DERIVED`).
- Tenant-scoped jobs, idempotency keys, and pipeline state tracking on `DiscoveryCandidate`.
- Provider-neutral query construction (`build_discovery_query`) with explicit field-support documentation (`PROVIDER_FIELD_SUPPORT`).
- Deterministic signal detection and scoring are isolated from discovery and remain unchanged per SOP.
- WS6.2B added pre-fetch candidate validation, rejecting obvious non-company URLs before `FETCH_SOURCE` enqueue.

### What WS6.2B fixed

**FACT:** Before WS6.2B, every SerpAPI organic result became a candidate. `CompanyDiscoveryService.execute_job()` now calls `validate_discovery_hit()` before accepting a hit (`backend/src/prospectiq/application/discovery.py`, lines 123–136).

**UNIT-TESTED:** WS6.2 first-experiment URLs (IBM Think, Investopedia, FTC.gov, Plaid resources, House.gov) are rejected. Stripe/Chime careers pages are accepted (`backend/tests/test_discovery_candidate_validation.py`, `backend/tests/test_discovery.py::test_discovery_rejects_non_company_search_results`).

### What remains unproven

**FACT:** The one authorized WS6.2B live SerpAPI call timed out (`RetryableDiscoveryError`, 15s). Raw results = 0; no live validation of the new filter on real provider output (`docs/real-data-validation-report.md`, WS6.2B section).

**INTERPRETATION:** Unit tests prove validation logic; live discovery quality improvement is **not yet demonstrated**.

### Suitability for continued V0 validation

**INTERPRETATION:** The architecture is **suitable for continued V0 validation**. The pipeline is coherent, provenance-aware, and test-covered. The primary gap is **search-result quality and query intent**, not missing pipeline stages.

**RECOMMENDATION:** Continue V0 validation with controlled, quota-budgeted experiments. Do not expand scope (SaaS, LinkedIn automation, scoring redesign) until discovery produces a measurable rate of real company candidates.

### Main discovery-quality bottleneck

**INTERPRETATION:** The bottleneck is **search-result → company-candidate discrimination at discovery time**, compounded by:
1. Generic Google queries that surface educational/regulatory/content pages.
2. URL-only validation that cannot distinguish a real target company from a generic keyword domain (e.g. `fintech.com`).
3. No post-search ICP verification (employee count, industry, geography) — only query-text hints.

---

## 2. CURRENT END-TO-END DISCOVERY FLOW

Actual implementation flow (corrected where docs differ):

```text
POST /discovery/companies
  → api/routes/discovery.py
  → normalize_discovery_request()                    [domain/discovery.py]
  → CompanyDiscoveryService.submit()                 [application/discovery.py]
  → JobQueue.enqueue(DISCOVER_COMPANIES)             [infrastructure/jobs.py]
        idempotency: discovery_idempotency_key()

Worker claims job
  → worker/main.py::handle_job()
  → CompanyDiscoveryService.execute_job()            [application/discovery.py]
      → SerpApiDiscoveryProvider.discover()          [infrastructure/discovery/serpapi_provider.py]
          → build_discovery_query(request)           [domain/discovery_query.py]
          → SerpAPI GET search.json (paginated loop)
          → _normalize_hit() per organic result
      → FOR each hit:
          → candidate_website_url() / candidate_fetch_url()
          → validate_discovery_hit()                 [domain/discovery_candidate_validation.py]
          → default_field_checks() → merge validation labels
          → status: SKIPPED_* or accepted
          → _persist_discovery_evidence()            [DISCOVERY_RECORD]
          → DiscoveryCandidateRepository.upsert()
          → IF accepted: CompanySourceIngestionService.submit()  [application/ingestion.py]
                → FETCH_SOURCE job

Worker: FETCH_SOURCE
  → CompanySourceIngestionService.execute_job()
  → HttpPageSourceAdapter fetch
  → Company + CompanySource + SOURCE_DERIVED Evidence
  → CompanyPipelineService.after_fetch_succeeded()   [application/pipeline.py]
      → (news disabled in validation) RESEARCH_LEAD enqueue

Worker: RESEARCH_LEAD
  → CompanyResearchService.research()                [application/research.py]
      → SignalDetectionService.detect()              [domain/detection.py]
      → LeadScoringService.apply_to_lead()           [application/services.py → domain/scoring.py]
  → CompanyPipelineService.after_research_succeeded()
      → DiscoveryCandidate → RESEARCHED, lead_id set
```

| Step | Module / class / function |
|------|---------------------------|
| API submit | `api/routes/discovery.py` → `CompanyDiscoveryService.submit()` |
| Request normalization | `normalize_discovery_request()` — `domain/discovery.py:270` |
| Query construction | `build_discovery_query()` — `domain/discovery_query.py:23` |
| Provider call | `SerpApiDiscoveryProvider.discover()` — `serpapi_provider.py:63` |
| Hit normalization | `SerpApiDiscoveryProvider._normalize_hit()` — `serpapi_provider.py:149` |
| Candidate validation | `validate_discovery_hit()` — `discovery_candidate_validation.py:148` |
| ICP metadata (not filtering) | `default_field_checks()` / `PROVIDER_FIELD_SUPPORT` — `domain/discovery.py:74` |
| Candidate persistence | `SqlAlchemyDiscoveryCandidateRepository.upsert()` — `infrastructure/repositories.py` |
| Discovery evidence | `_persist_discovery_evidence()` — `application/discovery.py:275` |
| Source fetch | `CompanySourceIngestionService.ingest()` — `application/ingestion.py` |
| Pipeline orchestration | `CompanyPipelineService` — `application/pipeline.py` |
| Signal detection | `SignalDetectionService.detect()` — `domain/detection.py:259` |
| Scoring / qualification | `ScoringRuleset.score()` — `domain/scoring.py:61` |
| External opportunity fit | **Not in production pipeline** — `_assess_external_opportunity_fit()` in `scripts/run_real_data_validation.py:434` only |

**IMPLEMENTATION OBSERVATION:** Rejected hits are still persisted as `DiscoveryCandidate` rows with `ingestion_status=skipped_non_company`; they are not deleted. Fetch is not enqueued for them (`application/discovery.py:167–171`).

**IMPLEMENTATION OBSERVATION:** `ICPRuleset.evaluate_company()` exists (`domain/icp.py:50`) but is **not invoked** anywhere in the discovery → research pipeline. ICP enforcement at discovery is query-relevance only.

---

## 3. USER REQUIREMENT → SEARCH QUERY

### Execution path

1. API or script supplies industry, countries, employee range, hiring flag, keywords, limit.
2. `normalize_discovery_request()` validates and normalizes (`domain/discovery.py:270`).
3. `SerpApiDiscoveryProvider.discover()` calls `build_discovery_query(request)` (`serpapi_provider.py:68`).
4. Resulting string is sent as SerpAPI parameter `q`.

### Query template

```python
# domain/discovery_query.py:23-34
"{industry_label} companies [in {geo1, geo2}] [hiring] [{employee_min}-{employee_max} employees] {keyword1 keyword2 ...}"
```

**Example (WS6.2 default):**
`fintech companies in USA hiring 11-1000 employees software development technology`

**Example (WS6.2B):**
`fintech companies in USA hiring 11-1000 employees fintech startup careers software engineer`

### Field usage matrix

| Field | In model | In query | SerpAPI filter param | Post-discovery verification |
|-------|----------|----------|----------------------|----------------------------|
| `industry` | ✅ | ✅ (alias label) | ❌ | ❌ |
| `countries` | ✅ | ✅ (alias label) | ❌ | ❌ |
| `employee_min/max` | ✅ | ✅ (text) | ❌ | ❌ |
| `hiring_required` | ✅ | ✅ (word "hiring") | ❌ | ❌ (signals later if careers fetched) |
| `keywords` | ✅ | ✅ (appended) | ❌ | ❌ |
| `limit` | ✅ | ❌ | ❌ (controls pagination cap) | — |
| `min_headcount_growth_pct` | ✅ | ❌ | ❌ | ❌ (`NOT_SUPPORTED`) |
| `company_types` | ✅ | ❌ | ❌ | ❌ (`NOT_SUPPORTED`) |
| `SearchProfile.functions/seniorities` | ✅ (separate model) | ❌ | ❌ | ❌ (not wired) |

**FACT:** Industry and geography are translated via `INDUSTRY_ALIASES` / `GEOGRAPHY_ALIASES` (`domain/company.py:40–79`). Employee range appears as literal text; SerpAPI/Google does not enforce it.

**FACT:** Opportunity types (external development, staff augmentation, RFP, etc.) are **not represented** in query construction unless passed manually as keywords. No dedicated query family exists.

**FACT:** One query string per discovery job. No multi-query fan-out in application code.

### Pagination and budget

| Control | Location | Default | Effect |
|---------|----------|---------|--------|
| `request.limit` | `DiscoveryRequest.limit` | capped 1–100 | Max hits returned |
| `discovery_page_size` | `config.py:51` | 10 | SerpAPI `num` param |
| `discovery_max_pages` | `config.py:52` | 2 | Max `_fetch_page()` calls per job |
| `discovery_timeout_seconds` | `config.py:53` | 15.0 | Per-request HTTP timeout |

**FACT:** Pagination loop in `SerpApiDiscoveryProvider.discover()` (`serpapi_provider.py:81–96`) — each page is one SerpAPI HTTP call. Default config = up to **2 SerpAPI calls per discovery job**.

**FACT:** Validation script forces `PROSPECTIQ_DISCOVERY_MAX_PAGES=1` and tracks quota via monkeypatched `_fetch_page` (`scripts/run_real_data_validation.py:227–302`).

---

## 4. WHAT SERPAPI ACTUALLY PROVIDES

### Adapter behavior

| Aspect | Implementation |
|--------|----------------|
| Endpoint | `https://serpapi.com/search.json` (`serpapi_provider.py:22`) |
| Engine | `google` (`serpapi_provider.py:100`) |
| Params sent | `engine`, `q`, `api_key`, `num`, `start` |
| Params **not** sent | Industry enum, geo filter, employee filter, hiring filter, site: restrictions |

### Fields consumed from response

| SerpAPI field | Used as |
|---------------|---------|
| `organic_results[].link` | `ProviderDiscoveryHit.website`, `source_locator` |
| `organic_results[].title` | `ProviderDiscoveryHit.name` (truncated 512) |
| `organic_results[].position` | `ProviderDiscoveryHit.provider_rank` |
| `organic_results[].snippet` | `raw_reference.snippet` → discovery evidence snippet |

### Fields ignored

**FACT:** SerpAPI does not expose structured company attributes in this adapter. The following are **not parsed or stored** from search results:
- Employee count / company size
- Industry classification
- Company type (private/public/VC-backed)
- Headquarters / geography
- Hiring status (verified)
- Revenue, funding stage
- External project requirements

**IMPLEMENTATION OBSERVATION:** `hit.confidence` is hardcoded to `"medium"` in `_normalize_hit()` regardless of snippet/title (`serpapi_provider.py:164`).

### Error, retry, timeout

| Condition | Exception | Permanent? |
|-----------|-----------|------------|
| Timeout | `RetryableDiscoveryError` | No |
| Transport error | `RetryableDiscoveryError` | No |
| HTTP 429, 5xx | `RetryableDiscoveryError` | No |
| HTTP 401/403, other 4xx | `PermanentDiscoveryError` | Yes |
| Malformed JSON / payload error | `PermanentDiscoveryError` | Yes |

**FACT:** No in-provider retry loop. Job queue retries failed jobs up to `DEFAULT_MAX_ATTEMPTS=5` (`domain/jobs.py:35`, `infrastructure/jobs.py:138`). On retry, `execute_job()` re-invokes `provider.discover()`, which **may consume additional SerpAPI calls** (each retry = new pagination loop).

**FACT:** WS6.2B live failure: 15s timeout → 0 organic results → job marked failed, 1 quota unit consumed, no retry in validation run (`docs/real-data-validation-report.md`).

### Provenance

Discovery evidence metadata includes: `provider_key`, `discovery_job_id`, `candidate_name/domain/website`, `provider_rank`, full `request` snapshot, `raw_reference` (`application/discovery.py:296–306`).

### Attributes NOT reliably available from search provider

| Attribute | Available? |
|-----------|------------|
| Employee count | ❌ Not from SerpAPI organic results |
| Industry | ❌ Not verified |
| Company type | ❌ Not available |
| Geographic HQ | ❌ Not verified |
| Actual hiring status | ❌ Not verified (only query hint + later careers fetch) |
| External project requirement | ❌ Not available |

---

## 5. CANDIDATE VALIDATION

**Module:** `backend/src/prospectiq/domain/discovery_candidate_validation.py`  
**Entry point:** `validate_discovery_hit(hit: ProviderDiscoveryHit) -> CandidateValidationResult`

### Rules (deterministic, URL-based)

| Rule | Mechanism | Reject reason |
|------|-----------|---------------|
| Government | `.gov`, `.mil` TLD; `.gov.` in host | `government_tld` |
| Educational | `.edu` TLD | `educational_tld` |
| Blocked hosts | LinkedIn, job boards, social, Wikipedia, Google/Bing | `blocked_provider_host` |
| Media hosts | Registrable label in `MEDIA_HOST_LABELS` (investopedia, forbes, etc.) | `media_host_pattern` |
| Editorial subdomain | First label in `EDITORIAL_SUBDOMAIN_LABELS` (news, blog, think, etc.) | `editorial_subdomain` |
| Content path | First segment in `CONTENT_PATH_SEGMENTS` (think, resources, articles, etc.) | `content_path` |
| Deep non-careers path | ≥3 path segments, first not careers/about/company | `deep_non_careers_path` |

### Accepted patterns

- Root domain (no path or `/` only) → `VALID_COMPANY`
- First segment in `CAREERS_PATH_SEGMENTS` (careers, jobs, hiring, etc.) → `VALID_COMPANY`
- First segment in `COMPANY_PAGE_SEGMENTS` (about, company, team, contact) → `VALID_COMPANY`

**FACT:** Validation uses URL/host/path only. `hit.name` (SerpAPI title) is **not** used.

### Why `fintech.com` still passes

**UNIT-TESTED:** `test_accepts_fintech_com_root_as_company_domain` explicitly asserts acceptance (`test_discovery_candidate_validation.py:68`).

**IMPLEMENTATION OBSERVATION:**
- Host `fintech.com` → registrable label `fintech`
- Not in `MEDIA_HOST_LABELS`
- Not gov/edu
- Empty path → falls through to default accept at line 235–238

**INTERPRETATION:** A generic industry-keyword domain is **indistinguishable** from a legitimate company domain using current rules. The validator answers "is this URL structurally plausibly a company page?" not "is this an ICP-fit fintech company?"

**FACT:** This cannot currently be determined deterministically without additional signals (company registry, homepage content fetch, industry classification source). That verification belongs in research/ingestion, not URL parsing alone.

### Obvious false positives that remain possible

- Generic keyword domains (`fintech.com`, `healthcare.com`)
- Non-target companies that match industry terms in domain name
- Company `/products`, `/solutions`, `/platform` pages (≤2 segments, not in content list)
- Partner directories, documentation sites on company domains
- Large enterprises outside employee range (not filterable at discovery)
- Subsidiary/careers pages where company identity is ambiguous

---

## 6. ICP FILTERING

### What exists

1. **`PROVIDER_FIELD_SUPPORT`** — documents which ICP fields are query-matched vs not-verified (`domain/discovery.py:74–114`). Stored in `DiscoveryCandidate.field_checks`; **does not reject candidates**.

2. **`ICPRuleset`** — full company ICP evaluation (`domain/icp.py:50–85`): employee size, headcount growth, company type, hiring, industry, geography.

**FACT:** `ICPRuleset` is **not called** from discovery, ingestion, research, or scoring paths. Only tested in `backend/tests/test_icp.py`.

3. **`validate_discovery_hit()`** — URL quality filter (not ICP filter).

4. **Domain dedupe** — within single discovery job (`application/discovery.py:137–148`).

5. **Qualification** — `is_qualified()` requires ≥2 distinct buying signals (`domain/scoring.py:57`). This is **not ICP matching**.

### Criterion verification status

| Criterion | Discovery | Research / ingestion |
|-----------|-----------|----------------------|
| Industry | NOT VERIFIED (query hint only) | Often null on `Company` unless inferred from fetch |
| Geography | NOT VERIFIED (query hint only) | Often null unless inferred |
| Employee range | NOT VERIFIED (query text only) | `Company.employee_count` if extracted — **not verified from current implementation** at fetch time |
| Hiring | NOT VERIFIED at search | INFERRED via `HIRING_TECH_ROLES` signal from careers evidence |
| Headcount growth | NOT SUPPORTED | Requires data not in V0 fetch |
| Company type | NOT SUPPORTED | Requires data not in V0 fetch |
| Keywords | Query relevance only | Not re-checked |

**INTERPRETATION:** Current implementation relies almost entirely on **search-query relevance** plus **URL validation**, not factual company verification against ICP.

---

## 7. DISCOVERY VS RESEARCH

| Question | Stage | Current implementation |
|----------|-------|------------------------|
| Could this be a company worth researching? | **Discovery** | SerpAPI hit + URL validation + dedupe |
| What is actually true about this company? | **Research** | Fetch homepage/careers → evidence → signal detection |
| Is it ICP-fit (size, geo, industry)? | **Research (intended)** | `ICPRuleset` exists but **not wired** |
| Does it show buying signals? | **Research** | `SignalDetectionService` on `SOURCE_DERIVED` evidence |
| Does it need an external dev vendor? | **Not automated** | Validation script heuristic only |

**INTERPRETATION:** The architecture **preserves the discovery/research distinction** in pipeline stages and evidence origins. Discovery evidence (`DISCOVERY_RECORD`) is never used for signal detection — only `SOURCE_DERIVED` evidence is (`domain/detection.py:271`).

**GAP:** Discovery over-claims company candidacy (any accepted URL) while research under-verifies ICP attributes (no `ICPRuleset` integration).

---

## 8. EXTERNAL SOFTWARE-DEVELOPMENT OPPORTUNITY DISCOVERY

Business goal: find companies with plausible **external software-development opportunity**, not merely companies hiring engineers.

### A. Explicit external-development requirement

**Examples:** software development partner, contract developers, staff augmentation, RFP, outsourced development, technology partner.

| Capability | Today | Where |
|------------|-------|-------|
| Query terms for partner/vendor language | ❌ Not in default query template | Would require keywords |
| Detection of explicit vendor language | ❌ No production signal | Validation script `HIGH_FIT_TERMS` only |
| Evidence from search snippets | ⚠️ Stored in discovery evidence snippet but not analyzed | `application/discovery.py:295` |

**INTERPRETATION:** Current discovery **cannot reliably find** explicit external-development requirements. Generic hiring queries will not surface RFP/partner pages consistently.

### B. Emerging project opportunity

**Examples:** new platform, digital transformation, modernization, AI initiative, funding + tech expansion.

| Capability | Today | Where |
|------------|-------|-------|
| Platform/launch/modernization query terms | ⚠️ Manual keywords only | `DiscoveryRequest.keywords` |
| `EXPANSION_LAUNCH` signal | ✅ Implemented | Requires news evidence with `fact_kind=expansion_announcement` |
| `FUNDING_NEWS` signal | ✅ Implemented | Requires news evidence with `fact_kind=funding_announcement` |
| News ingestion in validation | ❌ Disabled (`PROSPECTIQ_NEWS_PROVIDER=none`) | `scripts/run_real_data_validation.py:231` |
| Website text analysis for transformation | ❌ Deferred (`TALKS_ABOUT_TECH_GROWTH`) | `domain/detection.py:48–54` |

**INTERPRETATION:** Project-opportunity detection depends on **news ingestion** (currently off in validation) or future structured website analysis. Discovery search alone does not detect these.

### C. Hiring as buying signal

| Capability | Today | Where |
|------------|-------|-------|
| Hiring in query | ✅ Word "hiring" if `hiring_required=True` | `discovery_query.py:28` |
| `HIRING_TECH_ROLES` signal | ✅ Implemented | Careers/jobs URL + hiring language + tech role patterns |
| Weight | +3 (unchanged) | `domain/signal.py:33` |
| Proves external vendor need? | ❌ **No** | By design — hiring ≠ outsourcing intent |

**FACT:** Validation script explicitly labels hiring-only evidence as `LOW` external opportunity fit (`scripts/run_real_data_validation.py:453–456`).

**INTERPRETATION:** Current pipeline can detect **technology hiring activity** (buying signal) but **cannot infer external project/vendor need** without explicit language in fetched evidence.

---

## 9. WHY WS6.2 PRODUCED BAD CANDIDATES

WS6.2 first experiment: one SerpAPI search, six organic results, all accepted as candidates (pre-WS6.2B).

| Result | Current WS6.2B outcome | Reason | Validation status |
|--------|------------------------|--------|-------------------|
| `fintech.com` | **ACCEPT** | Root domain, no blocking rule | UNIT-TESTED |
| `ibm.com/think/...` | **REJECT** | First path segment `think` ∈ `CONTENT_PATH_SEGMENTS` | UNIT-TESTED |
| `investopedia.com` | **REJECT** | Registrable label `investopedia` ∈ `MEDIA_HOST_LABELS` | UNIT-TESTED |
| `ftc.gov` | **REJECT** | `.gov` TLD | UNIT-TESTED |
| `plaid.com/resources/...` | **REJECT** | First segment `resources` ∈ `CONTENT_PATH_SEGMENTS` | UNIT-TESTED |
| `financialservices.house.gov` | **REJECT** | `.gov` TLD | UNIT-TESTED |

**FACT:** No live SerpAPI re-run has validated these rejections on provider output. All assessments above are **UNIT-TESTED**, not **LIVE-VALIDATED**.

**Root cause (WS6.2):** `CompanyDiscoveryService.execute_job()` accepted every organic hit with no validation layer. Query `"fintech companies in USA hiring ... software development technology"` is semantically broad and Google returns definitional/regulatory/editorial content for "fintech" topics.

---

## 10. CURRENT FALSE-POSITIVE RISKS

Supported by implementation inspection:

| Risk | Mechanism |
|------|-----------|
| Generic keyword domains | Root-domain accept rule (`fintech.com`) |
| Industry term sites, not target companies | Same as above |
| Company marketing/product pages | `/products`, `/solutions` not in `CONTENT_PATH_SEGMENTS`; ≤2 segments accepted |
| Documentation / developer portals | `/docs` rejected only as subdomain, not path |
| Partner/marketplace directories | No directory-path rejection |
| Job aggregators | Blocked at provider (`glassdoor.com`, `indeed.com`) — partial |
| Press pages on company domain | `/press` in `CONTENT_PATH_SEGMENTS` — rejected; `/newsroom` not listed |
| Educational content on `.com` | Only `.edu` TLD rejected, not educational content on commercial domains |
| Wrong employee range | Not verifiable at discovery |
| Wrong geography | Not verifiable at discovery |
| Hiring signal without vendor need | Detectable as buying signal; external fit remains LOW/UNKNOWN |
| Duplicate companies across runs | Only deduped within single job, not cross-job |
| SerpAPI title misleading | Title stored as candidate name but not used for validation |

---

## 11. DISCOVERY SOURCE STRATEGY

### Current source strategy

**Primary:** SerpAPI Google organic search → company/careers URL → HTTP fetch → evidence → signals.

**Secondary (optional, disabled in validation):** SerpAPI news for funding/expansion signals.

**Tertiary (human):** Sales Navigator recipe generation in validation script only.

### What SerpAPI/Google search is good at

- Finding publicly indexed pages matching natural-language queries
- Surfacing careers pages when query includes hiring/careers terms
- Broad exploratory company discovery by industry + geography keywords
- Returning rank, title, snippet for provenance

### What it is bad at

- Structured ICP filtering (employee count, company type)
- Distinguishing educational/regulatory content from companies (partially mitigated by WS6.2B validation)
- Proving external vendor / outsourcing intent
- Verifying hiring status without fetching careers page
- Decision-maker identification
- Reliable company attribute extraction

### Suitability by task

| Task | SerpAPI search alone | + Fetch | + News | + Licensed data |
|------|---------------------|---------|--------|-----------------|
| Explicit project requirements | Poor | Fair | Fair | Good |
| Finding companies | Fair | Good | — | Good |
| Finding company signals | Poor | Good (careers) | Good (funding/launch) | Good |
| Verifying company facts | Poor | Fair | Fair | Good |
| Finding decision makers | No | No | No | Partial → **human LinkedIn** |

### RECOMMENDATION — future source hierarchy (not implemented)

1. **Public company websites + careers pages** — primary evidence for hiring signals (current V0 path).
2. **Public company announcements / news** — funding, expansion, launch (enable news selectively).
3. **Permitted search APIs** — discovery only; not verification.
4. **Licensed company intelligence providers** — employee count, industry, HQ (future ICP verification).
5. **Explicit project marketplaces / RFP sources** — where permitted, for Family C queries.
6. **Sales Navigator** — human-controlled decision-maker identification only; no automation.

---

## 12. SEARCH STRATEGY RECOMMENDATION

**RECOMMENDATION:** Separate query intent into families. Do not implement in this review.

### Family A — Company discovery
```
"{industry} startup" site:*.com -site:gov -site:edu careers
"fintech company" USA "about us"
```

### Family B — Hiring / technology activity
```
site:{domain} (careers OR jobs) ("software engineer" OR "backend engineer")
"{industry}" "we are hiring" engineer USA
```

### Family C — External development requirement
```
"{industry}" ("software development partner" OR "technology partner" OR "staff augmentation")
"RFP" "software development" {industry}
```

### Family D — Product / platform / project activity
```
"{industry}" ("platform launch" OR "new product" OR "digital transformation")
"{company}" modernization cloud migration
```

### Family E — Funding / expansion
```
"{industry}" startup "series A" OR "series B" 2025
"{industry}" "expansion" "engineering" USA
```
*(Prefer news API over web search when enabled.)*

### Family F — Technology implementation / modernization
```
"{industry}" ("API development" OR "cloud migration" OR "legacy modernization")
```

### Why generic queries return content pages

**INTERPRETATION:** Query `"fintech companies hiring software engineer"` matches **topic content** (definitions, regulations, guides) as strongly as **company careers pages** because Google ranks informational intent highly for broad industry terms. Employee-range text in query does not restrict results.

### Why query intent must be separated from candidate validation

- **Query** controls what Google returns (recall).
- **Validation** controls what becomes a company candidate (precision).
- Neither substitutes for **research** (verification).

### Why discovery and research must remain separate stages

Discovery with unverified search hits produces false company records if treated as facts. Research on fetched evidence produces auditable signals. Mixing them would contaminate scoring with unverified search snippets.

---

## 13. SEARCH BUDGET ANALYSIS

### Per discovery job (default config)

| Setting | Value | SerpAPI calls |
|---------|-------|---------------|
| `discovery_max_pages=2` | 2 pages max | Up to 2 |
| `discovery_page_size=10` | 10 results/page | — |
| `discovery_max_candidates=20` | May stop early if limit reached | ≤2 |

**FACT:** Each `_fetch_page()` = 1 SerpAPI HTTP call = 1 billable search (validation script tracks this way).

### Retry behavior

| Event | Additional SerpAPI calls? |
|-------|---------------------------|
| Page 2 pagination | Yes (+1 per page) |
| Job retry after timeout | Yes — full `discover()` re-run |
| Idempotent job replay | No — job not re-executed |
| Validation quota hook | Raises on `used > budget` | 

**INTERPRETATION:** A single discovery job with default `max_pages=2` and one retry after timeout could consume **up to 4 SerpAPI calls** without explicit budget guard outside the validation script.

### Validation script controls

| Control | Value |
|---------|-------|
| Default budget | 8 (cap 10) |
| WS6.2B mode | 1 |
| Forced pages | 1 |
| News | disabled |

### Theoretical multi-query strategy (not implemented)

If 6 query families × 1 page each = **6 SerpAPI calls per ICP run** (before retries). With `DEFAULT_MAX_ATTEMPTS=5` on timeout, worst case multiplies by retry count unless discovery jobs are marked dead after first attempt in validation mode.

**RECOMMENDATION:** Any future multi-query strategy requires explicit per-run budget enforcement in application code, not only in the validation script.

---

## 14. NEXT REAL-DATA EXPERIMENT

**RECOMMENDATION:** WS6.2D — Live validation of WS6.2B filter + careers-targeted query.

| Parameter | Value |
|-----------|-------|
| **Objective** | Prove WS6.2B validation improves live candidate precision vs WS6.2 |
| **Hypothesis** | A careers-focused query returns ≥3 `VALID_COMPANY` candidates; ≥50% of accepted hits are real fintech companies (not content/gov/media) |
| **Query pattern** | `"fintech startup" careers "software engineer" USA` via existing `build_discovery_query` with keywords `["fintech startup", "careers", "software engineer"]`, `hiring_required=true`, industry=fintech, countries=USA |
| **Max SerpAPI searches** | **1** (pages=1, no pagination, no news) |
| **Timeout** | Consider `PROSPECTIQ_DISCOVERY_TIMEOUT_SECONDS=30` for experiment only — **not implemented**; note current 15s caused WS6.2B failure |
| **Pipeline** | Existing: discovery → fetch → research; no bypass |

### Expected candidate characteristics

- Accepted URLs: root domains or `/careers`/`/jobs` paths on commercial domains
- Rejected: gov, edu, media, `/resources`, `/think`, editorial subdomains
- Fetch may fail (403) on some careers sites — track separately from discovery quality

### Success criteria

| Outcome | Criteria |
|---------|----------|
| **Success** | ≥1 SerpAPI response received; ≥3 accepted candidates; ≥2 manually classifiable as `VALID_COMPANY` fintech firms; zero gov/media/content in accepted set |
| **Partial / inconclusive** | Response received but <3 accepted OR accepted set includes generic-keyword domains only OR all fetches fail |
| **Failure** | Timeout/zero results again OR accepted set majority content/gov/media (filter regression) |

### What to record

Query text, raw organic count, accepted/rejected counts, rejection reason breakdown, unique domains, fetch outcomes, signals, qualification, external opportunity fit (script heuristic), manual `VALID_COMPANY` classification per accepted hit.

**Do not execute without explicit quota authorization.**

---

## 15. V0 READINESS ASSESSMENT

| Area | Current State | Evidence | Remaining Gap |
|------|---------------|----------|---------------|
| Architecture | End-to-end pipeline wired; discovery → fetch → research | `docs/company-discovery.md`, code inspection | `ICPRuleset` not integrated |
| Provider integration | SerpAPI adapter functional; mocked tests pass | `test_discovery.py`, `serpapi_provider.py` | Live reliability (timeout in WS6.2B); no structured company attrs |
| Candidate validation | WS6.2B URL validator deployed | 8 unit tests + integration test | Live unproven; generic domains pass; title unused |
| ICP filtering | Query hints + metadata only | `PROVIDER_FIELD_SUPPORT` | No factual ICP enforcement post-discovery |
| Company verification | HTTP fetch of candidate URL | `CompanySourceIngestionService` | Employee/industry/geo often unverified; fetch failures common |
| Signal detection | 3 active rules (hiring, funding, expansion) | `domain/detection.py` | 3 deferred; no external-vendor signal |
| Scoring | SOP weights unchanged | `domain/scoring.py`, 136 tests | N/A |
| Qualification | ≥2 distinct buying signals | `domain/scoring.py:57` | Hiring-only leads may qualify without vendor fit |
| External opportunity fit | Script-only heuristic | `run_real_data_validation.py:434` | Not in production; not persisted |
| Provenance | Discovery + source evidence separated | `application/discovery.py:275` | Search snippet not used for signals |
| Compliance | No LinkedIn automation; permitted API | `docs/company-discovery.md` | Deferred person-level signals |
| Real-world discovery quality | WS6.2 poor; WS6.2B inconclusive | `docs/real-data-validation-report.md` | Live precision unproven |

---

## 16. RECOMMENDED NEXT WORKSTREAM

**RECOMMENDATION:** **WS6.2D — Controlled live re-validation (1 SerpAPI call) + query-family prototype in config only**

Smallest engineering workstream after this review, prioritized by impact:

### Priority 1 — Live proof (operations, not code)
- Execute WS6.2D experiment with 1 SerpAPI call when quota authorized.
- Manually classify accepted candidates (`VALID_COMPANY` vs false positive).
- Update `docs/real-data-validation-report.md`.

### Priority 2 — Minimal code (if Priority 1 confirms filter works)
- Add optional query-family selector or `-site:` hints in `build_discovery_query()` for company-discovery family (Family A/B) — **small, deterministic change**.
- Extend validation to reject `/docs`, `/developers`, `/partners` paths if live data shows false positives.
- Use SerpAPI title heuristics (e.g. reject titles containing "What is", "Definition", "Guide to") — requires careful unit tests.

### Priority 3 — Research-stage ICP (after discovery quality stable)
- Wire `ICPRuleset.evaluate_company()` into research or dossier output as **informational** checks (not hard reject) until company attributes are populated reliably.

### Explicitly defer
- Scoring / qualification changes
- LinkedIn automation
- New provider implementations
- Architecture rewrite
- News enablement until discovery precision baseline established

---

## Appendix — Files Inspected

| File | Purpose |
|------|---------|
| `backend/src/prospectiq/application/discovery.py` | Discovery orchestration |
| `backend/src/prospectiq/application/pipeline.py` | Fetch → research pipeline |
| `backend/src/prospectiq/application/research.py` | Signal detection + scoring trigger |
| `backend/src/prospectiq/application/ingestion.py` | Company source fetch |
| `backend/src/prospectiq/domain/discovery.py` | Models, statuses, normalization |
| `backend/src/prospectiq/domain/discovery_query.py` | Query construction |
| `backend/src/prospectiq/domain/discovery_candidate_validation.py` | Candidate validation |
| `backend/src/prospectiq/domain/detection.py` | Signal rules |
| `backend/src/prospectiq/domain/scoring.py` | Scoring / qualification |
| `backend/src/prospectiq/domain/signal.py` | Signal types / weights |
| `backend/src/prospectiq/domain/icp.py` | ICP ruleset (unwired) |
| `backend/src/prospectiq/infrastructure/discovery/serpapi_provider.py` | SerpAPI adapter |
| `backend/src/prospectiq/infrastructure/config.py` | Discovery settings |
| `backend/src/prospectiq/infrastructure/jobs.py` | Job retry semantics |
| `backend/src/prospectiq/worker/main.py` | Worker job handling |
| `scripts/run_real_data_validation.py` | Validation runner + external fit |
| `backend/tests/test_discovery.py` | Discovery tests |
| `backend/tests/test_discovery_candidate_validation.py` | Validation unit tests |
| `docs/company-discovery.md` | Discovery documentation |
| `docs/real-data-validation-report.md` | WS6.2 / WS6.2B results |

---

*This document describes existing implementation and recommended next steps. Recommendations are not implemented functionality unless explicitly labeled FACT or IMPLEMENTATION OBSERVATION.*
