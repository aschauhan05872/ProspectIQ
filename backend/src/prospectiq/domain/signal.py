"""Buying-signal types from the Lead Generation SOP scoring table."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from prospectiq.domain.common import (
    CompanyId,
    EvidenceId,
    LeadId,
    PersonId,
    SignalId,
    TenantId,
)


class SignalType(StrEnum):
    CHANGED_JOB_RECENTLY = "changed_job_recently"
    ACTIVE_ON_LINKEDIN = "active_on_linkedin"
    TALKS_ABOUT_TECH_GROWTH = "talks_about_tech_growth"
    HIRING_TECH_ROLES = "hiring_tech_roles"
    FUNDING_NEWS = "funding_news"
    EXPANSION_LAUNCH = "expansion_launch"


# SOP scoring table. Do not change weights without an explicit SOP update.
SIGNAL_WEIGHTS: dict[SignalType, int] = {
    SignalType.CHANGED_JOB_RECENTLY: 2,
    SignalType.ACTIVE_ON_LINKEDIN: 1,
    SignalType.TALKS_ABOUT_TECH_GROWTH: 2,
    SignalType.HIRING_TECH_ROLES: 3,
    SignalType.FUNDING_NEWS: 3,
    SignalType.EXPANSION_LAUNCH: 2,
}

BUYING_SIGNAL_TYPES: frozenset[SignalType] = frozenset(SIGNAL_WEIGHTS)


@dataclass(frozen=True, slots=True)
class DetectedSignal:
    signal_type: SignalType
    evidence_id: EvidenceId
    reason: str = ""


@dataclass(slots=True)
class Signal:
    id: SignalId
    tenant_id: TenantId
    signal_type: SignalType
    weight: int
    detected_at: datetime
    evidence_id: EvidenceId
    company_id: CompanyId | None = None
    person_id: PersonId | None = None
    lead_id: LeadId | None = None
    reason: str | None = None
