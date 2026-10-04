"""
Verification — public, rate limited per IP.

Flow:
    visitor text → database search (/api/v1/search) → thresholds → verdict, ruling,
    the words that differ from the source, and the isnad tree merged across the books

An English text is searched through an Arabic rendering of it (app/services/query.py); the
verdict then says whether a hadith with that meaning is in the sources.
"""

import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

from app.api.deps import ensure_open, get_database, get_rag, visitor_id
from app.core.rate_limit import rate_limited
from app.models.schemas import SearchRequest, SearchResponse, Verdict
from app.services.database import DatabaseClient, DatabaseError
from app.services.query import for_search
from app.services.rag import RAGService
from app.services.verification import build_results, merged_isnad, verdict_message

router = APIRouter(
    tags=["search"], dependencies=[Depends(rate_limited("search", "search_per_minute"))]
)


@router.post("/search", response_model=SearchResponse)
def search(
    payload: SearchRequest,
    request: Request,
    background: BackgroundTasks,
    db: DatabaseClient = Depends(get_database),
    rag: RAGService = Depends(get_rag),
) -> SearchResponse:
    ensure_open(db, "search")
    query = payload.query.strip()
    if not query:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="النص فارغ")

    started = time.perf_counter()
    text, lang, searched_as = for_search(query, rag)
    try:
        matches = db.search(text, payload.top_k)
    except DatabaseError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    results = build_results(matches, text, lang, translated=searched_as is not None)
    verdict = results[0].verdict if results else Verdict.NO_MATCH
    tree, tree_sources, extracted = merged_isnad(results)
    # Reported after the response is sent, so statistics never slow the visitor down.
    background.add_task(
        db.record_event, "search", visitor_id(request), query, verdict.value,
        int((time.perf_counter() - started) * 1000),
    )
    return SearchResponse(
        query=query, verdict=verdict, verdict_message=verdict_message(verdict, lang), results=results,
        sanad_tree=tree, sanad_sources=tree_sources, sanad_extracted=extracted,
        language=lang, searched_as=searched_as,
    )
