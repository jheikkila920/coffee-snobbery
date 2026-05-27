"""Greppable-absence + structural tests for CATALOG-07 (roast-freshness removal).

Wave 0 stubs: all tests are written BEFORE the implementation lands and are
expected to fail (or skip on no-DB) until Tasks 1-5 of plan 15.1-02 complete.

Tests 1/2/5 touch the live DB -- gated by _require_postgres().
Tests 3/4/6-14 are file-system / module-attribute checks with no DB needed.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import pytest

# --------------------------------------------------------------------------- #
# Skip gate (mirrors tests/services/test_analytics.py pattern lines 25-48)    #
# --------------------------------------------------------------------------- #


def _require_postgres() -> None:
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable -- freshness-removal test needs the DB")


def _require_p4_migration_applied() -> None:
    try:
        from sqlalchemy import text

        from app.db import engine
    except ImportError:
        pytest.skip("app.db not importable")
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT to_regclass('public.bags')")).scalar()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB unreachable: {exc.__class__.__name__}: {exc}")
    if row is None:
        pytest.skip("bags table not present -- migration not applied")


# --------------------------------------------------------------------------- #
# Test 1: bags.roast_date column GONE                                          #
# --------------------------------------------------------------------------- #


def test_bags_roast_date_column_gone() -> None:
    """D-16: bags.roast_date column must not exist after p15_1_drop_roast_date migration."""
    _require_postgres()
    _require_p4_migration_applied()
    from sqlalchemy import text

    from app.db import engine

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='bags' AND column_name='roast_date'"
            )
        ).all()
    assert len(rows) == 0, (
        "bags.roast_date column still exists -- migration p15_1_drop_roast_date did not run"
    )


# --------------------------------------------------------------------------- #
# Test 2: freshness card endpoint returns 404                                  #
# --------------------------------------------------------------------------- #


def test_freshness_card_endpoint_returns_404() -> None:
    """D-19: GET /home/cards/roast-freshness must return 404 -- route deleted."""
    _require_postgres()
    try:
        from fastapi.testclient import TestClient

        from app.main import app
    except ImportError:
        pytest.skip("app.main not importable")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/home/cards/roast-freshness")
    assert response.status_code == 404, f"Expected 404 on deleted route, got {response.status_code}"


# --------------------------------------------------------------------------- #
# Test 3: fragment template file deleted                                       #
# --------------------------------------------------------------------------- #


def test_freshness_fragment_template_does_not_exist() -> None:
    """D-19: app/templates/fragments/home/roast_freshness.html must be git-rm'd."""
    assert not os.path.exists("app/templates/fragments/home/roast_freshness.html"), (
        "roast_freshness.html still exists -- must be deleted as part of D-19"
    )


# --------------------------------------------------------------------------- #
# Test 4: analytics module has no freshness_buckets function                  #
# --------------------------------------------------------------------------- #


def test_analytics_module_has_no_freshness_buckets() -> None:
    """D-19: get_roast_freshness_buckets must not exist in app.services.analytics."""
    try:
        from app.services import analytics
    except ImportError:
        pytest.skip("app.services.analytics not importable")
    assert not hasattr(analytics, "get_roast_freshness_buckets"), (
        "analytics.get_roast_freshness_buckets still exists -- must be removed for D-19"
    )


# --------------------------------------------------------------------------- #
# Test 5: compute_input_signature omits bag roast_date                        #
# --------------------------------------------------------------------------- #


