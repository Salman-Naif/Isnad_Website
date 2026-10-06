"""
Search by meaning — public, rate limited per IP (with verification).

Verification asks "is this text a known hadith?"; this asks "which hadiths are about this?".
The visitor writes an idea («الصلاة أهم شيء») and gets the stored texts closest to it in
meaning, whatever their words, closest first. No verdict: each one can then be verified.

Flow:
    visitor idea → database search (/api/v1/search, by meaning) → closest texts above
    EXPLORE_MIN_SIMILARITY, with ruling, scholar, topic and source
"""

import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

from app.api.deps import ensure_open, get_database, get_rag, visitor_id
from app.config import get_settings
from app.core.rate_limit import rate_limited
from app.models.schemas import ExploreRequest, ExploreResponse, ExploreResult
from app.services.database import DatabaseClient, DatabaseError
from app.services.grouping import group, is_subject
from app.services.query import for_search
from app.services.rag import RAGService

MAX_DB_TOP_K = 20  # the most the database returns

router = APIRouter(
    tags=["explore"], dependencies=[Depends(rate_limited("search", "search_per_minute"))]
)


@router.post("/explore", response_model=ExploreResponse)
def explore(
    payload: ExploreRequest,
    request: Request,
    background: BackgroundTasks,
    db: DatabaseClient = Depends(get_database),
    rag: RAGService = Depends(get_rag),
) -> ExploreResponse:
    ensure_open(db, "search")
    query = payload.query.strip()
    if not query:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="النص فارغ")

    started = time.perf_counter()
    text, lang, searched_as = for_search(query, rag)  # an English idea, through its Arabic rendering
    try:
        # More than shown: a hadith found in several books is shown once (grouping.group).
        matches = db.search(text, min(payload.top_k * 2, MAX_DB_TOP_K))
    except DatabaseError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    floor = get_settings().explore_min_similarity
    results = [
        ExploreResult(
            text=m.text, similarity=round(min(1.0, max(0.0, m.similarity)), 4), kind=m.kind,
            hukm=m.hukm, mohaddith=m.mohaddith, topic=m.topic, source=m.source,
        )
        for m in matches
        if m.similarity >= floor
    ]
    if not is_subject(text):  # a subject keeps the database's order (grouping.is_subject)
        results.sort(key=lambda r: r.similarity, reverse=True)
    results = group(results, payload.top_k)
    background.add_task(
        db.record_event, "search", visitor_id(request), query, "explore",
        int((time.perf_counter() - started) * 1000),
    )
    return ExploreResponse(query=query, results=results, language=lang, searched_as=searched_as)
