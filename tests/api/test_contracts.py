"""API tests: the shape of each response the page's JavaScript relies on."""

import pytest

from app.models.schemas import Match, SiteConfig
from app.services.rag import RAGError

HADITH = Match(id="h1", text="إنما الأعمال بالنيات", similarity=0.97, kind="structured_hadith",
               hukm="صحيح", mohaddith="البخاري", source="صحيح البخاري")


def test_search_response_shape(client, db):
    db.matches = [HADITH]
    body = client.post("/api/search", json={"query": "إنما الأعمال بالنيات"}).json()
    assert set(body) == {"query", "verdict", "verdict_message", "results", "sanad_tree", "sanad_sources",
                         "sanad_extracted", "language", "searched_as"}
    assert (body["language"], body["searched_as"]) == ("ar", None)
    assert set(body["results"][0]) == {"text", "similarity", "word_overlap", "match_type", "verdict",
                                       "verdict_message", "kind", "hukm", "mohaddith", "sanad", "sanad_tree",
                                       "sanad_extracted", "words", "topic", "source", "compiler"}
    assert body["results"][0]["words"][0] == {"word": "إنما", "changed": False}
    assert body["verdict"] in {"verified", "found", "distorted", "meaning", "no_match"}


def test_search_top_k_is_passed_on_and_bounded(client, db):
    client.post("/api/search", json={"query": "نص", "top_k": 7})
    assert db.searches == [("نص", 7)]
    assert client.post("/api/search", json={"query": "نص", "top_k": 0}).status_code == 422


def test_chat_response_shape_and_unique_sources(client, db, rag):
    db.matches = [HADITH, HADITH.model_copy(update={"id": "h2"})]
    body = client.post("/api/chat", json={"question": "ما حكمه؟", "context_query": "إنما الأعمال"}).json()
    assert set(body) == {"answer", "sources", "passages", "warnings", "refused"}
    assert body["sources"] == ["صحيح البخاري"]
    assert set(body["passages"][0]) == {"number", "text", "hukm", "mohaddith", "source"}


def test_chat_searches_the_hadith_first_then_the_question(client, db, rag):
    db.matches = [HADITH]
    client.post("/api/chat", json={"question": "ما حكمه؟", "context_query": "إنما الأعمال بالنيات"})
    assert [q for q, _ in db.searches] == ["إنما الأعمال بالنيات", "ما حكمه؟"]
    assert rag.calls[0]["subject"] == "إنما الأعمال بالنيات"


@pytest.mark.parametrize(("config", "status_code"), [
    (SiteConfig(maintenance_mode=True), 503),
    (SiteConfig(chat_enabled=False), 503),
    (SiteConfig(), 200),
])
def test_chat_follows_the_dashboard_switches(client, db, config, status_code):
    db.config = config
    assert client.post("/api/chat", json={"question": "سؤال"}).status_code == status_code


def test_chat_model_error_is_503_with_its_message(client, db, rag):
    db.matches = [HADITH]
    rag.error = RAGError("تعذّر الوصول إلى نموذج الحوار حاليًا")
    res = client.post("/api/chat", json={"question": "سؤال"})
    assert res.status_code == 503 and res.json() == {"detail": "تعذّر الوصول إلى نموذج الحوار حاليًا"}


def test_api_responses_are_not_cached(client, db):
    assert client.post("/api/search", json={"query": "نص"}).headers["cache-control"] == "no-store"


def test_page_is_html_and_health_is_json(client):
    assert client.get("/").headers["content-type"].startswith("text/html")
    assert client.get("/health").json() == {"status": "ok"}


def test_maintenance_page_asks_to_retry_later(client, db):
    db.config = SiteConfig(maintenance_mode=True)
    res = client.get("/")
    assert res.status_code == 503 and res.headers["retry-after"] == "600"
