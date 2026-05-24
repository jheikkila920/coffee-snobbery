"""Phase 2 cold-container E2E smoke test.

Asserts the ROADMAP success criterion (amended per D-01/D-03):

    cold container → /setup → auto-login → see / with "Signed in as <username>"
    → /logout → /login

Uses the existing ``client`` fixture (lifespan-aware ``TestClient``) and
the ``fresh_db`` autouse fixture (clean ``users`` + ``setup_completed='false'``
per test). The test reproduces the manual smoke flow a human would walk
after ``docker compose up -d`` on a virgin volume:

1. GET ``/setup``                           → 200 + form rendered
2. POST ``/setup``                          → 303 → ``/`` + ``Set-Cookie: session_id``
3. GET ``/`` (with session cookie)          → 200 + "Signed in as <username>"
4. POST ``/logout``                         → 303 → ``/login`` + clear-cookie
5. GET ``/`` (no session cookie)            → 200 + "Sign in" link

Plan 02-10 wires the CSRFFormFieldShim into ``app.main``; without that the
POST in step 2 would 403 even with a valid form-field token. The shim
hoists the ``X-CSRF-Token`` form field into the request header so
``starlette-csrf`` 3.0's header-only check accepts the token.
"""

from __future__ import annotations

import re

import pytest


def _require_phase02_wired() -> None:
    """Skip cleanly if any Wave 4 / Wave 5 dependency is missing."""
    try:
        from app.csrf import CSRFFormFieldShim  # noqa: F401
        from app.routers.admin import router as admin_router  # noqa: F401
        from app.routers.auth import router as auth_router  # noqa: F401
    except ImportError as exc:
        pytest.skip(f"Wave 4/5 deps not yet present: {exc}")


def test_cold_container_through_login(client) -> None:
    """End-to-end Phase 2 happy path on a virgin DB.

    The ``fresh_db`` autouse fixture wipes ``users`` and resets
    ``app_settings.setup_completed='false'`` before this test runs, so
    GET /setup will render the form (not redirect to /login).
    """
    _require_phase02_wired()

    # ----- Step 1: GET /setup renders the form -----
    r_setup_get = client.get("/setup")
    assert r_setup_get.status_code == 200, (
        f"GET /setup must 200 on a fresh DB; got {r_setup_get.status_code}: "
        f"{r_setup_get.text[:200]}"
    )
    assert "First-time setup" in r_setup_get.text
    token = r_setup_get.cookies.get("csrftoken")
    assert token, "starlette-csrf must set csrftoken cookie on GET /setup response"

    # ----- Step 2: POST /setup with valid form + CSRF pair -----
    # The form field name 'X-CSRF-Token' matches CSRF_HEADER_NAME so the
    # CSRFFormFieldShim hoists it into the request header before
    # CSRFMiddleware runs its header-only check. The header is ALSO sent
    # directly (HTMX-style) so the test exercises the idempotent-shim path
    # too — both paths must accept the request.
    r_setup = client.post(
        "/setup",
        data={
            "X-CSRF-Token": token,
            "username": "smoketest",
            "email": "smoke@example.com",
            "password": "twelve-chars-min-password",
        },
        headers={"X-CSRF-Token": token},
        cookies={"csrftoken": token},
        follow_redirects=False,
    )
    assert r_setup.status_code == 303, (
        f"D-03 auto-login: POST /setup must 303 → /, got "
        f"{r_setup.status_code}: {r_setup.text[:300]}"
    )
    assert r_setup.headers["location"] == "/"
    set_cookie = r_setup.headers.get("set-cookie", "")
    assert "session_id=" in set_cookie, (
        f"auto-login must set session_id cookie; got Set-Cookie: {set_cookie!r}"
    )

    # ----- Step 3: extract the signed cookie value for follow-up -----
    # TestClient could auto-follow redirects + carry cookies, but
    # follow_redirects=False above means we drive the next step manually so
    # the assertions are unambiguous about what each request carries.
    m = re.search(r"session_id=([^;]+)", set_cookie)
    assert m, f"could not extract session_id value: {set_cookie}"
    session_signed = m.group(1)

    # ----- Step 4: GET / with the session cookie renders the authenticated home -----
    # The home route is require_user-gated, so an unauthenticated request redirects
    # to /login. A 200 carrying the analytics home content confirms the session
    # cookie authenticated the user. The placeholder "Signed in as {user}" footer
    # and the inline sign-out link were retired when Phase 6 replaced the index.html
    # placeholder with the analytics home; the persistent nav/identity + sign-out
    # chrome is Phase 11 scope. Logout itself is still exercised directly in Step 5.
    r_home = client.get(
        "/",
        cookies={"session_id": session_signed, "csrftoken": token},
    )
    assert r_home.status_code == 200
    assert "Recent brews" in r_home.text, (
        "authenticated home must render the analytics home (e.g. the always-on "
        f"'Recent brews' section); got body: {r_home.text[:500]}"
    )

    # ----- Step 5: POST /logout -----
    # Refresh CSRF token from the latest response in case rotation kicked in.
    token2 = r_home.cookies.get("csrftoken", token)
    r_logout = client.post(
        "/logout",
        data={"X-CSRF-Token": token2},
        headers={"X-CSRF-Token": token2},
        cookies={"csrftoken": token2, "session_id": session_signed},
        follow_redirects=False,
    )
    assert r_logout.status_code == 303
    assert r_logout.headers["location"] == "/login"

    # ----- Step 6: session cookie cleared -----
    logout_set_cookie = r_logout.headers.get("set-cookie", "")
    assert "session_id=" in logout_set_cookie
    assert "Max-Age=0" in logout_set_cookie or "max-age=0" in logout_set_cookie, (
        f"logout must emit clear-cookie for session_id (Max-Age=0); got: {logout_set_cookie}"
    )

    # ----- Step 7: GET / after logout is rejected by the auth gate -----
    # Don't carry the session_id cookie — it's been cleared client-side too.
    # Phase 6 replaced the public index.html placeholder with the require_user-gated
    # analytics home, consistent with every other full-page route (brew/catalog all
    # 401 for anonymous). A logged-out request to / is therefore rejected rather than
    # rendering a public page with a "Sign in" link. (A friendly /login redirect and
    # the nav chrome are Phase 11 scope.)
    r_anon = client.get("/", cookies={"csrftoken": token2})
    assert r_anon.status_code == 401
    assert "Signed in as" not in r_anon.text
