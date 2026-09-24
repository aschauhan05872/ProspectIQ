"""Durable background job contract.

Jobs are idempotent, retryable, and owned by a single worker lease. The
application layer depends on this model, not on Redis or a vendor queue SDK.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from prospectiq.domain.common import JobId, TenantId, utcnow


class JobType(StrEnum):
    DISCOVER_COMPANIES = "discover_companies"
    FETCH_SOURCE = "fetch_source"
    FETCH_COMPANY_NEWS = "fetch_company_news"
    RESEARCH_LEAD = "research_lead"
    IMPORT_PROSPECTS = "import_prospects"
    RESOLVE_COMPANY = "resolve_company"
    RESEARCH_COMPANY = "research_company"
    ANALYZE_RESEARCH = "analyze_research"
    MAP_SERVICES = "map_services"
    GENERATE_OUTREACH = "generate_outreach"
    GENERATE_PITCH_BRIEF = "generate_pitch_brief"
    SCORE_LEAD = "score_lead"
    GENERATE_DRAFT = "generate_draft"
    SEND_NOTIFICATION = "send_notification"


class JobStatus(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD = "dead"


DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_LEASE_SECONDS = 60


@dataclass(slots=True)
class Job:
    id: JobId
    tenant_id: TenantId
    job_type: JobType
    idempotency_key: str
    payload: dict[str, Any]
    status: JobStatus
    attempts: int
    max_attempts: int
    available_at: datetime
    leased_until: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    extra: dict[str, Any] = field(default_factory=dict)


def backoff_seconds(attempts: int) -> int:
    """Exponential backoff: 5, 10, 20, 40, ... capped at 15 minutes."""

    return int(min(5 * (2 ** max(attempts - 1, 0)), 15 * 60))


def next_available_at(attempts: int, *, now: datetime | None = None) -> datetime:
    current = now or utcnow()
    return current + timedelta(seconds=backoff_seconds(attempts))
