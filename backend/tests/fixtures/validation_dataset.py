"""Deterministic validation cases A–J for signal/scoring behavior."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from prospectiq.domain.common import CompanyId, Confidence, EvidenceId, TenantId
from prospectiq.domain.detection import EXPANSION_FACT_KIND, FUNDING_FACT_KIND
from prospectiq.domain.evidence import Evidence, EvidenceOrigin
from prospectiq.domain.scoring import LeadClassification
from prospectiq.domain.signal import SignalType
from prospectiq.domain.source_registry import SourceClass

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
TENANT = TenantId(UUID("00000000-0000-0000-0000-000000000001"))


@dataclass(frozen=True, slots=True)
class ValidationCase:
    case_id: str
    description: str
    evidence: tuple[Evidence, ...]
    expected_score: int
    expected_classification: LeadClassification
    expected_qualified: bool
    expected_signal_types: tuple[SignalType, ...]


def _hiring_evidence(company_id: CompanyId) -> Evidence:
    return Evidence(
        id=EvidenceId(uuid4()),
        tenant_id=TENANT,
        fact="We are hiring a Software Engineer.",
        origin=EvidenceOrigin.SOURCE_DERIVED,
        source_class=SourceClass.CAREERS_PAGE,
        source_locator="https://example.test/careers",
        collected_at=NOW,
        confidence=Confidence.HIGH,
        snippet="hiring",
        company_id=company_id,
        metadata={"fact_kind": "page_content"},
    )


def _funding_evidence(company_id: CompanyId, *, headline: str, event_suffix: str) -> Evidence:
    return Evidence(
        id=EvidenceId(uuid4()),
        tenant_id=TENANT,
        fact=headline,
        origin=EvidenceOrigin.SOURCE_DERIVED,
        source_class=SourceClass.PUBLIC_FUNDING,
        source_locator=f"https://news.test/funding/{event_suffix}",
        collected_at=NOW,
        confidence=Confidence.MEDIUM,
        snippet=headline,
        company_id=company_id,
        metadata={
            "fact_kind": FUNDING_FACT_KIND,
            "headline": headline,
            "event_key": event_suffix,
        },
    )


def _expansion_evidence(company_id: CompanyId, *, headline: str, event_suffix: str) -> Evidence:
    return Evidence(
        id=EvidenceId(uuid4()),
        tenant_id=TENANT,
        fact=headline,
        origin=EvidenceOrigin.SOURCE_DERIVED,
        source_class=SourceClass.PUBLIC_ANNOUNCEMENT,
        source_locator=f"https://news.test/expansion/{event_suffix}",
        collected_at=NOW,
        confidence=Confidence.MEDIUM,
        snippet=headline,
        company_id=company_id,
        metadata={
            "fact_kind": EXPANSION_FACT_KIND,
            "headline": headline,
            "event_key": event_suffix,
        },
    )


def build_validation_cases() -> list[ValidationCase]:
    company = CompanyId(uuid4())
    return [
        ValidationCase("A", "No buying signals", (), 0, LeadClassification.COLD, False, ()),
        ValidationCase(
            "B",
            "Hiring only",
            (_hiring_evidence(company),),
            3,
            LeadClassification.WARM,
            False,
            (SignalType.HIRING_TECH_ROLES,),
        ),
        ValidationCase(
            "C",
            "Funding only",
            (_funding_evidence(company, headline="Raised Series B funding", event_suffix="b"),),
            3,
            LeadClassification.WARM,
            False,
            (SignalType.FUNDING_NEWS,),
        ),
        ValidationCase(
            "D",
            "Hiring + Funding",
            (
                _hiring_evidence(company),
                _funding_evidence(company, headline="Raised Series B funding", event_suffix="b"),
            ),
            6,
            LeadClassification.HOT,
            True,
            (SignalType.HIRING_TECH_ROLES, SignalType.FUNDING_NEWS),
        ),
        ValidationCase(
            "E",
            "Hiring + Expansion",
            (
                _hiring_evidence(company),
                _expansion_evidence(
                    company, headline="Company launches new product line", event_suffix="launch"
                ),
            ),
            5,
            LeadClassification.WARM,
            True,
            (SignalType.HIRING_TECH_ROLES, SignalType.EXPANSION_LAUNCH),
        ),
        ValidationCase(
            "F",
            "Funding + Expansion",
            (
                _funding_evidence(company, headline="Raised seed funding", event_suffix="seed"),
                _expansion_evidence(
                    company, headline="Expansion into European market", event_suffix="eu"
                ),
            ),
            5,
            LeadClassification.WARM,
            True,
            (SignalType.FUNDING_NEWS, SignalType.EXPANSION_LAUNCH),
        ),
        ValidationCase(
            "G",
            "All three signals",
            (
                _hiring_evidence(company),
                _funding_evidence(company, headline="Raised Series A funding", event_suffix="a"),
                _expansion_evidence(
                    company, headline="Product launch announced", event_suffix="prod"
                ),
            ),
            8,
            LeadClassification.HOT,
            True,
            (
                SignalType.HIRING_TECH_ROLES,
                SignalType.FUNDING_NEWS,
                SignalType.EXPANSION_LAUNCH,
            ),
        ),
        ValidationCase(
            "H",
            "Duplicate funding evidence for one event",
            (
                _funding_evidence(company, headline="Raised Series B funding", event_suffix="dup"),
                _funding_evidence(
                    company,
                    headline="Raised Series B funding",
                    event_suffix="dup",
                ),
            ),
            3,
            LeadClassification.WARM,
            False,
            (SignalType.FUNDING_NEWS,),
        ),
    ]
