"""Unit tests for Phase 5 deterministic fact extraction rules."""

from __future__ import annotations

from collections import Counter
from uuid import uuid4

from prospectiq.domain.common import CompanyId, EvidenceId
from prospectiq.domain.company_facts import (
    CompanyFactCategory,
    CompanyFactTier,
    EvidencePageContext,
    compute_fact_dedupe_key,
)
from prospectiq.domain.fact_extraction_rules import (
    ExtractionBatchState,
    extract_deterministic_facts,
    is_acceptable_page_title,
    leading_headings,
    normalize_title_key,
)
from prospectiq.infrastructure.fact_extraction.deterministic_extractor import (
    DeterministicEvidenceFactExtractor,
)
from tests.fixtures.intermark_evidence import intermark_evidence_contexts


def _ctx(
    *,
    text: str,
    title: str | None = None,
    locator: str = "https://acme.test/page",
) -> EvidencePageContext:
    return EvidencePageContext(
        evidence_id=EvidenceId(uuid4()),
        company_id=CompanyId(uuid4()),
        source_locator=locator,
        page_type="other",
        title=title,
        text=text,
    )


def test_office_list_extraction() -> None:
    context = _ctx(
        locator="https://acme.test/contacts",
        text="Offices United Kingdom London United Arab Emirates Dubai Thailand Phuket",
    )
    facts = extract_deterministic_facts(context)
    offices = [f for f in facts if f.subject == "office_location"]
    assert len(offices) >= 2
    values = {item.value for item in offices}
    assert "United Kingdom London" in values
    assert "United Arab Emirates Dubai" in values


def test_location_phrase_extraction() -> None:
    context = _ctx(text="We are based in Dubai and growing.")
    facts = extract_deterministic_facts(context)
    assert any(f.subject == "operating_location" and "Dubai" in f.value for f in facts)


def test_offices_count_extraction() -> None:
    context = _ctx(text="With 7 offices across the region.")
    facts = extract_deterministic_facts(context)
    offices = [
        f
        for f in facts
        if f.category is CompanyFactCategory.ORGANIZATION and f.subject == "offices"
    ]
    assert len(offices) == 1
    assert offices[0].value == "7"


def test_partners_count_preserves_plus() -> None:
    context = _ctx(text="Over 500+ partners worldwide.")
    facts = extract_deterministic_facts(context)
    partners = [f for f in facts if f.subject == "partners"]
    assert partners
    assert partners[0].value == "500+"


def test_partners_count_over_prefix_adds_plus() -> None:
    context = _ctx(text="With 7 offices, over 500 partner globally we serve clients.")
    facts = extract_deterministic_facts(context)
    partners = [f for f in facts if f.subject == "partners"]
    assert partners
    assert partners[0].value == "500+"


def test_events_page_activity_extraction() -> None:
    context = _ctx(
        locator="https://acme.test/events",
        text="Events\nAnnual investment forum for partners",
    )
    facts = extract_deterministic_facts(context)
    assert any(
        f.category is CompanyFactCategory.ACTIVITY and f.subject == "content_channel"
        for f in facts
    )


def test_webinar_activity_extraction() -> None:
    context = _ctx(
        locator="https://acme.test/events/summit",
        text="Upcoming webinar on market trends\nAbout event",
    )
    facts = extract_deterministic_facts(context)
    assert any(f.subject == "activity_type" and f.value == "webinar" for f in facts)


def test_expert_blog_activity_extraction() -> None:
    context = _ctx(
        locator="https://acme.test/expert-blog",
        text="Blog\nAll materials\nMarket insights for investors",
    )
    facts = extract_deterministic_facts(context)
    channels = [f for f in facts if f.subject == "content_channel"]
    assert any(item.value == "expert_blog" for item in channels)


def test_event_title_from_headings() -> None:
    context = _ctx(
        locator="https://acme.test/events/1",
        title="INTERMARK GLOBAL. Real Estate for life, investments and immigration",
        text=(
            "Financial breakthrough: The path to smart investments\n"
            "About event\nProgram details"
        ),
    )
    facts = extract_deterministic_facts(context)
    names = [f for f in facts if f.subject == "activity_name"]
    assert names
    assert "Financial breakthrough" in names[0].value


