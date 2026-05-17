"""FastAPI application factory — Phase 0 (Plan 00-04).

This is the module ``entrypoint.sh`` resolves via ``uvicorn app.main:app``.
It wires the four substrates Phase 0 has built so far:

- :mod:`app.config` — pydantic-settings ``Settings`` (Plan 00-01).
- :mod:`app.logging` — structlog ``configure_logging`` (Plan 00-02).
- :mod:`app.db` — SQLAlchemy 2.0 sync engine + ``dispose_engine`` (Plan 00-03).
- ``app/templates`` + ``app/static`` — Jinja2 templates with autoescape ON
  and the content-hashed Tailwind CSS path computed once at app-factory time
  (this plan's Task 1).

Phase 0 owns exactly two HTTP routes (CONTEXT D-12):

- ``GET /healthz`` — DB-touching; opens a transaction, applies
  ``SET LOCAL statement_timeout = '2000ms'`` so a hanging query cannot extend
  the response window beyond the CONTEXT D-08 2-second ceiling, then issues
  ``SELECT 1``. Returns ``{"status": "ok"}`` on success, ``503`` with
  ``{"status": "error"}`` on failure.

- ``GET /`` — renders the placeholder ``pages/index.html``.

Phase 1 adds middleware (CSRF, session, request_id binding, security
headers); Phase 2 adds the ``/setup`` router; Phase 4+ adds the catalog
routers. Each lands additively — this module never gains a hard-coded
router import.

Anti-patterns intentionally avoided here:

- ``@app.on_event("startup"/"shutdown")`` — deprecated upstream; use
  :func:`contextlib.asynccontextmanager` ``lifespan`` only.
- ``async def healthz(...)`` calling sync ``Session.execute(...)`` — blocks
  the event loop. Phase 0 ships ONLY sync handlers.
- A second engine for the healthz timeout — duplicates pool bookkeeping and
  still inherits the main engine's pool-acquisition timeout. Per-request
  ``SET LOCAL statement_timeout`` is the simpler psycopg-native pattern.
- Mounting ``app/static/photos`` — Phase 4 owns photos via a custom router
  with auth + ownership checks.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.config import settings
from app.db import dispose_engine, engine
from app.logging import configure_logging

log = structlog.get_logger(__name__)


def compute_tailwind_css_path() -> str:
    """Resolve the content-hashed Tailwind CSS to a ``/static/...`` URL path.

    Globs ``app/static/css/tailwind.*.css`` excluding the source file
    (``tailwind.src.css``) and returns the URL path for the single hashed
    result. Called ONCE at app-factory time (CONTEXT D-15) — never per
    request. Phase 11 may replace this with a full asset manifest.

    Raises:
        RuntimeError: When zero hashed files match (Dockerfile stage 1 did
            not run / did not emit anything) or when multiple match
            (something went wrong in the build; listing the duplicates so
            an operator can diagnose).
    """
    css_dir = Path("app/static/css")
    candidates = sorted(
        p for p in css_dir.glob("tailwind.*.css") if p.name != "tailwind.src.css"
    )
    if not candidates:
        raise RuntimeError(
            "Tailwind CSS missing — Dockerfile stage 1 did not produce "
            "app/static/css/tailwind.<hash>.css"
        )
    if len(candidates) > 1:
        raise RuntimeError(
            "Multiple hashed Tailwind CSS files found — expected exactly one: "
            + ", ".join(str(p) for p in candidates)
        )
    return f"/static/css/{candidates[0].name}"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open the structured logger and verify DB reachability before yielding.

    Startup order matters: ``configure_logging`` runs first so any
    SQLAlchemy or engine warnings during the smoke SELECT land in the
    structured stream. The smoke connection uses the main engine's pool
    knobs (Plan 00-03 / CONTEXT D-10); a failure here aborts startup,
    which is intended — a container that cannot reach Postgres should
    exit, not serve broken responses.

    Shutdown calls :func:`app.db.dispose_engine` so checked-in connections
    are closed cleanly before the worker exits.
    """
    # Startup
    configure_logging(format=settings.LOG_FORMAT, level=settings.LOG_LEVEL)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    log.info("app.startup", version=app.version)
    yield
    # Shutdown
    log.info("app.shutdown")
    dispose_engine()


def create_app() -> FastAPI:
    """Build the FastAPI app, mount static + templates, register Phase 0 routes."""
    app = FastAPI(lifespan=lifespan, title="Snobbery", version="0.1.0")

    # /static serves everything under app/static — Tailwind CSS, future JS,
    # PWA manifest icons. Photos (Phase 4) get their own auth-gated router.
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    # Jinja2Templates defaults to autoescape=True; do NOT touch that.
    templates = Jinja2Templates(directory="app/templates")
    templates.env.globals["tailwind_css_path"] = compute_tailwind_css_path()
    app.state.templates = templates

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        """DB-touching healthcheck (CONTEXT D-08).

        Opens a transaction with the main engine (pool-acquisition still
        bounded by the engine's ``pool_timeout=5``), applies a
        per-transaction ``SET LOCAL statement_timeout = '2000ms'`` so the
        following SELECT cannot exceed the CONTEXT D-08 2-second ceiling,
        then executes ``SELECT 1``. The literal strings
        ``SET LOCAL statement_timeout`` and ``2000ms`` are present here so
        a future audit / grep can confirm the timeout is honored without
        running the code.

        On failure, logs an ``app.healthz_failed`` structured event with
        the exception CLASS NAME only — never the traceback — to avoid
        leaking SQL parameter values or DB error detail.
        """
        try:
            with engine.begin() as conn:
                conn.execute(text("SET LOCAL statement_timeout = '2000ms'"))
                conn.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001 — intentional broad catch; class name only logged
            log.warning("app.healthz_failed", error_class=type(exc).__name__)
            return JSONResponse({"status": "error"}, status_code=503)
        return JSONResponse({"status": "ok"})

    @app.get("/")
    def home(request: Request) -> object:
        """Render the Phase 0 placeholder home page (CONTEXT D-12)."""
        return request.app.state.templates.TemplateResponse(
            request=request, name="pages/index.html", context={}
        )

    return app


app = create_app()
