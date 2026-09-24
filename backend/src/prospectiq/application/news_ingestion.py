"""Permitted company news ingestion → evidence records."""

from __future__ import annotations

from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from prospectiq.application.ports import (
    CompanyNewsProvider,
    CompanyRepository,
    EvidenceRepository,
    JobQueue,
    NewsRecord,
)
from prospectiq.domain.common import CompanyId, Confidence, EvidenceId, TenantScope
from prospectiq.domain.company import Company
from prospectiq.domain.detection import EXPANSION_FACT_KIND, FUNDING_FACT_KIND
from prospectiq.domain.evidence import Evidence, EvidenceOrigin
from prospectiq.domain.jobs import Job, JobType
from prospectiq.domain.news import PermanentNewsError
from prospectiq.infrastructure.logging import get_logger

logger = get_logger("prospectiq.news")


def fetch_company_news_idempotency_key(company_id: CompanyId) -> str:
    return f"fetch_company_news:{company_id}"


class IngestedCompanyNews:
    def __init__(
        self,
        *,
        company_id: CompanyId,
        evidence_ids: list[EvidenceId],
        funding_count: int,
        expansion_count: int,
    ) -> None:
        self.company_id = company_id
        self.evidence_ids = evidence_ids
        self.funding_count = funding_count
        self.expansion_count = expansion_count


class CompanyNewsIngestionService:
    def __init__(
        self,
        *,
        companies: CompanyRepository,
        evidence: EvidenceRepository,
        provider: CompanyNewsProvider | None,
        jobs: JobQueue | None = None,
    ) -> None:
        self._companies = companies
        self._evidence = evidence
        self._provider = provider
        self._jobs = jobs

    async def submit(
        self,
        scope: TenantScope,
        company_id: CompanyId,
        *,
        pipeline_context: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if self._jobs is None:
            raise PermanentNewsError("Job queue is required to submit news fetch.")
        if self._provider is None:
            raise PermanentNewsError("News provider is not configured.")
        company = await self._require_company(scope, company_id)
        key = fetch_company_news_idempotency_key(company.id)
        payload: dict[str, Any] = {"company_id": str(company.id)}
        if scope.workspace_id is not None:
            payload["workspace_id"] = str(scope.workspace_id)
        if pipeline_context:
            payload.update(pipeline_context)
        job = await self._jobs.enqueue(scope, JobType.FETCH_COMPANY_NEWS, key, payload)
        return {
            "job_id": str(job.id),
            "already_enqueued": bool(job.extra.get("idempotent_replay")),
        }

    async def execute_job(self, job: Job) -> IngestedCompanyNews:
        if self._provider is None:
            raise PermanentNewsError("News provider is not configured.")
        from prospectiq.domain.common import WorkspaceId

        workspace_raw = job.payload.get("workspace_id")
        scope = TenantScope(
            tenant_id=job.tenant_id,
            workspace_id=WorkspaceId(UUID(str(workspace_raw))) if workspace_raw else None,
            job_id=str(job.id),
        )
        company_id = CompanyId(UUID(str(job.payload["company_id"])))
        company = await self._require_company(scope, company_id)
        logger.info(
            "job_started",
            tenant_id=str(scope.tenant_id),
            job_id=str(job.id),
            job_type=job.job_type.value,
            company_id=str(company.id),
            operation="fetch_company_news",
        )
        records = await self._provider.fetch_company_news(scope, company)
        evidence_ids: list[EvidenceId] = []
        funding_count = 0
        expansion_count = 0
        for record in records:
            item = await self._persist_record(scope, company, record)
            evidence_ids.append(item.id)
            kind = str(record.metadata.get("fact_kind") or "")
            if kind == FUNDING_FACT_KIND:
                funding_count += 1
            elif kind == EXPANSION_FACT_KIND:
                expansion_count += 1
        logger.info(
            "job_completed",
            tenant_id=str(scope.tenant_id),
            job_id=str(job.id),
            company_id=str(company.id),
            evidence_count=len(evidence_ids),
            operation="fetch_company_news",
        )
        return IngestedCompanyNews(
            company_id=company.id,
            evidence_ids=evidence_ids,
            funding_count=funding_count,
            expansion_count=expansion_count,
        )

    async def _persist_record(
        self,
        scope: TenantScope,
        company: Company,
        record: NewsRecord,
    ) -> Evidence:
        event_key = record.metadata.get("event_key") or _event_key(
            company.id, record.metadata.get("headline") or record.fact
        )
        locator = record.locator
        existing = await self._evidence.list_for_locator(scope, locator)
        kind = record.metadata.get("fact_kind")
        match = next(
            (
                item
                for item in existing
                if item.metadata.get("fact_kind") == kind
                and item.metadata.get("event_key") == event_key
            ),
            None,
        )
        evidence = Evidence(
            id=match.id if match else EvidenceId(uuid4()),
            tenant_id=scope.tenant_id,
            fact=record.fact,
            origin=EvidenceOrigin.SOURCE_DERIVED,
            source_class=record.source_class,
            source_locator=locator,
            collected_at=record.collected_at,
            confidence=Confidence(record.confidence)
            if record.confidence in {item.value for item in Confidence}
            else Confidence.MEDIUM,
            snippet=record.snippet,
            company_id=company.id,
            metadata={**record.metadata, "event_key": event_key},
        )
        return await self._evidence.upsert(scope, evidence)

    async def _require_company(self, scope: TenantScope, company_id: CompanyId) -> Company:
        company = await self._companies.get(scope, company_id)
        if company is None:
            raise PermanentNewsError("Company was not found in this tenant.")
        return company


def _event_key(company_id: CompanyId, headline: str) -> str:
    digest = sha256(f"{company_id}:{headline.strip().lower()}".encode()).hexdigest()[:16]
    return digest
