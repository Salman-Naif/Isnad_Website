"""API tests: POST /api/search and the verdicts it returns."""

import pytest

from app.models.schemas import SiteConfig
from app.services.database import DatabaseError
from tests.conftest import BOOK_PASSAGE, HADITH


def search(client, query="إنما الأعمال بالنيات"):
    return client.post("/api/search", json={"query": query})


def test_same_text_as_a_ruled_hadith_is_verified(client, db):
    db.matches = [HADITH]
    body = search(client).json()
    assert body["verdict"] == "verified"
    best = body["results"][0]
    assert best["hukm"] == "صحيح" and best["mohaddith"] == "البخاري ومسلم"
    assert [n["name"] for n in best["sanad"]] == ["النبي ﷺ", "عمر بن الخطاب"]


def test_same_text_from_a_book_is_found_not_verified(client, db):
    db.matches = [BOOK_PASSAGE]
    assert search(client).json()["verdict"] == "found"


@pytest.mark.parametrize(("similarity", "verdict"), [
    (0.91, "verified"),
    (0.89, "distorted"),
    (0.70, "distorted"),
    (0.60, "distorted"),
    (0.59, "no_match"),
    (0.10, "no_match"),
])
def test_thresholds(client, db, similarity, verdict):
    db.matches = [HADITH.model_copy(update={"similarity": similarity})]
    assert search(client).json()["verdict"] == verdict


def test_results_are_sorted_best_first(client, db):
    db.matches = [HADITH.model_copy(update={"id": "a", "similarity": 0.5}), HADITH]
    sims = [r["similarity"] for r in search(client).json()["results"]]
    assert sims == sorted(sims, reverse=True)


def test_empty_database(client, db):
    body = search(client).json()
    assert body["verdict"] == "no_match" and body["results"] == []


def test_search_is_reported_for_statistics(client, db):
    db.matches = [HADITH]
    search(client, "  إنما الأعمال بالنيات  ")
    [event] = db.events
    assert event["type"] == "search"
    assert event["query"] == "إنما الأعمال بالنيات"
    assert event["result"] == "verified"


def test_blank_query(client):
    assert search(client, "   ").status_code == 422


def test_maintenance_and_switched_off_search(client, db):
    db.config = SiteConfig(maintenance_mode=True, maintenance_message="صيانة")
    res = search(client)
    assert res.status_code == 503 and res.json()["detail"] == "صيانة"

    db.config = SiteConfig(search_enabled=False)
    assert search(client).status_code == 503


def test_database_unavailable(client, db):
    db.error = DatabaseError("خدمة قاعدة البيانات غير متاحة حاليًا")
    res = search(client)
    assert res.status_code == 503
    assert "غير متاحة" in res.json()["detail"]


def test_a_saying_that_only_sounds_like_a_hadith_is_no_match(client, db):
    # «صوموا تصحوا» landed on an unrelated short hadith at 0.73 with no word in common.
    db.matches = [HADITH.model_copy(update={"similarity": 0.73, "word_overlap": 0.0})]
    assert search(client).json()["verdict"] == "no_match"


def test_an_altered_quote_is_a_distortion(client, db):
    db.matches = [HADITH.model_copy(update={"similarity": 0.68, "word_overlap": 0.85})]
    assert search(client).json()["verdict"] == "distorted"

