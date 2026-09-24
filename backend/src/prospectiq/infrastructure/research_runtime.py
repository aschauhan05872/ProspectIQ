"""Compose company research from existing repositories and the scoring service."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from prospectiq.application.research import CompanyResearchService
from prospectiq.application.services import LeadScoringService
from prospectiq.infrastructure.jobs import PostgresJobQueue
from prospectiq.infrastructure.repositories import (
    SqlAlchemyCompanyRepository,
    SqlAlchemyEvidenceRepository,
    SqlAlchemyLeadRepository,
    SqlAlchemySignalRepository,
)


def build_research_service(session: AsyncSession) -> CompanyResearchService:
    leads = SqlAlchemyLeadRepository(session)
    return CompanyResearchService(
        companies=SqlAlchemyCompanyRepository(session),
        evidence=SqlAlchemyEvidenceRepository(session),
        signals=SqlAlchemySignalRepository(session),
        leads=leads,
        scoring=LeadScoringService(leads),
        jobs=PostgresJobQueue(session),
    )
