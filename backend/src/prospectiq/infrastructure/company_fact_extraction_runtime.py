"""Runtime wiring for structured company fact extraction."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from prospectiq.application.company_fact_extraction import CompanyFactExtractionService
from prospectiq.infrastructure.fact_extraction.deterministic_extractor import (
    DeterministicEvidenceFactExtractor,
)
from prospectiq.infrastructure.jobs import PostgresJobQueue
from prospectiq.infrastructure.repositories import (
    SqlAlchemyCompanyFactRepository,
    SqlAlchemyCompanyResearchCaseRepository,
    SqlAlchemyEvidenceRepository,
    SqlAlchemyResearchPageRepository,
)


def build_company_fact_extraction_service(
    session: AsyncSession,
) -> CompanyFactExtractionService:
    return CompanyFactExtractionService(
        cases=SqlAlchemyCompanyResearchCaseRepository(session),
        pages=SqlAlchemyResearchPageRepository(session),
        evidence=SqlAlchemyEvidenceRepository(session),
        facts=SqlAlchemyCompanyFactRepository(session),
        jobs=PostgresJobQueue(session),
        extractor=DeterministicEvidenceFactExtractor(),
    )
