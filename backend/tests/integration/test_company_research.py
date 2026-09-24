"""Integration tests for company research persistence and jobs."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from tests.integration.conftest import NOW

from prospectiq.domain.common import CompanyId
from prospectiq.domain.company import Company
from prospectiq.domain.company_research import CompanyResearchStatus
from prospectiq.domain.jobs import JobType
from prospectiq.infrastructure.company_research_runtime import build_company_research_service
from prospectiq.infrastructure.config import Settings
from prospectiq.infrastructure.models import JobRow
from prospectiq.infrastructure.repositories import (
    SqlAlchemyCompanyRepository,
    SqlAlchemyCompanyResearchCaseRepository,
)


@pytest.mark.integration
async def test_research_case_persistence_and_job_enqueue(
    db_session: AsyncSession,
    tenant_scope: object,
    integration_settings: Settings,
) -> None:
    companies = SqlAlchemyCompanyRepository(db_session)
    cases = SqlAlchemyCompanyResearchCaseRepository(db_session)
    company = Company(
        id=CompanyId(uuid4()),
        tenant_id=tenant_scope.tenant_id,  # type: ignore[attr-defined]
        name="Research Co",
        normalized_name="research-co.test",
        website="https://research-co.test",
        industry=None,
        geography=None,
        employee_count=50,
        headcount_growth_pct=None,
        company_type=None,
        is_hiring=None,
        created_at=NOW,
        updated_at=NOW,
    )
    await companies.upsert(tenant_scope, company)  # type: ignore[arg-type]
    await db_session.flush()

    service = build_company_research_service(db_session, integration_settings)
    submission = await service.submit(tenant_scope, company.id)  # type: ignore[arg-type]
    stored = await cases.get(tenant_scope, submission.case_id)  # type: ignore[arg-type]
    assert stored is not None
    assert stored.status is CompanyResearchStatus.QUEUED
    assert stored.job_id == submission.job_id

    job_row = await db_session.get(JobRow, submission.job_id)
    assert job_row is not None
    assert job_row.job_type == JobType.RESEARCH_COMPANY.value
    await db_session.commit()
