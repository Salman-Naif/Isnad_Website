"""Integration tests: the database client's edge cases, and the chat service through the real
OpenAI SDK against a fake OpenRouter (so the exact request the SDK sends is checked)."""

import json

import httpx
import openai
import pytest

from app.config import get_settings
from app.models.schemas import Match
from app.services import database
from app.services.database import DatabaseError
from app.services.rag import RAGError, RAGService
from tests.integration.test_database_client import client_with

# --- Database client ---


def test_search_422_means_no_results():
    db, _ = client_with(lambda r: httpx.Response(422, json={"detail": "Empty query"}))
    assert db.search("َ", 5) == []


@pytest.mark.parametrize("status_code", [401, 500, 503])
def test_search_errors_become_the_friendly_message(status_code):
    db, _ = client_with(lambda r: httpx.Response(status_code, json={}))
    with pytest.raises(DatabaseError, match="غير متاحة"):
        db.search("نص", 5)


def test_missing_configuration_is_reported_without_calling(monkeypatch):
    db, seen = client_with(lambda r: httpx.Response(200, json={"matches": []}))
    monkeypatch.setattr(db.settings, "database_url", "")
    with pytest.raises(DatabaseError):
        db.search("نص", 5)
    assert seen == []


def test_events_are_sent_truncated_with_latency():
    db, seen = client_with(lambda r: httpx.Response(204))
    db.record_event("search", "v" * 32, query="x" * 5000, result="verified", latency_ms=42)
    body = json.loads(seen[0].content)
    assert seen[0].url.path == "/api/v1/events"
    assert len(body["query"]) == 2000
    assert body == {"type": "search", "visitor_id": "v" * 32, "query": "x" * 2000,
                    "result": "verified", "latency_ms": 42}


def test_config_cache_expires(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(database.time, "monotonic", lambda: now[0])
    replies = iter([{"announcement": "أول"}, {"announcement": "ثان"}])
    db, seen = client_with(lambda r: httpx.Response(200, json=next(replies)))
    assert db.site_config().announcement == "أول"
    now[0] += get_settings().site_config_cache_seconds - 1
    assert db.site_config().announcement == "أول"  # still cached
    now[0] += 2
    assert db.site_config().announcement == "ثان"
    assert len(seen) == 2


def test_malformed_config_keeps_the_last_good_one(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(database.time, "monotonic", lambda: now[0])
    replies = iter([httpx.Response(200, json={"maintenance_mode": True}),
                    httpx.Response(200, content=b"not json")])
    db, _ = client_with(lambda r: next(replies))
    assert db.site_config().maintenance_mode is True
    now[0] += 3600
    assert db.site_config().maintenance_mode is True


# --- Chat service through the real OpenAI SDK ---


def rag_over(monkeypatch, handler) -> tuple[RAGService, list[httpx.Request]]:
    monkeypatch.setattr(get_settings(), "openrouter_api_key", "sk-or-test")
    seen: list[httpx.Request] = []

    def record(request):
        seen.append(request)
        return handler(request)

    service = RAGService()
    service._client = openai.OpenAI(
        base_url="https://openrouter.test/api/v1", api_key="sk-or-test", max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(record)),
    )
    return service, seen


PASSAGE = Match(id="h1", text="إنما الأعمال بالنيات", similarity=0.95, kind="structured_hadith", hukm="صحيح")


def completion(content: str) -> dict:
    return {"id": "c1", "object": "chat.completion", "created": 0, "model": "m",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}]}


def test_request_the_sdk_sends_to_openrouter(monkeypatch):
    service, seen = rag_over(monkeypatch, lambda r: httpx.Response(200, json=completion("صحيح، رواه البخاري")))
    assert service.answer("ما حكمه؟", [PASSAGE]) == "صحيح، رواه البخاري"

    [request] = seen
    body = json.loads(request.content)
    assert request.url.path == "/api/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer sk-or-test"
    assert body["model"] == get_settings().llm_model
    assert body["reasoning"] == {"enabled": False}  # extra_body is merged into the JSON
    assert body["max_tokens"] == get_settings().llm_max_tokens
    assert [m["role"] for m in body["messages"]] == ["system", "user"]


@pytest.mark.parametrize("status_code", [401, 429, 500, 502])
def test_openrouter_errors_become_friendly_messages(monkeypatch, status_code):
    service, _ = rag_over(monkeypatch, lambda r: httpx.Response(status_code, json={"error": {"message": "x"}}))
    with pytest.raises(RAGError, match="تعذّر"):
        service.answer("سؤال", [PASSAGE])


def test_missing_key_is_reported_before_any_call(monkeypatch):
    service, seen = rag_over(monkeypatch, lambda r: httpx.Response(200, json=completion("x")))
    service._client = None
    monkeypatch.setattr(service.settings, "openrouter_api_key", "")
    with pytest.raises(RAGError, match="غير مهيأة"):
        service.answer("سؤال", [PASSAGE])
    assert seen == []


def sse(*pieces: str) -> bytes:
    """A streamed completion as OpenRouter sends it (server-sent events)."""
    events = [
        {"id": "c1", "object": "chat.completion.chunk", "created": 0, "model": "m",
         "choices": [{"index": 0, "delta": {"content": p}, "finish_reason": None}]}
        for p in pieces
    ]
    return "".join(f"data: {json.dumps(e, ensure_ascii=False)}\n\n" for e in events).encode() + b"data: [DONE]\n\n"


def test_stream_asks_for_a_streamed_answer_and_yields_its_pieces(monkeypatch):
    service, seen = rag_over(monkeypatch, lambda r: httpx.Response(
        200, content=sse("صحيح، ", "رواه البخاري [1]"), headers={"Content-Type": "text/event-stream"}))
    assert list(service.stream("ما حكمه؟", [PASSAGE])) == ["صحيح، ", "رواه البخاري [1]"]
    assert json.loads(seen[0].content)["stream"] is True


def test_stream_unreachable_model_fails_before_any_piece(monkeypatch):
    service, _ = rag_over(monkeypatch, lambda r: httpx.Response(502, json={"error": {"message": "x"}}))
    with pytest.raises(RAGError, match="تعذّر"):
        service.stream("سؤال", [PASSAGE])


def test_stream_with_no_text_is_an_error(monkeypatch):
    service, _ = rag_over(monkeypatch, lambda r: httpx.Response(
        200, content=b"data: [DONE]\n\n", headers={"Content-Type": "text/event-stream"}))
    with pytest.raises(RAGError, match="لم يُرجع"):
        list(service.stream("سؤال", [PASSAGE]))
