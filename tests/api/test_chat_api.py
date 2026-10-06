"""API tests: POST /api/chat."""

from app.models.schemas import SiteConfig
from app.services import guard
from app.services.rag import RAGError
from tests.conftest import BOOK_PASSAGE, HADITH


def ask(client, **payload):
    return client.post("/api/chat", json={"question": "ما حكم هذا الحديث؟", **payload})


def test_answer_uses_passages_from_the_database(client, db, rag):
    db.matches = [HADITH, BOOK_PASSAGE]
    res = ask(client, context_query="إنما الأعمال بالنيات")

    assert res.status_code == 200, res.text
    assert res.json() == {
        "answer": "إجابة تجريبية [1]",
        "warnings": [],
        "refused": False,
        "sources": ["صحيح البخاري", "كتاب.pdf"],
        # numbered as in the model's context, so «[2]» in the answer is passage 2
        "passages": [
            {"number": 1, "text": HADITH.text, "hukm": "صحيح", "mohaddith": "البخاري ومسلم", "source": "صحيح البخاري"},
            {"number": 2, "text": BOOK_PASSAGE.text, "hukm": None, "mohaddith": None, "source": "كتاب.pdf"},
        ],
    }
    [call] = rag.calls
    assert call["contexts"][0].hukm == "صحيح"
    assert len({c.id for c in call["contexts"]}) == len(call["contexts"])  # no duplicates
    # The model is told which text "this hadith" means
    assert call["subject"] == "إنما الأعمال بالنيات"
    # The searched text is looked up first, then the question itself
    assert [q for q, _ in db.searches] == ["إنما الأعمال بالنيات", "ما حكم هذا الحديث؟"]


def test_history_is_passed_to_the_model(client, db, rag):
    db.matches = [HADITH]
    ask(client, history=[{"role": "user", "content": "السلام عليكم"}, {"role": "assistant", "content": "وعليكم السلام"}])
    assert rag.calls[0]["history"][0] == {"role": "user", "content": "السلام عليكم"}


def test_question_is_reported_for_statistics(client, db):
    db.matches = [HADITH]
    ask(client)
    assert db.events[0]["type"] == "chat"
    assert db.events[0]["query"] == "ما حكم هذا الحديث؟"


def test_model_failure(client, db, rag):
    db.matches = [HADITH]
    rag.error = RAGError("تعذّر الوصول إلى نموذج الحوار حاليًا")
    res = ask(client)
    assert res.status_code == 503
    assert res.json()["detail"] == "تعذّر الوصول إلى نموذج الحوار حاليًا"


def test_chat_switched_off(client, db):
    db.config = SiteConfig(chat_enabled=False)
    assert ask(client).status_code == 503


# --- /api/chat/stream: the answer as the model writes it, one JSON object per line ---


def stream(client, **payload):
    import json

    res = client.post("/api/chat/stream", json={"question": "ما حكم هذا الحديث؟", **payload})
    return res, [json.loads(line) for line in res.text.splitlines() if line.strip()]


def test_stream_sends_the_passages_then_the_answer_piece_by_piece(client, db, rag):
    db.matches = [HADITH]
    res, events = stream(client, context_query="إنما الأعمال بالنيات")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/x-ndjson")
    assert res.headers["cache-control"] == "no-store"
    assert [e["type"] for e in events] == ["passages", "delta", "delta", "check", "done"]
    assert events[3] == {"type": "check", "warnings": [], "refused": False}
    assert events[0]["passages"][0]["number"] == 1 and events[0]["sources"] == ["صحيح البخاري"]
    assert "".join(e["text"] for e in events if e["type"] == "delta") == "إجابة تجريبية [1]"
    assert rag.calls[0]["subject"] == "إنما الأعمال بالنيات"


def test_stream_is_reported_once_the_answer_is_sent(client, db):
    db.matches = [HADITH]
    stream(client)
    assert [(e["type"], e["query"]) for e in db.events] == [("chat", "ما حكم هذا الحديث؟")]


def test_stream_unreachable_model_is_an_error_status(client, db, rag):
    db.matches = [HADITH]
    rag.error = RAGError("تعذّر الوصول إلى نموذج الحوار حاليًا")
    res, _ = stream(client)
    assert res.status_code == 503 and res.json()["detail"] == "تعذّر الوصول إلى نموذج الحوار حاليًا"


