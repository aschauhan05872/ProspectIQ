from __future__ import annotations

import inspect
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from prospectiq.application.research import CompanyResearchService, catalog_payload
from prospectiq.application.services import LeadScoringService
from prospectiq.domain.common import (
    CompanyId,
    Confidence,
    EvidenceId,
    TenantId,
    TenantScope,
    WorkspaceId,
)
from prospectiq.domain.company import Company
from prospectiq.domain.detection import (
    SIGNAL_RULE_CATALOG,
    HiringTechRolesRule,
    SignalDetectionService,
    deferred_signal_types,
)
from prospectiq.domain.evidence import Evidence, EvidenceOrigin
from prospectiq.domain.ingestion import PermanentSourceError
from prospectiq.domain.jobs import JobType
from prospectiq.domain.scoring import LeadClassification
from prospectiq.domain.signal import SIGNAL_WEIGHTS, DetectedSignal, SignalType
from prospectiq.domain.source_registry import SourceClass
from prospectiq.infrastructure.jobs import InMemoryJobQueue
from tests.fakes import (
    InMemoryCompanyRepository,
    InMemoryEvidenceRepository,
    InMemoryLeadRepository,
    InMemorySignalRepository,
)

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
TENANT = TenantId(UUID("00000000-0000-0000-0000-000000000001"))
OTHER_TENANT = TenantId(UUID("00000000-0000-0000-0000-000000000099"))
WORKSPACE = WorkspaceId(UUID("00000000-0000-0000-0000-000000000002"))


def _scope(tenant_id: TenantId = TENANT) -> TenantScope:
    return TenantScope(tenant_id=tenant_id, workspace_id=WORKSPACE, request_id="research-test")