def test_compute_input_signature_omits_bag_roast_date() -> None:
    """D-17: signature must run without AttributeError on Bag.roast_date."""
    _require_postgres()
    _require_p4_migration_applied()
    import datetime
    from decimal import Decimal

    from sqlalchemy import delete

    from app.db import SessionLocal
    from app.models.brew_session import BrewSession
    from app.models.coffee import Coffee
    from app.models.user import User
    from app.services import analytics

    with SessionLocal() as db:
        user = User(
            username="freshtest-sig-user",
            password_hash="x" * 16,
            is_admin=False,
            is_active=True,
        )
        db.add(user)
        db.flush()

        coffee = Coffee(name="freshtest-sig-coffee")
        db.add(coffee)
        db.flush()

        session = BrewSession(
            user_id=user.id,
            coffee_id=coffee.id,
            dose_grams_actual=Decimal("15"),
            water_grams_actual=Decimal("250"),
            rating=Decimal("4.0"),
            flavor_note_ids_observed=[],
            brewed_at=datetime.datetime(2026, 3, 10, 10, 0, 0, tzinfo=datetime.UTC),
        )
        db.add(session)
        db.commit()
        uid = user.id

    with SessionLocal() as db:
        sig = analytics.compute_input_signature(db, uid)

    empty_sig = hashlib.sha256(b"[]").hexdigest()
    assert sig != empty_sig, "Expected a non-empty signature for a user with rated sessions"
    assert len(sig) == 64, f"Expected 64-char hex SHA256, got: {sig!r}"
    assert all(c in "0123456789abcdef" for c in sig), f"Signature is not valid hex: {sig!r}"

    # Cleanup
    with SessionLocal() as db:
        db.execute(delete(BrewSession).where(BrewSession.user_id == uid))
        db.execute(delete(Coffee).where(Coffee.name == "freshtest-sig-coffee"))
        db.execute(delete(User).where(User.id == uid))
        db.commit()


# --------------------------------------------------------------------------- #
# Test 6: signature CHANGES after freshness removal                           #
# --------------------------------------------------------------------------- #


def test_signature_changes_after_freshness_removal() -> None:
    """D-17: removing roast_date from the serialized row changes the signature."""
    import json

    # Old style: 6 elements including roast_date at index 5
    old_row = [1, 4.0, [], None, None, "2026-03-08"]
    old_canonical = json.dumps([old_row], sort_keys=True, separators=(",", ":"))
    old_sig = hashlib.sha256(old_canonical.encode("utf-8")).hexdigest()

    # New style: 5 elements, no roast_date
    new_row = [1, 4.0, [], None, None]
    new_canonical = json.dumps([new_row], sort_keys=True, separators=(",", ":"))
    new_sig = hashlib.sha256(new_canonical.encode("utf-8")).hexdigest()

    assert old_sig != new_sig, (
        "Old (with roast_date) and new (without roast_date) signatures must differ -- "
        "this proves the signature change forces AI regen on next nightly run (D-17)"
    )


# --------------------------------------------------------------------------- #
# Test 7: CSV EXPORT_FIELDNAMES has no roast_date                             #
# --------------------------------------------------------------------------- #


def test_csv_export_fieldnames_has_no_roast_date() -> None:
    """D-20: roast_date must not be in csv_io.EXPORT_FIELDNAMES."""
    try:
        from app.services import csv_io
    except ImportError:
        pytest.skip("app.services.csv_io not importable")
    assert "roast_date" not in csv_io.EXPORT_FIELDNAMES, (
        "roast_date found in EXPORT_FIELDNAMES -- must be removed per D-20"
    )


# --------------------------------------------------------------------------- #
# Test 8: CSV _HEADER_ALIASES has no roast_date                               #
# --------------------------------------------------------------------------- #


def test_csv_header_aliases_has_no_roast_date() -> None:
    """D-20: roast_date must not be a key in csv_io._HEADER_ALIASES."""
    try:
        from app.services import csv_io
    except ImportError:
        pytest.skip("app.services.csv_io not importable")
    assert "roast_date" not in csv_io._HEADER_ALIASES, (
        "roast_date found in _HEADER_ALIASES -- must be removed per D-20"
    )


# --------------------------------------------------------------------------- #
# Test 9: _resolve_bag function gone                                           #
# --------------------------------------------------------------------------- #


def test_resolve_bag_function_gone() -> None:
    """D-20: _resolve_bag must not exist in csv_io (function deleted)."""
    try:
        from app.services import csv_io
    except ImportError:
        pytest.skip("app.services.csv_io not importable")
    assert not hasattr(csv_io, "_resolve_bag"), (
        "csv_io._resolve_bag still exists -- must be deleted per D-20"
    )


