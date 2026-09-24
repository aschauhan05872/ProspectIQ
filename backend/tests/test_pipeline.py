from __future__ import annotations

import inspect
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from prospectiq.application.discovery import CompanyDiscoveryService
from prospectiq.application.ingestion import CompanySourceIngestionService
from prospectiq.application.pipeline import CompanyPipelineService
from prospectiq.application.ports import NormalizedRecord
from prospectiq.application.research import CompanyResearchService
from prospectiq.application.services import LeadScoringService
from prospectiq.domain.common import (
    CompanyId,
    Confidence,
    EvidenceId,
    JobId,
    TenantId,
    TenantScope,
    WorkspaceId,
)
from prospectiq.domain.company import Company
from prospectiq.domain.discovery import (
    DiscoveryCandidate,
    DiscoveryIngestionStatus,
    DiscoveryRequest,
    ProviderDiscoveryHit,
    default_field_checks,
    normalize_discovery_request,
)
from prospectiq.domain.evidence import Evidence, EvidenceOrigin
from prospectiq.domain.ingestion import (
    IngestedCompanySource,
    PermanentSourceError,
    RetryableSourceError,
)
from prospectiq.domain.jobs import Job, JobStatus, JobType
from prospectiq.domain.scoring import LeadClassification
from prospectiq.domain.signal import Signal, SignalId, SignalType
from prospectiq.domain.source_registry import SourceClass
from prospectiq.infrastructure.config import Settings
from prospectiq.infrastructure.jobs import InMemoryJobQueue
from prospectiq.infrastructure.repositories import TenantMismatchError
from tests.fakes import (
    InMemoryCompanyRepository,
    InMemoryCompanySourceRepository,
    InMemoryDiscoveryCandidateRepository,
    InMemoryEvidenceRepository,
    InMemoryLeadRepository,
    InMemorySignalRepository,
)
from tests.test_ingestion import _service as ingestion_service_factory
from tests.test_ingestion import _StaticAdapter

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
TENANT = TenantId(UUID("00000000-0000-0000-0000-000000000001"))
OTHER = TenantId(UUID("00000000-0000-0000-0000-000000000099"))
WORKSPACE = WorkspaceId(UUID("00000000-0000-0000-0000-000000000002"))
SETTINGS = Settings()


def _scope(tenant_id: TenantId = TENANT) -> TenantScope:
    return TenantScope(tenant_id=tenant_id, workspace_id=WORKSPACE, request_id="pipeline-test")


class _DiscoveryProvider:
    provider_key = "test_provider"

    async def discover(
        self, scope: TenantScope, request: DiscoveryRequest
    ) -> list[ProviderDiscoveryHit]:
        return [
            ProviderDiscoveryHit(
                name="Acme Health",
                website="https://acme.test/careers",
                domain="acme.test",
                source_locator="https://acme.test/careers",
            )
        ]


def _careers_records() -> list[NormalizedRecord]:
    return [
        NormalizedRecord(
            fact="Careers page: We are hiring a Software Engineer. Apply now.",
            locator="https://acme.test/careers",
            snippet="We are hiring a Software Engineer.",
            collected_at=NOW,
            confidence="high",
            metadata={
                "fact_kind": "page_content",
                "title": "Acme Careers",
                "final_url": "https://acme.test/careers",
                "http_status": 200,
            },
        ),
        NormalizedRecord(
            fact="Hiring language observed on careers page.",
            locator="https://acme.test/careers",
            snippet="We are hiring a Software Engineer.",
            collected_at=NOW,
            confidence="high",
            metadata={
                "fact_kind": "hiring_language_observed",
                "observed_hiring_phrases": ["software engineer"],
            },
        ),
    ]


