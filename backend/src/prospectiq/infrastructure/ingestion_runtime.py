"""Compose the company-source ingestion use case from infrastructure adapters."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from prospectiq.application.ingestion import CompanySourceIngestionService
from prospectiq.application.ports import SourceAdapter
from prospectiq.domain.source_registry import SourceClass
from prospectiq.infrastructure.config import Settings
from prospectiq.infrastructure.http_fetch import FetchLimits, SafeHttpFetcher
from prospectiq.infrastructure.jobs import PostgresJobQueue
from prospectiq.infrastructure.providers import build_source_registry
from prospectiq.infrastructure.repositories import (
    SqlAlchemyCompanyRepository,
    SqlAlchemyCompanySourceRepository,
    SqlAlchemyEvidenceRepository,
)
from prospectiq.infrastructure.web_source import HttpPageSourceAdapter


def fetch_limits(settings: Settings) -> FetchLimits:
    return FetchLimits(
        connect_timeout_seconds=settings.fetch_connect_timeout_seconds,
        read_timeout_seconds=settings.fetch_read_timeout_seconds,
        total_timeout_seconds=settings.fetch_total_timeout_seconds,
        max_response_bytes=settings.fetch_max_response_bytes,
        max_redirects=settings.fetch_max_redirects,
        user_agent=settings.fetch_user_agent,
    )


def http_source_adapters(
    limits: FetchLimits,
    *,
    fetcher: SafeHttpFetcher | None = None,
) -> dict[SourceClass, SourceAdapter]:
    shared = fetcher or SafeHttpFetcher(limits)
    return {
        SourceClass.COMPANY_WEBSITE: HttpPageSourceAdapter(
            shared, SourceClass.COMPANY_WEBSITE, "http_company_website"
        ),
        SourceClass.CAREERS_PAGE: HttpPageSourceAdapter(
            shared, SourceClass.CAREERS_PAGE, "http_careers_page"
        ),
    }


def build_ingestion_service(
    session: AsyncSession,
    settings: Settings,
    *,
    fetcher: SafeHttpFetcher | None = None,
) -> CompanySourceIngestionService:
    build_source_registry(official_linkedin_authorized=settings.official_linkedin_enabled)
    return CompanySourceIngestionService(
        jobs=PostgresJobQueue(session),
        companies=SqlAlchemyCompanyRepository(session),
        company_sources=SqlAlchemyCompanySourceRepository(session),
        evidence=SqlAlchemyEvidenceRepository(session),
        adapters=http_source_adapters(fetch_limits(settings), fetcher=fetcher),
    )
