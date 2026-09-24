"""SerpAPI permitted search provider. Uses the provider API, not HTML scraping."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from prospectiq.domain.common import TenantScope
from prospectiq.domain.discovery import (
    DiscoveryRequest,
    PermanentDiscoveryError,
    ProviderDiscoveryHit,
    RetryableDiscoveryError,
)
from prospectiq.domain.discovery_query import build_discovery_query
from prospectiq.infrastructure.logging import get_logger

logger = get_logger("prospectiq.discovery.serpapi")

SERPAPI_BASE_URL = "https://serpapi.com/search.json"
BLOCKED_RESULT_HOST_SUFFIXES = (
    "linkedin.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "wikipedia.org",
    "instagram.com",
    "tiktok.com",
    "reddit.com",
    "glassdoor.com",
    "indeed.com",
    "monster.com",
    "google.com",
    "bing.com",
)


class SerpApiDiscoveryProvider:
    provider_key = "serpapi"

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float,
        page_size: int,
        max_pages: int,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise PermanentDiscoveryError(
                "SerpAPI credentials are missing. Set PROSPECTIQ_SERPAPI_API_KEY."
            )
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._page_size = max(1, min(page_size, 100))
        self._max_pages = max(1, min(max_pages, 5))
        self._client = client

    async def discover(
        self,
        scope: TenantScope,
        request: DiscoveryRequest,
    ) -> list[ProviderDiscoveryHit]:
        query = build_discovery_query(request)
        logger.info(
            "discovery_provider_query",
            tenant_id=str(scope.tenant_id),
            provider=self.provider_key,
            query=query,
            limit=request.limit,
            operation="discover_companies",
        )
        hits: list[ProviderDiscoveryHit] = []
        seen_locators: set[str] = set()
        start = 0
        pages = 0
        while len(hits) < request.limit and pages < self._max_pages:
            payload = await self._fetch_page(query, start=start)
            organic = payload.get("organic_results") or []
            if not organic:
                break
            for item in organic:
                hit = self._normalize_hit(item)
                if hit is None or hit.source_locator in seen_locators:
                    continue
                seen_locators.add(hit.source_locator)
                hits.append(hit)
                if len(hits) >= request.limit:
                    break
            pages += 1
            start += self._page_size
        return hits[: request.limit]

    async def _fetch_page(self, query: str, *, start: int) -> dict[str, Any]:
        params: dict[str, str | int] = {
            "engine": "google",
            "q": query,
            "api_key": self._api_key,
            "num": self._page_size,
            "start": start,
        }
        try:
            if self._client is not None:
                response = await self._client.get(
                    SERPAPI_BASE_URL,
                    params=params,
                    timeout=self._timeout_seconds,
                )
            else:
                async with httpx.AsyncClient(trust_env=False) as client:
                    response = await client.get(
                        SERPAPI_BASE_URL,
                        params=params,
                        timeout=self._timeout_seconds,
                    )
        except httpx.TimeoutException as exc:
            raise RetryableDiscoveryError("SerpAPI request timed out.") from exc
        except httpx.TransportError as exc:
            raise RetryableDiscoveryError("SerpAPI network failure.") from exc
        return self._parse_response(response)

    def _parse_response(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code == 429:
            raise RetryableDiscoveryError("SerpAPI rate limit reached (429).")
        if response.status_code in {500, 502, 503, 504}:
            raise RetryableDiscoveryError(f"SerpAPI temporary failure ({response.status_code}).")
        if response.status_code in {401, 403}:
            raise PermanentDiscoveryError("SerpAPI authentication failed.")
        if response.status_code >= 400:
            raise PermanentDiscoveryError(f"SerpAPI rejected the request ({response.status_code}).")
        try:
            payload = response.json()
        except ValueError as exc:
            raise PermanentDiscoveryError("SerpAPI returned malformed JSON.") from exc
        if not isinstance(payload, dict):
            raise PermanentDiscoveryError("SerpAPI returned an unexpected payload.")
        error = payload.get("error")
        if error:
            message = str(error)
            if "Invalid API key" in message or "Unauthorized" in message:
                raise PermanentDiscoveryError("SerpAPI authentication failed.")
            raise PermanentDiscoveryError(f"SerpAPI error: {message}")
        return payload

    def _normalize_hit(self, item: dict[str, Any]) -> ProviderDiscoveryHit | None:
        link = str(item.get("link") or "").strip()
        if not link:
            return None
        host = (urlparse(link).hostname or "").lower().removeprefix("www.")
        if not host or self._is_blocked_host(host):
            return None
        title = str(item.get("title") or host).strip()
        position = item.get("position")
        rank = int(position) if isinstance(position, int) else None
        return ProviderDiscoveryHit(
            name=title[:512],
            website=link,
            domain=host,
            source_locator=link,
            confidence="medium",
            provider_rank=rank,
            raw_reference={
                "title": item.get("title"),
                "snippet": item.get("snippet"),
                "position": position,
            },
        )

    @staticmethod
    def _is_blocked_host(host: str) -> bool:
        return any(
            host == suffix or host.endswith(f".{suffix}")
            for suffix in BLOCKED_RESULT_HOST_SUFFIXES
        )
