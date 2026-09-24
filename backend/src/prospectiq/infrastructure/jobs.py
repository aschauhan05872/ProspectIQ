"""Durable job queue: PostgreSQL is the system of record; Redis is optional notify."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from prospectiq.domain.common import JobId, TenantId, TenantScope, utcnow
from prospectiq.domain.jobs import (
    DEFAULT_LEASE_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    Job,
    JobStatus,
    JobType,
    next_available_at,
)
from prospectiq.infrastructure.logging import get_logger
from prospectiq.infrastructure.models import JobRow

logger = get_logger("prospectiq.jobs")


class PostgresJobQueue:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(
        self,
        scope: TenantScope,
        job_type: JobType,
        idempotency_key: str,
        payload: dict[str, Any],
    ) -> Job:
        now = utcnow()
        job_id = uuid4()
        stmt = (
            insert(JobRow)
            .values(
                id=job_id,
                tenant_id=scope.tenant_id,
                job_type=job_type.value,
                idempotency_key=idempotency_key,
                payload=payload,
                status=JobStatus.PENDING.value,
                attempts=0,
                max_attempts=DEFAULT_MAX_ATTEMPTS,
                available_at=now,
                leased_until=None,
                last_error=None,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(constraint="uq_jobs_tenant_idempotency")
            .returning(JobRow.id)
        )
        result = await self._session.execute(stmt)
        inserted_id = result.scalar_one_or_none()
        if inserted_id is None:
            existing = await self._session.execute(
                select(JobRow).where(
                    JobRow.tenant_id == scope.tenant_id,
                    JobRow.idempotency_key == idempotency_key,
                )
            )
            row = existing.scalar_one()
            logger.info(
                "job_enqueue_idempotent_hit",
                tenant_id=str(scope.tenant_id),
                job_type=job_type.value,
                idempotency_key=idempotency_key,
                job_id=str(row.id),
            )
            existing_job = _job_from_row(row)
            existing_job.extra["idempotent_replay"] = True
            return existing_job
        inserted = await self._session.get(JobRow, inserted_id)
        if inserted is None:
            raise RuntimeError("Job insert succeeded but the row could not be loaded.")
        row = inserted
        logger.info(
            "job_enqueued",
            tenant_id=str(scope.tenant_id),
            job_type=job_type.value,
            idempotency_key=idempotency_key,
            job_id=str(row.id),
        )
        return _job_from_row(row)

    async def claim(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> Job | None:
        stmt: Select[tuple[JobRow]] = (
            select(JobRow)
            .where(
                JobRow.status.in_([JobStatus.PENDING.value, JobStatus.FAILED.value]),
                JobRow.available_at <= now,
            )
            .order_by(JobRow.available_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        row.status = JobStatus.LEASED.value
        row.attempts += 1
        row.leased_until = now + timedelta(seconds=lease_seconds)
        row.updated_at = now
        logger.info(
            "job_claimed",
            job_id=str(row.id),
            tenant_id=str(row.tenant_id),
            job_type=row.job_type,
            worker_id=worker_id,
            attempt=row.attempts,
        )
        return _job_from_row(row)

    async def complete(self, job: Job) -> None:
        row = await self._session.get(JobRow, job.id)
        if row is None:
            return
        row.status = JobStatus.SUCCEEDED.value
        row.updated_at = utcnow()
        row.last_error = None
        logger.info("job_succeeded", job_id=str(job.id), tenant_id=str(job.tenant_id))

    async def fail(
        self, job: Job, error: str, *, now: datetime, permanent: bool = False
    ) -> Job:
        row = await self._session.get(JobRow, job.id)
        if row is None:
            job.status = JobStatus.DEAD
            job.last_error = error
            return job
        row.last_error = error
        row.updated_at = now
        if permanent or row.attempts >= row.max_attempts:
            row.status = JobStatus.DEAD.value
        else:
            row.status = JobStatus.FAILED.value
            row.available_at = next_available_at(row.attempts, now=now)
        logger.warning(
            "job_failed",
            job_id=str(job.id),
            tenant_id=str(job.tenant_id),
            attempts=row.attempts,
            status=row.status,
            error=error,
        )
        return _job_from_row(row)


class InMemoryJobQueue:
    """Test/dev queue with the same idempotency and retry semantics."""

    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}

    def _key(self, tenant_id: TenantId, idempotency_key: str) -> str:
        return f"{tenant_id}:{idempotency_key}"

    async def enqueue(
        self,
        scope: TenantScope,
        job_type: JobType,
        idempotency_key: str,
        payload: dict[str, Any],
    ) -> Job:
        key = self._key(scope.tenant_id, idempotency_key)
        existing = self.jobs.get(key)
        if existing is not None:
            existing.extra["idempotent_replay"] = True
            return existing
        now = utcnow()
        job = Job(
            id=JobId(uuid4()),
            tenant_id=scope.tenant_id,
            job_type=job_type,
            idempotency_key=idempotency_key,
            payload=payload,
            status=JobStatus.PENDING,
            attempts=0,
            max_attempts=DEFAULT_MAX_ATTEMPTS,
            available_at=now,
            leased_until=None,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
        self.jobs[key] = job
        return job

    async def claim(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> Job | None:
        candidates = [
            job
            for job in self.jobs.values()
            if job.status in {JobStatus.PENDING, JobStatus.FAILED} and job.available_at <= now
        ]
        if not candidates:
            return None
        job = sorted(candidates, key=lambda item: item.available_at)[0]
        job.status = JobStatus.LEASED
        job.attempts += 1
        job.leased_until = now + timedelta(seconds=lease_seconds)
        job.updated_at = now
        job.extra["worker_id"] = worker_id
        return job

    async def complete(self, job: Job) -> None:
        job.status = JobStatus.SUCCEEDED
        job.updated_at = utcnow()
        job.last_error = None

    async def fail(
        self, job: Job, error: str, *, now: datetime, permanent: bool = False
    ) -> Job:
        job.last_error = error
        job.updated_at = now
        if permanent or job.attempts >= job.max_attempts:
            job.status = JobStatus.DEAD
        else:
            job.status = JobStatus.FAILED
            job.available_at = next_available_at(job.attempts, now=now)
        return job


def _job_from_row(row: JobRow) -> Job:
    return Job(
        id=JobId(row.id),
        tenant_id=TenantId(row.tenant_id),
        job_type=JobType(row.job_type),
        idempotency_key=row.idempotency_key,
        payload=row.payload,
        status=JobStatus(row.status),
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        available_at=row.available_at,
        leased_until=row.leased_until,
        last_error=row.last_error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
