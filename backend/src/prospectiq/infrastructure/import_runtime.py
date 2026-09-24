"""Runtime wiring for prospect import services."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from prospectiq.application.company_resolution import CompanyResolutionService
from prospectiq.application.prospect_import import ProspectImportService
from prospectiq.infrastructure.jobs import PostgresJobQueue
from prospectiq.infrastructure.repositories import (
    SqlAlchemyCompanyRepository,
    SqlAlchemyImportBatchRepository,
    SqlAlchemyImportedProspectRepository,
    SqlAlchemyPersonRepository,
)


def build_prospect_import_service(session: AsyncSession) -> ProspectImportService:
    return ProspectImportService(
        batches=SqlAlchemyImportBatchRepository(session),
        prospects=SqlAlchemyImportedProspectRepository(session),
        jobs=PostgresJobQueue(session),
    )


def build_company_resolution_service(session: AsyncSession) -> CompanyResolutionService:
    return CompanyResolutionService(
        companies=SqlAlchemyCompanyRepository(session),
        persons=SqlAlchemyPersonRepository(session),
        prospects=SqlAlchemyImportedProspectRepository(session),
    )
