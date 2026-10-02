"""API tests: the public page follows the dashboard controls and counts visits."""

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


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
