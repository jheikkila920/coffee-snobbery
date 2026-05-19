"""FastAPI application factory — assembled by Phase 1 Plan 09.

This is the module ``entrypoint.sh`` resolves via ``uvicorn app.main:app``.
It composes everything Phase 0 + Phase 1 have built:

- :mod:`app.config` — pydantic-settings ``Settings`` (Plan 00-01).
- :mod:`app.logging_config` — structlog ProcessorFormatter init shim
  delegating to :mod:`app.logging`'s :func:`configure_logging`
  (Plans 00-02 / 01-02).
- :mod:`app.db` — SQLAlchemy 2.0 sync engine + ``dispose_engine``
  (Plan 00-03). An async session factory for ``SessionMiddleware`` is
  composed here at module load (no dedicated Phase 0 helper yet — see
  SUMMARY note).
- The five-piece Phase 1 middleware stack and the slowapi limiter.
- The three Phase 1 routers (csp_report, auth, debug).

Middleware order (Starlette adds reverse-of-add; last added is OUTERMOST):

    1. SessionMiddleware            (INNERMOST — closest to route handler)
    2. CSRFMiddleware (starlette_csrf)
    3. CSRFFormFieldShim            (NEW Phase 2 D-15 — hoists form field to header)
    4. FragmentCacheHeadersMiddleware
    5. SecurityHeadersMiddleware
    6. RequestContextMiddleware     (OUTERMOST — closest to wire)

Why this order (RESEARCH §3 + §13.4 + §18.2):

- RequestContextMiddleware OUTERMOST so it mints ``request_id`` +
  ``csp_nonce`` on the request path BEFORE SecurityHeadersMiddleware reads
  the nonce on the response path (pitfall 13.4).
- CSRFMiddleware added AFTER SessionMiddleware so on the request path
  CSRFMiddleware runs FIRST (outside) and fail-fasts with 403 before the
  inner SessionMiddleware does any DB lookup — saves work on attack
  traffic (RESEARCH §3).
- CSRFFormFieldShim added BETWEEN CSRFMiddleware (added 2nd, runs 5th on the
  request path) and FragmentCacheHeadersMiddleware (added 3rd before shim
  → now 4th). On the request path the shim therefore runs JUST BEFORE
  CSRFMiddleware so its header injection is visible by the time
  starlette-csrf's header-only check runs. The shim is a no-op on requests
  that already have the X-CSRF-Token header (HTMX path), so the existing
  Phase 1 CSRF behavior is unchanged.
- SessionMiddleware INNERMOST so route handlers see ``request.state.user``
  already resolved when their handler body runs.

Phase 8 plugs APScheduler into ``lifespan`` here. Phase 0's DB smoke
``SELECT 1`` is preserved.

Anti-patterns intentionally avoided:

- Starlette's deprecated startup/shutdown event decorators — gone in
  Starlette 1.0; use :func:`contextlib.asynccontextmanager` ``lifespan``
  only.
- A second engine for the healthz timeout — duplicates pool bookkeeping
  and still inherits the main engine's pool-acquisition timeout.
- Mounting ``app/static/photos`` — Phase 4 owns photos via a custom
  router with auth + ownership checks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette_csrf import CSRFMiddleware

from app.config import settings
from app.csrf import CSRFFormFieldShim, csrf_middleware_kwargs
from app.db import SessionLocal, dispose_engine, engine
from app.logging_config import configure_logging
from app.middleware import (
    FragmentCacheHeadersMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
    SessionMiddleware,
)
from app.rate_limit import register_rate_limiter
from app.routers import admin as admin_router
from app.routers import auth as auth_router
from app.routers import coffees as coffees_router
from app.routers import csp_report as csp_report_router
from app.routers import debug as debug_router
from app.routers import equipment as equipment_router
from app.routers import flavor_notes as flavor_notes_router
from app.routers import photos as photos_router
from app.routers import recipes as recipes_router
from app.routers import roasters as roasters_router
from app.services import credentials
from app.services import settings as settings_service
from app.services.encryption import startup_check as encryption_startup_check
from app.templates_setup import templates

# Configure logging at module import so uvicorn's first log line already
# flows through the structlog ProcessorFormatter — running it inside
# ``lifespan`` would miss the uvicorn startup banner.
configure_logging(level=settings.LOG_LEVEL)

log = structlog.get_logger(__name__)


# Minimal async engine + factory for SessionMiddleware. Phase 0 ships a
# sync engine; Phase 1's services/sessions.py uses AsyncSession. The
# psycopg 3 driver supports both modes off the same connection URL —
# SQLAlchemy 2.0 picks the async path when the URL is consumed by
# ``create_async_engine``. A future Phase 0 follow-up may move this into
# :mod:`app.db`; until then the factory lives here (Plan 09 SUMMARY note).
_async_engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
async_session_factory = async_sessionmaker(_async_engine, expire_on_commit=False)


def compute_tailwind_css_path() -> str:
    """Resolve the content-hashed Tailwind CSS to a ``/static/...`` URL path.

    Globs ``app/static/css/tailwind.*.css`` excluding the source file
    and returns the URL path for the single hashed result. Called once
    at app-factory time. Raises if zero or multiple matches — see Phase 0
    Plan 04 for the rationale.
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
    """Startup smoke check + Phase 3 hooks + clean shutdown.

    Phase 8 will start APScheduler here; Phase 0's sync ``SELECT 1`` smoke
    against the main engine is preserved. Shutdown disposes both engines.

    Phase 3 hooks (D-16). All three are sync; await-free is fine inside the
    async lifespan body. ``encryption_startup_check`` runs FIRST so a bad
    ``APP_ENCRYPTION_KEY`` fails fast before any DB I/O. ``rewrap_if_needed``
    runs BEFORE ``prewarm_cache`` so the new fingerprint written by rewrap
    lands in the cache (T-03-T5). Any failure propagates: uvicorn exits
    non-zero, docker healthcheck flips unhealthy (T-03-T3). No outer
    ``try/except`` — the per-row guard inside ``rewrap_if_needed`` is the
    only swallow point.
    """
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    encryption_startup_check()  # raises EncryptionStartupError -> uvicorn exits non-zero
    with SessionLocal() as db:
        credentials.rewrap_if_needed(db)
        settings_service.prewarm_cache(db)
    log.info("app.startup", version=app.version)
    yield
    log.info("app.shutdown")
    dispose_engine()
    await _async_engine.dispose()


