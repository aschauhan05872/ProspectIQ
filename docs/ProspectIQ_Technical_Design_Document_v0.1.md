# ProspectIQ — AI Lead Intelligence Engine

**Technical Design Document v0.1**  
**Date:** 22 September 2026  
**Phase:** Internal V0 / dogfooding  
**Future:** Multi-tenant SaaS → MCP

## 1. Executive Summary
ProspectIQ turns the supplied B2B lead-generation/outreach SOP into a production-minded lead-intelligence system. V0 is internal: discovery, research, signal detection, scoring, enrichment, AI message drafting, notifications, CRM/follow-up tracking. LinkedIn remains a human-controlled execution surface unless an officially approved integration provides a permitted capability.

## 2. Product Roadmap
1. Internal V0
2. 2–3 day technical/quality validation
3. 1–2 week sales-process validation
4. Multi-tenant SaaS
5. MCP interface over the same core engine

## 3. Core Principles
- Evidence over guesswork
- Human-controlled LinkedIn execution
- Deterministic business rules + bounded AI
- Source abstraction
- UI/API/MCP share the same domain/application services
- Tenant isolation from V0
- Least privilege
- Idempotent asynchronous jobs
- Observability and provenance first
- Modular monolith before microservices

## 4. SOP-Derived Business Rules
### ICP
- Company size: 11–1,000 employees
- Headcount growth: 10%+
- Company type: private/public/venture-backed
- Hiring: yes
- Priority industries: HealthTech, Fintech/Financial Services, Insurance, Retail/E-commerce, Telecom, Manufacturing, Logistics/Supply Chain, Travel/Hospitality
- Target geographies: USA, UK, Europe, UAE/Saudi Arabia/Qatar, Australia, Canada

### Decision makers
Functions: Engineering, IT, Product, Operations, Business Development. Seniority: CXO, VP, Director, Head, Partner, Owner; managers only for companies under 200 employees.

### Signal weights
| Signal | Weight |
|---|---:|
| Changed job recently | +2 |
| Active on LinkedIn | +1 |
| Talks about technology/growth | +2 |
| Hiring tech roles | +3 |
| Funding/news | +3 |
| Expansion/launch | +2 |

Classification: 0–2 Cold, 3–5 Warm, 6–10 HOT. Qualification requires 2+ buying signals.

### Outreach sequence
Research → Connect → Engage → First Message → Follow-Up 1 → Follow-Up 2 → Follow-Up 3 → Qualification → Meeting/Next Step → Strategy Sheet. Follow-ups are approximately 2–3, 3–5, and 4–7 business days after the relevant prior stage. Stop automated-style follow-ups once the prospect is engaged.

## 5. Architecture
```text
Permitted Sources
      ↓
Discovery Adapters → Source Evidence → Normalization
                                 ↓
                        Company Intelligence
                                 ↓
                     Person Matching + Signals
                                 ↓
                       Deterministic Scoring
                                 ↓
                         AI Research/Drafts
                                 ↓
                 Lead API / Internal Workspace
                      ↙       ↓        ↘
                 Telegram   Email      Web UI
                                 ↓
                      Human LinkedIn Action
                                 ↓
                      Activity / Follow-up
```

### V0 deployment style
**Modular monolith + asynchronous workers**. Recommended stack: Python/FastAPI, PostgreSQL, Redis + durable queue, React/Next.js, containerized deployment. Exact library choices can be finalized during repo implementation.

## 6. Core Modules
- identity
- tenant
- discovery
- source_registry
- company
- person
- signal
- scoring
- research
- outreach
- notifications
- pipeline
- ai_gateway
- audit

## 7. Data Model
Core entities: Tenant, Workspace, User, SearchProfile, Company, CompanySource, Person, PersonSource, Signal, Evidence, Lead, ResearchRun, MessageDraft, Activity, FollowUpTask, Notification, SourcePolicy, AuditEvent.

