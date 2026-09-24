"""PostgreSQL integration test fixtures.

Uses PROSPECTIQ_TEST_DATABASE_URL when set, otherwise the Docker Compose default
against database ``prospectiq_test``. Tests skip when PostgreSQL is unavailable.

Create the test database once (example):

    CREATE DATABASE prospectiq_test OWNER prospectiq;
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from functools import lru_cache
from urllib.parse import urlparse
from uuid import UUID

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from prospectiq.domain.common import TenantId, TenantScope, WorkspaceId
from prospectiq.infrastructure.config import Settings
from prospectiq.infrastructure.db import dispose_engine

DEFAULT_TEST_DB = "prospectiq_test"
DEFAULT_TEST_URL = (
    "postgresql+asyncpg://prospectiq:prospectiq@localhost:5432/prospectiq_test"
)

TENANT_A = TenantId(UUID("00000000-0000-0000-0000-000000000001"))
TENANT_B = TenantId(UUID("00000000-0000-0000-0000-000000000099"))
WORKSPACE_A = WorkspaceId(UUID("00000000-0000-0000-0000-000000000002"))
NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)

# Application tables populated by integration tests. Truncated before each test so
# committed rows from prior tests cannot leak (session.rollback() alone is not enough).
INTEGRATION_DATA_TABLES = (
    "jobs",
    "research_pages",
    "company_research_cases",
    "imported_prospects",
    "import_batches",
    "audit_events",
    "notifications",
    "follow_up_tasks",
    "activities",
    "message_drafts",
    "research_runs",
    "lead_scores",
    "leads",
    "signals",
    "evidence",
    "person_sources",
    "persons",
    "company_sources",
    "discovery_candidates",
    "companies",
    "search_profiles",
    "users",
    "workspaces",
    "source_policies",
    "tenants",
)


async def _truncate_integration_data(engine: object) -> None:
    tables = ", ".join(INTEGRATION_DATA_TABLES)
    async with engine.begin() as conn:  # type: ignore[union-attr]
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


def test_database_url() -> str:
    return os.environ.get("PROSPECTIQ_TEST_DATABASE_URL", DEFAULT_TEST_URL)


def _asyncpg_dsn(sqlalchemy_url: str) -> str:
    parsed = urlparse(sqlalchemy_url.replace("+asyncpg", ""))
    return (
        f"postgresql://{parsed.username}:{parsed.password}@"
        f"{parsed.hostname}:{parsed.port or 5432}{parsed.path}"
    )


@lru_cache(maxsize=1)
def _postgres_reachable() -> bool:
    url = test_database_url()
    admin_dsn = _asyncpg_dsn(url.rsplit("/", 1)[0] + "/postgres")
    try:
        import asyncio

        async def _check() -> bool:
            conn = await asyncpg.connect(admin_dsn, timeout=3)
            try:
                await conn.close()
                return True
            except Exception:
                return False

        return asyncio.run(_check())
    except Exception:
        return False


async def _ensure_test_database() -> None:
    base_url = test_database_url()
    admin_dsn = _asyncpg_dsn(base_url.rsplit("/", 1)[0] + "/postgres")
    conn = await asyncpg.connect(admin_dsn, timeout=5)
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", DEFAULT_TEST_DB
        )
        if not exists:
            await conn.execute(f'CREATE DATABASE "{DEFAULT_TEST_DB}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def postgres_available() -> bool:
    if not _postgres_reachable():
        return False
    import asyncio

    try:
        asyncio.run(_ensure_test_database())
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def integration_settings(postgres_available: bool) -> Settings:
    if not postgres_available:
        pytest.skip("PostgreSQL is not available for integration tests.")
    os.environ["PROSPECTIQ_DATABASE_URL"] = test_database_url()
    from prospectiq.infrastructure.config import get_settings

    get_settings.cache_clear()
    import asyncio

    asyncio.run(dispose_engine())
    return get_settings()


@pytest.fixture(scope="session")
def migrated_schema(integration_settings: Settings) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", integration_settings.database_url)
    command.upgrade(cfg, "head")


@pytest.fixture
async def db_session(
    integration_settings: Settings,
    migrated_schema: None,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncSession]:
    monkeypatch.setattr("prospectiq.domain.common.utcnow", lambda: NOW)
    monkeypatch.setattr("prospectiq.domain.jobs.utcnow", lambda: NOW)
    engine = create_async_engine(integration_settings.database_url, pool_pre_ping=True)
    await _truncate_integration_data(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest.fixture
async def seeded_tenant(db_session: AsyncSession) -> TenantScope:
    await db_session.execute(
        text(
            """
            INSERT INTO tenants (id, name, slug, created_at, updated_at)
            VALUES (:id, 'Internal', 'internal', :now, :now)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"id": TENANT_A, "now": NOW},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO workspaces (id, tenant_id, name, created_at, updated_at)
            VALUES (:id, :tenant_id, 'Default', :now, :now)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"id": WORKSPACE_A, "tenant_id": TENANT_A, "now": NOW},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO tenants (id, name, slug, created_at, updated_at)
            VALUES (:id, 'Other', 'other', :now, :now)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"id": TENANT_B, "now": NOW},
    )
    await db_session.flush()
    return TenantScope(tenant_id=TENANT_A, workspace_id=WORKSPACE_A, request_id="integration")


@pytest.fixture
def tenant_scope(seeded_tenant: TenantScope) -> TenantScope:
    return seeded_tenant
