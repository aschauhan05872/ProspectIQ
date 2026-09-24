"""Unit tests for discovery candidate validation (WS6.2B)."""

from __future__ import annotations

from prospectiq.domain.discovery import ProviderDiscoveryHit
from prospectiq.domain.discovery_candidate_validation import (
    CandidateQualityClass,
    CandidateRejectReason,
    validate_discovery_hit,
)


def _hit(url: str, name: str = "Example") -> ProviderDiscoveryHit:
    return ProviderDiscoveryHit(
        name=name,
        website=url,
        domain=None,
        source_locator=url,
    )


def test_rejects_government_domains() -> None:
    result = validate_discovery_hit(_hit("https://ftc.gov/business-guidance/credit-finance/fintech"))
    assert not result.accepted
    assert result.quality_class is CandidateQualityClass.GOVERNMENT_REGULATORY
    assert result.reject_reason is CandidateRejectReason.GOVERNMENT_TLD


def test_rejects_house_government_page() -> None:
    result = validate_discovery_hit(
        _hit("https://financialservices.house.gov/calendar/eventsingle.aspx?EventID=1")
    )
    assert not result.accepted
    assert result.quality_class is CandidateQualityClass.GOVERNMENT_REGULATORY


def test_rejects_investopedia_media() -> None:
    result = validate_discovery_hit(_hit("https://www.investopedia.com/terms/f/fintech.asp"))
    assert not result.accepted
    assert result.quality_class is CandidateQualityClass.MEDIA_EDUCATIONAL


def test_rejects_ibm_think_content_page() -> None:
    result = validate_discovery_hit(_hit("https://www.ibm.com/think/topics/fintech"))
    assert not result.accepted
    assert result.quality_class is CandidateQualityClass.CONTENT_PAGE
    assert result.reject_reason is CandidateRejectReason.CONTENT_PATH


def test_rejects_plaid_resources_page() -> None:
    result = validate_discovery_hit(_hit("https://plaid.com/resources/fintech/what-is-fintech"))
    assert not result.accepted
    assert result.quality_class is CandidateQualityClass.CONTENT_PAGE


def test_accepts_company_root_domain() -> None:
    result = validate_discovery_hit(_hit("https://stripe.com"))
    assert result.accepted
    assert result.quality_class is CandidateQualityClass.VALID_COMPANY


def test_accepts_company_careers_page() -> None:
    result = validate_discovery_hit(_hit("https://www.chime.com/careers"))
    assert result.accepted
    assert result.quality_class is CandidateQualityClass.VALID_COMPANY


def test_accepts_fintech_com_root_as_company_domain() -> None:
    result = validate_discovery_hit(_hit("https://fintech.com"))
    assert result.accepted
    assert result.quality_class is CandidateQualityClass.VALID_COMPANY
