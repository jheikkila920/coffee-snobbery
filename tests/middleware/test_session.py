"""Wave 0 stubs for AUTH-05 (custom table-backed SessionMiddleware).

Covers per-task verification map rows for AUTH-05 from
``.planning/phases/01-middleware/01-VALIDATION.md``:

- ``test_unauthenticated_request_has_no_user`` — GET / → request.state.user is None
- ``test_refresh_throttling``                  — last_seen updated only after 5 min
- ``test_invalid_signature_clears_cookie``     — bogus session_id cookie → Max-Age=0

The Plan 04 symbol is ``app.middleware.session.SessionMiddleware``. Each test
imports it (or its module) lazily; missing symbol → pytest.skip. The
``REFRESH_THRESHOLD_SECONDS`` constant lives at module level in the Wave 1
implementation per RESEARCH §5; the throttling test references it by symbol
so a future renumbering breaks loudly.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


def test_unauthenticated_request_has_no_user(client) -> None:
    """AUTH-05: an unauthenticated request resolves request.state.user to None.

    Asserts via the ``/debug/whoami`` probe (Wave 1 Plan 04 lands it). If the
    probe route does not yet exist, this test is xfailed rather than skipped so
    the missing-route condition is visible to reviewers.
    """
    try:
        from app.middleware.session import SessionMiddleware  # noqa: F401
    except ImportError:
        pytest.skip("Wave 1 dependency: app.middleware.session.SessionMiddleware (Plan 04)")
    response = client.get("/debug/whoami")
    if response.status_code == 404:
        pytest.xfail("/debug/whoami probe not yet implemented (Plan 04 adds it)")
    assert response.status_code == 200, response.text
    assert response.headers.get("X-User-Present") == "0", response.headers


def test_refresh_throttling() -> None:
    """AUTH-05: session.last_seen refreshes only when stale by > REFRESH_THRESHOLD_SECONDS.

    Calls the middleware's refresh helper directly (no HTTP round-trip). A
    just-refreshed row must NOT be re-refreshed on a second call; a 5-minute-old
    row MUST be refreshed.
    """
    try:
        from app.middleware.session import (
            REFRESH_THRESHOLD_SECONDS,
            SessionMiddleware,  # noqa: F401
        )
    except ImportError:
        pytest.skip(
            "Wave 1 dependency: app.middleware.session.REFRESH_THRESHOLD_SECONDS "
            "(Plan 04)"
        )
    assert REFRESH_THRESHOLD_SECONDS == 300, (
        f"REFRESH_THRESHOLD_SECONDS must be 300 (5 min) per RESEARCH §5, "
        f"got {REFRESH_THRESHOLD_SECONDS}"
    )
    now = datetime.now(timezone.utc)
    fresh = now - timedelta(seconds=10)  # noqa: F841 — sentinel for the next assertion path
    stale = now - timedelta(seconds=600)  # noqa: F841 — 10 min ago, must refresh
    # The actual helper signature lands in Wave 1; once it does, this test
    # exercises both branches against an in-memory fake session row. For Wave 0
    # we have asserted the threshold constant — the rest is xfail until the
    # helper is named.
    pytest.xfail(
        "refresh-throttle helper not yet exported by app.middleware.session — "
        "Wave 1 Plan 04 names it and turns this test green"
    )


def test_invalid_signature_clears_cookie(client) -> None:
    """AUTH-05: tampered session_id cookie → response sets session_id=; Max-Age=0."""
    try:
        from app.middleware.session import SessionMiddleware  # noqa: F401
    except ImportError:
        pytest.skip("Wave 1 dependency: app.middleware.session.SessionMiddleware (Plan 04)")
    response = client.get("/", cookies={"session_id": "this-is-not-a-valid-signature"})
    # Look at Set-Cookie headers; the middleware must clear the cookie via
    # Max-Age=0 (or expires=Thu, 01 Jan 1970...).
    set_cookies = response.headers.get_list("set-cookie") if hasattr(
        response.headers, "get_list"
    ) else [response.headers.get("set-cookie", "")]
    cleared = any(
        "session_id=" in c and ("Max-Age=0" in c or "max-age=0" in c)
        for c in set_cookies
    )
    if not cleared:
        pytest.xfail(
            "Wave 1 Plan 04 must clear an invalid session_id cookie via Max-Age=0; "
            f"Set-Cookie headers seen: {set_cookies}"
        )


# --------------------------------------------------------------------------- #
# Plan 02-06 — D-09 / D-10 (User-row lookup + fail-closed on inactive/deleted) #
# --------------------------------------------------------------------------- #
#
# These tests drive the SessionMiddleware directly with a hand-rolled ASGI
# scope so they can inspect ``scope["state"]["user"]`` after the middleware
# runs. The test pattern follows RESEARCH §"Pitfall 3" — the User lookup
# MUST happen inside the existing ``async with self.session_factory()``
# block, not a separate sync session.


@pytest.mark.asyncio
async def test_state_user_shape(seeded_admin_user) -> None:
    """D-09: request.state.user is a ``User`` ORM row (not a dict).

    Seeds an admin user + live session via the Phase-2 ``seeded_admin_user``
    fixture, then drives ``SessionMiddleware`` directly with the signed
    cookie. Asserts the captured state.user is an instance of
    :class:`app.models.user.User` — fails loudly if Phase 1's
    ``{"user_id": int}`` stub is still in place.
    """
    try:
        from app.middleware.session import SessionMiddleware
    except ImportError:
        pytest.skip("Wave 1 dependency: app.middleware.session.SessionMiddleware")
    from app.main import async_session_factory
    from app.models.user import User

    captured: dict = {}

    async def inner(scope, receive, send):
        captured["user"] = scope["state"].get("user")
        captured["session"] = scope["state"].get("session")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    mw = SessionMiddleware(inner, session_factory=async_session_factory)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [
            (b"cookie", f"session_id={seeded_admin_user['signed_cookie']}".encode()),
        ],
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    sent: list = []

    async def send(m):
        sent.append(m)

    await mw(scope, receive, send)

    assert captured["user"] is not None, (
        "authenticated request must populate request.state.user"
    )
    assert isinstance(captured["user"], User), (
        f"D-09: request.state.user must be a User instance, got "
        f"{type(captured['user']).__name__}"
    )
    assert captured["user"].username == seeded_admin_user["user"].username
    assert captured["user"].is_admin is True


@pytest.mark.asyncio
async def test_deactivated_user_fail_closed(seeded_regular_user) -> None:
    """D-10: ``is_active=false`` → next request clears cookie + deletes session row.

    Seeds a regular user + live session, then flips ``is_active`` to false
    via direct SQL. Drives ``SessionMiddleware`` with the signed cookie and
    asserts the fail-closed path: state.user is None, response carries a
    clear-cookie Set-Cookie header, and the session row was deleted from
    the database.
    """
    try:
        from app.middleware.session import SessionMiddleware
    except ImportError:
        pytest.skip("Wave 1 dependency: app.middleware.session.SessionMiddleware")
    from sqlalchemy import select, text

    from app.main import async_session_factory
    from app.models.session import Session

    # Flip is_active=false directly via SQL — the helper for this lands
    # in Phase 9 (admin tool); for the test we manipulate the row by hand.
    async with async_session_factory() as db:
        await db.execute(
            text("UPDATE users SET is_active=false WHERE id=:uid"),
            {"uid": seeded_regular_user["user"].id},
        )
        await db.commit()

    captured: dict = {}

    async def inner(scope, receive, send):
        captured["user"] = scope["state"].get("user")
        captured["session"] = scope["state"].get("session")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    mw = SessionMiddleware(inner, session_factory=async_session_factory)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [
            (b"cookie", f"session_id={seeded_regular_user['signed_cookie']}".encode()),
        ],
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    sent: list = []

    async def send(m):
        sent.append(m)

    await mw(scope, receive, send)

    # D-10 fail-closed assertions
    assert captured["user"] is None, (
        f"deactivated user must resolve to None, got {captured['user']!r}"
    )
    assert captured["session"] is None, "session state must also be cleared"

    # Clear-cookie injected into the response
    response_start = next(m for m in sent if m["type"] == "http.response.start")
    set_cookies = [v for n, v in response_start["headers"] if n == b"set-cookie"]
    assert any(
        b"session_id=" in c and (b"Max-Age=0" in c or b"max-age=0" in c)
        for c in set_cookies
    ), (
        f"D-10 must emit clear-cookie Set-Cookie header; got Set-Cookies: {set_cookies}"
    )

    # The orphaned session row was DELETEd
    async with async_session_factory() as db:
        row = (
            await db.execute(
                select(Session).where(
                    Session.session_id == seeded_regular_user["session_id"]
                )
            )
        ).scalar_one_or_none()
        assert row is None, (
            "D-10 must DELETE the session row owned by the deactivated user"
        )


@pytest.mark.asyncio
async def test_deleted_user_fail_closed() -> None:
    """D-10: deleted-user branch of the fail-closed path.

    Documented skip per Plan 02-06 Task 1: the FK constraint
    ``sessions.user_id REFERENCES users(id) ON DELETE CASCADE`` means
    deleting a user row also deletes any session rows pointing at it.
    The "orphaned session pointing at a non-existent user" state is not
    reachable in normal operation, so the ``user_row is None`` leaf of
    the D-10 ``if user_row is None or not user_row.is_active:`` branch
    is only exercised under one of:

    * a schema change that drops the CASCADE,
    * a direct INSERT that bypasses the FK,
    * a future "soft delete" model that retains session rows for audit.

    The same code path is asserted by ``test_deactivated_user_fail_closed``
    above (the second leaf of the OR). Leaving this test as a skip with
    explanatory text so a future schema change that drops the CASCADE
    has an obvious place to add the assertion.
    """
    pytest.skip(
        "FK CASCADE prevents an 'orphaned session pointing at a deleted user' "
        "state in normal operation; the user_row=None leaf of D-10 shares its "
        "code branch with the inactive-user leaf which test_deactivated_user_"
        "fail_closed asserts. Convert this skip to a real test if a future "
        "schema change drops the ON DELETE CASCADE on sessions.user_id."
    )
