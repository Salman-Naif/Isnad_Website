"""
Chat with the model (RAG) — public, rate limited per IP.

The question is answered from the passages the database finds for it (and for the text
the visitor last searched), not from the model's general knowledge. The answer cites the
passages by number ([1], [2]…) and they are sent with it, so the visitor can read them.

  POST /api/chat          the whole answer at once (JSON)
  POST /api/chat/stream   the answer as the model writes it, one JSON object per line:
                            {"type": "passages", "passages": [...], "sources": [...]}
                            {"type": "delta", "text": "..."}   (repeated)
                            {"type": "check", "warnings": [...], "refused": false}
                            {"type": "done"}  or  {"type": "error", "detail": "..."}

Guarding against answers outside the scope or not backed by the sources, in three layers:
  1. retrieval — passages below CHAT_MIN_SIMILARITY are dropped; with none left, a fixed answer
     is given and the model is not called;
  2. the prompt — the rules of the challenge's reference pack (app/services/rag.py);
  3. the answer check — quotations, citations and sourcing are verified against the passages
     (app/services/guard.py) and what fails is shown next to the answer.
"""

import json
import time
from collections.abc import Iterator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.api.deps import ensure_open, get_database, get_rag, visitor_id
from app.config import get_settings
from app.core.rate_limit import rate_limited
from app.models.schemas import ChatPassage, ChatRequest, ChatResponse, Match
from app.services import guard
from app.services.database import DatabaseClient, DatabaseError
from app.services.language import language_of
from app.services.query import for_question, for_search, subject_of
from app.services.rag import RAGError, RAGService

router = APIRouter(
    tags=["chat"], dependencies=[Depends(rate_limited("chat", "chat_per_minute"))]
)


def retrieve(db: DatabaseClient, searched: str, asked: list[tuple[str, bool]], limit: int) -> list[Match]:
    """Passages without duplicates: the searched hadith's first, then the question's — its
    subject's (searched by title) and its own words' — taken in turn."""
    queries = ([(searched, False)] if searched else []) + asked
    per_text = max(1, limit // max(1, len(queries)) + 1)
    results = [db.search(text, per_text, by_title=by_title) for text, by_title in queries]
    lead, rest = (results[0], results[1:]) if searched else ([], results)
    turns = [found[i] for i in range(per_text) for found in rest if i < len(found)]
    unique: dict[str, Match] = {}
    for match in lead + turns:
        unique.setdefault(match.id, match)
    return list(unique.values())[:limit]


def _contexts(db: DatabaseClient, rag: RAGService, payload: ChatRequest) -> list[Match]:
    settings = get_settings()
    # An English searched text looks for its passages through its Arabic rendering; an English
    # question through its word-for-word rendering, and a question through its subject too.
    searched = for_search(payload.context_query.strip(), rag)[0] if payload.context_query.strip() else ""
    asked: list[tuple[str, bool]] = []
    if payload.question.strip():
        question = for_question(payload.question.strip(), rag)
        subject = subject_of(question)
        asked = ([(subject, True)] if subject else []) + [(question, False)]
    try:
        found = retrieve(db, searched, asked, settings.chat_context_passages)
    except DatabaseError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    # Only passages that are about the question: the closest text to «ما عاصمة فرنسا؟» is still
    # some hadith, and given to the model it invites an answer the sources don't support. Nor a
    # chain ending «بمثله»: without the text it points to, it can't be told which hadith it is.
    return [m for m in found if m.similarity >= settings.chat_min_similarity and not guard.refers_back(m.text)]


def _check(answer: str, contexts: list[Match], payload: ChatRequest) -> tuple[list[str], bool]:
    """(warnings about the answer, whether it is a refusal resting on no passage)."""
    own = [t for t in (payload.question, payload.context_query) if t.strip()]
    rulings = [f"{m.hukm or ''} {m.mohaddith or ''}" for m in contexts]
    warnings = guard.check_answer(answer, [m.text for m in contexts], own, rulings, language_of(payload.question))
    return warnings, guard.is_refusal(answer)


def _sources(contexts: list[Match]) -> list[str]:
    return list(dict.fromkeys(m.source for m in contexts if m.source))


def _passages(contexts: list[Match]) -> list[ChatPassage]:
    """Numbered as in the model's context, so «[2]» in the answer is passage 2 here."""
    return [
        ChatPassage(number=n, text=m.text, hukm=m.hukm, mohaddith=m.mohaddith, source=m.source)
        for n, m in enumerate(contexts, start=1)
    ]


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    request: Request,
    background: BackgroundTasks,
    db: DatabaseClient = Depends(get_database),
    rag: RAGService = Depends(get_rag),
) -> ChatResponse:
    ensure_open(db, "chat")
    started = time.perf_counter()
    contexts = _contexts(db, rag, payload)
    try:
        # Nothing in the sources is about the question: the model is not asked at all.
        answer = guard.no_context_answer(language_of(payload.question)) if not contexts else rag.answer(
            payload.question,
            contexts,
            history=[m.model_dump() for m in payload.history],
            subject=payload.context_query.strip(),
        )
    except RAGError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    background.add_task(
        db.record_event, "chat", visitor_id(request), payload.question, "",
        int((time.perf_counter() - started) * 1000),
    )
    warnings, refused = _check(answer, contexts, payload)
    if refused:
        return ChatResponse(answer=answer, refused=True)
    return ChatResponse(
        answer=answer, sources=_sources(contexts), passages=_passages(contexts), warnings=warnings,
    )


def _line(event: dict) -> bytes:
    return (json.dumps(event, ensure_ascii=False) + "\n").encode()


@router.post("/chat/stream")
def chat_stream(
    payload: ChatRequest,
    request: Request,
    background: BackgroundTasks,
    db: DatabaseClient = Depends(get_database),
    rag: RAGService = Depends(get_rag),
) -> StreamingResponse:
    ensure_open(db, "chat")
    started = time.perf_counter()
    contexts = _contexts(db, rag, payload)
    try:
        # Opened before the response starts: an unreachable model is still a 503. Nothing in
        # the sources is about the question: the model is not asked at all.
        pieces = iter([guard.no_context_answer(language_of(payload.question))]) if not contexts else rag.stream(
            payload.question,
            contexts,
            history=[m.model_dump() for m in payload.history],
            subject=payload.context_query.strip(),
        )
    except RAGError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    def events() -> Iterator[bytes]:
        yield _line({
            "type": "passages",
            "passages": [p.model_dump() for p in _passages(contexts)],
            "sources": _sources(contexts),
        })
        answer = []
        try:
            for text in pieces:
                answer.append(text)
                yield _line({"type": "delta", "text": text})
        except RAGError as exc:
            yield _line({"type": "error", "detail": str(exc)})
            return
        warnings, refused = _check("".join(answer), contexts, payload)
        yield _line({"type": "check", "warnings": warnings, "refused": refused})
        yield _line({"type": "done"})

    # Runs once the whole answer has been sent.
    background.add_task(
        db.record_event, "chat", visitor_id(request), payload.question, "",
        int((time.perf_counter() - started) * 1000),
    )
    return StreamingResponse(
        events(), media_type="application/x-ndjson", background=background,
        # Proxies must pass each line on as it comes, not hold the answer back.
        headers={"X-Accel-Buffering": "no"},
    )
