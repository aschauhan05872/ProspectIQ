"""Minimal read-only operator APIs for internal V0."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from prospectiq.api.deps import db_session, tenant_scope
from prospectiq.application.dossier import LeadDossierService
from prospectiq.domain.common import CompanyId, LeadId, TenantScope
from prospectiq.domain.ingestion import PermanentSourceError
from prospectiq.infrastructure.repositories import (
    SqlAlchemyCompanyRepository,
    SqlAlchemyDiscoveryCandidateRepository,
    SqlAlchemyEvidenceRepository,
    SqlAlchemyLeadRepository,
    SqlAlchemySignalRepository,
)
from prospectiq.infrastructure.research_runtime import build_research_service

operator_router = APIRouter(prefix="/operator", tags=["operator"])


def _dossier_service(session: AsyncSession) -> LeadDossierService:
    return LeadDossierService(
        companies=SqlAlchemyCompanyRepository(session),
        evidence=SqlAlchemyEvidenceRepository(session),
        signals=SqlAlchemySignalRepository(session),
        leads=SqlAlchemyLeadRepository(session),
        candidates=SqlAlchemyDiscoveryCandidateRepository(session),
        research=build_research_service(session),
    )


@operator_router.get("/candidates")
async def list_candidates(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    scope: TenantScope = Depends(tenant_scope),
    session: AsyncSession = Depends(db_session),
) -> dict[str, object]:
    repo = SqlAlchemyDiscoveryCandidateRepository(session)
    rows = await repo.list_for_tenant(
        scope, ingestion_status=status, limit=limit, offset=offset
    )
    return {
        "items": [
            {
                "id": str(item.id),
                "name": item.name,
                "domain": item.domain,
                "ingestion_status": item.ingestion_status.value,
                "company_id": str(item.company_id) if item.company_id else None,
                "fetch_job_id": str(item.fetch_job_id) if item.fetch_job_id else None,
                "research_job_id": str(item.research_job_id) if item.research_job_id else None,
                "lead_id": str(item.lead_id) if item.lead_id else None,
                "discovered_at": item.discovered_at.isoformat(),
            }
            for item in rows
        ],
        "limit": limit,
        "offset": offset,
    }


@operator_router.get("/leads")
async def list_operator_leads(
    qualified: bool | None = Query(default=None),
    classification: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    scope: TenantScope = Depends(tenant_scope),
    session: AsyncSession = Depends(db_session),
) -> dict[str, object]:
    repo = SqlAlchemyLeadRepository(session)
    leads = await repo.list_for_workspace(
        scope,
        limit=limit,
        offset=offset,
        is_qualified=qualified,
        classification=classification,
    )
    return {
        "items": [
            {
                "id": str(lead.id),
                "company_id": str(lead.company_id),
                "status": lead.status.value,
                "score": lead.score,
                "classification": lead.classification.value,
                "is_qualified": lead.is_qualified,
                "updated_at": lead.updated_at.isoformat(),
            }
            for lead in leads
        ],
        "limit": limit,
        "offset": offset,
    }


@operator_router.get("/leads/{lead_id}/dossier")
async def get_lead_dossier(
    lead_id: UUID,
    scope: TenantScope = Depends(tenant_scope),
    session: AsyncSession = Depends(db_session),
) -> dict[str, object]:
    service = _dossier_service(session)
    try:
        dossier = await service.get_by_lead_id(scope, LeadId(lead_id))
    except PermanentSourceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialize_dossier(dossier)


@operator_router.get("/companies/{company_id}/dossier")
async def get_company_dossier(
    company_id: UUID,
    scope: TenantScope = Depends(tenant_scope),
    session: AsyncSession = Depends(db_session),
) -> dict[str, object]:
    service = _dossier_service(session)
    try:
        dossier = await service.get_by_company_id(scope, CompanyId(company_id))
    except PermanentSourceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialize_dossier(dossier)


def _serialize_dossier(dossier: object) -> dict[str, object]:
    return {
        "company": dossier.company,  # type: ignore[attr-defined]
        "evidence": dossier.evidence,  # type: ignore[attr-defined]
        "signals": dossier.signals,  # type: ignore[attr-defined]
        "score": dossier.score,  # type: ignore[attr-defined]
        "pipeline": dossier.pipeline,  # type: ignore[attr-defined]
    }
