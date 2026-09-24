from __future__ import annotations

import pytest

from prospectiq.domain.source_registry import SourceClass
from prospectiq.domain.source_url import InvalidSourceUrl, parse_source_url


def test_valid_https_is_normalized() -> None:
    parsed = parse_source_url("HTTPS://WWW.Example.COM/About/")
    assert parsed.normalized == "https://example.com/About"
    assert parsed.identity_host == "example.com"
    assert parsed.origin == "https://example.com"
    assert parsed.source_class is SourceClass.COMPANY_WEBSITE
    assert parsed.identity_requires_review is False


def test_careers_path_is_classified() -> None:
    parsed = parse_source_url("https://acme.com/careers")
    assert parsed.source_class is SourceClass.CAREERS_PAGE


def test_http_and_https_same_identity() -> None:
    http = parse_source_url("http://www.acme.com/")
    https = parse_source_url("https://acme.com")
    assert http.identity_host == https.identity_host == "acme.com"


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "not-a-url",
        "",
        "https://user:secret@example.com",
        "https://linkedin.com/company/acme",
        "https://www.linkedin.com/in/someone",
        "http://localhost/careers",
        "http://127.0.0.1/",
        "http://192.168.1.20/",
        "http://10.0.0.8/",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/",
    ],
)
def test_invalid_or_forbidden_urls(url: str) -> None:
    with pytest.raises(InvalidSourceUrl):
        parse_source_url(url)
