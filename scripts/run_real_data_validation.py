#!/usr/bin/env python3
"""WS6.2 real-data validation runner (quota-aware).

Uses the existing ProspectIQ pipeline. Does NOT mock providers or insert fake companies.

Search budget: default 8 discovery API calls (hard cap 10). News disabled to preserve quota.

Database: writes to prospectiq_test by default. Set PROSPECTIQ_VALIDATION_USE_LIVE_DB=1
to use PROSPECTIQ_DATABASE_URL from .env (not recommended for live production DB).

Usage:
    cd backend
    ..\\.venv\\Scripts\\python.exe ..\\scripts\\run_real_data_validation.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

BACKEND_SRC = Path(__file__).resolve().parents[1] / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from prospectiq.application.dossier import LeadDossierService  # noqa: E402
from prospectiq.domain.common import (  # noqa: E402
    CompanyId,
    TenantId,
    TenantScope,
    WorkspaceId,
    utcnow,
)
from prospectiq.domain.discovery import (  # noqa: E402
    DiscoveryRequest,
    PermanentDiscoveryError,
    normalize_discovery_request,
)
from prospectiq.infrastructure.config import Settings  # noqa: E402
from prospectiq.infrastructure.db import dispose_engine, get_session_factory  # noqa: E402
from prospectiq.infrastructure.discovery_runtime import build_discovery_service  # noqa: E402
from prospectiq.infrastructure.jobs import PostgresJobQueue  # noqa: E402
from prospectiq.infrastructure.research_runtime import build_research_service  # noqa: E402
from prospectiq.infrastructure.repositories import (  # noqa: E402
    SqlAlchemyCompanyRepository,
    SqlAlchemyDiscoveryCandidateRepository,
    SqlAlchemyEvidenceRepository,
    SqlAlchemyLeadRepository,
    SqlAlchemySignalRepository,
)
from prospectiq.worker.main import handle_job  # noqa: E402
from sqlalchemy import text  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"
REPORT_PATH = REPO_ROOT / "docs" / "real-data-validation-report.md"

VALIDATION_TENANT_ID = UUID("00000000-0000-0000-0000-000000000062")
VALIDATION_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000063")
VALIDATION_TENANT_SLUG = "real-data-validation-ws62"

DEFAULT_VALIDATION_DB = "postgresql+asyncpg://prospectiq:prospectiq@localhost:5432/prospectiq_test"
SEARCH_BUDGET_DEFAULT = 8
SEARCH_BUDGET_HARD_CAP = 10
TARGET_UNIQUE_CANDIDATES = 25
MAX_JOB_ITERATIONS = 500

SALES_NAV_TITLES = (
    "CTO",
    "VP Engineering",
    "Head of Engineering",
    "Director of Engineering",
    "VP Technology",
    "Head of Technology",
    "Head of Product",
    "Founder",
    "Co-Founder",
)

HIGH_FIT_TERMS = (
    "development agency",
    "software vendor",
    "technology partner",
    "contract engineering",
    "staff augmentation",
    "outsourc",
    "rfp",
    "implementation partner",
    "systems integrator",
)
MEDIUM_FIT_TERMS = (
    "platform launch",
    "product launch",
    "modernization",
    "cloud migration",
    "api",
    "new product",
    "engineering expansion",
    "digital transformation",
)
LOW_FIT_TERMS = (
    "software engineer",
    "hiring",
    "open role",
    "careers",
)


@dataclass
class SearchQuotaTracker:
    budget: int
    used: int = 0
    successful: int = 0
    failed: int = 0
    pagination_requests: int = 0
    retry_attempts: int = 0
    remaining_reported: int | None = None
    events: list[dict[str, Any]] = field(default_factory=list)

    def record_attempt(
        self,
        *,
        operation: str,
        success: bool,
        http_status: int | None = None,
        result_count: int | None = None,
        error: str | None = None,
        is_pagination: bool = False,
    ) -> None:
        if is_pagination:
            self.pagination_requests += 1
        self.used += 1
        if success:
            self.successful += 1
        else:
            self.failed += 1
        self.events.append(
            {
                "operation": operation,
                "success": success,
                "http_status": http_status,
                "result_count": result_count,
                "error": error,
                "is_pagination": is_pagination,
                "search_number": self.used,
            }
        )
        if self.used > self.budget:
            raise PermanentDiscoveryError(
                f"Validation search budget exceeded ({self.used}/{self.budget}). Stopping."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "budget": self.budget,
            "used": self.used,
            "successful": self.successful,
            "failed": self.failed,
            "pagination_requests": self.pagination_requests,
            "retry_attempts": self.retry_attempts,
            "remaining_reported": self.remaining_reported,
            "events": self.events,
        }


@dataclass
class ValidationRun:
    status: str = "UNKNOWN"
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    environment: dict[str, Any] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)
    search_quota: dict[str, Any] = field(default_factory=dict)
    icp: dict[str, Any] = field(default_factory=dict)
    discovery: dict[str, Any] = field(default_factory=dict)
    pipeline: dict[str, Any] = field(default_factory=dict)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    company_records: list[dict[str, Any]] = field(default_factory=list)
    qualified_records: list[dict[str, Any]] = field(default_factory=list)
    signal_distribution: dict[str, int] = field(default_factory=dict)
    score_distribution: dict[str, int] = field(default_factory=dict)
    external_fit_distribution: dict[str, int] = field(default_factory=dict)
    signal_validation_sample: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)
    sales_nav_recipes: list[dict[str, Any]] = field(default_factory=list)
    ws62b: dict[str, Any] = field(default_factory=dict)


def _load_settings() -> Settings:
    """Load settings from repo-root .env without printing secrets."""
    os.environ.pop("PROSPECTIQ_TEST_DATABASE_URL", None)
    if ENV_FILE.exists():
        # Apply .env values to os.environ (pydantic will read them)
        for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

    budget = min(
        int(os.environ.get("PROSPECTIQ_VALIDATION_SEARCH_BUDGET", SEARCH_BUDGET_DEFAULT)),
        SEARCH_BUDGET_HARD_CAP,
    )
    os.environ["PROSPECTIQ_VALIDATION_SEARCH_BUDGET"] = str(budget)

    use_live = os.environ.get("PROSPECTIQ_VALIDATION_USE_LIVE_DB", "").lower() in {
        "1",
        "true",
        "yes",
    }
    if not use_live:
        os.environ["PROSPECTIQ_DATABASE_URL"] = os.environ.get(
            "PROSPECTIQ_VALIDATION_DATABASE_URL", DEFAULT_VALIDATION_DB
        )

    # Quota-safe discovery limits: single page, no news API calls
    os.environ["PROSPECTIQ_DISCOVERY_MAX_PAGES"] = "1"
    os.environ["PROSPECTIQ_DISCOVERY_PAGE_SIZE"] = "10"
    os.environ["PROSPECTIQ_DISCOVERY_MAX_CANDIDATES"] = str(TARGET_UNIQUE_CANDIDATES)
    os.environ["PROSPECTIQ_NEWS_PROVIDER"] = "none"

    if os.environ.get("PROSPECTIQ_SERPAPI_API_KEY", "").strip():
        os.environ["PROSPECTIQ_DISCOVERY_PROVIDER"] = "serpapi"

    from prospectiq.infrastructure.config import get_settings

    get_settings.cache_clear()
    return get_settings()


def _check_blockers(settings: Settings) -> list[str]:
    blockers: list[str] = []
    if settings.discovery_provider.lower().strip() in {"", "none"}:
        blockers.append("BLOCKED: PROSPECTIQ_DISCOVERY_PROVIDER (set to serpapi in .env)")
    if not settings.serpapi_api_key.get_secret_value().strip():
        blockers.append("BLOCKED: PROSPECTIQ_SERPAPI_API_KEY (set in .env, never commit)")
    return blockers


def _safe_settings_summary(settings: Settings) -> dict[str, Any]:
    use_live = os.environ.get("PROSPECTIQ_VALIDATION_USE_LIVE_DB", "").lower() in {
        "1",
        "true",
        "yes",
    }
    return {
        "env": settings.env,
        "database_url_host": settings.database_url.split("@")[-1],
        "validation_database_mode": "live" if use_live else "isolated_test_db",
        "discovery_provider": settings.discovery_provider,
        "news_provider": settings.news_provider,
        "serpapi_configured": bool(settings.serpapi_api_key.get_secret_value().strip()),
        "discovery_max_pages": settings.discovery_max_pages,
        "discovery_max_candidates": settings.discovery_max_candidates,
        "search_budget": int(os.environ.get("PROSPECTIQ_VALIDATION_SEARCH_BUDGET", SEARCH_BUDGET_DEFAULT)),
    }


def _install_quota_hooks(tracker: SearchQuotaTracker) -> None:
    """Monkeypatch SerpAPI fetch methods in-process for this script only."""
    from prospectiq.infrastructure.discovery import serpapi_provider as discovery_mod

    original_fetch = discovery_mod.SerpApiDiscoveryProvider._fetch_page

    async def tracked_fetch(self: object, query: str, *, start: int) -> dict[str, Any]:
        is_pagination = start > 0
        try:
            payload = await original_fetch(self, query, start=start)  # type: ignore[arg-type]
            organic = payload.get("organic_results") or []
            tracker.record_attempt(
                operation="discovery_search",
                success=True,
                http_status=200,
                result_count=len(organic),
                is_pagination=is_pagination,
            )
            if "account_info" in payload and isinstance(payload["account_info"], dict):
                remaining = payload["account_info"].get("searches_remaining")
                if isinstance(remaining, int):
                    tracker.remaining_reported = remaining
            return payload
        except Exception as exc:
            tracker.record_attempt(
                operation="discovery_search",
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                is_pagination=is_pagination,
            )
            raise

    discovery_mod.SerpApiDiscoveryProvider._fetch_page = tracked_fetch  # type: ignore[method-assign]


def _build_icp(settings: Settings, *, ws62b: bool = False) -> DiscoveryRequest:
    limit = min(TARGET_UNIQUE_CANDIDATES, settings.discovery_max_candidates)
    if ws62b:
        return normalize_discovery_request(
            industry="fintech",
            countries=["USA"],
            employee_min=11,
            employee_max=1000,
            hiring_required=True,
            keywords=["fintech startup", "careers", "software engineer"],
            limit=limit,
        )
    return normalize_discovery_request(
        industry="fintech",
        countries=["USA"],
        employee_min=11,
        employee_max=1000,
        hiring_required=True,
        keywords=["software development", "technology"],
        limit=limit,
    )


async def _ensure_validation_tenant(session: object) -> TenantScope:
    now = utcnow()
    await session.execute(  # type: ignore[attr-defined]
        text(
            """
            INSERT INTO tenants (id, name, slug, created_at, updated_at)
            VALUES (:id, 'Real Data Validation WS6.2', :slug, :now, :now)
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, updated_at = EXCLUDED.updated_at
            """
        ),
        {"id": VALIDATION_TENANT_ID, "slug": VALIDATION_TENANT_SLUG, "now": now},
    )
    await session.execute(  # type: ignore[attr-defined]
        text(
            """
            INSERT INTO workspaces (id, tenant_id, name, created_at, updated_at)
            VALUES (:id, :tenant_id, 'Validation Workspace', :now, :now)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"id": VALIDATION_WORKSPACE_ID, "tenant_id": VALIDATION_TENANT_ID, "now": now},
    )
    await session.flush()  # type: ignore[attr-defined]
    return TenantScope(
        tenant_id=TenantId(VALIDATION_TENANT_ID),
        workspace_id=WorkspaceId(VALIDATION_WORKSPACE_ID),
        request_id="ws62-real-data-validation",
    )


