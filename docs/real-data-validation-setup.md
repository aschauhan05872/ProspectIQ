# Real-data validation setup (WS6.1)

This document explains why `prospectiq` / `prospectiq` authentication fails on a typical Windows dev machine and how to establish a reproducible validation environment **without changing application credentials**.

## Expected configuration

| Setting | Value |
|---|---|
| User | `prospectiq` |
| Password | `prospectiq` |
| Database | `prospectiq` |
| Test database | `prospectiq_test` |
| Port (default) | `5432` |

Source: `docker-compose.yml`, `.env.example`, `backend/alembic.ini`.

## Diagnosed failure mode (this environment)

1. **Docker CLI is not installed** — `docker compose up -d postgres` cannot run.
2. **Port 5432 is already in use** by `postgresql-x64-18` (PostgreSQL 18 Windows service).
3. **The `prospectiq` role does not exist** on that PostgreSQL 18 instance.
4. Connection attempts with `prospectiq:prospectiq` return `InvalidPasswordError` (not connection refused).
5. **`PROSPECTIQ_SERPAPI_API_KEY` is not set** — live SerpAPI discovery/news cannot run.

Run the diagnostic script:

```powershell
.\scripts\diagnose_postgres_environment.ps1
```

## Remediation path A — Docker Compose (recommended by project)

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/).
2. If port 5432 is occupied, either stop the local PostgreSQL 18 service **or** change `docker-compose.yml` postgres mapping to `"5433:5432"` and set:

   ```powershell
   $env:PROSPECTIQ_DATABASE_URL="postgresql+asyncpg://prospectiq:prospectiq@localhost:5433/prospectiq"
   $env:PROSPECTIQ_TEST_DATABASE_URL="postgresql+asyncpg://prospectiq:prospectiq@localhost:5433/prospectiq_test"
   ```

3. Start Postgres:

   ```powershell
   docker compose up -d postgres
   ```

4. Migrate and test:

   ```powershell
   cd backend
   alembic upgrade head
   pytest -m integration
   ```

## Remediation path B — Local PostgreSQL 18

1. Connect as superuser:

   ```powershell
   & "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d postgres
   ```

2. Run `scripts/setup_prospectiq_postgres.sql`.

3. Migrate and test (same as path A step 4).

## Live SerpAPI validation

Copy `.env.example` to `.env` and set:

```env
PROSPECTIQ_DISCOVERY_PROVIDER=serpapi
PROSPECTIQ_SERPAPI_API_KEY=<your-key>
PROSPECTIQ_NEWS_PROVIDER=serpapi
```

Controlled discovery request:

```http
POST /discovery/companies
{
  "industry": "healthtech",
  "countries": ["USA"],
  "employee_min": 11,
  "employee_max": 1000,
  "hiring_required": true,
  "limit": 5
}
```

Run API + worker, then inspect dossiers:

```http
GET /operator/candidates
GET /operator/companies/{company_id}/dossier
```

## What WS6.1 validates (no new features)

- PostgreSQL schema + migrations
- Job claim idempotency (`FOR UPDATE SKIP LOCKED`)
- Repository persistence + tenant isolation
- Live discovery → fetch → optional news → research → scoring
- Signal quality (hiring, funding, expansion) against real evidence
- False positive / freshness documentation

Do **not** modify detectors during validation. Document issues as P0–P3 for a follow-up workstream.