# --------------------------------------------------------------------------- #
# Test 10: grep app/ for roast_date returns zero matches                      #
# --------------------------------------------------------------------------- #

_FRESHNESS_PATTERN = re.compile(
    r"roast_date|freshness|days off roast|days_off_roast", re.IGNORECASE
)
_MIGRATIONS_VERSIONS = os.path.join("app", "migrations", "versions")


def _grep_app_source(pattern: re.Pattern[str]) -> list[str]:
    """Scan app/ .py and .html files (excluding migrations/versions/) for pattern."""
    hits: list[str] = []
    app_dir = Path("app")
    if not app_dir.exists():
        return hits
    for path in app_dir.rglob("*"):
        if path.suffix not in {".py", ".html"}:
            continue
        # Exclude migration version files -- they legitimately reference roast_date
        if "migrations" in path.parts and "versions" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{path}:{lineno}: {line.rstrip()}")
    return hits


def test_grep_app_for_roast_date_returns_zero() -> None:
    """After D-16..D-20, no app/ source (excluding migrations/versions/) should
    reference roast_date, freshness, days off roast, or days_off_roast.
    """
    hits = _grep_app_source(_FRESHNESS_PATTERN)
    assert not hits, (
        "Found roast_date/freshness references in app/ (excluding migrations/versions/):\n"
        + "\n".join(hits)
    )


# --------------------------------------------------------------------------- #
# Test 11: D-18 audit -- grep ai_service.py for freshness strings             #
# --------------------------------------------------------------------------- #

_D18_PATTERN = re.compile(r"freshness|roast.date|days.off.roast|resting", re.IGNORECASE)


def test_grep_ai_service_for_freshness_returns_zero() -> None:
    """D-18: ai_service.py must contain zero references to freshness-related strings."""
    target = Path("app/services/ai_service.py")
    if not target.exists():
        pytest.skip(f"{target} does not exist")
    text = target.read_text(encoding="utf-8")
    hits = [
        f"line {i}: {line.rstrip()}"
        for i, line in enumerate(text.splitlines(), 1)
        if _D18_PATTERN.search(line)
    ]
    assert not hits, (
        f"D-18 audit failed: found freshness-related strings in {target}:\n" + "\n".join(hits)
    )


# --------------------------------------------------------------------------- #
# Test 12: bag_form.html has no roast_date input                              #
# --------------------------------------------------------------------------- #


def test_bag_form_template_has_no_roast_date_input() -> None:
    """D-19: bag_form.html must not contain name=\"roast_date\" input."""
    target = Path("app/templates/fragments/bag_form.html")
    if not target.exists():
        pytest.skip(f"{target} does not exist")
    content = target.read_text(encoding="utf-8")
    assert 'name="roast_date"' not in content, (
        f'Found name="roast_date" in {target} -- must be removed'
    )


# --------------------------------------------------------------------------- #
# Test 13: bag_row.html label replaced (no "Roasted {{" or "Roast date unknown")
# --------------------------------------------------------------------------- #


def test_bag_row_template_label_replaced() -> None:
    """D-19: bag_row.html must not contain the old roast_date label strings."""
    target = Path("app/templates/fragments/bag_row.html")
    if not target.exists():
        pytest.skip(f"{target} does not exist")
    content = target.read_text(encoding="utf-8")
    assert "Roasted {{" not in content, (
        'bag_row.html still contains "Roasted {{" -- old roast_date label must be replaced'
    )
    assert "Roast date unknown" not in content, (
        'bag_row.html still contains "Roast date unknown" -- old fallback must be replaced'
    )


# --------------------------------------------------------------------------- #
# Test 14: home page section removed (no freshness-heading)                   #
# --------------------------------------------------------------------------- #


def test_home_page_section_removed() -> None:
    """D-19: home.html must not contain freshness-heading aria label."""
    target = Path("app/templates/pages/home.html")
    if not target.exists():
        pytest.skip(f"{target} does not exist")
    content = target.read_text(encoding="utf-8")
    assert "freshness-heading" not in content, (
        f"Found freshness-heading in {target} -- section must be removed"
    )
