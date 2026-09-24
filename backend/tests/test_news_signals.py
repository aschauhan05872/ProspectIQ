"""Phase 4–5: funding/expansion news signal detection."""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from prospectiq.domain.common import CompanyId
from prospectiq.domain.company import Company
from prospectiq.domain.detection import (
    EXPANSION_FACT_KIND,
    FUNDING_FACT_KIND,
    SignalDetectionService,
)
from prospectiq.domain.signal import SignalType
from prospectiq.infrastructure.news.serpapi_news import SerpApiNewsProvider, _records_from_payload
from tests.fixtures.validation_dataset import NOW, TENANT, _expansion_evidence, _funding_evidence


def test_funding_news_detected_from_permitted_evidence() -> None:
    company = CompanyId(uuid4())
    evidence = _funding_evidence(company, headline="Raised", event_suffix="x")
    detected = SignalDetectionService().detect([evidence])
    assert len(detected) == 1
    assert detected[0].signal_type is SignalType.FUNDING_NEWS


def test_expansion_launch_detected_from_permitted_evidence() -> None:
    company = CompanyId(uuid4())
    detected = SignalDetectionService().detect(
        [_expansion_evidence(company, headline="Product launch", event_suffix="x")]
    )
    assert len(detected) == 1
    assert detected[0].signal_type is SignalType.EXPANSION_LAUNCH


def test_serpapi_news_payload_classification() -> None:
    payload = {
        "news_results": [
            {
                "title": "Acme raises $20M Series B led by Example VC",
                "link": "https://permitted-news.test/acme-series-b",
                "snippet": "Funding round completed.",
            },
            {
                "title": "Acme launches expansion into Europe",
                "link": "https://permitted-news.test/acme-eu",
                "snippet": "Market entry announced.",
            },
            {
                "title": "Acme mentions technology in annual report",
                "link": "https://permitted-news.test/generic",
                "snippet": "Generic copy only.",
            },
        ]
    }
    records = _records_from_payload(payload, company_name="Acme")
    kinds = {item.metadata.get("fact_kind") for item in records}
    assert FUNDING_FACT_KIND in kinds
    assert EXPANSION_FACT_KIND in kinds
    assert len(records) == 2


@pytest.mark.asyncio
async def test_serpapi_news_provider_mock_http() -> None:
    payload = {
        "news_results": [
            {
                "title": "Beta Corp raised seed funding",
                "link": "https://permitted-news.test/beta",
                "snippet": "Investment announced.",
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    provider = SerpApiNewsProvider(
        api_key="test-key",
        timeout_seconds=5,
        max_results=5,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    company = Company(
        id=CompanyId(uuid4()),
        tenant_id=TENANT,
        name="Beta Corp",
        normalized_name="beta.test",
        website="https://beta.test",
        industry=None,
        geography=None,
        employee_count=None,
        headcount_growth_pct=None,
        company_type=None,
        is_hiring=None,
        created_at=NOW,
        updated_at=NOW,
    )
    from prospectiq.domain.common import TenantScope

    records = await provider.fetch_company_news(TenantScope(tenant_id=TENANT), company)
    assert len(records) == 1
    assert records[0].metadata.get("fact_kind") == FUNDING_FACT_KIND
