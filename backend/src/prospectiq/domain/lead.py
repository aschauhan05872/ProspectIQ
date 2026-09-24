"""Lead aggregate: company + person + score + pipeline status."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from prospectiq.domain.common import CompanyId, LeadId, PersonId, TenantId, WorkspaceId
from prospectiq.domain.pipeline import LeadStatus
from prospectiq.domain.scoring import LeadClassification


@dataclass(slots=True)
class Lead:
    id: LeadId
    tenant_id: TenantId
    workspace_id: WorkspaceId
    company_id: CompanyId
    person_id: PersonId | None
    status: LeadStatus
    score: int
    classification: LeadClassification
    is_qualified: bool
    search_profile_id: UUID | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class LeadScoreRecord:
    id: UUID
    tenant_id: TenantId
    lead_id: LeadId
    total_score: int
    classification: LeadClassification
    is_qualified: bool
    distinct_buying_signals: int
    breakdown: list[dict[str, object]]
    ruleset_version: str
    scored_at: datetime
