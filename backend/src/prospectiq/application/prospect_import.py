"""CSV prospect import: parse, validate, persist imported prospects."""

from __future__ import annotations

import csv
import io
from typing import Any
from uuid import UUID, uuid4

from prospectiq.application.ports import ImportBatchRepository, ImportedProspectRepository, JobQueue
from prospectiq.domain.common import ImportBatchId, ImportedProspectId, TenantScope, utcnow
from prospectiq.domain.import_normalization import (
    detect_column_mapping,
    duplicate_key,
    map_row_to_fields,
)
from prospectiq.domain.jobs import Job, JobType
from prospectiq.domain.prospect_import import (
    ImportBatch,
    ImportBatchStatus,
    ImportedProspect,
    ImportedProspectStatus,
    ImportPreview,
    ImportResult,
    ImportRowError,
    ImportSubmission,
    ProspectImportError,
    ResolutionStatus,
    content_hash,
    import_idempotency_key,
)
from prospectiq.infrastructure.logging import get_logger

logger = get_logger("prospectiq.prospect_import")

MAX_IMPORT_ROWS = 10_000
MAX_IMPORT_BYTES = 5 * 1024 * 1024
PREVIEW_SAMPLE_ROWS = 5


def preview_csv_content(content: bytes) -> ImportPreview:
    """Parse CSV headers and sample rows without persistence."""
    rows, headers = _parse_csv(content)
    mapping_result = detect_column_mapping(headers)
    samples: list[dict[str, Any]] = []
    for index, row in enumerate(rows[:PREVIEW_SAMPLE_ROWS], start=2):
        normalized = map_row_to_fields(row, mapping_result.mapping)
        samples.append({"row_number": index, "normalized": normalized, "raw": dict(row)})
    return ImportPreview(
        detected_headers=mapping_result.detected_headers,
        column_mapping={k: v.value for k, v in mapping_result.mapping.items()},
        unmapped_headers=mapping_result.unmapped_headers,
        sample_rows=tuple(samples),
        estimated_row_count=len(rows),
    )


