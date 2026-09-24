from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from prospectiq.application.ingestion import CompanySourceIngestionService
from prospectiq.application.ports import FetchRequest, NormalizedRecord
from prospectiq.domain.common import TenantId, TenantScope
from prospectiq.domain.evidence import EvidenceOrigin
from prospectiq.domain.ingestion import PermanentSourceError, RetryableSourceError
from prospectiq.domain.jobs import JobStatus, JobType
from prospectiq.domain.source_registry import SourceClass
from prospectiq.domain.source_url import parse_source_url
from prospectiq.infrastructure.http_fetch import FetchLimits, SafeHttpFetcher
from prospectiq.infrastructure.jobs import InMemoryJobQueue
from prospectiq.infrastructure.web_source import HttpPageSourceAdapter
from tests.fakes import (
    InMemoryCompanyRepository,
    InMemoryCompanySourceRepository,
    InMemoryEvidenceRepository,
)


class _StaticAdapter:
    adapter_key = "test"
    source_class = SourceClass.COMPANY_WEBSITE

    def __init__(self, records: list[NormalizedRecord] | Exception) -> None:
        self._records = records

    async def fetch(self, request: FetchRequest) -> list[NormalizedRecord]:
        if isinstance(self._records, Exception):
            raise self._records
        return self._records


def _scope(tenant: str = "00000000-0000-0000-0000-000000000001") -> TenantScope:
    return TenantScope(tenant_id=TenantId(UUID(tenant)))


def _service(
    adapter: object | None = None,
    *,
    jobs: InMemoryJobQueue | None = None,
) -> tuple[
    CompanySourceIngestionService,
    InMemoryJobQueue,
    InMemoryCompanyRepository,
    InMemoryEvidenceRepository,
]:
    queue = jobs or InMemoryJobQueue()
    companies = InMemoryCompanyRepository()
    sources = InMemoryCompanySourceRepository()
    evidence = InMemoryEvidenceRepository()
    records = [
        NormalizedRecord(
            fact="Company page titled 'Acme': We build software.",
            locator="https://acme.test",
            snippet="We build software.",
            collected_at=datetime(2026, 9, 22, 12, 0, tzinfo=UTC),
            confidence="high",
            metadata={
                "fact_kind": "page_content",
                "title": "Acme",
                "final_url": "https://acme.test",
                "http_status": 200,
            },
        )
    ]
    chosen = adapter or _StaticAdapter(records)
    service = CompanySourceIngestionService(
        jobs=queue,
        companies=companies,
        company_sources=sources,
        evidence=evidence,
        adapters={
            SourceClass.COMPANY_WEBSITE: chosen,  # type: ignore[arg-type]
            SourceClass.CAREERS_PAGE: chosen,  # type: ignore[arg-type]
        },
    )
    return service, queue, companies, evidence


@pytest.mark.asyncio
async def test_submit_is_idempotent_for_the_same_url() -> None:
    service, queue, _, _ = _service()
    first = await service.submit(_scope(), "https://www.acme.test/")
    second = await service.submit(_scope(), "https://acme.test")
    assert first.job_id == second.job_id
    assert second.already_enqueued is True
    assert first.source_class is SourceClass.COMPANY_WEBSITE
    assert len(queue.jobs) == 1


@pytest.mark.asyncio
async def test_ingest_persists_source_derived_evidence_and_company() -> None:
    service, _, companies, evidence = _service()
    result = await service.ingest(_scope(), "https://acme.test")
    assert result.page_title == "Acme"
    assert result.identity_requires_review is False
    stored = next(iter(companies.items.values()))
    assert stored.normalized_name == "acme.test"
    assert stored.website == "https://acme.test"
    locator = parse_source_url("https://acme.test").normalized
    items = await evidence.list_for_locator(_scope(), locator)
    assert len(items) == 1
    assert items[0].origin is EvidenceOrigin.SOURCE_DERIVED
    assert items[0].source_locator == locator
    assert items[0].company_id == result.company_id
    assert items[0].collected_at is not None
    assert items[0].source_class is SourceClass.COMPANY_WEBSITE


@pytest.mark.asyncio
async def test_duplicate_ingest_does_not_create_extra_evidence() -> None:
    service, _, companies, evidence = _service()
    first = await service.ingest(_scope(), "https://acme.test")
    second = await service.ingest(_scope(), "https://acme.test")
    assert first.company_id == second.company_id
    assert first.evidence_ids == second.evidence_ids
    assert len(companies.items) == 1
    assert len(evidence.items) == 1


