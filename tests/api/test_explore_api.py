"""API tests: POST /api/explore — the hadiths about an idea, closest in meaning first."""

import pytest

from app.models.schemas import Match, SiteConfig
from app.services.database import DatabaseError


def hadith(id_, similarity, text="نص", **fields):
    return Match(id=id_, text=text, similarity=similarity, kind="structured_hadith", **fields)


def explore(client, query="الصلاة أهم شيء", **body):
    return client.post("/api/explore", json={"query": query, **body})


def test_hadiths_about_the_idea_come_closest_first_with_their_ruling(client, db):
    db.matches = [
        hadith("t", 0.62, "بين الرجل وبين الشرك والكفر ترك الصلاة", hukm="صحيح", mohaddith="مسلم",
               topic="الصلاة", source="صحيح مسلم"),
        hadith("a", 0.71, "العهد الذي بيننا وبينهم الصلاة فمن تركها فقد كفر", hukm="صحيح",
               mohaddith="الألباني", source="جامع الترمذي"),
    ]
    body = explore(client).json()
    assert body["query"] == "الصلاة أهم شيء"
    assert [r["text"] for r in body["results"]] == [
        "العهد الذي بيننا وبينهم الصلاة فمن تركها فقد كفر",
        "بين الرجل وبين الشرك والكفر ترك الصلاة",
    ]
    assert body["results"][1] == {
        "text": "بين الرجل وبين الشرك والكفر ترك الصلاة", "similarity": 0.62, "kind": "structured_hadith",
        "hukm": "صحيح", "mohaddith": "مسلم", "topic": "الصلاة", "source": "صحيح مسلم",
    }


def test_texts_far_from_the_idea_are_left_out(client, db):
    db.matches = [hadith("near", 0.45), hadith("far", 0.4499)]
    assert [r["similarity"] for r in explore(client).json()["results"]] == [0.45]


def test_nothing_close_is_an_empty_list_not_an_error(client, db):
    db.matches = [hadith("far", 0.2)]
    res = explore(client)
    assert res.status_code == 200 and res.json()["results"] == []


def test_asks_the_database_for_ten_by_default(client, db):
    explore(client)
    assert db.searches == [("الصلاة أهم شيء", 10)]


def test_the_search_is_reported_for_the_statistics(client, db):
    explore(client)
    assert [(e["type"], e["query"], e["result"]) for e in db.events] == [("search", "الصلاة أهم شيء", "explore")]


@pytest.mark.parametrize("body", [{"query": ""}, {"query": "   "}, {"query": "x" * 501}, {"query": "ن", "top_k": 11}])
def test_invalid_input(client, db, body):
    assert client.post("/api/explore", json=body).status_code == 422
    assert db.searches == []


def test_database_unavailable(client, db):
    db.error = DatabaseError("خدمة قاعدة البيانات غير متاحة حاليًا")
    res = explore(client)
    assert res.status_code == 503 and "غير متاحة" in res.json()["detail"]


@pytest.mark.parametrize(("config", "detail"), [
    (SiteConfig(maintenance_mode=True, maintenance_message="صيانة"), "صيانة"),
    (SiteConfig(search_enabled=False), "البحث متوقف مؤقتًا"),
])
def test_follows_the_dashboard_switches(client, db, config, detail):
    db.config = config
    res = explore(client)
    assert res.status_code == 503 and res.json()["detail"] == detail
    assert db.searches == []


def test_shares_the_search_rate_limit(client, db, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "search_per_minute", 2)
    assert client.post("/api/search", json={"query": "نص"}).status_code == 200
    assert explore(client).status_code == 200
    assert explore(client).status_code == 429
