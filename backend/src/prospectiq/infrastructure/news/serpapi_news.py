"""SerpAPI Google News provider. Uses the permitted JSON API, not HTML scraping."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import httpx

from prospectiq.application.ports import NewsRecord
from prospectiq.domain.common import TenantScope
from prospectiq.domain.company import Company
from prospectiq.domain.detection import EXPANSION_FACT_KIND, FUNDING_FACT_KIND
from prospectiq.domain.news import PermanentNewsError, RetryableNewsError
from prospectiq.domain.source_registry import SourceClass
from prospectiq.infrastructure.logging import get_logger

logger = get_logger("prospectiq.news.serpapi")

SERPAPI_BASE_URL = "https://serpapi.com/search.json"

FUNDING_PATTERN = re.compile(
    r"\b(?:raised|raises|funding|investment|series [a-e]|seed round|venture capital|"
    r"led by|million|billion)\b",
    re.IGNORECASE,
)
EXPANSION_PATTERN = re.compile(
    r"\b(?:expansion|expands|new office|product launch|launches|opening in|"
    r"market entry|grand opening)\b",
    re.IGNORECASE,
)


class SerpApiNewsProvider:
    provider_key = "serpapi"

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float,
        max_results: int,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise PermanentNewsError(
                "SerpAPI credentials are missing. Set PROSPECTIQ_SERPAPI_API_KEY."
            )
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._max_results = max(1, min(max_results, 20))
        self._client = client

    async def fetch_company_news(
        self,
        scope: TenantScope,
        company: Company,
    ) -> list[NewsRecord]:
        query = f'"{company.name}" funding OR expansion OR launch'
        if company.normalized_name:
            query = f'"{company.name}" OR {company.normalized_name} funding OR launch'
        logger.info(
            "news_provider_query",
            tenant_id=str(scope.tenant_id),
            company_id=str(company.id),
            provider=self.provider_key,
            query=query,
            operation="fetch_company_news",
        )
        params: dict[str, str | int] = {
            "engine": "google_news",
            "q": query,
            "api_key": self._api_key,
            "num": self._max_results,
        }
        own_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout_seconds)
        try:
            response = await client.get(SERPAPI_BASE_URL, params=params)
        except httpx.TimeoutException as exc:
            raise RetryableNewsError("SerpAPI news request timed out.") from exc
        except httpx.HTTPError as exc:
            raise RetryableNewsError(f"SerpAPI news network error: {exc}") from exc
        finally:
            if own_client:
                await client.aclose()
        if response.status_code == 429 or response.status_code >= 500:
            raise RetryableNewsError(f"SerpAPI news HTTP {response.status_code}.")
        if response.status_code >= 400:
            raise PermanentNewsError(f"SerpAPI news HTTP {response.status_code}.")
        payload = response.json()
        if not isinstance(payload, dict):
            raise PermanentNewsError("SerpAPI news returned malformed JSON.")
        return _records_from_payload(payload, company_name=company.name)


def _records_from_payload(payload: dict[str, Any], *, company_name: str) -> list[NewsRecord]:
    news_results = payload.get("news_results") or []
    if not isinstance(news_results, list):
        return []
    now = datetime.now(tz=UTC)
    records: list[NewsRecord] = []
    seen_headlines: set[str] = set()
    for item in news_results:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        link = str(item.get("link") or item.get("source") or "").strip()
        snippet = str(item.get("snippet") or item.get("description") or "")[:2000]
        if not title or not link:
            continue
        headline_key = title.lower()
        if headline_key in seen_headlines:
            continue
        seen_headlines.add(headline_key)
        text = f"{title} {snippet}"
        fact_kind: str | None = None
        source_class = SourceClass.PUBLIC_NEWS
        if FUNDING_PATTERN.search(text):
            fact_kind = FUNDING_FACT_KIND
            source_class = SourceClass.PUBLIC_FUNDING
        elif EXPANSION_PATTERN.search(text):
            fact_kind = EXPANSION_FACT_KIND
            source_class = SourceClass.PUBLIC_ANNOUNCEMENT
        else:
            continue
        records.append(
            NewsRecord(
                fact=f"{company_name}: {title}",
                locator=link,
                snippet=snippet or None,
                collected_at=now,
                confidence="medium",
                source_class=source_class,
                metadata={
                    "fact_kind": fact_kind,
                    "headline": title,
                    "provider_key": "serpapi",
                    "provider_engine": "google_news",
                },
            )
        )
    return records
