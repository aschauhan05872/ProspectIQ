"""Deterministic Phase 5 fact extraction rules (SOURCE_DERIVED only)."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from urllib.parse import urlparse

from prospectiq.domain.common import Confidence, EvidenceId
from prospectiq.domain.company_facts import (
    CompanyFactCategory,
    CompanyFactTier,
    EvidencePageContext,
    ExtractedCompanyFact,
)
from prospectiq.domain.evidence import EvidenceOrigin

_MONTH_NAMES = frozenset(
    {
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "jan",
        "feb",
        "mar",
        "apr",
        "jun",
        "jul",
        "aug",
        "sep",
        "sept",
        "oct",
        "nov",
        "dec",
    }
)
_BOILERPLATE_HEADINGS = frozenset(
    {
        "main",
        "events",
        "blog",
        "about event",
        "about company",
        "contact us",
        "look at what our clients are saying",
        "all events",
        "all materials",
        "the program of the event",
        "what will we discuss on the forum",
        "headline in one, two or three lines",
        "the experts' knowledge is packed in one place",
        "office entry rules",
        "check out the most important events",
    }
)
_GENERIC_TITLE_FRAGMENTS = (
    "real estate for life",
    "investments and immigration",
    "intermark global",
)
_FORM_KEYWORDS = (
    "contact form",
    "request a demo",
    "book a demo",
    "schedule a call",
    "get in touch",
    "send us a message",
)
_OFFERING_PAGE_TYPES = frozenset({"services", "products", "solutions", "platform"})
_COUNTRY_CITY_PATTERN = re.compile(
    r"\b(United Kingdom|United Arab Emirates|United States|South Korea|"
    r"Indonesia|Thailand|Turkey|China|Germany|France|Spain|Italy|Netherlands|"
    r"Singapore|Malaysia|Vietnam|Japan|Australia|Canada|India|Saudi Arabia|UAE)\s+"
    r"([A-Z][a-z]+)\b"
)
_OFFICES_COUNT_PATTERN = re.compile(r"\b(\d+\+?)\s+offices?\b", re.IGNORECASE)
_PARTNERS_COUNT_PATTERN = re.compile(
    r"\b(over\s+)?(\d+\+?)\s+partners?\b",
    re.IGNORECASE,
)
_LOCATION_PHRASE_PATTERN = re.compile(
    r"\b(?:based in|located in|headquarters in|office in|offices in)\s+"
    r"([A-Z][A-Za-z0-9\s,.-]{2,80})",
    re.IGNORECASE,
)
_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
_PHONE_PATTERN = re.compile(
    r"(?<!\w)(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)|\d{2,4})[\s.-]?\d{3,4}[\s.-]?\d{3,4}"
    r"(?:\s*(?:ext|x)\.?\s*\d+)?(?!\w)"
)
_STATED_MARKETS_PATTERN = re.compile(
    r"\b(?:real estate )?markets?\s+([A-Za-z]+(?:\s*,\s*[A-Za-z]+|\s+or\s+[A-Za-z]+)+)",
    re.IGNORECASE,
)
_WEBINAR_PATTERN = re.compile(r"\bwebinars?\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ExtractionBatchState:
    title_counts: Counter[str]


def _fact(
    *,
    category: CompanyFactCategory,
    subject: str,
    value: str,
    evidence_id: EvidenceId,
    tier: CompanyFactTier = CompanyFactTier.SUBSTANTIVE,
    confidence: Confidence = Confidence.HIGH,
) -> ExtractedCompanyFact:
    return ExtractedCompanyFact(
        category=category,
        subject=subject,
        value=value,
        evidence_ids=(evidence_id,),
        origin=EvidenceOrigin.SOURCE_DERIVED,
        confidence=confidence,
        fact_tier=tier,
    )


def normalize_title_key(title: str) -> str:
    return " ".join(title.lower().split())


def is_acceptable_page_title(
    title: str,
    *,
    source_locator: str,
    batch: ExtractionBatchState,
) -> bool:
    cleaned = title.strip()
    if not cleaned or len(cleaned) < 4:
        return False

    tokens = cleaned.split()
    if len(tokens) == 1:
        token = tokens[0].lower().strip(".")
        if token in _MONTH_NAMES:
            return False
        if len(token) <= 3:
            return False

    if re.fullmatch(r"\d{1,4}", cleaned):
        return False

    normalized = normalize_title_key(cleaned)
    parsed = urlparse(source_locator)
    is_home = parsed.path in {"", "/"}
    is_generic = any(fragment in normalized for fragment in _GENERIC_TITLE_FRAGMENTS)
    if is_generic and not is_home:
        return False

    if batch.title_counts[normalized] >= 2 and is_generic:
        return False

    return True


def leading_headings(text: str) -> list[str]:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    headings: list[str] = []
    for line in lines[:10]:
        lowered = line.lower()
        if lowered in _BOILERPLATE_HEADINGS:
            continue
        if len(line) < 12 or len(line) > 160:
            if headings:
                break
            continue
        if not line[0].isupper():
            break
        headings.append(line)
        if len(headings) >= 4:
            break
    return headings


def _is_corrupted_heading(heading: str) -> bool:
    """Reject headings with obvious scrape artifacts (e.g. 'investments2')."""
    tokens = heading.split()
    if not tokens:
        return True
    last = tokens[-1]
    if re.search(r"[A-Za-z]\d+$", last):
        return True
    return False


def _best_content_heading(
    *,
    headings: list[str],
    title: str | None,
    source_locator: str,
    batch: ExtractionBatchState,
) -> str | None:
    title_key = normalize_title_key(title) if title else ""
    for heading in headings:
        key = normalize_title_key(heading)
        if key == title_key:
            continue
        if heading.lower() in _BOILERPLATE_HEADINGS:
            continue
        if any(fragment in key for fragment in _GENERIC_TITLE_FRAGMENTS):
            continue
        if len(heading.split()) == 1 and heading.lower() in _MONTH_NAMES:
            continue
        if _is_corrupted_heading(heading):
            continue
        return heading

    parsed = urlparse(source_locator)
    if parsed.path.count("/") >= 2:
        lines = [line.strip() for line in headings if line.strip()]
        for line in lines:
            key = normalize_title_key(line)
            if key == title_key:
                continue
            if line.lower() in _BOILERPLATE_HEADINGS:
                continue
            if any(fragment in key for fragment in _GENERIC_TITLE_FRAGMENTS):
                continue
            if _is_corrupted_heading(line):
                continue
            return line
    return None


def _extract_geography(context: EvidencePageContext) -> list[ExtractedCompanyFact]:
    facts: list[ExtractedCompanyFact] = []
    text = context.text
    evidence_id = context.evidence_id

    if re.search(r"\bOffices\b", text, re.IGNORECASE):
        for match in _COUNTRY_CITY_PATTERN.finditer(text):
            country = match.group(1).strip()
            city = match.group(2).strip(" .,")
            if city:
                facts.append(
                    _fact(
                        category=CompanyFactCategory.GEOGRAPHY,
                        subject="office_location",
                        value=f"{country} {city}",
                        evidence_id=evidence_id,
                        confidence=Confidence.HIGH,
                    )
                )

    for match in _LOCATION_PHRASE_PATTERN.finditer(text):
        location = match.group(1).strip(" .,")
        if location:
            facts.append(
                _fact(
                    category=CompanyFactCategory.GEOGRAPHY,
                    subject="operating_location",
                    value=location,
                    evidence_id=evidence_id,
                    confidence=Confidence.MEDIUM,
                )
            )

    for match in _STATED_MARKETS_PATTERN.finditer(text):
        markets_blob = match.group(1)
        for part in re.split(r",|\bor\b", markets_blob):
            market = part.strip()
            if market and market[0].isupper() and len(market) >= 3:
                facts.append(
                    _fact(
                        category=CompanyFactCategory.GEOGRAPHY,
                        subject="stated_market",
                        value=market,
                        evidence_id=evidence_id,
                        confidence=Confidence.MEDIUM,
                    )
                )

    return facts


def _extract_organization(context: EvidencePageContext) -> list[ExtractedCompanyFact]:
    facts: list[ExtractedCompanyFact] = []
    text = context.text
    evidence_id = context.evidence_id

    for match in _OFFICES_COUNT_PATTERN.finditer(text):
        facts.append(
            _fact(
                category=CompanyFactCategory.ORGANIZATION,
                subject="offices",
                value=match.group(1),
                evidence_id=evidence_id,
                confidence=Confidence.HIGH,
            )
        )
        break

    for match in _PARTNERS_COUNT_PATTERN.finditer(text):
        over_prefix = match.group(1)
        raw_value = match.group(2)
        value = raw_value if raw_value.endswith("+") or not over_prefix else f"{raw_value}+"
        facts.append(
            _fact(
                category=CompanyFactCategory.ORGANIZATION,
                subject="partners",
                value=value,
                evidence_id=evidence_id,
                confidence=Confidence.HIGH,
            )
        )
        break

    return facts


def _extract_activity(
    context: EvidencePageContext,
    *,
    headings: list[str],
    batch: ExtractionBatchState,
) -> list[ExtractedCompanyFact]:
    facts: list[ExtractedCompanyFact] = []
    path = urlparse(context.source_locator).path.lower()
    text = context.text
    lowered = text.lower()
    evidence_id = context.evidence_id

    is_events_path = "/events" in path
    is_blog_path = "/blog" in path or "expert-blog" in path

    if is_events_path and ("event" in lowered or "forum" in lowered or "webinar" in lowered):
        facts.append(
            _fact(
                category=CompanyFactCategory.ACTIVITY,
                subject="content_channel",
                value="events",
                evidence_id=evidence_id,
                confidence=Confidence.HIGH,
            )
        )

    if is_blog_path and "blog" in lowered:
        channel = "expert_blog" if "expert" in path else "blog"
        facts.append(
            _fact(
                category=CompanyFactCategory.ACTIVITY,
                subject="content_channel",
                value=channel,
                evidence_id=evidence_id,
                confidence=Confidence.HIGH,
            )
        )

    if _WEBINAR_PATTERN.search(text) and is_events_path:
        facts.append(
            _fact(
                category=CompanyFactCategory.ACTIVITY,
                subject="activity_type",
                value="webinar",
                evidence_id=evidence_id,
                confidence=Confidence.MEDIUM,
            )
        )

    heading = _best_content_heading(
        headings=headings,
        title=context.title,
        source_locator=context.source_locator,
        batch=batch,
    )
    if heading and (is_events_path or is_blog_path):
        facts.append(
            _fact(
                category=CompanyFactCategory.ACTIVITY,
                subject="activity_name",
                value=heading,
                evidence_id=evidence_id,
                confidence=Confidence.MEDIUM,
            )
        )

    return facts


def extract_deterministic_facts(
    context: EvidencePageContext,
    *,
    batch: ExtractionBatchState | None = None,
) -> list[ExtractedCompanyFact]:
    """Extract explicit, structured facts from one research page evidence context."""

    state = batch or ExtractionBatchState(title_counts=Counter())
    facts: list[ExtractedCompanyFact] = []
    evidence_id = context.evidence_id
    page_type = context.page_type
    locator = context.source_locator
    text = context.text
    title = (context.title or "").strip()
    headings = leading_headings(text)

    if title:
        normalized_title = normalize_title_key(title)
        state.title_counts[normalized_title] += 1

    facts.append(
        _fact(
            category=CompanyFactCategory.DIGITAL,
            subject="page_classification",
            value=f"{page_type} page at {locator}",
            evidence_id=evidence_id,
            tier=CompanyFactTier.METADATA,
        )
    )

    if title and is_acceptable_page_title(title, source_locator=locator, batch=state):
        facts.append(
            _fact(
                category=CompanyFactCategory.BUSINESS,
                subject="page_title",
                value=title,
                evidence_id=evidence_id,
                tier=CompanyFactTier.METADATA,
            )
        )

    if page_type in _OFFERING_PAGE_TYPES and title:
        if is_acceptable_page_title(title, source_locator=locator, batch=state):
            facts.append(
                _fact(
                    category=CompanyFactCategory.BUSINESS,
                    subject="stated_offering",
                    value=title,
                    evidence_id=evidence_id,
                    confidence=Confidence.MEDIUM,
                )
            )

    content_heading = _best_content_heading(
        headings=headings,
        title=title,
        source_locator=locator,
        batch=state,
    )
    if content_heading and page_type in _OFFERING_PAGE_TYPES:
        facts.append(
            _fact(
                category=CompanyFactCategory.BUSINESS,
                subject="stated_offering",
                value=content_heading,
                evidence_id=evidence_id,
                confidence=Confidence.MEDIUM,
            )
        )

    if page_type == "contact":
        facts.append(
            _fact(
                category=CompanyFactCategory.COMMERCIAL,
                subject="contact_page",
                value=locator,
                evidence_id=evidence_id,
            )
        )

    lowered = text.lower()
    for keyword in _FORM_KEYWORDS:
        if keyword in lowered:
            facts.append(
                _fact(
                    category=CompanyFactCategory.DIGITAL,
                    subject="contact_mechanism",
                    value=keyword,
                    evidence_id=evidence_id,
                    confidence=Confidence.MEDIUM,
                )
            )
            break

    for match in _EMAIL_PATTERN.findall(text):
        facts.append(
            _fact(
                category=CompanyFactCategory.DIGITAL,
                subject="email_address",
                value=match,
                evidence_id=evidence_id,
            )
        )

    for match in _PHONE_PATTERN.findall(text):
        normalized_phone = " ".join(match.split())
        facts.append(
            _fact(
                category=CompanyFactCategory.DIGITAL,
                subject="phone_number",
                value=normalized_phone,
                evidence_id=evidence_id,
                confidence=Confidence.MEDIUM,
            )
        )

    facts.extend(_extract_geography(context))
    facts.extend(_extract_organization(context))
    facts.extend(_extract_activity(context, headings=headings, batch=state))

    return facts
