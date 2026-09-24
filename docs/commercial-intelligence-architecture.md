# Commercial Intelligence Architecture (V1)

**Status:** Phase 1–3 foundation in progress  
**Date:** 2026-09-24  
**Product:** Internal Sales Intelligence Platform (extends existing discovery pipeline)

---

## 1. Mission

Transform ProspectIQ from a company-discovery / lead-scoring pipeline into an internal platform that answers:

> **Why should our software company contact this company?**

With evidence-backed: business context → observed issues → opportunities → services → outreach → engagement → pitch brief.

---

## 2. Preserved Existing Architecture

The following **must not be destabilized**:

| Component | Location | Status |
|-----------|----------|--------|
| Discovery pipeline | `application/discovery.py` | Unchanged |
| Source ingestion | `application/ingestion.py` | Unchanged |
| Deterministic research | `application/research.py` | Unchanged |
| Signal detection | `domain/detection.py` | Unchanged |
| Scoring / qualification | `domain/scoring.py` | Unchanged |
| Evidence provenance | `domain/evidence.py` | Extended (new fact kinds) |
| Job queue | `infrastructure/jobs.py` | Extended (new job types) |
| Tenant isolation | `TenantScope` everywhere | Required on all new writes |

**FACT:** Buying-signal weights and qualification (≥2 distinct signals) remain unchanged.

**FACT:** `SOURCE_DERIVED` vs `AI_INTERPRETATION` distinction is preserved.

---

## 3. Layered Data Flow

```text
CSV Import (Phase 2)
  → ImportedProspect + ImportBatch
  → CompanyResolutionService (Phase 3)
      → Company + Person (reuse existing entities)
  → RESEARCH_COMPANY job (Phase 4+)
      → CompanyResearchCase
      → ResearchPage records
      → Evidence (structured fact kinds)
      → CompanyResearchSummary (Phase 6)
      → DigitalExperienceAnalysis (Phase 7)
      → OpportunityDetectionService (Phase 8)
      → ServiceMappingService (Phase 12)
      → OutreachGenerationService (Phase 15, draft-only)
      → Human approval (Phase 16)
      → Outreach tracking (Phase 17)
      → EngagementCase + PitchBrief (Phase 19–20)
```

Existing discovery flow runs **in parallel** — not replaced:

```text
DISCOVER_COMPANIES → FETCH_SOURCE → RESEARCH_LEAD → scoring
```

---

## 4. New Domain Entities (Planned)

| Entity | Phase | Purpose |
|--------|-------|---------|
| `ImportBatch` | 2 | Trace CSV file → rows |
| `ImportedProspect` | 2 | Normalized contact + company from row |
| `CompanyResolutionResult` | 3 | Domain → Company linkage |
| `CompanyResearchCase` | 4 | Bounded website research run |
| `ResearchPage` | 4 | Single fetched page metadata |
| `CompanyResearchSummary` | 6 | Evidence-linked summary |
| `Opportunity` | 8 | Classified business/tech opportunity |
| `ServiceCatalogItem` | 11 | Internal service definitions |
| `OpportunityServiceMapping` | 12 | Explainable opportunity → service |
| `OutreachSequence` / `OutreachMessage` | 15–17 | Draft outreach lifecycle |
| `EngagementCase` | 19 | Post-reply engagement |
| `PitchBrief` | 20 | Discovery/pitch document |
| `ReviewFeedback` | 37 | Human correction of AI output |

**Reuse (no duplicate):** `Company`, `Person`, `Evidence`, `Signal`, `Lead`, `Job`, `MessageDraft`, `Activity`.

---

## 5. Job Types

### Existing (unchanged handlers)
- `DISCOVER_COMPANIES`, `FETCH_SOURCE`, `FETCH_COMPANY_NEWS`, `RESEARCH_LEAD`

