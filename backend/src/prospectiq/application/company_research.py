"""Controlled multi-page company website research (Phase 4)."""

from __future__ import annotations

from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

from prospectiq.application.ports import (
    CompanyRepository,
    CompanyResearchCaseRepository,
    EvidenceRepository,
    JobQueue,
    ResearchPageRepository,
)
from prospectiq.domain.common import CompanyId, Confidence, EvidenceId, TenantScope, utcnow
from prospectiq.domain.company import Company
from prospectiq.domain.company_research import (
    COMPANY_RESEARCH_VERSION,
    CompanyResearchCase,
    CompanyResearchResult,
    CompanyResearchStatus,
    CompanyResearchSubmission,
    PermanentCompanyResearchError,
    ResearchErrorCode,
    ResearchPage,
    ResearchPageFetchStatus,
    RetryableCompanyResearchError,
    build_page_fact,
    content_fingerprint,
    research_job_idempotency_key,
)
from prospectiq.domain.evidence import Evidence, EvidenceOrigin
from prospectiq.domain.ingestion import PermanentSourceError, RetryableSourceError, SourceFactKind
from prospectiq.domain.jobs import Job, JobType
from prospectiq.domain.research_plan import build_initial_plan, merge_discovered_pages
from prospectiq.domain.source_registry import SourceClass
from prospectiq.domain.source_url import InvalidSourceUrl, parse_source_url
from prospectiq.infrastructure.html_links import extract_page_links
from prospectiq.infrastructure.html_normalize import normalize_page
from prospectiq.infrastructure.http_fetch import SafeHttpFetcher
from prospectiq.infrastructure.logging import get_logger

logger = get_logger("prospectiq.company_research")


