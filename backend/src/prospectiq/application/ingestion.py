"""Ingest a single permitted company website or careers URL."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from prospectiq.application.ports import (
    CompanyRepository,
    CompanySourceRepository,
    EvidenceRepository,
    FetchRequest,
    JobQueue,
    NormalizedRecord,
    SourceAdapter,
)
from prospectiq.domain.common import (
    CompanyId,
    Confidence,
    EvidenceId,
    TenantScope,
    utcnow,
)
from prospectiq.domain.company import Company, CompanySource
from prospectiq.domain.evidence import Evidence, EvidenceOrigin
from prospectiq.domain.ingestion import (
    CompanySourceSubmission,
    IngestedCompanySource,
    PermanentSourceError,
    SourceFactKind,
    page_company_name,
)
from prospectiq.domain.jobs import Job, JobType
from prospectiq.domain.source_registry import SourceClass
from prospectiq.domain.source_url import (
    NormalizedSourceUrl,
    fetch_source_idempotency_key,
    parse_source_url,
)
from prospectiq.infrastructure.logging import get_logger

logger = get_logger("prospectiq.ingestion")


class CompanySourceIngestionService:
    def __init__(
        self,
        *,
        jobs: JobQueue,
        companies: CompanyRepository,
        company_sources: CompanySourceRepository,
        evidence: EvidenceRepository,
        adapters: dict[SourceClass, SourceAdapter],
    ) -> None:
        self._jobs = jobs
        self._companies = companies
        self._company_sources = company_sources
        self._evidence = evidence
        self._adapters = adapters

    async def submit(
        self,
        scope: TenantScope,
        url: str,
        *,
        pipeline_context: dict[str, str] | None = None,
    ) -> CompanySourceSubmission:
        parsed = parse_source_url(url)
        _assert_tenant(scope)
        key = fetch_source_idempotency_key(parsed.normalized)
        payload: dict[str, Any] = {
            "url": parsed.original,
            "normalized_url": parsed.normalized,
            "source_class": parsed.source_class.value,
        }
        if scope.workspace_id is not None:
            payload["workspace_id"] = str(scope.workspace_id)
        if pipeline_context:
            payload.update(pipeline_context)
        job = await self._jobs.enqueue(
            scope,
            JobType.FETCH_SOURCE,
            key,
            payload,
        )
        already = bool(job.extra.get("idempotent_replay"))
        logger.info(
            "company_source_submitted",
            tenant_id=str(scope.tenant_id),
            job_id=str(job.id),
            source_class=parsed.source_class.value,
            domain=parsed.identity_host,
            operation="submit_company_source",
        )
        return CompanySourceSubmission(
            tenant_id=scope.tenant_id,
            job_id=job.id,
            idempotency_key=job.idempotency_key,
            normalized_url=parsed.normalized,
            source_class=parsed.source_class,
            status="accepted",
            already_enqueued=already,
        )

    async def execute_job(self, job: Job) -> IngestedCompanySource:
        scope = TenantScope(tenant_id=job.tenant_id, job_id=str(job.id))
        url = str(job.payload.get("normalized_url") or job.payload.get("url") or "")
        logger.info(
            "job_started",
            tenant_id=str(job.tenant_id),
            job_id=str(job.id),
            job_type=job.job_type.value,
            operation="fetch_source",
        )
        try:
            result = await self.ingest(scope, url)
        except Exception:
            logger.info(
                "job_failed",
                tenant_id=str(job.tenant_id),
                job_id=str(job.id),
                job_type=job.job_type.value,
                operation="fetch_source",
            )
            raise
        logger.info(
            "job_completed",
            tenant_id=str(job.tenant_id),
            job_id=str(job.id),
            job_type=job.job_type.value,
            company_id=str(result.company_id),
            operation="fetch_source",
        )
        return result

    async def ingest(self, scope: TenantScope, url: str) -> IngestedCompanySource:
        parsed = parse_source_url(url)
        _assert_tenant(scope)
        adapter = self._adapters.get(parsed.source_class)
        if adapter is None:
            raise PermanentSourceError(
                f"No permitted adapter is registered for {parsed.source_class.value}."
            )
        records = await adapter.fetch(FetchRequest(scope, parsed.normalized))
        if not records:
            raise PermanentSourceError("Source adapter returned no records.")
        logger.info(
            "source_fetch_succeeded",
            tenant_id=str(scope.tenant_id),
            job_id=scope.job_id,
            domain=parsed.identity_host,
            source_class=parsed.source_class.value,
            operation="fetch_source",
        )
        company = await self._upsert_company(scope, parsed, records[0])
        source = await self._upsert_source(scope, company, parsed, records[0])
        evidence_ids: list[EvidenceId] = []
        observed: list[str] = []
        title: str | None = None
        for record in records:
            item = await self._upsert_evidence(scope, company, parsed, record)
            evidence_ids.append(item.id)
            kind = str(record.metadata.get("fact_kind") or "")
            if kind == SourceFactKind.HIRING_LANGUAGE_OBSERVED.value:
                phrases = record.metadata.get("observed_hiring_phrases") or []
                if isinstance(phrases, list):
                    observed = [str(p) for p in phrases]
            if kind == SourceFactKind.PAGE_CONTENT.value:
                raw_title = record.metadata.get("title")
                title = str(raw_title) if raw_title else None
        return IngestedCompanySource(
            tenant_id=scope.tenant_id,
            company_id=company.id,
            company_source_id=source.id,
            evidence_ids=evidence_ids,
            normalized_url=parsed.normalized,
            source_class=parsed.source_class,
            identity_requires_review=parsed.identity_requires_review,
            page_title=title,
            observed_hiring_phrases=observed,
            collected_at=records[0].collected_at,
        )

    async def _upsert_company(
        self,
        scope: TenantScope,
        parsed: NormalizedSourceUrl,
        record: NormalizedRecord,
    ) -> Company:
        now = utcnow()
        existing = await self._companies.get_by_normalized_name(scope, parsed.identity_host)
        title = record.metadata.get("title")
        name = page_company_name(str(title) if title else None, parsed)
        if existing is None:
            company = Company(
                id=CompanyId(uuid4()),
                tenant_id=scope.tenant_id,
                name=name,
                normalized_name=parsed.identity_host,
                website=parsed.origin,
                industry=None,
                geography=None,
                employee_count=None,
                headcount_growth_pct=None,
                company_type=None,
                is_hiring=None,
                created_at=now,
                updated_at=now,
            )
            return await self._companies.upsert(scope, company)
        if existing.name == existing.normalized_name and name != existing.normalized_name:
            existing.name = name
        if not existing.website:
            existing.website = parsed.origin
        existing.updated_at = now
        return await self._companies.upsert(scope, existing)

    async def _upsert_source(
        self,
        scope: TenantScope,
        company: Company,
        parsed: NormalizedSourceUrl,
        record: NormalizedRecord,
    ) -> CompanySource:
        existing = await self._company_sources.get_by_locator(scope, parsed.normalized)
        source = CompanySource(
            id=existing.id if existing else uuid4(),
            tenant_id=scope.tenant_id,
            company_id=company.id,
            source_class=parsed.source_class,
            locator=parsed.normalized,
            raw_reference=str(record.metadata.get("final_url") or parsed.normalized),
            collected_at=record.collected_at,
        )
        return await self._company_sources.upsert(scope, source)

    async def _upsert_evidence(
        self,
        scope: TenantScope,
        company: Company,
        parsed: NormalizedSourceUrl,
        record: NormalizedRecord,
    ) -> Evidence:
        existing_rows = await self._evidence.list_for_locator(scope, parsed.normalized)
        kind = record.metadata.get("fact_kind")
        match = next(
            (item for item in existing_rows if item.metadata.get("fact_kind") == kind),
            None,
        )
        evidence = Evidence(
            id=match.id if match else EvidenceId(uuid4()),
            tenant_id=scope.tenant_id,
            fact=record.fact,
            origin=EvidenceOrigin.SOURCE_DERIVED,
            source_class=parsed.source_class,
            source_locator=parsed.normalized,
            collected_at=record.collected_at,
            confidence=Confidence(record.confidence)
            if record.confidence in {item.value for item in Confidence}
            else Confidence.MEDIUM,
            snippet=record.snippet,
            company_id=company.id,
            metadata=dict(record.metadata),
        )
        return await self._evidence.upsert(scope, evidence)


def _assert_tenant(scope: TenantScope) -> None:
    if scope.tenant_id is None:
        raise PermanentSourceError("Tenant context is required.")

