"""End-to-end company pipeline: fetch completion → research enqueue → candidate state."""

from __future__ import annotations

from uuid import UUID

from prospectiq.application.news_ingestion import CompanyNewsIngestionService, IngestedCompanyNews
from prospectiq.application.ports import DiscoveryCandidateRepository
from prospectiq.application.research import CompanyResearchResult, CompanyResearchService
from prospectiq.domain.common import JobId, TenantScope, WorkspaceId, utcnow
from prospectiq.domain.discovery import DiscoveryCandidate, DiscoveryIngestionStatus
from prospectiq.domain.ingestion import IngestedCompanySource
from prospectiq.domain.jobs import Job
from prospectiq.infrastructure.config import Settings
from prospectiq.infrastructure.logging import get_logger
from prospectiq.infrastructure.repositories import TenantMismatchError

logger = get_logger("prospectiq.pipeline")


class CompanyPipelineService:
    def __init__(
        self,
        *,
        candidates: DiscoveryCandidateRepository,
        research: CompanyResearchService,
        news: CompanyNewsIngestionService | None = None,
        settings: Settings,
    ) -> None:
        self._candidates = candidates
        self._research = research
        self._news = news
        self._settings = settings

    def scope_for_job(self, job: Job) -> TenantScope:
        workspace_raw = job.payload.get("workspace_id")
        workspace_id = (
            WorkspaceId(UUID(str(workspace_raw)))
            if workspace_raw
            else WorkspaceId(self._settings.internal_workspace_id)
        )
        return TenantScope(
            tenant_id=job.tenant_id,
            workspace_id=workspace_id,
            job_id=str(job.id),
        )

    async def after_fetch_succeeded(
        self,
        scope: TenantScope,
        job: Job,
        result: IngestedCompanySource,
    ) -> None:
        if result.tenant_id != scope.tenant_id:
            raise TenantMismatchError("Ingested company source belongs to another tenant.")
        candidate = await self._candidate_for_fetch(scope, job)
        if candidate is not None:
            _require_same_tenant(candidate.tenant_id, scope.tenant_id)
            if candidate.company_id is not None and candidate.company_id != result.company_id:
                raise TenantMismatchError("Discovery candidate company mismatch.")
            candidate.company_id = result.company_id
            candidate.fetch_job_id = job.id
            candidate.source_evidence_ids = [str(item) for item in result.evidence_ids]
            candidate.ingestion_status = DiscoveryIngestionStatus.FETCHED
            candidate.updated_at = utcnow()
            await self._candidates.upsert(scope, candidate)
        pipeline_context = {
            "fetch_job_id": str(job.id),
        }
        if candidate is not None:
            pipeline_context["discovery_candidate_id"] = str(candidate.id)
        next_scope = TenantScope(
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
            job_id=str(job.id),
        )
        news_enabled = (
            self._news is not None
            and self._settings.news_provider.lower().strip() not in {"", "none"}
        )
        if news_enabled:
            submission = await self._news.submit(  # type: ignore[union-attr]
                next_scope,
                result.company_id,
                pipeline_context=pipeline_context,
            )
            if candidate is not None:
                candidate.ingestion_status = DiscoveryIngestionStatus.NEWS_QUEUED
                candidate.updated_at = utcnow()
                await self._candidates.upsert(scope, candidate)
            logger.info(
                "pipeline_fetch_completed",
                tenant_id=str(scope.tenant_id),
                fetch_job_id=str(job.id),
                news_job_id=submission["job_id"],
                company_id=str(result.company_id),
                candidate_id=str(candidate.id) if candidate else None,
                operation="pipeline_fetch",
            )
            return
        research = await self._research.submit(
            next_scope,
            result.company_id,
            pipeline_context=pipeline_context,
        )
        if candidate is not None:
            candidate.ingestion_status = DiscoveryIngestionStatus.RESEARCH_QUEUED
            candidate.research_job_id = JobId(UUID(str(research.job_id)))
            candidate.updated_at = utcnow()
            await self._candidates.upsert(scope, candidate)
        logger.info(
            "pipeline_fetch_completed",
            tenant_id=str(scope.tenant_id),
            fetch_job_id=str(job.id),
            research_job_id=research.job_id,
            company_id=str(result.company_id),
            candidate_id=str(candidate.id) if candidate else None,
            operation="pipeline_fetch",
        )

    async def after_news_succeeded(
        self,
        scope: TenantScope,
        job: Job,
        result: IngestedCompanyNews,
    ) -> None:
        candidate = await self._candidate_for_news(scope, job)
        pipeline_context = {"fetch_job_id": job.payload.get("fetch_job_id", "")}
        if candidate is not None:
            pipeline_context["discovery_candidate_id"] = str(candidate.id)
            existing = list(candidate.source_evidence_ids)
            existing.extend(str(item) for item in result.evidence_ids)
            candidate.source_evidence_ids = existing
            candidate.updated_at = utcnow()
            await self._candidates.upsert(scope, candidate)
        research = await self._research.submit(
            scope,
            result.company_id,
            pipeline_context={k: v for k, v in pipeline_context.items() if v},
        )
        if candidate is not None:
            candidate.ingestion_status = DiscoveryIngestionStatus.RESEARCH_QUEUED
            candidate.research_job_id = JobId(UUID(str(research.job_id)))
            candidate.updated_at = utcnow()
            await self._candidates.upsert(scope, candidate)
        logger.info(
            "pipeline_news_completed",
            tenant_id=str(scope.tenant_id),
            news_job_id=str(job.id),
            research_job_id=research.job_id,
            company_id=str(result.company_id),
            candidate_id=str(candidate.id) if candidate else None,
            operation="pipeline_news",
        )

    async def after_news_failed(self, scope: TenantScope, job: Job, *, permanent: bool) -> None:
        if not permanent:
            return
        candidate = await self._candidate_for_news(scope, job)
        if candidate is None:
            return
        candidate.ingestion_status = DiscoveryIngestionStatus.FETCH_FAILED
        candidate.updated_at = utcnow()
        await self._candidates.upsert(scope, candidate)

    async def after_fetch_failed(self, scope: TenantScope, job: Job, *, permanent: bool) -> None:
        if not permanent:
            return
        candidate = await self._candidate_for_fetch(scope, job)
        if candidate is None:
            return
        candidate.ingestion_status = DiscoveryIngestionStatus.FETCH_FAILED
        candidate.updated_at = utcnow()
        await self._candidates.upsert(scope, candidate)
        logger.warning(
            "pipeline_fetch_failed",
            tenant_id=str(scope.tenant_id),
            fetch_job_id=str(job.id),
            candidate_id=str(candidate.id),
            operation="pipeline_fetch",
        )

    async def after_research_succeeded(
        self,
        scope: TenantScope,
        job: Job,
        result: CompanyResearchResult,
    ) -> None:
        candidate = await self._candidate_for_research(scope, job)
        if candidate is None:
            return
        _require_same_tenant(candidate.tenant_id, scope.tenant_id)
        if candidate.company_id is not None and candidate.company_id != result.company_id:
            raise TenantMismatchError("Discovery candidate company mismatch.")
        candidate.company_id = result.company_id
        candidate.research_job_id = job.id
        candidate.lead_id = result.lead_id
        candidate.ingestion_status = DiscoveryIngestionStatus.RESEARCHED
        candidate.updated_at = utcnow()
        await self._candidates.upsert(scope, candidate)
        logger.info(
            "pipeline_research_completed",
            tenant_id=str(scope.tenant_id),
            research_job_id=str(job.id),
            company_id=str(result.company_id),
            lead_id=str(result.lead_id) if result.lead_id else None,
            candidate_id=str(candidate.id),
            score=result.score.total_score,
            qualified=result.score.is_qualified,
            operation="pipeline_research",
        )

    async def after_research_failed(self, scope: TenantScope, job: Job, *, permanent: bool) -> None:
        if not permanent:
            return
        candidate = await self._candidate_for_research(scope, job)
        if candidate is None:
            return
        candidate.ingestion_status = DiscoveryIngestionStatus.RESEARCH_FAILED
        candidate.updated_at = utcnow()
        await self._candidates.upsert(scope, candidate)
        logger.warning(
            "pipeline_research_failed",
            tenant_id=str(scope.tenant_id),
            research_job_id=str(job.id),
            candidate_id=str(candidate.id),
            operation="pipeline_research",
        )

    async def _candidate_for_fetch(
        self, scope: TenantScope, job: Job
    ) -> DiscoveryCandidate | None:
        return await self._resolve_candidate(
            scope,
            discovery_candidate_id=job.payload.get("discovery_candidate_id"),
            fetch_job_id=job.id,
        )

    async def _candidate_for_research(
        self, scope: TenantScope, job: Job
    ) -> DiscoveryCandidate | None:
        fetch_raw = job.payload.get("fetch_job_id")
        fetch_job_id = JobId(UUID(str(fetch_raw))) if fetch_raw else None
        return await self._resolve_candidate(
            scope,
            discovery_candidate_id=job.payload.get("discovery_candidate_id"),
            fetch_job_id=fetch_job_id,
        )

    async def _candidate_for_news(self, scope: TenantScope, job: Job) -> DiscoveryCandidate | None:
        fetch_raw = job.payload.get("fetch_job_id")
        fetch_job_id = JobId(UUID(str(fetch_raw))) if fetch_raw else None
        return await self._resolve_candidate(
            scope,
            discovery_candidate_id=job.payload.get("discovery_candidate_id"),
            fetch_job_id=fetch_job_id,
        )

    async def _resolve_candidate(
        self,
        scope: TenantScope,
        *,
        discovery_candidate_id: object,
        fetch_job_id: JobId | None,
    ) -> DiscoveryCandidate | None:
        if discovery_candidate_id:
            candidate_id = UUID(str(discovery_candidate_id))
            found = await self._candidates.get_by_id(scope, candidate_id)
            if found is not None:
                return found
            foreign = await self._candidates.find_by_id(candidate_id)
            if foreign is not None:
                raise TenantMismatchError("Discovery candidate belongs to another tenant.")
        if fetch_job_id is not None:
            return await self._candidates.get_by_fetch_job_id(scope, fetch_job_id)
        return None


def _require_same_tenant(candidate_tenant: object, scope_tenant: object) -> None:
    if str(candidate_tenant) != str(scope_tenant):
        raise TenantMismatchError("Discovery candidate belongs to another tenant.")
