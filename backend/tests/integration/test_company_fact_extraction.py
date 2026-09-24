"""Integration tests for enriched Phase 5 fact extraction."""

from __future__ import annotations

from uuid import uuid4

import pytest
from tests.fixtures.intermark_evidence import CASE_ID, COMPANY_ID, intermark_evidence_contexts
from tests.integration.conftest import NOW

from prospectiq.domain.common import Confidence, TenantScope
from prospectiq.domain.company import Company
from prospectiq.domain.company_facts import CompanyFactCategory, CompanyFactTier
from prospectiq.domain.company_research import (
    CompanyResearchCase,
    CompanyResearchStatus,
    ResearchPage,
    ResearchPageFetchStatus,
    ResearchPageType,
)
from prospectiq.domain.evidence import Evidence, EvidenceOrigin
from prospectiq.domain.ingestion import SourceFactKind
from prospectiq.domain.jobs import Job, JobStatus, JobType
from prospectiq.domain.source_registry import SourceClass
from prospectiq.infrastructure.company_fact_extraction_runtime import (
    build_company_fact_extraction_service,
)
from prospectiq.infrastructure.repositories import (
    SqlAlchemyCompanyRepository,
    SqlAlchemyCompanyResearchCaseRepository,
    SqlAlchemyEvidenceRepository,
    SqlAlchemyResearchPageRepository,
)


def _page_type(value: str) -> ResearchPageType:
    try:
        return ResearchPageType(value)
    except ValueError:
        return ResearchPageType.OTHER


@pytest.mark.integration
async def test_intermark_fixture_extraction_persists_substantive_facts(
    db_session: object,
    tenant_scope: TenantScope,
) -> None:
    companies = SqlAlchemyCompanyRepository(db_session)  # type: ignore[arg-type]
    cases = SqlAlchemyCompanyResearchCaseRepository(db_session)  # type: ignore[arg-type]
    pages = SqlAlchemyResearchPageRepository(db_session)  # type: ignore[arg-type]
    evidence_repo = SqlAlchemyEvidenceRepository(db_session)  # type: ignore[arg-type]
    service = build_company_fact_extraction_service(db_session)  # type: ignore[arg-type]

    company = Company(
        id=COMPANY_ID,
        tenant_id=tenant_scope.tenant_id,
        name="Intermark Global",
        normalized_name="intermark.global",
        website="https://intermark.global/",
        industry=None,
        geography=None,
        employee_count=None,
        headcount_growth_pct=None,
        company_type=None,
        is_hiring=None,
        created_at=NOW,
        updated_at=NOW,
    )
    await companies.upsert(tenant_scope, company)
    await db_session.flush()  # type: ignore[attr-defined]
    case = CompanyResearchCase(
        id=CASE_ID,
        tenant_id=tenant_scope.tenant_id,
        company_id=company.id,
        status=CompanyResearchStatus.COMPLETED,
        job_id=None,
        requested_at=NOW,
        started_at=NOW,
        completed_at=NOW,
        failed_at=None,
        pages_requested=10,
        pages_fetched=10,
        pages_failed=0,
        research_version="company-research-v1",
        error_code=None,
        error_message_safe=None,
        created_at=NOW,
        updated_at=NOW,
    )
    await cases.create(tenant_scope, case)

    for ctx in intermark_evidence_contexts():
        page_id = uuid4()
        await pages.create(
            tenant_scope,
            ResearchPage(
                id=page_id,
                tenant_id=tenant_scope.tenant_id,
                research_case_id=CASE_ID,
                company_id=company.id,
                url=ctx.source_locator,
                normalized_url=ctx.source_locator,
                page_type=_page_type(ctx.page_type),
                title=ctx.title,
                http_status=200,
                content_type="text/html",
                content_hash="fixture",
                normalized_text=ctx.text,
                fetched_at=NOW,
                fetch_duration_ms=10,
                fetch_status=ResearchPageFetchStatus.SUCCEEDED,
                failure_class=None,
                evidence_id=ctx.evidence_id,
                created_at=NOW,
                updated_at=NOW,
            ),
        )
        await evidence_repo.add(
            tenant_scope,
            Evidence(
                id=ctx.evidence_id,
                tenant_id=tenant_scope.tenant_id,
                fact=f"Fixture page {ctx.page_type}",
                origin=EvidenceOrigin.SOURCE_DERIVED,
                source_class=SourceClass.COMPANY_WEBSITE,
                source_locator=ctx.source_locator,
                collected_at=NOW,
                confidence=Confidence.HIGH,
                snippet=ctx.text[:500],
                company_id=company.id,
                metadata={
                    "fact_kind": SourceFactKind.RESEARCH_PAGE_CONTENT.value,
                    "research_case_id": str(CASE_ID),
                    "research_page_id": str(page_id),
                    "page_type": ctx.page_type,
                    "title": ctx.title,
                    "content_hash": "fixture",
                },
            ),
        )
    await db_session.flush()  # type: ignore[attr-defined]

    job = Job(
        id=uuid4(),  # type: ignore[arg-type]
        tenant_id=tenant_scope.tenant_id,
        job_type=JobType.EXTRACT_COMPANY_FACTS,
        idempotency_key="integration-intermark",
        payload={"research_case_id": str(CASE_ID), "company_id": str(company.id)},
        status=JobStatus.LEASED,
        attempts=1,
        max_attempts=5,
        available_at=NOW,
        leased_until=None,
        last_error=None,
        created_at=NOW,
        updated_at=NOW,
    )
    result = await service.execute_job(job)
    facts = await service.list_for_case(tenant_scope, CASE_ID)
    substantive = [f for f in facts if f.fact_tier is CompanyFactTier.SUBSTANTIVE]
    categories = {f.category for f in substantive}

    assert result.facts_created >= 15
    assert CompanyFactCategory.GEOGRAPHY in categories
    assert CompanyFactCategory.ACTIVITY in categories
    assert CompanyFactCategory.ORGANIZATION in categories
    assert all(f.evidence_ids for f in facts)
    await db_session.commit()  # type: ignore[attr-defined]
