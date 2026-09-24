"""Company-source ingestion API. Presentation only."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from prospectiq.api.deps import db_session, settings_dep, tenant_scope
from prospectiq.domain.common import TenantScope
from prospectiq.domain.source_url import InvalidSourceUrl
from prospectiq.infrastructure.config import Settings
from prospectiq.infrastructure.ingestion_runtime import build_ingestion_service

router = APIRouter(prefix="/sources", tags=["sources"])


class CompanySourceRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class CompanySourceAccepted(BaseModel):
    status: str
    tenant_id: str
    job_id: str
    idempotency_key: str
    normalized_url: str
    source_class: str
    already_enqueued: bool


@router.post("/company", response_model=CompanySourceAccepted)
async def submit_company_source(
    body: CompanySourceRequest,
    scope: TenantScope = Depends(tenant_scope),
    session: AsyncSession = Depends(db_session),
    settings: Settings = Depends(settings_dep),
) -> CompanySourceAccepted:
    service = build_ingestion_service(session, settings)
    try:
        result = await service.submit(scope, body.url)
    except InvalidSourceUrl as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CompanySourceAccepted(
        status=result.status,
        tenant_id=str(result.tenant_id),
        job_id=str(result.job_id),
        idempotency_key=result.idempotency_key,
        normalized_url=result.normalized_url,
        source_class=result.source_class.value,
        already_enqueued=result.already_enqueued,
    )
