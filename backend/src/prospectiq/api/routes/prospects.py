"""Prospect CSV import and listing APIs."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from prospectiq.api.deps import db_session, tenant_scope
from prospectiq.application.prospect_import import preview_csv_content
from prospectiq.domain.common import ImportBatchId, ImportedProspectId, TenantScope
from prospectiq.domain.prospect_import import ProspectImportError
from prospectiq.infrastructure.import_runtime import (
    build_company_resolution_service,
    build_prospect_import_service,
)

router = APIRouter(prefix="/prospects", tags=["prospects"])


class ImportPreviewResponse(BaseModel):
    detected_headers: list[str]
    column_mapping: dict[str, str]
    unmapped_headers: list[str]
    sample_rows: list[dict[str, Any]]
    estimated_row_count: int


class ImportAcceptedResponse(BaseModel):
    batch_id: str
    job_id: str
    status: str
    already_enqueued: bool


class ImportBatchResponse(BaseModel):
    batch_id: str
    source_filename: str
    provider: str | None
    status: str
    total_rows: int
    imported_rows: int
    skipped_rows: int
    error_rows: int
    duplicate_rows: int
    dry_run: bool
    errors: list[dict[str, Any]]


class ProspectResponse(BaseModel):
    id: str
    import_batch_id: str
    source_row_number: int
    status: str
    resolution_status: str
    company_id: str | None
    person_id: str | None
    normalized_data: dict[str, Any]


class ResolveBatchResponse(BaseModel):
    resolved: int
    skipped: int
    manual_review: int
    not_found: int


@router.post("/import/preview", response_model=ImportPreviewResponse)
async def preview_import(
    file: UploadFile = File(...),
    scope: TenantScope = Depends(tenant_scope),
) -> ImportPreviewResponse:
    _ = scope
    content = await file.read()
    preview = preview_csv_content(content)
    return ImportPreviewResponse(
        detected_headers=list(preview.detected_headers),
        column_mapping=dict(preview.column_mapping),
        unmapped_headers=list(preview.unmapped_headers),
        sample_rows=list(preview.sample_rows),
        estimated_row_count=preview.estimated_row_count,
    )


@router.post("/import", response_model=ImportAcceptedResponse, status_code=202)
async def submit_import(
    file: UploadFile = File(...),
    provider: str | None = Form(default=None),
    dry_run: bool = Form(default=False),
    scope: TenantScope = Depends(tenant_scope),
    session: AsyncSession = Depends(db_session),
) -> ImportAcceptedResponse:
    content = await file.read()
    filename = file.filename or "import.csv"
    service = build_prospect_import_service(session)
    try:
        submission = await service.submit_import(
            scope,
            filename=filename,
            content=content,
            provider=provider,
            dry_run=dry_run,
        )
    except ProspectImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ImportAcceptedResponse(
        batch_id=str(submission.batch_id),
        job_id=str(submission.job_id),
        status=submission.status.value,
        already_enqueued=submission.already_enqueued,
    )


@router.get("/import/{batch_id}", response_model=ImportBatchResponse)
async def get_import_batch(
    batch_id: UUID,
    scope: TenantScope = Depends(tenant_scope),
    session: AsyncSession = Depends(db_session),
) -> ImportBatchResponse:
    service = build_prospect_import_service(session)
    batch = await service.get_batch(scope, ImportBatchId(batch_id))
    if batch is None:
        raise HTTPException(status_code=404, detail="Import batch not found.")
    return ImportBatchResponse(
        batch_id=str(batch.id),
        source_filename=batch.source_filename,
        provider=batch.provider,
        status=batch.status.value,
        total_rows=batch.total_rows,
        imported_rows=batch.imported_rows,
        skipped_rows=batch.skipped_rows,
        error_rows=batch.error_rows,
        duplicate_rows=batch.duplicate_rows,
        dry_run=batch.dry_run,
        errors=batch.errors,
    )


@router.post("/import/{batch_id}/resolve", response_model=ResolveBatchResponse)
async def resolve_import_batch(
    batch_id: UUID,
    scope: TenantScope = Depends(tenant_scope),
    session: AsyncSession = Depends(db_session),
) -> ResolveBatchResponse:
    import_service = build_prospect_import_service(session)
    batch = await import_service.get_batch(scope, ImportBatchId(batch_id))
    if batch is None:
        raise HTTPException(status_code=404, detail="Import batch not found.")
    prospects = await import_service.list_prospects(
        scope, batch_id=ImportBatchId(batch_id), limit=10_000
    )
    resolver = build_company_resolution_service(session)
    stats = await resolver.resolve_batch(scope, prospects)
    return ResolveBatchResponse(
        resolved=stats["resolved"],
        skipped=stats["skipped"],
        manual_review=stats["manual_review"],
        not_found=stats["not_found"],
    )


@router.get("", response_model=list[ProspectResponse])
async def list_prospects(
    batch_id: UUID | None = None,
    limit: int = 100,
    offset: int = 0,
    scope: TenantScope = Depends(tenant_scope),
    session: AsyncSession = Depends(db_session),
) -> list[ProspectResponse]:
    service = build_prospect_import_service(session)
    prospects = await service.list_prospects(
        scope,
        batch_id=ImportBatchId(batch_id) if batch_id else None,
        limit=min(limit, 500),
        offset=offset,
    )
    return [_prospect_body(item) for item in prospects]


@router.get("/{prospect_id}", response_model=ProspectResponse)
async def get_prospect(
    prospect_id: UUID,
    scope: TenantScope = Depends(tenant_scope),
    session: AsyncSession = Depends(db_session),
) -> ProspectResponse:
    service = build_prospect_import_service(session)
    prospect = await service.get_prospect(scope, ImportedProspectId(prospect_id))
    if prospect is None:
        raise HTTPException(status_code=404, detail="Prospect not found.")
    return _prospect_body(prospect)


def _prospect_body(prospect: object) -> ProspectResponse:
    return ProspectResponse(
        id=str(prospect.id),  # type: ignore[attr-defined]
        import_batch_id=str(prospect.import_batch_id),  # type: ignore[attr-defined]
        source_row_number=prospect.source_row_number,  # type: ignore[attr-defined]
        status=prospect.status.value,  # type: ignore[attr-defined]
        resolution_status=prospect.resolution_status.value,  # type: ignore[attr-defined]
        company_id=str(prospect.company_id) if prospect.company_id else None,  # type: ignore[attr-defined]
        person_id=str(prospect.person_id) if prospect.person_id else None,  # type: ignore[attr-defined]
        normalized_data=dict(prospect.normalized_data),  # type: ignore[attr-defined]
    )