### New (phased rollout)
| JobType | Phase | Handler |
|---------|-------|---------|
| `IMPORT_PROSPECTS` | 2 | Parse CSV, persist prospects |
| `RESOLVE_COMPANY` | 3 | Link prospect → company/person |
| `RESEARCH_COMPANY` | 4 | Controlled multi-page research |
| `ANALYZE_RESEARCH` | 7–8 | Digital experience + opportunities |
| `MAP_SERVICES` | 12 | Opportunity → service catalog |
| `GENERATE_OUTREACH` | 15 | Draft messages (no send) |
| `GENERATE_PITCH_BRIEF` | 20 | Post-engagement brief |

All jobs: tenant-scoped, idempotent keys, `FOR UPDATE SKIP LOCKED` claiming.

---

## 6. AI Boundaries

**Interface:** `AIAnalysisProvider` (extends existing `AIGateway` pattern)

| AI may | AI must NOT |
|--------|-------------|
| Extract evidence from page text | Query arbitrary DB tables |
| Summarize company research | Send LinkedIn/email |
| Hypothesize opportunities | Modify buying score |
| Draft outreach / pitch brief | Fabricate evidence |
| Map services to opportunities | Override human approval |

**Prompt injection defense:** Website content is untrusted data in a fenced block below system instructions. See `application/ai_context.py` (Phase 27).

---

## 7. Scoring Separation

| Model | Purpose | Changes allowed |
|-------|---------|-------------------|
| `BUYING_SIGNAL_SCORE` | SOP weights 0–13+ | **None** |
| `OPPORTUNITY_FIT` | Business relevance of opportunity | New, separate |
| `OPPORTUNITY_CONFIDENCE` | Evidence strength | New, separate |

---

## 8. Security Controls

- SSRF: reuse `http_fetch.py` + `source_url.py` validation
- CSV injection: sanitize formula-prefix cells (`=`, `+`, `-`, `@`)
- Tenant isolation: all repositories scope by `tenant_id`
- PII logging: no full email/phone in logs
- LinkedIn: metadata only from import; no scraping/automation
- Outreach: `DRAFT` default; human approval required

---

## 9. Implementation Phases

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | Architecture plan (this doc) | ✅ |
| 2 | CSV import | 🔄 In progress |
| 3 | Company resolution | 🔄 In progress |
| 4–6 | Research engine + evidence + summary | Planned |
| 7–10 | Digital analysis + opportunities | Planned |
| 11–14 | Service catalog + prioritization + contacts | Planned |
| 15–18 | Outreach generation + tracking + follow-ups | Planned |
| 19–21 | Engagement + pitch + sales memory | Planned |
| 22–24 | Dashboard + detail pages | Planned |
| 25–27 | Research queue + budget + AI architecture | Planned |
| 28–31 | Deterministic vs AI + security + tenant tests | Planned |
| 32–36 | DB + jobs + API + frontend + human review | Planned |
| 37–55 | Quality gates + docs + E2E validation | Planned |

---

## 10. API Conventions (New Routes)

Following existing thin-route pattern in `api/routes/`:

| Method | Path | Phase |
|--------|------|-------|
| POST | `/prospects/import` | 2 |
| GET | `/prospects/import/{batch_id}` | 2 |
| GET | `/prospects` | 2 |
| GET | `/prospects/{id}` | 2 |
| POST | `/prospects/import/{batch_id}/resolve` | 3 |
| POST | `/companies/{id}/research` | 4 |
| GET | `/companies/{id}/research` | 4 |
| GET | `/companies/{id}/opportunities` | 8 |
| GET | `/opportunities/{id}` | 8 |
| POST | `/opportunities/{id}/generate-outreach` | 15 |
| POST | `/outreach/{id}/approve` | 16 |
| POST | `/engagements/{id}/generate-pitch-brief` | 20 |

---

## 11. Deferred (V1 Scope Control)

- SaaS billing / multi-tenant auth UI
- LinkedIn automation
- Automated email campaigns
- MCP server / marketplace
- Microservices
- Vector database
- Autonomous browser agents
- Predictive forecasting AI

---

*See also: `docs/discovery-strategy-review.md`, `docs/company-discovery.md`*
