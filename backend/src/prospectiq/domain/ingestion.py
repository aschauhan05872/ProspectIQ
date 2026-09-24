"""Company-source ingestion types. Observations are not SOP scores."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from re import IGNORECASE, search
from uuid import UUID

from prospectiq.domain.common import CompanyId, EvidenceId, JobId, TenantId
from prospectiq.domain.source_registry import SourceClass
from prospectiq.domain.source_url import NormalizedSourceUrl


class SourceFactKind(StrEnum):
    PAGE_CONTENT = "page_content"
    HIRING_LANGUAGE_OBSERVED = "hiring_language_observed"
    RESEARCH_PAGE_CONTENT = "research_page_content"


class SourceFetchError(Exception):
    permanent: bool = False


class PermanentSourceError(SourceFetchError):
    permanent = True


class RetryableSourceError(SourceFetchError):
    permanent = False


# Phrases observed on a page. These are source-derived observations, not scores.
HIRING_LANGUAGE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("software engineer", r"\bsoftware engineers?\b"),
    ("backend engineer", r"\bback[\s-]?end engineers?\b"),
    ("frontend engineer", r"\bfront[\s-]?end engineers?\b"),
    ("full-stack engineer", r"\bfull[\s-]?stack engineers?\b"),
    ("data engineer", r"\bdata engineers?\b"),
    ("AI/ML engineer", r"\b(?:ai(?:/ml)?|machine learning) engineers?\b"),
    ("DevOps", r"\bdevops\b"),
    ("QA", r"\b(?:qa|quality assurance)\b"),
    ("product manager", r"\bproduct managers?\b"),
    ("engineering leadership", r"\b(?:cto|chief technology officer|vp engineering|"
     r"head of engineering|director of engineering)\b"),
)


def observe_hiring_language(text: str) -> list[str]:
    """Return phrases explicitly present in the page text. Does not create signals."""

    found: list[str] = []
    for label, pattern in HIRING_LANGUAGE_PATTERNS:
        if search(pattern, text, IGNORECASE) and label not in found:
            found.append(label)
    return found


@dataclass(frozen=True, slots=True)
class CompanySourceSubmission:
    tenant_id: TenantId
    job_id: JobId
    idempotency_key: str
    normalized_url: str
    source_class: SourceClass
    status: str
    already_enqueued: bool


@dataclass(frozen=True, slots=True)
class IngestedCompanySource:
    tenant_id: TenantId
    company_id: CompanyId
    company_source_id: UUID
    evidence_ids: list[EvidenceId]
    normalized_url: str
    source_class: SourceClass
    identity_requires_review: bool
    page_title: str | None
    observed_hiring_phrases: list[str] = field(default_factory=list)
    collected_at: datetime | None = None


def page_company_name(title: str | None, source: NormalizedSourceUrl) -> str:
    cleaned = (title or "").strip()
    if cleaned:
        return cleaned[:512]
    return source.identity_host
