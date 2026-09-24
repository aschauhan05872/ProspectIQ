"""Company resolution from imported prospect data. No LinkedIn scraping."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from prospectiq.domain.common import CompanyId
from prospectiq.domain.import_normalization import normalize_domain, normalize_website_url
from prospectiq.domain.prospect_import import ResolutionStatus


class ResolutionMethod(StrEnum):
    COMPANY_DOMAIN = "company_domain"
    WEBSITE = "website"
    COMPANY_NAME = "company_name"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class ResolutionInput:
    company_name: str | None
    company_domain: str | None
    website: str | None
    company_linkedin: str | None = None


@dataclass(frozen=True, slots=True)
class ResolutionPlan:
    """Deterministic plan for linking an imported prospect to a company."""

    status: ResolutionStatus
    method: ResolutionMethod
    normalized_domain: str | None
    normalized_website: str | None
    normalized_name: str | None
    notes: str


def plan_company_resolution(data: dict[str, Any]) -> ResolutionPlan:
    """Decide how to resolve company identity without network I/O."""
    domain = normalize_domain(data.get("company_domain") or data.get("website"))
    website = normalize_website_url(data.get("website"))
    name = (data.get("company_name") or "").strip() or None

    if domain:
        return ResolutionPlan(
            status=ResolutionStatus.RESOLVED,
            method=ResolutionMethod.COMPANY_DOMAIN,
            normalized_domain=domain,
            normalized_website=website or f"https://{domain}",
            normalized_name=domain,
            notes="Resolved via normalized company domain.",
        )

    if website:
        host = normalize_domain(website)
        if host:
            return ResolutionPlan(
                status=ResolutionStatus.RESOLVED,
                method=ResolutionMethod.WEBSITE,
                normalized_domain=host,
                normalized_website=website,
                normalized_name=host,
                notes="Resolved via explicit website URL.",
            )

    if name:
        slug = name.lower().strip()
        if len(slug) < 2:
            return ResolutionPlan(
                status=ResolutionStatus.NOT_FOUND,
                method=ResolutionMethod.NONE,
                normalized_domain=None,
                normalized_website=None,
                normalized_name=None,
                notes="Company name too short to resolve.",
            )
        return ResolutionPlan(
            status=ResolutionStatus.MANUAL_REVIEW,
            method=ResolutionMethod.COMPANY_NAME,
            normalized_domain=None,
            normalized_website=None,
            normalized_name=slug,
            notes="No domain/website; requires manual review or permitted search.",
        )

    return ResolutionPlan(
        status=ResolutionStatus.NOT_FOUND,
        method=ResolutionMethod.NONE,
        normalized_domain=None,
        normalized_website=None,
        normalized_name=None,
        notes="Insufficient company identifiers.",
    )


@dataclass(frozen=True, slots=True)
class CompanyResolutionResult:
    company_id: CompanyId | None
    status: ResolutionStatus
    method: ResolutionMethod
    created_new: bool
    notes: str
