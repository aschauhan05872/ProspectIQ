"""Deterministic lead scoring from the Lead Generation SOP.

An LLM must not assign the final score. This ruleset is versioned so SOP
weight changes do not require rewriting application services.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from prospectiq.domain.signal import (
    BUYING_SIGNAL_TYPES,
    SIGNAL_WEIGHTS,
    DetectedSignal,
    SignalType,
)

SCORING_RULESET_VERSION = "sop-lead-generation-v1"

MIN_BUYING_SIGNALS_FOR_QUALIFICATION = 2


class LeadClassification(StrEnum):
    COLD = "cold"
    WARM = "warm"
    HOT = "hot"


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    signal_type: SignalType
    weight: int
    evidence_id: str


@dataclass(frozen=True, slots=True)
class LeadScoreResult:
    total_score: int
    classification: LeadClassification
    is_qualified: bool
    distinct_buying_signals: int
    breakdown: tuple[ScoreBreakdown, ...]
    ruleset_version: str = SCORING_RULESET_VERSION


def classify_score(total_score: int) -> LeadClassification:
    """SOP bands: 0–2 Cold, 3–5 Warm, 6–10 HOT. Scores above 10 remain HOT."""

    if total_score <= 2:
        return LeadClassification.COLD
    if total_score <= 5:
        return LeadClassification.WARM
    return LeadClassification.HOT


def is_qualified(distinct_buying_signal_count: int) -> bool:
    return distinct_buying_signal_count >= MIN_BUYING_SIGNALS_FOR_QUALIFICATION


class ScoringRuleset:
    version = SCORING_RULESET_VERSION
    weights = SIGNAL_WEIGHTS

    def score(self, signals: list[DetectedSignal]) -> LeadScoreResult:
        seen: set[SignalType] = set()
        breakdown: list[ScoreBreakdown] = []
        total = 0
        for item in signals:
            if item.signal_type in seen:
                continue
            if item.signal_type not in self.weights:
                continue
            seen.add(item.signal_type)
            weight = self.weights[item.signal_type]
            total += weight
            breakdown.append(
                ScoreBreakdown(
                    signal_type=item.signal_type,
                    weight=weight,
                    evidence_id=str(item.evidence_id),
                )
            )
        buying = len(seen & BUYING_SIGNAL_TYPES)
        return LeadScoreResult(
            total_score=total,
            classification=classify_score(total),
            is_qualified=is_qualified(buying),
            distinct_buying_signals=buying,
            breakdown=tuple(breakdown),
            ruleset_version=self.version,
        )


DEFAULT_SCORING_RULESET = ScoringRuleset()
