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

from app.api.deps import ensure_open, get_database, visitor_id
from app.config import get_settings
from app.core.rate_limit import rate_limited
from app.models.schemas import ExploreRequest, ExploreResponse, ExploreResult
from app.services.database import DatabaseClient, DatabaseError

router = APIRouter(
    tags=["explore"], dependencies=[Depends(rate_limited("search", "search_per_minute"))]
)


@router.post("/explore", response_model=ExploreResponse)
def explore(
    payload: ExploreRequest,
    request: Request,
    background: BackgroundTasks,
    db: DatabaseClient = Depends(get_database),
) -> ExploreResponse:
    ensure_open(db, "search")
    query = payload.query.strip()
    if not query:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="النص فارغ")

    started = time.perf_counter()
    try:
        matches = db.search(query, payload.top_k)
    except DatabaseError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    floor = get_settings().explore_min_similarity
    results = sorted(
        (
            ExploreResult(
                text=m.text, similarity=round(min(1.0, max(0.0, m.similarity)), 4), kind=m.kind,
                hukm=m.hukm, mohaddith=m.mohaddith, topic=m.topic, source=m.source,
            )
            for m in matches
            if m.similarity >= floor
        ),
        key=lambda r: r.similarity,
        reverse=True,
    )
    background.add_task(
        db.record_event, "search", visitor_id(request), query, "explore",
        int((time.perf_counter() - started) * 1000),
    )
    return ExploreResponse(query=query, results=results)
