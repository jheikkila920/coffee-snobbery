"""Admin user management router — ADMIN-01.

Implements list / create / edit / password-reset / toggle-admin /
deactivate / reactivate / hard-delete with the D-15 block-and-deactivate
posture and D-16 last-admin/self-lockout guards.

Safety invariants
-----------------
D-15: Hard-delete is blocked when the target has brew_sessions.
      The application-level count check is the UX layer; the DB RESTRICT
      FK on brew_sessions.user_id is the safety net backstop.

D-16: Demoting, deactivating, or deleting the last active admin is refused.
      Self-lockout (admin targeting their own account for demotion/deactivate)
      is also refused. Both use a SELECT COUNT FOR UPDATE within a transaction
      to guard against last-admin race (RESEARCH Pitfall 7).

T-09-04: Any handler that toggles is_admin or deactivates / hard-deletes
         a user MUST delete that user's session rows to immediately evict
         stale auth cookies. Done via async bulk-delete because sessions.py
         is async-only.

CSRF: Every state-changing POST handler calls ``await request.form()`` and
      strips ``{"X-CSRF-Token"}`` before reading any other fields. This is
      MANDATORY — the CSRFFormFieldShim hoists the hidden field into the
      X-CSRF-Token header; a handler that never awaits request.form() is
      rejected by CSRFMiddleware with 403 before any guard runs.

Handler sync/async: READ handlers are sync def; all state-changing POSTs
are async def (required by CSRF await pattern and session-delete paths).
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import ValidationError
from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import events
from app.dependencies.auth import require_admin
from app.dependencies.db import get_session
from app.models.brew_session import BrewSession
from app.models.session import Session as SessionModel
from app.models.user import User
from app.schemas.admin_user import AdminPasswordReset, AdminUserCreate, AdminUserEdit
from app.services.auth import hash_password
from app.services.form_validation import errors_by_field
from app.templates_setup import templates

router = APIRouter()
log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _count_active_admins(db: Session) -> int:
    """Count active admin users with a FOR UPDATE row lock (Pitfall 7).

    The lock is applied to the inner subquery (on individual User rows), not
    to the outer COUNT — PostgreSQL does not allow FOR UPDATE on aggregates.
    This serializes concurrent admin-demotion transactions at the DB level.
    """
    locked_subq = (
        select(User.id)
        .where(User.is_admin.is_(True), User.is_active.is_(True))
        .with_for_update()
        .subquery()
    )
    return db.execute(select(func.count()).select_from(locked_subq)).scalar_one()


async def _delete_user_sessions(target_id: int) -> None:
    """Delete all session rows for target_id via the async session factory (T-09-04)."""
    from app.main import async_session_factory

    async with async_session_factory() as async_db:
        await async_db.execute(sql_delete(SessionModel).where(SessionModel.user_id == target_id))
        await async_db.commit()


def _render_error_fragment(
    request: Request,
    message: str,
    status_code: int = 200,
) -> Response:
    """Render a minimal error fragment for non-form guard failures."""
    return templates.TemplateResponse(
        request=request,
        name="fragments/admin_error.html",
        context={"error": message},
        status_code=status_code,
    )


# ---------------------------------------------------------------------------
# READ handlers (sync def)
# ---------------------------------------------------------------------------


@router.get("/users", response_class=HTMLResponse)
def list_users(
    request: Request,
    admin_user: User = Depends(require_admin),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """List all users. HTMX swap -> fragment; full GET -> page."""
    rows = db.execute(select(User).order_by(User.username)).scalars().all()
    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request,
            name="fragments/admin_user_list.html",
            context={"users": rows},
        )
    return templates.TemplateResponse(
        request=request,
        name="pages/admin_users.html",
        context={"users": rows},
    )


@router.get("/users/new", response_class=HTMLResponse)
def new_user_form(
    request: Request,
    admin_user: User = Depends(require_admin),  # noqa: B008
) -> Response:
    """Empty create-user form fragment."""
    return templates.TemplateResponse(
        request=request,
        name="fragments/admin_user_form.html",
        context={"values": {}, "errors": {}, "mode": "create"},
    )


@router.get("/users/{target_id}/edit", response_class=HTMLResponse)
def edit_user_form(
    target_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Pre-populated edit form fragment. Password hash is NEVER rendered."""
    target = db.get(User, target_id)
    if target is None:
        raise HTTPException(status_code=404)
    values = {
        "username": target.username,
        "email": target.email or "",
        "is_admin": target.is_admin,
    }
    return templates.TemplateResponse(
        request=request,
        name="fragments/admin_user_form.html",
        context={
            "values": values,
            "errors": {},
            "mode": "edit",
            "target_id": target_id,
        },
    )


# ---------------------------------------------------------------------------
# WRITE handlers (async def — CSRF await mandatory on every handler)
# ---------------------------------------------------------------------------