def _workflow_stack(
    *,
    adapter: object | None = None,
) -> tuple[
    CompanyDiscoveryService,
    CompanyPipelineService,
    CompanySourceIngestionService,
    CompanyResearchService,
    InMemoryJobQueue,
    InMemoryDiscoveryCandidateRepository,
    InMemoryEvidenceRepository,
    InMemorySignalRepository,
    InMemoryLeadRepository,
    InMemoryCompanyRepository,
]:
    queue = InMemoryJobQueue()
    companies = InMemoryCompanyRepository()
    sources = InMemoryCompanySourceRepository()
    evidence = InMemoryEvidenceRepository()
    candidates = InMemoryDiscoveryCandidateRepository()
    signals = InMemorySignalRepository()
    leads = InMemoryLeadRepository()
    ingestion, _, _, _ = ingestion_service_factory(
        adapter or _StaticAdapter(_careers_records()),
        jobs=queue,
    )
    ingestion._companies = companies  # type: ignore[attr-defined]
    ingestion._company_sources = sources  # type: ignore[attr-defined]
    ingestion._evidence = evidence  # type: ignore[attr-defined]
    research = CompanyResearchService(
        companies=companies,
        evidence=evidence,
        signals=signals,
        leads=leads,
        scoring=LeadScoringService(leads),
        jobs=queue,
    )
    pipeline = CompanyPipelineService(
        candidates=candidates,
        research=research,
        settings=SETTINGS,
    )
    discovery = CompanyDiscoveryService(
        jobs=queue,
        candidates=candidates,
        evidence=evidence,
        ingestion=ingestion,
        provider=_DiscoveryProvider(),
    )
    return (
        discovery,
        pipeline,
        ingestion,
        research,
        queue,
        candidates,
        evidence,
        signals,
        leads,
        companies,
    )


@pytest.mark.asyncio
async def test_full_happy_path_discovery_to_qualification_state() -> None:
    (
        discovery,
        pipeline,
        ingestion,
        research,
        queue,
        candidates,
        evidence,
        signals,
        leads,
        companies,
    ) = _workflow_stack()
    request = normalize_discovery_request(
        industry="healthtech",
        countries=["USA"],
        employee_min=11,
        employee_max=500,
        hiring_required=True,
        keywords=[],
        limit=5,
    )
    submission = await discovery.submit(_scope(), request)
    discover_job = queue.jobs[f"{TENANT}:{submission.idempotency_key}"]
    await discovery.execute_job(discover_job)
    stored = await candidates.list_for_job(_scope(), discover_job.id)
    assert len(stored) == 1
    assert stored[0].ingestion_status is DiscoveryIngestionStatus.FETCH_QUEUED
    fetch_job = next(item for item in queue.jobs.values() if item.job_type is JobType.FETCH_SOURCE)
    scope = pipeline.scope_for_job(fetch_job)
    fetch_result = await ingestion.execute_job(fetch_job)
    await pipeline.after_fetch_succeeded(scope, fetch_job, fetch_result)
    updated = await candidates.get_by_fetch_job_id(_scope(), fetch_job.id)
    assert updated is not None
    assert updated.company_id == fetch_result.company_id
    assert updated.source_evidence_ids
    assert updated.ingestion_status is DiscoveryIngestionStatus.RESEARCH_QUEUED
    research_job = next(
        item for item in queue.jobs.values() if item.job_type is JobType.RESEARCH_LEAD
    )
    research_scope = pipeline.scope_for_job(research_job)
    research_result = await research.execute_job(research_job)
    await pipeline.after_research_succeeded(research_scope, research_job, research_result)
    final = await candidates.get_by_id(_scope(), updated.id)
    assert final is not None
    assert final.ingestion_status is DiscoveryIngestionStatus.RESEARCHED
    assert final.lead_id is not None
    lead = leads.items[(TENANT, final.lead_id)]
    assert lead.score == 3
    assert lead.classification is LeadClassification.WARM
    assert lead.is_qualified is False
    assert len(await signals.list_for_company(_scope(), fetch_result.company_id)) == 1


