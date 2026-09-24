"""SSRF-aware HTTP GET. Infrastructure only; not imported by domain code."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from urllib.parse import urljoin, urlparse

import httpx

from prospectiq.domain.ingestion import PermanentSourceError, RetryableSourceError
from prospectiq.domain.source_url import (
    ALLOWED_SCHEMES,
    BLOCKED_HOSTS,
    InvalidSourceUrl,
    is_blocked_resolved_ip,
    parse_source_url,
)
from prospectiq.infrastructure.logging import get_logger

logger = get_logger("prospectiq.http_fetch")

ResolveHost = Callable[[str], list[ipaddress.IPv4Address | ipaddress.IPv6Address]]

ALLOWED_CONTENT_TYPES = frozenset(
    {
        "text/html",
        "application/xhtml+xml",
        "text/plain",
    }
)

RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


@dataclass(frozen=True, slots=True)
class FetchLimits:
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 10.0
    total_timeout_seconds: float = 15.0
    max_response_bytes: int = 1_048_576
    max_redirects: int = 3
    user_agent: str = "ProspectIQ/0.1 (+internal-company-research)"


@dataclass(frozen=True, slots=True)
class HttpFetchResult:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    body: bytes
    duration_ms: int


def default_resolve_host(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise RetryableSourceError(f"DNS resolution failed for host '{host}'.") from exc
    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        raw = info[4][0]
        try:
            addresses.append(ipaddress.ip_address(raw))
        except ValueError:
            continue
    if not addresses:
        raise RetryableSourceError(f"DNS resolution returned no addresses for host '{host}'.")
    return addresses


class SafeHttpFetcher:
    def __init__(
        self,
        limits: FetchLimits,
        *,
        resolve_host: ResolveHost = default_resolve_host,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._limits = limits
        self._resolve_host = resolve_host
        self._transport = transport

    async def get(self, url: str) -> HttpFetchResult:
        started = perf_counter()
        try:
            return await self._get(url, started)
        except (PermanentSourceError, RetryableSourceError) as exc:
            logger.info(
                "source_fetch_failed",
                domain=_safe_domain(url),
                error=str(exc),
                operation="http_get",
            )
            raise

    async def _get(self, url: str, started: float) -> HttpFetchResult:
        current = _validate_outbound_url(url)
        seen: set[str] = {current}
        timeout = httpx.Timeout(
            timeout=self._limits.total_timeout_seconds,
            connect=self._limits.connect_timeout_seconds,
            read=self._limits.read_timeout_seconds,
        )
        headers = {"User-Agent": self._limits.user_agent, "Accept": "text/html, text/plain"}
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            transport=self._transport,
            trust_env=False,
        ) as client:
            for _hop in range(self._limits.max_redirects + 1):
                _assert_destination_allowed(current, self._resolve_host)
                logger.info(
                    "source_fetch_attempted",
                    domain=_safe_domain(current),
                    operation="http_get",
                )
                try:
                    response = await client.get(current, headers=headers)
                except httpx.TimeoutException as exc:
                    raise RetryableSourceError("Source fetch timed out.") from exc
                except httpx.RequestError as exc:
                    raise RetryableSourceError(
                        "Source fetch failed due to a network error."
                    ) from exc

                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise PermanentSourceError(
                            "Redirect response was missing a Location header."
                        )
                    nxt = urljoin(current, location)
                    nxt = _validate_outbound_url(nxt)
                    if nxt in seen:
                        raise PermanentSourceError("Redirect loop detected.")
                    if len(seen) > self._limits.max_redirects:
                        raise PermanentSourceError("Too many redirects.")
                    seen.add(nxt)
                    current = nxt
                    continue

                duration_ms = int((perf_counter() - started) * 1000)
                if response.status_code in RETRYABLE_STATUS:
                    raise RetryableSourceError(f"Source returned HTTP {response.status_code}.")
                if response.status_code < 200 or response.status_code >= 300:
                    raise PermanentSourceError(f"Source returned HTTP {response.status_code}.")
                content_type = _content_type(response.headers.get("content-type"))
                if content_type not in ALLOWED_CONTENT_TYPES:
                    raise PermanentSourceError(
                        f"Unsupported content type: {content_type or 'unknown'}."
                    )
                body = _bounded_body(response, self._limits.max_response_bytes)
                logger.info(
                    "source_fetch_succeeded",
                    domain=_safe_domain(str(response.url)),
                    http_status=response.status_code,
                    content_type=content_type,
                    duration_ms=duration_ms,
                    operation="http_get",
                )
                return HttpFetchResult(
                    requested_url=url,
                    final_url=str(response.url),
                    status_code=response.status_code,
                    content_type=content_type,
                    body=body,
                    duration_ms=duration_ms,
                )
        raise PermanentSourceError("Too many redirects.")


def _validate_outbound_url(url: str) -> str:
    try:
        parsed = parse_source_url(url)
    except InvalidSourceUrl as exc:
        raise PermanentSourceError(str(exc)) from exc
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise PermanentSourceError("Only http and https URLs are permitted.")
    return parsed.normalized


def _assert_destination_allowed(url: str, resolve_host: ResolveHost) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").rstrip(".").lower()
    if not host or host in BLOCKED_HOSTS:
        raise PermanentSourceError("Requests to localhost or internal hosts are forbidden.")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        addresses = resolve_host(host)
        blocked = [str(item) for item in addresses if is_blocked_resolved_ip(item)]
        if blocked:
            raise PermanentSourceError(
                "Resolved host addresses are private or internal and cannot be fetched."
            ) from None
        return
    if is_blocked_resolved_ip(ip):
        raise PermanentSourceError(
            "Requests to private or internal network addresses are forbidden."
        )


def _content_type(header: str | None) -> str:
    if not header:
        return ""
    return header.split(";", 1)[0].strip().lower()


def _bounded_body(response: httpx.Response, max_bytes: int) -> bytes:
    content_length = response.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise PermanentSourceError("Source response exceeded the configured size limit.")
        except ValueError:
            pass
    body = response.content
    if len(body) > max_bytes:
        raise PermanentSourceError("Source response exceeded the configured size limit.")
    return body


def _safe_domain(url: str) -> str:
    parsed = urlparse(url)
    return (parsed.hostname or "").lower()
