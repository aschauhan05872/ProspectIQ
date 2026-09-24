"""Deterministic extraction from bounded research evidence contexts."""

from __future__ import annotations

from prospectiq.domain.company_facts import (
    EXTRACTION_METHOD_DETERMINISTIC,
    EvidencePageContext,
    ExtractedCompanyFact,
    extract_deterministic_facts,
)


class DeterministicEvidenceFactExtractor:
    """Extract explicit facts without LLM involvement."""

    extraction_method = EXTRACTION_METHOD_DETERMINISTIC

    def extract(self, contexts: list[EvidencePageContext]) -> list[ExtractedCompanyFact]:
        facts: list[ExtractedCompanyFact] = []
        seen: set[str] = set()
        for context in contexts:
            for fact in extract_deterministic_facts(context):
                key = fact.dedupe_key()
                if key in seen:
                    continue
                seen.add(key)
                facts.append(fact)
        return facts
