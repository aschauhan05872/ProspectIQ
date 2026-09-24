# Source document authority

Use these documents in this order. Do not silently replace, simplify, or reinterpret their rules.

1. **Technical Design Document v0.1** — architecture, boundaries, stack, data, security, observability, SaaS/MCP direction. Copy in-repo: [ProspectIQ_Technical_Design_Document_v0.1.md](./ProspectIQ_Technical_Design_Document_v0.1.md)
2. **LinkedIn Sales Navigator Lead Generation SOP** — ICP, company filters, decision-maker targeting, buying signals, qualification, scoring, research workflow.
3. **SOP: LinkedIn Outreach & Follow-Up Strategy** — outreach lifecycle, personalization, messaging, connection/follow-up, timing, qualification conversation, strategy-sheet tracking.

External originals used during bootstrap (not committed as binaries):

- `C:\Users\LOQ\Downloads\ProspectIQ_Technical_Design_Document_v0.1.md`
- `C:\Users\LOQ\Downloads\ProspectIQ_Technical_Design_Document_v0.1.docx`
- `C:\Users\LOQ\Downloads\LinkedIn_Sales_Navigator_SOP.docx.pdf`
- `C:\Users\LOQ\Downloads\SOP_ SalesNavigator-LinkedIn Outreach & Follow-Up Strategy.pdf`

## Documented conflicts / ambiguities

These are recorded rather than “fixed” by inventing business rules.

1. **Company size upper bound.** The TDD and Sales Navigator company filter are **11–1,000 employees**. The lead-generation SOP also says avoid 1–10 and 10,000+. Implementation uses **11–1,000**.
2. **HOT band vs theoretical max.** Classification is documented as 0–2 Cold, 3–5 Warm, 6–10 HOT. Sum of all SOP weights is 13. Implementation treats **6+ as HOT** (priority outreach) and still records the raw score.
3. **Discovery filters vs scoring weights.** Sales Navigator filters (posted in last 30 days, job change in 90 days, 1–3 years at company) are intake filters. Scoring uses the six weighted signals. They are modeled separately.
4. **Time-in-role research notes.** Research SOP: 0–12 months is a strong signal, 1–2 years a good signal. These are research notes, not extra score weights. Only “Changed job recently = +2” is scored.
5. **Message templates.** The lead-generation SOP includes short templates; the outreach SOP is the lifecycle/messaging source of truth. Draft generation should follow the outreach SOP framework.
6. **TDD Markdown vs DOCX.** Bootstrap used the Markdown v0.1 text (complete 21 sections). The DOCX is treated as the same v0.1 document. If they diverge later, the TDD remains architecture source of truth and the conflict must be recorded before a large change.

## Library choices finalized during implementation

The TDD allows exact libraries to be chosen in-repo:

| Concern | Choice | Why |
|---|---|---|
| API | FastAPI + Uvicorn | Specified stack; async; thin presentation over application services |
| ORM / migrations | SQLAlchemy 2.0 async + Alembic | Tenant-scoped mapping without leaking into domain |
| Settings | Pydantic Settings | Env-based secrets, typed config |
| Logging | structlog | Request/job/tenant IDs as structured fields |
| HTTP clients | httpx | Adapter-only outbound calls |
| Durable jobs | PostgreSQL job table + `SKIP LOCKED` | Durability, idempotency, horizontal workers |
| Notify channel | Redis (optional) | Matches TDD “Redis + durable queue” without making Redis the source of truth |
| UI workspace | Next.js (TypeScript) | Specified stack; not the intelligence engine |
| Tests | pytest | Domain rules run with no I/O |
