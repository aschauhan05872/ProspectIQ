"""Company discovery API. Presentation only."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from prospectiq.api.deps import db_session, settings_dep, tenant_scope
from prospectiq.domain.common import JobId, TenantScope
from prospectiq.domain.discovery import (
    DiscoveryResult,
    DiscoverySubmission,
    PermanentDiscoveryError,
    normalize_discovery_request,
    provider_support_payload,
)
from prospectiq.infrastructure.config import Settings
from prospectiq.infrastructure.discovery_runtime import build_discovery_service

router = APIRouter(prefix="/discovery", tags=["discovery"])


class CompanyDiscoveryRequest(BaseModel):
    industry: str = Field(min_length=1, max_length=128)
    countries: list[str] = Field(min_length=1)
    employee_min: int = Field(default=11, ge=1)
    employee_max: int = Field(default=1000, ge=1)
    hiring_required: bool = False
    keywords: list[str] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=100)


def _discovery_body(
    result: DiscoveryResult | DiscoverySubmission, *, status: str
) -> dict[str, object]:
    if isinstance(result, DiscoveryResult):
        return {
            "status": status,
            "tenant_id": str(result.tenant_id),
            "job_id": str(result.job_id),
            "provider_key": result.provider_key,
            "candidate_count": result.candidate_count,
            "accepted_count": result.accepted_count,
            "rejected_count": result.rejected_count,
            "fetch_jobs_created": result.fetch_jobs_created,
            "duration_ms": result.duration_ms,
            "field_support": provider_support_payload(),
            "candidates": [
                {
                    "id": str(item.id),
                    "name": item.name,
                    "domain": item.domain,
                    "website_url": item.website_url,
                    "normalized_website": item.normalized_website,
                    "provider_key": item.provider_key,
                    "source_locator": item.source_locator,
                    "discovered_at": item.discovered_at.isoformat(),
                    "confidence": item.confidence,
                    "provider_rank": item.provider_rank,
                    "field_checks": item.field_checks,
                    "evidence_id": str(item.evidence_id) if item.evidence_id else None,
                    "company_id": str(item.company_id) if item.company_id else None,
                    "fetch_job_id": str(item.fetch_job_id) if item.fetch_job_id else None,
                    "research_job_id": str(item.research_job_id) if item.research_job_id else None,
                    "lead_id": str(item.lead_id) if item.lead_id else None,
                    "source_evidence_ids": item.source_evidence_ids,
                    "ingestion_status": item.ingestion_status.value,
                }
                for item in result.candidates
            ],
        }
    return {
        "status": status,
        "tenant_id": str(result.tenant_id),
        "job_id": str(result.job_id),
        "idempotency_key": result.idempotency_key,
        "already_enqueued": result.already_enqueued,
        "provider_key": result.provider_key,
        "normalized_request": result.normalized_request,
        "field_support": [
            {
                "field_name": item.field_name,
                "requested_in_icp": item.requested_in_icp,
                "provider_support": item.provider_support.value,
                "notes": item.notes,
            }
            for item in result.field_support
        ],
    }


@router.post("/companies")
async def submit_company_discovery(
    body: CompanyDiscoveryRequest,
    scope: TenantScope = Depends(tenant_scope),
    session: AsyncSession = Depends(db_session),
    settings: Settings = Depends(settings_dep),
) -> dict[str, object]:
    try:
        request = normalize_discovery_request(
            industry=body.industry,
            countries=body.countries,
            employee_min=body.employee_min,
            employee_max=body.employee_max,
            hiring_required=body.hiring_required,
            keywords=body.keywords,
            limit=min(body.limit, settings.discovery_max_candidates),
        )
        service = build_discovery_service(session, settings)
        result = await service.submit(scope, request)
    except PermanentDiscoveryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    status = "already_enqueued" if result.already_enqueued else "accepted"
    return _discovery_body(result, status=status)


@router.get("/companies/{job_id}")
async def get_company_discovery(
    job_id: UUID,
    scope: TenantScope = Depends(tenant_scope),
    session: AsyncSession = Depends(db_session),
    settings: Settings = Depends(settings_dep),
) -> dict[str, object]:
    try:
        service = build_discovery_service(session, settings)
        result = await service.get_result(scope, JobId(job_id))
    except PermanentDiscoveryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _discovery_body(result, status="ready")
