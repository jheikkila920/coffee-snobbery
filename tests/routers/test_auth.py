"""Phase 2 auth-router integration tests (Plan 02-07).

Replaces ``tests/routers/test_auth_stub.py`` (Wave 0 Phase-1 stub). The
file is deleted in the same commit that lands this one.

Covers VALIDATION map rows for AUTH-01 / AUTH-02 / AUTH-03 / AUTH-06 /
AUTH-07 plus D-07 (generic-error 200 re-render) and D-12 (POST-only
``/logout`` with CSRF).

CSRF enforcement pattern (post Plan 02-10)
------------------------------------------
CSRF-gated negative tests (``test_login_csrf_blocked``,
``test_logout_csrf_blocked``) send a placeholder ``session_id`` cookie to
trigger ``CSRFMiddleware``'s ``sensitive_cookies={"session_id"}`` gate. The
middleware then verifies the double-submit pair (cookie value vs header /
form-field value); both are absent → 403. Plan 02-10 wires the
``CSRFFormFieldShim`` so the form-field path is reachable; these negative
tests prove the gate still fires when neither path is taken.

``_csrf_pair`` helper
---------------------
Primes the ``csrftoken`` cookie via a safe GET and returns
``(token, headers, cookies)`` so the calling test can drive a CSRF-valid
POST. Skips if the cookie is not minted (Wave 0 middleware-stack regression
safety; same pattern as ``tests/middleware/test_csrf.py:_csrf_pair``).
"""

from __future__ import annotations

import asyncio

import pytest

# --------------------------------------------------------------------------- #
# Common helpers                                                              #
# --------------------------------------------------------------------------- #


def _require_auth_router() -> None:
    """Skip the calling test if Plan 02-07's ``app.routers.auth`` is absent."""
    try:
        from app.routers.auth import router  # noqa: F401
    except ImportError:
        pytest.skip("Wave 4 dep: app.routers.auth (Plan 02-07)")


def _csrf_pair(client) -> tuple[str, dict[str, str], dict[str, str]]:
    """Return ``(token, headers, cookies)`` for a CSRF-valid POST.

    Skips if ``csrftoken`` cookie is not minted by middleware. Mirrors the
    helper in ``tests/middleware/test_csrf.py`` so the contract stays
    consistent across the suite.
    """
    primer = client.get("/")
    token = primer.cookies.get("csrftoken")
    if not token:
        pytest.skip("CSRF cookie 'csrftoken' not yet set by middleware (Plan 02-10 wiring)")
    return token, {"X-CSRF-Token": token}, {"csrftoken": token}


# --------------------------------------------------------------------------- #
# AUTH-01 — /setup happy path + post-completion redirect                      #
# --------------------------------------------------------------------------- #


def test_setup_happy_path(client) -> None:
    """AUTH-01: clean DB → GET /setup renders form; POST /setup → 303 to / + session cookie."""
    _require_auth_router()
    # GET renders the form (200 + recognizable text in body)
    r = client.get("/setup")
    assert r.status_code == 200, f"GET /setup expected 200, got {r.status_code}"
    assert "First-time setup" in r.text or "<input" in r.text

    # POST with valid form + CSRF pair → 303 to /
    token, headers, cookies = _csrf_pair(client)
    r2 = client.post(
        "/setup",
        data={
            "X-CSRF-Token": token,
            "username": "admin",
            "email": "admin@example.com",
            "password": "twelve-chars-min-password",
        },
        headers=headers,
        cookies=cookies,
        follow_redirects=False,
    )
    assert r2.status_code == 303, f"expected 303 to /, got {r2.status_code}: {r2.text[:200]}"
    assert r2.headers["location"] == "/"
    set_cookie = r2.headers.get("set-cookie", "")
    assert "session_id=" in set_cookie, (
        f"expected session_id Set-Cookie on auto-login, got: {set_cookie}"
    )