def _ensure_migrations(settings: Settings) -> None:
    """Run Alembic synchronously (must not call from inside asyncio.run)."""
    import subprocess

    env = os.environ.copy()
    env["PROSPECTIQ_DATABASE_URL"] = settings.database_url
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "upgrade",
            "head",
        ],
        cwd=str(REPO_ROOT / "backend"),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Alembic migration failed. "
            f"See stderr: {result.stderr[-500:] if result.stderr else 'unknown'}"
        )


async def _drain_job_queue(settings: Settings, run: ValidationRun) -> None:
    factory = get_session_factory(settings)
    completed: dict[str, int] = {}

    for _ in range(MAX_JOB_ITERATIONS):
        async with factory() as session:
            queue = PostgresJobQueue(session)
            job = await queue.claim(worker_id="ws62-validation", now=utcnow())
            if job is None:
                await session.commit()
                break
            try:
                await handle_job(job, session=session, settings=settings)
                await queue.complete(job)
                await session.commit()
                key = job.job_type.value
                completed[key] = completed.get(key, 0) + 1
            except Exception as exc:
                run.failures.append(
                    {
                        "job_id": str(job.id),
                        "job_type": job.job_type.value,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    }
                )
                await session.rollback()
                async with factory() as fail_session:
                    fail_queue = PostgresJobQueue(fail_session)
                    permanent = "Permanent" in type(exc).__name__
                    await fail_queue.fail(job, str(exc), now=utcnow(), permanent=permanent)
                    await fail_session.commit()
                if "budget exceeded" in str(exc).lower():
                    break
    run.pipeline["jobs_completed"] = completed


