"""TEST-01: Happy-path end-to-end smoke test.

Drives the full acceptance-criteria chain:

    setup → create coffee (with roaster) → create equipment → create recipe
    → log a brew session → GET / renders home sections (cold-start or analytics)

This is a HARD test under SNOB_CI=1 — it FAILS (does not skip) when the brew
or catalog routers are unimportable or Postgres is unreachable. Mirror the
Plan 12-01 SNOB_CI pattern established in conftest.py.

CSRF triple-send idiom (from test_phase02_smoke.py):
    client.post(url,
        data={"X-CSRF-Token": token, ...},
        headers={"X-CSRF-Token": token},
        cookies={"csrftoken": token, "session_id": session_signed},
        follow_redirects=False)
    Refresh `token` from each response's csrftoken cookie before the next POST.
"""

from __future__ import annotations

import json
import os
import re

import pytest

_CI_MODE = os.environ.get("SNOB_CI") == "1"


def _require_wired(label: str) -> None:
    """Hard-fail in CI if any catalog/brew router dependency is missing.

    Under SNOB_CI=1, a missing router import is a real failure — not a skip.
    Outside CI, a missing import produces a clean pytest.skip.
    """
    try:
        from app.routers.brew import router as brew_router  # noqa: F401
        from app.routers.coffees import router as coffees_router  # noqa: F401
        from app.routers.equipment import router as equipment_router  # noqa: F401
        from app.routers.recipes import router as recipes_router  # noqa: F401
        from app.routers.roasters import router as roasters_router  # noqa: F401
    except ImportError as exc:
        if _CI_MODE:
            pytest.fail(f"SNOB_CI=1 but {label} routers unimportable: {exc}")
        else:
            pytest.skip(f"{label} routers not yet present: {exc}")


# HARD-test enforcement note: the conftest ``client`` fixture routes its
# Postgres-unreachable path through ``_require_postgres``, which fails under
# SNOB_CI=1 (and skips otherwise). So requesting ``client`` is sufficient to
# make this smoke a HARD failure in CI when the DB is down — no per-test guard
# needed (a prior no-op ``_require_postgres_hard`` helper was removed as it
# delivered nothing at runtime; see 12-REVIEW WR-03).


def _extract_id_from_html(html: str, prefix: str) -> int:
    """Parse the numeric ID from ``id="<prefix>-<N>"`` in the response HTML.

    The row templates render e.g. ``id="roaster-3"``, ``id="coffee-7"``.
    Returns the integer id or raises AssertionError if not found.
    """
    m = re.search(rf'id="{re.escape(prefix)}-(\d+)"', html)
    assert m, (
        f"Expected id=\"{prefix}-<N>\" in response HTML; "
        f"got: {html[:400]}"
    )
    return int(m.group(1))


