"""Service-layer tests for plan 05-03 — CSV brew import/export (BREW-10, BREW-11).

Task 1 (import): per-row resolve (D-12 coffee / D-13 bag), dedup (D-14), single
transaction (BREW-11, Pitfall 4), and D-09 observed-note auto-create.
Task 2 (export): name-based, round-trip-safe (D-15), computed ratio + EY, and
CSV formula-injection neutralization.

Mirrors the structural shape of ``tests/services/test_brew_sessions_service.py``:
real Postgres via the ``_require_postgres`` + ``_require_p5_migration_applied``
skip gates, the ``SessionLocal`` context-manager pattern, and a ``clean_csv``
fixture that wipes the Phase-5 + seeded catalog rows before and after each test.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest

# --------------------------------------------------------------------------- #
# Skip gates (mirror tests/services/test_brew_sessions_service.py)             #
# --------------------------------------------------------------------------- #


def _require_postgres() -> None:
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — Phase 5 CSV test needs the DB")


def _require_p5_migration_applied() -> None:
    try:
        from sqlalchemy import text

        from app.db import engine
    except ImportError:
        pytest.skip("app.db not importable")
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT to_regclass('public.brew_sessions')")).scalar()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB unreachable: {exc.__class__.__name__}: {exc}")
    if row is None:
        pytest.skip("p5_brew_sessions migration not applied")


# --------------------------------------------------------------------------- #
# Seeding helpers + clean fixture                                             #
# --------------------------------------------------------------------------- #


def _seed_user(db, *, username: str):
    from app.models.user import User

    user = User(username=username, password_hash="x" * 16, is_admin=False, is_active=True)
    db.add(user)
    db.flush()
    return user


def _seed_roaster(db, *, name: str):
    from app.models.roaster import Roaster

    roaster = Roaster(name=name)
    db.add(roaster)
    db.flush()
    return roaster


def _seed_coffee(db, *, name: str, roaster_id: int | None = None):
    from app.models.coffee import Coffee

    coffee = Coffee(name=name, roaster_id=roaster_id)
    db.add(coffee)
    db.flush()
    return coffee


def _seed_bag(db, *, coffee_id: int, roast_date):
    from app.models.bag import Bag

    bag = Bag(coffee_id=coffee_id, roast_date=roast_date)
    db.add(bag)
    db.flush()
    return bag


@pytest.fixture
def clean_csv() -> Iterator[None]:
    """Wipe Phase-5 rows + the seeded catalog/users the CSV tests create.

    brew_sessions FKs to users (RESTRICT), coffees (RESTRICT), bags (SET NULL),
    so delete sessions first, then bags, then the seeded coffees / roasters /
    flavor notes / users (identified by the ``csvtest-`` username and the
    ``CSV `` name prefixes the helpers use).
    """
    from sqlalchemy import text

    from app.db import engine

    def _reset() -> None:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM brew_sessions"))
            conn.execute(text("DELETE FROM brew_drafts"))
            conn.execute(
                text(
                    "DELETE FROM bags WHERE coffee_id IN "
                    "(SELECT id FROM coffees WHERE name LIKE 'CSV %')"
                )
            )
            conn.execute(text("DELETE FROM coffees WHERE name LIKE 'CSV %'"))
            conn.execute(text("DELETE FROM roasters WHERE name LIKE 'CSV %'"))
            conn.execute(text("DELETE FROM flavor_notes WHERE name LIKE 'csvnote-%'"))
            conn.execute(
                text(
                    "DELETE FROM sessions WHERE user_id IN "
                    "(SELECT id FROM users WHERE username LIKE 'csvtest-%')"
                )
            )
            conn.execute(text("DELETE FROM users WHERE username LIKE 'csvtest-%'"))

    _reset()
    yield
    _reset()


# Canonical Snobbery-native export header order (the authoritative round-trip
# format the importer's alias table treats as primary). Helpers build CSVs with
# only the subset of columns each test needs.
def _csv(rows: list[dict[str, str]], *, fieldnames: list[str]) -> bytes:
    import csv
    import io

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in fieldnames})
    return buf.getvalue().encode("utf-8")


# --------------------------------------------------------------------------- #
# Task 1 — import outcomes                                                     #
# --------------------------------------------------------------------------- #


def test_import_outcomes(clean_csv: None) -> None:
    """Refused (coffee not in catalog / ambiguous / bag not found), skipped
    (duplicate), inserted (freestyle + with bag)."""
    _require_postgres()
    _require_p5_migration_applied()
    from app.db import SessionLocal
    from app.services import brew_sessions as brew_svc
    from app.services import csv_io

    with SessionLocal() as db:
        user = _seed_user(db, username="csvtest-outcomes")
        r1 = _seed_roaster(db, name="CSV Roaster One")
        r2 = _seed_roaster(db, name="CSV Roaster Two")
        # Unique coffee (single roaster) — resolves.
        _seed_coffee(db, name="CSV Solo", roaster_id=r1.id)
        # Ambiguous coffee — same name under two roasters.
        _seed_coffee(db, name="CSV Ambiguous", roaster_id=r1.id)
        _seed_coffee(db, name="CSV Ambiguous", roaster_id=r2.id)
        # Coffee with a bag.
        bagged = _seed_coffee(db, name="CSV Bagged", roaster_id=r1.id)
        from datetime import date

        bag = _seed_bag(db, coffee_id=bagged.id, roast_date=date(2026, 5, 1))
        db.commit()
        uid = user.id
        bag_id = bag.id

    # Pre-seed an existing session to trigger the dedup-skip branch.
    dup_brewed_at = datetime(2026, 5, 10, 8, 0, 0, tzinfo=UTC)
    with SessionLocal() as db:
        from sqlalchemy import select

        from app.models.coffee import Coffee

        solo_id = db.execute(select(Coffee.id).where(Coffee.name == "CSV Solo")).scalar_one()
        brew_svc.create_brew_session(
            db,
            by_user_id=uid,
            coffee_id=solo_id,
            bag_id=None,
            recipe_id=None,
            brewer_id=None,
            grinder_id=None,
            kettle_id=None,
            water_type="",
            dose_grams_actual=Decimal("15"),
            water_grams_actual=Decimal("250"),
            yield_grams_actual=None,
            tds_pct=None,
            water_temp_c_actual=None,
            grind_setting_actual="",
            rating=None,
            flavor_note_ids_observed=[],
            notes="",
            brewed_at=dup_brewed_at,
        )

    fieldnames = [
        "coffee_name",
        "roaster_name",
        "roast_date",
        "dose_grams",
        "water_grams",
        "brewed_at",
    ]
    rows = [
        # 1. coffee not in catalog -> refused
        {
            "coffee_name": "CSV Nonexistent",
            "dose_grams": "15",
            "water_grams": "250",
            "brewed_at": "2026-05-11T08:00:00+00:00",
        },
        # 2. ambiguous coffee, no roaster -> refused
        {
            "coffee_name": "CSV Ambiguous",
            "dose_grams": "15",
            "water_grams": "250",
            "brewed_at": "2026-05-11T09:00:00+00:00",
        },
        # 3. duplicate of the pre-seeded session -> skipped
        {
            "coffee_name": "CSV Solo",
            "dose_grams": "15",
            "water_grams": "250",
            "brewed_at": "2026-05-10T08:00:00+00:00",
        },
        # 4. names a bag (roast_date) that does not resolve -> refused
        {
            "coffee_name": "CSV Bagged",
            "roast_date": "2099-01-01",
            "dose_grams": "15",
            "water_grams": "250",
            "brewed_at": "2026-05-11T10:00:00+00:00",
        },
        # 5. freestyle (no bag named) -> inserted
        {
            "coffee_name": "CSV Solo",
            "dose_grams": "16",
            "water_grams": "256",
            "brewed_at": "2026-05-11T11:00:00+00:00",
        },
        # 6. names a resolving bag -> inserted with bag_id
        {
            "coffee_name": "CSV Bagged",
            "roast_date": "2026-05-01",
            "dose_grams": "17",
            "water_grams": "272",
            "brewed_at": "2026-05-11T12:00:00+00:00",
        },
    ]
    raw = _csv(rows, fieldnames=fieldnames)

    with SessionLocal() as db:
        outcomes = csv_io.import_brews(db, raw_bytes=raw, by_user_id=uid)

    statuses = [o.status for o in outcomes]
    assert statuses == ["refused", "refused", "skipped", "refused", "inserted", "inserted"]
    assert "not in catalog" in outcomes[0].reason
    assert "ambiguous" in outcomes[1].reason
    assert "duplicate" in outcomes[2].reason
    assert "bag" in outcomes[3].reason.lower()

    # The two inserted rows landed; the bagged one carries the bag id.
    with SessionLocal() as db:
        rows_db = brew_svc.list_brew_sessions(db, by_user_id=uid)
    # 1 pre-seeded + 2 inserted = 3 total.
    assert len(rows_db) == 3
    bagged_rows = [r for r in rows_db if r.bag_id == bag_id]
    assert len(bagged_rows) == 1


def test_import_single_transaction(clean_csv: None, monkeypatch) -> None:
    """A forced DB error during the batch insert rolls back ALL accepted rows."""
    _require_postgres()
    _require_p5_migration_applied()
    from app.db import SessionLocal
    from app.services import brew_sessions as brew_svc
    from app.services import csv_io

    with SessionLocal() as db:
        user = _seed_user(db, username="csvtest-singletxn")
        r1 = _seed_roaster(db, name="CSV Roaster Txn")
        _seed_coffee(db, name="CSV TxnCoffee", roaster_id=r1.id)
        db.commit()
        uid = user.id

    fieldnames = ["coffee_name", "dose_grams", "water_grams", "brewed_at"]
    rows = [
        {
            "coffee_name": "CSV TxnCoffee",
            "dose_grams": "15",
            "water_grams": "250",
            "brewed_at": "2026-05-12T08:00:00+00:00",
        },
        {
            "coffee_name": "CSV TxnCoffee",
            "dose_grams": "16",
            "water_grams": "256",
            "brewed_at": "2026-05-12T09:00:00+00:00",
        },
    ]
    raw = _csv(rows, fieldnames=fieldnames)

    # Force the single commit to fail so the whole batch must roll back.
    from sqlalchemy.exc import OperationalError

    def _boom(self):  # noqa: ANN001, ANN202
        raise OperationalError("forced", {}, Exception("forced commit failure"))

    monkeypatch.setattr("sqlalchemy.orm.Session.commit", _boom)

    with SessionLocal() as db:
        with pytest.raises(Exception):  # noqa: B017, PT011
            csv_io.import_brews(db, raw_bytes=raw, by_user_id=uid)

    monkeypatch.undo()

    # Nothing committed.
    with SessionLocal() as db:
        rows_db = brew_svc.list_brew_sessions(db, by_user_id=uid)
    assert rows_db == []


def test_import_autocreates_observed_notes(clean_csv: None) -> None:
    """Observed flavor notes that don't exist are auto-created (category='other')
    inside the same transaction (D-09) and linked to the inserted session."""
    _require_postgres()
    _require_p5_migration_applied()
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models.flavor_note import FlavorNote
    from app.services import brew_sessions as brew_svc
    from app.services import csv_io

    with SessionLocal() as db:
        user = _seed_user(db, username="csvtest-notes")
        r1 = _seed_roaster(db, name="CSV Roaster Notes")
        _seed_coffee(db, name="CSV NotesCoffee", roaster_id=r1.id)
        # One note already exists (case-variant to prove citext link, not dup).
        existing = FlavorNote(name="csvnote-Blueberry", category="fruit")
        db.add(existing)
        db.commit()
        uid = user.id

    fieldnames = ["coffee_name", "dose_grams", "water_grams", "brewed_at", "observed_flavor_notes"]
    rows = [
        {
            "coffee_name": "CSV NotesCoffee",
            "dose_grams": "15",
            "water_grams": "250",
            "brewed_at": "2026-05-13T08:00:00+00:00",
            # one existing (case-variant), one brand new -> auto-create.
            "observed_flavor_notes": "csvnote-blueberry; csvnote-Jasmine",
        },
    ]
    raw = _csv(rows, fieldnames=fieldnames)

    with SessionLocal() as db:
        outcomes = csv_io.import_brews(db, raw_bytes=raw, by_user_id=uid)
    assert [o.status for o in outcomes] == ["inserted"]

    with SessionLocal() as db:
        notes = (
            db.execute(select(FlavorNote).where(FlavorNote.name.ilike("csvnote-%"))).scalars().all()
        )
        names = sorted(n.name.lower() for n in notes)
        # Existing blueberry reused (not duplicated) + new jasmine created.
        assert names == ["csvnote-blueberry", "csvnote-jasmine"]
        jasmine = next(n for n in notes if n.name.lower() == "csvnote-jasmine")
        assert jasmine.category == "other"

        rows_db = brew_svc.list_brew_sessions(db, by_user_id=uid)
        assert len(rows_db) == 1
        observed = set(rows_db[0].flavor_note_ids_observed)
        assert {n.id for n in notes} == observed
