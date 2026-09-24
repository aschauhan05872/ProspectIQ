from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from prospectiq.application.ports import AIRequest, AIResponse
from prospectiq.application.services import BoundedAIService
from prospectiq.domain.common import Confidence, EvidenceId, TenantId, TenantScope
from prospectiq.domain.evidence import (
    Evidence,
    EvidenceError,
    EvidenceOrigin,
    assert_claims_bound_to_known_evidence,
)
from prospectiq.domain.source_registry import SourceClass


def test_source_derived_evidence_requires_provenance() -> None:
    with pytest.raises(EvidenceError):
        Evidence(
            id=EvidenceId(uuid4()),
            tenant_id=TenantId(uuid4()),
            fact="Hiring software engineers",
            origin=EvidenceOrigin.SOURCE_DERIVED,
            source_class=None,
            source_locator=None,
            collected_at=datetime.now(UTC),
            confidence=Confidence.HIGH,
            snippet=None,
        )


def test_ai_interpretation_cannot_claim_a_source_class() -> None:
    with pytest.raises(EvidenceError):
        Evidence(
            id=EvidenceId(uuid4()),
            tenant_id=TenantId(uuid4()),
            fact="They probably need outsourcing",
            origin=EvidenceOrigin.AI_INTERPRETATION,
            source_class=SourceClass.PUBLIC_NEWS,
            source_locator="https://example.test",
            collected_at=datetime.now(UTC),
            confidence=Confidence.LOW,
            snippet=None,
        )


def test_unknown_evidence_ids_are_rejected() -> None:
    known = EvidenceId(uuid4())
    fake = EvidenceId(uuid4())
    with pytest.raises(EvidenceError):
        assert_claims_bound_to_known_evidence([fake], {known})


class _FakeGateway:
    def __init__(self, cited: list[str]) -> None:
        self.cited = cited

    async def complete(self, request: AIRequest) -> AIResponse:
        return AIResponse("research_summary", {"summary": "ok"}, self.cited)


@pytest.mark.asyncio
async def test_bounded_ai_rejects_fabricated_evidence_and_cross_tenant() -> None:
    known = EvidenceId(uuid4())
    scope = TenantScope(tenant_id=TenantId(UUID("00000000-0000-0000-0000-000000000001")))
    service = BoundedAIService(_FakeGateway([str(uuid4())]))
    with pytest.raises(EvidenceError):
        await service.run(
            scope=scope,
            operation="research_summary",
            authorized_context={"lead": "x"},
            allowed_evidence_ids=[known],
        )
    with pytest.raises(EvidenceError):
        await service.run(
            scope=scope,
            operation="research_summary",
            authorized_context={"tenant_id": "00000000-0000-0000-0000-000000000099"},
            allowed_evidence_ids=[known],
        )
