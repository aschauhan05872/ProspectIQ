"""Unit tests for Phase 4 controlled company research."""

from __future__ import annotations

import ipaddress
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest

from prospectiq.application.company_research import CompanyResearchService
from prospectiq.domain.common import CompanyId, TenantId, TenantScope
from prospectiq.domain.company import Company
from prospectiq.domain.company_research import (
    CompanyResearchStatus,
    PermanentCompanyResearchError,
    ResearchErrorCode,
    ResearchPageFetchStatus,
    RetryableCompanyResearchError,
)
from prospectiq.domain.evidence import EvidenceOrigin
from prospectiq.domain.ingestion import PermanentSourceError, SourceFactKind
from prospectiq.domain.jobs import JobStatus, JobType
from prospectiq.domain.research_plan import merge_discovered_pages
from prospectiq.infrastructure.html_links import extract_page_links
from prospectiq.infrastructure.http_fetch import FetchLimits, SafeHttpFetcher
from prospectiq.infrastructure.jobs import InMemoryJobQueue
from tests.fakes import (
    InMemoryCompanyRepository,
    InMemoryCompanyResearchCaseRepository,
    InMemoryEvidenceRepository,
    InMemoryResearchPageRepository,
)

TENANT = TenantId(UUID("00000000-0000-0000-0000-000000000001"))
OTHER_TENANT = TenantId(UUID("00000000-0000-0000-0000-000000000099"))
NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


def _scope(tenant: TenantId = TENANT) -> TenantScope:
    return TenantScope(tenant_id=tenant)


