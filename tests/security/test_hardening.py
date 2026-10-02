"""Security tests: headers, CSP-safe markup, and nothing secret in what the browser receives."""

import re


def test_page_never_reveals_the_site_key_or_database_url(client):
    html = client.get("/").text + client.get("/static/js/app.js").text
    assert "test-site-key" not in html
    assert "database.test" not in html


def test_security_headers(client):
    res = client.get("/")
    csp = res.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert res.headers["x-frame-options"] == "DENY"
    assert res.headers["x-content-type-options"] == "nosniff"


def test_page_has_no_inline_styles_or_scripts(client):
    # The CSP only allows the site's own files; inline code would be blocked in the browser.
    html = client.get("/").text
    assert not re.search(r"\sstyle=", html)
    assert not re.search(r"<script(?![^>]*\ssrc=)", html)


def test_api_docs_are_off(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