def test_setup_blocked_after_completion(client) -> None:
    """AUTH-01: when setup_completed='true', GET + POST /setup redirect to /login."""
    _require_auth_router()
    # Flip the flag via the engine (fresh_db autouse resets to 'false' before this test).
    from sqlalchemy import text

    from app.db import engine

    with engine.begin() as conn:
        conn.execute(text("UPDATE app_settings SET value='true' WHERE key='setup_completed'"))

    # GET /setup → 303 to /login
    r = client.get("/setup", follow_redirects=False)
    assert r.status_code == 303, f"GET /setup post-completion: expected 303, got {r.status_code}"
    assert r.headers["location"] == "/login"

    # POST /setup → 303 to /login (no argon2 cost incurred per RESEARCH Open Q5)
    token, headers, cookies = _csrf_pair(client)
    r2 = client.post(
        "/setup",
        data={
            "X-CSRF-Token": token,
            "username": "secondadmin",
            "email": "second@example.com",
            "password": "twelve-chars-min-password",
        },
        headers=headers,
        cookies=cookies,
        follow_redirects=False,
    )
    assert r2.status_code == 303, (
        f"POST /setup post-completion: expected 303, got {r2.status_code}: {r2.text[:200]}"
    )
    assert r2.headers["location"] == "/login"


# --------------------------------------------------------------------------- #
# AUTH-02 — concurrent /setup race                                            #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_setup_concurrent_race(async_client) -> None:
    """AUTH-02: two concurrent POST /setups → exactly one 303→/ + one 303→/login."""
    _require_auth_router()

    # Prime the CSRF cookie via an async GET. httpx.AsyncClient stores cookies
    # in its own jar; explicit pass-through into both posts isolates the
    # contract.
    primer = await async_client.get("/setup")
    token = primer.cookies.get("csrftoken")
    if not token:
        pytest.skip("CSRF cookie not primed by GET /setup")
    headers = {"X-CSRF-Token": token}
    cookies = {"csrftoken": token}
    body = {
        "X-CSRF-Token": token,
        "username": "racer",
        "email": "r@example.com",
        "password": "twelve-chars-min-password",
    }

    r1, r2 = await asyncio.gather(
        async_client.post(
            "/setup", data=body, headers=headers, cookies=cookies, follow_redirects=False
        ),
        async_client.post(
            "/setup", data=body, headers=headers, cookies=cookies, follow_redirects=False
        ),
    )

    # One winner (303→/), one loser (303→/login). Both 303 in HTTP —
    # distinguish by Location.
    locations = sorted([r1.headers.get("location", ""), r2.headers.get("location", "")])
    assert locations == ["/", "/login"], (
        f"AUTH-02: expected one 303→/ + one 303→/login, got locations={locations}"
    )

    # Exactly one user row in the DB.
    from sqlalchemy import select

    from app.main import async_session_factory
    from app.models.user import User

    async with async_session_factory() as db:
        users = (await db.execute(select(User))).scalars().all()
        assert len(users) == 1, f"AUTH-02: exactly one user row expected, got {len(users)}"


# --------------------------------------------------------------------------- #
# AUTH-03 — /login + no /register                                             #
# --------------------------------------------------------------------------- #


def test_no_register_route(client) -> None:
    """AUTH-03: /register MUST NOT exist (no public registration)."""
    # No router-import gate — the absence is the assertion.
    r1 = client.get("/register")
    r2 = client.post("/register", data={})
    assert r1.status_code == 404, f"GET /register must 404, got {r1.status_code}"
    assert r2.status_code in (404, 405), f"POST /register must 404 or 405, got {r2.status_code}"


def test_login_happy_path(client, seeded_regular_user) -> None:
    """AUTH-03: valid creds → 303 to / + session_id Set-Cookie."""
    _require_auth_router()
    token, headers, cookies = _csrf_pair(client)
    r = client.post(
        "/login",
        data={
            "X-CSRF-Token": token,
            "username": seeded_regular_user["user"].username,
            "password": "twelve-chars-min-password",
        },
        headers=headers,
        cookies=cookies,
        follow_redirects=False,
    )
    assert r.status_code == 303, (
        f"happy-path /login expected 303, got {r.status_code}: {r.text[:200]}"
    )
    assert r.headers["location"] == "/"
    assert "session_id=" in r.headers.get("set-cookie", "")


def test_login_wrong_password(client, seeded_regular_user) -> None:
    """AUTH-03 + D-07: wrong password → 200 + generic re-render."""
    _require_auth_router()
    token, headers, cookies = _csrf_pair(client)
    r = client.post(
        "/login",
        data={
            "X-CSRF-Token": token,
            "username": seeded_regular_user["user"].username,
            "password": "WRONG-password-here",
        },
        headers=headers,
        cookies=cookies,
        follow_redirects=False,
    )
    assert r.status_code == 200, (
        f"D-07: wrong password returns 200 + re-render, got {r.status_code}"
    )
    assert "Invalid username or password." in r.text


