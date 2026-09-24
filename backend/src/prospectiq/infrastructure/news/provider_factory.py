"""News provider factory."""

from __future__ import annotations

from prospectiq.application.ports import CompanyNewsProvider
from prospectiq.infrastructure.config import Settings
from prospectiq.infrastructure.news.serpapi_news import SerpApiNewsProvider


def build_news_provider(settings: Settings) -> CompanyNewsProvider | None:
    provider = settings.news_provider.lower().strip()
    if provider in {"", "none"}:
        return None
    if provider == "serpapi":
        return SerpApiNewsProvider(
            api_key=settings.serpapi_api_key.get_secret_value(),
            timeout_seconds=settings.discovery_timeout_seconds,
            max_results=settings.news_max_results,
        )
    raise ValueError(f"Unsupported news provider: {settings.news_provider}")
