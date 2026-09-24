"""Build the configured company-discovery provider."""

from __future__ import annotations

import httpx

from prospectiq.application.ports import CompanyDiscoveryProvider
from prospectiq.domain.discovery import PermanentDiscoveryError
from prospectiq.infrastructure.config import Settings
from prospectiq.infrastructure.discovery.serpapi_provider import SerpApiDiscoveryProvider


def build_discovery_provider(
    settings: Settings,
    *,
    client: httpx.AsyncClient | None = None,
) -> CompanyDiscoveryProvider:
    provider = settings.discovery_provider.lower().strip()
    if provider in {"", "none"}:
        raise PermanentDiscoveryError(
            "Discovery provider is not configured. Set PROSPECTIQ_DISCOVERY_PROVIDER."
        )
    if provider == "serpapi":
        return SerpApiDiscoveryProvider(
            api_key=settings.serpapi_api_key.get_secret_value(),
            timeout_seconds=settings.discovery_timeout_seconds,
            page_size=settings.discovery_page_size,
            max_pages=settings.discovery_max_pages,
            client=client,
        )
    raise PermanentDiscoveryError(f"Unsupported discovery provider: {provider}")