# --------------------------------------------------------------------------- #
# AUTH-06 — session cookie attributes                                         #
# --------------------------------------------------------------------------- #


def test_session_cookie_attributes(client, seeded_regular_user) -> None:
    """AUTH-06: Set-Cookie carries HttpOnly + Secure + SameSite=Lax + Max-Age + Path."""
    _require_auth_router()
    token, headers, cookies = _csrf_pair(client)
    r = client.post(
        "/login",
        data={
            "X-CSRF-Token": token,
            "username": seeded_regular_user["user"].username,
            "password": "twelve-chars-min-password",
        },
        headers=headers,
        cookies=cookies,
        follow_redirects=False,
    )
    # A login response may emit multiple Set-Cookie headers (e.g., csrftoken
    # rotation + session_id mint). Walk all of them to find the session.
    if hasattr(r.headers, "get_list"):
        set_cookies = r.headers.get_list("set-cookie")
    else:  # pragma: no cover — older httpx fallback
        raw = r.headers.get("set-cookie", "")
        set_cookies = [raw] if raw else []
    session_cookie = next((c for c in set_cookies if c.startswith("session_id=")), "")
    assert session_cookie, (
        f"AUTH-06: no session_id Set-Cookie on login response; got: {set_cookies!r}"
    )
    assert "HttpOnly" in session_cookie, f"missing HttpOnly: {session_cookie}"
    assert "Secure" in session_cookie, f"missing Secure: {session_cookie}"
    assert "SameSite=Lax" in session_cookie, f"missing SameSite=Lax: {session_cookie}"
    assert "Max-Age=2592000" in session_cookie, f"missing Max-Age=2592000: {session_cookie}"
    assert "Path=/" in session_cookie, f"missing Path=/: {session_cookie}"


# --------------------------------------------------------------------------- #
# AUTH-07 — session fixation defense                                          #
# --------------------------------------------------------------------------- #


def test_session_fixation_defense(client, seeded_regular_user) -> None:
    """AUTH-07: login regenerates session_id; old row DELETEd; cookie value changes."""
    _require_auth_router()
    old_sid = seeded_regular_user["session_id"]
    old_signed = seeded_regular_user["signed_cookie"]
    token, headers, cookies = _csrf_pair(client)
    cookies["session_id"] = old_signed
    r = client.post(
        "/login",
        data={
            "X-CSRF-Token": token,
            "username": seeded_regular_user["user"].username,
            "password": "twelve-chars-min-password",
        },
        headers=headers,
        cookies=cookies,
        follow_redirects=False,
    )
    assert r.status_code == 303, f"login expected 303, got {r.status_code}"
    if hasattr(r.headers, "get_list"):
        set_cookies = r.headers.get_list("set-cookie")
    else:  # pragma: no cover
        raw = r.headers.get("set-cookie", "")
        set_cookies = [raw] if raw else []
    new_session_set_cookie = next((c for c in set_cookies if c.startswith("session_id=")), "")
    assert new_session_set_cookie, (
        f"AUTH-07: no session_id Set-Cookie on response; got: {set_cookies!r}"
    )
    # New session_id value differs from the pre-set one
    assert old_signed not in new_session_set_cookie, (
        "AUTH-07: new session cookie must differ from pre-set"
    )

    # Old session row no longer exists in DB
    from sqlalchemy import select

    from app.main import async_session_factory
    from app.models.session import Session

    async def _check():
        async with async_session_factory() as db:
            return (
                await db.execute(select(Session).where(Session.session_id == old_sid))
            ).scalar_one_or_none()

    assert asyncio.run(_check()) is None, "AUTH-07: old session row must be DELETEd on regeneration"


