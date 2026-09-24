from __future__ import annotations

from uuid import uuid4

from prospectiq.domain.common import EvidenceId
from prospectiq.domain.scoring import (
    DEFAULT_SCORING_RULESET,
    LeadClassification,
    classify_score,
    is_qualified,
)
from prospectiq.domain.signal import DetectedSignal, SignalType


def _sig(signal_type: SignalType) -> DetectedSignal:
    return DetectedSignal(signal_type=signal_type, evidence_id=EvidenceId(uuid4()))


def test_sop_weights_and_hot_classification() -> None:
    result = DEFAULT_SCORING_RULESET.score(
        [
            _sig(SignalType.CHANGED_JOB_RECENTLY),
            _sig(SignalType.ACTIVE_ON_LINKEDIN),
            _sig(SignalType.TALKS_ABOUT_TECH_GROWTH),
            _sig(SignalType.HIRING_TECH_ROLES),
            _sig(SignalType.FUNDING_NEWS),
            _sig(SignalType.EXPANSION_LAUNCH),
        ]
    )
    assert result.total_score == 13
    assert result.classification is LeadClassification.HOT
    assert result.is_qualified is True
    assert result.distinct_buying_signals == 6
    assert result.ruleset_version == "sop-lead-generation-v1"


def test_duplicate_signals_are_not_double_counted() -> None:
    result = DEFAULT_SCORING_RULESET.score(
        [
            _sig(SignalType.HIRING_TECH_ROLES),
            _sig(SignalType.HIRING_TECH_ROLES),
        ]
    )
    assert result.total_score == 3
    assert result.classification is LeadClassification.WARM
    assert result.distinct_buying_signals == 1
    assert result.is_qualified is False


def test_classification_bands_match_sop() -> None:
    assert classify_score(0) is LeadClassification.COLD
    assert classify_score(2) is LeadClassification.COLD
    assert classify_score(3) is LeadClassification.WARM
    assert classify_score(5) is LeadClassification.WARM
    assert classify_score(6) is LeadClassification.HOT
    assert classify_score(10) is LeadClassification.HOT
    assert classify_score(13) is LeadClassification.HOT


def test_qualification_requires_two_buying_signals() -> None:
    assert is_qualified(1) is False
    assert is_qualified(2) is True
    one = DEFAULT_SCORING_RULESET.score([_sig(SignalType.FUNDING_NEWS)])
    assert one.is_qualified is False
    two = DEFAULT_SCORING_RULESET.score(
        [_sig(SignalType.FUNDING_NEWS), _sig(SignalType.EXPANSION_LAUNCH)]
    )
    assert two.total_score == 5
    assert two.classification is LeadClassification.WARM
    assert two.is_qualified is True
