"""Company research: detect evidence-backed signals, then score the lead."""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from prospectiq.application.ports import (
    CompanyRepository,
    EvidenceRepository,
    JobQueue,
    LeadRepository,
    SignalRepository,
)
from prospectiq.application.services import LeadScoringService
from prospectiq.domain.common import (
    CompanyId,
    LeadId,
    SignalId,
    TenantScope,
    WorkspaceId,
    utcnow,
)
from prospectiq.domain.company import Company
from prospectiq.domain.detection import (
    DETECTION_RULESET_VERSION,
    SIGNAL_RULE_CATALOG,
    SignalDetectionService,
    deferred_signal_types,
)
from prospectiq.domain.evidence import Evidence
from prospectiq.domain.ingestion import PermanentSourceError
from prospectiq.domain.jobs import Job, JobType
from prospectiq.domain.lead import Lead
from prospectiq.domain.pipeline import LeadStatus
from prospectiq.domain.scoring import LeadClassification, LeadScoreResult
from prospectiq.domain.signal import SIGNAL_WEIGHTS, DetectedSignal, Signal
from prospectiq.infrastructure.logging import get_logger

logger = get_logger("prospectiq.research")


def research_lead_idempotency_key(
    company_id: CompanyId, evidence: Sequence[Evidence]
) -> str:
    if not evidence:
        return f"research_lead:{company_id}:empty"
    parts = [
        f"{item.id}:{item.collected_at.isoformat()}:{item.fact}"
        for item in sorted(evidence, key=lambda row: str(row.id))
    ]
    digest = sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"research_lead:{company_id}:{digest}"


class CompanyResearchResult:
    def __init__(
        self,
        *,
        company_id: CompanyId,
        lead_id: LeadId | None,
        signals: list[DetectedSignal],
        score: LeadScoreResult,
        already_enqueued: bool = False,
        job_id: str | None = None,
    ) -> None:
        self.company_id = company_id
        self.lead_id = lead_id
        self.signals = signals
        self.score = score
        self.already_enqueued = already_enqueued
        self.job_id = job_id
        self.detection_ruleset_version = DETECTION_RULESET_VERSION
        self.deferred_signals = [item.value for item in deferred_signal_types()]


