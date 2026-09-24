from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from prospectiq.domain.common import TenantScope, utcnow
from prospectiq.domain.jobs import JobStatus, JobType, backoff_seconds
from prospectiq.infrastructure.jobs import InMemoryJobQueue


@pytest.mark.asyncio
async def test_enqueue_is_idempotent(scope: TenantScope) -> None:
    queue = InMemoryJobQueue()
    first = await queue.enqueue(scope, JobType.SCORE_LEAD, "score:lead-1", {"lead_id": "1"})
    second = await queue.enqueue(scope, JobType.SCORE_LEAD, "score:lead-1", {"lead_id": "1"})
    assert first.id == second.id
    assert len(queue.jobs) == 1


@pytest.mark.asyncio
async def test_claim_complete_and_retry_backoff(scope: TenantScope) -> None:
    queue = InMemoryJobQueue()
    await queue.enqueue(scope, JobType.RESEARCH_LEAD, "research:lead-1", {})
    now = utcnow()
    claimed = await queue.claim(worker_id="w1", now=now)
    assert claimed is not None
    assert claimed.status is JobStatus.LEASED
    assert claimed.attempts == 1
    failed = await queue.fail(claimed, "provider timeout", now=now)
    assert failed.status is JobStatus.FAILED
    assert failed.available_at == now + timedelta(seconds=backoff_seconds(1))
    not_ready = await queue.claim(worker_id="w1", now=now)
    assert not_ready is None
    later = await queue.claim(worker_id="w2", now=failed.available_at)
    assert later is not None
    await queue.complete(later)
    assert later.status is JobStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_dead_letter_after_max_attempts(scope: TenantScope) -> None:
    queue = InMemoryJobQueue()
    job = await queue.enqueue(scope, JobType.FETCH_SOURCE, "fetch:1", {})
    job.max_attempts = 2
    now = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
    for _ in range(2):
        claimed = await queue.claim(worker_id="w1", now=now)
        assert claimed is not None
        await queue.fail(claimed, "boom", now=now)
        now = claimed.available_at
    assert claimed.status is JobStatus.DEAD
