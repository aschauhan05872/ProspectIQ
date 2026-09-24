from __future__ import annotations

import inspect
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from prospectiq.application.discovery import CompanyDiscoveryService
from prospectiq.application.ingestion import CompanySourceIngestionService
from prospectiq.application.ports import CompanyDiscoveryProvider
from prospectiq.domain.common import TenantId, TenantScope, WorkspaceId
from prospectiq.domain.company import Geography, Industry
from prospectiq.domain.discovery import (
    DiscoveryIngestionStatus,
    DiscoveryRequest,
    FieldVerificationStatus,
    PermanentDiscoveryError,
    ProviderDiscoveryHit,
    RetryableDiscoveryError,
    candidate_website_url,
    discovery_idempotency_key,
    normalize_discovery_request,
)
from prospectiq.domain.discovery_query import build_discovery_query
from prospectiq.domain.evidence import EvidenceOrigin
from prospectiq.domain.jobs import JobType
from prospectiq.domain.source_registry import SourceClass
from prospectiq.infrastructure.config import Settings
from prospectiq.infrastructure.discovery.provider_factory import build_discovery_provider
from prospectiq.infrastructure.discovery.serpapi_provider import SerpApiDiscoveryProvider
from prospectiq.infrastructure.jobs import InMemoryJobQueue
from tests.fakes import (
    InMemoryDiscoveryCandidateRepository,
    InMemoryEvidenceRepository,
)
from tests.test_ingestion import _service as ingestion_service_factory

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
TENANT = TenantId(UUID("00000000-0000-0000-0000-000000000001"))
OTHER = TenantId(UUID("00000000-0000-0000-0000-000000000099"))
WORKSPACE = WorkspaceId(UUID("00000000-0000-0000-0000-000000000002"))


def _scope(tenant_id: TenantId = TENANT) -> TenantScope:
    return TenantScope(tenant_id=tenant_id, workspace_id=WORKSPACE, request_id="discovery-test")


def _request(**overrides: object) -> DiscoveryRequest:
    base = normalize_discovery_request(
        industry="healthtech",
        countries=["USA"],
        employee_min=11,
        employee_max=500,
        hiring_required=True,
        keywords=["platform"],
        limit=5,
    )
    payload = base.to_payload()
    payload.update(overrides)
    return DiscoveryRequest.from_payload(payload)


class _StaticProvider:
    provider_key = "test_provider"

    def __init__(self, hits: list[ProviderDiscoveryHit] | Exception) -> None:
        self._hits = hits

    async def discover(
        self, scope: TenantScope, request: DiscoveryRequest
    ) -> list[ProviderDiscoveryHit]:
        if isinstance(self._hits, Exception):
            raise self._hits
        return self._hits[: request.limit]


def _discovery_service(
    provider: CompanyDiscoveryProvider | None = None,
    *,
    jobs: InMemoryJobQueue | None = None,
) -> tuple[
    CompanyDiscoveryService,
    InMemoryJobQueue,
    InMemoryDiscoveryCandidateRepository,
    InMemoryEvidenceRepository,
    CompanySourceIngestionService,
]:
    queue = jobs or InMemoryJobQueue()
    candidates = InMemoryDiscoveryCandidateRepository()
    evidence = InMemoryEvidenceRepository()
    ingestion, _, _, _ = ingestion_service_factory(jobs=queue)
    service = CompanyDiscoveryService(
        jobs=queue,
        candidates=candidates,
        evidence=evidence,
        ingestion=ingestion,
        provider=provider or _StaticProvider([]),
    )
    return service, queue, candidates, evidence, ingestion


def test_discovery_request_normalization() -> None:
    request = normalize_discovery_request(
        industry="Healthcare / HealthTech",
        countries=["United States", "Canada"],
        employee_min=11,
        employee_max=500,
        hiring_required=True,
        keywords=["  SaaS ", "platform", "platform"],
        limit=150,
    )
    assert request.industry is Industry.HEALTHCARE_HEALTHTECH
    assert request.countries == (Geography.USA, Geography.CANADA)
    assert request.keywords == ("saas", "platform")
    assert request.limit == 100


def test_provider_neutral_query_has_no_provider_syntax() -> None:
    query = build_discovery_query(_request())
    assert "serpapi" not in query.lower()
    assert "healthcare" in query.lower()
    assert "usa" in query.lower()
    assert "hiring" in query.lower()


def test_missing_provider_credentials_raise_permanent_error() -> None:
    settings = Settings(discovery_provider="serpapi", serpapi_api_key="")
    with pytest.raises(PermanentDiscoveryError, match="SerpAPI credentials"):
        build_discovery_provider(settings)


def test_unconfigured_provider_raises_clear_error() -> None:
    settings = Settings(discovery_provider="none")
    with pytest.raises(PermanentDiscoveryError, match="not configured"):
        build_discovery_provider(settings)


