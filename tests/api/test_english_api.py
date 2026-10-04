"""API tests: English texts through verification, search by meaning and the chat."""

from app.services import guard
from app.services.rag import RAGError
from tests.conftest import HADITH

ENGLISH = "Actions are but by intentions"


def test_an_english_text_is_searched_through_its_arabic_rendering(client, db, rag):
    db.matches = [HADITH.model_copy(update={"similarity": 1.0, "word_overlap": 1.0})]
    rag.renderings[ENGLISH] = "إنما الأعمال بالنيات"
    body = client.post("/api/search", json={"query": ENGLISH}).json()
    assert rag.translations == [ENGLISH] and db.searches[0][0] == "إنما الأعمال بالنيات"
    assert (body["language"], body["searched_as"], body["query"]) == ("en", "إنما الأعمال بالنيات", ENGLISH)
    assert body["verdict"] == "meaning" and body["verdict_message"].startswith("A hadith with this meaning")
    [best] = body["results"]
    assert best["text"] == HADITH.text and best["hukm"] == "صحيح" and best["words"] == []
    assert body["sanad_tree"] is not None  # the hadith found keeps its isnad
    assert db.events[-1]["query"] == ENGLISH  # the statistics keep what the visitor wrote


def test_without_a_rendering_only_a_strong_match_counts(client, db, rag):
    rag.translation_error = RAGError("down")
    db.matches = [HADITH.model_copy(update={"similarity": 0.7})]
    body = client.post("/api/search", json={"query": ENGLISH}).json()
    assert db.searches[0][0] == ENGLISH and body["searched_as"] is None
    assert body["verdict"] == "no_match"


def test_an_arabic_text_is_never_translated(client, db, rag):
    db.matches = [HADITH]
    body = client.post("/api/search", json={"query": "إنما الأعمال بالنيات"}).json()
    assert rag.translations == [] and body["language"] == "ar" and body["verdict"] == "verified"


def test_search_by_meaning_takes_an_english_idea(client, db, rag):
    db.matches = [HADITH]
    rag.renderings["kindness to parents"] = "بر الوالدين"
    body = client.post("/api/explore", json={"query": "kindness to parents"}).json()
    assert db.searches[0][0] == "بر الوالدين"
    assert (body["language"], body["searched_as"]) == ("en", "بر الوالدين")


def test_an_english_question_finds_its_passages_in_arabic(client, db, rag):
    db.matches = [HADITH]
    rag.renderings.update({"Who narrated it?": "من رواه؟", ENGLISH: "إنما الأعمال بالنيات"})
    rag.reply = "Narrated by al-Bukhari «إنما الأعمال بالنيات» [1]."
    body = client.post("/api/chat", json={"question": "Who narrated it?", "context_query": ENGLISH}).json()
    assert [s[0] for s in db.searches] == ["إنما الأعمال بالنيات", "من رواه؟"]
    assert body["answer"] == rag.reply and body["warnings"] == [] and not body["refused"]
    assert rag.calls[0]["question"] == "Who narrated it?"  # the model is asked the visitor's question


def test_an_english_question_with_nothing_in_the_sources(client, db, rag):
    db.matches = []
    body = client.post("/api/chat", json={"question": "What is the capital of France?"}).json()
    assert body["answer"] == guard.NO_CONTEXT_ANSWER_EN and body["refused"] and rag.calls == []


def test_the_answer_check_speaks_the_question_language(client, db, rag):
    db.matches = [HADITH]
    rag.reply = "Narrated by al-Bukhari."  # cites nothing
    body = client.post("/api/chat", json={"question": "Who narrated the hadith on intentions?"}).json()
    assert body["warnings"] == [guard._WARNINGS["en"]["uncited"]]