def _company(tenant_id: TenantId = TENANT) -> Company:
    return Company(
        id=CompanyId(uuid4()),
        tenant_id=tenant_id,
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


def _evidence(
    *,
    fact: str,
    locator: str = "https://acme.test/careers",
    source_class: SourceClass = SourceClass.CAREERS_PAGE,
    origin: EvidenceOrigin = EvidenceOrigin.SOURCE_DERIVED,
    company_id: CompanyId | None = None,
    tenant_id: TenantId = TENANT,
    metadata: dict[str, object] | None = None,
    snippet: str | None = None,
) -> Evidence:
    return Evidence(
        id=EvidenceId(uuid4()),
        tenant_id=tenant_id,
        fact=fact,
        origin=origin,
        source_class=source_class if origin is EvidenceOrigin.SOURCE_DERIVED else None,
        source_locator=locator if origin is EvidenceOrigin.SOURCE_DERIVED else None,
        collected_at=NOW,
        confidence=Confidence.HIGH,
        snippet=snippet or fact,
        company_id=company_id,
        metadata=metadata or {"fact_kind": "page_content", "title": "Careers"},
    )


class _FundingFixtureRule:
    signal_type = SignalType.FUNDING_NEWS

    def detect(self, evidence: list[Evidence]) -> DetectedSignal | None:
        for item in evidence:
            if item.metadata.get("fact_kind") == "funding_announcement":
                return DetectedSignal(
                    signal_type=self.signal_type,
                    evidence_id=item.id,
                    reason="Test fixture funding evidence.",
                )
        return None


def _service(
    *,
    detector: SignalDetectionService | None = None,
    jobs: InMemoryJobQueue | None = None,
) -> tuple[
    CompanyResearchService,
    InMemoryCompanyRepository,
    InMemoryEvidenceRepository,
    InMemorySignalRepository,
    InMemoryLeadRepository,
    InMemoryJobQueue,
]:
    companies = InMemoryCompanyRepository()
    evidence = InMemoryEvidenceRepository()
    signals = InMemorySignalRepository()
    leads = InMemoryLeadRepository()
    queue = jobs or InMemoryJobQueue()
    service = CompanyResearchService(
        companies=companies,
        evidence=evidence,
        signals=signals,
        leads=leads,
        scoring=LeadScoringService(leads),
        jobs=queue,
        detector=detector,
    )
    return service, companies, evidence, signals, leads, queue


async def _seed(
    companies: InMemoryCompanyRepository,
    evidence: InMemoryEvidenceRepository,
    company: Company,
    records: list[Evidence],
    scope: TenantScope | None = None,
) -> None:
    current = scope or _scope(company.tenant_id)
    await companies.upsert(current, company)
    for item in records:
        item.company_id = company.id
        item.tenant_id = company.tenant_id
        await evidence.add(current, item)


def test_hiring_tech_roles_detected_from_careers_evidence() -> None:
    evidence = _evidence(fact="We are hiring a Software Engineer to join the platform team.")
    detected = SignalDetectionService().detect([evidence])
    assert len(detected) == 1
    assert detected[0].signal_type is SignalType.HIRING_TECH_ROLES
    assert detected[0].evidence_id == evidence.id
    assert "software engineer" in detected[0].reason.lower()


def test_non_hiring_technology_language_does_not_produce_hiring_signal() -> None:
    detector = SignalDetectionService()
    assert detector.detect([
        _evidence(fact="We have software engineers and a strong engineering leadership team.")
    ]) == []
    assert detector.detect([
        _evidence(fact="Engineering leadership is a core part of how we work.")
    ]) == []
    assert detector.detect([
        _evidence(
            fact="We are hiring a marketing manager to grow the brand.",
        )
    ]) == []


def test_generic_website_words_do_not_create_tech_growth_or_other_signals() -> None:
    detected = SignalDetectionService().detect([
        _evidence(
            fact=(
                "We use technology and innovation to drive growth. "
                "Our CEO recently changed jobs and is active on LinkedIn. "
                "We raised funding and launched a new office."
            ),
            locator="https://acme.test/",
            source_class=SourceClass.COMPANY_WEBSITE,
        )
    ])
    assert detected == []
    assert SignalType.TALKS_ABOUT_TECH_GROWTH in deferred_signal_types()
    implemented = [item.signal_type for item in SIGNAL_RULE_CATALOG if item.implemented]
    assert implemented == [
        SignalType.HIRING_TECH_ROLES,
        SignalType.FUNDING_NEWS,
        SignalType.EXPANSION_LAUNCH,
    ]


def test_careers_page_content_and_hiring_observation_are_combined() -> None:
    locator = "https://acme.test/careers"
    page = _evidence(
        fact="Join our team. Current openings are listed below.",
        locator=locator,
        metadata={"fact_kind": "page_content"},
    )
    observed = _evidence(
        fact="Hiring language observed on careers page.",
        locator=locator,
        metadata={
            "fact_kind": "hiring_language_observed",
            "observed_hiring_phrases": ["software engineer"],
        },
    )
    detected = SignalDetectionService().detect([page, observed])
    assert len(detected) == 1
    assert detected[0].signal_type is SignalType.HIRING_TECH_ROLES
    assert detected[0].evidence_id in {page.id, observed.id}


def test_ai_interpretation_is_ignored() -> None:
    detected = SignalDetectionService().detect([
        _evidence(
            fact="We are hiring a Software Engineer.",
            origin=EvidenceOrigin.AI_INTERPRETATION,
        )
    ])
    assert detected == []


def test_signal_detection_module_has_no_network_or_ai() -> None:
    import prospectiq.domain.detection as module

    source = inspect.getsource(module)
    assert "import httpx" not in source
    assert "import requests" not in source
    assert "openai" not in source
    assert "urllib" not in source
    assert "detect(self, evidence" in inspect.getsource(SignalDetectionService.detect)


@pytest.mark.asyncio
async def test_research_hiring_signal_score_warm_and_not_qualified() -> None:
    service, companies, evidence, signals, leads, _queue = _service()
    company = _company()
    item = _evidence(fact="Now hiring: Backend Engineer and QA Engineer.")
    await _seed(companies, evidence, company, [item])

    result = await service.research(_scope(), company.id)

    assert [item.signal_type for item in result.signals] == [SignalType.HIRING_TECH_ROLES]
    assert result.signals[0].evidence_id == item.id
    assert result.score.total_score == SIGNAL_WEIGHTS[SignalType.HIRING_TECH_ROLES]
    assert result.score.classification is LeadClassification.WARM
    assert result.score.is_qualified is False
    assert result.score.distinct_buying_signals == 1
    stored = await signals.list_for_company(_scope(), company.id)
    assert len(stored) == 1
    assert stored[0].evidence_id == item.id
    assert stored[0].reason
    assert leads.scores[0].total_score == 3
    assert result.lead_id is not None
    fetched = await service.get_result(_scope(), company.id)
    assert fetched.score.total_score == 3
    assert fetched.signals[0].evidence_id == item.id


@pytest.mark.asyncio
async def test_duplicate_and_repeated_detection_is_idempotent() -> None:
    service, companies, evidence, signals, _leads, _queue = _service()
    company = _company()
    first = _evidence(fact="We are looking for a Frontend Engineer. Apply today.")
    second = _evidence(fact="We are looking for a Frontend Engineer. Apply today.")
    await _seed(companies, evidence, company, [first, second])

    first_run = await service.research(_scope(), company.id)
    second_run = await service.research(_scope(), company.id)
    stored = await signals.list_for_company(_scope(), company.id)

    assert len(first_run.signals) == 1
    assert len(second_run.signals) == 1
    assert len(stored) == 1
    assert first_run.signals[0].signal_type is second_run.signals[0].signal_type
    assert stored[0].id == (await signals.get_by_company_and_type(
        _scope(), company.id, SignalType.HIRING_TECH_ROLES
    )).id


@pytest.mark.asyncio
async def test_multiple_signals_are_additive_and_can_qualify() -> None:
    detector = SignalDetectionService(rules=[HiringTechRolesRule(), _FundingFixtureRule()])
    service, companies, evidence, _signals, _leads, _queue = _service(detector=detector)
    company = _company()
    hiring = _evidence(fact="This role: Full Stack Engineer. Apply now.")
    funding = _evidence(
        fact="Series B announced on a permitted news source.",
        locator="https://news.test/acme-series-b",
        source_class=SourceClass.PUBLIC_NEWS,
        metadata={"fact_kind": "funding_announcement"},
    )
    await _seed(companies, evidence, company, [hiring, funding])

    result = await service.research(_scope(), company.id)
    assert result.score.total_score == 6
    assert result.score.classification is LeadClassification.HOT
    assert result.score.is_qualified is True
    assert result.score.distinct_buying_signals == 2


@pytest.mark.asyncio
async def test_raw_score_is_not_clamped_to_hot_band() -> None:
    signals = [
        DetectedSignal(SignalType.HIRING_TECH_ROLES, EvidenceId(uuid4()), "hiring"),
        DetectedSignal(SignalType.FUNDING_NEWS, EvidenceId(uuid4()), "funding"),
        DetectedSignal(SignalType.EXPANSION_LAUNCH, EvidenceId(uuid4()), "launch"),
        DetectedSignal(SignalType.TALKS_ABOUT_TECH_GROWTH, EvidenceId(uuid4()), "talk"),
        DetectedSignal(SignalType.CHANGED_JOB_RECENTLY, EvidenceId(uuid4()), "job"),
        DetectedSignal(SignalType.ACTIVE_ON_LINKEDIN, EvidenceId(uuid4()), "li"),
    ]
    result = LeadScoringService(InMemoryLeadRepository()).score_signals(signals)
    assert result.total_score == 13
    assert result.classification is LeadClassification.HOT


@pytest.mark.asyncio
async def test_tenant_isolation_for_signals_and_research() -> None:
    service, companies, evidence, signals, _leads, _queue = _service()
    company_a = _company(TENANT)
    company_b = _company(OTHER_TENANT)
    await _seed(
        companies,
        evidence,
        company_a,
        [_evidence(fact="We are hiring a Data Engineer. Job openings below.")],
    )
    await _seed(companies, evidence, company_b, [])

    await service.research(_scope(TENANT), company_a.id)
    other = await service.research(_scope(OTHER_TENANT), company_b.id)
    assert other.signals == []
    assert other.score.total_score == 0
    assert await signals.list_for_company(_scope(OTHER_TENANT), company_a.id) == []
    assert await signals.list_for_company(_scope(TENANT), company_b.id) == []
    with pytest.raises(PermanentSourceError):
        await service.research(_scope(OTHER_TENANT), company_a.id)


@pytest.mark.asyncio
async def test_submit_uses_existing_research_lead_job() -> None:
    service, companies, evidence, _signals, _leads, queue = _service()
    company = _company()
    await _seed(
        companies,
        evidence,
        company,
        [_evidence(fact="Hiring a Product Manager. Open positions listed.")],
    )
    first = await service.submit(_scope(), company.id)
    second = await service.submit(_scope(), company.id)
    assert first.job_id == second.job_id
    assert second.already_enqueued is True
    job = next(iter(queue.jobs.values()))
    assert job.job_type is JobType.RESEARCH_LEAD
    executed = await service.execute_job(job)
    assert executed.score.total_score == 3
    assert executed.score.is_qualified is False


def test_catalog_documents_deferred_linkedin_and_growth_signals() -> None:
    payload = {item["signal_type"]: item for item in catalog_payload()}
    assert payload["hiring_tech_roles"]["implemented"] is True
    assert payload["hiring_tech_roles"]["weight"] == 3
    assert payload["talks_about_tech_growth"]["implemented"] is False
    assert payload["changed_job_recently"]["implemented"] is False
    assert payload["active_on_linkedin"]["implemented"] is False
    linkedin = str(payload["active_on_linkedin"]["requires_evidence"])
    assert "LinkedIn remains human-controlled" in linkedin
