"""Unit tests for deterministic research page planning and classification."""

from __future__ import annotations

from prospectiq.domain.company_research import ResearchPageType
from prospectiq.domain.research_plan import (
    build_initial_plan,
    classify_page_type,
    is_blocked_external_host,
    is_same_domain,
    merge_discovered_pages,
    normalize_research_url,
)


def test_classify_page_type_from_path() -> None:
    assert classify_page_type(path="/") is ResearchPageType.HOME
    assert classify_page_type(path="/about") is ResearchPageType.ABOUT
    assert classify_page_type(path="/products/widget") is ResearchPageType.PRODUCTS
    assert classify_page_type(path="/services") is ResearchPageType.SERVICES
    assert classify_page_type(path="/careers") is ResearchPageType.CAREERS
    assert classify_page_type(path="/jobs/open") is ResearchPageType.CAREERS
    assert classify_page_type(path="/blog/post") is ResearchPageType.BLOG
    assert classify_page_type(path="/random") is ResearchPageType.OTHER


def test_classify_page_type_from_anchor_and_title() -> None:
    assert classify_page_type(path="/team", anchor="About our team") is ResearchPageType.ABOUT
    assert classify_page_type(path="/x", title="Contact Us") is ResearchPageType.CONTACT


def test_same_domain_policy() -> None:
    assert is_same_domain("https://acme.test/about", "acme.test")
    assert is_same_domain("https://www.acme.test/about", "acme.test")
    assert is_same_domain("https://sub.acme.test/page", "acme.test")
    assert not is_same_domain("https://other.test/page", "acme.test")


def test_blocked_external_hosts() -> None:
    assert is_blocked_external_host("https://linkedin.com/company/acme")
    assert is_blocked_external_host("https://www.facebook.com/acme")
    assert not is_blocked_external_host("https://acme.test/about")


def test_normalize_research_url_strips_fragments_and_mailto() -> None:
    base = "https://acme.test/"
    assert normalize_research_url(base, "/about") == "https://acme.test/about"
    assert normalize_research_url(base, "mailto:hi@acme.test") is None
    assert normalize_research_url(base, "#section") is None


def test_build_initial_plan_only_homepage() -> None:
    plan = build_initial_plan("https://acme.test", max_pages=10)
    assert len(plan) == 1
    assert plan[0].page_type is ResearchPageType.HOME


def test_merge_discovered_pages_respects_max_and_priority() -> None:
    discovered = [
        ("https://acme.test/blog", "Blog"),
        ("https://acme.test/about", "About"),
        ("https://acme.test/services", "Services"),
        ("https://acme.test/contact", "Contact"),
        ("https://acme.test/products", "Products"),
        ("https://linkedin.com/company/acme", "LinkedIn"),
        ("https://other.test/page", "Other"),
    ]
    plan = merge_discovered_pages(
        homepage_url="https://acme.test",
        identity_host="acme.test",
        discovered=discovered,
        max_pages=4,
    )
    urls = [item.normalized_url for item in plan]
    assert len(urls) == 4
    assert "https://acme.test" in urls
    assert "https://acme.test/about" in urls
    assert all("linkedin.com" not in url for url in urls)
    assert all("other.test" not in url for url in urls)