def test_month_only_title_rejection() -> None:
    batch = ExtractionBatchState(title_counts=Counter())
    assert not is_acceptable_page_title(
        "May",
        source_locator="https://acme.test/events/4",
        batch=batch,
    )


def test_repeated_generic_title_rejection() -> None:
    batch = ExtractionBatchState(title_counts=Counter())
    title = "INTERMARK GLOBAL. Real Estate for life, investments and immigration"
    batch.title_counts[normalize_title_key(title)] = 2
    assert not is_acceptable_page_title(
        title,
        source_locator="https://acme.test/events/2",
        batch=batch,
    )


def test_unsupported_geography_not_invented() -> None:
    context = _ctx(text="Welcome to our corporate website.")
    facts = extract_deterministic_facts(context)
    assert not any(f.category is CompanyFactCategory.GEOGRAPHY for f in facts)


def test_unsupported_organization_scale_not_invented() -> None:
    context = _ctx(text="We are a leading company in our sector.")
    facts = extract_deterministic_facts(context)
    assert not any(f.category is CompanyFactCategory.ORGANIZATION for f in facts)


def test_provenance_for_new_facts() -> None:
    context = _ctx(
        locator="https://acme.test/contacts",
        text="Offices United Kingdom London Email sales@acme.test",
    )
    facts = extract_deterministic_facts(context)
    assert facts
    assert all(context.evidence_id in fact.evidence_ids for fact in facts)
    assert all(fact.origin.value == "source_derived" for fact in facts)


def test_dedupe_stability_includes_tier() -> None:
    evidence_id = EvidenceId(uuid4())
    key_a = compute_fact_dedupe_key(
        category=CompanyFactCategory.DIGITAL,
        subject="email_address",
        value="a@b.test",
        evidence_ids=[evidence_id],
        fact_tier=CompanyFactTier.SUBSTANTIVE,
    )
    key_b = compute_fact_dedupe_key(
        category=CompanyFactCategory.DIGITAL,
        subject="email_address",
        value="a@b.test",
        evidence_ids=[evidence_id],
        fact_tier=CompanyFactTier.METADATA,
    )
    assert key_a != key_b


def test_page_metadata_marked_as_metadata_tier() -> None:
    context = _ctx(title="About Us", text="About our company")
    facts = extract_deterministic_facts(context)
    meta = [f for f in facts if f.subject == "page_classification"]
    assert meta
    assert meta[0].fact_tier is CompanyFactTier.METADATA


def test_intermark_fixture_produces_rich_substantive_facts() -> None:
    extractor = DeterministicEvidenceFactExtractor()
    contexts = intermark_evidence_contexts()
    facts = extractor.extract(contexts)
    substantive = [f for f in facts if f.fact_tier is CompanyFactTier.SUBSTANTIVE]
    by_category = {cat.value: 0 for cat in CompanyFactCategory}
    for fact in substantive:
        by_category[fact.category.value] += 1

    assert len(contexts) == 10
    assert by_category["geography"] >= 3
    assert by_category["organization"] >= 1
    assert by_category["activity"] >= 3
    assert by_category["commercial"] >= 1
    assert by_category["digital"] >= 2
    assert len(substantive) >= 15
    assert not any(f.subject == "page_title" and f.value == "May" for f in facts)
    assert not any(f.value == "May" for f in substantive)


def test_intermark_stated_markets_from_blog() -> None:
    blog = next(c for c in intermark_evidence_contexts() if "expert-blog" in c.source_locator)
    facts = extract_deterministic_facts(blog)
    markets = [f for f in facts if f.subject == "stated_market"]
    values = {item.value for item in markets}
    assert "Bali" in values or "Phuket" in values or "Dubai" in values


def test_leading_headings_skips_boilerplate() -> None:
    text = "Financial breakthrough: The path to smart investments\nAbout event\nMain"
    headings = leading_headings(text)
    assert headings
    assert "Financial breakthrough" in headings[0]


def test_corrupted_heading_not_used_as_activity_name() -> None:
    context = _ctx(
        locator="https://acme.test/events/2",
        title="INTERMARK GLOBAL. Real Estate for life, investments and immigration",
        text="Financial breakthrough: The path to smart investments2\nAbout event",
    )
    facts = extract_deterministic_facts(context)
    names = [f for f in facts if f.subject == "activity_name"]
    assert not any("investments2" in n.value for n in names)