@router.post("/users", response_class=HTMLResponse)
async def create_user(
    request: Request,
    admin_user: User = Depends(require_admin),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Create a new user. Validation errors -> form re-render at HTTP 200."""
    form_data = await request.form()
    skip = {"X-CSRF-Token"}
    raw = {k: v for k, v in form_data.items() if k not in skip}

    # Coerce empty email to None so EmailStr doesn't reject ""
    if raw.get("email") == "":
        raw["email"] = None
    # Coerce is_admin checkbox: present = True, absent = False
    raw["is_admin"] = raw.get("is_admin") in ("true", "on", "1", True)

    try:
        form = AdminUserCreate(**raw)
    except ValidationError as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/admin_user_form.html",
            context={"values": raw, "errors": errors_by_field(exc), "mode": "create"},
            status_code=200,
        )

    new_user = User(
        username=form.username,
        email=str(form.email) if form.email else None,
        password_hash=hash_password(form.password),
        is_admin=form.is_admin,
        is_active=True,
    )
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(
            request=request,
            name="fragments/admin_user_form.html",
            context={
                "values": raw,
                "errors": {"username": "Username already exists."},
                "mode": "create",
            },
            status_code=200,
        )

    log.info(events.ADMIN_USER_CREATED, user_id=new_user.id, by_user_id=admin_user.id)
    return templates.TemplateResponse(
        request=request,
        name="fragments/admin_user_row.html",
        context={"user": new_user, "include_oob_form_clear": True},
    )


@router.post("/users/{target_id}", response_class=HTMLResponse)
async def update_user(
    target_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Edit save: updates username/email/password/is_admin.

    If is_admin changes, the D-16 guard runs. If a new password is provided
    it is validated against the 12-char floor and hashed.
    """
    target = db.get(User, target_id)
    if target is None:
        raise HTTPException(status_code=404)

    form_data = await request.form()
    skip = {"X-CSRF-Token"}
    raw = {k: v for k, v in form_data.items() if k not in skip}

    # Coerce empty email to None so EmailStr doesn't reject ""
    if raw.get("email") == "":
        raw["email"] = None
    # Coerce is_admin checkbox: present = True, absent = False
    raw["is_admin"] = raw.get("is_admin") in ("true", "on", "1", True)

    # Validate through Pydantic (matches create path — EmailStr, length rules)
    try:
        form = AdminUserEdit(**raw)
    except ValidationError as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/admin_user_form.html",
            context={
                "values": raw,
                "errors": errors_by_field(exc),
                "mode": "edit",
                "target_id": target_id,
            },
            status_code=200,
        )

    new_username = form.username
    new_email = str(form.email) if form.email else None
    new_is_admin_raw = form.is_admin
    new_password = raw.get("password", "").strip()

    # Validate password if provided
    if new_password:
        try:
            AdminPasswordReset(password=new_password)
        except ValidationError as exc:
            return templates.TemplateResponse(
                request=request,
                name="fragments/admin_user_form.html",
                context={
                    "values": raw,
                    "errors": errors_by_field(exc),
                    "mode": "edit",
                    "target_id": target_id,
                },
                status_code=200,
            )

    # D-16 guard if is_admin is being demoted
    if target.is_admin and not new_is_admin_raw:
        # Use transaction for FOR UPDATE count
        admin_count = _count_active_admins(db)
        if admin_count <= 1:
            return _render_error_fragment(request, "Cannot demote the last active admin.", 409)
        if target_id == admin_user.id:
            return _render_error_fragment(request, "Cannot demote yourself.", 409)

    # Self-lockout guard on is_admin demotion
    if target.is_admin and not new_is_admin_raw and target_id == admin_user.id:
        return _render_error_fragment(request, "Cannot demote yourself.", 409)

    # Apply changes
    password_changed = False
    target.username = new_username
    target.email = new_email
    if new_password:
        target.password_hash = hash_password(new_password)
        password_changed = True
    is_admin_changed = target.is_admin != new_is_admin_raw
    target.is_admin = new_is_admin_raw

    try:
        db.commit()
        db.refresh(target)
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(
            request=request,
            name="fragments/admin_user_form.html",
            context={
                "values": raw,
                "errors": {"username": "Username already exists."},
                "mode": "edit",
                "target_id": target_id,
            },
            status_code=200,
        )

    log.info(events.ADMIN_USER_UPDATED, user_id=target.id, by_user_id=admin_user.id)
    if password_changed:
        log.info(events.ADMIN_PASSWORD_RESET, user_id=target.id, by_user_id=admin_user.id)

    # Invalidate sessions on is_admin change OR password reset (T-09-04).
    # A password reset on a compromised account must force re-auth everywhere.
    if is_admin_changed or password_changed:
        await _delete_user_sessions(target_id)
    if is_admin_changed:
        log.info(events.ADMIN_IS_ADMIN_TOGGLED, user_id=target.id, by_user_id=admin_user.id)

    return templates.TemplateResponse(
        request=request,
        name="fragments/admin_user_row.html",
        context={"user": target},
    )


