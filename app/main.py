"""
Isnad main website — entry point.

The public site: visitors verify a hadith or quote and ask the model about it. The sources
and their search live in the separate database service (Isnad_Database), reached through its API
with SITE_API_KEY; the chat model is called through OpenRouter.

  /             the page (search + chat), or the maintenance page
  /api/search   verify a text
  /api/explore  hadiths about an idea (search by meaning)
  /api/chat     ask the model, answered only from the sources
  /health       liveness
"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.api.routes import chat, explore, health, pages, search
from app.config import BASE_DIR, get_settings
from app.core.logging import setup_logging

settings = get_settings()
setup_logging(settings.log_level)

SECURITY_HEADERS = {
    # Only this site's own scripts, styles and API — no third-party code can run on the page.
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; font-src 'self'; object-src 'none'; frame-ancestors 'none'; "
        "base-uri 'self'; form-action 'self'"
    ),
    # Visitors only ever reach the site over HTTPS once they have seen it (Railway serves
    # HTTPS; the header is ignored on plain-HTTP localhost).
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}

app = FastAPI(
    title="Isnad",
    version="1.0.0",
    # The API is for this site's own page, not a public developer API.
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")

app.include_router(pages.router)
app.include_router(health.router)
app.include_router(search.router, prefix="/api")
app.include_router(explore.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
