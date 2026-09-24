"""Application services. These are the only entry points future MCP should call."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from prospectiq.application.ports import AIGateway, AIRequest, LeadRepository
from prospectiq.domain.common import EvidenceId, LeadId, TenantScope
from prospectiq.domain.evidence import EvidenceError, assert_claims_bound_to_known_evidence
from prospectiq.domain.lead import Lead, LeadScoreRecord
from prospectiq.domain.scoring import DEFAULT_SCORING_RULESET, LeadScoreResult, ScoringRuleset
from prospectiq.domain.signal import DetectedSignal


class LeadScoringService:
    """Applies deterministic SOP scoring. The LLM never writes the final score."""

    def __init__(
        self,
        leads: LeadRepository,
        ruleset: ScoringRuleset | None = None,
    ) -> None:
        self._leads = leads
        self._ruleset = ruleset or DEFAULT_SCORING_RULESET

    def score_signals(self, signals: list[DetectedSignal]) -> LeadScoreResult:
        return self._ruleset.score(signals)

    async def apply_to_lead(
        self,
        scope: TenantScope,
        lead: Lead,
        signals: list[DetectedSignal],
        score_id: UUID,
        scored_at: datetime,
    ) -> tuple[Lead, LeadScoreResult]:
        result = self._ruleset.score(signals)
        lead.score = result.total_score
        lead.classification = result.classification
        lead.is_qualified = result.is_qualified
        lead.updated_at = scored_at
        await self._leads.upsert(scope, lead)
        await self._leads.save_score(
            scope,
            LeadScoreRecord(
                id=score_id,
                tenant_id=scope.tenant_id,
                lead_id=lead.id,
                total_score=result.total_score,
                classification=result.classification,
                is_qualified=result.is_qualified,
                distinct_buying_signals=result.distinct_buying_signals,
                breakdown=[
                    {
                        "signal_type": item.signal_type.value,
                        "weight": item.weight,
                        "evidence_id": item.evidence_id,
                    }
                    for item in result.breakdown
                ],
                ruleset_version=result.ruleset_version,
                scored_at=scored_at,
            ),
        )
        return lead, result


class BoundedAIService:
    """AI may summarize or draft; it cannot invent evidence or touch the database."""

    def __init__(self, gateway: AIGateway) -> None:
        self._gateway = gateway

    async def run(
        self,
        *,
        scope: TenantScope,
        operation: str,
        authorized_context: dict[str, object],
        allowed_evidence_ids: list[EvidenceId],
    ) -> object:
        if "tenant_id" in authorized_context and str(authorized_context["tenant_id"]) != str(
            scope.tenant_id
        ):
            raise EvidenceError("AI context tenant does not match the request tenant.")
        request = AIRequest(
            operation=operation,
            tenant_id=scope.tenant_id,
            authorized_context=authorized_context,
            allowed_evidence_ids=[str(item) for item in allowed_evidence_ids],
        )
        response = await self._gateway.complete(request)
        claimed = [EvidenceId(UUID(item)) for item in response.cited_evidence_ids]
        assert_claims_bound_to_known_evidence(claimed, set(allowed_evidence_ids))
        return response


class LeadQueryService:
    def __init__(self, leads: LeadRepository) -> None:
        self._leads = leads

    async def get(self, scope: TenantScope, lead_id: LeadId) -> Lead | None:
        return await self._leads.get(scope, lead_id)

    async def list_workspace(
        self,
        scope: TenantScope,
        *,
        limit: int = 50,
        offset: int = 0,
        is_qualified: bool | None = None,
        classification: str | None = None,
    ) -> list[Lead]:
        return await self._leads.list_for_workspace(
            scope,
            limit=limit,
            offset=offset,
            is_qualified=is_qualified,
            classification=classification,
        )