@router.post("/users/{target_id}/toggle-admin", response_class=HTMLResponse)
async def toggle_admin(
    target_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Toggle is_admin on target user with D-16 guard + immediate session eviction."""
    # CSRF FIRST: mandatory await before any guard
    form_data = await request.form()
    _ = {k: v for k, v in form_data.items() if k != "X-CSRF-Token"}

    target = db.get(User, target_id)
    if target is None:
        raise HTTPException(status_code=404)

    # D-16 guard: refuse to demote if it would leave zero active admins
    if target.is_admin:
        admin_count = _count_active_admins(db)
        if admin_count <= 1:
            return _render_error_fragment(request, "Cannot demote the last active admin.", 409)
        if target_id == admin_user.id:
            return _render_error_fragment(request, "Cannot demote yourself.", 409)

    # Flip is_admin
    target.is_admin = not target.is_admin
    db.commit()
    db.refresh(target)

    # Invalidate target's sessions (T-09-04)
    await _delete_user_sessions(target_id)

    log.info(
        events.ADMIN_IS_ADMIN_TOGGLED,
        user_id=target.id,
        new_is_admin=target.is_admin,
        by_user_id=admin_user.id,
    )
    return templates.TemplateResponse(
        request=request,
        name="fragments/admin_user_row.html",
        context={"user": target},
    )


@router.post("/users/{target_id}/deactivate", response_class=HTMLResponse)
async def deactivate_user(
    target_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Deactivate a user. D-16 guards: refuse last-admin or self.
    Session eviction is immediate (T-09-04).
    """
    # CSRF FIRST: mandatory await even though no form fields are read
    form_data = await request.form()
    _ = {k: v for k, v in form_data.items() if k != "X-CSRF-Token"}

    target = db.get(User, target_id)
    if target is None:
        raise HTTPException(status_code=404)

    # D-16 self-lockout guard
    if target_id == admin_user.id:
        return _render_error_fragment(request, "Cannot deactivate yourself.", 409)

    # D-16 last-admin guard
    if target.is_admin:
        admin_count = _count_active_admins(db)
        if admin_count <= 1:
            return _render_error_fragment(request, "Cannot deactivate the last active admin.", 409)

    target.is_active = False
    db.commit()
    db.refresh(target)

    # Invalidate sessions (T-09-04)
    await _delete_user_sessions(target_id)

    log.info(events.ADMIN_USER_DEACTIVATED, user_id=target.id, by_user_id=admin_user.id)
    return templates.TemplateResponse(
        request=request,
        name="fragments/admin_user_row.html",
        context={"user": target},
    )


@router.post("/users/{target_id}/reactivate", response_class=HTMLResponse)
async def reactivate_user(
    target_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Reactivate a previously-deactivated user. No D-16 guard needed."""
    # CSRF FIRST: mandatory await
    form_data = await request.form()
    _ = {k: v for k, v in form_data.items() if k != "X-CSRF-Token"}

    target = db.get(User, target_id)
    if target is None:
        raise HTTPException(status_code=404)

    target.is_active = True
    db.commit()
    db.refresh(target)

    log.info(events.ADMIN_USER_REACTIVATED, user_id=target.id, by_user_id=admin_user.id)
    return templates.TemplateResponse(
        request=request,
        name="fragments/admin_user_row.html",
        context={"user": target},
    )


@router.post("/users/{target_id}/delete", response_class=HTMLResponse)
async def delete_user(
    target_id: int,
    request: Request,
    admin_user: User = Depends(require_admin),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Hard-delete a user. D-15 + D-16 guards + async session eviction."""
    # CSRF FIRST: mandatory await
    form_data = await request.form()
    _ = {k: v for k, v in form_data.items() if k != "X-CSRF-Token"}

    target = db.get(User, target_id)
    if target is None:
        raise HTTPException(status_code=404)

    # D-16 guard: refuse to delete last active admin or self
    if target_id == admin_user.id:
        return _render_error_fragment(request, "Cannot delete yourself.", 409)

    if target.is_admin:
        admin_count = _count_active_admins(db)
        if admin_count <= 1:
            return _render_error_fragment(request, "Cannot delete the last active admin.", 409)

    # D-15 guard: refuse hard-delete if user has brew_sessions (RESTRICT FK)
    brew_count = db.execute(
        select(func.count()).select_from(BrewSession).where(BrewSession.user_id == target_id)
    ).scalar_one()
    if brew_count > 0:
        return _render_error_fragment(
            request,
            "User has brew history — deactivate instead.",
            409,
        )

    # Delete sessions first (belt-and-braces; sessions FK is CASCADE but
    # explicit delete gives cleaner log + ensures eviction before commit)
    await _delete_user_sessions(target_id)

    try:
        db.delete(target)
        db.commit()
    except IntegrityError:
        # RESTRICT FK backstop (belt-and-braces, should not reach here)
        db.rollback()
        return _render_error_fragment(
            request,
            "User has brew history — deactivate instead.",
            409,
        )

    log.info(events.ADMIN_USER_DELETED, user_id=target_id, by_user_id=admin_user.id)
    # Return empty fragment that HTMX swaps outerHTML of the row (removes it)
    return templates.TemplateResponse(
        request=request,
        name="fragments/admin_user_deleted.html",
        context={"target_id": target_id},
    )