def _source_origin_label(source_class: str | None, origin: str) -> str:
    if source_class == "permitted_search_api":
        return "PROSPECTIQ_DISCOVERY"
    if source_class == "company_website":
        return "COMPANY_WEBSITE"
    if source_class == "careers_page":
        return "COMPANY_CAREERS"
    if source_class in {"public_news", "public_funding", "public_announcement"}:
        return "NEWS"
    return origin.upper() if origin else "UNKNOWN"


def _assess_external_opportunity_fit(dossier: object) -> tuple[str, list[str]]:
    evidence = dossier.evidence  # type: ignore[attr-defined]
    signals = dossier.signals  # type: ignore[attr-defined]
    text_blob = " ".join(
        (ev.get("fact") or "") + " " + (ev.get("snippet") or "") for ev in evidence
    ).lower()
    for sig in signals:
        text_blob += " " + (sig.get("reason") or "")

    reasons: list[str] = []
    if any(term in text_blob for term in HIGH_FIT_TERMS):
        reasons.append("Evidence mentions vendor/partner/contract/agency language.")
        return "HIGH", reasons
    if any(sig["signal_type"] in {"funding_news", "expansion_launch"} for sig in signals):
        reasons.append("Funding or expansion signal may imply build capacity need (hypothesis).")
        return "MEDIUM", reasons
    if any(term in text_blob for term in MEDIUM_FIT_TERMS):
        reasons.append("Evidence mentions platform/product/modernization initiative.")
        return "MEDIUM", reasons
    if any(sig["signal_type"] == "hiring_tech_roles" for sig in signals):
        reasons.append(
            "Only generic tech hiring observed — buying signal, not proof of external-project need."
        )
        return "LOW", reasons
    if any(term in text_blob for term in LOW_FIT_TERMS):
        reasons.append("Generic technology/hiring language only.")
        return "LOW", reasons
    return "UNKNOWN", ["Insufficient evidence for external software-development opportunity assessment."]


