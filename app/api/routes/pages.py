"""
The public page. Follows the controls set in the database dashboard: maintenance mode
shows a maintenance page; the announcement banner and the search / chat switches are
applied on the page. Each page view is reported as a visit for the statistics.
"""

import hashlib

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.api.deps import VISITOR_COOKIE, VISITOR_COOKIE_MAX_AGE, get_database, visitor_id
from app.config import BASE_DIR
from app.services.database import DatabaseClient

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


def _asset_version() -> str:
    """Changes whenever a stylesheet or script does, so browsers fetch the new one with the new
    page instead of pairing the new page with a cached script."""
    digest = hashlib.sha256()
    for path in sorted((BASE_DIR / "app" / "static").rglob("*.*")):
        digest.update(path.read_bytes())
    return digest.hexdigest()[:10]


templates.env.globals["asset_version"] = _asset_version()

router = APIRouter(include_in_schema=False)


@router.get("/", response_class=HTMLResponse)
def index(request: Request, background: BackgroundTasks, db: DatabaseClient = Depends(get_database)):
    config = db.site_config()
    if config.maintenance_mode:
        return templates.TemplateResponse(
            request, "maintenance.html", {"config": config}, status_code=503,
            headers={"Retry-After": "600"},
        )

    vid = visitor_id(request)
    response = templates.TemplateResponse(request, "index.html", {"config": config})
    if request.cookies.get(VISITOR_COOKIE) != vid:
        # Anonymous random id, only for counting unique visitors — no personal data.
        response.set_cookie(
            VISITOR_COOKIE, vid, max_age=VISITOR_COOKIE_MAX_AGE, httponly=True,
            samesite="lax", secure=request.url.scheme == "https", path="/",
        )
    background.add_task(db.record_event, "visit", vid)
    return response
