"""Deterministic validation of search hits before they become company candidates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse

from prospectiq.domain.discovery import ProviderDiscoveryHit


class CandidateQualityClass(StrEnum):
    VALID_COMPANY = "valid_company"
    CONTENT_PAGE = "content_page"
    GOVERNMENT_REGULATORY = "government_regulatory"
    MEDIA_EDUCATIONAL = "media_educational"
    BLOCKED_HOST = "blocked_host"


class CandidateRejectReason(StrEnum):
    GOVERNMENT_TLD = "government_tld"
    EDUCATIONAL_TLD = "educational_tld"
    CONTENT_PATH = "content_path"
    EDITORIAL_SUBDOMAIN = "editorial_subdomain"
    MEDIA_HOST_PATTERN = "media_host_pattern"
    DEEP_NON_CAREERS_PATH = "deep_non_careers_path"
    BLOCKED_PROVIDER_HOST = "blocked_provider_host"


GOVERNMENT_TLD_SUFFIXES = (".gov", ".mil")
EDUCATIONAL_TLD_SUFFIXES = (".edu",)

CONTENT_PATH_SEGMENTS = frozenset(
    {
        "think",
        "topics",
        "terms",
        "resources",
        "articles",
        "article",
        "blog",
        "blogs",
        "news",
        "guides",
        "guide",
        "wiki",
        "press",
        "press-releases",
        "events",
        "calendar",
        "hearing",
        "hearings",
        "business-guidance",
        "opinion",
        "learn",
        "education",
        "courses",
        "magazine",
        "story",
        "stories",
        "partner-content",
        "reports",
        "whitepapers",
        "glossary",
        "definition",
        "definitions",
        "explained",
        "what-is",
    }
)

CAREERS_PATH_SEGMENTS = frozenset(
    {
        "careers",
        "career",
        "jobs",
        "job",
        "join-us",
        "joinus",
        "work-with-us",
        "vacancies",
        "openings",
        "hiring",
    }
)

COMPANY_PAGE_SEGMENTS = frozenset(
    {
        "about",
        "company",
        "team",
        "contact",
        "home",
    }
)

EDITORIAL_SUBDOMAIN_LABELS = frozenset(
    {
        "news",
        "blog",
        "blogs",
        "docs",
        "learn",
        "wiki",
        "support",
        "help",
        "media",
        "press",
        "research",
        "stories",
        "resources",
        "think",
        "education",
    }
)

MEDIA_HOST_LABELS = frozenset(
    {
        "investopedia",
        "wikipedia",
        "forbes",
        "techcrunch",
        "medium",
        "bloomberg",
        "reuters",
        "cnbc",
        "nytimes",
        "theguardian",
        "bbc",
        "economist",
    }
)


@dataclass(frozen=True, slots=True)
class CandidateValidationResult:
    accepted: bool
    quality_class: CandidateQualityClass
    reject_reason: CandidateRejectReason | None = None

    @property
    def rejection_label(self) -> str | None:
        if self.reject_reason is None:
            return None
        return self.reject_reason.value


def validate_discovery_hit(hit: ProviderDiscoveryHit) -> CandidateValidationResult:
    """Return whether a provider hit should become a company discovery candidate."""
    raw = (hit.website or hit.source_locator or "").strip()
    if not raw:
        return CandidateValidationResult(
            accepted=False,
            quality_class=CandidateQualityClass.CONTENT_PAGE,
            reject_reason=CandidateRejectReason.CONTENT_PATH,
        )

    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path = (parsed.path or "/").lower().strip("/")
    segments = [segment for segment in path.split("/") if segment]

    if not host:
        return CandidateValidationResult(
            accepted=False,
            quality_class=CandidateQualityClass.CONTENT_PAGE,
            reject_reason=CandidateRejectReason.CONTENT_PATH,
        )

    if _host_blocked_by_provider(host):
        return CandidateValidationResult(
            accepted=False,
            quality_class=CandidateQualityClass.BLOCKED_HOST,
            reject_reason=CandidateRejectReason.BLOCKED_PROVIDER_HOST,
        )

    if host.endswith(GOVERNMENT_TLD_SUFFIXES) or ".gov." in host:
        return CandidateValidationResult(
            accepted=False,
            quality_class=CandidateQualityClass.GOVERNMENT_REGULATORY,
            reject_reason=CandidateRejectReason.GOVERNMENT_TLD,
        )

    if host.endswith(EDUCATIONAL_TLD_SUFFIXES):
        return CandidateValidationResult(
            accepted=False,
            quality_class=CandidateQualityClass.MEDIA_EDUCATIONAL,
            reject_reason=CandidateRejectReason.EDUCATIONAL_TLD,
        )

    host_labels = host.split(".")
    registrable = host_labels[-2] if len(host_labels) >= 2 else host_labels[0]
    if registrable in MEDIA_HOST_LABELS:
        return CandidateValidationResult(
            accepted=False,
            quality_class=CandidateQualityClass.MEDIA_EDUCATIONAL,
            reject_reason=CandidateRejectReason.MEDIA_HOST_PATTERN,
        )

    if len(host_labels) >= 3:
        subdomain = host_labels[0]
        if subdomain in EDITORIAL_SUBDOMAIN_LABELS:
            return CandidateValidationResult(
                accepted=False,
                quality_class=CandidateQualityClass.CONTENT_PAGE,
                reject_reason=CandidateRejectReason.EDITORIAL_SUBDOMAIN,
            )

    if segments:
        first = segments[0]
        if first in CONTENT_PATH_SEGMENTS:
            return CandidateValidationResult(
                accepted=False,
                quality_class=CandidateQualityClass.CONTENT_PAGE,
                reject_reason=CandidateRejectReason.CONTENT_PATH,
            )
        if first in CAREERS_PATH_SEGMENTS or first in COMPANY_PAGE_SEGMENTS:
            return CandidateValidationResult(
                accepted=True,
                quality_class=CandidateQualityClass.VALID_COMPANY,
            )
        if len(segments) >= 2 and segments[0] in CONTENT_PATH_SEGMENTS:
            return CandidateValidationResult(
                accepted=False,
                quality_class=CandidateQualityClass.CONTENT_PAGE,
                reject_reason=CandidateRejectReason.CONTENT_PATH,
            )
        if len(segments) >= 3:
            return CandidateValidationResult(
                accepted=False,
                quality_class=CandidateQualityClass.CONTENT_PAGE,
                reject_reason=CandidateRejectReason.DEEP_NON_CAREERS_PATH,
            )

    return CandidateValidationResult(
        accepted=True,
        quality_class=CandidateQualityClass.VALID_COMPANY,
    )


def _host_blocked_by_provider(host: str) -> bool:
    blocked_suffixes = (
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
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in blocked_suffixes)
