"""GET /search — live search results fragment endpoint (Phase 10, SEARCH-03/04).

This router exposes the single read-only endpoint that the persistent search
header calls via HTMX. It delegates all query logic to
``app.services.search.run_search`` and renders the grouped fragment.

Security notes:
  - ``require_user`` ensures unauthenticated callers receive 401 (T-10-AUTHZ).
  - No CSRF token required — GET is read-only; ``starlette-csrf`` only validates
    POST/PUT/PATCH/DELETE.
  - ``FragmentCacheHeadersMiddleware`` applies ``Cache-Control: no-store`` +
    ``Vary: HX-Request`` automatically on HTMX responses. No route-level headers.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.dependencies.auth import require_user
from app.dependencies.db import get_session
from app.models.user import User
from app.rate_limit import SEARCH_LIMIT, limiter
from app.services import search as search_service
from app.templates_setup import templates

router = APIRouter(prefix="/search")


@router.get("", response_class=HTMLResponse)
@limiter.limit(SEARCH_LIMIT)
def search_results(
    request: Request,
    q: str = "",
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Return a grouped search-results fragment for HTMX live search.

    Returns an empty 200 body when the query is shorter than 2 characters
    or longer than 100 characters (S4: cap on raw q before strip).
    """
    if len(q) > 100:  # S4: cap on raw q, before strip()
        return HTMLResponse("", status_code=200)
    if len(q.strip()) < 2:
        return HTMLResponse("", status_code=200)
    results = search_service.run_search(db, query=q.strip(), user_id=user.id)
    return templates.TemplateResponse(
        request=request,
        name="fragments/search_results.html",
        context={"results": results, "query": q.strip()},
    )


__all__ = ["router"]
