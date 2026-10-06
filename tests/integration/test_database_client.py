"""Integration tests: the client for the database service, against a fake HTTP server."""

import json

import httpx
import pytest

from app.config import get_settings
from app.services.database import DatabaseClient, DatabaseError


def client_with(handler) -> tuple[DatabaseClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    db = DatabaseClient()
    db._client = httpx.Client(
        base_url="http://database.test",
        headers={"X-API-Key": "test-site-key"},
        transport=httpx.MockTransport(record),
    )
    return db, seen


MATCH = {"id": "hadith-1", "text": "نص", "similarity": 0.97, "kind": "structured_hadith", "hukm": "صحيح",
         "sanad": [{"name": "النبي ﷺ", "grade": "المصدر"}]}


def test_search_sends_the_site_key_and_parses_matches():
    db, seen = client_with(lambda r: httpx.Response(200, json={"matches": [MATCH]}))
    [match] = db.search("نص", 3)

    assert seen[0].url.path == "/api/v1/search"
    assert seen[0].headers["x-api-key"] == "test-site-key"
    assert json.loads(seen[0].content) == {"query": "نص", "top_k": 3}
    assert match.hukm == "صحيح" and match.sanad[0].name == "النبي ﷺ"


def test_a_search_by_title_says_so():
    db, seen = client_with(lambda r: httpx.Response(200, json={"matches": []}))
    db.search("الصيام", 20, by_title=True)
    assert json.loads(seen[0].content) == {"query": "الصيام", "top_k": 20, "by_title": True}


@pytest.mark.parametrize("status_code", [401, 500, 503])
def test_search_failures_become_a_friendly_error(status_code):
    db, _ = client_with(lambda r: httpx.Response(status_code, json={}))
    with pytest.raises(DatabaseError, match="غير متاحة"):
        db.search("نص", 3)


def test_unreachable_database():
    def down(request):
        raise httpx.ConnectError("offline")

    db, _ = client_with(down)
    with pytest.raises(DatabaseError):
        db.search("نص", 3)


def test_site_config_is_cached():
    db, seen = client_with(lambda r: httpx.Response(200, json={"maintenance_mode": True, "maintenance_message": "صيانة",
                                                                 "search_enabled": True, "chat_enabled": False,
                                                                 "announcement": "", "main_site_url": ""}))
    first = db.site_config()
    second = db.site_config()
    assert first.maintenance_mode and not first.chat_enabled
    assert second is first
    assert len(seen) == 1


def test_site_config_falls_back_when_the_database_is_down(monkeypatch):
    responses = iter([httpx.Response(200, json={"announcement": "إعلان"}), httpx.Response(503)])
    db, _ = client_with(lambda r: next(responses))
    monkeypatch.setattr(get_settings(), "site_config_cache_seconds", 0)

    assert db.site_config().announcement == "إعلان"
    assert db.site_config().announcement == "إعلان"  # last known controls, not a crash


def test_site_config_defaults_when_never_reached():
    def down(request):
        raise httpx.ConnectError("offline")

    db, _ = client_with(down)
    config = db.site_config()
    assert not config.maintenance_mode and config.search_enabled and config.chat_enabled


def test_events_never_raise():
    db, seen = client_with(lambda r: httpx.Response(500))
    db.record_event("visit", "v" * 32)  # must not raise
    assert json.loads(seen[0].content)["type"] == "visit"