def _sales_nav_recipe(company_name: str) -> dict[str, Any]:
    return {
        "company": company_name,
        "seniority": ["CXO", "VP", "Director"],
        "functions": ["Engineering", "Technology", "Product"],
        "titles": list(SALES_NAV_TITLES),
        "note": "Human-controlled Sales Navigator search. Do NOT automate LinkedIn.",
    }


async def _collect_results(settings: Settings, scope: TenantScope, run: ValidationRun) -> None:
    factory = get_session_factory(settings)
    async with factory() as session:
        candidates_repo = SqlAlchemyDiscoveryCandidateRepository(session)
        dossier_svc = LeadDossierService(
            companies=SqlAlchemyCompanyRepository(session),
            evidence=SqlAlchemyEvidenceRepository(session),
            signals=SqlAlchemySignalRepository(session),
            leads=SqlAlchemyLeadRepository(session),
            candidates=candidates_repo,
            research=build_research_service(session),
        )

        rows = await candidates_repo.list_for_tenant(scope, limit=300)
        job_id = run.discovery.get("job_id")
        if job_id:
            rows = [item for item in rows if str(item.discovery_job_id) == job_id]
        unique_domains = {item.domain for item in rows if item.domain}
        run.discovery["candidates_discovered"] = len(rows)
        run.discovery["unique_domains"] = len(unique_domains)
        run.candidates = [
            {
                "name": item.name,
                "domain": item.domain,
                "website": item.website_url,
                "source_locator": item.source_locator,
                "provider": item.provider_key,
                "discovered_at": item.discovered_at.isoformat(),
                "confidence": item.confidence,
                "ingestion_status": item.ingestion_status.value,
                "company_id": str(item.company_id) if item.company_id else None,
                "field_checks": dict(item.field_checks),
            }
            for item in rows
        ]

        fetched = sum(
            1
            for item in rows
            if item.ingestion_status.value
            in {"fetched", "news_queued", "research_queued", "researched", "research_failed"}
        )
        researched = sum(1 for item in rows if item.ingestion_status.value == "researched")
        run.pipeline["candidates_fetched"] = fetched
        run.pipeline["companies_researched"] = researched
        run.pipeline["unique_companies"] = len(unique_domains)

        signal_counts: dict[str, int] = {}
        score_counts = {"Cold": 0, "Warm": 0, "Hot": 0}
        fit_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0}
        qualified: list[dict[str, Any]] = []
        all_companies: list[dict[str, Any]] = []
        validation_sample: list[dict[str, Any]] = []

        company_ids = {item.company_id for item in rows if item.company_id}
        total_evidence = 0
        for company_id in company_ids:
            dossier = await dossier_svc.get_by_company_id(scope, CompanyId(company_id))
            total_evidence += len(dossier.evidence)
            for sig in dossier.signals:
                signal_counts[sig["signal_type"]] = signal_counts.get(sig["signal_type"], 0) + 1
            classification = dossier.score.get("classification", "Cold")
            if classification in score_counts:
                score_counts[classification] += 1
            fit, fit_reasons = _assess_external_opportunity_fit(dossier)
            fit_counts[fit] += 1
            record = {
                "company": dossier.company["name"],
                "industry": dossier.company.get("industry"),
                "country": dossier.company.get("geography"),
                "website": dossier.company.get("website"),
                "signals": dossier.signals,
                "evidence_count": len(dossier.evidence),
                "raw_score": dossier.score.get("total_score"),
                "classification": classification,
                "qualified": dossier.score.get("qualified"),
                "distinct_signal_count": dossier.score.get("distinct_signal_count"),
                "external_opportunity_fit": fit,
                "external_opportunity_reasoning": fit_reasons,
                "source_attribution": list(
                    {
                        _source_origin_label(ev.get("source_class"), ev.get("origin", ""))
                        for ev in dossier.evidence
                    }
                ),
            }
            all_companies.append(record)
            if dossier.score.get("qualified"):
                qualified.append(record)
                run.sales_nav_recipes.append(_sales_nav_recipe(dossier.company["name"]))
            for sig in dossier.signals[:2]:
                validation_sample.append(
                    {
                        "company": dossier.company["name"],
                        "signal_type": sig["signal_type"],
                        "reason": sig["reason"],
                        "manual_classification": "UNCERTAIN",
                    }
                )

        run.company_records = all_companies
        run.qualified_records = qualified
        run.signal_distribution = signal_counts
        run.score_distribution = score_counts
        run.external_fit_distribution = fit_counts
        run.signal_validation_sample = validation_sample[:15]
        run.pipeline["total_evidence"] = total_evidence
        run.pipeline["companies_with_evidence"] = sum(1 for c in all_companies if c["evidence_count"])
        run.pipeline["companies_with_signals"] = sum(1 for c in all_companies if c["signals"])
        run.pipeline["qualified_count"] = len(qualified)


