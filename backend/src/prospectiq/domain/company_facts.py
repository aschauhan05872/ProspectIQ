"""Structured company facts derived from research evidence (Phase 5).

Facts are traceable intelligence — not opportunities, scores, or recommendations.
"""

from __future__ import annotations

import hashlib
import re
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

COMPANY_FACT_EXTRACTION_VERSION = "company-fact-extraction-v1"
EXTRACTION_METHOD_DETERMINISTIC = "deterministic_v1"
EXTRACTION_METHOD_AI = "ai_v1"


class CompanyFactCategory(StrEnum):
    BUSINESS = "business"
    GEOGRAPHY = "geography"
    COMMERCIAL = "commercial"
    ACTIVITY = "activity"
    DIGITAL = "digital"
    ORGANIZATION = "organization"


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

    def dedupe_key(self) -> str:
        return compute_fact_dedupe_key(
            category=self.category,
            subject=self.subject,
            value=self.value,
            evidence_ids=self.evidence_ids,
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
) -> str:
    normalized_value = " ".join(value.lower().split())
    ids = ",".join(sorted(str(item) for item in evidence_ids))
    raw = f"{category.value}:{subject}:{normalized_value}:{ids}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
_PHONE_PATTERN = re.compile(
    r"(?<!\w)(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)|\d{2,4})[\s.-]?\d{3,4}[\s.-]?\d{3,4}(?:\s*(?:ext|x)\.?\s*\d+)?(?!\w)"
)
_LOCATION_PATTERN = re.compile(
    r"\b(?:based in|located in|headquarters in|office in|offices in)\s+"
    r"([A-Z][A-Za-z0-9\s,.-]{2,80})",
    re.IGNORECASE,
)
_FORM_KEYWORDS = (
    "contact form",
    "request a demo",
    "book a demo",
    "schedule a call",
    "get in touch",
    "send us a message",
)
_OFFERING_PAGE_TYPES = frozenset({"services", "products", "solutions", "platform"})
_CONTENT_PAGE_TYPES = frozenset({"news", "blog"})


def extract_deterministic_facts(context: EvidencePageContext) -> list[ExtractedCompanyFact]:
    """Extract explicit, structured facts from one research page evidence context."""

    facts: list[ExtractedCompanyFact] = []
    evidence_id = context.evidence_id
    page_type = context.page_type
    locator = context.source_locator
    text = context.text
    title = (context.title or "").strip()

    facts.append(
        ExtractedCompanyFact(
            category=CompanyFactCategory.DIGITAL,
            subject="page_classification",
            value=f"{page_type} page at {locator}",
            evidence_ids=(evidence_id,),
            origin=EvidenceOrigin.SOURCE_DERIVED,
            confidence=Confidence.HIGH,
        )
    )

    if title:
        facts.append(
            ExtractedCompanyFact(
                category=CompanyFactCategory.BUSINESS,
                subject="page_title",
                value=title,
                evidence_ids=(evidence_id,),
                origin=EvidenceOrigin.SOURCE_DERIVED,
                confidence=Confidence.HIGH,
            )
        )

    if page_type in _OFFERING_PAGE_TYPES and title:
        facts.append(
            ExtractedCompanyFact(
                category=CompanyFactCategory.BUSINESS,
                subject="stated_offering",
                value=title,
                evidence_ids=(evidence_id,),
                origin=EvidenceOrigin.SOURCE_DERIVED,
                confidence=Confidence.MEDIUM,
            )
        )

    if page_type == "contact":
        facts.append(
            ExtractedCompanyFact(
                category=CompanyFactCategory.COMMERCIAL,
                subject="contact_page",
                value=locator,
                evidence_ids=(evidence_id,),
                origin=EvidenceOrigin.SOURCE_DERIVED,
                confidence=Confidence.HIGH,
            )
        )

    if page_type in _CONTENT_PAGE_TYPES:
        facts.append(
            ExtractedCompanyFact(
                category=CompanyFactCategory.ACTIVITY,
                subject="content_channel",
                value=page_type,
                evidence_ids=(evidence_id,),
                origin=EvidenceOrigin.SOURCE_DERIVED,
                confidence=Confidence.HIGH,
            )
        )

    lowered = text.lower()
    for keyword in _FORM_KEYWORDS:
        if keyword in lowered:
            facts.append(
                ExtractedCompanyFact(
                    category=CompanyFactCategory.DIGITAL,
                    subject="contact_mechanism",
                    value=keyword,
                    evidence_ids=(evidence_id,),
                    origin=EvidenceOrigin.SOURCE_DERIVED,
                    confidence=Confidence.MEDIUM,
                )
            )
            break

    for match in _EMAIL_PATTERN.findall(text):
        facts.append(
            ExtractedCompanyFact(
                category=CompanyFactCategory.DIGITAL,
                subject="email_address",
                value=match,
                evidence_ids=(evidence_id,),
                origin=EvidenceOrigin.SOURCE_DERIVED,
                confidence=Confidence.HIGH,
            )
        )

    for match in _PHONE_PATTERN.findall(text):
        normalized_phone = " ".join(match.split())
        facts.append(
            ExtractedCompanyFact(
                category=CompanyFactCategory.DIGITAL,
                subject="phone_number",
                value=normalized_phone,
                evidence_ids=(evidence_id,),
                origin=EvidenceOrigin.SOURCE_DERIVED,
                confidence=Confidence.MEDIUM,
            )
        )

    for match in _LOCATION_PATTERN.finditer(text):
        location = match.group(1).strip(" .,")
        if location:
            facts.append(
                ExtractedCompanyFact(
                    category=CompanyFactCategory.GEOGRAPHY,
                    subject="operating_location",
                    value=location,
                    evidence_ids=(evidence_id,),
                    origin=EvidenceOrigin.SOURCE_DERIVED,
                    confidence=Confidence.MEDIUM,
                )
            )

    return facts


def validate_extracted_fact_payload(payload: dict[str, Any]) -> ExtractedCompanyFact:
    """Validate structured AI/deterministic extractor output before persistence."""

    try:
        category = CompanyFactCategory(str(payload["category"]))
        subject = str(payload["subject"]).strip()
        value = str(payload["value"]).strip()
        origin = EvidenceOrigin(str(payload["origin"]))
        confidence = Confidence(str(payload["confidence"]))
        evidence_ids = tuple(EvidenceId(UUID(str(item))) for item in payload["evidence_ids"])
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
    )
