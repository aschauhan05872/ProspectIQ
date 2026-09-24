"""Deterministic URL validation and classification. No HTTP I/O."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

from prospectiq.domain.source_registry import SourceClass

ALLOWED_SCHEMES = frozenset({"http", "https"})

BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata.google.internal.",
    }
)

LINKEDIN_HOST_SUFFIXES = (
    "linkedin.com",
    "linkedin.cn",
    "lnkd.in",
)

CAREERS_PATH_MARKERS = (
    "/careers",
    "/career",
    "/jobs",
    "/job",
    "/join-us",
    "/joinus",
    "/work-with-us",
    "/vacancies",
    "/openings",
)


class InvalidSourceUrl(Exception):
    """The supplied URL is not a permitted company-source locator."""


@dataclass(frozen=True, slots=True)
class NormalizedSourceUrl:
    original: str
    normalized: str
    scheme: str
    host: str
    identity_host: str
    path: str
    source_class: SourceClass
    identity_requires_review: bool
    origin: str


def parse_source_url(raw: str) -> NormalizedSourceUrl:
    if raw is None or not str(raw).strip():
        raise InvalidSourceUrl("URL is required.")
    candidate = str(raw).strip()
    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise InvalidSourceUrl("Only http and https URLs are permitted.")
    if parsed.username or parsed.password:
        raise InvalidSourceUrl("URLs must not include credentials.")
    host = _hostname(parsed)
    if not host:
        raise InvalidSourceUrl("URL host is required.")
    if host in BLOCKED_HOSTS:
        raise InvalidSourceUrl("Requests to localhost or internal metadata hosts are forbidden.")
    if _is_linkedin_host(host):
        raise InvalidSourceUrl(
            "LinkedIn URLs are not a permitted automated source. "
            "LinkedIn execution remains human-controlled."
        )
    ip = _literal_ip(host)
    if ip is not None and not _is_public_ip(ip):
        raise InvalidSourceUrl("Requests to private or internal network addresses are forbidden.")

    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    query = parsed.query
    identity_host = host[4:] if host.startswith("www.") else host
    normalized = urlunparse(
        (parsed.scheme.lower(), _netloc(parsed, identity_host), path, "", query, "")
    )
    origin = urlunparse((parsed.scheme.lower(), _netloc(parsed, identity_host), "", "", "", ""))
    return NormalizedSourceUrl(
        original=candidate,
        normalized=normalized,
        scheme=parsed.scheme.lower(),
        host=host,
        identity_host=identity_host,
        path=path,
        source_class=_classify_path(path),
        identity_requires_review=ip is not None,
        origin=origin.rstrip("/"),
    )


def fetch_source_idempotency_key(normalized_url: str) -> str:
    return f"fetch_source:{normalized_url}"


def _hostname(parsed: object) -> str:
    host = getattr(parsed, "hostname", None)
    if not host:
        return ""
    return str(host).rstrip(".").lower()


def _netloc(parsed: object, host: str) -> str:
    port = getattr(parsed, "port", None)
    scheme = getattr(parsed, "scheme", "").lower()
    if port is None:
        return host
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        return host
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"{host}:{port}"


def _classify_path(path: str) -> SourceClass:
    lowered = path.lower()
    if any(marker in lowered for marker in CAREERS_PATH_MARKERS):
        return SourceClass.CAREERS_PAGE
    return SourceClass.COMPANY_WEBSITE


def _is_linkedin_host(host: str) -> bool:
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in LINKEDIN_HOST_SUFFIXES)


def _literal_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(ip.is_global) and not ip.is_multicast


def is_blocked_resolved_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not _is_public_ip(ip)
