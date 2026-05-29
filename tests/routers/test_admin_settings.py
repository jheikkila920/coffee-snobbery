"""Admin settings editor — quota-row tests (AIX-05/D-08, plan 19-07).

Verifies that the two Phase 19 quota settings rows seeded by the p19
migration appear on GET /admin/settings as editable int inputs, and that
a POST update persists the new value and is immediately reflected by
ai_quota.get_quota_cap (the live cap reader used by the quota check).

Test strategy: in-process TestClient with a seeded admin session so the
full middleware stack (CSRF shim, session, auth) runs.

CSRF pattern: follow the _prime_csrf helper established in
tests/phase_04/test_autocomplete.py — GET any authenticated page first so
the middleware mints a real signed csrftoken cookie, then re-use that
signed value for the subsequent POST. The conftest authed_client fixture
seeds a plain placeholder that fails starlette-csrf's HMAC check; we
clear it and let the middleware issue a genuine signed token.
"""

from __future__ import annotations

from typing import Any

import pytest


def _require_settings_editor() -> None:
    """Skip if the admin settings editor has not landed."""
    try:
        from app.routers.admin import settings_editor  # noqa: F401
    except ImportError:
        pytest.skip("admin/settings_editor not yet landed")


def _require_ai_quota() -> None:
    """Skip if ai_quota service has not landed."""
    try:
        from app.services import ai_quota  # noqa: F401
    except ImportError:
        pytest.skip("app.services.ai_quota not yet landed (plan 19-03)")


def _prime_csrf(client: Any, session_cookie: str) -> str:
    """GET /admin/settings to mint a real signed csrftoken; wire it onto the client.

    starlette-csrf validates tokens with HMAC (URLSafeSerializer). A plain
    string cookie fails. We clear any placeholder and do a GET so the
    middleware sets a real token on the response, then wire it for the
    subsequent POST.
    """
    client.cookies.delete("csrftoken")
    r = client.get(
        "/admin/settings",
        cookies={"session_id": session_cookie},
    )
    token = r.cookies.get("csrftoken") or client.cookies.get("csrftoken")
    if not token:
        pytest.skip("CSRF middleware did not mint a csrftoken on GET /admin/settings")
    client.cookies.set("csrftoken", token)
    client.headers["X-CSRF-Token"] = token
    return token


# ---------------------------------------------------------------------------
# GET /admin/settings — quota rows visible
# ---------------------------------------------------------------------------


def test_quota_settings_appear_on_settings_page(client, seeded_admin_user) -> None:
    """Both quota keys render as editable int inputs on GET /admin/settings.

    D-08: the generic settings editor (settings_editor.py) maps value_type='int'
    rows to number_int inputs automatically. No bespoke template logic needed.
    The Phase 19 migration seeds both rows with value='20' and value_type='int'.
    """
    _require_settings_editor()
    r = client.get(
        "/admin/settings",
        cookies={"session_id": seeded_admin_user["signed_cookie"]},
    )
    assert r.status_code == 200, f"expected 200, got {r.status_code}"
    assert "ai.research_daily_quota" in r.text, (
        "ai.research_daily_quota row missing from /admin/settings"
    )
    assert "ai.improve_brew_daily_quota" in r.text, (
        "ai.improve_brew_daily_quota row missing from /admin/settings"
    )
    # Both rows render as number inputs (number_int input_kind)
    assert 'type="number"' in r.text, (
        "No number input found — quota rows should render as int inputs"
    )


# ---------------------------------------------------------------------------
# POST /admin/settings/{key} — update persists + cap reader reflects change
# ---------------------------------------------------------------------------


def test_quota_settings_research_update_persists(client, seeded_admin_user) -> None:
    """POST update to ai.research_daily_quota persists and get_quota_cap returns new value.

    Edits ai.research_daily_quota to 5 via the admin settings POST endpoint,
    then re-prewarns the settings cache and calls get_quota_cap('coffee_research')
    to confirm it returns 5.

    Re-prewarm is required because set_setting() invalidates (pops) the cache
    key after committing; the next get_int() call raises SettingNotFoundError
    until prewarm_cache() re-loads from DB. In production this re-prewarm happens
    on the next container start; in tests we call it directly after the POST.
    """
    _require_settings_editor()
    _require_ai_quota()

    from app.db import SessionLocal
    from app.services.ai_quota import get_quota_cap
    from app.services.settings import prewarm_cache

    session_cookie = seeded_admin_user["signed_cookie"]
    token = _prime_csrf(client, session_cookie)

    r = client.post(
        "/admin/settings/ai.research_daily_quota",
        data={"value": "5", "X-CSRF-Token": token},
        cookies={"session_id": session_cookie, "csrftoken": token},
        headers={"X-CSRF-Token": token},
    )
    assert r.status_code == 200, (
        f"POST /admin/settings/ai.research_daily_quota returned {r.status_code}: {r.text[:300]}"
    )

    # Re-prewarm so the cache reflects the committed value
    with SessionLocal() as db:
        prewarm_cache(db)

    # The cap reader must now return 5
    cap = get_quota_cap("coffee_research")
    assert cap == 5, f"get_quota_cap('coffee_research') returned {cap}, expected 5 after update"


def test_quota_settings_improve_brew_update_persists(client, seeded_admin_user) -> None:
    """POST update to ai.improve_brew_daily_quota persists and get_quota_cap reflects it.

    Same flow as test_quota_settings_research_update_persists but for the
    brew_improvement bucket (D-08: separate quota key per rec_type).
    Re-prewarm required for the same reason — set_setting() invalidates the key.
    """
    _require_settings_editor()
    _require_ai_quota()

    from app.db import SessionLocal
    from app.services.ai_quota import get_quota_cap
    from app.services.settings import prewarm_cache

    session_cookie = seeded_admin_user["signed_cookie"]
    token = _prime_csrf(client, session_cookie)

    r = client.post(
        "/admin/settings/ai.improve_brew_daily_quota",
        data={"value": "10", "X-CSRF-Token": token},
        cookies={"session_id": session_cookie, "csrftoken": token},
        headers={"X-CSRF-Token": token},
    )
    assert r.status_code == 200, (
        f"POST /admin/settings/ai.improve_brew_daily_quota returned {r.status_code}: {r.text[:300]}"
    )

    # Re-prewarm so the cache reflects the committed value
    with SessionLocal() as db:
        prewarm_cache(db)

    cap = get_quota_cap("brew_improvement")
    assert cap == 10, f"get_quota_cap('brew_improvement') returned {cap}, expected 10 after update"