def test_stream_failure_midway_ends_with_an_error_line(client, db, rag):
    def pieces():
        yield "بداية "
        raise RAGError("انقطعت الإجابة قبل اكتمالها، حاول مرة أخرى")

    db.matches = [HADITH]
    rag.pieces = pieces()
    res, events = stream(client)
    assert res.status_code == 200
    assert [e["type"] for e in events] == ["passages", "delta", "error"]
    assert events[-1]["detail"] == "انقطعت الإجابة قبل اكتمالها، حاول مرة أخرى"


def test_stream_follows_the_chat_switch_and_database(client, db):
    db.config = SiteConfig(chat_enabled=False)
    assert stream(client)[0].status_code == 503
    db.config = SiteConfig()
    from app.services.database import DatabaseError

    db.error = DatabaseError("خدمة قاعدة البيانات غير متاحة حاليًا")
    assert stream(client)[0].status_code == 503


# --- Staying in scope and on the sources ---


def test_passages_unrelated_to_the_question_never_reach_the_model(client, db, rag):
    """The closest text to «ما عاصمة فرنسا؟» is still some hadith: below the floor it is dropped,
    and with nothing left the fixed answer is given without calling the model."""
    db.matches = [HADITH.model_copy(update={"similarity": 0.52})]
    body = ask(client, question="ما عاصمة فرنسا؟").json()
    assert body["answer"] == guard.NO_CONTEXT_ANSWER
    assert body["passages"] == [] and body["refused"] is True
    assert rag.calls == []


def test_only_the_related_passages_are_given(client, db, rag):
    db.matches = [HADITH, BOOK_PASSAGE.model_copy(update={"similarity": 0.4})]
    ask(client)
    assert [c.id for c in rag.calls[0]["contexts"]] == [HADITH.id]


def test_an_out_of_scope_refusal_comes_without_passages(client, db, rag):
    db.matches = [HADITH]
    rag.reply = guard.OUT_OF_SCOPE_ANSWER
    body = ask(client, question="اكتب لي قصيدة").json()
    assert body == {"answer": guard.OUT_OF_SCOPE_ANSWER, "sources": [], "passages": [], "warnings": [],
                    "refused": True}


def test_a_quotation_missing_from_the_sources_is_flagged(client, db, rag):
    db.matches = [HADITH]
    rag.reply = "قال النبي ﷺ: «صوموا تصحوا وسافروا تغنموا» [1]"
    body = ask(client).json()
    assert len(body["warnings"]) == 1 and "صوموا تصحوا" in body["warnings"][0]


def test_the_stream_reports_the_check_before_done(client, db, rag):
    db.matches = [HADITH]
    rag.pieces = ["قال: «لا يؤمن أحدكم حتى يحب لأخيه» ", "[7]"]
    _, events = stream(client)
    check = next(e for e in events if e["type"] == "check")
    assert len(check["warnings"]) == 2 and check["refused"] is False  # unsourced quote, citation [7]


def test_a_chain_without_its_own_text_is_not_given_to_the_model(client, db, rag):
    """«… عن عائشة عن النبي ﷺ بمثله» points to a hadith elsewhere in the book: given alone, the
    model attributed the wrong hadith to ʿAisha."""
    db.matches = [HADITH, HADITH.model_copy(update={
        "id": "m5", "text": "حدثنا هشام بن عروة عن أبيه عن عائشة عن النبي صلى الله عليه وسلم بمثله ."})]
    ask(client)
    assert [c.id for c in rag.calls[0]["contexts"]] == [HADITH.id]


def test_a_question_is_searched_by_its_subject_too(client, db):
    from app.models.schemas import Match

    db.matches = [Match(id="niyya", text="إنما الأعمال بالنيات", similarity=0.8, kind="structured_hadith")]
    client.post("/api/chat", json={"question": "من روى حديث النية؟"})
    assert db.searches[0][0] == "النية" and db.by_title[0] is True  # the subject, by title
    assert db.searches[1][0] == "من روى حديث النية؟" and db.by_title[1] is False  # then the question


def test_a_question_with_no_subject_of_its_own_searches_the_text_first(client, db):
    client.post("/api/chat", json={"question": "من رواه؟ وما حكمه؟", "context_query": "إنما الأعمال بالنيات"})
    assert [s[0] for s in db.searches] == ["إنما الأعمال بالنيات", "من رواه؟ وما حكمه؟"]
    assert db.by_title == [False, False]
