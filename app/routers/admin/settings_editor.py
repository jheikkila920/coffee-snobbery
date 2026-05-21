"""Admin settings editor router — ADMIN-03.

Renders all ``app_settings`` rows with type-driven input controls (D-05) and
handles per-row inline save via ``set_setting`` (D-06). System-written status
rows are rendered display-only and save attempts are rejected with 403 (D-04).

Value types in the seed (D-05 verified):
  int / float -> number input (float uses step=0.25 or 0.01)
  bool        -> checkbox (submitted as "on" / absent -> "true" / "false")
  string      -> single-line text input
  null        -> read-only display (value is None)

Read-only guard (D-04 + Research A1):
  _READ_ONLY_KEYS — hard-coded set; save handler returns 403 before calling
  set_setting for any key in this set.

Status rows (last_ai_run_status, last_backup_status) read via raw
``select(AppSetting...)`` — NOT via get_str — because set_setting pops the
cache key and the next prewarm has not run yet (RESEARCH.md Pitfall 2).
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import events
from app.dependencies.auth import require_admin
from app.dependencies.db import get_session
from app.models.app_setting import AppSetting
from app.models.user import User
from app.templates_setup import templates

log = structlog.get_logger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# D-04: Read-only keys — must never be writable via this editor.
# system/critical rows; set_setting is NOT called for any of these.
# Research A1: encryption_key_primary_fingerprint added even though D-04 does
# not name it explicitly — it is managed by the encryption service alone.
# ---------------------------------------------------------------------------
_READ_ONLY_KEYS: frozenset[str] = frozenset(
    {
        "last_ai_run_status",
        "last_backup_status",
        "last_backup_at",
        "setup_completed",
        "encryption_key_primary_fingerprint",
    }
)


def _input_kind(value_type: str, key: str) -> str:
    """Map value_type + key to a template input_kind token.

    Returns one of: "number_int", "number_float", "checkbox", "text", "readonly".
    "readonly" covers null and any key in _READ_ONLY_KEYS regardless of type.
    """
    if key in _READ_ONLY_KEYS:
        return "readonly"
    if value_type == "int":
        return "number_int"
    if value_type == "float":
        return "number_float"
    if value_type == "bool":
        return "checkbox"
    if value_type == "string":
        return "text"
    # null + any unknown type -> read-only display
    return "readonly"


def _build_row_context(row: Any) -> dict[str, Any]:
    """Build the per-row template context from a raw AppSetting query result."""
    key = row.key
    editable = key not in _READ_ONLY_KEYS and row.value_type not in ("null",)
    return {
        "key": key,
        "value": row.value,
        "value_type": row.value_type,
        "description": row.description,
        "editable": editable,
        "input_kind": _input_kind(row.value_type, key),
        "saved": False,
        "error": None,
    }


# ---------------------------------------------------------------------------
# GET /admin/settings — list all settings rows
# ---------------------------------------------------------------------------


@router.get("/settings", response_class=HTMLResponse)
def list_settings(
    request: Request,
    user: User = Depends(require_admin),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Render all app_settings rows with type-driven input controls.

    Reads via raw SELECT — NOT get_str — so status rows with a popped cache
    key are still readable (RESEARCH.md Pitfall 2 / T-09-17).
    HTMX fragment vs full page split follows the roasters.py pattern.
    """
    rows = db.execute(
        select(
            AppSetting.key,
            AppSetting.value,
            AppSetting.value_type,
            AppSetting.description,
        ).order_by(AppSetting.key)
    ).all()

    setting_rows = [_build_row_context(r) for r in rows]

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request,
            name="fragments/admin_setting_row.html",
            context={"rows": setting_rows},
        )
    return templates.TemplateResponse(
        request=request,
        name="pages/admin_settings.html",
        context={"settings": setting_rows, "user": user},
    )


# ---------------------------------------------------------------------------
# POST /admin/settings/{key} — per-row inline save
# ---------------------------------------------------------------------------


@router.post("/settings/{key}", response_class=HTMLResponse)
async def save_setting(
    key: str,
    request: Request,
    user: User = Depends(require_admin),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Save an editable setting row.

    D-04 guard fires FIRST: returns 403 for any key in _READ_ONLY_KEYS
    without ever calling set_setting (T-09-15 tamper mitigation).

    Checkbox rows: submitted as "on" when checked or absent when unchecked.
    Mapped to "true" / "false" before passing to set_setting (which reads
    the existing value_type from the DB and coerces accordingly).

    set_setting is the single authoritative coercion + cache invalidation +
    ADMIN_APP_SETTING_CHANGED audit point (D-06 / T-09-16 / T-09-17).
    """
    # D-04 read-only guard — MUST be first, before form read (T-09-15)
    if key in _READ_ONLY_KEYS:
        raise HTTPException(status_code=403, detail="Read-only setting")

    # CSRF: await request.form() is mandatory (CSRFFormFieldShim pattern)
    form_data = await request.form()
    raw = {k: v for k, v in form_data.items() if k != "X-CSRF-Token"}

    # Fetch the existing row to know value_type for checkbox normalisation
    existing = db.execute(
        select(
            AppSetting.key,
            AppSetting.value,
            AppSetting.value_type,
            AppSetting.description,
        ).where(AppSetting.key == key)
    ).one_or_none()

    if existing is None:
        raise HTTPException(status_code=404, detail="Setting not found")

    # Normalise the submitted value before handing to set_setting
    value_type = existing.value_type
    if value_type == "bool":
        # Checkbox: "on" when ticked, absent when unticked
        submitted = raw.get("value", "")
        value_str = "true" if submitted.lower() in ("on", "true", "1") else "false"
    else:
        value_str = raw.get("value", "")

    try:
        from app.services import settings as settings_service

        settings_service.set_setting(db, key, value_str, by_user_id=user.id)
    except Exception as exc:
        # Re-render the row with an inline error (HTTP 200 — HTMX swaps on 2xx)
        row_ctx = _build_row_context(existing)
        row_ctx["error"] = str(exc)
        return templates.TemplateResponse(
            request=request,
            name="fragments/admin_setting_row.html",
            context={"row": row_ctx},
            status_code=200,
        )

    # Re-fetch after save for accurate display value
    updated = db.execute(
        select(
            AppSetting.key,
            AppSetting.value,
            AppSetting.value_type,
            AppSetting.description,
        ).where(AppSetting.key == key)
    ).one_or_none()

    row_ctx = _build_row_context(updated) if updated else _build_row_context(existing)
    row_ctx["saved"] = True

    log.info(events.ADMIN_APP_SETTING_CHANGED, setting_key=key, by_user_id=user.id)

    return templates.TemplateResponse(
        request=request,
        name="fragments/admin_setting_row.html",
        context={"row": row_ctx},
    )