class CompanyResearchService:
    def __init__(
        self,
        *,
        companies: CompanyRepository,
        evidence: EvidenceRepository,
        signals: SignalRepository,
        leads: LeadRepository,
        scoring: LeadScoringService,
        jobs: JobQueue | None = None,
        detector: SignalDetectionService | None = None,
    ) -> None:
        self._companies = companies
        self._evidence = evidence
        self._signals = signals
        self._leads = leads
        self._scoring = scoring
        self._jobs = jobs
        self._detector = detector or SignalDetectionService()

    async def submit(
        self,
        scope: TenantScope,
        company_id: CompanyId,
        *,
        pipeline_context: dict[str, str] | None = None,
    ) -> CompanyResearchResult:
        if self._jobs is None:
            raise PermanentSourceError("Job queue is required to submit research.")
        company = await self._require_company(scope, company_id)
        records = await self._evidence.list_for_company(scope, company.id)
        key = research_lead_idempotency_key(company.id, records)
        payload: dict[str, Any] = {
            "company_id": str(company.id),
        }
        if scope.workspace_id is not None:
            payload["workspace_id"] = str(scope.workspace_id)
        if pipeline_context:
            payload.update(pipeline_context)
        job = await self._jobs.enqueue(
            scope,
            JobType.RESEARCH_LEAD,
            key,
            payload,
        )
        logger.info(
            "company_research_submitted",
            tenant_id=str(scope.tenant_id),
            job_id=str(job.id),
            company_id=str(company.id),
            operation="research_lead",
        )
        return CompanyResearchResult(
            company_id=company.id,
            lead_id=None,
            signals=[],
            score=LeadScoreResult(
                total_score=0,
                classification=LeadClassification.COLD,
                is_qualified=False,
                distinct_buying_signals=0,
                breakdown=(),
            ),
            already_enqueued=bool(job.extra.get("idempotent_replay")),
            job_id=str(job.id),
        )

    async def execute_job(self, job: Job) -> CompanyResearchResult:
        workspace_raw = job.payload.get("workspace_id")
        scope = TenantScope(
            tenant_id=job.tenant_id,
            workspace_id=WorkspaceId(UUID(str(workspace_raw))) if workspace_raw else None,
            job_id=str(job.id),
        )
        company_id = CompanyId(UUID(str(job.payload["company_id"])))
        logger.info(
            "job_started",
            tenant_id=str(job.tenant_id),
            job_id=str(job.id),
            job_type=job.job_type.value,
            operation="research_lead",
        )
        return await self.research(scope, company_id)

    async def research(self, scope: TenantScope, company_id: CompanyId) -> CompanyResearchResult:
        company = await self._require_company(scope, company_id)
        records = await self._evidence.list_for_company(scope, company.id)
        detected = self._detector.detect(records)
        detected_types = {item.signal_type for item in detected}
        stored_signals = await self._signals.list_for_company(scope, company.id)
        for stored in stored_signals:
            if stored.signal_type not in detected_types:
                await self._signals.delete(scope, stored.id)
        lead = await self._get_or_create_lead(scope, company)
        persisted: list[DetectedSignal] = []
        now = utcnow()
        for item in detected:
            existing = await self._signals.get_by_company_and_type(
                scope, company.id, item.signal_type
            )
            signal = Signal(
                id=existing.id if existing else SignalId(uuid4()),
                tenant_id=scope.tenant_id,
                signal_type=item.signal_type,
                weight=SIGNAL_WEIGHTS[item.signal_type],
                detected_at=now,
                evidence_id=item.evidence_id,
                company_id=company.id,
                lead_id=lead.id,
                reason=item.reason,
            )
            saved = await self._signals.upsert(scope, signal)
            persisted.append(
                DetectedSignal(
                    signal_type=saved.signal_type,
                    evidence_id=saved.evidence_id,
                    reason=saved.reason or item.reason,
                )
            )
        lead, score = await self._scoring.apply_to_lead(
            scope, lead, persisted, uuid4(), now
        )
        logger.info(
            "job_completed",
            tenant_id=str(scope.tenant_id),
            company_id=str(company.id),
            lead_id=str(lead.id),
            score=score.total_score,
            classification=score.classification.value,
            qualified=score.is_qualified,
            signal_count=len(persisted),
            operation="research_lead",
        )
        return CompanyResearchResult(
            company_id=company.id,
            lead_id=lead.id,
            signals=persisted,
            score=score,
        )

    async def get_result(self, scope: TenantScope, company_id: CompanyId) -> CompanyResearchResult:
        company = await self._require_company(scope, company_id)
        records = await self._evidence.list_for_company(scope, company.id)
        detected = self._detector.detect(records)
        lead = await self._leads.get_by_company(scope, company.id)
        score = self._scoring.score_signals(detected)
        return CompanyResearchResult(
            company_id=company.id,
            lead_id=lead.id if lead else None,
            signals=detected,
            score=score,
        )

    async def _require_company(self, scope: TenantScope, company_id: CompanyId) -> Company:
        company = await self._companies.get(scope, company_id)
        if company is None:
            raise PermanentSourceError("Company was not found in this tenant.")
        return company

    async def _get_or_create_lead(self, scope: TenantScope, company: Company) -> Lead:
        existing = await self._leads.get_by_company(scope, company.id)
        if existing is not None:
            return existing
        workspace_id = scope.workspace_id
        if workspace_id is None:
            raise PermanentSourceError("Workspace context is required to create a lead.")
        now = utcnow()
        lead = Lead(
            id=LeadId(uuid4()),
            tenant_id=scope.tenant_id,
            workspace_id=workspace_id,
            company_id=company.id,
            person_id=None,
            status=LeadStatus.RESEARCH,
            score=0,
            classification=LeadClassification.COLD,
            is_qualified=False,
            search_profile_id=None,
            created_at=now,
            updated_at=now,
        )
        return await self._leads.upsert(scope, lead)


def catalog_payload() -> list[dict[str, object]]:
    return [
        {
            "signal_type": item.signal_type.value,
            "description": item.description,
            "weight": item.weight,
            "implemented": item.implemented,
            "requires_evidence": item.requires_evidence,
        }
        for item in SIGNAL_RULE_CATALOG
    ]