def test_happy_path_full_chain(client) -> None:
    """End-to-end acceptance-criteria smoke: setup → catalog → brew → home.

    Steps:
      1  Bootstrap via /setup (fresh DB, mirrors Phase 2 smoke)
      2  POST /roasters — create a roaster; parse id from response HTML
      3  POST /coffees  — create a coffee referencing the roaster
      4  POST /equipment (brewer) — create a brewer; parse id
      5  POST /equipment (grinder) — create a grinder; parse id
      6  POST /equipment (kettle) — create a kettle; parse id
      7  POST /recipes  — create a recipe with a minimal steps JSON array
      8  POST /brew     — log a session; expect 204 + HX-Redirect: /brew
      9  GET /          — home shell; assert 200 + section markers present

    The test is a HARD failure under SNOB_CI=1 (not a skip).
    """
    _require_wired("brew + catalog")

    # ------------------------------------------------------------------ #
    # Step 1: bootstrap via /setup                                        #
    # (mirrors test_phase02_smoke.py: GET → csrftoken → POST → 303 →     #
    #  extract session_id)                                                #
    # ------------------------------------------------------------------ #
    r_setup_get = client.get("/setup")
    assert r_setup_get.status_code == 200, (
        f"GET /setup must 200 on fresh DB; got {r_setup_get.status_code}: "
        f"{r_setup_get.text[:200]}"
    )
    token = r_setup_get.cookies.get("csrftoken")
    assert token, "starlette-csrf must set csrftoken cookie on GET /setup"

    r_setup = client.post(
        "/setup",
        data={
            "X-CSRF-Token": token,
            "username": "happypath",
            "email": "happypath@example.com",
            "password": "twelve-chars-min-password",
        },
        headers={"X-CSRF-Token": token},
        cookies={"csrftoken": token},
        follow_redirects=False,
    )
    assert r_setup.status_code == 303, (
        f"POST /setup must 303; got {r_setup.status_code}: {r_setup.text[:300]}"
    )
    set_cookie = r_setup.headers.get("set-cookie", "")
    assert "session_id=" in set_cookie, (
        f"auto-login must set session_id; got: {set_cookie!r}"
    )

    m = re.search(r"session_id=([^;]+)", set_cookie)
    assert m, f"could not extract session_id: {set_cookie}"
    session_signed = m.group(1)

    # Refresh CSRF token from setup response in case rotation kicked in.
    token = r_setup.cookies.get("csrftoken", token)

    def _cookies() -> dict[str, str]:
        return {"csrftoken": token, "session_id": session_signed}

    # ------------------------------------------------------------------ #
    # Step 2: POST /roasters                                              #
    # ------------------------------------------------------------------ #
    r_roaster = client.post(
        "/roasters",
        data={"X-CSRF-Token": token, "name": "Smoke Roasters"},
        headers={"X-CSRF-Token": token},
        cookies=_cookies(),
        follow_redirects=False,
    )
    # Success → 200 + row fragment (not a 30x redirect)
    assert r_roaster.status_code == 200, (
        f"POST /roasters must 200 on success; got {r_roaster.status_code}: "
        f"{r_roaster.text[:300]}"
    )
    roaster_id = _extract_id_from_html(r_roaster.text, "roaster")
    token = r_roaster.cookies.get("csrftoken", token)

    # ------------------------------------------------------------------ #
    # Step 3: POST /coffees                                               #
    # ------------------------------------------------------------------ #
    r_coffee = client.post(
        "/coffees",
        data={
            "X-CSRF-Token": token,
            "name": "Smoke Blend",
            "roaster_id": str(roaster_id),
            "country": "Ethiopia",
            "process": "washed",
            "roast_level": "light",
        },
        headers={"X-CSRF-Token": token},
        cookies=_cookies(),
        follow_redirects=False,
    )
    assert r_coffee.status_code == 200, (
        f"POST /coffees must 200 on success; got {r_coffee.status_code}: "
        f"{r_coffee.text[:300]}"
    )
    coffee_id = _extract_id_from_html(r_coffee.text, "coffee")
    token = r_coffee.cookies.get("csrftoken", token)

    # ------------------------------------------------------------------ #
    # Step 4: POST /equipment — brewer                                    #
    # ------------------------------------------------------------------ #
    r_brewer = client.post(
        "/equipment",
        data={
            "X-CSRF-Token": token,
            "type": "brewer",
            "brand": "Hario",
            "model": "V60",
        },
        headers={"X-CSRF-Token": token},
        cookies=_cookies(),
        follow_redirects=False,
    )
    assert r_brewer.status_code == 200, (
        f"POST /equipment (brewer) must 200; got {r_brewer.status_code}: "
        f"{r_brewer.text[:300]}"
    )
    brewer_id = _extract_id_from_html(r_brewer.text, "equipment")
    token = r_brewer.cookies.get("csrftoken", token)

    # ------------------------------------------------------------------ #
    # Step 5: POST /equipment — grinder                                   #
    # ------------------------------------------------------------------ #
    r_grinder = client.post(
        "/equipment",
        data={
            "X-CSRF-Token": token,
            "type": "grinder",
            "brand": "Comandante",
            "model": "C40",
        },
        headers={"X-CSRF-Token": token},
        cookies=_cookies(),
        follow_redirects=False,
    )
    assert r_grinder.status_code == 200, (
        f"POST /equipment (grinder) must 200; got {r_grinder.status_code}: "
        f"{r_grinder.text[:300]}"
    )
    grinder_id = _extract_id_from_html(r_grinder.text, "equipment")
    token = r_grinder.cookies.get("csrftoken", token)

    # ------------------------------------------------------------------ #
    # Step 6: POST /equipment — kettle                                    #
    # ------------------------------------------------------------------ #
    r_kettle = client.post(
        "/equipment",
        data={
            "X-CSRF-Token": token,
            "type": "kettle",
            "brand": "Brewista",
            "model": "Artisan",
        },
        headers={"X-CSRF-Token": token},
        cookies=_cookies(),
        follow_redirects=False,
    )
    assert r_kettle.status_code == 200, (
        f"POST /equipment (kettle) must 200; got {r_kettle.status_code}: "
        f"{r_kettle.text[:300]}"
    )
    kettle_id = _extract_id_from_html(r_kettle.text, "equipment")
    token = r_kettle.cookies.get("csrftoken", token)

    # ------------------------------------------------------------------ #
    # Step 7: POST /recipes                                               #
    # steps is a JSON-stringified array per the router (json.loads path)  #
    # ------------------------------------------------------------------ #
    steps_json = json.dumps([
        {"water_grams": 50, "time_seconds": 30, "label": "bloom"},
        {"water_grams": 200, "time_seconds": 120, "label": "main pour"},
    ])
    r_recipe = client.post(
        "/recipes",
        data={
            "X-CSRF-Token": token,
            "name": "Smoke V60",
            "dose_grams": "15",
            "water_grams": "250",
            "water_temp_c": "93",
            "grind_setting": "18 clicks",
            "steps": steps_json,
        },
        headers={"X-CSRF-Token": token},
        cookies=_cookies(),
        follow_redirects=False,
    )
    assert r_recipe.status_code == 200, (
        f"POST /recipes must 200 on success; got {r_recipe.status_code}: "
        f"{r_recipe.text[:300]}"
    )
    recipe_id = _extract_id_from_html(r_recipe.text, "recipe")
    token = r_recipe.cookies.get("csrftoken", token)

    # ------------------------------------------------------------------ #
    # Step 8: POST /brew — log the session                                #
    # Success: 204 + HX-Redirect: /brew  (NOT 200)                       #
    # ------------------------------------------------------------------ #
    r_brew = client.post(
        "/brew",
        data={
            "X-CSRF-Token": token,
            "coffee_id": str(coffee_id),
            "recipe_id": str(recipe_id),
            "brewer_id": str(brewer_id),
            "grinder_id": str(grinder_id),
            "kettle_id": str(kettle_id),
            "dose_grams_actual": "15.0",
            "water_grams_actual": "250.0",
            "water_temp_c_actual": "93",
            "grind_setting_actual": "18 clicks",
            "brewed_at": "2026-05-23T09:00:00",
        },
        headers={"X-CSRF-Token": token},
        cookies=_cookies(),
        follow_redirects=False,
    )
    assert r_brew.status_code == 204, (
        f"POST /brew must 204 on success (not 200); got {r_brew.status_code}: "
        f"{r_brew.text[:300]}"
    )
    hx_redirect = r_brew.headers.get("HX-Redirect", "")
    assert hx_redirect == "/brew", (
        f"POST /brew must set HX-Redirect: /brew; got {hx_redirect!r}"
    )
    token = r_brew.cookies.get("csrftoken", token)

    # ------------------------------------------------------------------ #
    # Step 9: GET / — home shell                                          #
    # Assert 200 + real section markers from the home template            #
    # ------------------------------------------------------------------ #
    r_home = client.get("/", cookies=_cookies())
    assert r_home.status_code == 200, (
        f"GET / must 200 for authenticated user; got {r_home.status_code}: "
        f"{r_home.text[:300]}"
    )

    # "Recent brews" is always-on regardless of cold-start gate (D-01, HOME-07).
    assert "Recent brews" in r_home.text, (
        "home shell must always render the 'Recent brews' section; "
        f"got: {r_home.text[:500]}"
    )

    # The cold-start gate check: we just logged 1 session (< 3 needed).
    # The home page renders either the cold-start meter OR the full analytics
    # cards. Assert one of the two stable markers is present.
    cold_start_active = "Build your taste profile." in r_home.text
    analytics_active = "Top Coffees" in r_home.text or "What to buy next" in r_home.text

    assert cold_start_active or analytics_active, (
        "home shell must render either the cold-start meter "
        "('Build your taste profile.') or analytics cards "
        "('Top Coffees' / 'What to buy next'); "
        f"got: {r_home.text[:600]}"
    )

    # With only 1 brew session the cold-start gate should still be closed.
    # Confirm the progress meter is present (the `role="progressbar"` attribute
    # lives in the _cold_start.html include).
    assert 'role="progressbar"' in r_home.text, (
        "home shell must include the cold-start progress meter after 1 brew session "
        "(gate requires 3 sessions); missing progressbar role attribute. "
        f"Body: {r_home.text[:500]}"
    )
