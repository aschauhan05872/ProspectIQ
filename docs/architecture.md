# ProspectIQ Architecture (V0 Foundation)

This document explains the repository structure and engineering boundaries. It does **not** replace the Technical Design Document.

Canonical product/architecture source: [ProspectIQ Technical Design Document v0.1](./ProspectIQ_Technical_Design_Document_v0.1.md)

Business-rule sources:

- LinkedIn Sales Navigator Lead Generation SOP — ICP, filters, qualification, scoring
- SOP: LinkedIn Outreach & Follow-Up Strategy — outreach lifecycle, messaging, follow-up timing, strategy-sheet tracking

## Why this architecture

ProspectIQ is a **modular monolith**: one deployable backend, hard module boundaries, and an application layer that the Web UI, HTTP API, and a future MCP server can all call. That avoids rewriting the intelligence engine when Phase 2 (SaaS) and Phase 3 (MCP) arrive, without paying for microservices in V0.

Dependency direction is inward:

```text
UI / API / future MCP
        ↓
 Application services (use cases)
        ↓
 Domain (entities, SOP rules, compliance)
        ↑
 Infrastructure adapters (DB, providers, AI, jobs, notifications)
```

The domain and application layers must not import FastAPI, SQLAlchemy models, Redis, or a specific AI vendor SDK.

## Module responsibilities

| Module | Responsibility |
|---|---|
| `identity` | Internal users. No enterprise SSO in V0. |
| `tenant` | Tenant and workspace. Every SaaS-bound record is tenant-scoped. |
| `discovery` | Search profiles and company/prospect candidate intake from permitted sources. |
| `source_registry` | Permitted source classes, policies, adapter lookup. |
| `company` / `person` | Canonical company and decision-maker records plus source links. |
| `signal` / `scoring` | Detected buying signals and deterministic SOP scoring. |
| `research` | Research runs and AI summaries bound to evidence IDs. |
| `outreach` | Drafts, human activity log, follow-up tasks. |
| `notifications` | Outbound alerts (email/Telegram later). Channel adapters only. |
| `pipeline` | Lead lifecycle aligned to the outreach SOP stages. |
| `ai_gateway` | Bounded, schema-validated AI calls. No DB or network autonomy. |
| `audit` | Security/process audit events. |
| `jobs` | Durable, idempotent, retryable background work. |

## Data flow

```text
Permitted source adapter
  → Normalized records + Evidence (source, locator, time, confidence)
  → Company / Person upsert
  → Signal detection (facts only; AI may suggest, rules decide)
  → Deterministic scoring / HOT-WARM-COLD
  → Optional AI research summary / outreach draft (evidence IDs required)
  → Lead API / workspace
  → Human LinkedIn action recorded as Activity
  → Follow-up task scheduling (business-day windows from the SOP)
```

AI-generated text is stored as interpretation, never as `EvidenceOrigin.SOURCE_DERIVED`.

## External provider abstraction

Business logic talks to `SourceAdapter` / `DiscoveryPort`. A provider is registered in the source registry with:

- source class
- policy (permitted, official-integration-only, denied)
- rate-limit metadata
- adapter implementation

Replacing a news API or licensed data vendor should require a new adapter plus registry entry, not changes to scoring or lead lifecycle code.

## AI boundary

The AI gateway receives only the minimum authorized context for one operation (for example: lead facts + evidence IDs + region + draft type). It cannot:

- query the database
- see another tenant
- invent source evidence
- mutate records
- perform LinkedIn or other unauthorized external actions

Application services persist results after schema validation and evidence-ID checks.

## LinkedIn compliance boundary

Automated: permitted/public research, scoring, drafting, notifications, CRM/follow-up scheduling.

Human-controlled: open LinkedIn, verify the person/company, send connection requests, send messages, read/respond to conversations, decide whether to pursue.

The source registry rejects scraping, browser automation, credential-based LinkedIn automation, auto-connect, auto-message, anti-detection, and rate-limit/CAPTCHA bypass adapters. An official LinkedIn adapter may exist as an interface and stays disabled until an authorized integration is configured.

## Background processing model

Jobs are first-class durable records in PostgreSQL. Redis is an optional notify/wakeup channel, not the system of record.

This answers horizontal scaling without a rewrite:

- Workers claim jobs with `FOR UPDATE SKIP LOCKED`
- Idempotency keys prevent duplicate enqueue
- Attempts, backoff, and terminal failure are stored on the job
- Adding workers is a process-count change, not a design change

V0 can run a single worker process. The claim protocol is already concurrency-safe.

## Future SaaS boundary

V0 is one internal tenant, but:

- every business table has `tenant_id`
- repositories require `TenantContext`
- request/job logs include tenant ID

Do not add billing, SSO, marketplace, or per-tenant quotas yet. When SaaS starts, add authz and optionally PostgreSQL RLS on the existing tenant column. Do not introduce global unscoped “all customers” tables.

## Future MCP boundary

MCP tools must call the same application services as the API. They must not open a database session or call providers directly. Proposed tool names live in the TDD §14 and are not implemented in V0.

## Company website ingestion (first permitted source)

V0 can ingest a **single** company website or careers URL through `CompanySourceIngestionService` and `FETCH_SOURCE`. See [company-source-ingestion.md](./company-source-ingestion.md).

HTTP, HTML parsing, and SSRF checks stay in infrastructure. The application layer only sees `SourceAdapter` records and persists existing `Company`, `CompanySource`, and `Evidence` entities.

## Deterministic signal detection

Stored evidence is evaluated by `SignalDetectionService`, then scored by the existing `LeadScoringService`. See [signal-detection.md](./signal-detection.md).

V0 currently implements `HIRING_TECH_ROLES` from careers/jobs evidence. LinkedIn, funding, expansion, recent job-change, and generic tech/growth language are catalogued but not inferred from company pages.

## Company discovery and pipeline

ICP-shaped requests run through `CompanyDiscoveryService` and `DISCOVER_COMPANIES`, then enqueue existing `FETCH_SOURCE` jobs for valid websites. See [company-discovery.md](./company-discovery.md).

`CompanyPipelineService` connects the stages automatically:

```text
DISCOVER_COMPANIES → FETCH_SOURCE → RESEARCH_LEAD → signals → scoring → qualification
```

After a successful fetch, the worker updates the originating `DiscoveryCandidate` (`company_id`, evidence IDs, status) and enqueues `RESEARCH_LEAD`. Research is deterministic: it reads stored evidence, runs `SignalDetectionService`, then `LeadScoringService`. No network or LLM calls occur in this path.

The first configured provider is SerpAPI (permitted search API). Provider credentials stay in environment configuration.

## What V0 intentionally does not include

Broad crawling, LinkedIn automation, AI research/drafts, lead dossier UI, Telegram/email delivery, production auth, MCP, billing, and enterprise SSO.
