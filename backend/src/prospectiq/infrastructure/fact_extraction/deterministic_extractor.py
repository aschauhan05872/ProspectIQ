"""Deterministic extraction from bounded research evidence contexts."""

from __future__ import annotations

from collections import Counter

from prospectiq.domain.company_facts import (
    EXTRACTION_METHOD_DETERMINISTIC,
    EvidencePageContext,
    ExtractedCompanyFact,
)
from prospectiq.domain.fact_extraction_rules import (
    ExtractionBatchState,
    extract_deterministic_facts,
)


class DeterministicEvidenceFactExtractor:
    """Extract explicit facts without LLM involvement."""

    extraction_method = EXTRACTION_METHOD_DETERMINISTIC

    def extract(self, contexts: list[EvidencePageContext]) -> list[ExtractedCompanyFact]:
        facts: list[ExtractedCompanyFact] = []
        seen: set[str] = set()
        batch = ExtractionBatchState(title_counts=Counter())
        for context in contexts:
            for fact in extract_deterministic_facts(context, batch=batch):
                key = fact.dedupe_key()
                if key in seen:
                    continue
                seen.add(key)
                facts.append(fact)
        return facts