def _render_report(run: ValidationRun) -> str:
    lines = [
        "# Real-Data Validation Report (WS6.2)",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        f"Run started: {run.started_at}",
        f"**Status: {run.status}**",
        "",
        "## Search Quota",
        "",
        "```json",
        json.dumps(run.search_quota, indent=2),
        "```",
        "",
        "## Environment",
        "",
        "```json",
        json.dumps(run.environment, indent=2),
        "```",
        "",
    ]
    if run.blockers:
        lines.append("## Blockers")
        lines.append("")
        for b in run.blockers:
            lines.append(f"- {b}")
        lines.append("")

    lines.extend(
        [
            "## ICP",
            "",
            "```json",
            json.dumps(run.icp, indent=2),
            "```",
            "",
            "## Summary Metrics",
            "",
            f"- Candidates discovered: {run.discovery.get('candidates_discovered', 0)}",
            f"- Unique domains: {run.discovery.get('unique_domains', 0)}",
            f"- Website fetches succeeded: {run.pipeline.get('candidates_fetched', 0)}",
            f"- Companies researched: {run.pipeline.get('companies_researched', 0)}",
            f"- Total evidence rows: {run.pipeline.get('total_evidence', 0)}",
            f"- Qualified companies: {run.pipeline.get('qualified_count', 0)}",
            "",
            "## External Opportunity Fit Distribution",
            "",
            "```json",
            json.dumps(run.external_fit_distribution, indent=2),
            "```",
            "",
            "## Signal Distribution",
            "",
            "```json",
            json.dumps(run.signal_distribution, indent=2),
            "```",
            "",
            f"## Qualified Opportunities ({len(run.qualified_records)})",
            "",
        ]
    )
    for idx, rec in enumerate(run.qualified_records, 1):
        lines.append(f"### {idx}. {rec['company']}")
        lines.append(f"- Website: {rec.get('website')}")
        lines.append(f"- Score: {rec.get('raw_score')} ({rec.get('classification')})")
        lines.append(f"- External fit: **{rec.get('external_opportunity_fit')}**")
        for reason in rec.get("external_opportunity_reasoning", []):
            lines.append(f"  - {reason}")
        for sig in rec.get("signals", []):
            lines.append(f"  - Signal: {sig['signal_type']} — {sig.get('reason', '')}")
        lines.append("")

    if not run.qualified_records:
        lines.append("_No qualified companies in this run._")
        lines.append("")

    lines.extend(["## Strongest Opportunities (by external fit)", ""])
    ranked = sorted(
        run.company_records,
        key=lambda r: {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "UNKNOWN": 3}.get(
            r.get("external_opportunity_fit", "UNKNOWN"), 4
        ),
    )
    for rec in ranked[:5]:
        if rec.get("evidence_count", 0) == 0:
            continue
        lines.append(
            f"- **{rec['company']}** — fit={rec.get('external_opportunity_fit')}, "
            f"qualified={rec.get('qualified')}, score={rec.get('raw_score')}"
        )
    lines.append("")

    lines.extend(["## Failures", ""])
    if run.failures:
        lines.append("```json")
        lines.append(json.dumps(run.failures, indent=2))
        lines.append("```")
    else:
        lines.append("_None recorded._")
    lines.append("")

    lines.extend(["## Sales Navigator Recipes (Human Only)", ""])
    for recipe in run.sales_nav_recipes:
        lines.append(f"- **{recipe['company']}**: {', '.join(recipe['titles'][:4])}…")
    if not run.sales_nav_recipes:
        lines.append("_None generated._")
    lines.append("")
    lines.append("---")
    if run.ws62b:
        lines.extend(_render_ws62b_section(run))
    lines.append("_First controlled real-data experiment. Not commercial validation._")
    return "\n".join(lines)


