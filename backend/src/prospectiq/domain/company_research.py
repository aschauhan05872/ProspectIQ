"""Controlled company website research — evidence collection only (Phase 4)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from prospectiq.domain.common import CompanyId, EvidenceId, JobId, TenantId

COMPANY_RESEARCH_VERSION = "company-research-v1"


class CompanyResearchStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NOT_RESEARCHABLE = "not_researchable"


class ResearchPageType(StrEnum):
    HOME = "home"
    ABOUT = "about"
    PRODUCTS = "products"
    SERVICES = "services"
    SOLUTIONS = "solutions"
    PLATFORM = "platform"
    TECHNOLOGY = "technology"
    CONTACT = "contact"
    CAREERS = "careers"
    NEWS = "news"
    BLOG = "blog"
    OTHER = "other"


class ResearchPageFetchStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ResearchErrorCode(StrEnum):
    NO_WEBSITE = "no_website"
    INVALID_WEBSITE = "invalid_website"
    ALL_PAGES_FAILED = "all_pages_failed"
    PARTIAL_FAILURE = "partial_failure"
    UNKNOWN = "unknown"


# Lower number = higher priority when selecting pages within budget.
PAGE_TYPE_PRIORITY: dict[ResearchPageType, int] = {
    ResearchPageType.HOME: 0,
    ResearchPageType.ABOUT: 1,
    ResearchPageType.PRODUCTS: 2,
    ResearchPageType.SERVICES: 3,
    ResearchPageType.SOLUTIONS: 4,
    ResearchPageType.PLATFORM: 5,
    ResearchPageType.TECHNOLOGY: 6,
    ResearchPageType.CONTACT: 7,
    ResearchPageType.CAREERS: 8,
    ResearchPageType.NEWS: 9,
    ResearchPageType.BLOG: 10,
    ResearchPageType.OTHER: 99,
}


class CompanyResearchError(Exception):
    permanent: bool = True
    error_code: ResearchErrorCode | None = None

    def __init__(
        self,
        message: str,
        *,
        error_code: ResearchErrorCode | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code


class PermanentCompanyResearchError(CompanyResearchError):
    permanent = True


class RetryableCompanyResearchError(CompanyResearchError):
    permanent = False


@dataclass(frozen=True, slots=True)
class PlannedResearchPage:
    url: str
    normalized_url: str
    page_type: ResearchPageType
    priority: int


@dataclass(slots=True)
class CompanyResearchCase:
    id: UUID
    tenant_id: TenantId
    company_id: CompanyId
    status: CompanyResearchStatus
    job_id: JobId | None
    requested_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None
    pages_requested: int
    pages_fetched: int
    pages_failed: int
    research_version: str
    error_code: ResearchErrorCode | None
    error_message_safe: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class ResearchPage:
    id: UUID
    tenant_id: TenantId
    research_case_id: UUID
    company_id: CompanyId
    url: str
    normalized_url: str
    page_type: ResearchPageType
    title: str | None
    http_status: int | None
    content_type: str | None
    content_hash: str | None
    normalized_text: str | None
    fetched_at: datetime | None
    fetch_duration_ms: int | None
    fetch_status: ResearchPageFetchStatus
    failure_class: str | None
    evidence_id: EvidenceId | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CompanyResearchSubmission:
    case_id: UUID
    job_id: JobId
    status: CompanyResearchStatus
    already_enqueued: bool


@dataclass(frozen=True, slots=True)
class CompanyResearchResult:
    case: CompanyResearchCase
    pages: tuple[ResearchPage, ...]
    evidence_count: int


def research_job_idempotency_key(case_id: UUID) -> str:
    return f"research_company:{case_id}"


def content_fingerprint(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return digest[:32]


def build_page_fact(*, page_type: ResearchPageType, title: str | None, text: str) -> str:
    """Deterministic source-derived fact — no opportunity interpretation."""
    label = page_type.value.replace("_", " ")
    snippet = text.strip()[:800]
    if title:
        return f"Company {label} page titled '{title}': {snippet}"[:4000]
    return f"Company {label} page content: {snippet}"[:4000]
