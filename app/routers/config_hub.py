"""Config hub router — catalog landing page + mobile account surface (Phase 11, Plan 03).

Routes:
  GET /config — catalog hub page, links to all five catalog entities.
                Mobile-only section shows user identity + sign-out CSRF POST form (D-03).

Gated by ``Depends(require_user)`` — anonymous users get 401.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response

from app.dependencies.auth import require_user
from app.models.user import User
from app.templates_setup import templates

router = APIRouter()


@router.get("/config", response_class=HTMLResponse)
def config_hub(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
) -> Response:
    """Render the catalog hub page (Phase 11 D-03).

    No DB queries needed — the hub links are static.
    The user object is passed for the mobile sign-out identity display.
    """
    return templates.TemplateResponse(
        request=request,
        name="pages/config_hub.html",
        context={"user": user},
    )