@pytest.mark.asyncio
async def test_serpapi_maps_organic_results() -> None:
    payload = {
        "organic_results": [
            {
                "title": "Acme Health",
                "link": "https://www.acme-health.test/about",
                "snippet": "HealthTech platform",
                "position": 1,
            },
            {
                "title": "LinkedIn profile",
                "link": "https://www.linkedin.com/company/acme",
                "snippet": "blocked",
                "position": 2,
            },
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("api_key") == "test-key"
        return httpx.Response(200, json=payload)

    provider = SerpApiDiscoveryProvider(
        api_key="test-key",
        timeout_seconds=5,
        page_size=10,
        max_pages=1,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    hits = await provider.discover(_scope(), _request(limit=2))
    assert len(hits) == 1
    assert hits[0].name == "Acme Health"
    assert hits[0].domain == "acme-health.test"
    assert hits[0].website == "https://www.acme-health.test/about"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (429, RetryableDiscoveryError),
        (503, RetryableDiscoveryError),
        (401, PermanentDiscoveryError),
    ],
)
async def test_serpapi_error_classification(status_code: int, error_type: type[Exception]) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": "provider failure"})

    provider = SerpApiDiscoveryProvider(
        api_key="test-key",
        timeout_seconds=5,
        page_size=10,
        max_pages=1,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(error_type):
        await provider.discover(_scope(), _request())


@pytest.mark.asyncio
async def test_serpapi_timeout_is_retryable() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    provider = SerpApiDiscoveryProvider(
        api_key="test-key",
        timeout_seconds=1,
        page_size=10,
        max_pages=1,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(RetryableDiscoveryError):
        await provider.discover(_scope(), _request())


@pytest.mark.asyncio
async def test_serpapi_malformed_response_is_permanent() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    provider = SerpApiDiscoveryProvider(
        api_key="test-key",
        timeout_seconds=5,
        page_size=10,
        max_pages=1,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(PermanentDiscoveryError, match="malformed JSON"):
        await provider.discover(_scope(), _request())


def test_candidate_website_normalization_reuses_source_url() -> None:
    website, domain = candidate_website_url("https://WWW.Acme-Health.test/careers/")
    assert website == "https://acme-health.test"
    assert domain == "acme-health.test"


@pytest.mark.asyncio
async def test_discovery_enqueues_fetch_source_for_valid_candidates() -> None:
    hits = [
        ProviderDiscoveryHit(
            name="Acme",
            website="https://acme.test/about",
            domain="acme.test",
            source_locator="https://acme.test/about",
        )
    ]
    service, queue, candidates, evidence, _ingestion = _discovery_service(_StaticProvider(hits))
    submission = await service.submit(_scope(), _request())
    job = queue.jobs[f"{TENANT}:{submission.idempotency_key}"]
    result = await service.execute_job(job)
    assert result.accepted_count == 1
    assert result.fetch_jobs_created == 1
    stored = await candidates.list_for_job(_scope(), job.id)
    assert stored[0].ingestion_status is DiscoveryIngestionStatus.FETCH_QUEUED
    fetch_jobs = [item for item in queue.jobs.values() if item.job_type is JobType.FETCH_SOURCE]
    assert len(fetch_jobs) == 1
    assert stored[0].fetch_job_id == fetch_jobs[0].id
    discovery_evidence = next(iter(evidence.items.values()))
    assert discovery_evidence.origin is EvidenceOrigin.DISCOVERY_RECORD
    assert discovery_evidence.source_class is SourceClass.PERMITTED_SEARCH_API


@pytest.mark.asyncio
async def test_discovery_rejects_non_company_search_results() -> None:
    hits = [
        ProviderDiscoveryHit(
            name="IBM Think",
            website="https://www.ibm.com/think/topics/fintech",
            domain="ibm.com",
            source_locator="https://www.ibm.com/think/topics/fintech",
        ),
        ProviderDiscoveryHit(
            name="Stripe",
            website="https://stripe.com/careers",
            domain="stripe.com",
            source_locator="https://stripe.com/careers",
        ),
    ]
    service, queue, candidates, _, _ = _discovery_service(_StaticProvider(hits))
    submission = await service.submit(_scope(), _request())
    job = queue.jobs[f"{TENANT}:{submission.idempotency_key}"]
    result = await service.execute_job(job)
    assert result.accepted_count == 1
    assert result.rejected_count == 1
    assert result.fetch_jobs_created == 1
    stored = await candidates.list_for_job(_scope(), job.id)
    by_status = {item.ingestion_status for item in stored}
    assert DiscoveryIngestionStatus.SKIPPED_NON_COMPANY in by_status
    assert DiscoveryIngestionStatus.FETCH_QUEUED in by_status


@pytest.mark.asyncio
async def test_duplicate_domain_in_one_run_is_not_double_enqueued() -> None:
    hits = [
        ProviderDiscoveryHit(
            name="Acme A",
            website="https://acme.test/a",
            domain="acme.test",
            source_locator="https://acme.test/a",
        ),
        ProviderDiscoveryHit(
            name="Acme B",
            website="https://www.acme.test/b",
            domain="acme.test",
            source_locator="https://acme.test/b",
        ),
    ]
    service, queue, candidates, _, _ = _discovery_service(_StaticProvider(hits))
    submission = await service.submit(_scope(), _request())
    job = queue.jobs[f"{TENANT}:{submission.idempotency_key}"]
    result = await service.execute_job(job)
    assert result.fetch_jobs_created == 1
    stored = await candidates.list_for_job(_scope(), job.id)
    statuses = {item.ingestion_status for item in stored}
    assert DiscoveryIngestionStatus.FETCH_QUEUED in statuses
    assert DiscoveryIngestionStatus.SKIPPED_DUPLICATE in statuses


@pytest.mark.asyncio
async def test_discovery_job_idempotency() -> None:
    service, queue, _, _, _ = _discovery_service(_StaticProvider([]))
    request = _request()
    first = await service.submit(_scope(), request)
    second = await service.submit(_scope(), request)
    assert first.job_id == second.job_id
    assert second.already_enqueued is True
    assert len(queue.jobs) == 1
    assert discovery_idempotency_key(request) in first.idempotency_key


@pytest.mark.asyncio
async def test_repeated_discovery_upserts_same_candidate_locator() -> None:
    hit = ProviderDiscoveryHit(
        name="Acme",
        website="https://acme.test",
        domain="acme.test",
        source_locator="https://acme.test",
    )
    service, queue, candidates, _, _ = _discovery_service(_StaticProvider([hit]))
    request = _request()
    submission = await service.submit(_scope(), request)
    job = queue.jobs[f"{TENANT}:{submission.idempotency_key}"]
    await service.execute_job(job)
    await service.execute_job(job)
    stored = await candidates.list_for_job(_scope(), job.id)
    assert len(stored) == 1


@pytest.mark.asyncio
async def test_tenant_isolation_for_discovery_candidates() -> None:
    hit = ProviderDiscoveryHit(
        name="Acme",
        website="https://acme.test",
        domain="acme.test",
        source_locator="https://acme.test",
    )
    service, queue, candidates, evidence, _ = _discovery_service(_StaticProvider([hit]))
    submission = await service.submit(_scope(TENANT), _request())
    job = queue.jobs[f"{TENANT}:{submission.idempotency_key}"]
    await service.execute_job(job)
    assert await candidates.list_for_job(_scope(OTHER), job.id) == []
    assert all(tenant_id == TENANT for (tenant_id, _) in evidence.items)


@pytest.mark.asyncio
async def test_bounded_result_count_from_provider() -> None:
    hits = [
        ProviderDiscoveryHit(
            name=f"Co {index}",
            website=f"https://co{index}.test",
            domain=f"co{index}.test",
            source_locator=f"https://co{index}.test",
        )
        for index in range(10)
    ]
    service, queue, _, _, _ = _discovery_service(_StaticProvider(hits))
    submission = await service.submit(_scope(), _request(limit=3))
    job = queue.jobs[f"{TENANT}:{submission.idempotency_key}"]
    result = await service.execute_job(job)
    assert result.candidate_count == 3


def test_domain_module_has_no_network_calls() -> None:
    import prospectiq.domain.discovery as discovery_module
    import prospectiq.domain.discovery_query as query_module

    for module in (discovery_module, query_module):
        source = inspect.getsource(module)
        assert "import httpx" not in source
        assert "requests" not in source


def test_icp_field_support_documents_unverified_filters() -> None:
    from prospectiq.domain.discovery import PROVIDER_FIELD_SUPPORT

    support = {item.field_name: item.provider_support for item in PROVIDER_FIELD_SUPPORT}
    assert support["industry"] is FieldVerificationStatus.MATCHED
    assert support["employee_min"] is FieldVerificationStatus.NOT_VERIFIED
    assert support["min_headcount_growth_pct"] is FieldVerificationStatus.NOT_SUPPORTED


def test_invalid_industry_is_permanent() -> None:
    with pytest.raises(PermanentDiscoveryError):
        normalize_discovery_request(
            industry="unknown-industry",
            countries=["USA"],
            employee_min=11,
            employee_max=100,
            hiring_required=False,
            keywords=[],
            limit=5,
        )


@pytest.mark.asyncio
async def test_get_result_returns_persisted_candidates() -> None:
    hit = ProviderDiscoveryHit(
        name="Acme",
        website="https://acme.test",
        domain="acme.test",
        source_locator="https://acme.test",
    )
    service, queue, _, _, _ = _discovery_service(_StaticProvider([hit]))
    submission = await service.submit(_scope(), _request())
    job = queue.jobs[f"{TENANT}:{submission.idempotency_key}"]
    await service.execute_job(job)
    fetched = await service.get_result(_scope(), job.id)
    assert fetched.candidate_count == 1
    assert fetched.candidates[0].normalized_website == "https://acme.test"