def create_app() -> FastAPI:
    """Build the FastAPI app, wire middleware + routers, register Phase 1 routes.

    Order:
    1. Construct app with lifespan (docs disabled in Phase 1 — /debug/proxy
       and /login stub aren't safe to surface without is_admin; Phase 2 may
       re-enable behind the admin gate).
    2. ``register_rate_limiter`` — must run before any router include so
       slowapi finds ``app.state.limiter`` at decoration-effective time.
    3. Mount StaticFiles at ``/static`` — BEFORE middleware adds so the
       FragmentCache ``/static/`` bypass sees the route on the right path.
    4. Add middleware (reverse-of-add ordering; see module docstring).
    5. Include routers.
    """
    app = FastAPI(
        lifespan=lifespan,
        title="Snobbery",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
    )

    register_rate_limiter(app)

    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    # Templates: Phase 0's app.state.templates wrapper still feeds the
    # placeholder home page; Phase 1's Plan 08 templates_setup.templates is
    # the canonical Jinja2Templates instance for new routes. The two share
    # the same directory — autoescape ON on both per SEC-05.
    templates.env.globals["tailwind_css_path"] = compute_tailwind_css_path()
    app.state.templates = templates

    # Middleware stack — last added is OUTERMOST (Starlette reverse-of-add).
    # Phase 2 D-15: CSRFFormFieldShim is added AFTER CSRFMiddleware so that on
    # the request path the shim runs OUTSIDE / BEFORE CSRFMiddleware. The shim
    # hoists the X-CSRF-Token form field into the request header before
    # CSRFMiddleware's header-only token check sees the request.
    app.add_middleware(SessionMiddleware, session_factory=async_session_factory)
    app.add_middleware(CSRFMiddleware, **csrf_middleware_kwargs(settings.APP_SECRET_KEY))
    app.add_middleware(CSRFFormFieldShim)
    app.add_middleware(FragmentCacheHeadersMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)

    # Routers.
    app.include_router(csp_report_router.router)
    app.include_router(auth_router.router)
    app.include_router(debug_router.router)
    app.include_router(admin_router.router)
    app.include_router(roasters_router.router)
    app.include_router(flavor_notes_router.router)
    app.include_router(coffees_router.router)
    app.include_router(equipment_router.router)
    app.include_router(recipes_router.router)
    app.include_router(photos_router.router)

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        """DB-touching healthcheck (CONTEXT D-08).

        Per-transaction ``SET LOCAL statement_timeout = '2000ms'`` caps the
        SELECT at the D-08 2-second ceiling. The literal strings are kept
        here so a grep audit can confirm the timeout without running code.
        """
        try:
            with engine.begin() as conn:
                conn.execute(text("SET LOCAL statement_timeout = '2000ms'"))
                conn.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001 — class name only logged
            log.warning("app.healthz_failed", error_class=type(exc).__name__)
            return JSONResponse({"status": "error"}, status_code=503)
        return JSONResponse({"status": "ok"})

    @app.get("/")
    def home(request: Request) -> object:
        """Render the placeholder home page (Phase 0).

        Phase 4 replaces this with the real home page route — keeping the
        Phase 0 template path here means existing healthcheck flows and
        manual smoke tests stay green during the Phase 1 → Phase 4
        transition.
        """
        return request.app.state.templates.TemplateResponse(
            request=request, name="pages/index.html", context={}
        )

    return app


app = create_app()
