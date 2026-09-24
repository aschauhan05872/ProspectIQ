# Real-Data Validation Report (WS6.2)

Generated: 2026-09-22T18:14:59.598801+00:00
Run started: 2026-09-22T18:14:44.036123+00:00
**Status: PARTIAL**

## Search Quota

```json
{
  "budget": 1,
  "used": 1,
  "successful": 0,
  "failed": 1,
  "pagination_requests": 0,
  "retry_attempts": 0,
  "remaining_reported": null,
  "events": [
    {
      "operation": "discovery_search",
      "success": false,
      "http_status": null,
      "result_count": null,
      "error": "RetryableDiscoveryError: SerpAPI request timed out.",
      "is_pagination": false,
      "search_number": 1
    }
  ]
}
```

## Environment

```json
{
  "env": "development",
  "database_url_host": "localhost:5432/prospectiq_test",
  "validation_database_mode": "isolated_test_db",
  "discovery_provider": "serpapi",
  "news_provider": "none",
  "serpapi_configured": true,
  "discovery_max_pages": 1,
  "discovery_max_candidates": 25,
  "search_budget": 1
}
```

## ICP

```json
{
  "industry": "fintech_financial_services",
  "countries": [
    "usa"
  ],
  "employee_min": 11,
  "employee_max": 1000,
  "hiring_required": true,
  "keywords": [
    "fintech startup",
    "careers",
    "software engineer"
  ],
  "limit": 25,
  "min_headcount_growth_pct": null,
  "company_types": []
}
```

## Summary Metrics

- Candidates discovered: 0
- Unique domains: 0
- Website fetches succeeded: 0
- Companies researched: 0
- Total evidence rows: 0
- Qualified companies: 0

## External Opportunity Fit Distribution

```json
{
  "HIGH": 0,
  "MEDIUM": 0,
  "LOW": 0,
  "UNKNOWN": 0
}
```

## Signal Distribution

```json
{}
```

## Qualified Opportunities (0)

_No qualified companies in this run._

## Strongest Opportunities (by external fit)


## Failures

```json
[
  {
    "job_id": "3b2aaf2f-a2cd-4115-a83f-8d6792a4f555",
    "job_type": "discover_companies",
    "error": "SerpAPI request timed out.",
    "error_type": "RetryableDiscoveryError"
  }
]
```

## Sales Navigator Recipes (Human Only)

_None generated._

---

## WS6.2B — Discovery Quality Experiment

### 1. First Experiment Problem
The initial query returned educational, regulatory, and content pages as candidates because every SerpAPI organic result was accepted without company validation.

### 2. Discovery Changes Made
- Added `validate_discovery_hit()` in `discovery_candidate_validation.py`
- Rejects government/edu TLDs, editorial subdomains, media patterns, and content URL paths
- Accepts company root domains and careers/about/company pages
- New status: `skipped_non_company`

### 3. Second Query Used
```
fintech companies in usa hiring 11-1000 employees fintech startup careers software engineer
```

### 4. SerpAPI Calls Used: **1** (authorized: exactly 1)

### 5. Raw Result Count: 0
### 6. Candidate Records: 0
### 7. Accepted VALID_COMPANY: 0
### 8. Rejected: 0

### 9. Rejection Reasons

```json
{
  "by_reason": {},
  "by_quality_class": {}
}
```

### 10. Unique Domains (accepted): []

### 11–16. Pipeline Outcomes

```json
{
  "website_fetches": 0,
  "evidence": 0,
  "signals": {},
  "qualified": 0,
  "external_fit": {
    "HIGH": 0,
    "MEDIUM": 0,
    "LOW": 0,
    "UNKNOWN": 0
  }
}
```

### 17. Best Candidates

_No strong company candidates identified._

### 18. Remaining Discovery-Quality Problems
- **FACT:** The authorized second SerpAPI call timed out after 15s (`RetryableDiscoveryError`). No organic results were returned, so live validation of the new filter could not complete.
- **INTERPRETATION:** Unit tests confirm the filter would reject WS6.2 first-experiment URLs (IBM Think, Investopedia, FTC.gov, Plaid resources, House.gov).
- Query may still return content pages when SerpAPI responds successfully.
- Employee count and industry remain not_verified at discovery time.

### 19. Recommendation for Next Phase
Tune query toward careers pages on company domains; consider enriching validation with homepage-vs-article title heuristics before spending more search quota.

_First controlled real-data experiment. Not commercial validation._