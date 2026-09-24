"""Structured company facts derived from research evidence (Phase 5).

Facts are traceable intelligence — not opportunities, scores, or recommendations.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from prospectiq.domain.common import (
    CompanyFactId,
    CompanyId,
    Confidence,
    EvidenceId,
    JobId,
    TenantId,
)
from prospectiq.domain.evidence import EvidenceOrigin

COMPANY_FACT_EXTRACTION_VERSION = "company-fact-extraction-v2"
EXTRACTION_METHOD_DETERMINISTIC = "deterministic_v2"
EXTRACTION_METHOD_AI = "ai_v1"


class CompanyFactCategory(StrEnum):
    BUSINESS = "business"
    GEOGRAPHY = "geography"
    COMMERCIAL = "commercial"
    ACTIVITY = "activity"
    DIGITAL = "digital"
    ORGANIZATION = "organization"


class CompanyFactTier(StrEnum):
    SUBSTANTIVE = "substantive"
    METADATA = "metadata"


class CompanyFactStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class CompanyFactError(Exception):
    permanent: bool = True


class PermanentCompanyFactError(CompanyFactError):
    permanent = True


class RetryableCompanyFactError(CompanyFactError):
    permanent = False


@dataclass(frozen=True, slots=True)
class EvidencePageContext:
    """Bounded input for fact extraction — website content is untrusted data."""

    evidence_id: EvidenceId
    company_id: CompanyId
    source_locator: str
    page_type: str
    title: str | None
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExtractedCompanyFact:
    category: CompanyFactCategory
    subject: str
    value: str
    evidence_ids: tuple[EvidenceId, ...]
    origin: EvidenceOrigin
    confidence: Confidence
    fact_tier: CompanyFactTier = CompanyFactTier.SUBSTANTIVE

    def dedupe_key(self) -> str:
        return compute_fact_dedupe_key(
            category=self.category,
            subject=self.subject,
            value=self.value,
            evidence_ids=self.evidence_ids,
            fact_tier=self.fact_tier,
        )


@dataclass(slots=True)
class CompanyFact:
    id: CompanyFactId
    tenant_id: TenantId
    company_id: CompanyId
    research_case_id: UUID
    category: CompanyFactCategory
    subject: str
    value: str
    evidence_ids: list[EvidenceId]
    origin: EvidenceOrigin
    confidence: Confidence
    fact_tier: CompanyFactTier
    extraction_method: str
    extraction_version: str
    status: CompanyFactStatus
    dedupe_key: str
    extracted_at: datetime
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CompanyFactExtractionSubmission:
    job_id: JobId
    research_case_id: UUID
    already_enqueued: bool


@dataclass(frozen=True, slots=True)
class CompanyFactExtractionResult:
    research_case_id: UUID
    company_id: CompanyId
    facts_created: int
    facts_updated: int
    facts_total: int


def extract_facts_job_idempotency_key(case_id: UUID) -> str:
    return f"extract_company_facts:{case_id}:{COMPANY_FACT_EXTRACTION_VERSION}"


def compute_fact_dedupe_key(
    *,
    category: CompanyFactCategory,
    subject: str,
    value: str,
    evidence_ids: tuple[EvidenceId, ...] | list[EvidenceId],
    fact_tier: CompanyFactTier = CompanyFactTier.SUBSTANTIVE,
) -> str:
    normalized_value = " ".join(value.lower().split())
    ids = ",".join(sorted(str(item) for item in evidence_ids))
    raw = f"{category.value}:{subject}:{normalized_value}:{fact_tier.value}:{ids}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def validate_extracted_fact_payload(payload: dict[str, Any]) -> ExtractedCompanyFact:
    """Validate structured AI/deterministic extractor output before persistence."""

    try:
        category = CompanyFactCategory(str(payload["category"]))
        subject = str(payload["subject"]).strip()
        value = str(payload["value"]).strip()
        origin = EvidenceOrigin(str(payload["origin"]))
        confidence = Confidence(str(payload["confidence"]))
        evidence_ids = tuple(EvidenceId(UUID(str(item))) for item in payload["evidence_ids"])
        fact_tier = CompanyFactTier(str(payload.get("fact_tier", CompanyFactTier.SUBSTANTIVE)))
    except (KeyError, ValueError, TypeError) as exc:
        raise PermanentCompanyFactError(f"Malformed extractor output: {exc}") from exc

    if not subject or not value:
        raise PermanentCompanyFactError(
            "Malformed extractor output: subject and value are required."
        )
    if not evidence_ids:
        raise PermanentCompanyFactError("Malformed extractor output: evidence_ids cannot be empty.")
    if origin is EvidenceOrigin.AI_INTERPRETATION and confidence is Confidence.HIGH:
        raise PermanentCompanyFactError(
            "AI interpretations cannot be stored with high confidence in Phase 5."
        )
    return ExtractedCompanyFact(
        category=category,
        subject=subject,
        value=value,
        evidence_ids=evidence_ids,
        origin=origin,
        confidence=confidence,
        fact_tier=fact_tier,
    )


__all__ = [
    "COMPANY_FACT_EXTRACTION_VERSION",
    "EXTRACTION_METHOD_AI",
    "EXTRACTION_METHOD_DETERMINISTIC",
    "CompanyFact",
    "CompanyFactCategory",
    "CompanyFactError",
    "CompanyFactExtractionResult",
    "CompanyFactExtractionSubmission",
    "CompanyFactStatus",
    "CompanyFactTier",
    "EvidencePageContext",
    "ExtractedCompanyFact",
    "PermanentCompanyFactError",
    "RetryableCompanyFactError",
    "compute_fact_dedupe_key",
    "extract_facts_job_idempotency_key",
    "validate_extracted_fact_payload",
]
