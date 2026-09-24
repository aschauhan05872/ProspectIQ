"""Prospect CSV import domain models."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from prospectiq.domain.common import (
    CompanyId,
    ImportBatchId,
    ImportedProspectId,
    PersonId,
    TenantId,
)


class ImportBatchStatus(StrEnum):
    PENDING = "pending"
    PARSING = "parsing"
    VALIDATING = "validating"
    IMPORTING = "importing"
    COMPLETED = "completed"
    FAILED = "failed"


class ImportedProspectStatus(StrEnum):
    IMPORTED = "imported"
    DUPLICATE = "duplicate"
    ERROR = "error"
    SKIPPED = "skipped"


class ResolutionStatus(StrEnum):
    PENDING = "pending"
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"
    MANUAL_REVIEW = "manual_review"


class ProspectImportError(Exception):
    permanent: bool = True


@dataclass(frozen=True, slots=True)
class ImportRowError:
    row_number: int
    message: str


@dataclass(slots=True)
class ImportBatch:
    id: ImportBatchId
    tenant_id: TenantId
    source_filename: str
    provider: str | None
    status: ImportBatchStatus
    column_mapping: dict[str, str]
    detected_headers: list[str]
    total_rows: int
    imported_rows: int
    skipped_rows: int
    error_rows: int
    duplicate_rows: int
    errors: list[dict[str, Any]]
    dry_run: bool
    job_id: UUID | None
    content_hash: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    stored_content: bytes | None = field(default=None, repr=False)


@dataclass(slots=True)
class ImportedProspect:
    id: ImportedProspectId
    tenant_id: TenantId
    import_batch_id: ImportBatchId
    source_row_number: int
    status: ImportedProspectStatus
    resolution_status: ResolutionStatus
    company_id: CompanyId | None
    person_id: PersonId | None
    duplicate_of_id: ImportedProspectId | None
    error_message: str | None
    raw_data: dict[str, Any]
    normalized_data: dict[str, Any]
    duplicate_key: str | None
    provider: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ImportPreview:
    detected_headers: tuple[str, ...]
    column_mapping: dict[str, str]
    unmapped_headers: tuple[str, ...]
    sample_rows: tuple[dict[str, Any], ...]
    estimated_row_count: int


@dataclass(frozen=True, slots=True)
class ImportSubmission:
    batch_id: ImportBatchId
    job_id: UUID
    status: ImportBatchStatus
    already_enqueued: bool


@dataclass(frozen=True, slots=True)
class ImportResult:
    batch_id: ImportBatchId
    status: ImportBatchStatus
    total_rows: int
    imported_rows: int
    skipped_rows: int
    error_rows: int
    duplicate_rows: int
    errors: tuple[ImportRowError, ...]


def import_idempotency_key(
    *,
    filename: str,
    content_hash: str,
    dry_run: bool,
) -> str:
    payload = json.dumps(
        {"filename": filename, "hash": content_hash, "dry_run": dry_run},
        sort_keys=True,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"import_prospects:{digest}"


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