def _company(
    *,
    company_id: UUID | None = None,
    website: str | None = "https://acme.test",
    tenant: TenantId = TENANT,
) -> Company:
    cid = company_id or uuid4()
    return Company(
        id=CompanyId(cid),
        tenant_id=tenant,
        name="Acme Inc",
        normalized_name="acme.test",
        website=website,
        industry=None,
        geography=None,
        employee_count=100,
        headcount_growth_pct=None,
        company_type=None,
        is_hiring=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _resolve(_host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    return [ipaddress.ip_address("8.8.8.8")]


def _html_fetcher(pages: dict[str, str], *, status: int = 200) -> SafeHttpFetcher:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url).rstrip("/")
        for key, html in pages.items():
            if url == key.rstrip("/") or url.endswith(key.rstrip("/")):
                return httpx.Response(status, headers={"content-type": "text/html"}, text=html)
        return httpx.Response(404, headers={"content-type": "text/html"}, text="Not found")

    return SafeHttpFetcher(
        FetchLimits(),
        resolve_host=_resolve,
        transport=httpx.MockTransport(handler),
    )


def _service(
    *,
    fetcher: SafeHttpFetcher | None = None,
    max_pages: int = 10,
    jobs: InMemoryJobQueue | None = None,
) -> tuple[
    CompanyResearchService,
    InMemoryJobQueue,
    InMemoryCompanyRepository,
    InMemoryCompanyResearchCaseRepository,
    InMemoryResearchPageRepository,
    InMemoryEvidenceRepository,
]:
    queue = jobs or InMemoryJobQueue()
    companies = InMemoryCompanyRepository()
    cases = InMemoryCompanyResearchCaseRepository()
    pages = InMemoryResearchPageRepository()
    evidence = InMemoryEvidenceRepository()
    home_html = """
    <html><head><title>Acme Home</title></head>
    <body><p>We provide telemedicine services.</p>
    <a href="/about">About Us</a>
    <a href="/services">Services</a>
    <a href="https://linkedin.com/company/acme">LinkedIn</a>
    </body></html>
    """
    default_fetcher = fetcher or _html_fetcher(
        {
            "https://acme.test": home_html,
            "https://acme.test/about": "<html><head><title>About</title></head>"
            "<body><p>Founded in 2010.</p></body></html>",
            "https://acme.test/services": "<html><head><title>Services</title></head>"
            "<body><p>Virtual consultations.</p></body></html>",
        }
    )
    service = CompanyResearchService(
        companies=companies,
        cases=cases,
        pages=pages,
        evidence=evidence,
        jobs=queue,
        fetcher=default_fetcher,
        max_pages_per_company=max_pages,
        max_research_time_seconds=120.0,
    )
    return service, queue, companies, cases, pages, evidence


async def _seed_company(
    companies: InMemoryCompanyRepository,
    *,
    website: str | None = "https://acme.test",
) -> Company:
    company = _company(website=website)
    await companies.upsert(_scope(), company)
    return company


@pytest.mark.asyncio
async def test_submit_creates_case_and_job() -> None:
    service, queue, companies, cases, _, _ = _service()
    company = await _seed_company(companies)
    submission = await service.submit(_scope(), company.id)
    assert submission.status is CompanyResearchStatus.QUEUED
    stored = await cases.get(_scope(), submission.case_id)
    assert stored is not None
    assert stored.job_id == submission.job_id
    assert len(queue.jobs) == 1
    job = next(iter(queue.jobs.values()))
    assert job.job_type is JobType.RESEARCH_COMPANY


@pytest.mark.asyncio
async def test_submit_rejects_company_without_website() -> None:
    service, _, companies, _, _, _ = _service()
    company = await _seed_company(companies, website=None)
    with pytest.raises(PermanentCompanyResearchError) as exc:
        await service.submit(_scope(), company.id)
    assert exc.value.error_code is ResearchErrorCode.NO_WEBSITE


@pytest.mark.asyncio
async def test_execute_researches_homepage_and_same_domain_links() -> None:
    service, queue, companies, _, pages, evidence = _service(max_pages=3)
    company = await _seed_company(companies)
    submission = await service.submit(_scope(), company.id)
    job = await queue.claim(worker_id="w1", now=NOW)
    assert job is not None
    result = await service.execute_job(job)
    assert result.case.status is CompanyResearchStatus.COMPLETED
    assert result.case.pages_fetched >= 2
    stored_pages = await pages.list_for_case(_scope(), submission.case_id)
    urls = {page.normalized_url for page in stored_pages}
    assert any(url.rstrip("/") == "https://acme.test" for url in urls)
    assert any("/about" in url or "/services" in url for url in urls)
    assert all("linkedin.com" not in url for url in urls)
    items = await evidence.list_for_company(_scope(), company.id)
    assert len(items) >= 2
    assert all(item.origin is EvidenceOrigin.SOURCE_DERIVED for item in items)
    fact_kind = SourceFactKind.RESEARCH_PAGE_CONTENT.value
    assert all(item.metadata.get("fact_kind") == fact_kind for item in items)


@pytest.mark.asyncio
async def test_evidence_deduplication_on_unchanged_content() -> None:
    service, queue, companies, _, _, evidence = _service(max_pages=1)
    company = await _seed_company(companies)
    await service.submit(_scope(), company.id)
    job1 = await queue.claim(worker_id="w1", now=NOW)
    assert job1 is not None
    first = await service.execute_job(job1)

    await service.submit(_scope(), company.id)
    job2 = await queue.claim(worker_id="w1", now=NOW)
    assert job2 is not None
    second = await service.execute_job(job2)

    first_ids = {page.evidence_id for page in first.pages if page.evidence_id}
    second_ids = {page.evidence_id for page in second.pages if page.evidence_id}
    assert first_ids == second_ids
    assert len(await evidence.list_for_company(_scope(), company.id)) == len(first_ids)


@pytest.mark.asyncio
async def test_tenant_isolation() -> None:
    service, _, companies, cases, _, _ = _service()
    company = await _seed_company(companies)
    submission = await service.submit(_scope(), company.id)
    assert await cases.get(_scope(OTHER_TENANT), submission.case_id) is None


@pytest.mark.asyncio
async def test_all_pages_failed_marks_case_failed() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403, headers={"content-type": "text/html"}, text="Forbidden")

    fetcher = SafeHttpFetcher(
        FetchLimits(), resolve_host=_resolve, transport=httpx.MockTransport(handler)
    )
    service, queue, companies, _, _, _ = _service(fetcher=fetcher)
    company = await _seed_company(companies)
    await service.submit(_scope(), company.id)
    job = await queue.claim(worker_id="w1", now=NOW)
    assert job is not None
    result = await service.execute_job(job)
    assert result.case.status is CompanyResearchStatus.FAILED
    assert result.case.error_code is ResearchErrorCode.ALL_PAGES_FAILED


@pytest.mark.asyncio
async def test_mixed_success_and_failure_is_completed_with_partial_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).rstrip("/").endswith("acme.test"):
            html = (
                "<html><head><title>Home</title></head>"
                "<body><a href='/about'>About</a></body></html>"
            )
            return httpx.Response(200, headers={"content-type": "text/html"}, text=html)
        return httpx.Response(500, headers={"content-type": "text/html"}, text="Error")

    fetcher = SafeHttpFetcher(
        FetchLimits(), resolve_host=_resolve, transport=httpx.MockTransport(handler)
    )
    service, queue, companies, _, pages, _ = _service(fetcher=fetcher, max_pages=3)
    company = await _seed_company(companies)
    submission = await service.submit(_scope(), company.id)
    job = await queue.claim(worker_id="w1", now=NOW)
    result = await service.execute_job(job)
    assert result.case.status is CompanyResearchStatus.COMPLETED
    assert result.case.error_code is ResearchErrorCode.PARTIAL_FAILURE
    stored = await pages.list_for_case(_scope(), submission.case_id)
    statuses = {page.fetch_status for page in stored}
    assert ResearchPageFetchStatus.SUCCEEDED in statuses
    assert ResearchPageFetchStatus.FAILED in statuses


