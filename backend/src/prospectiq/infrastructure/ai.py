"""AI gateway. The model never gets a database session or unrestricted tools."""

from __future__ import annotations

from prospectiq.application.ports import AIRequest, AIResponse
from prospectiq.domain.evidence import EvidenceError


class UnconfiguredAIGateway:
    """Default V0 gateway. Real providers are plugged in behind this interface."""

    async def complete(self, request: AIRequest) -> AIResponse:
        if request.operation not in {
            "research_summary",
            "signal_extraction_assist",
            "outreach_draft",
        }:
            raise EvidenceError(f"Unsupported AI operation: {request.operation}")
        return AIResponse(
            operation=request.operation,
            content={
                "status": "unconfigured",
                "message": "No AI provider is configured. Domain scoring does not require AI.",
            },
            cited_evidence_ids=[],
        )