Every SaaS-bound business table should be tenant-scoped from V0.

## 8. LinkedIn Compliance Boundary
### Automated
- Research and aggregation from permitted/public sources
- Scoring/enrichment/message drafting
- Notifications and CRM/follow-up scheduling

### Human
- Open LinkedIn
- Verify profile/company
- Connect
- Send message
- Handle conversation

### Official integration only
Any programmatic LinkedIn capability that requires LinkedIn API access must use an approved capability and the applicable authorization/terms. No unauthorized scraping, browser automation, bypassing limits or automated engagement.

## 9. Research Strategy
Primary source classes: company websites, careers/job data, public announcements/news, permitted search/data APIs, licensed business data and official LinkedIn integrations when authorized. Store source, locator, timestamp, evidence snippet/fact, confidence and policy metadata.

## 10. AI Boundary
AI receives only minimum authorized context and cannot directly query the database or perform arbitrary network actions. LLM outputs are schema-validated. Every research claim used in scoring/message generation should be linked to internal evidence IDs.

## 11. API
Initial route groups: `/searches`, `/leads`, `/research`, `/drafts`, `/activities`, `/followups`, `/notifications`, `/health`, `/ready`.

Domain/application services are shared by Web UI and future MCP.

## 12. Async Jobs
Discovery, source fetch, lead research, scoring, draft generation and notifications run asynchronously. Use retry/backoff, provider-aware rate limits and idempotency keys.

## 13. SaaS Readiness
Tenant-aware request context, authorization, tenant-scoped repositories, future PostgreSQL RLS, per-tenant configuration, quotas/usage metering and audit.

## 14. MCP (Future)
Proposed tools: `search_companies`, `search_prospects`, `research_company`, `research_prospect`, `detect_buying_signals`, `score_lead`, `generate_outreach`, `get_hot_leads`, `get_followups`, `record_activity`. MCP must call application services, never direct DB access.

## 15. Security / Privacy
HTTPS, secure secrets, authorization, tenant isolation, audit, backups, minimal data collection, source-specific retention and deletion policies, security testing, outbound request controls.

## 16. Observability
Capture request/job IDs, tenant IDs, source IDs, latency, queue depth, job failures, source health, notification delivery and audit events.

## 17. Testing
Unit, integration, contract, API, AI-evaluation, end-to-end, security and load tests. Major components should answer senior-level interview concerns: retries, concurrency, security, caching, scaling, observability and testing.

## 18. V0 Implementation Order
1. Baseline/config/logging/health
2. DB/migrations
3. Source registry/adapters
4. Discovery
5. Research
6. Signals + scoring
7. Lead dossier UI/API
8. AI gateway + drafts
9. Notifications
10. Activities/follow-ups
11. Monitoring/audit
12. Real-world 2–3 day dry run

## 19. Validation
- Day 1: system correctness and source evidence
- Day 2: lead quality, score quality, draft quality, retry/idempotency
- Day 3: real manual LinkedIn workflow and follow-up tracking
- 1–2 weeks: measure actual reply/qualification/meeting conversion and tune evidence-based rules

## 20. Metrics
Candidate yield, research yield, HOT lead rate, contact rate, reply rate, qualified conversation rate, meeting rate, source precision, false-positive rate, research cost per lead and time-to-alert.

## 21. References
### Internal
- LinkedIn Sales Navigator Lead Generation SOP
- SOP: LinkedIn Outreach & Follow-Up Strategy

### Current external
- LinkedIn User Agreement: https://ac.linkedin.com/legal/user-agreement
- LinkedIn Sales Navigator API/Platform: https://learn.microsoft.com/en-us/linkedin/sales/
- LinkedIn Display Services: https://learn.microsoft.com/en-us/linkedin/sales/display-services/
- MCP 2026-07-28 release: https://blog.modelcontextprotocol.io/posts/2026-07-28/
