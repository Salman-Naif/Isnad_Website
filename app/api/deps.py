"""
Dependencies shared across routes.

The database client and the chat-model client keep their connections open, so each
is created once and reused. Visitors are recognised by an anonymous random cookie,
used only to count unique visitors in the dashboard statistics.
"""

import uuid
from functools import lru_cache
from typing import Literal

from fastapi import HTTPException, Request, status

from app.services.database import DatabaseClient
from app.services.rag import RAGService

VISITOR_COOKIE = "isnad_vid"
VISITOR_COOKIE_MAX_AGE = 365 * 24 * 3600


@lru_cache
def get_database() -> DatabaseClient:
    return DatabaseClient()


@lru_cache
def get_rag() -> RAGService:
    return RAGService()


def visitor_id(request: Request) -> str:
    """The visitor's anonymous id (set by the page), or a fresh one."""
    value = request.cookies.get(VISITOR_COOKIE, "")
    return value if len(value) == 32 and value.isalnum() else uuid.uuid4().hex


def ensure_open(db: DatabaseClient, feature: Literal["search", "chat"]) -> None:
    """Refuse the request while the dashboard has the site or this feature switched off."""
    config = db.site_config()
    if config.maintenance_mode:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=config.maintenance_message)
    if feature == "search" and not config.search_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="البحث متوقف مؤقتًا")
    if feature == "chat" and not config.chat_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="الحوار متوقف مؤقتًا")
