"""Permitted source classes and source policies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from prospectiq.domain.common import TenantId
from prospectiq.domain.compliance import LinkedInComplianceError, assert_capability_allowed


class SourceClass(StrEnum):
    COMPANY_WEBSITE = "company_website"
    CAREERS_PAGE = "careers_page"
    PUBLIC_ANNOUNCEMENT = "public_announcement"
    PUBLIC_NEWS = "public_news"
    PUBLIC_FUNDING = "public_funding"
    PERMITTED_SEARCH_API = "permitted_search_api"
    LICENSED_DATA_PROVIDER = "licensed_data_provider"
    CSV_DATA_PROVIDER = "csv_data_provider"
    OFFICIAL_LINKEDIN = "official_linkedin"


PERMITTED_SOURCE_CLASSES: frozenset[SourceClass] = frozenset(
    {
        SourceClass.COMPANY_WEBSITE,
        SourceClass.CAREERS_PAGE,
        SourceClass.PUBLIC_ANNOUNCEMENT,
        SourceClass.PUBLIC_NEWS,
        SourceClass.PUBLIC_FUNDING,
        SourceClass.PERMITTED_SEARCH_API,
        SourceClass.LICENSED_DATA_PROVIDER,
        SourceClass.CSV_DATA_PROVIDER,
    }
)


@dataclass(frozen=True, slots=True)
class SourcePolicy:
    id: UUID
    source_class: SourceClass
    is_permitted: bool
    requires_official_integration: bool
    tenant_id: TenantId | None
    notes: str
    created_at: datetime


@dataclass(slots=True)
class RegisteredAdapter:
    adapter_key: str
    source_class: SourceClass
    is_enabled: bool
    rate_limit_per_minute: int | None = None


class SourceRegistry:
    """In-process registry. Persistence of policies is an infrastructure concern."""

    def __init__(self) -> None:
        self._adapters: dict[str, RegisteredAdapter] = {}

    def register(
        self,
        adapter: RegisteredAdapter,
        *,
        official_linkedin_authorized: bool = False,
        uses_linkedin_credentials: bool = False,
        automates_linkedin_engagement: bool = False,
    ) -> None:
        claims_official = adapter.source_class is SourceClass.OFFICIAL_LINKEDIN
        assert_capability_allowed(
            adapter_key=adapter.adapter_key,
            uses_linkedin_credentials=uses_linkedin_credentials,
            automates_linkedin_engagement=automates_linkedin_engagement,
            official_linkedin_authorized=official_linkedin_authorized,
            claims_official_linkedin=claims_official,
        )
        if (
            adapter.source_class is SourceClass.OFFICIAL_LINKEDIN
            and not official_linkedin_authorized
        ):
            raise LinkedInComplianceError(
                "Cannot enable an official LinkedIn adapter without authorization."
            )
        if adapter.source_class not in PERMITTED_SOURCE_CLASSES and not (
            claims_official and official_linkedin_authorized
        ):
            raise LinkedInComplianceError(
                f"Source class {adapter.source_class} is not a permitted automated source."
            )
        self._adapters[adapter.adapter_key] = adapter

    def get(self, adapter_key: str) -> RegisteredAdapter | None:
        return self._adapters.get(adapter_key)

    def enabled(self) -> list[RegisteredAdapter]:
        return [adapter for adapter in self._adapters.values() if adapter.is_enabled]


def default_source_policies(*, now: datetime) -> list[dict[str, object]]:
    """Canonical V0 policy rows. Official LinkedIn stays disabled."""

    notes = {
        SourceClass.COMPANY_WEBSITE: "Public company website content.",
        SourceClass.CAREERS_PAGE: "Public careers/jobs pages.",
        SourceClass.PUBLIC_ANNOUNCEMENT: "Public company announcements.",
        SourceClass.PUBLIC_NEWS: "Public news sources.",
        SourceClass.PUBLIC_FUNDING: "Public funding/news sources.",
        SourceClass.PERMITTED_SEARCH_API: "Explicitly permitted search/data APIs.",
        SourceClass.LICENSED_DATA_PROVIDER: "Licensed business-information providers.",
        SourceClass.CSV_DATA_PROVIDER: "Permitted CSV/data-provider exports (Apollo-style).",
        SourceClass.OFFICIAL_LINKEDIN: "Official LinkedIn API only when authorized.",
    }
    rows: list[dict[str, object]] = []
    for source_class in SourceClass:
        official = source_class is SourceClass.OFFICIAL_LINKEDIN
        rows.append(
            {
                "source_class": source_class,
                "is_permitted": not official,
                "requires_official_integration": official,
                "notes": notes[source_class],
                "created_at": now,
            }
        )
    return rows


@dataclass(slots=True)
class RateLimitState:
    adapter_key: str
    window_started_at: datetime
    requests_in_window: int = 0
    extra: dict[str, object] = field(default_factory=dict)
