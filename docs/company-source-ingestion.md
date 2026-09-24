# Company website / careers ingestion (V0)

This is the first permitted external-data path. It fetches **one explicitly supplied HTTP(S) URL**. It does not crawl, does not scrape LinkedIn, and does not score leads.

## Flow

```text
POST /sources/company { "url": "https://example.com" }
        ↓
Validate / normalize URL (domain)
        ↓
Enqueue FETCH_SOURCE (Postgres job, tenant + normalized URL idempotency key)
        ↓
Worker claims job
        ↓
SSRF-safe HTTP GET of that URL only
        ↓
HTML / text normalization
        ↓
Upsert Company (identity = host without www)
        ↓
Upsert CompanySource + SOURCE_DERIVED Evidence
        ↓
Job succeeded
```

## Supported sources

| Source class | When |
|---|---|
| `company_website` | Default public company page |
| `careers_page` | Path contains careers/jobs markers (`/careers`, `/jobs`, …) |

LinkedIn hosts are rejected at validation. Official LinkedIn remains disabled.

## Security restrictions

Configured in `.env` (`PROSPECTIQ_FETCH_*`):

- HTTP/HTTPS only; no credentials in the URL
- Connection / read / total timeouts
- Max response size and max redirects
- Redirect targets are re-validated
- Localhost, loopback, private, link-local, and metadata addresses are blocked
- DNS results are checked before the request
- Response bodies, cookies, and secrets are not logged
- `trust_env=False` so ambient proxies are not used accidentally

## Provenance

Each evidence row is `origin=source_derived` and stores source class, normalized URL, collection time, confidence, snippet, and HTTP metadata (status, final URL, title). AI is not called.

Hiring phrases found on a careers page are stored as `fact_kind=hiring_language_observed`. That observation is not itself a SOP buying signal. Company research (`POST /research/company`) may later detect `HIRING_TECH_ROLES` from that careers evidence when open-role language and a documented tech title are both present. See [signal-detection.md](./signal-detection.md).

## Jobs

- Type: `FETCH_SOURCE` (existing enum)
- Idempotency key: `fetch_source:{normalized_url}`
- Retryable: timeouts, DNS/network, 408/429/5xx
- Permanent (dead-letter): invalid URL, SSRF, 4xx, unsupported content type, oversized body

Re-submitting the same normalized URL returns the existing job.

## Local run

```powershell
copy .env.example .env
cd backend
alembic upgrade head
uvicorn prospectiq.api.main:app --reload
python -m prospectiq.worker.main
```

```http
POST /sources/company
{ "url": "https://example.com" }
```

## Tests

```powershell
cd backend
pytest tests/test_source_url.py tests/test_http_fetch.py tests/test_html_normalize.py tests/test_ingestion.py
```

HTTP is mocked. These tests do not call third-party websites. Applying the unique-constraint migration requires PostgreSQL.
