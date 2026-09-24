"""Integration tests for Phase 5 company fact extraction."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from tests.integration.conftest import NOW

from prospectiq.domain.common import CompanyId, Confidence, EvidenceId, TenantScope
from prospectiq.domain.company import Company
from prospectiq.domain.company_facts import CompanyFactCategory
from prospectiq.domain.company_research import (
    CompanyResearchCase,
    CompanyResearchStatus,
    ResearchPage,
    ResearchPageFetchStatus,
    ResearchPageType,
)
from prospectiq.domain.evidence import Evidence, EvidenceOrigin
from prospectiq.domain.ingestion import SourceFactKind
from prospectiq.domain.jobs import JobType
from prospectiq.domain.source_registry import SourceClass
from prospectiq.infrastructure.company_fact_extraction_runtime import (
    build_company_fact_extraction_service,
)
from prospectiq.infrastructure.jobs import PostgresJobQueue
from prospectiq.infrastructure.repositories import (
    SqlAlchemyCompanyRepository,
    SqlAlchemyCompanyResearchCaseRepository,
    SqlAlchemyEvidenceRepository,
    SqlAlchemyResearchPageRepository,
)


@pytest.mark.integration
async def test_fact_extraction_persistence_and_retrieval(
    db_session: AsyncSession,
    tenant_scope: TenantScope,
) -> None:
    companies = SqlAlchemyCompanyRepository(db_session)
    cases = SqlAlchemyCompanyResearchCaseRepository(db_session)
    pages = SqlAlchemyResearchPageRepository(db_session)
    evidence_repo = SqlAlchemyEvidenceRepository(db_session)
    service = build_company_fact_extraction_service(db_session)

    company = Company(
        id=CompanyId(uuid4()),
        tenant_id=tenant_scope.tenant_id,
        name="Fact Co",
        normalized_name="fact-co.test",
        website="https://fact-co.test",
        industry=None,
        geography=None,
        employee_count=25,
        headcount_growth_pct=None,
        company_type=None,
        is_hiring=None,
        created_at=NOW,
        updated_at=NOW,
    )
    await companies.upsert(tenant_scope, company)
    await db_session.flush()

    case_id = uuid4()
    case = CompanyResearchCase(
        id=case_id,
        tenant_id=tenant_scope.tenant_id,
        company_id=company.id,
        status=CompanyResearchStatus.COMPLETED,
        job_id=None,
        requested_at=NOW,
        started_at=NOW,
        completed_at=NOW,
        failed_at=None,
        pages_requested=1,
        pages_fetched=1,
        pages_failed=0,
        research_version="company-research-v1",
        error_code=None,
        error_message_safe=None,
        created_at=NOW,
        updated_at=NOW,
    )
    await cases.create(tenant_scope, case)

    evidence_id = EvidenceId(uuid4())
    page_id = uuid4()
    await pages.create(
        tenant_scope,
        ResearchPage(
            id=page_id,
            tenant_id=tenant_scope.tenant_id,
            research_case_id=case_id,
            company_id=company.id,
            url="https://fact-co.test/services",
            normalized_url="https://fact-co.test/services",
            page_type=ResearchPageType.SERVICES,
            title="Our Services",
            http_status=200,
            content_type="text/html",
            content_hash="hash123",
            normalized_text="We offer consulting services. Contact sales@fact-co.test.",
            fetched_at=NOW,
            fetch_duration_ms=50,
            fetch_status=ResearchPageFetchStatus.SUCCEEDED,
            failure_class=None,
            evidence_id=evidence_id,
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    await evidence_repo.add(
        tenant_scope,
        Evidence(
            id=evidence_id,
            tenant_id=tenant_scope.tenant_id,
            fact="Company services page content",
            origin=EvidenceOrigin.SOURCE_DERIVED,
            source_class=SourceClass.COMPANY_WEBSITE,
            source_locator="https://fact-co.test/services",
            collected_at=NOW,
            confidence=Confidence.HIGH,
            snippet="We offer consulting services.",
            company_id=company.id,
            metadata={
                "fact_kind": SourceFactKind.RESEARCH_PAGE_CONTENT.value,
                "research_case_id": str(case_id),
                "research_page_id": str(page_id),
                "page_type": ResearchPageType.SERVICES.value,
                "title": "Our Services",
                "content_hash": "hash123",
            },
        ),
    )
    await db_session.flush()

    submission = await service.submit_for_case(tenant_scope, case_id)
    queue = PostgresJobQueue(db_session)
    job = await queue.claim(worker_id="integration", now=NOW, lease_seconds=60)
    assert job is not None
    assert job.job_type is JobType.EXTRACT_COMPANY_FACTS
    assert job.id == submission.job_id

    result = await service.execute_job(job)
    assert result.facts_created >= 2
    await queue.complete(job)

    case_facts = await service.list_for_case(tenant_scope, case_id)
    company_facts = await service.list_for_company(tenant_scope, company.id)
    assert len(case_facts) == result.facts_total
    assert len(company_facts) == result.facts_total
    assert any(fact.category is CompanyFactCategory.BUSINESS for fact in case_facts)
    assert all(fact.evidence_ids for fact in case_facts)

    repeat = await service.execute_job(job)
    assert repeat.facts_created == 0
    assert repeat.facts_total == result.facts_total
    await db_session.commit()
