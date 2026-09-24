"""Runtime wiring for company news ingestion."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from prospectiq.application.news_ingestion import CompanyNewsIngestionService
from prospectiq.infrastructure.config import Settings
from prospectiq.infrastructure.jobs import PostgresJobQueue
from prospectiq.infrastructure.news.provider_factory import build_news_provider
from prospectiq.infrastructure.repositories import (
    SqlAlchemyCompanyRepository,
    SqlAlchemyEvidenceRepository,
)


def build_news_service(session: AsyncSession, settings: Settings) -> CompanyNewsIngestionService:
    return CompanyNewsIngestionService(
        companies=SqlAlchemyCompanyRepository(session),
        evidence=SqlAlchemyEvidenceRepository(session),
        provider=build_news_provider(settings),
        jobs=PostgresJobQueue(session),
    )
