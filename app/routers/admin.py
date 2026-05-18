"""Admin surface — Phase 2 stub; Phase 9 expands into the full admin app.

Single route ``GET /admin`` per CONTEXT D-13:

* Body is the literal "Admin (stub) — wiring lands in Phase 9", rendered
  inside ``pages/admin.html`` which extends ``base.html`` (CSP nonce flows
  through; future Phase 9 work has an existing-template hook).
* Gated by :func:`app.dependencies.auth.require_admin` (Form 1 — receives
  the User object so Phase 9's expansion has the user parameter wired).
* Returns 200 for admin, 403 for non-admin OR anonymous (require_admin
  folds both into the same 403 per D-13 + AUTH-09 VALIDATION row).

Phase 9 will add sub-routes for ADMIN-01..06 (user CRUD, API keys,
app_settings editor, backups, system info, API health). All of those
will share this router's import path and the same require_admin gate.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response

from app.dependencies.auth import require_admin
from app.models.user import User
from app.templates_setup import templates

router = APIRouter()


@router.get("/admin", response_class=HTMLResponse)
def admin_stub(
    request: Request,
    user: User = Depends(require_admin),  # noqa: B008 — FastAPI canonical Form 1; Depends() in arg default is the framework idiom (see 02-RESEARCH §"Depends(require_admin) pattern").
) -> Response:
    """D-13: Admin stub — 200 with literal body, gated by is_admin.

    The ``user`` parameter is unused in Phase 2 but the Form 1 dependency
    shape is forward-compatible: Phase 9 reads ``user.username`` /
    ``user.is_admin`` / ``user.email`` directly in the same handler shape.
    """
    return templates.TemplateResponse(
        request=request,
        name="pages/admin.html",
        context={"user": user},
    )
