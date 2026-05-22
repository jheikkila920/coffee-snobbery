"""Admin router sub-package — Phase 9.

Expands the Phase 2 single-file stub (``app/routers/admin.py``) into a proper
sub-package. The ``router`` exported here is the same object that
``app/main.py`` already imports as ``admin_router.router``; the import path
``app.routers.admin`` resolves identically whether it is a module or a package.

Sub-routers for each admin section (users, credentials, settings_editor,
backups, system) are included via import guards: if a feature module does not
yet exist the guard swallows the ``ImportError`` and the hub route keeps
working. Each feature plan (09-02..09-06) only has to create its own module
file — no edits to this file are needed.
"""

from __future__ import annotations

import importlib

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response

from app.dependencies.auth import require_admin
from app.models.user import User
from app.templates_setup import templates

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin")

# ---------------------------------------------------------------------------
# Hub route — GET /admin
# ---------------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
def admin_hub(
    request: Request,
    user: User = Depends(require_admin),  # noqa: B008
) -> Response:
    """Landing hub for the admin section (D-01).

    Renders an overview page that links to the five sub-sections. Gated by
    ``require_admin`` so non-admins receive 403.
    """
    return templates.TemplateResponse(
        request=request,
        name="pages/admin.html",
        context={"user": user},
    )


# ---------------------------------------------------------------------------
# Feature sub-router auto-include with import guards
#
# Each guard imports the feature module and calls router.include_router().
# A missing module (ImportError) is silently swallowed so this package ships
# fully functional before any feature plan has run.  Plans 09-02..09-06 are
# purely additive — they create their module file and never touch this block.
# ---------------------------------------------------------------------------

_SUB_MODULES = [
    "users",
    "credentials",
    "settings_editor",
    "backups",
    "system",
]

for _name in _SUB_MODULES:
    try:
        _sub = importlib.import_module(f"app.routers.admin.{_name}")
    except ModuleNotFoundError as exc:
        # Only swallow "this exact module file is absent"; a broken import
        # *inside* an existing module must not be silently dropped.
        if exc.name == f"app.routers.admin.{_name}":
            log.warning("admin.submodule_absent", module=_name)
            continue
        raise
    router.include_router(_sub.router)
