# ProspectIQ PostgreSQL environment diagnostic (WS6.1)
# Read-only checks — does not modify credentials or database state.

Write-Host "=== ProspectIQ PostgreSQL Diagnostic ===" -ForegroundColor Cyan

$expectedUser = "prospectiq"
$expectedPassword = "prospectiq"
$expectedDb = "prospectiq"
$expectedTestDb = "prospectiq_test"
$port = 5432

Write-Host "`n[1] Docker CLI"
if (Get-Command docker -ErrorAction SilentlyContinue) {
    Write-Host "  docker: available"
    docker compose version 2>$null
} else {
    Write-Host "  docker: NOT FOUND"
    Write-Host "  -> Docker Compose postgres (prospectiq/prospectiq) cannot be started."
}

Write-Host "`n[2] Local PostgreSQL service"
$pgService = Get-Service -Name "*postgres*" -ErrorAction SilentlyContinue
if ($pgService) {
    foreach ($svc in $pgService) {
        Write-Host "  $($svc.Name): $($svc.Status)"
    }
} else {
    Write-Host "  No PostgreSQL Windows service found."
}

Write-Host "`n[3] Port $port listener"
$conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) {
    Write-Host "  Port $port is in use (PID $($conn.OwningProcess))"
} else {
    Write-Host "  Port $port is not listening."
}

Write-Host "`n[4] psql client"
$psql = "C:\Program Files\PostgreSQL\18\bin\psql.exe"
if (Test-Path $psql) {
    Write-Host "  Found: $psql"
} else {
    Write-Host "  psql not found at default PG18 path."
}

Write-Host "`n[5] Expected credential probe (prospectiq/prospectiq)"
$backend = Join-Path $PSScriptRoot "..\backend"
$python = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}
& $python -c @"
import asyncio, asyncpg
async def main():
    try:
        c = await asyncpg.connect(host='localhost', port=$port, user='$expectedUser', password='$expectedPassword', database='postgres', timeout=3)
        print('  AUTH OK for prospectiq user')
        await c.close()
    except asyncpg.InvalidPasswordError:
        print('  AUTH FAIL: password authentication failed for user prospectiq')
        print('  -> prospectiq role likely does not exist on this PostgreSQL instance,')
        print('     or password differs from Docker Compose default.')
    except Exception as e:
        print(f'  ERROR: {type(e).__name__}: {e}')
asyncio.run(main())
"@

Write-Host "`n[6] Environment variables"
if ($env:PROSPECTIQ_DATABASE_URL) { Write-Host "  PROSPECTIQ_DATABASE_URL: set" } else { Write-Host "  PROSPECTIQ_DATABASE_URL: not set" }
if ($env:PROSPECTIQ_TEST_DATABASE_URL) { Write-Host "  PROSPECTIQ_TEST_DATABASE_URL: set" } else { Write-Host "  PROSPECTIQ_TEST_DATABASE_URL: not set" }
if ($env:PROSPECTIQ_SERPAPI_API_KEY) { Write-Host "  PROSPECTIQ_SERPAPI_API_KEY: set" } else { Write-Host "  PROSPECTIQ_SERPAPI_API_KEY: not set" }

Write-Host "`n[7] Root cause summary"
Write-Host @"
  The project expects PostgreSQL with user/db/password: prospectiq/prospectiq/prospectiq
  (see docker-compose.yml and .env.example).

  On this machine, port 5432 is served by a separate PostgreSQL 18 Windows installation,
  NOT the Docker Compose container. The prospectiq role has not been created there.

  Remediation options (choose one):
    A) Install Docker Desktop, map postgres to port 5433 if 5432 is occupied, set
       PROSPECTIQ_DATABASE_URL accordingly, run: docker compose up -d postgres
    B) As postgres superuser on PG18, run scripts/setup_prospectiq_postgres.sql
    C) Stop local PG18, use Docker Compose on port 5432

  See docs/real-data-validation-setup.md for full steps.
"@ -ForegroundColor Yellow