def test_preset_cookie_does_not_inherit(client, seeded_regular_user) -> None:
    """AUTH-07: an attacker-pre-set session_id cookie value MUST NOT carry over.

    Forge a syntactically-valid (signed-but-revoked) cookie before login; the
    response's new session cookie value MUST differ from the pre-set value.
    """
    _require_auth_router()
    # Use the seeded user's existing signed cookie as the "pre-set" value —
    # any signed-but-revoked value would do; using the seeded one keeps the
    # fixture small.
    preset_signed = seeded_regular_user["signed_cookie"]
    token, headers, cookies = _csrf_pair(client)
    cookies["session_id"] = preset_signed

    r = client.post(
        "/login",
        data={
            "X-CSRF-Token": token,
            "username": seeded_regular_user["user"].username,
            "password": "twelve-chars-min-password",
        },
        headers=headers,
        cookies=cookies,
        follow_redirects=False,
    )
    assert r.status_code == 303
    if hasattr(r.headers, "get_list"):
        set_cookies = r.headers.get_list("set-cookie")
    else:  # pragma: no cover
        raw = r.headers.get("set-cookie", "")
        set_cookies = [raw] if raw else []
    new_session_set_cookie = next((c for c in set_cookies if c.startswith("session_id=")), "")
    assert new_session_set_cookie, "no session_id Set-Cookie on response"
    # The attacker's preset value must not be the new session value.
    assert f"session_id={preset_signed}" not in new_session_set_cookie, (
        "AUTH-07: attacker pre-set session cookie value MUST NOT carry forward"
    )


def test_logout_clears_session(client, seeded_regular_user) -> None:
    """AUTH-07 + D-12: POST /logout DELETEs session row + clears cookie + 303 to /login."""
    _require_auth_router()
    sid = seeded_regular_user["session_id"]
    signed = seeded_regular_user["signed_cookie"]
    token, headers, cookies = _csrf_pair(client)
    cookies["session_id"] = signed
    r = client.post(
        "/logout",
        data={"X-CSRF-Token": token},
        headers=headers,
        cookies=cookies,
        follow_redirects=False,
    )
    assert r.status_code == 303, f"logout expected 303, got {r.status_code}"
    assert r.headers["location"] == "/login"

    if hasattr(r.headers, "get_list"):
        set_cookies = r.headers.get_list("set-cookie")
    else:  # pragma: no cover
        raw = r.headers.get("set-cookie", "")
        set_cookies = [raw] if raw else []
    clear_cookie = next((c for c in set_cookies if c.startswith("session_id=")), "")
    assert clear_cookie, f"logout missing session_id Set-Cookie; got: {set_cookies!r}"
    assert "Max-Age=0" in clear_cookie or "max-age=0" in clear_cookie, (
        f"logout cookie must carry Max-Age=0: {clear_cookie}"
    )

    # DB row deleted
    from sqlalchemy import select

    from app.main import async_session_factory
    from app.models.session import Session

    async def _check():
        async with async_session_factory() as db:
            return (
                await db.execute(select(Session).where(Session.session_id == sid))
            ).scalar_one_or_none()

    assert asyncio.run(_check()) is None, "session row must be DELETEd on logout"


# --------------------------------------------------------------------------- #
# CSRF — /login + /logout blocked without a token                             #
# --------------------------------------------------------------------------- #


def test_login_csrf_blocked(client) -> None:
    """CSRF: POST /login without token → 403.

    CSRFMiddleware (starlette-csrf 3.0) only enforces when a sensitive cookie
    (``session_id``) is present — that is the double-submit-cookie pattern's
    contract (see ``app/csrf.py:CSRF_SENSITIVE_COOKIES``). The test sends a
    placeholder ``session_id`` cookie to trigger enforcement, then omits both
    the header AND the form-field token so the shim has nothing to hoist.
    Plan 02-10 wires the shim into ``app.main``; this test asserts that even
    with the shim mounted, a CSRF-less POST is rejected with 403.
    """
    _require_auth_router()
    r = client.post(
        "/login",
        data={"username": "x", "password": "y"},
        cookies={"session_id": "placeholder-not-validated-csrf-fires-first"},
    )
    assert r.status_code == 403


def test_logout_csrf_blocked(client) -> None:
    """CSRF + D-12: POST /logout without token → 403.

    Sends a placeholder ``session_id`` cookie to trigger CSRFMiddleware's
    sensitive-cookie gate (see ``test_login_csrf_blocked`` rationale).
    The CSRF check fires before the route handler — the placeholder cookie
    value is never validated by SessionMiddleware because the 403 short-
    circuits the chain.
    """
    _require_auth_router()
    r = client.post(
        "/logout",
        data={},
        cookies={"session_id": "placeholder-not-validated-csrf-fires-first"},
    )
    assert r.status_code == 403
