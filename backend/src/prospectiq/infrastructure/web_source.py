"""Permitted company-website / careers-page adapter."""

from __future__ import annotations

from prospectiq.application.ports import FetchRequest, NormalizedRecord
from prospectiq.domain.common import utcnow
from prospectiq.domain.ingestion import observe_hiring_language
from prospectiq.domain.source_registry import SourceClass
from prospectiq.domain.source_url import parse_source_url
from prospectiq.infrastructure.html_normalize import normalize_page
from prospectiq.infrastructure.http_fetch import FetchLimits, SafeHttpFetcher


class HttpPageSourceAdapter:
    adapter_key = "http_company_page"

    def __init__(
        self,
        fetcher: SafeHttpFetcher,
        source_class: SourceClass,
        adapter_key: str | None = None,
    ) -> None:
        self._fetcher = fetcher
        self.source_class = source_class
        if adapter_key is not None:
            self.adapter_key = adapter_key
        elif source_class is SourceClass.CAREERS_PAGE:
            self.adapter_key = "http_careers_page"
        else:
            self.adapter_key = "http_company_website"

    async def fetch(self, request: FetchRequest) -> list[NormalizedRecord]:
        parsed = parse_source_url(request.locator)
        fetched = await self._fetcher.get(parsed.normalized)
        page = normalize_page(fetched.body, fetched.content_type)
        collected_at = utcnow()
        metadata = {
            "requested_url": fetched.requested_url,
            "final_url": fetched.final_url,
            "http_status": fetched.status_code,
            "content_type": fetched.content_type,
            "title": page.title,
            "headings": page.headings,
            "fetch_duration_ms": fetched.duration_ms,
            "source_class": parsed.source_class.value,
            "identity_host": parsed.identity_host,
            "identity_requires_review": parsed.identity_requires_review,
        }
        records = [
            NormalizedRecord(
                fact=_page_fact(page),
                locator=parsed.normalized,
                snippet=page.text[:500] or None,
                collected_at=collected_at,
                confidence="high",
                metadata={**metadata, "fact_kind": "page_content"},
            )
        ]
        observed = observe_hiring_language(page.text)
        if parsed.source_class is SourceClass.CAREERS_PAGE and observed:
            records.append(
                NormalizedRecord(
                    fact="Page contains hiring language: " + ", ".join(observed) + ".",
                    locator=parsed.normalized,
                    snippet=", ".join(observed),
                    collected_at=collected_at,
                    confidence="medium",
                    metadata={
                        **metadata,
                        "fact_kind": "hiring_language_observed",
                        "observed_hiring_phrases": observed,
                        "is_inferred_signal": False,
                    },
                )
            )
        return records


def build_http_page_adapter(
    source_class: SourceClass,
    limits: FetchLimits,
    *,
    fetcher: SafeHttpFetcher | None = None,
) -> HttpPageSourceAdapter:
    return HttpPageSourceAdapter(fetcher or SafeHttpFetcher(limits), source_class)


def _page_fact(page: object) -> str:
    title = getattr(page, "title", None)
    text = getattr(page, "text", "")
    if title:
        return f"Company page titled '{title}': {text}"[:4000]
    return f"Company page content: {text}"[:4000]
