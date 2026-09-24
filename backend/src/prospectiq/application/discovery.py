"""Company discovery: permitted provider → candidates → existing FETCH_SOURCE."""

from __future__ import annotations

from datetime import datetime
from time import perf_counter
from uuid import UUID, uuid4

from prospectiq.application.ingestion import CompanySourceIngestionService
from prospectiq.application.ports import (
    CompanyDiscoveryProvider,
    DiscoveryCandidateRepository,
    EvidenceRepository,
    JobQueue,
)
from prospectiq.domain.common import (
    Confidence,
    EvidenceId,
    JobId,
    TenantScope,
    WorkspaceId,
    utcnow,
)
from prospectiq.domain.discovery import (
    PROVIDER_FIELD_SUPPORT,
    DiscoveryCandidate,
    DiscoveryFactKind,
    DiscoveryIngestionStatus,
    DiscoveryRequest,
    DiscoveryResult,
    DiscoverySubmission,
    PermanentDiscoveryError,
    ProviderDiscoveryHit,
    candidate_fetch_url,
    candidate_website_url,
    default_field_checks,
    discovery_idempotency_key,
)
from prospectiq.domain.discovery_candidate_validation import validate_discovery_hit
from prospectiq.domain.evidence import Evidence, EvidenceOrigin
from prospectiq.domain.jobs import Job, JobType
from prospectiq.domain.source_registry import SourceClass
from prospectiq.domain.source_url import InvalidSourceUrl
from prospectiq.infrastructure.logging import get_logger

logger = get_logger("prospectiq.discovery")


