"""Read-only lead intelligence dossier assembly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from prospectiq.application.ports import (
    CompanyRepository,
    DiscoveryCandidateRepository,
    EvidenceRepository,
    LeadRepository,
    SignalRepository,
)
from prospectiq.application.research import CompanyResearchService
from prospectiq.domain.common import CompanyId, LeadId, TenantScope
from prospectiq.domain.evidence import EvidenceOrigin
from prospectiq.domain.ingestion import PermanentSourceError
from prospectiq.domain.signal import SIGNAL_WEIGHTS


@dataclass(frozen=True, slots=True)
class LeadDossier:
    company: dict[str, Any]
    evidence: list[dict[str, Any]]
    signals: list[dict[str, Any]]
    score: dict[str, Any]
    pipeline: dict[str, Any] | None


class LeadDossierService:
    def __init__(
        self,
        *,
        companies: CompanyRepository,
        evidence: EvidenceRepository,
        signals: SignalRepository,
        leads: LeadRepository,
        candidates: DiscoveryCandidateRepository,
        research: CompanyResearchService,
    ) -> None:
        self._companies = companies
        self._evidence = evidence
        self._signals = signals
        self._leads = leads
        self._candidates = candidates
        self._research = research

    async def get_by_lead_id(self, scope: TenantScope, lead_id: LeadId) -> LeadDossier:
        lead = await self._leads.get(scope, lead_id)
        if lead is None:
            raise PermanentSourceError("Lead was not found in this tenant.")
        return await self.get_by_company_id(scope, lead.company_id, lead_id=lead_id)

    async def get_by_company_id(
        self,
        scope: TenantScope,
        company_id: CompanyId,
        *,
        lead_id: LeadId | None = None,
    ) -> LeadDossier:
        company = await self._companies.get(scope, company_id)
        if company is None:
            raise PermanentSourceError("Company was not found in this tenant.")
        records = await self._evidence.list_for_company(scope, company.id)
        stored_signals = await self._signals.list_for_company(scope, company.id)
        research = await self._research.get_result(scope, company.id)
        candidate = await self._find_candidate(scope, company.id)
        resolved_lead_id = lead_id or research.lead_id
        return LeadDossier(
            company={
                "id": str(company.id),
                "name": company.name,
                "normalized_name": company.normalized_name,
                "website": company.website,
                "industry": company.industry.value if company.industry else None,
                "geography": company.geography.value if company.geography else None,
            },
            evidence=[_evidence_payload(item) for item in records],
            signals=[
                {
                    "signal_type": item.signal_type.value,
                    "weight": SIGNAL_WEIGHTS[item.signal_type],
                    "reason": item.reason,
                    "evidence_id": str(item.evidence_id),
                    "detected_at": item.detected_at.isoformat(),
                }
                for item in stored_signals
            ],
            score={
                "total_score": research.score.total_score,
                "classification": research.score.classification.value,
                "qualified": research.score.is_qualified,
                "distinct_signal_count": research.score.distinct_buying_signals,
                "ruleset_version": research.score.ruleset_version,
            },
            pipeline=_pipeline_payload(candidate, resolved_lead_id),
        )

    async def _find_candidate(
        self, scope: TenantScope, company_id: CompanyId
    ) -> object | None:
        rows = await self._candidates.list_for_tenant(scope, limit=200)
        for item in rows:
            if item.company_id == company_id:
                return item
        return None


def _evidence_payload(item: object) -> dict[str, Any]:
    evidence = item  # Evidence dataclass
    origin = evidence.origin.value  # type: ignore[attr-defined]
    return {
        "id": str(evidence.id),  # type: ignore[attr-defined]
        "origin": origin,
        "source_class": evidence.source_class.value if evidence.source_class else None,  # type: ignore[attr-defined]
        "source_locator": evidence.source_locator,  # type: ignore[attr-defined]
        "collected_at": evidence.collected_at.isoformat(),  # type: ignore[attr-defined]
        "confidence": evidence.confidence.value,  # type: ignore[attr-defined]
        "fact_kind": evidence.metadata.get("fact_kind"),  # type: ignore[attr-defined]
        "fact": (evidence.fact or "")[:500],  # type: ignore[attr-defined]
        "snippet": (evidence.snippet or "")[:500] if evidence.snippet else None,  # type: ignore[attr-defined]
        "is_ai_interpretation": origin == EvidenceOrigin.AI_INTERPRETATION.value,
    }


def _pipeline_payload(candidate: object | None, lead_id: LeadId | None) -> dict[str, Any] | None:
    if candidate is None:
        return None
    return {
        "candidate_id": str(candidate.id),  # type: ignore[attr-defined]
        "ingestion_status": candidate.ingestion_status.value,  # type: ignore[attr-defined]
        "discovery_job_id": str(candidate.discovery_job_id),  # type: ignore[attr-defined]
        "fetch_job_id": str(candidate.fetch_job_id) if candidate.fetch_job_id else None,  # type: ignore[attr-defined]
        "research_job_id": str(candidate.research_job_id) if candidate.research_job_id else None,  # type: ignore[attr-defined]
        "lead_id": str(lead_id) if lead_id else None,
        "source_evidence_ids": list(candidate.source_evidence_ids),  # type: ignore[attr-defined]
        "discovered_at": candidate.discovered_at.isoformat(),  # type: ignore[attr-defined]
        "updated_at": candidate.updated_at.isoformat(),  # type: ignore[attr-defined]
    }