@pytest.mark.asyncio
async def test_retryable_homepage_failure_propagates_for_job_retry() -> None:
    calls = {"count": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        raise httpx.TimeoutException("timeout")

    fetcher = SafeHttpFetcher(
        FetchLimits(), resolve_host=_resolve, transport=httpx.MockTransport(handler)
    )
    service, queue, companies, _, _, _ = _service(fetcher=fetcher)
    company = await _seed_company(companies)
    await service.submit(_scope(), company.id)
    job = await queue.claim(worker_id="w1", now=NOW)
    assert job is not None
    with pytest.raises(RetryableCompanyResearchError):
        await service.execute_job(job)
    failed = await queue.fail(job, "timeout", now=NOW)
    assert failed.status is JobStatus.FAILED


@pytest.mark.asyncio
async def test_permanent_homepage_failure_does_not_retry_when_later_pages_succeed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.rstrip("/").endswith("acme.test"):
            html = "<html><body><a href='/about'>About</a></body></html>"
            return httpx.Response(200, headers={"content-type": "text/html"}, text=html)
        if "/about" in url:
            raise PermanentSourceError("unsupported content type")
        return httpx.Response(404, text="missing")

    fetcher = SafeHttpFetcher(
        FetchLimits(), resolve_host=_resolve, transport=httpx.MockTransport(handler)
    )
    service, queue, companies, _, _, _ = _service(fetcher=fetcher, max_pages=2)
    company = await _seed_company(companies)
    await service.submit(_scope(), company.id)
    job = await queue.claim(worker_id="w1", now=NOW)
    result = await service.execute_job(job)
    assert result.case.pages_fetched >= 1
    assert result.case.status is CompanyResearchStatus.COMPLETED


def test_extract_page_links_and_merge_discovered_pages_responsibilities() -> None:
    html = """
    <html><body>
    <a href="/about">About</a>
    <a href="https://other.test/x">External</a>
    </body></html>
    """
    links = extract_page_links("https://acme.test", html.encode(), "text/html")
    extracted_urls = [url for url, _ in links]
    assert "https://acme.test/about" in extracted_urls
    assert "https://other.test/x" in extracted_urls

    plan = merge_discovered_pages(
        homepage_url="https://acme.test",
        identity_host="acme.test",
        discovered=links,
        max_pages=10,
    )
    planned_urls = {item.normalized_url for item in plan}
    assert any(url.rstrip("/") == "https://acme.test" for url in planned_urls)
    assert "https://acme.test/about" in planned_urls
    assert not any("other.test" in url for url in planned_urls)


@pytest.mark.asyncio
async def test_job_idempotency_key_prevents_duplicate_jobs_for_same_case() -> None:
    service, queue, companies, cases, _, _ = _service()
    company = await _seed_company(companies)
    first = await service.submit(_scope(), company.id)
    case = await cases.get(_scope(), first.case_id)
    assert case is not None
    await queue.enqueue(
        _scope(),
        JobType.RESEARCH_COMPANY,
        f"research_company:{first.case_id}",
        {"company_id": str(company.id), "research_case_id": str(first.case_id)},
    )
    assert len(queue.jobs) == 1


@pytest.mark.asyncio
async def test_ssrf_private_resolution_rejected_via_shared_fetcher() -> None:
    def private_resolve(_host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        return [ipaddress.ip_address("127.0.0.1")]

    transport = httpx.MockTransport(lambda _: httpx.Response(200))
    fetcher = SafeHttpFetcher(FetchLimits(), resolve_host=private_resolve, transport=transport)
    service, queue, companies, _, _, _ = _service(fetcher=fetcher)
    company = await _seed_company(companies, website="https://evil.test")
    await service.submit(_scope(), company.id)
    job = await queue.claim(worker_id="w1", now=NOW)
    assert job is not None
    result = await service.execute_job(job)
    assert result.case.status is CompanyResearchStatus.FAILED


@pytest.mark.asyncio
async def test_redirect_loop_marks_page_failed() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://acme.test"}, text="loop")

    fetcher = SafeHttpFetcher(
        FetchLimits(max_redirects=2),
        resolve_host=_resolve,
        transport=httpx.MockTransport(handler),
    )
    service, queue, companies, _, pages, _ = _service(fetcher=fetcher, max_pages=1)
    company = await _seed_company(companies)
    submission = await service.submit(_scope(), company.id)
    job = await queue.claim(worker_id="w1", now=NOW)
    result = await service.execute_job(job)
    assert result.case.status is CompanyResearchStatus.FAILED
    stored = await pages.list_for_case(_scope(), submission.case_id)
    assert stored[0].fetch_status is ResearchPageFetchStatus.FAILED


@pytest.mark.asyncio
async def test_get_latest_for_company() -> None:
    service, queue, companies, _, _, _ = _service(max_pages=1)
    company = await _seed_company(companies)
    await service.submit(_scope(), company.id)
    job = await queue.claim(worker_id="w1", now=NOW)
    await service.execute_job(job)
    latest = await service.get_latest_for_company(_scope(), company.id)
    assert latest is not None
    assert latest.case.company_id == company.id
    assert latest.evidence_count >= 1