class CompanyResearchService:
    def __init__(
        self,
        *,
        companies: CompanyRepository,
        cases: CompanyResearchCaseRepository,
        pages: ResearchPageRepository,
        evidence: EvidenceRepository,
        jobs: JobQueue,
        fetcher: SafeHttpFetcher,
        max_pages_per_company: int,
        max_research_time_seconds: float,
    ) -> None:
        self._companies = companies
        self._cases = cases
        self._pages = pages
        self._evidence = evidence
        self._jobs = jobs
        self._fetcher = fetcher
        self._max_pages = max(1, min(max_pages_per_company, 50))
        self._max_research_time = max_research_time_seconds

    async def submit(self, scope: TenantScope, company_id: CompanyId) -> CompanyResearchSubmission:
        _assert_tenant(scope)
        company = await self._require_company(scope, company_id)
        website = (company.website or "").strip()
        if not website:
            raise PermanentCompanyResearchError(
                "Company has no website URL. Resolve company or set website before research.",
                error_code=ResearchErrorCode.NO_WEBSITE,
            )
        try:
            parsed = parse_source_url(website)
        except InvalidSourceUrl as exc:
            raise PermanentCompanyResearchError(
                str(exc),
                error_code=ResearchErrorCode.INVALID_WEBSITE,
            ) from exc

        now = utcnow()
        case_id = uuid4()
        case = CompanyResearchCase(
            id=case_id,
            tenant_id=scope.tenant_id,
            company_id=company.id,
            status=CompanyResearchStatus.QUEUED,
            job_id=None,
            requested_at=now,
            started_at=None,
            completed_at=None,
            failed_at=None,
            pages_requested=0,
            pages_fetched=0,
            pages_failed=0,
            research_version=COMPANY_RESEARCH_VERSION,
            error_code=None,
            error_message_safe=None,
            created_at=now,
            updated_at=now,
        )
        await self._cases.create(scope, case)

        payload: dict[str, Any] = {
            "company_id": str(company.id),
            "research_case_id": str(case_id),
            "website": parsed.normalized,
            "identity_host": parsed.identity_host,
        }
        if scope.workspace_id is not None:
            payload["workspace_id"] = str(scope.workspace_id)

        job = await self._jobs.enqueue(
            scope,
            JobType.RESEARCH_COMPANY,
            research_job_idempotency_key(case_id),
            payload,
        )
        case.job_id = job.id
        case.updated_at = utcnow()
        await self._cases.update(scope, case)

        logger.info(
            "company_research_submitted",
            tenant_id=str(scope.tenant_id),
            company_id=str(company.id),
            case_id=str(case_id),
            job_id=str(job.id),
        )
        return CompanyResearchSubmission(
            case_id=case_id,
            job_id=job.id,
            status=case.status,
            already_enqueued=bool(job.extra.get("idempotent_replay")),
        )

    async def execute_job(self, job: Job) -> CompanyResearchResult:
        scope = TenantScope(tenant_id=job.tenant_id, job_id=str(job.id))
        company_id = CompanyId(UUID(str(job.payload["company_id"])))
        case_id = UUID(str(job.payload["research_case_id"]))
        case = await self._cases.get(scope, case_id)
        if case is None:
            raise PermanentCompanyResearchError("Research case not found.")
        if case.company_id != company_id:
            raise PermanentCompanyResearchError("Research case company mismatch.")

        started = perf_counter()
        now = utcnow()
        case.status = CompanyResearchStatus.RUNNING
        case.started_at = now
        case.updated_at = now
        await self._cases.update(scope, case)

        homepage = str(job.payload.get("website") or "")
        identity_host = str(job.payload.get("identity_host") or "")
        if not homepage or not identity_host:
            company = await self._require_company(scope, company_id)
            if not company.website:
                await self._fail_case(
                    scope,
                    case,
                    error_code=ResearchErrorCode.NO_WEBSITE,
                    message="Company has no website URL.",
                )
                return await self._result(scope, case)
            parsed = parse_source_url(company.website)
            homepage = parsed.normalized
            identity_host = parsed.identity_host

        plan = build_initial_plan(homepage, max_pages=self._max_pages)
        case.pages_requested = len(plan)
        await self._cases.update(scope, case)

        saved_pages: list[ResearchPage] = []
        discovered: list[tuple[str, str | None]] = []
        fetched = 0
        failed = 0

        for planned in plan:
            if perf_counter() - started > self._max_research_time:
                logger.warning(
                    "company_research_time_budget_exceeded",
                    tenant_id=str(scope.tenant_id),
                    case_id=str(case.id),
                )
                break
            page_record, page_discovered = await self._fetch_and_persist(
                scope,
                case=case,
                planned_url=planned.normalized_url,
                page_type=planned.page_type,
                identity_host=identity_host,
                fetched_so_far=fetched,
            )
            saved_pages.append(page_record)
            if page_record.fetch_status is ResearchPageFetchStatus.SUCCEEDED:
                fetched += 1
                discovered.extend(page_discovered)
            else:
                failed += 1

        if discovered and len(saved_pages) < self._max_pages:
            extended = merge_discovered_pages(
                homepage_url=homepage,
                identity_host=identity_host,
                discovered=discovered,
                max_pages=self._max_pages,
            )
            already = {item.normalized_url for item in saved_pages}
            for planned in extended:
                if planned.normalized_url in already:
                    continue
                if len(saved_pages) >= self._max_pages:
                    break
                if perf_counter() - started > self._max_research_time:
                    break
                case.pages_requested += 1
                page_record, _ = await self._fetch_and_persist(
                    scope,
                    case=case,
                    planned_url=planned.normalized_url,
                    page_type=planned.page_type,
                    identity_host=identity_host,
                    fetched_so_far=fetched,
                )
                saved_pages.append(page_record)
                already.add(planned.normalized_url)
                if page_record.fetch_status is ResearchPageFetchStatus.SUCCEEDED:
                    fetched += 1
                else:
                    failed += 1

        case.pages_fetched = fetched
        case.pages_failed = failed
        case.pages_requested = len(saved_pages)
        case.updated_at = utcnow()

        if fetched == 0:
            await self._fail_case(
                scope,
                case,
                error_code=ResearchErrorCode.ALL_PAGES_FAILED,
                message="All researched pages failed to fetch.",
            )
        elif failed > 0:
            case.status = CompanyResearchStatus.COMPLETED
            case.completed_at = utcnow()
            case.error_code = ResearchErrorCode.PARTIAL_FAILURE
            case.error_message_safe = f"{failed} of {len(saved_pages)} pages failed."
            await self._cases.update(scope, case)
            logger.info(
                "company_research_completed_partial",
                tenant_id=str(scope.tenant_id),
                case_id=str(case.id),
                fetched=fetched,
                failed=failed,
            )
        else:
            case.status = CompanyResearchStatus.COMPLETED
            case.completed_at = utcnow()
            case.error_code = None
            case.error_message_safe = None
            await self._cases.update(scope, case)
            logger.info(
                "company_research_completed",
                tenant_id=str(scope.tenant_id),
                case_id=str(case.id),
                fetched=fetched,
            )

        return await self._result(scope, case, pages=saved_pages)

    async def get_case(self, scope: TenantScope, case_id: UUID) -> CompanyResearchResult | None:
        case = await self._cases.get(scope, case_id)
        if case is None:
            return None
        pages = await self._pages.list_for_case(scope, case_id)
        return await self._result(scope, case, pages=pages)

    async def get_latest_for_company(
        self, scope: TenantScope, company_id: CompanyId
    ) -> CompanyResearchResult | None:
        case = await self._cases.get_latest_for_company(scope, company_id)
        if case is None:
            return None
        pages = await self._pages.list_for_case(scope, case.id)
        return await self._result(scope, case, pages=pages)

    async def _fetch_and_persist(
        self,
        scope: TenantScope,
        *,
        case: CompanyResearchCase,
        planned_url: str,
        page_type: object,
        identity_host: str,
        fetched_so_far: int = 0,
    ) -> tuple[ResearchPage, list[tuple[str, str | None]]]:
        now = utcnow()
        page_id = uuid4()
        discovered: list[tuple[str, str | None]] = []
        page = ResearchPage(
            id=page_id,
            tenant_id=scope.tenant_id,
            research_case_id=case.id,
            company_id=case.company_id,
            url=planned_url,
            normalized_url=planned_url,
            page_type=page_type,  # type: ignore[arg-type]
            title=None,
            http_status=None,
            content_type=None,
            content_hash=None,
            normalized_text=None,
            fetched_at=None,
            fetch_duration_ms=None,
            fetch_status=ResearchPageFetchStatus.FAILED,
            failure_class="unknown",
            evidence_id=None,
            created_at=now,
            updated_at=now,
        )

        if not identity_host or not planned_url.startswith(("http://", "https://")):
            page.failure_class = "invalid_url"
            return await self._save_page(scope, page), discovered

        try:
            fetched = await self._fetcher.get(planned_url)
            normalized = normalize_page(fetched.body, fetched.content_type)
            text = normalized.text
            content_hash = content_fingerprint(text)
            page.http_status = fetched.status_code
            page.content_type = fetched.content_type
            page.title = normalized.title
            page.content_hash = content_hash
            page.normalized_text = text
            page.fetched_at = utcnow()
            page.fetch_duration_ms = fetched.duration_ms
            page.fetch_status = ResearchPageFetchStatus.SUCCEEDED
            page.failure_class = None
            page.updated_at = utcnow()

            evidence_id = await self._upsert_page_evidence(
                scope,
                case=case,
                page=page,
                final_url=fetched.final_url,
            )
            page.evidence_id = evidence_id
            discovered = extract_page_links(fetched.final_url, fetched.body, fetched.content_type)
            logger.info(
                "company_research_page_succeeded",
                tenant_id=str(scope.tenant_id),
                case_id=str(case.id),
                page_type=str(page_type),
                http_status=fetched.status_code,
            )
        except RetryableSourceError as exc:
            page.failure_class = "retryable_http"
            saved = await self._save_page(scope, page)
            if fetched_so_far == 0:
                raise RetryableCompanyResearchError(str(exc)) from exc
            return saved, discovered
        except PermanentSourceError as exc:
            page.failure_class = "permanent_http"
            logger.info(
                "company_research_page_failed",
                tenant_id=str(scope.tenant_id),
                case_id=str(case.id),
                error=str(exc),
            )
        except Exception as exc:
            page.failure_class = "permanent_unknown"
            logger.info(
                "company_research_page_failed",
                tenant_id=str(scope.tenant_id),
                case_id=str(case.id),
                error=str(exc),
            )

        return await self._save_page(scope, page), discovered

    async def _upsert_page_evidence(
        self,
        scope: TenantScope,
        *,
        case: CompanyResearchCase,
        page: ResearchPage,
        final_url: str,
    ) -> EvidenceId:
        assert page.content_hash is not None
        assert page.normalized_text is not None
        parsed = parse_source_url(final_url)
        source_class = (
            SourceClass.CAREERS_PAGE
            if parsed.source_class is SourceClass.CAREERS_PAGE
            else SourceClass.COMPANY_WEBSITE
        )
        locator = parsed.normalized
        existing_rows = await self._evidence.list_for_locator(scope, locator)
        for item in existing_rows:
            if (
                item.metadata.get("fact_kind") == SourceFactKind.RESEARCH_PAGE_CONTENT.value
                and item.metadata.get("content_hash") == page.content_hash
            ):
                return item.id

        fact = build_page_fact(
            page_type=page.page_type,
            title=page.title,
            text=page.normalized_text,
        )
        evidence = Evidence(
            id=EvidenceId(uuid4()),
            tenant_id=scope.tenant_id,
            fact=fact,
            origin=EvidenceOrigin.SOURCE_DERIVED,
            source_class=source_class,
            source_locator=locator,
            collected_at=page.fetched_at or utcnow(),
            confidence=Confidence.HIGH,
            snippet=page.normalized_text[:500] or None,
            company_id=case.company_id,
            metadata={
                "fact_kind": SourceFactKind.RESEARCH_PAGE_CONTENT.value,
                "research_case_id": str(case.id),
                "research_page_id": str(page.id),
                "page_type": page.page_type.value,
                "title": page.title,
                "content_hash": page.content_hash,
                "http_status": page.http_status,
                "content_type": page.content_type,
                "collection_method": "controlled_website_research",
                "final_url": final_url,
                "research_version": case.research_version,
            },
        )
        saved = await self._evidence.add(scope, evidence)
        return saved.id

    async def _save_page(self, scope: TenantScope, page: ResearchPage) -> ResearchPage:
        return await self._pages.create(scope, page)

    async def _fail_case(
        self,
        scope: TenantScope,
        case: CompanyResearchCase,
        *,
        error_code: ResearchErrorCode,
        message: str,
    ) -> None:
        now = utcnow()
        case.status = CompanyResearchStatus.FAILED
        case.failed_at = now
        case.completed_at = None
        case.error_code = error_code
        case.error_message_safe = message
        case.updated_at = now
        await self._cases.update(scope, case)
        logger.warning(
            "company_research_failed",
            tenant_id=str(scope.tenant_id),
            case_id=str(case.id),
            error_code=error_code.value,
        )

    async def _result(
        self,
        scope: TenantScope,
        case: CompanyResearchCase,
        *,
        pages: list[ResearchPage] | None = None,
    ) -> CompanyResearchResult:
        page_list = pages if pages is not None else await self._pages.list_for_case(scope, case.id)
        evidence = await self._evidence.list_for_company(scope, case.company_id)
        research_evidence = [
            item
            for item in evidence
            if item.metadata.get("fact_kind") == SourceFactKind.RESEARCH_PAGE_CONTENT.value
            and item.metadata.get("research_case_id") == str(case.id)
        ]
        return CompanyResearchResult(
            case=case,
            pages=tuple(page_list),
            evidence_count=len(research_evidence),
        )

    async def _require_company(self, scope: TenantScope, company_id: CompanyId) -> Company:
        company = await self._companies.get(scope, company_id)
        if company is None:
            raise PermanentCompanyResearchError("Company not found.")
        return company


def _assert_tenant(scope: TenantScope) -> None:
    if scope.tenant_id is None:
        raise PermanentCompanyResearchError("Tenant context is required.")
