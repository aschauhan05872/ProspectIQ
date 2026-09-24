"""Deterministic buying-signal detection from stored evidence.

Detection answers: which SOP signals are supported by source-derived evidence?
Scoring remains in LeadScoringService / ScoringRuleset.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from re import IGNORECASE, search
from typing import Protocol

from prospectiq.domain.evidence import Evidence, EvidenceOrigin
from prospectiq.domain.signal import SIGNAL_WEIGHTS, DetectedSignal, SignalType
from prospectiq.domain.source_registry import SourceClass

DETECTION_RULESET_VERSION = "sop-lead-generation-v1"


@dataclass(frozen=True, slots=True)
class SignalRuleSpec:
    signal_type: SignalType
    description: str
    weight: int
    implemented: bool
    requires_evidence: str


SIGNAL_RULE_CATALOG: tuple[SignalRuleSpec, ...] = (
    SignalRuleSpec(
        SignalType.CHANGED_JOB_RECENTLY,
        "Prospect changed jobs recently.",
        SIGNAL_WEIGHTS[SignalType.CHANGED_JOB_RECENTLY],
        False,
        "Person-level role-change evidence from a permitted source. "
        "Not available from company websites.",
    ),
    SignalRuleSpec(
        SignalType.ACTIVE_ON_LINKEDIN,
        "Prospect is active on LinkedIn.",
        SIGNAL_WEIGHTS[SignalType.ACTIVE_ON_LINKEDIN],
        False,
        "Official LinkedIn activity evidence. LinkedIn remains human-controlled; "
        "this is not inferred from a website.",
    ),
    SignalRuleSpec(
        SignalType.TALKS_ABOUT_TECH_GROWTH,
        "Talks about technology or growth.",
        SIGNAL_WEIGHTS[SignalType.TALKS_ABOUT_TECH_GROWTH],
        False,
        "Deferred: current website text is too unstructured. Generic words like "
        "technology/innovation/growth are not enough.",
    ),
    SignalRuleSpec(
        SignalType.HIRING_TECH_ROLES,
        "Company is hiring technology roles.",
        SIGNAL_WEIGHTS[SignalType.HIRING_TECH_ROLES],
        True,
        "Careers/jobs-page evidence that states an open/hiring technology role.",
    ),
    SignalRuleSpec(
        SignalType.FUNDING_NEWS,
        "Funding or material company news.",
        SIGNAL_WEIGHTS[SignalType.FUNDING_NEWS],
        True,
        "Permitted public news/funding evidence with fact_kind=funding_announcement.",
    ),
    SignalRuleSpec(
        SignalType.EXPANSION_LAUNCH,
        "Expansion or product launch.",
        SIGNAL_WEIGHTS[SignalType.EXPANSION_LAUNCH],
        True,
        "Permitted public announcement evidence with fact_kind=expansion_announcement.",
    ),
)


FUNDING_FACT_KIND = "funding_announcement"
EXPANSION_FACT_KIND = "expansion_announcement"

NEWS_SOURCE_CLASSES = frozenset(
    {
        SourceClass.PUBLIC_NEWS,
        SourceClass.PUBLIC_FUNDING,
        SourceClass.PUBLIC_ANNOUNCEMENT,
        SourceClass.PERMITTED_SEARCH_API,
        SourceClass.LICENSED_DATA_PROVIDER,
    }
)


HIRING_CONTEXT_PATTERN = (
    r"\b(?:now hiring|we(?:['’]re| are) hiring|we(?:['’]re| are) looking for|"
    r"join our (?:team|company)|open(?:ing)?s?(?: roles?| positions?| jobs?)?|"
    r"job openings?|current openings?|vacancies|apply (?:now|today)|"
    r"this (?:position|role|job)|we have an opening|seeking (?:a|an)|"
    r"hiring (?:a|an|our)|open role)\b"
)

TECH_ROLE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("software engineer", r"\bsoftware engineers?\b"),
    ("backend engineer", r"\bback[\s-]?end engineers?\b"),
    ("frontend engineer", r"\bfront[\s-]?end engineers?\b"),
    ("full-stack engineer", r"\bfull[\s-]?stack engineers?\b"),
    ("data engineer", r"\bdata engineers?\b"),
    ("AI/ML engineer", r"\b(?:ai(?:[\s/-]?ml)?|machine learning) engineers?\b"),
    ("DevOps", r"\bdevops(?: engineers?)?\b"),
    ("QA", r"\b(?:qa engineers?|qa analysts?|quality assurance engineers?|hiring (?:a |an )?qa)\b"),
    ("UI/UX", r"\b(?:ui[\s/-]?ux|ux designers?|ui designers?|ui engineers?|ux engineers?)\b"),
    ("product manager", r"\bproduct managers?\b"),
)

LEADERSHIP_OPENING_PATTERN = (
    r"\b(?:hiring|opening for|seeking)(?: a| an| our)? "
    r"(?:cto|chief technology officer|vp(?: of)? engineering|head of engineering|"
    r"director of engineering)\b"
)


def _evidence_text(item: Evidence) -> str:
    parts = [item.fact or "", item.snippet or ""]
    phrases = item.metadata.get("observed_hiring_phrases")
    if isinstance(phrases, list):
        parts.extend(str(phrase) for phrase in phrases)
    title = item.metadata.get("title")
    if title:
        parts.append(str(title))
    return " ".join(parts)


def _is_careers_evidence(item: Evidence) -> bool:
    if item.source_class is SourceClass.CAREERS_PAGE:
        return True
    locator = (item.source_locator or "").lower()
    return any(marker in locator for marker in ("/careers", "/jobs", "/job"))


def _tech_roles_in(text: str) -> list[str]:
    found: list[str] = []
    for label, pattern in TECH_ROLE_PATTERNS:
        if search(pattern, text, IGNORECASE) and label not in found:
            found.append(label)
    if search(LEADERSHIP_OPENING_PATTERN, text, IGNORECASE):
        found.append("engineering leadership opening")
    return found


def _choose_supporting_evidence(items: Sequence[Evidence]) -> Evidence:
    for item in items:
        if _tech_roles_in(_evidence_text(item)):
            return item
    for item in items:
        if item.metadata.get("fact_kind") == "hiring_language_observed":
            return item
    return items[0]


class DetectionRule(Protocol):
    signal_type: SignalType

    def detect(self, evidence: Sequence[Evidence]) -> DetectedSignal | None: ...


def _event_key(item: Evidence) -> str:
    raw = item.metadata.get("event_key")
    if raw:
        return str(raw)
    return str(item.id)


def _is_news_evidence(item: Evidence) -> bool:
    if item.source_class in NEWS_SOURCE_CLASSES:
        return True
    kind = str(item.metadata.get("fact_kind") or "")
    return kind in {FUNDING_FACT_KIND, EXPANSION_FACT_KIND}


class FundingNewsRule:
    signal_type = SignalType.FUNDING_NEWS

    def detect(self, evidence: Sequence[Evidence]) -> DetectedSignal | None:
        candidates: list[Evidence] = []
        for item in evidence:
            if item.origin is not EvidenceOrigin.SOURCE_DERIVED:
                continue
            if not _is_news_evidence(item):
                continue
            kind = str(item.metadata.get("fact_kind") or "")
            if kind == FUNDING_FACT_KIND or item.source_class is SourceClass.PUBLIC_FUNDING:
                candidates.append(item)
        if not candidates:
            return None
        chosen = sorted(candidates, key=lambda row: row.collected_at, reverse=True)[0]
        headline = str(chosen.metadata.get("headline") or chosen.fact)
        return DetectedSignal(
            signal_type=self.signal_type,
            evidence_id=chosen.id,
            reason=f"Permitted public funding announcement: {headline[:200]}.",
        )


class ExpansionLaunchRule:
    signal_type = SignalType.EXPANSION_LAUNCH

    def detect(self, evidence: Sequence[Evidence]) -> DetectedSignal | None:
        candidates: list[Evidence] = []
        for item in evidence:
            if item.origin is not EvidenceOrigin.SOURCE_DERIVED:
                continue
            if not _is_news_evidence(item):
                continue
            kind = str(item.metadata.get("fact_kind") or "")
            if kind == EXPANSION_FACT_KIND:
                candidates.append(item)
        if not candidates:
            return None
        chosen = sorted(candidates, key=lambda row: row.collected_at, reverse=True)[0]
        headline = str(chosen.metadata.get("headline") or chosen.fact)
        return DetectedSignal(
            signal_type=self.signal_type,
            evidence_id=chosen.id,
            reason=f"Permitted public expansion/launch announcement: {headline[:200]}.",
        )


class HiringTechRolesRule:
    signal_type = SignalType.HIRING_TECH_ROLES

    def detect(self, evidence: Sequence[Evidence]) -> DetectedSignal | None:
        groups: dict[str, list[Evidence]] = defaultdict(list)
        for item in evidence:
            if item.origin is not EvidenceOrigin.SOURCE_DERIVED:
                continue
            if not _is_careers_evidence(item):
                continue
            groups[item.source_locator or str(item.id)].append(item)
        for items in groups.values():
            text = " ".join(_evidence_text(item) for item in items)
            if not search(HIRING_CONTEXT_PATTERN, text, IGNORECASE):
                continue
            roles = _tech_roles_in(text)
            if not roles:
                continue
            chosen = _choose_supporting_evidence(items)
            return DetectedSignal(
                signal_type=self.signal_type,
                evidence_id=chosen.id,
                reason=(
                    "Careers page contains active technology hiring language: "
                    + ", ".join(roles)
                    + "."
                ),
            )
        return None


class SignalDetectionService:
    """Pure function over stored evidence. No network, no LLM, no LinkedIn."""

    def __init__(self, rules: Sequence[DetectionRule] | None = None) -> None:
        default_rules: list[DetectionRule] = [
            HiringTechRolesRule(),
            FundingNewsRule(),
            ExpansionLaunchRule(),
        ]
        self._rules: list[DetectionRule] = list(rules) if rules is not None else default_rules

    def detect(self, evidence: Sequence[Evidence]) -> list[DetectedSignal]:
        usable = [item for item in evidence if item.origin is EvidenceOrigin.SOURCE_DERIVED]
        found: list[DetectedSignal] = []
        seen: set[SignalType] = set()
        for rule in self._rules:
            detected = rule.detect(usable)
            if detected is None or detected.signal_type in seen:
                continue
            seen.add(detected.signal_type)
            found.append(detected)
        return found


def deferred_signal_types() -> tuple[SignalType, ...]:
    return tuple(item.signal_type for item in SIGNAL_RULE_CATALOG if not item.implemented)
