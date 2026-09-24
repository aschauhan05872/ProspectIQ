from __future__ import annotations

from prospectiq.infrastructure.html_normalize import normalize_page

HTML = b"""
<html>
  <head>
    <title>  Acme Health  </title>
    <style>body { color: red; }</style>
    <script>alert('xss')</script>
  </head>
  <body>
    <nav>Home About Careers</nav>
    <h1>We build software</h1>
    <h2>Platform</h2>
    <p>Custom   integrations   for hospitals.</p>
    <footer>Copyright</footer>
  </body>
</html>
"""


def test_title_headings_and_noise_removal() -> None:
    page = normalize_page(HTML, "text/html")
    assert page.title == "Acme Health"
    assert "We build software" in page.headings
    assert "Platform" in page.headings
    assert "Custom integrations for hospitals." in page.text
    assert "alert" not in page.text
    assert "color: red" not in page.text
    assert "Home About Careers" not in page.text
    assert "Copyright" not in page.text


def test_plain_text_passthrough() -> None:
    page = normalize_page(b"Hello   world\n\nthere", "text/plain")
    assert page.title is None
    assert page.text == "Hello world there"
