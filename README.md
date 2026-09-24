# ProspectIQ

Internal V0 of the **AI Lead Intelligence Engine**.

The intelligence core is independent of the UI so the same engine can later serve a multi-tenant SaaS application and an MCP/API layer. LinkedIn execution stays human-controlled.

## Architecture

See [docs/architecture.md](docs/architecture.md). Product source of truth: [docs/ProspectIQ_Technical_Design_Document_v0.1.md](docs/ProspectIQ_Technical_Design_Document_v0.1.md). Document authority: [docs/source-documents.md](docs/source-documents.md).

## Stack (TDD)

- Python / FastAPI modular monolith
- PostgreSQL
- Redis as optional job notify; Postgres is the durable job store
- React / Next.js workspace
- Docker Compose for local infrastructure

## Quick start

```powershell
copy .env.example .env
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -m "not integration"
ruff check src tests
mypy src
```

### PostgreSQL integration tests

Integration tests use a dedicated database (`prospectiq_test` by default). Create it once, then run migrations and integration tests:

```powershell
docker compose up -d postgres
# In psql: CREATE DATABASE prospectiq_test OWNER prospectiq;
cd backend
$env:PROSPECTIQ_DATABASE_URL="postgresql+asyncpg://prospectiq:prospectiq@localhost:5432/prospectiq_test"
alembic upgrade head
pytest -m integration
```

Start local infrastructure, then migrate and run the API:

```powershell
docker compose up -d postgres redis
cd backend
alembic upgrade head
uvicorn prospectiq.api.main:app --reload --host 0.0.0.0 --port 8000
```

Worker (separate process):

```powershell
python -m prospectiq.worker.main
```

Frontend workspace (placeholder UI; the engine does not depend on it):

```powershell
cd frontend
npm install
npm run dev
```

## Company source ingestion

Submit one public company URL. The worker fetches that URL only (no crawl, no LinkedIn):

```http
POST /sources/company
{ "url": "https://example.com" }
```

Details: [docs/company-source-ingestion.md](docs/company-source-ingestion.md).

## Company research / signal detection

After evidence exists, enqueue deterministic research (no network, no LLM):

```http
POST /research/company
{ "company_id": "<uuid>" }
```

```http
GET /research/company/{company_id}
```

Details: [docs/signal-detection.md](docs/signal-detection.md).

## Operator read APIs (internal V0)

Read-only endpoints for inspecting pipeline state and lead dossiers:

```http
GET /operator/candidates?status=research_queued&limit=50
GET /operator/leads?qualified=true&classification=hot
GET /operator/leads/{lead_id}/dossier
GET /operator/companies/{company_id}/dossier
```

Optional news/funding ingestion (SerpAPI Google News when configured):

```env
PROSPECTIQ_NEWS_PROVIDER=serpapi
PROSPECTIQ_SERPAPI_API_KEY=your-key
```

## Company discovery

Discover candidate companies from a configured permitted search API, then enqueue existing website ingestion:

```http
POST /discovery/companies
{
  "industry": "healthtech",
  "countries": ["USA"],
  "employee_min": 11,
  "employee_max": 1000,
  "hiring_required": true,
  "limit": 20
}
```

Details: [docs/company-discovery.md](docs/company-discovery.md).

## What is implemented

- Domain models and SOP-faithful scoring / ICP / follow-up rules
- Permitted company website / careers HTTP ingestion
- Deterministic `HIRING_TECH_ROLES` detection from stored careers evidence
- Lead scoring / qualification through the existing `LeadScoringService`
- Permitted company discovery through a configurable provider (SerpAPI adapter)
- Provider, AI, and job ports
- Tenant-scoped persistence schema and Alembic migrations
- FastAPI health/readiness, route-group stubs, `POST /sources/company`, `/research/company`, and `/discovery/companies`
- Worker `FETCH_SOURCE`, `RESEARCH_LEAD`, and `DISCOVER_COMPANIES` handlers
- Unit tests that do not require external websites

## What is not implemented

AI research/drafts, LinkedIn or funding/expansion signals, lead dossier UI, Telegram/email delivery, SaaS auth/billing, MCP, and LinkedIn automation.
