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

The hub page (pages/admin.html) was removed in the Phase 9 gap-closure pass.
GET /admin now serves the System page; GET /admin/system 301-redirects to
/admin for bookmark compatibility.

Route registration note: the System page handler is defined in system.py but
registered directly on this package router (path "") because FastAPI raises
FastAPIError when include_router() combines an empty include-prefix with a ""
route path. The sub-router action routes (/system/ai-refresh,
/system/test-connection/*) are still registered via include_router as normal.
"""

from __future__ import annotations

import importlib

import structlog
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin")

# ---------------------------------------------------------------------------
# GET /admin — System page (registered directly; see module docstring for why)
# ---------------------------------------------------------------------------

# Import guard: if system.py hasn't landed yet, skip the registration and
# leave /admin without a handler (same graceful-degradation policy as the
# sub-router guards below).
try:
    from app.routers.admin.system import admin_system as _admin_system_fn

    router.add_api_route(
        "",
        _admin_system_fn,
        methods=["GET"],
        response_class=HTMLResponse,
        name="admin_system",
    )
except ImportError:
    log.warning("admin.submodule_absent", module="system (landing route)")


# ---------------------------------------------------------------------------
# Feature sub-router auto-include with import guards
#
# Each guard imports the feature module and calls router.include_router().
# A missing module (ImportError) is silently swallowed so the hub kept
# working before feature plans landed.  Plans 09-02..09-06 are purely
# additive — they create their module file and never touch this block.
# system.py registers GET "/system" (redirect) + action POSTs.
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
