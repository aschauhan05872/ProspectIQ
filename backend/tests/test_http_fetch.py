from __future__ import annotations

import ipaddress

import httpx
import pytest

from prospectiq.domain.ingestion import PermanentSourceError, RetryableSourceError
from prospectiq.infrastructure.http_fetch import FetchLimits, SafeHttpFetcher


def _public_resolve(_host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    return [ipaddress.ip_address("8.8.8.8")]


def _fetcher(
    handler: object,
    *,
    resolve: object = _public_resolve,
    limits: FetchLimits | None = None,
) -> SafeHttpFetcher:
    return SafeHttpFetcher(
        limits or FetchLimits(max_response_bytes=64, max_redirects=2),
        resolve_host=resolve,  # type: ignore[arg-type]
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_successful_html_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "example.com"
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="<html><title>Acme</title><body>Hello</body></html>",
        )

    result = await _fetcher(handler).get("https://example.com")
    assert result.status_code == 200
    assert result.content_type == "text/html"
    assert b"Acme" in result.body


@pytest.mark.asyncio
async def test_non_2xx_is_permanent() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, headers={"content-type": "text/html"}, text="missing")

    with pytest.raises(PermanentSourceError, match="404"):
        await _fetcher(handler).get("https://example.com/missing")


@pytest.mark.asyncio
async def test_timeout_is_retryable() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    with pytest.raises(RetryableSourceError, match="timed out"):
        await _fetcher(handler).get("https://example.com")


@pytest.mark.asyncio
async def test_oversized_response_is_rejected() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html", "content-length": "1000"},
            text="x" * 80,
        )

    with pytest.raises(PermanentSourceError, match="size limit"):
        await _fetcher(handler).get("https://example.com")


@pytest.mark.asyncio
async def test_invalid_content_type_is_rejected() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF")

    with pytest.raises(PermanentSourceError, match="content type"):
        await _fetcher(handler).get("https://example.com/file.pdf")


@pytest.mark.asyncio
async def test_redirect_to_public_host_is_followed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/go":
            return httpx.Response(302, headers={"location": "https://example.com/final"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text="done")

    result = await _fetcher(handler).get("https://example.com/go")
    assert result.status_code == 200
    assert result.final_url.endswith("/final")


@pytest.mark.asyncio
async def test_redirect_to_private_address_is_blocked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})

    with pytest.raises(PermanentSourceError):
        await _fetcher(handler).get("https://example.com/go")


@pytest.mark.asyncio
async def test_dns_to_loopback_is_blocked() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text="nope")

    def resolve(_host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        return [ipaddress.ip_address("127.0.0.1")]

    with pytest.raises(PermanentSourceError, match="private or internal"):
        await _fetcher(handler, resolve=resolve).get("https://example.com")


@pytest.mark.asyncio
async def test_server_error_is_retryable() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, headers={"content-type": "text/html"}, text="busy")

    with pytest.raises(RetryableSourceError, match="503"):
        await _fetcher(handler).get("https://example.com")