@pytest.mark.asyncio
async def test_tenant_isolation_on_ingest_path() -> None:
    service, _, companies, evidence = _service()
    await service.ingest(_scope("00000000-0000-0000-0000-000000000001"), "https://acme.test")
    other = _scope("00000000-0000-0000-0000-000000000099")
    assert await companies.get_by_normalized_name(other, "acme.test") is None
    locator = parse_source_url("https://acme.test").normalized
    assert await evidence.list_for_locator(other, locator) == []
    other_result = await service.ingest(other, "https://acme.test")
    assert other_result.tenant_id == other.tenant_id
    assert len(companies.items) == 2


@pytest.mark.asyncio
async def test_careers_page_records_hiring_language_not_a_score() -> None:
    html = """
    <html><head><title>Acme Jobs</title></head>
    <body><h1>Open roles</h1>
    <p>We are hiring a Software Engineer and a Product Manager.</p>
    </body></html>
    """

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text=html)

    def resolve(_host: str) -> list:
        import ipaddress

        return [ipaddress.ip_address("8.8.8.8")]

    fetcher = SafeHttpFetcher(
        FetchLimits(),
        resolve_host=resolve,
        transport=httpx.MockTransport(handler),
    )
    adapter = HttpPageSourceAdapter(fetcher, SourceClass.CAREERS_PAGE)
    service, _, _, evidence = _service(adapter)
    result = await service.ingest(_scope(), "https://acme.test/careers")
    assert result.source_class is SourceClass.CAREERS_PAGE
    assert "software engineer" in result.observed_hiring_phrases
    assert "product manager" in result.observed_hiring_phrases
    careers_locator = parse_source_url("https://acme.test/careers").normalized
    kinds = {
        item.metadata.get("fact_kind")
        for item in await evidence.list_for_locator(_scope(), careers_locator)
    }
    assert kinds == {"page_content", "hiring_language_observed"}
    hiring = next(
        item
        for item in await evidence.list_for_locator(_scope(), careers_locator)
        if item.metadata.get("fact_kind") == "hiring_language_observed"
    )
    assert hiring.origin is EvidenceOrigin.SOURCE_DERIVED
    assert hiring.metadata.get("is_inferred_signal") is False


@pytest.mark.asyncio
async def test_retryable_and_permanent_job_failures() -> None:
    queue = InMemoryJobQueue()
    retry_service, _, _, _ = _service(_StaticAdapter(RetryableSourceError("timeout")), jobs=queue)
    await queue.enqueue(
        _scope(),
        JobType.FETCH_SOURCE,
        "fetch_source:https://acme.test",
        {"url": "https://acme.test"},
    )
    claimed = await queue.claim(worker_id="w1", now=datetime(2026, 9, 22, 12, 0, tzinfo=UTC))
    assert claimed is not None
    with pytest.raises(RetryableSourceError):
        await retry_service.execute_job(claimed)
    failed = await queue.fail(claimed, "timeout", now=claimed.updated_at)
    assert failed.status is JobStatus.FAILED

    permanent_service, pqueue, _, _ = _service(_StaticAdapter(PermanentSourceError("bad url")))
    pjob = await pqueue.enqueue(
        _scope(), JobType.FETCH_SOURCE, "fetch_source:https://nope.test", {"url": "https://nope.test"}
    )
    pclaimed = await pqueue.claim(worker_id="w1", now=datetime(2026, 9, 22, 12, 0, tzinfo=UTC))
    assert pclaimed is not None
    with pytest.raises(PermanentSourceError):
        await permanent_service.execute_job(pclaimed)
    dead = await pqueue.fail(pclaimed, "bad url", now=pclaimed.updated_at, permanent=True)
    assert dead.status is JobStatus.DEAD
    assert pjob.id == pclaimed.id


@pytest.mark.asyncio
async def test_successful_job_execute() -> None:
    service, queue, _, _ = _service()
    accepted = await service.submit(_scope(), "https://acme.test")
    claimed = await queue.claim(worker_id="w1", now=datetime(2026, 9, 22, 12, 0, tzinfo=UTC))
    assert claimed is not None
    result = await service.execute_job(claimed)
    await queue.complete(claimed)
    assert result.company_id is not None
    assert accepted.job_id == claimed.id
    assert claimed.status is JobStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_http_www_and_trailing_slash_share_company() -> None:
    service, _, companies, _ = _service()
    first = await service.ingest(_scope(), "https://www.acme.test/about/")
    second = await service.ingest(_scope(), "https://acme.test/about")
    assert first.company_id == second.company_id
    assert len(companies.items) == 1
