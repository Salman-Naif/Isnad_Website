"""
Client for the Isnad database service (the Isnad_Database repository).

All calls go server-to-server with SITE_API_KEY in the X-API-Key header; the key never
reaches the visitor's browser.

  site_config()   controls set in the dashboard (cached for a few seconds)
  search()        the stored passages closest to a query, with ruling and sanad
  record_event()  report a visit / search / chat question for the dashboard statistics
"""

import logging
import threading
import time

import httpx

from app.config import get_settings
from app.models.schemas import Match, SiteConfig

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """The database service couldn't answer (message is shown to the visitor)."""


UNAVAILABLE = "خدمة قاعدة البيانات غير متاحة حاليًا، حاول مرة أخرى بعد قليل"
RETRY_DELAYS = (1.0, 2.0)  # seconds before the 2nd and 3rd try
RETRY_STATUSES = {502, 503, 504}


class DatabaseClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = httpx.Client(
            base_url=self.settings.database_url,
            headers={"X-API-Key": self.settings.site_api_key},
            timeout=self.settings.database_timeout_seconds,
        )
        self._config: SiteConfig | None = None
        self._config_fetched_at = 0.0
        self._lock = threading.Lock()

    def _post(self, path: str, payload: dict) -> httpx.Response:
        if not (self.settings.database_url and self.settings.site_api_key):
            logger.error("DATABASE_URL or SITE_API_KEY is not set")
            raise DatabaseError(UNAVAILABLE)
        # A redeploy stops the database service for a moment (its volume moves to the new
        # copy): a refused connection or a 502/503/504 is tried again shortly, so a visitor
        # rarely sees it. A slow answer is not: it already waited its full timeout.
        for delay in RETRY_DELAYS:
            try:
                res = self._client.post(path, json=payload)
            except (httpx.ConnectError, httpx.RemoteProtocolError):
                pass
            except httpx.HTTPError as exc:
                logger.error("Database service unreachable: %s", exc)
                raise DatabaseError(UNAVAILABLE) from exc
            else:
                if res.status_code not in RETRY_STATUSES:
                    return res
            time.sleep(delay)
        try:
            return self._client.post(path, json=payload)
        except httpx.HTTPError as exc:
            logger.error("Database service unreachable: %s", exc)
            raise DatabaseError(UNAVAILABLE) from exc

    def site_config(self) -> SiteConfig:
        """Dashboard controls, cached; if the database is unreachable, the last known ones."""
        with self._lock:
            fresh = time.monotonic() - self._config_fetched_at < self.settings.site_config_cache_seconds
            if self._config is not None and fresh:
                return self._config
            try:
                res = self._client.get("/api/v1/site-config")
                res.raise_for_status()
                self._config = SiteConfig(**res.json())
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("Could not read site config: %s", exc)
                if self._config is None:
                    return SiteConfig()  # defaults: site open, features on
            self._config_fetched_at = time.monotonic()
            return self._config

    def search(self, query: str, top_k: int, by_title: bool = False) -> list[Match]:
        body = {"query": query, "top_k": top_k, **({"by_title": True} if by_title else {})}
        res = self._post("/api/v1/search", body)
        if res.status_code == 401:
            logger.error("The database refused SITE_API_KEY — it must match the database service")
            raise DatabaseError(UNAVAILABLE)
        if res.status_code == 422:
            return []
        if res.status_code != 200:
            logger.error("Database search failed (%s): %s", res.status_code, res.text[:300])
            raise DatabaseError(UNAVAILABLE)
        return [Match(**m) for m in res.json().get("matches", [])]

    def record_event(
        self,
        type_: str,
        visitor_id: str,
        query: str = "",
        result: str = "",
        latency_ms: int | None = None,
    ) -> None:
        """Best effort: statistics must never break or slow down the visitor's request."""
        try:
            self._post("/api/v1/events", {
                "type": type_,
                "visitor_id": visitor_id,
                "query": query[:2000],
                "result": result,
                "latency_ms": latency_ms,
            })
        except DatabaseError:
            pass
        except Exception:
            logger.exception("Could not record %s event", type_)
