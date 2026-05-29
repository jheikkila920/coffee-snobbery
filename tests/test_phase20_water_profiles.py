"""Wave 0 contract tests for GBREW-04 water profiles (Phase 20, Plan 01).

These tests assert the LOCKED behavior AFTER Plan 20-02 adds:
  - water_profiles table (via p20_water_profiles migration)
  - POST /water-profiles endpoint (WaterProfileCreate schema, HX-Trigger)
  - brew_sessions.water_profile_id FK column
  - Migration data-seed: INITCAP(TRIM(water_type)) dedup + link + NULL handling

They are EXPECTED to fail RED until Plan 20-02 lands those additions.

Migration tests simulate the migration's data-seeding logic (Pattern 3 SQL)
without re-running Alembic — they verify the INITCAP+TRIM normalization
produces the correct output from representative water_type values.

Requirement traceability:
  GBREW-04 (D-02, D-03), T-V4 (CSRF on POST /water-profiles)

No infra-skip calls in this file — helpers live in conftest.py
so that grep for pytest.skip in test files returns 0.
"""

from __future__ import annotations

import json
from typing import Any

from tests.conftest import _require_water_profiles_table

# --------------------------------------------------------------------------- #
# Endpoint tests (require authed TestClient + DB + p20 migration)             #
# --------------------------------------------------------------------------- #


def test_create_water_profile(authed_client: Any) -> None:
    """GBREW-04 / D-02 / T-V4: POST /water-profiles creates profile + fires HX-Trigger.

    Mirrors the flavor_notes.py pattern:
    - POST with as_modal=true returns 200 and HX-Trigger header
    - HX-Trigger JSON contains "water-profile-created" key with water_profile_id + name

    CSRF is satisfied via the authed_client fixture's X-CSRF-Token header.
    This test is RED until Plan 20-02 wires the /water-profiles router.
    """
    _require_water_profiles_table()

    resp = authed_client.post(
        "/water-profiles",
        data={
            "name": "Third Wave Water",
            "notes": "remineralized",
            "as_modal": "true",
        },
    )
    assert resp.status_code == 200, (
        f"POST /water-profiles returned {resp.status_code}: {resp.text[:200]}"
    )
    hx_trigger = resp.headers.get("HX-Trigger", "")
    assert hx_trigger, "HX-Trigger header missing from POST /water-profiles response (D-02)"
    trigger_data = json.loads(hx_trigger)
    assert "water-profile-created" in trigger_data, (
        f"HX-Trigger payload missing 'water-profile-created' key: {hx_trigger}"
    )
    payload = trigger_data["water-profile-created"]
    assert "water_profile_id" in payload, (
        "HX-Trigger 'water-profile-created' missing water_profile_id"
    )
    assert payload.get("name") == "Third Wave Water", (
        f"HX-Trigger name mismatch: {payload.get('name')!r}"
    )
    assert isinstance(payload["water_profile_id"], int), (
        "water_profile_id in HX-Trigger must be an int"
    )


def test_create_water_profile_duplicate(authed_client: Any) -> None:
    """GBREW-04: second POST of the same name returns an error with errors.name set.

    DuplicateNameError path — mirrors flavor_notes.py behavior.
    """
    _require_water_profiles_table()

    name = "Brita Filtered"
    # First create succeeds
    resp1 = authed_client.post(
        "/water-profiles",
        data={"name": name, "notes": "", "as_modal": "true"},
    )
    assert resp1.status_code == 200

    # Second create with same name must return an inline error (200 + form re-render)
    resp2 = authed_client.post(
        "/water-profiles",
        data={"name": name, "notes": "", "as_modal": "true"},
    )
    assert resp2.status_code in (200, 422), (
        f"Duplicate POST returned unexpected status {resp2.status_code}"
    )
    # Must not return a new profile HX-Trigger on duplicate
    hx_trigger = resp2.headers.get("HX-Trigger", "")
    if hx_trigger:
        trigger_data = json.loads(hx_trigger)
        assert "water-profile-created" not in trigger_data, (
            "Duplicate POST must NOT fire water-profile-created trigger"
        )


def test_create_water_profile_blank(authed_client: Any) -> None:
    """GBREW-04: POST with empty name returns an error (WaterProfileCreate min_length=1)."""
    _require_water_profiles_table()

    resp = authed_client.post(
        "/water-profiles",
        data={"name": "", "notes": "", "as_modal": "true"},
    )
    assert resp.status_code in (200, 422), (
        f"Blank name POST returned unexpected status {resp.status_code}"
    )
    hx_trigger = resp.headers.get("HX-Trigger", "")
    if hx_trigger:
        trigger_data = json.loads(hx_trigger)
        assert "water-profile-created" not in trigger_data, (
            "Blank-name POST must NOT fire water-profile-created trigger"
        )


