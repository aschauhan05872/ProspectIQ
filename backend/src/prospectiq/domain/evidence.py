"""Source-derived facts vs AI interpretations.

Important research facts must retain: what was detected, which source produced
it, when it was collected, confidence, locator/reference metadata, and the
company/person/lead it belongs to. AI must not fabricate evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from prospectiq.domain.common import (
    CompanyId,
    Confidence,
    EvidenceId,
    LeadId,
    PersonId,
    TenantId,
)
from prospectiq.domain.source_registry import SourceClass


class EvidenceOrigin(StrEnum):
    SOURCE_DERIVED = "source_derived"
    DISCOVERY_RECORD = "discovery_record"
    AI_INTERPRETATION = "ai_interpretation"


class EvidenceError(Exception):
    """Raised when evidence provenance rules are violated."""


@dataclass(slots=True)
class Evidence:
    id: EvidenceId
    tenant_id: TenantId
    fact: str
    origin: EvidenceOrigin
    source_class: SourceClass | None
    source_locator: str | None
    collected_at: datetime
    confidence: Confidence
    snippet: str | None
    company_id: CompanyId | None = None
    person_id: PersonId | None = None
    lead_id: LeadId | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.origin in {EvidenceOrigin.SOURCE_DERIVED, EvidenceOrigin.DISCOVERY_RECORD}:
            if self.source_class is None or not self.source_locator:
                raise EvidenceError(
                    "Source-derived and discovery evidence require source_class and source_locator."
                )
        if self.origin is EvidenceOrigin.AI_INTERPRETATION and self.source_class is not None:
            raise EvidenceError(
                "AI interpretations cannot be stored as if they came from an external source."
            )


def assert_claims_bound_to_known_evidence(
    claimed_evidence_ids: list[EvidenceId],
    known_evidence_ids: set[EvidenceId],
) -> None:
    unknown = [str(item) for item in claimed_evidence_ids if item not in known_evidence_ids]
    if unknown:
        raise EvidenceError(
            "AI output referenced unknown evidence IDs and cannot be treated as fact: "
            + ", ".join(unknown)
        )
