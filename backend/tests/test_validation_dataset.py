"""Phase 9: deterministic validation dataset cases A–H."""

from __future__ import annotations

from uuid import uuid4

import pytest

from prospectiq.application.services import LeadScoringService
from prospectiq.domain.detection import SignalDetectionService
from tests.fakes import InMemoryLeadRepository
from tests.fixtures.validation_dataset import ValidationCase, build_validation_cases


@pytest.mark.parametrize("case", build_validation_cases(), ids=lambda item: item.case_id)
def test_validation_case(case: ValidationCase) -> None:
    detected = SignalDetectionService().detect(list(case.evidence))
    score = LeadScoringService(InMemoryLeadRepository()).score_signals(detected)
    assert score.total_score == case.expected_score
    assert score.classification is case.expected_classification
    assert score.is_qualified is case.expected_qualified
    assert {item.signal_type for item in detected} == set(case.expected_signal_types)


def test_case_i_idempotent_research_state() -> None:
    case = next(item for item in build_validation_cases() if item.case_id == "B")
    detector = SignalDetectionService()
    first = detector.detect(list(case.evidence))
    second = detector.detect(list(case.evidence))
    scoring = LeadScoringService(InMemoryLeadRepository())
    assert scoring.score_signals(first) == scoring.score_signals(second)


def test_case_j_tenant_isolation_on_evidence_company() -> None:
    from uuid import UUID

    from prospectiq.domain.common import TenantId

    case = next(item for item in build_validation_cases() if item.case_id == "B")
    evidence = case.evidence[0]
    assert evidence.tenant_id == TenantId(UUID("00000000-0000-0000-0000-000000000001"))
    other = TenantId(UUID("00000000-0000-0000-0000-000000000099"))
    assert evidence.tenant_id != other


def test_non_hiring_language_does_not_create_signal() -> None:
    from prospectiq.domain.common import CompanyId, Confidence, EvidenceId
    from prospectiq.domain.evidence import Evidence, EvidenceOrigin
    from prospectiq.domain.source_registry import SourceClass
    from tests.fixtures.validation_dataset import NOW, TENANT

    company = CompanyId(uuid4())
    samples = [
        "Our engineering team builds great products.",
        "Technology leadership drives our strategy.",
        "We work with software engineers across partners.",
        "We are hiring a marketing manager.",
    ]
    for text in samples:
        item = Evidence(
            id=EvidenceId(uuid4()),
            tenant_id=TENANT,
            fact=text,
            origin=EvidenceOrigin.SOURCE_DERIVED,
            source_class=SourceClass.CAREERS_PAGE,
            source_locator="https://example.test/careers",
            collected_at=NOW,
            confidence=Confidence.HIGH,
            snippet=text,
            company_id=company,
            metadata={"fact_kind": "page_content"},
        )
        detected = SignalDetectionService().detect([item])
        assert detected == []