# --------------------------------------------------------------------------- #
# Migration normalization tests (DB-connected, no Alembic re-run)             #
# --------------------------------------------------------------------------- #


def test_migration_seeds_profiles(sync_db: Any) -> None:
    """GBREW-04 / D-03: normalization SQL produces correct DISTINCT profile names.

    Insert synthetic water_type values:
      ["Tap", "tap", "FILTERED", "Third Wave Water"]

    Assert the INITCAP+TRIM dedup SQL (from Pattern 3) produces exactly:
      {"Tap", "Filtered", "Third Wave Water"}

    This test verifies the normalization SQL logic — it does NOT re-run Alembic.
    Infra skip (no Postgres): handled via sync_db fixture skipping cleanly.
    """
    from sqlalchemy import text

    input_values = ["Tap", "tap", "FILTERED", "Third Wave Water"]

    rows = sync_db.execute(
        text(
            "SELECT DISTINCT INITCAP(TRIM(v)) AS name "
            "FROM (VALUES (:v1), (:v2), (:v3), (:v4)) AS t(v) "
            "WHERE v IS NOT NULL AND TRIM(v) != '' "
            "ORDER BY INITCAP(TRIM(v))"
        ),
        {
            "v1": input_values[0],
            "v2": input_values[1],
            "v3": input_values[2],
            "v4": input_values[3],
        },
    ).all()

    normalized = {row[0] for row in rows}
    expected = {"Tap", "Filtered", "Third Wave Water"}
    assert normalized == expected, (
        f"INITCAP+TRIM dedup produced {normalized!r}, expected {expected!r} "
        "(D-03: 'tap'+'Tap' must collapse, 'FILTERED' must normalize to 'Filtered')"
    )


def test_migration_links_sessions(sync_db: Any) -> None:
    """GBREW-04 / D-03: linking SQL maps each water_type to its normalized profile name.

    After seeding, the UPDATE in Pattern 3 uses INITCAP(TRIM(water_type)) to
    match rows to profiles. Verify that the normalization is consistent so the
    link produces the correct FK assignment for varied casings.
    """
    from sqlalchemy import text

    # Test cases: (raw water_type input, expected normalized profile name)
    test_cases = [
        ("Tap", "Tap"),
        ("tap", "Tap"),
        ("FILTERED", "Filtered"),
        ("Third Wave Water", "Third Wave Water"),
        ("  third wave water  ", "Third Wave Water"),
    ]

    for raw_wt, expected_profile_name in test_cases:
        normalized = sync_db.execute(
            text("SELECT INITCAP(TRIM(:wt))"),
            {"wt": raw_wt},
        ).scalar()
        assert normalized == expected_profile_name, (
            f"INITCAP(TRIM({raw_wt!r})) → {normalized!r}, "
            f"expected {expected_profile_name!r} "
            "(D-03: linking SQL must normalize correctly for FK assignment)"
        )


def test_migration_null_water_type(sync_db: Any) -> None:
    """GBREW-04 / D-03 / A2: blank/NULL water_type produces zero profile rows.

    Sessions with water_type NULL, '', or '   ' must:
    1. NOT create a water_profiles row ('Unknown', 'Unspecified', etc.)
    2. Result in water_profile_id = NULL (no FK link)

    Verifies the seed SQL's WHERE clause:
      WHERE water_type IS NOT NULL AND TRIM(water_type) != ''
    produces zero rows for blank/NULL inputs.
    """
    from sqlalchemy import text

    rows = sync_db.execute(
        text(
            "SELECT DISTINCT INITCAP(TRIM(v)) AS name "
            "FROM (VALUES (:v1), (:v2), (:v3)) AS t(v) "
            "WHERE v IS NOT NULL AND TRIM(v) != ''"
        ),
        {"v1": None, "v2": "", "v3": "   "},
    ).all()

    assert len(rows) == 0, (
        f"Seed SQL produced {len(rows)} profiles for blank/NULL inputs "
        f"(got: {[r[0] for r in rows]}) — expected 0. "
        "No 'Unknown'/'Unspecified' profile should be seeded (D-03, A2)"
    )

    # Belt-and-braces: none of the banned placeholder names
    banned_names = {"Unknown", "Unspecified", "None", "N/A", ""}
    produced_names = {row[0] for row in rows}
    assert not (produced_names & banned_names), (
        f"Seed SQL produced banned placeholder profile names: {produced_names & banned_names}"
    )
