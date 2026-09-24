"""Permitted-source adapters. Provider specifics stay out of the domain."""

from __future__ import annotations

from prospectiq.application.ports import FetchRequest, NormalizedRecord, SourceAdapter
from prospectiq.domain.compliance import LinkedInComplianceError
from prospectiq.domain.source_registry import (
    RegisteredAdapter,
    SourceClass,
    SourceRegistry,
)


class DisabledOfficialLinkedInAdapter:
    """Placeholder for an authorized official integration. Disabled in V0."""

    adapter_key = "official_linkedin"
    source_class = SourceClass.OFFICIAL_LINKEDIN

    async def fetch(self, request: FetchRequest) -> list[NormalizedRecord]:
        raise LinkedInComplianceError(
            "Official LinkedIn integration is not authorized in V0. "
            "LinkedIn execution remains human-controlled."
        )


class NullSourceAdapter:
    """Safe no-op adapter used until a real permitted provider is configured."""

    def __init__(self, adapter_key: str, source_class: SourceClass) -> None:
        self.adapter_key = adapter_key
        self.source_class = source_class

    async def fetch(self, request: FetchRequest) -> list[NormalizedRecord]:
        return []


def build_source_registry(*, official_linkedin_authorized: bool = False) -> SourceRegistry:
    registry = SourceRegistry()
    registry.register(
        RegisteredAdapter(
            adapter_key="http_company_website",
            source_class=SourceClass.COMPANY_WEBSITE,
            is_enabled=True,
            rate_limit_per_minute=20,
        )
    )
    registry.register(
        RegisteredAdapter(
            adapter_key="http_careers_page",
            source_class=SourceClass.CAREERS_PAGE,
            is_enabled=True,
            rate_limit_per_minute=20,
        )
    )
    for source_class in (
        SourceClass.PUBLIC_ANNOUNCEMENT,
        SourceClass.PUBLIC_NEWS,
        SourceClass.PUBLIC_FUNDING,
        SourceClass.PERMITTED_SEARCH_API,
        SourceClass.LICENSED_DATA_PROVIDER,
    ):
        registry.register(
            RegisteredAdapter(
                adapter_key=f"null_{source_class.value}",
                source_class=source_class,
                is_enabled=True,
                rate_limit_per_minute=30,
            )
        )
    if official_linkedin_authorized:
        registry.register(
            RegisteredAdapter(
                adapter_key="official_linkedin",
                source_class=SourceClass.OFFICIAL_LINKEDIN,
                is_enabled=True,
            ),
            official_linkedin_authorized=True,
        )
    return registry


def adapter_for(source_class: SourceClass) -> SourceAdapter:
    if source_class is SourceClass.OFFICIAL_LINKEDIN:
        return DisabledOfficialLinkedInAdapter()
    if source_class in {SourceClass.COMPANY_WEBSITE, SourceClass.CAREERS_PAGE}:
        from prospectiq.infrastructure.http_fetch import FetchLimits, SafeHttpFetcher
        from prospectiq.infrastructure.web_source import HttpPageSourceAdapter

        key = (
            "http_careers_page"
            if source_class is SourceClass.CAREERS_PAGE
            else "http_company_website"
        )
        return HttpPageSourceAdapter(SafeHttpFetcher(FetchLimits()), source_class, key)
    return NullSourceAdapter(f"null_{source_class.value}", source_class)