@pytest.mark.asyncio
async def test_fetch_failure_does_not_enqueue_research() -> None:
    queue = InMemoryJobQueue()
    candidates = InMemoryDiscoveryCandidateRepository()
    evidence = InMemoryEvidenceRepository()
    companies = InMemoryCompanyRepository()
    sources = InMemoryCompanySourceRepository()
    ingestion = CompanySourceIngestionService(
        jobs=queue,
        companies=companies,
        company_sources=sources,
        evidence=evidence,
        adapters={SourceClass.COMPANY_WEBSITE: _StaticAdapter(PermanentSourceError("bad"))},  # type: ignore[arg-type]
    )
    research = CompanyResearchService(
        companies=companies,
        evidence=evidence,
        signals=InMemorySignalRepository(),
        leads=InMemoryLeadRepository(),
        scoring=LeadScoringService(InMemoryLeadRepository()),
        jobs=queue,
    )
    pipeline = CompanyPipelineService(
        candidates=candidates,
        research=research,
        settings=SETTINGS,
    )
    candidate_id = uuid4()
    fetch_job = await queue.enqueue(
        _scope(),
        JobType.FETCH_SOURCE,
        "fetch_source:https://bad.test",
        {
            "url": "https://bad.test",
            "normalized_url": "https://bad.test",
            "source_class": SourceClass.COMPANY_WEBSITE.value,
            "workspace_id": str(WORKSPACE),
            "discovery_candidate_id": str(candidate_id),
        },
    )
    await candidates.upsert(
        _scope(),
        DiscoveryCandidate(
            id=candidate_id,
            tenant_id=TENANT,
            discovery_job_id=JobId(uuid4()),
            name="Bad Co",
            domain="bad.test",
            website_url="https://bad.test",
            normalized_website="https://bad.test",
            provider_key="test",
            source_locator="https://bad.test",
            discovered_at=NOW,
            confidence=None,
            provider_rank=None,
            field_checks=default_field_checks(),
            evidence_id=None,
            company_id=None,
            fetch_job_id=fetch_job.id,
            research_job_id=None,
            lead_id=None,
            source_evidence_ids=[],
            ingestion_status=DiscoveryIngestionStatus.FETCH_QUEUED,
            request_snapshot={},
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    with pytest.raises(PermanentSourceError):
        await ingestion.execute_job(fetch_job)
    await pipeline.after_fetch_failed(pipeline.scope_for_job(fetch_job), fetch_job, permanent=True)
    assert not any(item.job_type is JobType.RESEARCH_LEAD for item in queue.jobs.values())
    failed = await candidates.get_by_id(_scope(), candidate_id)
    assert failed is not None
    assert failed.ingestion_status is DiscoveryIngestionStatus.FETCH_FAILED


@pytest.mark.asyncio
async def test_retryable_fetch_does_not_mark_failed_or_enqueue_research() -> None:
    queue = InMemoryJobQueue()
    ingestion, _, _, _ = ingestion_service_factory(
        _StaticAdapter(RetryableSourceError("timeout")),
        jobs=queue,
    )
    fetch_job = await queue.enqueue(
        _scope(),
        JobType.FETCH_SOURCE,
        "fetch_source:https://retry.test",
        {
            "url": "https://retry.test",
            "normalized_url": "https://retry.test",
            "source_class": "company_website",
        },
    )
    pipeline = CompanyPipelineService(
        candidates=InMemoryDiscoveryCandidateRepository(),
        research=CompanyResearchService(
            companies=InMemoryCompanyRepository(),
            evidence=InMemoryEvidenceRepository(),
            signals=InMemorySignalRepository(),
            leads=InMemoryLeadRepository(),
            scoring=LeadScoringService(InMemoryLeadRepository()),
            jobs=queue,
        ),
        settings=SETTINGS,
    )
    with pytest.raises(RetryableSourceError):
        await ingestion.execute_job(fetch_job)
    await pipeline.after_fetch_failed(pipeline.scope_for_job(fetch_job), fetch_job, permanent=False)
    assert not any(item.job_type is JobType.RESEARCH_LEAD for item in queue.jobs.values())


@pytest.mark.asyncio
async def test_research_is_idempotent_and_removes_stale_signals() -> None:
    (
        _discovery,
        pipeline,
        ingestion,
        research,
        queue,
        candidates,
        evidence,
        signals,
        leads,
        companies,
    ) = _workflow_stack()
    company = Company(
        id=CompanyId(uuid4()),
        tenant_id=TENANT,
        name="Acme",
        normalized_name="acme.test",
        website="https://acme.test",
        industry=None,
        geography=None,
        employee_count=None,
        headcount_growth_pct=None,
        company_type=None,
        is_hiring=None,
        created_at=NOW,
        updated_at=NOW,
    )
    await companies.upsert(_scope(), company)
    careers = Evidence(
        id=EvidenceId(uuid4()),
        tenant_id=TENANT,
        fact="We are hiring a Software Engineer.",
        origin=EvidenceOrigin.SOURCE_DERIVED,
        source_class=SourceClass.CAREERS_PAGE,
        source_locator="https://acme.test/careers",
        collected_at=NOW,
        confidence=Confidence.HIGH,
        snippet="hiring",
        company_id=company.id,
        metadata={"fact_kind": "page_content"},
    )
    await evidence.add(_scope(), careers)
    stale_id = SignalId(uuid4())
    await signals.upsert(
        _scope(),
        Signal(
            id=stale_id,
            tenant_id=TENANT,
            signal_type=SignalType.FUNDING_NEWS,
            weight=3,
            detected_at=NOW,
            evidence_id=careers.id,
            company_id=company.id,
            reason="stale fixture",
        ),
    )
    research_job = await queue.enqueue(
        _scope(),
        JobType.RESEARCH_LEAD,
        f"research_lead:{company.id}:test",
        {"company_id": str(company.id), "workspace_id": str(WORKSPACE)},
    )
    first = await research.execute_job(research_job)
    second = await research.execute_job(research_job)
    assert first.score.total_score == second.score.total_score == 3
    stored = await signals.list_for_company(_scope(), company.id)
    assert len(stored) == 1
    assert stored[0].signal_type is SignalType.HIRING_TECH_ROLES
    assert all(item.id != stale_id for item in stored)


@pytest.mark.asyncio
async def test_no_supported_signals_yields_cold_unqualified() -> None:
    (
        _discovery,
        pipeline,
        ingestion,
        research,
        queue,
        _candidates,
        evidence,
        signals,
        leads,
        companies,
    ) = _workflow_stack(adapter=_StaticAdapter([
        NormalizedRecord(
            fact="About our company.",
            locator="https://plain.test",
            snippet="About",
            collected_at=NOW,
            confidence="high",
            metadata={"fact_kind": "page_content", "title": "Plain"},
        )
    ]))
    fetch_job = await queue.enqueue(
        _scope(),
        JobType.FETCH_SOURCE,
        "fetch_source:https://plain.test",
        {
            "url": "https://plain.test",
            "normalized_url": "https://plain.test",
            "source_class": SourceClass.COMPANY_WEBSITE.value,
            "workspace_id": str(WORKSPACE),
        },
    )
    scope = pipeline.scope_for_job(fetch_job)
    result = await ingestion.execute_job(fetch_job)
    await pipeline.after_fetch_succeeded(scope, fetch_job, result)
    research_job = next(
        item for item in queue.jobs.values() if item.job_type is JobType.RESEARCH_LEAD
    )
    research_result = await research.execute_job(research_job)
    assert research_result.score.total_score == 0
    assert research_result.score.classification is LeadClassification.COLD
    assert research_result.score.is_qualified is False
    assert await signals.list_for_company(_scope(), result.company_id) == []


@pytest.mark.asyncio
async def test_tenant_isolation_on_candidate_company_association() -> None:
    candidates = InMemoryDiscoveryCandidateRepository()
    pipeline = CompanyPipelineService(
        candidates=candidates,
        research=CompanyResearchService(
            companies=InMemoryCompanyRepository(),
            evidence=InMemoryEvidenceRepository(),
            signals=InMemorySignalRepository(),
            leads=InMemoryLeadRepository(),
            scoring=LeadScoringService(InMemoryLeadRepository()),
            jobs=InMemoryJobQueue(),
        ),
        settings=SETTINGS,
    )
    candidate_id = uuid4()
    await candidates.upsert(
        _scope(TENANT),
        DiscoveryCandidate(
            id=candidate_id,
            tenant_id=TENANT,
            discovery_job_id=JobId(uuid4()),
            name="Acme",
            domain="acme.test",
            website_url="https://acme.test",
            normalized_website="https://acme.test",
            provider_key="test",
            source_locator="https://acme.test",
            discovered_at=NOW,
            confidence=None,
            provider_rank=None,
            field_checks=default_field_checks(),
            evidence_id=None,
            company_id=CompanyId(uuid4()),
            fetch_job_id=JobId(uuid4()),
            research_job_id=None,
            lead_id=None,
            source_evidence_ids=[],
            ingestion_status=DiscoveryIngestionStatus.FETCH_QUEUED,
            request_snapshot={},
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    job = Job(
        id=JobId(uuid4()),
        tenant_id=OTHER,
        job_type=JobType.FETCH_SOURCE,
        idempotency_key="x",
        payload={"discovery_candidate_id": str(candidate_id)},
        status=JobStatus.PENDING,
        attempts=0,
        max_attempts=5,
        available_at=NOW,
        leased_until=None,
        last_error=None,
        created_at=NOW,
        updated_at=NOW,
    )
    with pytest.raises(TenantMismatchError):
        await pipeline.after_fetch_succeeded(
            pipeline.scope_for_job(job),
            job,
            IngestedCompanySource(
                tenant_id=OTHER,
                company_id=CompanyId(uuid4()),
                company_source_id=uuid4(),
                evidence_ids=[],
                normalized_url="https://acme.test",
                source_class=SourceClass.COMPANY_WEBSITE,
                identity_requires_review=False,
                page_title=None,
            ),
        )


def test_research_module_has_no_network_or_ai() -> None:
    import prospectiq.application.research as module

    source = inspect.getsource(module)
    assert "httpx" not in source
    assert "openai" not in source
