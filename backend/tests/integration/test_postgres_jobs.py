"""Phase 1–2: PostgreSQL job persistence, idempotency, and claiming."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from prospectiq.domain.common import utcnow
from prospectiq.domain.jobs import JobStatus, JobType
from prospectiq.infrastructure.config import Settings
from prospectiq.infrastructure.jobs import PostgresJobQueue


@pytest.mark.integration
async def test_job_insert_and_idempotent_enqueue(
    db_session: AsyncSession,
    tenant_scope: object,
    integration_settings: Settings,
) -> None:
    queue = PostgresJobQueue(db_session)
    key = f"integration:{uuid4()}"
    first = await queue.enqueue(
        tenant_scope,  # type: ignore[arg-type]
        JobType.FETCH_SOURCE,
        key,
        {"url": "https://example.test"},
    )
    second = await queue.enqueue(
        tenant_scope,  # type: ignore[arg-type]
        JobType.FETCH_SOURCE,
        key,
        {"url": "https://example.test"},
    )
    assert first.id == second.id
    assert second.extra.get("idempotent_replay") is True
    await db_session.commit()


@pytest.mark.integration
async def test_concurrent_claim_only_one_worker_gets_job(
    db_session: AsyncSession,
    tenant_scope: object,
    integration_settings: Settings,
) -> None:
    queue = PostgresJobQueue(db_session)
    key = f"concurrent:{uuid4()}"
    enqueued = await queue.enqueue(
        tenant_scope,  # type: ignore[arg-type]
        JobType.RESEARCH_LEAD,
        key,
        {"company_id": str(uuid4())},
    )
    expected_job_id = enqueued.id
    await db_session.commit()

    engine = create_async_engine(integration_settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    now = utcnow()

    async def claim(worker: str) -> object | None:
        async with factory() as session:
            q = PostgresJobQueue(session)
            job = await q.claim(worker_id=worker, now=now)
            if job is not None:
                await session.commit()
            return job

    claimed_a, claimed_b = await asyncio.gather(claim("w-a"), claim("w-b"))
    await engine.dispose()

    claims = [(claimed_a, "w-a"), (claimed_b, "w-b")]
    winners = [
        worker for job, worker in claims if job is not None and job.id == expected_job_id
    ]
    assert len(winners) == 1, "exactly one worker must claim the enqueued job"
    assert sum(1 for job, _ in claims if job is None) == 1, "the other worker must get no job"
    for job, _ in claims:
        if job is not None:
            assert job.id == expected_job_id
            assert job.status is JobStatus.LEASED
