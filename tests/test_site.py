"""The public page follows the dashboard controls, counts visits, and ships safe headers."""

import re

from app.models.schemas import SiteConfig


def test_page_renders_search_and_chat(client, db):
    res = client.get("/")
    assert res.status_code == 200
    assert 'id="search-form"' in res.text and 'id="chat-form"' in res.text


def test_page_view_is_counted_with_an_anonymous_visitor_cookie(client, db):
    res = client.get("/")
    cookie = res.cookies.get("isnad_vid")
    assert cookie and len(cookie) == 32
    assert "httponly" in res.headers["set-cookie"].lower()
    assert db.events == [{"type": "visit", "visitor_id": cookie, "query": "", "result": ""}]

    client.get("/")  # same visitor on the next visit
    assert db.events[1]["visitor_id"] == cookie


def test_maintenance_mode_shows_the_message(client, db):
    db.config = SiteConfig(maintenance_mode=True, maintenance_message="صيانة قصيرة")
    res = client.get("/")
    assert res.status_code == 503
    assert "صيانة قصيرة" in res.text
    assert 'id="search-form"' not in res.text


def test_announcement_banner(client, db):
    db.config = SiteConfig(announcement="تم تحديث المصادر")
    assert "تم تحديث المصادر" in client.get("/").text


def test_switched_off_features_are_hidden(client, db):
    db.config = SiteConfig(search_enabled=False, chat_enabled=False)
    html = client.get("/").text
    assert 'id="search-form"' not in html and 'id="chat-form"' not in html
    assert "البحث متوقف مؤقتًا" in html and "الحوار متوقف مؤقتًا" in html


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


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_api_docs_are_off(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
