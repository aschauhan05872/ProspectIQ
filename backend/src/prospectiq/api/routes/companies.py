"""Company-level APIs including controlled website research."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from prospectiq.api.deps import db_session, settings_dep, tenant_scope
from prospectiq.domain.common import CompanyId, TenantScope
from prospectiq.domain.company_facts import CompanyFact, PermanentCompanyFactError
from prospectiq.domain.company_research import (
    CompanyResearchResult,
    PermanentCompanyResearchError,
    ResearchErrorCode,
)
from prospectiq.infrastructure.company_fact_extraction_runtime import (
    build_company_fact_extraction_service,
)
from prospectiq.infrastructure.company_research_runtime import build_company_research_service
from prospectiq.infrastructure.config import Settings

companies_router = APIRouter(prefix="/companies", tags=["companies"])
research_cases_router = APIRouter(prefix="/research", tags=["company-research"])


class CompanyResearchAccepted(BaseModel):
    research_case_id: str
    job_id: str
    status: str
    already_enqueued: bool


class CompanyFactExtractionAccepted(BaseModel):
    job_id: str
    research_case_id: str
    already_enqueued: bool


class CompanyFactResponse(BaseModel):
    fact_id: str
    company_id: str
    research_case_id: str
    category: str
    subject: str
    value: str
    evidence_ids: list[str]
    origin: str
    confidence: str
    extraction_method: str
    extraction_version: str
    status: str
    extracted_at: str


class CompanyFactsListResponse(BaseModel):
    facts: list[CompanyFactResponse]
    count: int


class CompanyResearchResponse(BaseModel):
    research_case_id: str
    company_id: str
    status: str
    job_id: str | None
    pages_requested: int
    pages_fetched: int
    pages_failed: int
    evidence_count: int
    research_version: str
    error_code: str | None
    error_message: str | None
    requested_at: str
    started_at: str | None
    completed_at: str | None
    failed_at: str | None
    pages: list[dict[str, Any]]


@companies_router.post(
    "/{company_id}/research",
    response_model=CompanyResearchAccepted,
    status_code=202,
)
async def start_company_research(
    company_id: UUID,
    scope: TenantScope = Depends(tenant_scope),
    session: AsyncSession = Depends(db_session),
    settings: Settings = Depends(settings_dep),
) -> CompanyResearchAccepted:
    service = build_company_research_service(session, settings)
    try:
        submission = await service.submit(scope, CompanyId(company_id))
    except PermanentCompanyResearchError as exc:
        code = exc.error_code or ResearchErrorCode.NO_WEBSITE
        raise HTTPException(
            status_code=400,
            detail={"message": str(exc), "error_code": code.value, "status": "not_researchable"},
        ) from exc
    return CompanyResearchAccepted(
        research_case_id=str(submission.case_id),
        job_id=str(submission.job_id),
        status=submission.status.value,
        already_enqueued=submission.already_enqueued,
    )


@companies_router.get("/{company_id}/research", response_model=CompanyResearchResponse)
async def get_company_research(
    company_id: UUID,
    scope: TenantScope = Depends(tenant_scope),
    session: AsyncSession = Depends(db_session),
    settings: Settings = Depends(settings_dep),
) -> CompanyResearchResponse:
    service = build_company_research_service(session, settings)
    result = await service.get_latest_for_company(scope, CompanyId(company_id))
    if result is None:
        raise HTTPException(status_code=404, detail="No research case found for company.")
    return _serialize_result(result)


@companies_router.get("/{company_id}/facts", response_model=CompanyFactsListResponse)
async def get_company_facts(
    company_id: UUID,
    scope: TenantScope = Depends(tenant_scope),
    session: AsyncSession = Depends(db_session),
) -> CompanyFactsListResponse:
    service = build_company_fact_extraction_service(session)
    facts = await service.list_for_company(scope, CompanyId(company_id))
    return _serialize_facts(facts)


@research_cases_router.post(
    "/cases/{case_id}/extract-facts",
    response_model=CompanyFactExtractionAccepted,
    status_code=202,
)
async def extract_research_case_facts(
    case_id: UUID,
    scope: TenantScope = Depends(tenant_scope),
    session: AsyncSession = Depends(db_session),
) -> CompanyFactExtractionAccepted:
    service = build_company_fact_extraction_service(session)
    try:
        submission = await service.submit_for_case(scope, case_id)
    except PermanentCompanyFactError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc
    return CompanyFactExtractionAccepted(
        job_id=str(submission.job_id),
        research_case_id=str(submission.research_case_id),
        already_enqueued=submission.already_enqueued,
    )


@research_cases_router.get("/cases/{case_id}/facts", response_model=CompanyFactsListResponse)
async def get_research_case_facts(
    case_id: UUID,
    scope: TenantScope = Depends(tenant_scope),
    session: AsyncSession = Depends(db_session),
) -> CompanyFactsListResponse:
    service = build_company_fact_extraction_service(session)
    try:
        facts = await service.list_for_case(scope, case_id)
    except PermanentCompanyFactError as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc
    return _serialize_facts(facts)


@research_cases_router.get("/cases/{case_id}", response_model=CompanyResearchResponse)
async def get_research_case(
    case_id: UUID,
    scope: TenantScope = Depends(tenant_scope),
    session: AsyncSession = Depends(db_session),
    settings: Settings = Depends(settings_dep),
) -> CompanyResearchResponse:
    service = build_company_research_service(session, settings)
    result = await service.get_case(scope, case_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Research case not found.")
    return _serialize_result(result)


def _serialize_facts(facts: list[CompanyFact]) -> CompanyFactsListResponse:
    return CompanyFactsListResponse(
        count=len(facts),
        facts=[
            CompanyFactResponse(
                fact_id=str(fact.id),
                company_id=str(fact.company_id),
                research_case_id=str(fact.research_case_id),
                category=fact.category.value,
                subject=fact.subject,
                value=fact.value,
                evidence_ids=[str(item) for item in fact.evidence_ids],
                origin=fact.origin.value,
                confidence=fact.confidence.value,
                extraction_method=fact.extraction_method,
                extraction_version=fact.extraction_version,
                status=fact.status.value,
                extracted_at=fact.extracted_at.isoformat(),
            )
            for fact in facts
        ],
    )


def _serialize_result(result: CompanyResearchResult) -> CompanyResearchResponse:
    case = result.case
    return CompanyResearchResponse(
        research_case_id=str(case.id),
        company_id=str(case.company_id),
        status=case.status.value,
        job_id=str(case.job_id) if case.job_id else None,
        pages_requested=case.pages_requested,
        pages_fetched=case.pages_fetched,
        pages_failed=case.pages_failed,
        evidence_count=result.evidence_count,
        research_version=case.research_version,
        error_code=case.error_code.value if case.error_code else None,
        error_message=case.error_message_safe,
        requested_at=case.requested_at.isoformat(),
        started_at=case.started_at.isoformat() if case.started_at else None,
        completed_at=case.completed_at.isoformat() if case.completed_at else None,
        failed_at=case.failed_at.isoformat() if case.failed_at else None,
        pages=[
            {
                "url": page.normalized_url,
                "page_type": page.page_type.value,
                "title": page.title,
                "http_status": page.http_status,
                "fetch_status": page.fetch_status.value,
                "failure_class": page.failure_class,
                "evidence_id": str(page.evidence_id) if page.evidence_id else None,
                "content_hash": page.content_hash,
            }
            for page in result.pages
        ],
    )
