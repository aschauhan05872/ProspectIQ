# Structured Evidence Analysis (Phase 5)

**Status:** Implemented (v2 extraction remediation)  
**Date:** 2026-09-24

---

## Objective

Transform Phase 4 `SOURCE_DERIVED` research evidence into structured, traceable company facts.

```text
research evidence (SOURCE_DERIVED)
        ↓
structured company facts
        ↓
fact → evidence references
```

Phase 5 does **not** generate opportunities, recommendations, scores, outreach, or digital-experience analysis.

---

## Domain Model

| Entity | Location | Purpose |
|--------|----------|---------|
| `CompanyFact` | `domain/company_facts.py` | Structured fact with provenance |
| `CompanyFactCategory` | same | `business`, `geography`, `commercial`, `activity`, `digital`, `organization` |
| `EvidencePageContext` | same | Bounded extractor input |
| `ExtractedCompanyFact` | same | Pre-persistence extraction result |

Each fact stores:

- category, subject, value
- `evidence_ids` (references to existing `Evidence` rows — no duplicated page content)
- `origin` (`source_derived` or `ai_interpretation`)
- `fact_tier` (`substantive` vs `metadata` — page classification/titles are metadata)
- confidence, extraction method/version, status
- `dedupe_key` for idempotent upserts

---

## Extraction Architecture

| Component | Location |
|-----------|----------|
| `EvidenceFactExtractor` port | `application/ports.py` |
| `DeterministicEvidenceFactExtractor` | `infrastructure/fact_extraction/deterministic_extractor.py` |
| `AIEvidenceFactExtractor` (optional) | `infrastructure/fact_extraction/ai_extractor.py` |
| `CompanyFactExtractionService` | `application/company_fact_extraction.py` |

Deterministic extraction handles explicit evidence: office locations, organization scale (offices/partners counts), activity/events/blog signals, contact emails/phones, stated markets, and title quality filtering. Page classification/titles are stored as `metadata` tier facts.

AI extraction remains behind the existing `AIGateway` boundary with:

- fenced untrusted source content
- structured output validation
- evidence ID binding checks
- rejection of adversarial or opportunity-like claims

---

## Job Lifecycle

| JobType | Idempotency key |
|---------|-----------------|
| `EXTRACT_COMPANY_FACTS` | `extract_company_facts:{case_id}:company-fact-extraction-v2` |

Triggered via API (does not modify Phase 4 research behavior). Worker handler in `worker/main.py`.

---

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/research/cases/{case_id}/extract-facts` | Enqueue extraction (202) |
| GET | `/companies/{company_id}/facts` | List active facts for company |
| GET | `/research/cases/{case_id}/facts` | List active facts for research case |

---

## Database

Migrations: `20260924_0008_company_facts.py`, `20260924_0009_company_fact_tier.py`

Table: `company_facts` with unique `(tenant_id, research_case_id, dedupe_key)` and `fact_tier` column.

---

## Security

- Website text is untrusted data — never executed as instructions
- Unsupported information remains absent rather than guessed
- AI interpretations cannot be stored with high confidence in Phase 5
- Tenant isolation enforced on all reads/writes

---

## Testing

- Unit: `tests/test_company_facts.py`
- Integration: `tests/integration/test_company_facts.py`
