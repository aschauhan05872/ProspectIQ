"""Search profiles and company discovery. One industry per search (SOP)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from prospectiq.domain.common import CompanyId, EvidenceId, JobId, LeadId, TenantId, WorkspaceId
from prospectiq.domain.company import (
    CompanyType,
    Geography,
    Industry,
    normalize_geography,
    normalize_industry,
)
from prospectiq.domain.icp import MAX_EMPLOYEES, MIN_EMPLOYEES
from prospectiq.domain.person import DecisionFunction, Seniority
from prospectiq.domain.source_url import InvalidSourceUrl, parse_source_url


class DiscoveryFetchError(Exception):
    permanent: bool = False


class PermanentDiscoveryError(DiscoveryFetchError):
    permanent = True


class RetryableDiscoveryError(DiscoveryFetchError):
    permanent = False


class FieldVerificationStatus(StrEnum):
    MATCHED = "matched"
    NOT_VERIFIED = "not_verified"
    NOT_SUPPORTED = "not_supported"


class DiscoveryIngestionStatus(StrEnum):
    DISCOVERED = "discovered"
    FETCH_QUEUED = "fetch_queued"
    FETCHED = "fetched"
    FETCH_FAILED = "fetch_failed"
    NEWS_QUEUED = "news_queued"
    RESEARCH_QUEUED = "research_queued"
    RESEARCHED = "researched"
    RESEARCH_FAILED = "research_failed"
    PENDING = "pending"
    ENQUEUED = "enqueued"
    ALREADY_ENQUEUED = "already_enqueued"
    SKIPPED_NO_URL = "skipped_no_url"
    SKIPPED_INVALID_URL = "skipped_invalid_url"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    SKIPPED_NON_COMPANY = "skipped_non_company"


class DiscoveryFactKind(StrEnum):
    DISCOVERY_CANDIDATE = "discovery_candidate"


@dataclass(frozen=True, slots=True)
class ProviderFieldSupport:
    field_name: str
    requested_in_icp: bool
    provider_support: FieldVerificationStatus
    notes: str


PROVIDER_FIELD_SUPPORT: tuple[ProviderFieldSupport, ...] = (
    ProviderFieldSupport(
        "industry", True, FieldVerificationStatus.MATCHED, "Used as search query terms."
    ),
    ProviderFieldSupport(
        "geography", True, FieldVerificationStatus.MATCHED, "Used as search query terms."
    ),
    ProviderFieldSupport(
        "keywords", True, FieldVerificationStatus.MATCHED, "Used as search query terms."
    ),
    ProviderFieldSupport(
        "employee_min",
        True,
        FieldVerificationStatus.NOT_VERIFIED,
        "May appear in query text; provider does not filter by headcount.",
    ),
    ProviderFieldSupport(
        "employee_max",
        True,
        FieldVerificationStatus.NOT_VERIFIED,
        "May appear in query text; provider does not filter by headcount.",
    ),
    ProviderFieldSupport(
        "hiring_required",
        True,
        FieldVerificationStatus.NOT_VERIFIED,
        "May appear in query text; provider does not verify hiring status.",
    ),
    ProviderFieldSupport(
        "min_headcount_growth_pct",
        True,
        FieldVerificationStatus.NOT_SUPPORTED,
        "Not available from the initial search API provider.",
    ),
    ProviderFieldSupport(
        "company_type",
        True,
        FieldVerificationStatus.NOT_SUPPORTED,
        "Not available from the initial search API provider.",
    ),
)


@dataclass(slots=True)
class SearchProfile:
    id: UUID
    tenant_id: TenantId
    workspace_id: WorkspaceId
    name: str
    industry: Industry
    geographies: list[Geography]
    functions: list[DecisionFunction]
    seniorities: list[Seniority]
    require_hiring: bool
    min_headcount_growth_pct: float
    min_employees: int
    max_employees: int
    extra_filters: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DiscoveryRequest:
    industry: Industry
    countries: tuple[Geography, ...]
    employee_min: int
    employee_max: int
    hiring_required: bool
    keywords: tuple[str, ...]
    limit: int
    min_headcount_growth_pct: float | None = None
    company_types: tuple[CompanyType, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "industry": self.industry.value,
            "countries": [item.value for item in self.countries],
            "employee_min": self.employee_min,
            "employee_max": self.employee_max,
            "hiring_required": self.hiring_required,
            "keywords": list(self.keywords),
            "limit": self.limit,
            "min_headcount_growth_pct": self.min_headcount_growth_pct,
            "company_types": [item.value for item in self.company_types],
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> DiscoveryRequest:
        return normalize_discovery_request(
            industry=str(payload["industry"]),
            countries=[str(item) for item in payload.get("countries") or []],
            employee_min=int(payload.get("employee_min", MIN_EMPLOYEES)),
            employee_max=int(payload.get("employee_max", MAX_EMPLOYEES)),
            hiring_required=bool(payload.get("hiring_required", False)),
            keywords=[str(item) for item in payload.get("keywords") or []],
            limit=int(payload.get("limit", 20)),
            min_headcount_growth_pct=payload.get("min_headcount_growth_pct"),
            company_types=[str(item) for item in payload.get("company_types") or []],
        )


@dataclass(frozen=True, slots=True)
class ProviderDiscoveryHit:
    name: str
    website: str | None
    domain: str | None
    source_locator: str
    confidence: str | None = None
    provider_rank: int | None = None
    raw_reference: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CompanyCandidate:
    name: str
    website: str | None
    industry: Industry | None
    geography: Geography | None
    employee_count: int | None
    source_adapter_key: str
    source_locator: str


@dataclass(slots=True)
class DiscoveryCandidate:
    id: UUID
    tenant_id: TenantId
    discovery_job_id: JobId
    name: str
    domain: str | None
    website_url: str | None
    normalized_website: str | None
    provider_key: str
    source_locator: str
    discovered_at: datetime
    confidence: str | None
    provider_rank: int | None
    field_checks: dict[str, str]
    evidence_id: EvidenceId | None
    company_id: CompanyId | None
    fetch_job_id: JobId | None
    research_job_id: JobId | None
    lead_id: LeadId | None
    source_evidence_ids: list[str]
    ingestion_status: DiscoveryIngestionStatus
    request_snapshot: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class DiscoverySubmission:
    tenant_id: TenantId
    job_id: JobId
    idempotency_key: str
    normalized_request: dict[str, Any]
    status: str
    already_enqueued: bool
    provider_key: str
    field_support: tuple[ProviderFieldSupport, ...]


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    tenant_id: TenantId
    job_id: JobId
    provider_key: str
    candidate_count: int
    accepted_count: int
    rejected_count: int
    fetch_jobs_created: int
    duration_ms: int
    candidates: tuple[DiscoveryCandidate, ...]


def _parse_industry(value: str) -> Industry:
    parsed = normalize_industry(value)
    if parsed is not None:
        return parsed
    try:
        return Industry(value)
    except ValueError as exc:
        raise PermanentDiscoveryError(f"Unsupported industry: {value}") from exc


def _parse_geography(value: str) -> Geography:
    parsed = normalize_geography(value)
    if parsed is not None:
        return parsed
    try:
        return Geography(value)
    except ValueError as exc:
        raise PermanentDiscoveryError(f"Unsupported geography: {value}") from exc


def normalize_discovery_request(
    *,
    industry: str,
    countries: list[str],
    employee_min: int,
    employee_max: int,
    hiring_required: bool,
    keywords: list[str],
    limit: int,
    min_headcount_growth_pct: float | None = None,
    company_types: list[str] | None = None,
) -> DiscoveryRequest:
    parsed_industry = _parse_industry(industry)
    geographies: list[Geography] = []
    for country in countries:
        parsed_geo = _parse_geography(country)
        if parsed_geo not in geographies:
            geographies.append(parsed_geo)
    if not geographies:
        raise PermanentDiscoveryError("At least one country is required.")
    if employee_min < MIN_EMPLOYEES or employee_max > MAX_EMPLOYEES:
        raise PermanentDiscoveryError(
            f"Employee range must stay within SOP bounds {MIN_EMPLOYEES}-{MAX_EMPLOYEES}."
        )
    if employee_min > employee_max:
        raise PermanentDiscoveryError("employee_min cannot exceed employee_max.")
    bounded_limit = max(1, min(limit, 100))
    parsed_types: list[CompanyType] = []
    for item in company_types or []:
        try:
            parsed_types.append(CompanyType(item))
        except ValueError as exc:
            raise PermanentDiscoveryError(f"Unsupported company type: {item}") from exc
    cleaned_keywords = tuple(
        dict.fromkeys(keyword.strip().lower() for keyword in keywords if keyword.strip())
    )
    return DiscoveryRequest(
        industry=parsed_industry,
        countries=tuple(geographies),
        employee_min=employee_min,
        employee_max=employee_max,
        hiring_required=hiring_required,
        keywords=cleaned_keywords,
        limit=bounded_limit,
        min_headcount_growth_pct=min_headcount_growth_pct,
        company_types=tuple(parsed_types),
    )


def discovery_idempotency_key(request: DiscoveryRequest) -> str:
    payload = json.dumps(request.to_payload(), sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"discover_companies:{digest}"


def candidate_idempotency_key(job_id: JobId, source_locator: str) -> str:
    digest = hashlib.sha256(source_locator.encode("utf-8")).hexdigest()[:16]
    return f"discovery_candidate:{job_id}:{digest}"


def candidate_website_url(raw: str | None) -> tuple[str | None, str | None]:
    if not raw or not str(raw).strip():
        return None, None
    try:
        parsed = parse_source_url(str(raw).strip())
    except InvalidSourceUrl:
        return None, None
    return parsed.origin, parsed.identity_host


def candidate_fetch_url(raw: str | None) -> str | None:
    """Normalized permitted URL used for FETCH_SOURCE (may include /careers paths)."""
    if not raw or not str(raw).strip():
        return None
    try:
        return parse_source_url(str(raw).strip()).normalized
    except InvalidSourceUrl:
        return None


def default_field_checks() -> dict[str, str]:
    return {item.field_name: item.provider_support.value for item in PROVIDER_FIELD_SUPPORT}


def provider_support_payload() -> list[dict[str, object]]:
    return [
        {
            "field_name": item.field_name,
            "requested_in_icp": item.requested_in_icp,
            "provider_support": item.provider_support.value,
            "notes": item.notes,
        }
        for item in PROVIDER_FIELD_SUPPORT
    ]
