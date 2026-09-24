"""Extract same-domain links from HTML. Infrastructure only."""

from __future__ import annotations

from bs4 import BeautifulSoup, Tag

from prospectiq.domain.research_plan import normalize_research_url


def extract_page_links(
    base_url: str, body: bytes, content_type: str
) -> list[tuple[str, str | None]]:
    """Return (absolute_url, anchor_text) pairs from anchor tags."""
    if "html" not in content_type and content_type != "application/xhtml+xml":
        return []
    soup = BeautifulSoup(body.decode("utf-8", errors="replace"), "html.parser")
    links: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        href = str(anchor.get("href") or "").strip()
        normalized = normalize_research_url(base_url, href)
        if normalized is None or normalized in seen:
            continue
        text = anchor.get_text(" ", strip=True) or None
        seen.add(normalized)
        links.append((normalized, text))
    return links