class CompanyDiscoveryService:
    def __init__(
        self,
        *,
        jobs: JobQueue,
        candidates: DiscoveryCandidateRepository,
        evidence: EvidenceRepository,
        ingestion: CompanySourceIngestionService,
        provider: CompanyDiscoveryProvider,
    ) -> None:
        self._jobs = jobs
        self._candidates = candidates
        self._evidence = evidence
        self._ingestion = ingestion
        self._provider = provider

    async def submit(self, scope: TenantScope, request: DiscoveryRequest) -> DiscoverySubmission:
        _assert_tenant(scope)
        key = discovery_idempotency_key(request)
        job = await self._jobs.enqueue(
            scope,
            JobType.DISCOVER_COMPANIES,
            key,
            {
                **request.to_payload(),
                "workspace_id": str(scope.workspace_id) if scope.workspace_id else None,
            },
        )
        already = bool(job.extra.get("idempotent_replay"))
        logger.info(
            "discovery_submitted",
            tenant_id=str(scope.tenant_id),
            job_id=str(job.id),
            provider=self._provider.provider_key,
            operation="discover_companies",
        )
        return DiscoverySubmission(
            tenant_id=scope.tenant_id,
            job_id=job.id,
            idempotency_key=job.idempotency_key,
            normalized_request=request.to_payload(),
            status="accepted",
            already_enqueued=already,
            provider_key=self._provider.provider_key,
            field_support=PROVIDER_FIELD_SUPPORT,
        )

    async def execute_job(self, job: Job) -> DiscoveryResult:
        workspace_raw = job.payload.get("workspace_id")
        scope = TenantScope(
            tenant_id=job.tenant_id,
            workspace_id=WorkspaceId(UUID(str(workspace_raw))) if workspace_raw else None,
            job_id=str(job.id),
        )
        request = DiscoveryRequest.from_payload(job.payload)
        started = perf_counter()
        logger.info(
            "job_started",
            tenant_id=str(job.tenant_id),
            job_id=str(job.id),
            job_type=job.job_type.value,
            provider=self._provider.provider_key,
            operation="discover_companies",
        )
        hits = await self._provider.discover(scope, request)
        accepted = 0
        rejected = 0
        fetch_jobs_created = 0
        saved_candidates: list[DiscoveryCandidate] = []
        seen_domains: set[str] = set()
        now = utcnow()
        for hit in hits:
            website, domain = candidate_website_url(hit.website)
            fetch_url = candidate_fetch_url(hit.website)
            validation = validate_discovery_hit(hit)
            field_checks = default_field_checks()
            status = DiscoveryIngestionStatus.DISCOVERED
            if website is None:
                status = DiscoveryIngestionStatus.SKIPPED_NO_URL
                rejected += 1
            elif not validation.accepted:
                status = DiscoveryIngestionStatus.SKIPPED_NON_COMPANY
                field_checks = {
                    **field_checks,
                    "candidate_validation": validation.rejection_label or "rejected",
                    "candidate_quality_class": validation.quality_class.value,
                }
                rejected += 1
            elif domain and domain in seen_domains:
                status = DiscoveryIngestionStatus.SKIPPED_DUPLICATE
                rejected += 1
            else:
                accepted += 1
                field_checks = {
                    **field_checks,
                    "candidate_validation": "accepted",
                    "candidate_quality_class": validation.quality_class.value,
                }
                if domain:
                    seen_domains.add(domain)
            existing = await self._candidates.get_by_locator(scope, job.id, hit.source_locator)
            candidate_id = existing.id if existing else uuid4()
            evidence_id = existing.evidence_id if existing else None
            if evidence_id is None:
                evidence_id = await self._persist_discovery_evidence(
                    scope,
                    job_id=job.id,
                    hit=hit,
                    request=request,
                    website=website,
                    domain=domain,
                    discovered_at=now,
                )
            fetch_job_id = existing.fetch_job_id if existing else None
            research_job_id = existing.research_job_id if existing else None
            lead_id = existing.lead_id if existing else None
            company_id = existing.company_id if existing else None
            source_evidence_ids = list(existing.source_evidence_ids) if existing else []
            if fetch_url and status not in {
                DiscoveryIngestionStatus.SKIPPED_NO_URL,
                DiscoveryIngestionStatus.SKIPPED_DUPLICATE,
                DiscoveryIngestionStatus.SKIPPED_NON_COMPANY,
            }:
                try:
                    submission = await self._ingestion.submit(
                        scope,
                        fetch_url,
                        pipeline_context={"discovery_candidate_id": str(candidate_id)},
                    )
                    fetch_job_id = submission.job_id
                    status = DiscoveryIngestionStatus.FETCH_QUEUED
                    if not submission.already_enqueued:
                        fetch_jobs_created += 1
                except InvalidSourceUrl:
                    status = DiscoveryIngestionStatus.SKIPPED_INVALID_URL
                    rejected += 1
                    accepted -= 1
            candidate = DiscoveryCandidate(
                id=candidate_id,
                tenant_id=scope.tenant_id,
                discovery_job_id=job.id,
                name=hit.name,
                domain=domain,
                website_url=hit.website,
                normalized_website=website,
                provider_key=self._provider.provider_key,
                source_locator=hit.source_locator,
                discovered_at=now,
                confidence=hit.confidence,
                provider_rank=hit.provider_rank,
                field_checks=field_checks,
                evidence_id=evidence_id,
                company_id=company_id,
                fetch_job_id=fetch_job_id,
                research_job_id=research_job_id,
                lead_id=lead_id,
                source_evidence_ids=source_evidence_ids,
                ingestion_status=status,
                request_snapshot=request.to_payload(),
                created_at=existing.created_at if existing else now,
                updated_at=now,
            )
            saved = await self._candidates.upsert(scope, candidate)
            saved_candidates.append(saved)
        duration_ms = int((perf_counter() - started) * 1000)
        logger.info(
            "job_completed",
            tenant_id=str(job.tenant_id),
            job_id=str(job.id),
            provider=self._provider.provider_key,
            candidate_count=len(saved_candidates),
            accepted_count=accepted,
            rejected_count=rejected,
            fetch_jobs_created=fetch_jobs_created,
            duration_ms=duration_ms,
            operation="discover_companies",
        )
        return DiscoveryResult(
            tenant_id=scope.tenant_id,
            job_id=job.id,
            provider_key=self._provider.provider_key,
            candidate_count=len(saved_candidates),
            accepted_count=accepted,
            rejected_count=rejected,
            fetch_jobs_created=fetch_jobs_created,
            duration_ms=duration_ms,
            candidates=tuple(saved_candidates),
        )

    async def get_result(self, scope: TenantScope, job_id: JobId) -> DiscoveryResult:
        candidates = await self._candidates.list_for_job(scope, job_id)
        accepted = sum(
            1
            for item in candidates
            if item.ingestion_status
            in {
                DiscoveryIngestionStatus.DISCOVERED,
                DiscoveryIngestionStatus.FETCH_QUEUED,
                DiscoveryIngestionStatus.FETCHED,
                DiscoveryIngestionStatus.NEWS_QUEUED,
                DiscoveryIngestionStatus.RESEARCH_QUEUED,
                DiscoveryIngestionStatus.RESEARCHED,
                DiscoveryIngestionStatus.ENQUEUED,
                DiscoveryIngestionStatus.ALREADY_ENQUEUED,
                DiscoveryIngestionStatus.PENDING,
            }
        )
        rejected = len(candidates) - accepted
        fetch_jobs_created = sum(
            1
            for item in candidates
            if item.ingestion_status is DiscoveryIngestionStatus.FETCH_QUEUED
        )
        provider_key = candidates[0].provider_key if candidates else self._provider.provider_key
        return DiscoveryResult(
            tenant_id=scope.tenant_id,
            job_id=job_id,
            provider_key=provider_key,
            candidate_count=len(candidates),
            accepted_count=accepted,
            rejected_count=rejected,
            fetch_jobs_created=fetch_jobs_created,
            duration_ms=0,
            candidates=tuple(candidates),
        )

    async def _persist_discovery_evidence(
        self,
        scope: TenantScope,
        *,
        job_id: JobId,
        hit: ProviderDiscoveryHit,
        request: DiscoveryRequest,
        website: str | None,
        domain: str | None,
        discovered_at: datetime,
    ) -> EvidenceId:
        evidence = Evidence(
            id=EvidenceId(uuid4()),
            tenant_id=scope.tenant_id,
            fact=f"Discovery candidate: {hit.name}",
            origin=EvidenceOrigin.DISCOVERY_RECORD,
            source_class=SourceClass.PERMITTED_SEARCH_API,
            source_locator=hit.source_locator,
            collected_at=discovered_at,
            confidence=Confidence.MEDIUM,
            snippet=str(hit.raw_reference.get("snippet") or "")[:2000] or None,
            metadata={
                "fact_kind": DiscoveryFactKind.DISCOVERY_CANDIDATE.value,
                "provider_key": self._provider.provider_key,
                "discovery_job_id": str(job_id),
                "candidate_name": hit.name,
                "candidate_domain": domain,
                "candidate_website": website,
                "provider_rank": hit.provider_rank,
                "request": request.to_payload(),
                "raw_reference": hit.raw_reference,
            },
        )
        saved = await self._evidence.add(scope, evidence)
        return saved.id


def _assert_tenant(scope: TenantScope) -> None:
    if scope.tenant_id is None:
        raise PermanentDiscoveryError("Tenant context is required.")
