"""Runtime wiring for controlled company research."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from prospectiq.application.company_research import CompanyResearchService
from prospectiq.infrastructure.config import Settings
from prospectiq.infrastructure.http_fetch import FetchLimits, SafeHttpFetcher
from prospectiq.infrastructure.jobs import PostgresJobQueue
from prospectiq.infrastructure.repositories import (
    SqlAlchemyCompanyRepository,
    SqlAlchemyCompanyResearchCaseRepository,
    SqlAlchemyEvidenceRepository,
    SqlAlchemyResearchPageRepository,
)


def build_company_research_service(
    session: AsyncSession, settings: Settings
) -> CompanyResearchService:
    limits = FetchLimits(
        connect_timeout_seconds=settings.fetch_connect_timeout_seconds,
        read_timeout_seconds=settings.fetch_read_timeout_seconds,
        total_timeout_seconds=settings.fetch_total_timeout_seconds,
        max_response_bytes=settings.fetch_max_response_bytes,
        max_redirects=settings.fetch_max_redirects,
        user_agent=settings.fetch_user_agent,
    )
    return CompanyResearchService(
        companies=SqlAlchemyCompanyRepository(session),
        cases=SqlAlchemyCompanyResearchCaseRepository(session),
        pages=SqlAlchemyResearchPageRepository(session),
        evidence=SqlAlchemyEvidenceRepository(session),
        jobs=PostgresJobQueue(session),
        fetcher=SafeHttpFetcher(limits),
        max_pages_per_company=settings.research_max_pages_per_company,
        max_research_time_seconds=settings.research_max_time_seconds,
    )