def _render_ws62b_section(run: ValidationRun) -> list[str]:
    w = run.ws62b
    lines = [
        "",
        "## WS6.2B — Discovery Quality Experiment",
        "",
        "### 1. First Experiment Problem",
        "The initial query returned educational, regulatory, and content pages as candidates "
        "because every SerpAPI organic result was accepted without company validation.",
        "",
        "### 2. Discovery Changes Made",
        "- Added `validate_discovery_hit()` in `discovery_candidate_validation.py`",
        "- Rejects government/edu TLDs, editorial subdomains, media patterns, and content URL paths",
        "- Accepts company root domains and careers/about/company pages",
        "- New status: `skipped_non_company`",
        "",
        "### 3. Second Query Used",
        f"```\n{w.get('query', '')}\n```",
        "",
        f"### 4. SerpAPI Calls Used: **{w.get('searches_used', 0)}** (authorized: exactly 1)",
        "",
        f"### 5. Raw Result Count: {w.get('raw_result_count', 0)}",
        f"### 6. Candidate Records: {w.get('candidate_count', 0)}",
        f"### 7. Accepted VALID_COMPANY: {w.get('accepted_valid_company', 0)}",
        f"### 8. Rejected: {w.get('rejected_count', 0)}",
        "",
        "### 9. Rejection Reasons",
        "",
        "```json",
        json.dumps(w.get("rejection_breakdown", {}), indent=2),
        "```",
        "",
        f"### 10. Unique Domains (accepted): {w.get('accepted_domains', [])}",
        "",
        "### 11–16. Pipeline Outcomes",
        "",
        "```json",
        json.dumps(
            {
                "website_fetches": run.pipeline.get("candidates_fetched", 0),
                "evidence": run.pipeline.get("total_evidence", 0),
                "signals": run.signal_distribution,
                "qualified": run.pipeline.get("qualified_count", 0),
                "external_fit": run.external_fit_distribution,
            },
            indent=2,
        ),
        "```",
        "",
        "### 17. Best Candidates",
        "",
    ]
    for rec in w.get("best_candidates", []):
        lines.append(f"- **{rec.get('company')}** ({rec.get('domain')}) — {rec.get('why')}")
    if not w.get("best_candidates"):
        lines.append("_No strong company candidates identified._")
    lines.extend(
        [
            "",
            "### 18. Remaining Discovery-Quality Problems",
            *(f"- {item}" for item in w.get("remaining_problems", [])),
            "",
            "### 19. Recommendation for Next Phase",
            w.get("recommendation", ""),
            "",
        ]
    )
    return lines


