"""Shared domain primitives."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import NewType
from uuid import UUID

TenantId = NewType("TenantId", UUID)
WorkspaceId = NewType("WorkspaceId", UUID)
UserId = NewType("UserId", UUID)
CompanyId = NewType("CompanyId", UUID)
PersonId = NewType("PersonId", UUID)
LeadId = NewType("LeadId", UUID)
EvidenceId = NewType("EvidenceId", UUID)
CompanyFactId = NewType("CompanyFactId", UUID)
SignalId = NewType("SignalId", UUID)
JobId = NewType("JobId", UUID)
ImportBatchId = NewType("ImportBatchId", UUID)
ImportedProspectId = NewType("ImportedProspectId", UUID)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class TenantScope:
    """Required on every SaaS-bound write/read in application services."""

    tenant_id: TenantId
    workspace_id: WorkspaceId | None = None
    user_id: UserId | None = None
    request_id: str | None = None
    job_id: str | None = None
