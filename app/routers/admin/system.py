"""Admin system info + API health router — ADMIN-05 / ADMIN-06 / D-12.

Implements the /admin/system page (System Info + API Health panels) plus the
two AI-refresh action handlers (D-13/D-14) and the single canonical
test-connection probe (D-12 / PATTERNS.md Decision Table).

Security invariants:
  T-09-25: Status rows read via raw select(AppSetting...), NEVER get_str()
           — set_setting pops the cache key; next get_str raises.
  T-09-26: error_status from ai_recommendations is autoescaped + truncated.
  T-09-27: force-refresh is explicitly labeled; distinct generated_by tag.
  T-09-28: AI refresh handler is async def; regenerate is awaited.
  T-09-29: require_admin on every route.
  T-09-30: Only _get_eligible_user_ids() users are refreshed (Phase 8 filter).
  T-09-31: Decrypted API key never enters template context or logs; del client
           in finally.

Router auto-includes via the Plan 01 import guard — do NOT edit __init__.py.
"""

from __future__ import annotations

import json
import tomllib
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import events
from app.dependencies.auth import require_admin
from app.dependencies.db import get_session
from app.models.ai_recommendation import AIRecommendation
from app.models.app_setting import AppSetting
from app.models.user import User
from app.services import ai_service
from app.services import credentials as cred_service
from app.templates_setup import templates

log = structlog.get_logger(__name__)

router = APIRouter()

_VALID_PROVIDERS = {"anthropic", "openai"}
_ERROR_TRUNCATE_CHARS = 200
_LAST_N_ERRORS = 5

# Storage directories — these are the in-container production paths.
_PHOTOS_DIR = Path("/app/data/photos")
_BACKUPS_DIR = Path("/app/data/backups")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dir_size_bytes(path: Path) -> int:
    """Sum st_size for all files under *path*; return 0 if path does not exist."""
    if not path.exists():
        return 0
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except OSError:
                pass
    return total


def _human_size(n_bytes: int) -> str:
    """Format bytes as human-readable string (B / KB / MB / GB)."""
    if n_bytes < 1024:
        return f"{n_bytes} B"
    if n_bytes < 1024**2:
        return f"{n_bytes / 1024:.1f} KB"
    if n_bytes < 1024**3:
        return f"{n_bytes / 1024**2:.1f} MB"
    return f"{n_bytes / 1024**3:.2f} GB"


def _truncate_error(s: str | None) -> str | None:
    """Truncate a long error_status string to _ERROR_TRUNCATE_CHARS chars."""
    if s is None:
        return None
    if len(s) > _ERROR_TRUNCATE_CHARS:
        return s[:_ERROR_TRUNCATE_CHARS] + "…"
    return s


# ---------------------------------------------------------------------------
# GET /admin/system — 301 redirect to /admin (bookmark compatibility)
# ---------------------------------------------------------------------------


@router.get("/system", response_class=HTMLResponse)
def admin_system_redirect(
    user: User = Depends(require_admin),  # noqa: B008
) -> RedirectResponse:
    """301 redirect /admin/system → /admin (keeps bookmarks working)."""
    return RedirectResponse("/admin", status_code=301)


# ---------------------------------------------------------------------------
# admin_system — System Info + API Health handler (exposed for __init__.py)
#
# Registered as GET /admin (path "") directly on the package router in
# __init__.py to avoid the FastAPI empty-prefix + empty-path error that
# occurs when include_router() combines an empty include-prefix with a ""
# route path. The function is defined here so all system logic stays in one
# module, but the route registration happens in __init__.py.
# ---------------------------------------------------------------------------


