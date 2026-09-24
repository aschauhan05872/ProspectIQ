"""Compose the end-to-end company pipeline service."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from prospectiq.application.pipeline import CompanyPipelineService
from prospectiq.infrastructure.config import Settings
from prospectiq.infrastructure.news_runtime import build_news_service
from prospectiq.infrastructure.repositories import SqlAlchemyDiscoveryCandidateRepository
from prospectiq.infrastructure.research_runtime import build_research_service


def build_pipeline_service(session: AsyncSession, settings: Settings) -> CompanyPipelineService:
    news_enabled = settings.news_provider.lower().strip() not in {"", "none"}
    return CompanyPipelineService(
        candidates=SqlAlchemyDiscoveryCandidateRepository(session),
        research=build_research_service(session),
        news=build_news_service(session, settings) if news_enabled else None,
        settings=settings,
    )
