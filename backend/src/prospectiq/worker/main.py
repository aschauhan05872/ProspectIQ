"""Worker loop: claim durable jobs, run handlers, retry with backoff."""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Awaitable, Callable
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from prospectiq.domain.common import utcnow
from prospectiq.domain.company_research import (
    PermanentCompanyResearchError,
    RetryableCompanyResearchError,
)
from prospectiq.domain.discovery import PermanentDiscoveryError, RetryableDiscoveryError
from prospectiq.domain.ingestion import PermanentSourceError, RetryableSourceError
from prospectiq.domain.jobs import DEFAULT_LEASE_SECONDS, Job, JobType
from prospectiq.domain.news import PermanentNewsError, RetryableNewsError
from prospectiq.domain.prospect_import import ProspectImportError
from prospectiq.infrastructure.company_research_runtime import build_company_research_service
from prospectiq.infrastructure.config import Settings, get_settings
from prospectiq.infrastructure.db import dispose_engine, get_session_factory
from prospectiq.infrastructure.discovery_runtime import build_discovery_service
from prospectiq.infrastructure.import_runtime import build_prospect_import_service
from prospectiq.infrastructure.ingestion_runtime import build_ingestion_service
from prospectiq.infrastructure.jobs import PostgresJobQueue
from prospectiq.infrastructure.logging import configure_logging, get_logger
from prospectiq.infrastructure.news_runtime import build_news_service
from prospectiq.infrastructure.pipeline_runtime import build_pipeline_service
from prospectiq.infrastructure.research_runtime import build_research_service

logger = get_logger("prospectiq.worker")

JobHandler = Callable[[Job], Awaitable[None]]


async def handle_job(job: Job, *, session: AsyncSession, settings: Settings) -> None:
    logger.info(
        "job_handler_started",
        job_id=str(job.id),
        tenant_id=str(job.tenant_id),
        job_type=job.job_type.value,
        attempt=job.attempts,
    )
    pipeline = build_pipeline_service(session, settings)
    scope = pipeline.scope_for_job(job)
    if job.job_type is JobType.FETCH_SOURCE:
        ingestion = build_ingestion_service(session, settings)
        fetch_result = await ingestion.execute_job(job)
        await pipeline.after_fetch_succeeded(scope, job, fetch_result)
        return
    if job.job_type is JobType.FETCH_COMPANY_NEWS:
        news = build_news_service(session, settings)
        news_result = await news.execute_job(job)
        await pipeline.after_news_succeeded(scope, job, news_result)
        return
    if job.job_type is JobType.RESEARCH_LEAD:
        research = build_research_service(session)
        research_result = await research.execute_job(job)
        await pipeline.after_research_succeeded(scope, job, research_result)
        return
    if job.job_type is JobType.DISCOVER_COMPANIES:
        discovery = build_discovery_service(session, settings)
        await discovery.execute_job(job)
        return
    if job.job_type is JobType.IMPORT_PROSPECTS:
        importer = build_prospect_import_service(session)
        await importer.execute_job(job)
        return
    if job.job_type is JobType.RESEARCH_COMPANY:
        company_research = build_company_research_service(session, settings)
        await company_research.execute_job(job)
        return
    return


async def worker_loop(*, poll_seconds: float = 2.0) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    worker_id = f"worker-{uuid4()}"
    factory = get_session_factory(settings)
    logger.info("worker_starting", worker_id=worker_id, env=settings.env)
    stopping = False

    def _stop(*_: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    while not stopping:
        async with factory() as session:
            queue = PostgresJobQueue(session)
            job = await queue.claim(
                worker_id=worker_id,
                now=utcnow(),
                lease_seconds=DEFAULT_LEASE_SECONDS,
            )
            if job is None:
                await session.commit()
            else:
                try:
                    await handle_job(job, session=session, settings=settings)
                    await queue.complete(job)
                    await session.commit()
                except Exception as exc:
                    permanent = isinstance(
                        exc,
                        (
                            PermanentSourceError,
                            PermanentDiscoveryError,
                            PermanentNewsError,
                            ProspectImportError,
                            PermanentCompanyResearchError,
                        ),
                    )
                    retryable = isinstance(
                        exc,
                        (
                            RetryableSourceError,
                            RetryableDiscoveryError,
                            RetryableNewsError,
                            RetryableCompanyResearchError,
                        ),
                    )
                    await session.rollback()
                    async with factory() as fail_session:
                        if permanent and job.job_type in {
                            JobType.FETCH_SOURCE,
                            JobType.FETCH_COMPANY_NEWS,
                            JobType.RESEARCH_LEAD,
                        }:
                            fail_pipeline = build_pipeline_service(fail_session, settings)
                            fail_scope = fail_pipeline.scope_for_job(job)
                            if job.job_type is JobType.FETCH_SOURCE:
                                await fail_pipeline.after_fetch_failed(
                                    fail_scope, job, permanent=True
                                )
                            elif job.job_type is JobType.FETCH_COMPANY_NEWS:
                                await fail_pipeline.after_news_failed(
                                    fail_scope, job, permanent=True
                                )
                            else:
                                await fail_pipeline.after_research_failed(
                                    fail_scope, job, permanent=True
                                )
                        fail_queue = PostgresJobQueue(fail_session)
                        await fail_queue.fail(
                            job,
                            str(exc),
                            now=utcnow(),
                            permanent=permanent,
                        )
                        await fail_session.commit()
                    log = logger.exception if not permanent and not retryable else logger.warning
                    log(
                        "job_handler_error",
                        job_id=str(job.id),
                        tenant_id=str(job.tenant_id),
                        permanent=permanent,
                    )
        await asyncio.sleep(poll_seconds)

    await dispose_engine()
    logger.info("worker_stopped", worker_id=worker_id)


def run() -> None:
    asyncio.run(worker_loop())


if __name__ == "__main__":
    run()
