from __future__ import annotations

import pytest

from prospectiq.domain.compliance import LinkedInComplianceError, assert_capability_allowed
from prospectiq.domain.source_registry import RegisteredAdapter, SourceClass, SourceRegistry
from prospectiq.infrastructure.providers import (
    DisabledOfficialLinkedInAdapter,
    build_source_registry,
)


def test_forbidden_adapter_keys_are_rejected() -> None:
    with pytest.raises(LinkedInComplianceError):
        assert_capability_allowed(adapter_key="linkedin_scrape_jobs")
    with pytest.raises(LinkedInComplianceError):
        assert_capability_allowed(adapter_key="playwright_linkedin")
    with pytest.raises(LinkedInComplianceError):
        assert_capability_allowed(adapter_key="news_api", automates_linkedin_engagement=True)
    with pytest.raises(LinkedInComplianceError):
        assert_capability_allowed(adapter_key="sales_nav", uses_linkedin_credentials=True)


def test_registry_rejects_unofficial_linkedin_and_allows_permitted_sources() -> None:
    registry = SourceRegistry()
    with pytest.raises(LinkedInComplianceError):
        registry.register(
            RegisteredAdapter("official_linkedin", SourceClass.OFFICIAL_LINKEDIN, True),
            official_linkedin_authorized=False,
        )
    registry.register(
        RegisteredAdapter("null_public_news", SourceClass.PUBLIC_NEWS, True),
    )
    assert registry.get("null_public_news") is not None


def test_default_registry_does_not_enable_linkedin() -> None:
    registry = build_source_registry(official_linkedin_authorized=False)
    assert registry.get("official_linkedin") is None
    assert any(item.source_class is SourceClass.CAREERS_PAGE for item in registry.enabled())


@pytest.mark.asyncio
async def test_official_linkedin_adapter_stays_disabled() -> None:
    adapter = DisabledOfficialLinkedInAdapter()
    with pytest.raises(LinkedInComplianceError):
        await adapter.fetch(request=None)  # type: ignore[arg-type]
