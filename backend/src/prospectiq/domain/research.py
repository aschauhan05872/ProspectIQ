"""Research runs. AI summaries are interpretations bound to evidence IDs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from prospectiq.domain.common import CompanyId, EvidenceId, LeadId, PersonId, TenantId


class ResearchRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class ResearchRun:
    id: UUID
    tenant_id: TenantId
    lead_id: LeadId | None
    company_id: CompanyId | None
    person_id: PersonId | None
    status: ResearchRunStatus
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None


@dataclass(slots=True)
class ResearchSummary:
    id: UUID
    tenant_id: TenantId
    research_run_id: UUID
    summary: str
    evidence_ids: list[EvidenceId]
    created_at: datetime