def admin_system(
    request: Request,
    user: User = Depends(require_admin),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """System Info + API Health page — served at GET /admin.

    Reads are raw DB queries; never calls get_str() for status rows so the
    page cannot crash after a backup/AI run pops the cache key (Pitfall 2).
    """
    # --- System Info (ADMIN-05) ---
    try:
        app_version = pkg_version("coffee-snobbery")
    except PackageNotFoundError:
        # Fallback when the package is not installed (e.g., running tests
        # directly in the container without pip install -e).
        _pyproject = Path("/app/pyproject.toml")
        if _pyproject.exists():
            with _pyproject.open("rb") as _f:
                app_version = tomllib.load(_f).get("project", {}).get("version", "unknown")
        else:
            app_version = "unknown"

    db_version: str = db.execute(text("SELECT version()")).scalar() or "unknown"

    session_count: int = db.execute(
        text("SELECT COUNT(*) FROM sessions WHERE expires_at > now()")
    ).scalar_one()

    photo_bytes = _dir_size_bytes(_PHOTOS_DIR)
    backup_bytes = _dir_size_bytes(_BACKUPS_DIR)

    # last_backup_status — raw select, NOT get_str (Pitfall 2 / T-09-25)
    backup_row = db.execute(
        select(AppSetting.value).where(AppSetting.key == "last_backup_status")
    ).scalar_one_or_none()
    last_backup: dict | None = None
    if backup_row and backup_row != "never_run":
        try:
            last_backup = json.loads(backup_row)
        except (ValueError, TypeError):
            last_backup = None

    # --- API Health (ADMIN-06) ---
    # last_ai_run_status — raw select, NOT get_str (Pitfall 2 / T-09-25)
    ai_row = db.execute(
        select(AppSetting.value).where(AppSetting.key == "last_ai_run_status")
    ).scalar_one_or_none()
    last_ai_run: dict | None = None
    if ai_row:
        try:
            last_ai_run = json.loads(ai_row)
        except (ValueError, TypeError):
            last_ai_run = None

    # Per-provider: last success row, last error row, last 5 errors
    per_provider: dict[str, dict] = {}
    for provider in ("anthropic", "openai"):
        # Last success (error_status IS NULL)
        last_success_row = db.execute(
            select(AIRecommendation)
            .where(
                AIRecommendation.provider_used == provider,
                AIRecommendation.error_status.is_(None),
            )
            .order_by(AIRecommendation.generated_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        # Last error row
        last_error_row = db.execute(
            select(AIRecommendation)
            .where(
                AIRecommendation.provider_used == provider,
                AIRecommendation.error_status.isnot(None),
            )
            .order_by(AIRecommendation.generated_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        # Last N error rows
        recent_errors = db.execute(
            select(
                AIRecommendation.error_status,
                AIRecommendation.model_used,
                AIRecommendation.generated_at,
            )
            .where(
                AIRecommendation.provider_used == provider,
                AIRecommendation.error_status.isnot(None),
            )
            .order_by(AIRecommendation.generated_at.desc())
            .limit(_LAST_N_ERRORS)
        ).all()

        per_provider[provider] = {
            "last_success": last_success_row,
            "last_error": last_error_row,
            "last_error_truncated": _truncate_error(
                last_error_row.error_status if last_error_row else None
            ),
            "recent_errors": [
                {
                    "error_status": _truncate_error(r.error_status),
                    "model_used": r.model_used,
                    "generated_at": r.generated_at,
                }
                for r in recent_errors
            ],
        }

    # Per-recommendation-type last run — window function to get the
    # error_status of the LATEST row per type, not the lexical MAX
    # (ROADMAP success #5; WR-03 fix).
    _latest_subq = select(
        AIRecommendation.recommendation_type,
        AIRecommendation.generated_at,
        AIRecommendation.error_status,
        func.row_number()
        .over(
            partition_by=AIRecommendation.recommendation_type,
            order_by=AIRecommendation.generated_at.desc(),
        )
        .label("rn"),
    ).subquery()
    per_rec_type_rows = db.execute(
        select(
            _latest_subq.c.recommendation_type,
            _latest_subq.c.generated_at,
            _latest_subq.c.error_status,
        ).where(_latest_subq.c.rn == 1)
    ).all()
    per_rec_type = [
        {
            "rec_type": r.recommendation_type,
            "last_run": r.generated_at,
            "last_status": r.error_status,
        }
        for r in per_rec_type_rows
    ]

    return templates.TemplateResponse(
        request=request,
        name="pages/admin_system.html",
        context={
            "user": user,
            "app_version": app_version,
            "db_version": db_version,
            "session_count": session_count,
            "photo_size": _human_size(photo_bytes),
            "backup_size": _human_size(backup_bytes),
            "last_backup": last_backup,
            "last_ai_run": last_ai_run,
            "per_provider": per_provider,
            "per_rec_type": per_rec_type,
        },
    )


# ---------------------------------------------------------------------------
# POST /admin/system/ai-refresh — Run AI refresh now (D-13/D-14)
# ---------------------------------------------------------------------------


@router.post("/system/ai-refresh", response_class=HTMLResponse)
async def run_ai_refresh(
    request: Request,
    user: User = Depends(require_admin),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Trigger AI recommendation refresh for all eligible users.

    Two modes (D-13/D-14):
    - force=false: respect-signature (default) — tagged "admin"
    - force=true: force-all, re-bills every eligible user — tagged "admin_force"

    COST-CONTROL INVARIANT (D-13): Only users returned by _get_eligible_user_ids
    are refreshed. This helper filters to is_active AND >= 3 brew_sessions.
    NEVER re-implement this filter here; omitting the >=3-session clause would
    re-bill ineligible users and break the Phase 8 cost control.

    Pitfall 4: regenerate() is async def — this handler MUST be async def.
    """
    form_data = await request.form()
    force_raw = form_data.get("force", "false")
    force = str(force_raw).lower().strip() in ("true", "1", "on")
    generated_by = "admin_force" if force else "admin"

    # Reuse Phase 8 eligibility filter — returns list[int] of user IDs
    from app.services.scheduler import _get_eligible_user_ids

    eligible_ids = _get_eligible_user_ids(db)

    results = []
    for uid in eligible_ids:
        # Pass sync db from get_session; regenerate brackets its own await
        status = await ai_service.regenerate(uid, generated_by, db=db, force=force)
        results.append({"user_id": uid, "status": status})

    # Tally
    tally: dict[str, int] = {}
    for r in results:
        tally[r["status"]] = tally.get(r["status"], 0) + 1

    # Emit audit event (no secrets — force flag + counts only)
    log.info(
        events.ADMIN_AI_REFRESH_TRIGGERED,
        force=force,
        generated_by=generated_by,
        total=len(eligible_ids),
        tally=tally,
        by_user_id=user.id,
    )

    return templates.TemplateResponse(
        request=request,
        name="fragments/admin_ai_refresh_result.html",
        context={
            "results": results,
            "force": force,
            "tally": tally,
            "total": len(eligible_ids),
        },
    )


# ---------------------------------------------------------------------------
# POST /admin/system/test-connection/{provider} — Auth probe (D-12)
# ---------------------------------------------------------------------------


@router.post("/system/test-connection/{provider}", response_class=HTMLResponse)
def test_connection(
    provider: str,
    request: Request,
    user: User = Depends(require_admin),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Single canonical test-connection probe (D-12 / PATTERNS.md).

    Calls the cheapest auth-only SDK operation (models.list()); writes ZERO
    ai_recommendations rows; decrypted key stays in handler scope only.

    SEC-6 (T-09-31):
    - cred.key is assigned to a local variable inside this handler.
    - It is NEVER added to template context, logged, or returned.
    - del client in finally drops the object holding the key reference.

    Sync def is correct (one sync SDK call; no session writes; threadpool).
    """
    if provider not in _VALID_PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown provider")

    cred = cred_service.get_provider_credential(db, provider)  # type: ignore[arg-type]
    if not cred:
        log.info(events.ADMIN_PROVIDER_TEST, provider=provider, result="not_configured")
        return templates.TemplateResponse(
            request=request,
            name="fragments/admin_test_result.html",
            context={"provider": provider, "status": "error", "reason": "not_configured"},
        )

    # Key stays in local scope — never logged, never in template context (SEC-6)
    result: dict[str, str] = {}
    client = None  # ensure del works in finally even if constructor raises
    try:
        if provider == "anthropic":
            import anthropic

            client = anthropic.Anthropic(api_key=cred.key)
            client.models.list()
        elif provider == "openai":
            import openai

            client = openai.OpenAI(api_key=cred.key)
            client.models.list()
        result = {"status": "ok"}
    except Exception as exc:
        import anthropic as _ant
        import openai as _oai

        if isinstance(
            exc, (_ant.AuthenticationError, _ant.PermissionDeniedError, _oai.AuthenticationError)
        ):
            result = {"status": "error", "reason": "invalid_key"}
        elif isinstance(
            exc,
            (
                _ant.APIConnectionError,
                _ant.APITimeoutError,
                _oai.APIConnectionError,
                _oai.APITimeoutError,
            ),
        ):
            result = {"status": "error", "reason": "network"}
        else:
            result = {"status": "error", "reason": "unknown"}
    finally:
        if client is not None:
            del client  # discard object holding key reference (SEC-6)

    log.info(
        events.ADMIN_PROVIDER_TEST,
        provider=provider,
        result=result.get("status"),
        reason=result.get("reason"),
    )

    return templates.TemplateResponse(
        request=request,
        name="fragments/admin_test_result.html",
        context={"provider": provider, **result},
    )


__all__ = ["admin_system", "router"]
