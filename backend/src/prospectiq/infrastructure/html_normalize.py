"""Deterministic HTML-to-text extraction. Infrastructure only."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup

_DROP_TAGS = frozenset(
    {"script", "style", "noscript", "svg", "iframe", "canvas", "template"}
)
_NOISE_TAGS = frozenset({"nav", "footer", "header", "aside"})
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class NormalizedPage:
    title: str | None
    headings: list[str]
    text: str


def normalize_page(
    body: bytes, content_type: str, *, max_text_chars: int = 20_000
) -> NormalizedPage:
    if content_type == "text/plain":
        text = _collapse(_decode(body))
        return NormalizedPage(title=None, headings=[], text=text[:max_text_chars])

    soup = BeautifulSoup(_decode(body), "html.parser")
    for tag in soup.find_all(_DROP_TAGS | _NOISE_TAGS):
        tag.decompose()

    title = None
    if soup.title and soup.title.string:
        title = _collapse(str(soup.title.string)) or None

    headings: list[str] = []
    for heading in soup.find_all(["h1", "h2", "h3"]):
        value = _collapse(_element_text(heading))
        if value and value not in headings:
            headings.append(value)
        if len(headings) >= 12:
            break

    root = soup.body if soup.body else soup
    text = _collapse(_element_text(root))
    if headings:
        heading_block = "\n".join(headings)
        if heading_block not in text:
            text = f"{heading_block}\n{text}".strip()
    return NormalizedPage(title=title, headings=headings, text=text[:max_text_chars])


def _decode(body: bytes) -> str:
    return body.decode("utf-8", errors="replace")


def _element_text(node: Any) -> str:
    return str(node.get_text(" ", strip=True))


def _collapse(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()
