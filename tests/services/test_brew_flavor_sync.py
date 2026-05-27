"""Service-layer unit tests for CATALOG-06 — _sync_coffee_flavor_notes helper.

Covers the diff/union algebra, idempotency, null-advertised handling,
and the no-commit guarantee.

Uses real Postgres via the _require_postgres skip gate + SessionLocal pattern.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

# --------------------------------------------------------------------------- #
# Skip gates                                                                   #
# --------------------------------------------------------------------------- #


def _require_postgres() -> None:
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — CATALOG-06 service test needs the DB")


def _require_migration_applied() -> None:
    try:
        from sqlalchemy import text

        from app.db import engine
    except ImportError:
        pytest.skip("app.db not importable")
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT to_regclass('public.coffees')")).scalar()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB unreachable: {exc.__class__.__name__}: {exc}")
    if row is None:
        pytest.skip("coffees table not present — migration not applied")


# --------------------------------------------------------------------------- #
# Seeding helpers + clean fixture                                               #
# --------------------------------------------------------------------------- #


def _seed_roaster(db) -> int:
    from app.models.roaster import Roaster

    r = Roaster(name="SyncTestRoaster")
    db.add(r)
    db.flush()
    return r.id


def _seed_coffee(db, *, roaster_id: int, advertised: list[int] | None = None) -> int:
    from app.models.coffee import Coffee

    c = Coffee(
        name="SyncTestCoffee",
        roaster_id=roaster_id,
        advertised_flavor_note_ids=advertised if advertised is not None else [],
    )
    db.add(c)
    db.flush()
    return c.id


def _seed_flavor_notes(db, count: int = 5) -> list[int]:
    from app.models.flavor_note import FlavorNote

    ids = []
    for i in range(count):
        fn = FlavorNote(name=f"SyncNote{i}", category="other")
        db.add(fn)
        db.flush()
        ids.append(fn.id)
    return ids


@pytest.fixture()
def clean_sync(sync_db) -> Iterator:  # type: ignore[no-untyped-def]
    """Wipe brew + catalog rows before and after each sync test."""
    yield sync_db
    try:
        from sqlalchemy import text

        sync_db.execute(text("DELETE FROM brew_sessions"))
        sync_db.execute(text("DELETE FROM coffees"))
        sync_db.execute(text("DELETE FROM flavor_notes"))
        sync_db.execute(text("DELETE FROM roasters"))
        sync_db.commit()
    except Exception:
        sync_db.rollback()


# --------------------------------------------------------------------------- #
# Tests                                                                         #
# --------------------------------------------------------------------------- #


def test_sync_adds_new_chips(clean_sync) -> None:
    """Chips present in the session but not in old set are unioned into advertised."""
    _require_postgres()
    _require_migration_applied()

    db = clean_sync
    from sqlalchemy import select

    from app.models.coffee import Coffee
    from app.services.brew_sessions import _sync_coffee_flavor_notes  # noqa: PLC2701

    r_id = _seed_roaster(db)
    note_ids = _seed_flavor_notes(db, 5)
    # advertised starts with notes 1 and 3 (index 1, 3)
    c_id = _seed_coffee(db, roaster_id=r_id, advertised=[note_ids[1], note_ids[3]])
    db.commit()

    # Session adds notes 0, 1, 2 (old=[])
    _sync_coffee_flavor_notes(
        db,
        coffee_id=c_id,
        old_session_ids=[],
        new_session_ids=[note_ids[0], note_ids[1], note_ids[2]],
    )
    db.commit()

    result = db.execute(select(Coffee.advertised_flavor_note_ids).where(Coffee.id == c_id)).scalar()
    # expected: union of {1,3} and {0,1,2} = {0,1,2,3}
    assert set(result) == {note_ids[0], note_ids[1], note_ids[2], note_ids[3]}


def test_sync_removes_chips_user_removed(clean_sync) -> None:
    """A chip removed from the session (was in old, not in new) is removed from advertised."""
    _require_postgres()
    _require_migration_applied()

    db = clean_sync
    from sqlalchemy import select

    from app.models.coffee import Coffee
    from app.services.brew_sessions import _sync_coffee_flavor_notes  # noqa: PLC2701

    r_id = _seed_roaster(db)
    note_ids = _seed_flavor_notes(db, 4)
    # advertised has all 4 notes
    c_id = _seed_coffee(db, roaster_id=r_id, advertised=note_ids[:])
    db.commit()

    # Old session had notes 0,1,2 — user removed note 1 (new=[0,2])
    _sync_coffee_flavor_notes(
        db,
        coffee_id=c_id,
        old_session_ids=[note_ids[0], note_ids[1], note_ids[2]],
        new_session_ids=[note_ids[0], note_ids[2]],
    )
    db.commit()

    result = db.execute(select(Coffee.advertised_flavor_note_ids).where(Coffee.id == c_id)).scalar()
    # note 1 was in old but not new → removed from advertised; note 3 stays (not touched)
    assert set(result) == {note_ids[0], note_ids[2], note_ids[3]}
    assert note_ids[1] not in result


def test_sync_idempotent_on_no_change(clean_sync) -> None:
    """Calling sync with old == new leaves advertised unchanged."""
    _require_postgres()
    _require_migration_applied()

    db = clean_sync
    from sqlalchemy import select

    from app.models.coffee import Coffee
    from app.services.brew_sessions import _sync_coffee_flavor_notes  # noqa: PLC2701

    r_id = _seed_roaster(db)
    note_ids = _seed_flavor_notes(db, 3)
    c_id = _seed_coffee(db, roaster_id=r_id, advertised=note_ids[:2])
    db.commit()

    before = set(note_ids[:2])
    _sync_coffee_flavor_notes(
        db,
        coffee_id=c_id,
        old_session_ids=note_ids[:2],
        new_session_ids=note_ids[:2],
    )
    db.commit()

    result = db.execute(select(Coffee.advertised_flavor_note_ids).where(Coffee.id == c_id)).scalar()
    assert set(result) == before


def test_sync_handles_null_advertised(clean_sync) -> None:
    """When coffee.advertised_flavor_note_ids is empty, treats it as empty set."""
    _require_postgres()
    _require_migration_applied()

    db = clean_sync
    from sqlalchemy import select, text

    from app.models.coffee import Coffee
    from app.services.brew_sessions import _sync_coffee_flavor_notes  # noqa: PLC2701

    r_id = _seed_roaster(db)
    note_ids = _seed_flavor_notes(db, 2)
    c_id = _seed_coffee(db, roaster_id=r_id, advertised=[])
    # Force advertised to empty array (the server_default handles this but be explicit)
    db.execute(
        text("UPDATE coffees SET advertised_flavor_note_ids = '{}' WHERE id = :id"),
        {"id": c_id},
    )
    db.commit()

    _sync_coffee_flavor_notes(
        db,
        coffee_id=c_id,
        old_session_ids=[],
        new_session_ids=note_ids,
    )
    db.commit()

    result = db.execute(select(Coffee.advertised_flavor_note_ids).where(Coffee.id == c_id)).scalar()
    assert set(result) == set(note_ids)


def test_sync_does_not_commit_caller_responsibility(clean_sync) -> None:
    """_sync_coffee_flavor_notes must NOT call db.commit() itself.

    We verify by monkey-patching db.commit to a sentinel and asserting it
    is not called during the helper invocation.
    """
    _require_postgres()
    _require_migration_applied()

    db = clean_sync
    from app.services.brew_sessions import _sync_coffee_flavor_notes  # noqa: PLC2701

    r_id = _seed_roaster(db)
    note_ids = _seed_flavor_notes(db, 2)
    c_id = _seed_coffee(db, roaster_id=r_id, advertised=[])
    db.commit()

    commit_called = []
    original_commit = db.commit

    def _spy_commit() -> None:
        commit_called.append(True)
        original_commit()

    db.commit = _spy_commit  # type: ignore[method-assign]

    _sync_coffee_flavor_notes(
        db,
        coffee_id=c_id,
        old_session_ids=[],
        new_session_ids=note_ids,
    )

    db.commit = original_commit  # restore
    # Helper must NOT have called commit
    assert commit_called == [], "_sync_coffee_flavor_notes must not commit; caller is responsible"