def _analyze_ws62b(run: ValidationRun, *, query: str, searches_used: int) -> None:
    from collections import Counter

    job_candidates = [
        c
        for c in run.candidates
        if c.get("field_checks")  # all from latest job mixed - filter by discovery job if needed
    ]
    rejection_reasons: Counter[str] = Counter()
    quality_classes: Counter[str] = Counter()
    accepted: list[dict[str, Any]] = []
    rejected = 0
    for cand in run.candidates:
        checks = cand.get("field_checks") or {}
        quality = checks.get("candidate_quality_class", "unknown")
        if cand.get("ingestion_status") == "skipped_non_company":
            rejected += 1
            reason = checks.get("candidate_validation", "rejected")
            rejection_reasons[reason] += 1
            quality_classes[quality] += 1
        elif cand.get("ingestion_status") not in {
            "skipped_no_url",
            "skipped_invalid_url",
            "skipped_duplicate",
        }:
            if quality == "valid_company":
                accepted.append(cand)

    best = []
    for rec in run.company_records:
        if rec.get("evidence_count", 0) > 0 or rec.get("signals"):
            best.append(
                {
                    "company": rec["company"],
                    "domain": rec.get("website"),
                    "why": "Passed validation and entered pipeline",
                    "score": rec.get("raw_score"),
                    "qualified": rec.get("qualified"),
                    "fit": rec.get("external_opportunity_fit"),
                }
            )

    remaining = []
    if not accepted:
        remaining.append("Query may still return content pages SerpAPI ranks highly.")
    if run.pipeline.get("candidates_fetched", 0) < len(accepted):
        remaining.append("Some validated companies blocked by HTTP fetch (403/redirect loops).")
    remaining.append("Employee count and industry remain not_verified at discovery time.")

    run.ws62b = {
        "query": query,
        "searches_used": searches_used,
        "raw_result_count": len(run.candidates),
        "candidate_count": len(run.candidates),
        "accepted_valid_company": len(accepted),
        "rejected_count": rejected,
        "rejection_breakdown": {
            "by_reason": dict(rejection_reasons),
            "by_quality_class": dict(quality_classes),
        },
        "accepted_domains": sorted({c.get("domain") for c in accepted if c.get("domain")}),
        "best_candidates": best[:10],
        "remaining_problems": remaining,
        "recommendation": (
            "Tune query toward careers pages on company domains; consider enriching validation "
            "with homepage-vs-article title heuristics before spending more search quota."
        ),
    }


