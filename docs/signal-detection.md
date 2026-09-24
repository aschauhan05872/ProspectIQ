# Deterministic buying-signal detection (V0)

This workstream detects SOP buying signals from **already stored evidence** and scores the company lead with the existing `LeadScoringService`. It does not fetch new sources, call an LLM, or touch LinkedIn.

## Flow

```text
POST /research/company { "company_id": "..." }
        ↓
Enqueue RESEARCH_LEAD (Postgres job, tenant-scoped)
        ↓
Load stored Evidence for that company
        ↓
SignalDetectionService (deterministic, no I/O)
        ↓
Upsert Signal (one current row per tenant + company + type)
        ↓
LeadScoringService.apply_to_lead
        ↓
Raw score + HOT/WARM/COLD + qualification
```

`GET /research/company/{company_id}` returns the last persisted signals and a deterministic rescore.

Detection answers **which signals exist**. Scoring answers **what the score is**. Those responsibilities stay separate.

## Supported now

| Signal | Weight | When it fires |
|---|---|---|
| `HIRING_TECH_ROLES` | +3 | Careers/jobs evidence that has **open/hiring language** and a documented tech role |
| `FUNDING_NEWS` | +3 | Permitted public news/funding evidence with `fact_kind=funding_announcement` (not generic website copy) |
| `EXPANSION_LAUNCH` | +2 | Permitted public announcement evidence with `fact_kind=expansion_announcement` |

Recognized roles follow the Lead Generation SOP list: Software Engineer, Backend Engineer, Frontend Engineer, Full Stack Engineer, Data Engineer, AI/ML Engineer, DevOps, QA, UI/UX, Product Manager.

Hiring context is required. Examples that do **not** fire:

- "we have software engineers"
- "engineering leadership" with no opening
- "we are hiring a marketing manager"
- generic website words such as technology / innovation / growth
- `fact_kind=hiring_language_observed` alone, unless the careers page also has hiring context plus a tech role (page content and hiring observations from the same locator are read together)

The signal stores:

- supporting `evidence_id`
- normalized source locator on that evidence
- evidence `collected_at`
- a human-readable `reason`

## Intentionally deferred

These SOP types exist in the catalog and weight table. They are **not** generated from company websites or careers pages:

| Signal | Weight | Why it is deferred |
|---|---|---|
| `CHANGED_JOB_RECENTLY` | +2 | Needs person-level role-change evidence from a permitted person-level source |
| `ACTIVE_ON_LINKEDIN` | +1 | LinkedIn stays human-controlled; no scrape or activity inference |
| `TALKS_ABOUT_TECH_GROWTH` | +2 | Current website text is too unstructured; generic adjectives are not enough |

Absence of evidence is not treated as evidence of absence. Future permitted providers add `SOURCE_DERIVED` evidence; new detection rules can then be enabled independently without changing scoring weights.

## Scoring and qualification

`LeadScoringService` / `ScoringRuleset` (`sop-lead-generation-v1`) remains the only scoring implementation.

- Raw score is the sum of distinct SOP weights. It is **not** clamped to 10.
- 0–2 Cold, 3–5 Warm, 6+ Hot
- Qualified only when **2+ distinct buying signals** are present

One hiring signal therefore scores 3, classifies Warm, and is **not** qualified.

## Idempotency and history

- Repeated detection against the same company + signal type upserts one current `Signal` row.
- Unchanged evidence produces the same job idempotency key (`research_lead:{company_id}:{fingerprint}`).
- Evidence rows are not deleted when a later fetch differs. The current signal may point at newer supporting evidence; older evidence remains.

## Jobs

- Type: existing `RESEARCH_LEAD`
- Tenant-scoped, retryable, observable through the existing Postgres queue
- No second queue

## What this does not do

No LinkedIn automation, crawling, AI scoring, extra data providers, SaaS, MCP, or dashboard.
