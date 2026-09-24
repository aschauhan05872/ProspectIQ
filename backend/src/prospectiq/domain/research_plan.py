"""Deterministic research page planning and classification. No HTTP I/O."""

from __future__ import annotations

from urllib.parse import urljoin, urlparse

from prospectiq.domain.company_research import (
    PAGE_TYPE_PRIORITY,
    PlannedResearchPage,
    ResearchPageType,
)

EXTERNAL_BLOCKED_SUFFIXES = (
    "linkedin.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "instagram.com",
    "tiktok.com",
    "reddit.com",
    "glassdoor.com",
    "indeed.com",
    "google.com",
    "bing.com",
)

PATH_TYPE_RULES: tuple[tuple[str, ResearchPageType], ...] = (
    ("/about", ResearchPageType.ABOUT),
    ("/about-us", ResearchPageType.ABOUT),
    ("/company", ResearchPageType.ABOUT),
    ("/products", ResearchPageType.PRODUCTS),
    ("/product", ResearchPageType.PRODUCTS),
    ("/services", ResearchPageType.SERVICES),
    ("/service", ResearchPageType.SERVICES),
    ("/solutions", ResearchPageType.SOLUTIONS),
    ("/solution", ResearchPageType.SOLUTIONS),
    ("/platform", ResearchPageType.PLATFORM),
    ("/technology", ResearchPageType.TECHNOLOGY),
    ("/tech", ResearchPageType.TECHNOLOGY),
    ("/contact", ResearchPageType.CONTACT),
    ("/contact-us", ResearchPageType.CONTACT),
    ("/careers", ResearchPageType.CAREERS),
    ("/career", ResearchPageType.CAREERS),
    ("/jobs", ResearchPageType.CAREERS),
    ("/job", ResearchPageType.CAREERS),
    ("/news", ResearchPageType.NEWS),
    ("/press", ResearchPageType.NEWS),
    ("/blog", ResearchPageType.BLOG),
    ("/blogs", ResearchPageType.BLOG),
    ("/insights", ResearchPageType.BLOG),
)


def classify_page_type(
    *, path: str, title: str | None = None, anchor: str | None = None
) -> ResearchPageType:
    normalized_path = (path or "/").lower().rstrip("/") or "/"
    if normalized_path in {"/", ""}:
        return ResearchPageType.HOME
    for prefix, page_type in PATH_TYPE_RULES:
        if normalized_path == prefix or normalized_path.startswith(prefix + "/"):
            return page_type
    combined = " ".join(filter(None, [title, anchor])).lower()
    if any(word in combined for word in ("career", "jobs", "hiring")):
        return ResearchPageType.CAREERS
    if "blog" in combined:
        return ResearchPageType.BLOG
    if "news" in combined or "press" in combined:
        return ResearchPageType.NEWS
    if "contact" in combined:
        return ResearchPageType.CONTACT
    if "about" in combined:
        return ResearchPageType.ABOUT
    return ResearchPageType.OTHER


def is_same_domain(url: str, identity_host: str) -> bool:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    target = identity_host.lower().removeprefix("www.")
    return host == target or host.endswith(f".{target}")


def is_blocked_external_host(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if not host:
        return True
    return any(
        host == suffix or host.endswith(f".{suffix}") for suffix in EXTERNAL_BLOCKED_SUFFIXES
    )


def normalize_research_url(base_url: str, link: str) -> str | None:
    if not link or link.startswith(("#", "mailto:", "tel:", "javascript:")):
        return None
    absolute = urljoin(base_url, link.strip())
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"}:
        return None
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    netloc = host if not parsed.port else f"{host}:{parsed.port}"
    return f"{parsed.scheme}://{netloc}{path}"


def build_initial_plan(homepage_url: str, *, max_pages: int) -> list[PlannedResearchPage]:
    parsed = urlparse(homepage_url)
    path = parsed.path or "/"
    page_type = classify_page_type(path=path)
    home = PlannedResearchPage(
        url=homepage_url,
        normalized_url=homepage_url,
        page_type=page_type,
        priority=PAGE_TYPE_PRIORITY[page_type],
    )
    return [home][:max_pages]


def merge_discovered_pages(
    *,
    homepage_url: str,
    identity_host: str,
    discovered: list[tuple[str, str | None]],
    max_pages: int,
) -> list[PlannedResearchPage]:
    """Merge homepage + classified same-domain links into a bounded plan."""
    plan: list[PlannedResearchPage] = []
    seen: set[str] = set()

    def add(url: str, page_type: ResearchPageType, anchor: str | None = None) -> None:
        if len(plan) >= max_pages:
            return
        if url in seen:
            return
        if not is_same_domain(url, identity_host):
            return
        if is_blocked_external_host(url):
            return
        seen.add(url)
        plan.append(
            PlannedResearchPage(
                url=url,
                normalized_url=url,
                page_type=page_type,
                priority=PAGE_TYPE_PRIORITY[page_type],
            )
        )

    home_type = classify_page_type(path=urlparse(homepage_url).path or "/")
    add(homepage_url, home_type)

    candidates: list[PlannedResearchPage] = []
    for url, anchor in discovered:
        if url in seen:
            continue
        if not is_same_domain(url, identity_host) or is_blocked_external_host(url):
            continue
        ptype = classify_page_type(path=urlparse(url).path or "/", anchor=anchor)
        candidates.append(
            PlannedResearchPage(
                url=url,
                normalized_url=url,
                page_type=ptype,
                priority=PAGE_TYPE_PRIORITY[ptype],
            )
        )

    candidates.sort(key=lambda item: (item.priority, item.normalized_url))
    for item in candidates:
        add(item.normalized_url, item.page_type)
        if len(plan) >= max_pages:
            break
    return plan
