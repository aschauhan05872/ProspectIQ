"""Thin route stubs. They call application services, not SQL or providers."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from prospectiq.api.deps import db_session, tenant_scope
from prospectiq.application.research import CompanyResearchResult
from prospectiq.application.services import LeadQueryService
from prospectiq.domain.common import CompanyId, TenantScope
from prospectiq.domain.ingestion import PermanentSourceError
from prospectiq.domain.signal import SIGNAL_WEIGHTS
from prospectiq.infrastructure.repositories import SqlAlchemyLeadRepository
from prospectiq.infrastructure.research_runtime import build_research_service

searches_router = APIRouter(prefix="/searches", tags=["searches"])
leads_router = APIRouter(prefix="/leads", tags=["leads"])
research_router = APIRouter(prefix="/research", tags=["research"])
drafts_router = APIRouter(prefix="/drafts", tags=["drafts"])
activities_router = APIRouter(prefix="/activities", tags=["activities"])
followups_router = APIRouter(prefix="/followups", tags=["followups"])
notifications_router = APIRouter(prefix="/notifications", tags=["notifications"])


@searches_router.get("")
async def list_searches() -> list[dict[str, str]]:
    return []


@leads_router.get("")
async def list_leads(
    scope: TenantScope = Depends(tenant_scope),
    session: AsyncSession = Depends(db_session),
) -> list[dict[str, object]]:
    service = LeadQueryService(SqlAlchemyLeadRepository(session))
    leads = await service.list_workspace(scope)
    return [
        {
            "id": str(lead.id),
            "status": lead.status.value,
            "score": lead.score,
            "classification": lead.classification.value,
            "is_qualified": lead.is_qualified,
        }
        for lead in leads
    ]


class CompanyResearchRequest(BaseModel):
    company_id: UUID


def _research_body(result: CompanyResearchResult, *, status: str) -> dict[str, object]:
    return {
        "status": status,
        "company_id": str(result.company_id),
        "lead_id": str(result.lead_id) if result.lead_id else None,
        "job_id": result.job_id,
        "already_enqueued": result.already_enqueued,
        "detection_ruleset_version": result.detection_ruleset_version,
        "deferred_signals": result.deferred_signals,
        "signals": [
            {
                "signal_type": item.signal_type.value,
                "evidence_id": str(item.evidence_id),
                "reason": item.reason,
                "weight": SIGNAL_WEIGHTS[item.signal_type],
            }
            for item in result.signals
        ],
        "score": {
            "total_score": result.score.total_score,
            "classification": result.score.classification.value,
            "is_qualified": result.score.is_qualified,
            "distinct_buying_signals": result.score.distinct_buying_signals,
            "ruleset_version": result.score.ruleset_version,
        },
    }


@research_router.get("")
async def list_research() -> list[dict[str, str]]:
    return []


@research_router.post("/company")
async def submit_company_research(
    body: CompanyResearchRequest,
    scope: TenantScope = Depends(tenant_scope),
    session: AsyncSession = Depends(db_session),
) -> dict[str, object]:
    service = build_research_service(session)
    try:
        result = await service.submit(scope, CompanyId(body.company_id))
    except PermanentSourceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    status = "already_enqueued" if result.already_enqueued else "accepted"
    return _research_body(result, status=status)


@research_router.get("/company/{company_id}")
async def get_company_research(
    company_id: UUID,
    scope: TenantScope = Depends(tenant_scope),
    session: AsyncSession = Depends(db_session),
) -> dict[str, object]:
    service = build_research_service(session)
    try:
        result = await service.get_result(scope, CompanyId(company_id))
    except PermanentSourceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _research_body(result, status="ready")


@drafts_router.get("")
async def list_drafts() -> list[dict[str, str]]:
    return []


@activities_router.get("")
async def list_activities() -> list[dict[str, str]]:
    return []


@followups_router.get("")
async def list_followups() -> list[dict[str, str]]:
    return []


@notifications_router.get("")
async def list_notifications() -> list[dict[str, str]]:
    return []