class ProspectImportService:
    def __init__(
        self,
        *,
        batches: ImportBatchRepository,
        prospects: ImportedProspectRepository,
        jobs: JobQueue,
    ) -> None:
        self._batches = batches
        self._prospects = prospects
        self._jobs = jobs

    def preview_csv(self, content: bytes) -> ImportPreview:
        return preview_csv_content(content)

    async def submit_import(
        self,
        scope: TenantScope,
        *,
        filename: str,
        content: bytes,
        provider: str | None = None,
        dry_run: bool = False,
        column_mapping_override: dict[str, str] | None = None,
    ) -> ImportSubmission:
        _assert_tenant(scope)
        if len(content) == 0:
            raise ProspectImportError("CSV file is empty.")
        if len(content) > MAX_IMPORT_BYTES:
            raise ProspectImportError(f"CSV exceeds maximum size ({MAX_IMPORT_BYTES} bytes).")
        digest = content_hash(content)
        key = import_idempotency_key(filename=filename, content_hash=digest, dry_run=dry_run)
        now = utcnow()
        batch_id = ImportBatchId(uuid4())
        rows, headers = _parse_csv(content)
        mapping_result = detect_column_mapping(headers)
        if column_mapping_override:
            from prospectiq.domain.import_normalization import ProspectField

            mapping = {
                header: ProspectField(field)
                for header, field in column_mapping_override.items()
                if field in ProspectField._value2member_map_
            }
        else:
            mapping = mapping_result.mapping

        batch = ImportBatch(
            id=batch_id,
            tenant_id=scope.tenant_id,
            source_filename=filename,
            provider=provider,
            status=ImportBatchStatus.PENDING,
            column_mapping={k: v.value for k, v in mapping.items()},
            detected_headers=list(headers),
            total_rows=len(rows),
            imported_rows=0,
            skipped_rows=0,
            error_rows=0,
            duplicate_rows=0,
            errors=[],
            dry_run=dry_run,
            job_id=None,
            content_hash=digest,
            created_at=now,
            updated_at=now,
            stored_content=content,
        )
        await self._batches.create(scope, batch)

        payload: dict[str, Any] = {
            "import_batch_id": str(batch_id),
            "filename": filename,
            "content_hash": digest,
            "provider": provider,
            "dry_run": dry_run,
        }
        if scope.workspace_id is not None:
            payload["workspace_id"] = str(scope.workspace_id)

        job = await self._jobs.enqueue(scope, JobType.IMPORT_PROSPECTS, key, payload)
        batch.job_id = job.id
        batch.status = ImportBatchStatus.PARSING
        batch.updated_at = utcnow()
        await self._batches.update(scope, batch)

        logger.info(
            "prospect_import_submitted",
            tenant_id=str(scope.tenant_id),
            batch_id=str(batch_id),
            job_id=str(job.id),
            row_count=len(rows),
            dry_run=dry_run,
        )
        return ImportSubmission(
            batch_id=batch_id,
            job_id=job.id,
            status=batch.status,
            already_enqueued=bool(job.extra.get("idempotent_replay")),
        )

    async def execute_job(self, job: Job) -> ImportResult:
        batch_id = ImportBatchId(UUID(str(job.payload["import_batch_id"])))
        scope = TenantScope(tenant_id=job.tenant_id, job_id=str(job.id))
        batch = await self._batches.get(scope, batch_id)
        if batch is None:
            raise ProspectImportError(f"Import batch {batch_id} not found.")

        batch.status = ImportBatchStatus.IMPORTING
        batch.updated_at = utcnow()
        await self._batches.update(scope, batch)

        content = batch.stored_content
        if content is None:
            raise ProspectImportError("Import batch missing stored CSV content.")

        from prospectiq.domain.import_normalization import ProspectField

        mapping = {
            header: ProspectField(field)
            for header, field in batch.column_mapping.items()
        }
        rows, _ = _parse_csv(content)
        if len(rows) > MAX_IMPORT_ROWS:
            raise ProspectImportError(f"CSV exceeds maximum {MAX_IMPORT_ROWS} rows.")

        seen_keys: set[str] = set()
        errors: list[ImportRowError] = []
        imported = skipped = error_count = duplicate_count = 0

        for row_number, row in enumerate(rows, start=2):
            try:
                normalized = map_row_to_fields(row, mapping)
                if not normalized.get("company_name") and not normalized.get("company_domain"):
                    skipped += 1
                    if not batch.dry_run:
                        await self._persist_row(
                            scope,
                            batch,
                            row_number,
                            row,
                            normalized,
                            ImportedProspectStatus.SKIPPED,
                            ResolutionStatus.NOT_FOUND,
                            error_message="Missing company name and domain.",
                        )
                    continue

                key = duplicate_key(normalized)
                if key and key in seen_keys:
                    duplicate_count += 1
                    if not batch.dry_run:
                        await self._persist_row(
                            scope,
                            batch,
                            row_number,
                            row,
                            normalized,
                            ImportedProspectStatus.DUPLICATE,
                            ResolutionStatus.PENDING,
                            error_message="Duplicate within batch.",
                        )
                    continue
                if key:
                    seen_keys.add(key)

                existing = await self._prospects.find_by_duplicate_key(scope, key) if key else None
                if existing is not None:
                    duplicate_count += 1
                    if not batch.dry_run:
                        await self._persist_row(
                            scope,
                            batch,
                            row_number,
                            row,
                            normalized,
                            ImportedProspectStatus.DUPLICATE,
                            ResolutionStatus.PENDING,
                            duplicate_of_id=existing.id,
                        )
                    continue

                imported += 1
                if not batch.dry_run:
                    await self._persist_row(
                        scope,
                        batch,
                        row_number,
                        row,
                        normalized,
                        ImportedProspectStatus.IMPORTED,
                        ResolutionStatus.PENDING,
                    )
            except Exception as exc:
                error_count += 1
                errors.append(ImportRowError(row_number=row_number, message=str(exc)))

        batch.imported_rows = imported
        batch.skipped_rows = skipped
        batch.error_rows = error_count
        batch.duplicate_rows = duplicate_count
        batch.errors = [{"row_number": e.row_number, "message": e.message} for e in errors]
        batch.status = ImportBatchStatus.COMPLETED
        batch.completed_at = utcnow()
        batch.updated_at = utcnow()
        await self._batches.update(scope, batch)

        logger.info(
            "prospect_import_completed",
            tenant_id=str(scope.tenant_id),
            batch_id=str(batch_id),
            imported=imported,
            duplicates=duplicate_count,
            skipped=skipped,
            errors=error_count,
            dry_run=batch.dry_run,
        )
        return ImportResult(
            batch_id=batch_id,
            status=batch.status,
            total_rows=len(rows),
            imported_rows=imported,
            skipped_rows=skipped,
            error_rows=error_count,
            duplicate_rows=duplicate_count,
            errors=tuple(errors),
        )

    async def get_batch(self, scope: TenantScope, batch_id: ImportBatchId) -> ImportBatch | None:
        return await self._batches.get(scope, batch_id)

    async def list_prospects(
        self,
        scope: TenantScope,
        *,
        batch_id: ImportBatchId | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ImportedProspect]:
        return await self._prospects.list_for_tenant(
            scope, batch_id=batch_id, limit=limit, offset=offset
        )

    async def get_prospect(
        self, scope: TenantScope, prospect_id: ImportedProspectId
    ) -> ImportedProspect | None:
        return await self._prospects.get(scope, prospect_id)

    async def _persist_row(
        self,
        scope: TenantScope,
        batch: ImportBatch,
        row_number: int,
        raw: dict[str, str],
        normalized: dict[str, Any],
        status: ImportedProspectStatus,
        resolution_status: ResolutionStatus,
        *,
        error_message: str | None = None,
        duplicate_of_id: ImportedProspectId | None = None,
    ) -> ImportedProspect:
        now = utcnow()
        prospect = ImportedProspect(
            id=ImportedProspectId(uuid4()),
            tenant_id=scope.tenant_id,
            import_batch_id=batch.id,
            source_row_number=row_number,
            status=status,
            resolution_status=resolution_status,
            company_id=None,
            person_id=None,
            duplicate_of_id=duplicate_of_id,
            error_message=error_message,
            raw_data=dict(raw),
            normalized_data=normalized,
            duplicate_key=duplicate_key(normalized),
            provider=batch.provider,
            created_at=now,
            updated_at=now,
        )
        return await self._prospects.create(scope, prospect)


def _parse_csv(content: bytes) -> tuple[list[dict[str, str]], list[str]]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ProspectImportError("CSV has no header row.")
    headers = [h.strip() for h in reader.fieldnames if h and h.strip()]
    rows = [{k: (v or "") for k, v in row.items()} for row in reader]
    return rows, headers


def _assert_tenant(scope: TenantScope) -> None:
    if scope.tenant_id is None:
        raise ProspectImportError("Tenant context is required.")
