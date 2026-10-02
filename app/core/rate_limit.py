"""
In-memory rate limiting.

Search and chat are public, so this is what keeps a single visitor (or a bot) from running up
the OpenRouter bill. In-memory is enough for a single Railway instance; it resets on restart.

Two limits apply to every request:
  - per visitor IP — the fair share of one visitor;
  - for the whole site — a ceiling on the cost. The IP comes from X-Forwarded-For, which a
    client can add values to before Railway's proxy appends its own: a bot rotating made-up
    addresses gets past the per-IP limit, never past this one.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.config import get_settings

MAX_KEYS = 10_000  # past this many, keys with no hit left in the window are forgotten
SITE = "*"  # the key of the whole-site counter


class RateLimiter:
    """Sliding-window counter: at most `limit` hits per `window_seconds` per key."""

    def __init__(self, window_seconds: int) -> None:
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int) -> bool:
        now = time.monotonic()
        with self._lock:
            if len(self._hits) > MAX_KEYS:
                self._forget_idle(now)
            hits = self._hits[key]
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True

    def _forget_idle(self, now: float) -> None:
        # A key's newest hit is its last one: once that is out of the window, so is the key.
        # (Checking for empty queues only would keep every address seen once, forever.)
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= now - self.window]:
            del self._hits[key]


_limiters: dict[str, RateLimiter] = {}


def client_ip(request: Request) -> str:
    # Behind Railway's proxy this is the address from X-Forwarded-For, because uvicorn
    # runs with --proxy-headers (see the Dockerfile). Not proof of identity: see above.
    return request.client.host if request.client else "unknown"


def rate_limited(name: str, setting: str, window_seconds: int = 60):
    """Dependency factory: limits are read from Settings.<setting> (per visitor) and
    Settings.<setting>_site (whole site) on each request."""

    def dependency(request: Request) -> None:
        settings = get_settings()
        visitors = _limiters.setdefault(name, RateLimiter(window_seconds))
        if not visitors.hit(client_ip(request), getattr(settings, setting)):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="طلبات كثيرة، حاول مرة أخرى بعد قليل",
                headers={"Retry-After": str(window_seconds)},
            )
        site = _limiters.setdefault(f"{name}{SITE}", RateLimiter(window_seconds))
        if not site.hit(SITE, getattr(settings, f"{setting}_site")):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="الخدمة مشغولة الآن، حاول مرة أخرى بعد دقيقة",
                headers={"Retry-After": str(window_seconds)},
            )

    return dependency


def reset_rate_limits() -> None:
    """Clear all counters (used by tests)."""
    _limiters.clear()