async def run_validation(*, settings: Settings, ws62b: bool = False) -> ValidationRun:
    if ws62b:
        os.environ["PROSPECTIQ_VALIDATION_SEARCH_BUDGET"] = "1"
    budget = int(os.environ.get("PROSPECTIQ_VALIDATION_SEARCH_BUDGET", SEARCH_BUDGET_DEFAULT))
    tracker = SearchQuotaTracker(budget=budget)
    run = ValidationRun()
    run.environment = _safe_settings_summary(settings)
    run.search_quota = tracker.to_dict()
    run.blockers = _check_blockers(settings)
    icp = _build_icp(settings, ws62b=ws62b)
    run.icp = icp.to_payload()

    try:
        if run.blockers:
            run.status = "BLOCKED"
            return run

        _install_quota_hooks(tracker)

        from prospectiq.domain.discovery_query import build_discovery_query

        query_text = build_discovery_query(icp)
        run.discovery["query"] = query_text

        factory = get_session_factory(settings)
        async with factory() as session:
            scope = await _ensure_validation_tenant(session)
            discovery = build_discovery_service(session, settings)
            submission = await discovery.submit(scope, icp)
            run.discovery["job_id"] = str(submission.job_id)
            run.discovery["idempotent_replay"] = submission.already_enqueued
            await session.commit()

        await _drain_job_queue(settings, run)
        run.search_quota = tracker.to_dict()
        await _collect_results(settings, scope, run)

        if ws62b:
            searches = 0 if run.discovery.get("idempotent_replay") else tracker.used
            _analyze_ws62b(run, query=query_text, searches_used=searches)
            if run.failures and run.discovery.get("candidates_discovered", 0) == 0:
                run.ws62b["provider_outcome"] = "discovery_job_failed"
                run.ws62b["remaining_problems"] = list(run.ws62b.get("remaining_problems", []))
                run.ws62b["remaining_problems"].insert(
                    0,
                    f"Discovery job failed: {run.failures[0].get('error', 'unknown')}",
                )

        if tracker.used > budget:
            run.status = "BLOCKED"
            run.blockers.append("Search budget exceeded")
        elif run.discovery.get("candidates_discovered", 0) == 0:
            run.status = "PARTIAL"
        elif run.pipeline.get("candidates_fetched", 0) == 0:
            run.status = "PARTIAL"
        else:
            run.status = "PASS" if run.pipeline.get("companies_researched", 0) > 0 else "PARTIAL"
    finally:
        await dispose_engine()

    return run


def main() -> int:
    parser = argparse.ArgumentParser(description="ProspectIQ real-data validation runner")
    parser.add_argument(
        "--ws62b",
        action="store_true",
        help="WS6.2B discovery quality experiment (exactly 1 SerpAPI search)",
    )
    args = parser.parse_args()
    if args.ws62b:
        os.environ["PROSPECTIQ_VALIDATION_SEARCH_BUDGET"] = "1"
    settings = _load_settings()
    blockers = _check_blockers(settings)
    if not blockers:
        _ensure_migrations(settings)
    run = asyncio.run(run_validation(settings=settings, ws62b=args.ws62b))
    run.search_quota  # ensure attached
    report = _render_report(run)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    q = run.search_quota
    print(f"STATUS: {run.status}")
    print(f"Search budget: {q.get('budget')}")
    print(f"Searches used: {q.get('used')}")
    print(f"Candidates: {run.discovery.get('candidates_discovered', 0)}")
    print(f"Unique companies: {run.pipeline.get('unique_companies', 0)}")
    print(f"Companies researched: {run.pipeline.get('companies_researched', 0)}")
    print(f"Qualified: {run.pipeline.get('qualified_count', 0)}")
    print(f"External fit: {run.external_fit_distribution}")
    print(f"Report: {REPORT_PATH}")
    if run.blockers:
        print("Blockers:")
        for b in run.blockers:
            print(f"  {b}")
    return 0 if run.status in {"PASS", "PARTIAL"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
