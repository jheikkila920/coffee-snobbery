"""Phase 2 real auth routes: ``/setup``, ``/login``, ``/logout``.

Replaces the Phase 1 stub bodies (no parallel module). The slowapi
decorators and the ``request: Request`` parameter are preserved verbatim
from the stub — slowapi requires the ``Request`` introspection at
decoration-effective time (analog: ``app/routers/csp_report.py:120-123``).

Locked behaviors (per ``.planning/phases/02-auth/02-CONTEXT.md``):

* **D-01** — ``GET /setup`` and ``POST /setup`` BOTH redirect to ``/login``
  (303) once ``app_settings.setup_completed='true'``.
* **D-03** — On a successful first-admin setup, the handler auto-logs the
  new user in (mints a session, emits ``Set-Cookie``, 303 to ``/``). No
  ``/setup → /login → re-type`` round-trip.
* **D-05** — Classic form POST → 303 (no HTMX on auth surfaces).
* **D-07** — Wrong / unknown credentials → ``200 + re-render`` with the
  generic "Invalid username or password." message (NOT 401). The
  ``username`` field is repopulated as a UX courtesy; the password is
  NOT.
* **D-12** — ``/logout`` is POST-only with CSRF (no GET — defends against
  drive-by ``<img src="/logout">``).
* **D-15** — Form-field CSRF via ``CSRFFormFieldShim`` (wired into
  ``app.main`` by Plan 02-10). The templates carry a hidden
  ``<input name="X-CSRF-Token">``; the shim hoists the value into the
  ``X-CSRF-Token`` header before ``CSRFMiddleware`` runs.

D-15 logging policy (Phase 1 carried)
-------------------------------------
* ``auth.login_succeeded`` → ``{user_id, ip, request_id}``.
* ``auth.login_failed`` ``reason=bad_password`` → ``{user_id, ip,
  request_id, reason}``.
* ``auth.login_failed`` ``reason=user_not_found`` → ``{ip, request_id,
  reason}`` — NO ``user_id``, NO ``attempted_username``.
* ``auth.login_failed`` ``reason=inactive`` → ``{user_id, ip, request_id,
  reason}``.
* ``auth.logout`` → ``{user_id (or None if no session), ip, request_id}``.
* ``admin.user_created`` → ``{user_id, ip, request_id}``.

The matching structlog assertions live in Plan 02-10 Task 4 (capsys
capture); this module emits the lines per the contract.

Race-protection seam (T-02-07-09 + RESEARCH Open Q5)
----------------------------------------------------
``POST /setup`` runs an **explicit ``SELECT value FROM app_settings WHERE
key='setup_completed'``** BEFORE calling ``create_first_admin``. Without
the pre-flight read, a repeat POST after setup is complete would incur
the full ~100 ms argon2 hash cost inside ``create_first_admin`` before
discovering the ``SELECT FOR UPDATE`` returns ``value='true'`` and
bailing out. The pre-flight read makes the repeat-POST path cheap; the
``create_first_admin`` ``SELECT FOR UPDATE`` is still the authoritative
race-protection inside the same transaction.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.db import get_async_session
from app.events import (
    ADMIN_USER_CREATED,
    AUTH_LOGIN_FAILED,
    AUTH_LOGIN_SUCCEEDED,
    AUTH_LOGOUT,
)
from app.models.user import User
from app.rate_limit import LOGIN_LIMIT, SETUP_LIMIT, limiter
from app.schemas.auth import LoginForm, SetupForm
from app.services.auth import dummy_verify, verify_password
from app.services.sessions import (
    build_session_clear_cookie,
    build_session_cookie,
    delete_session,
    regenerate_session,
)
from app.services.setup import create_first_admin
from app.signing import sign_session_id
from app.templates_setup import templates

log = structlog.get_logger()
router = APIRouter()


# --------------------------------------------------------------------------- #
# Internal helpers — IP + request_id extraction (kept private to this module) #
# --------------------------------------------------------------------------- #


def _ip(request: Request) -> str:
    """Best-effort client IP for D-15 log lines.

    Returns the literal string ``"unknown"`` when ``request.client`` is
    ``None`` (e.g., unit tests that synthesize a Request without a
    transport). uvicorn's ``--proxy-headers`` rewrites ``client.host``
    from ``X-Forwarded-For`` before this middleware runs in production.
    """
    return request.client.host if request.client else "unknown"


def _rid(request: Request) -> str:
    """Read the per-request UUID stashed by ``RequestContextMiddleware``."""
    return getattr(request.state, "request_id", "unknown")


# --------------------------------------------------------------------------- #
# /setup — first-admin create flow (AUTH-01 / AUTH-02 / D-01 / D-03)          #
# --------------------------------------------------------------------------- #


@router.get("/setup", response_class=HTMLResponse)
async def setup_form(
    request: Request,
    db: AsyncSession = Depends(get_async_session),  # noqa: B008 — FastAPI canonical Form 1; Depends() in arg default is the framework idiom.
) -> Response:
    """Render the first-admin setup form.

    D-01: when ``setup_completed='true'``, GET /setup redirects to
    /login (303). Otherwise renders ``pages/setup.html`` with no error.
    """
    row = await db.execute(text("SELECT value FROM app_settings WHERE key = 'setup_completed'"))
    if row.scalar() == "true":
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="pages/setup.html",
        context={"error": None},
    )


@router.post("/setup", response_class=HTMLResponse)
@limiter.limit(SETUP_LIMIT)
async def setup_submit(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_async_session),  # noqa: B008 — FastAPI canonical Form 1; Depends() in arg default is the framework idiom.
) -> Response:
    """First-admin POST. Guard → validate → ``create_first_admin`` → auto-login.

    Flow:

    1. **Explicit pre-flight guard** (RESEARCH Open Q5 + T-02-07-09):
       ``SELECT value FROM app_settings WHERE key='setup_completed'``.
       If ``'true'``, redirect to /login (303) BEFORE any argon2 cost.
    2. Validate the form shape via :class:`SetupForm`. On
       ``ValidationError``, re-render the form with a generic "Please
       check the form values." error (NOT the field-level Pydantic
       message — that would let an attacker enumerate the constraint
       set).
    3. Call :func:`create_first_admin` (AsyncSession + race-protected
       ``SELECT FOR UPDATE`` inside the service). Returns ``None`` on a
       lost race — in that case redirect to /login (303).
    4. On success: emit ``admin.user_created``, mint a fresh session via
       :func:`regenerate_session`, emit ``auth.login_succeeded``, and
       return a 303 to ``/`` with the signed session cookie attached
       (D-03 auto-login).
    """
    # Guard 1: setup already complete → 303 → /login, no argon2 cost.
    row = await db.execute(text("SELECT value FROM app_settings WHERE key = 'setup_completed'"))
    if row.scalar() == "true":
        return RedirectResponse(url="/login", status_code=303)

    # Guard 2: shape validation. Generic error per D-07 spirit (no
    # field-level enumeration).
    try:
        form = SetupForm(username=username, email=email, password=password)
    except ValidationError:
        return templates.TemplateResponse(
            request=request,
            name="pages/setup.html",
            context={"error": "Please check the form values."},
            status_code=200,
        )

    new_user = await create_first_admin(
        db,
        username=form.username,
        email=form.email,
        plaintext_password=form.password,
    )
    if new_user is None:
        # AUTH-02: lost the FOR UPDATE race; the winner already minted
        # the first admin and flipped setup_completed='true'. The
        # /login page handles the next step.
        return RedirectResponse(url="/login", status_code=303)

    log.info(
        ADMIN_USER_CREATED,
        user_id=new_user.id,
        ip=_ip(request),
        request_id=_rid(request),
    )

    # D-03 auto-login. No prior session_id (the visitor is by definition
    # unauthenticated until this moment), so pass ``None`` to
    # regenerate_session — it skips the DELETE and runs only the INSERT.
    new_session_id = await regenerate_session(db, None, new_user.id)
    log.info(
        AUTH_LOGIN_SUCCEEDED,
        user_id=new_user.id,
        ip=_ip(request),
        request_id=_rid(request),
    )
    response = RedirectResponse(url="/", status_code=303)
    response.headers.append("Set-Cookie", build_session_cookie(sign_session_id(new_session_id)))
    return response


# --------------------------------------------------------------------------- #
# /login — argon2 verify + session regenerate (AUTH-03 / AUTH-06 / AUTH-07)   #
# --------------------------------------------------------------------------- #


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request) -> Response:
    """Render the sign-in form with empty error + empty username."""
    return templates.TemplateResponse(
        request=request,
        name="pages/login.html",
        context={"error": None, "username": ""},
    )


@router.post("/login", response_class=HTMLResponse)
@limiter.limit(LOGIN_LIMIT)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_async_session),  # noqa: B008 — FastAPI canonical Form 1; Depends() in arg default is the framework idiom.
) -> Response:
    """Argon2-verify a login attempt; mint a new session on success.

    D-07: every failure leg returns ``200 + re-render`` with the generic
    "Invalid username or password." message. The username field is
    repopulated; the password field is NOT.

    D-15 logging contract: see the module docstring. The
    ``user_not_found`` branch deliberately does NOT carry ``user_id`` or
    ``attempted_username`` — anything more leaks the matched-user signal
    or the typed username into a structured log line where the user
    didn't consent to it.

    T-02-07-01 / ASVS V2.2.5 — the ``user is None`` branch calls
    :func:`dummy_verify` BEFORE rendering so the wall-clock cost matches
    the wrong-password branch (~100 ms argon2 verify).
    """
    # Loose shape validation — a bad-shape username is treated as wrong
    # credentials (no enumeration via 422 / field-level error).
    try:
        form = LoginForm(username=username, password=password)
    except ValidationError:
        # Symmetric cost even on shape failure so an attacker can't
        # distinguish "bad shape" from "valid shape, wrong creds" by
        # wall-clock timing.
        dummy_verify(password)
        log.info(
            AUTH_LOGIN_FAILED,
            ip=_ip(request),
            request_id=_rid(request),
            reason="user_not_found",
        )
        return templates.TemplateResponse(
            request=request,
            name="pages/login.html",
            context={
                "error": "Invalid username or password.",
                "username": username,
            },
            status_code=200,
        )

    result = await db.execute(select(User).where(User.username == form.username))
    user = result.scalar_one_or_none()

    if user is None:
        # D-15: user_not_found — symmetric argon2 cost, NO user_id, NO
        # attempted_username in the log.
        dummy_verify(form.password)
        log.info(
            AUTH_LOGIN_FAILED,
            ip=_ip(request),
            request_id=_rid(request),
            reason="user_not_found",
        )
        return templates.TemplateResponse(
            request=request,
            name="pages/login.html",
            context={
                "error": "Invalid username or password.",
                "username": form.username,
            },
            status_code=200,
        )

    if not user.is_active:
        # Deactivated user — same generic re-render; symmetric cost +
        # user_id logged (D-15) for the audit trail.
        dummy_verify(form.password)
        log.info(
            AUTH_LOGIN_FAILED,
            ip=_ip(request),
            request_id=_rid(request),
            user_id=user.id,
            reason="inactive",
        )
        return templates.TemplateResponse(
            request=request,
            name="pages/login.html",
            context={
                "error": "Invalid username or password.",
                "username": form.username,
            },
            status_code=200,
        )

    if not verify_password(user.password_hash, form.password):
        log.info(
            AUTH_LOGIN_FAILED,
            ip=_ip(request),
            request_id=_rid(request),
            user_id=user.id,
            reason="bad_password",
        )
        return templates.TemplateResponse(
            request=request,
            name="pages/login.html",
            context={
                "error": "Invalid username or password.",
                "username": form.username,
            },
            status_code=200,
        )

    # Happy path. Regenerate the session (AUTH-07 fixation defense): if a
    # prior session_id is attached to the request (from SessionMiddleware),
    # DELETE its row and mint a fresh UUID in the same transaction.
    prior_session = getattr(request.state, "session", None)
    prior_session_id = prior_session.session_id if prior_session else None
    new_session_id = await regenerate_session(db, prior_session_id, user.id)
    log.info(
        AUTH_LOGIN_SUCCEEDED,
        user_id=user.id,
        ip=_ip(request),
        request_id=_rid(request),
    )
    response = RedirectResponse(url="/", status_code=303)
    response.headers.append("Set-Cookie", build_session_cookie(sign_session_id(new_session_id)))
    return response


# --------------------------------------------------------------------------- #
# /logout — POST-only with CSRF; clear cookie + DELETE row (D-12)             #
# --------------------------------------------------------------------------- #


@router.post("/logout")
async def logout_submit(
    request: Request,
    db: AsyncSession = Depends(get_async_session),  # noqa: B008 — FastAPI canonical Form 1; Depends() in arg default is the framework idiom.
) -> Response:
    """Server-side session-row delete + clear-cookie response.

    D-12: POST-only (no GET) so that a drive-by ``<img src="/logout">``
    in a malicious page cannot log a victim out — only the
    CSRF-protected form post on this app's own pages can. CSRF is
    enforced by the middleware stack (``CSRFMiddleware`` + the
    ``CSRFFormFieldShim`` wired by Plan 02-10).

    The log line carries ``user_id=None`` when no session was attached
    (e.g., an already-logged-out user clicking sign-out in a stale tab —
    the response still succeeds; idempotency is the right shape for
    sign-out).
    """
    session = getattr(request.state, "session", None)
    user_id = session.user_id if session else None
    if session is not None:
        await delete_session(db, session.session_id)
    log.info(
        AUTH_LOGOUT,
        user_id=user_id,
        ip=_ip(request),
        request_id=_rid(request),
    )
    response = RedirectResponse(url="/login", status_code=303)
    response.headers.append("Set-Cookie", build_session_clear_cookie())
    return response


__all__ = ["router"]
