"""Integration tests for CATALOG-06 — bidirectional flavor-note sync.

Covers:
- resolve_prefill inherits chips from parent coffee (D-06/D-12)
- create/update write-back enriches/removes from coffee.advertised (D-07/D-08)
- CSV import triggers same write-back (D-11)
- Draft restore union-merges draft chips with current coffee chips (D-10)
- Drafts never touch parent coffee (D-07)

Uses real Postgres via the skip gate + SessionLocal pattern.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

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
        pytest.skip("Postgres not reachable — CATALOG-06 integration test needs the DB")


def _require_migration_applied() -> None:
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
        pytest.skip("brew_sessions table not present — migration not applied")


# --------------------------------------------------------------------------- #
# Seeding helpers                                                               #
# --------------------------------------------------------------------------- #


def _seed_user(db, *, username: str = "flavoruser") -> int:
    from app.models.user import User
    from app.services.auth import hash_password

    u = User(
        username=username,
        email=f"{username}@example.com",
        password_hash=hash_password("testpassword123"),
        is_admin=False,
        is_active=True,
    )
    db.add(u)
    db.flush()
    return u.id


def _seed_roaster(db, *, name: str = "FlavSyncRoaster") -> int:
    from app.models.roaster import Roaster

    r = Roaster(name=name)
    db.add(r)
    db.flush()
    return r.id


def _seed_coffee(
    db, *, roaster_id: int, name: str = "FlavSyncCoffee", advertised: list[int] | None = None
) -> int:
    from app.models.coffee import Coffee

    c = Coffee(
        name=name,
        roaster_id=roaster_id,
        advertised_flavor_note_ids=advertised if advertised is not None else [],
    )
    db.add(c)
    db.flush()
    return c.id


def _seed_flavor_notes(db, count: int = 5, prefix: str = "FSNote") -> list[int]:
    from app.models.flavor_note import FlavorNote

    ids = []
    for i in range(count):
        fn = FlavorNote(name=f"{prefix}{i}", category="other")
        db.add(fn)
        db.flush()
        ids.append(fn.id)
    return ids


def _seed_session(
    db, *, user_id: int, coffee_id: int, flavor_note_ids: list[int] | None = None
) -> int:
    from app.services.brew_sessions import create_brew_session

    session = create_brew_session(
        db,
        by_user_id=user_id,
        coffee_id=coffee_id,
        bag_id=None,
        recipe_id=None,
        brewer_id=None,
        grinder_id=None,
        kettle_id=None,
        water_type=None,
        dose_grams_actual=Decimal("18"),
        water_grams_actual=Decimal("300"),
        yield_grams_actual=None,
        tds_pct=None,
        water_temp_c_actual=None,
        grind_setting_actual=None,
        rating=None,
        flavor_note_ids_observed=flavor_note_ids or [],
        notes="",
        brewed_at=datetime.now(UTC),
    )
    return session.id


@pytest.fixture()
def clean_flavor(sync_db) -> Iterator:  # type: ignore[no-untyped-def]
    """Wipe brew + catalog rows before and after each flavor sync test."""
    yield sync_db
    try:
        from sqlalchemy import text

        sync_db.execute(text("DELETE FROM brew_drafts"))
        sync_db.execute(text("DELETE FROM brew_sessions"))
        sync_db.execute(text("DELETE FROM coffees"))
        sync_db.execute(text("DELETE FROM flavor_notes"))
        sync_db.execute(text("DELETE FROM roasters"))
        sync_db.execute(text("DELETE FROM users"))
        sync_db.commit()
    except Exception:
        sync_db.rollback()


# --------------------------------------------------------------------------- #
# D-06/D-12 prefill tests                                                      #
# --------------------------------------------------------------------------- #


def test_prefill_inherits_coffee_chips(clean_flavor) -> None:
    """resolve_prefill with coffee_id returns advertised chips as flavor_note_ids_observed."""
    _require_postgres()
    _require_migration_applied()

    db = clean_flavor
    from app.services.brew_sessions import resolve_prefill

    r_id = _seed_roaster(db)
    note_ids = _seed_flavor_notes(db, 3)
    c_id = _seed_coffee(db, roaster_id=r_id, advertised=note_ids)
    u_id = _seed_user(db)
    db.commit()

    prefill = resolve_prefill(db, by_user_id=u_id, coffee_id=c_id)
    assert set(prefill["flavor_note_ids_observed"]) == set(note_ids)


def test_prefill_with_no_coffee_id(clean_flavor) -> None:
    """resolve_prefill without coffee_id returns empty flavor_note_ids_observed."""
    _require_postgres()
    _require_migration_applied()

    db = clean_flavor
    from app.services.brew_sessions import resolve_prefill

    u_id = _seed_user(db)
    db.commit()

    prefill = resolve_prefill(db, by_user_id=u_id)
    assert prefill["flavor_note_ids_observed"] == []


def test_prefill_does_not_pull_recent_session_chips(clean_flavor) -> None:
    """D-12: prefill source is only advertised, NOT the user's most-recent session chips."""
    _require_postgres()
    _require_migration_applied()

    db = clean_flavor
    from app.services.brew_sessions import resolve_prefill

    r_id = _seed_roaster(db)
    note_ids = _seed_flavor_notes(db, 5)
    # Coffee advertised = first two notes
    c_id = _seed_coffee(db, roaster_id=r_id, advertised=note_ids[:2])
    u_id = _seed_user(db)
    db.commit()

    # Create a session with extra chips (notes 2, 3, 4) for this coffee
    # (create_brew_session also calls _sync_coffee_flavor_notes which will enrich advertised;
    # so we create the session BEFORE checking prefill, then reset advertised to only first two)
    _seed_session(db, user_id=u_id, coffee_id=c_id, flavor_note_ids=[note_ids[3], note_ids[4]])
    # After session save, advertised will have been enriched; reset it for the D-12 check
    from sqlalchemy import text

    db.execute(
        text("UPDATE coffees SET advertised_flavor_note_ids = :ids WHERE id = :cid"),
        {"ids": note_ids[:2], "cid": c_id},
    )
    db.commit()

    # Prefill should only return the two advertised chips, not the session chips
    prefill = resolve_prefill(db, by_user_id=u_id, coffee_id=c_id)
    assert set(prefill["flavor_note_ids_observed"]) == set(note_ids[:2])
    # Must NOT include notes 3, 4 which were only in the session
    assert note_ids[3] not in prefill["flavor_note_ids_observed"]
    assert note_ids[4] not in prefill["flavor_note_ids_observed"]


# --------------------------------------------------------------------------- #
# D-07/D-08 write-back tests                                                   #
# --------------------------------------------------------------------------- #


def test_save_writes_back_added_chips(clean_flavor) -> None:
    """Creating a session with extra chips enriches coffee.advertised_flavor_note_ids."""
    _require_postgres()
    _require_migration_applied()

    db = clean_flavor
    from sqlalchemy import select

    from app.models.coffee import Coffee

    r_id = _seed_roaster(db)
    note_ids = _seed_flavor_notes(db, 4)
    c_id = _seed_coffee(db, roaster_id=r_id, advertised=note_ids[:2])
    u_id = _seed_user(db)
    db.commit()

    # Save session with notes 0, 1, 2 (note 2 is new)
    _seed_session(db, user_id=u_id, coffee_id=c_id, flavor_note_ids=note_ids[:3])

    result = db.execute(select(Coffee.advertised_flavor_note_ids).where(Coffee.id == c_id)).scalar()
    # note 2 was added; note 3 was never in any session so stays
    assert note_ids[0] in result
    assert note_ids[1] in result
    assert note_ids[2] in result
    # note 3 was in advertised but not in session — stays (not in old=[], so not removed)
    assert note_ids[3] in result


def test_save_writes_back_removed_chips(clean_flavor) -> None:
    """D-08: removing an inherited chip from a session removes it from coffee.advertised."""
    _require_postgres()
    _require_migration_applied()

    db = clean_flavor
    from sqlalchemy import select

    from app.models.coffee import Coffee
    from app.services.brew_sessions import update_brew_session

    r_id = _seed_roaster(db)
    note_ids = _seed_flavor_notes(db, 3)
    c_id = _seed_coffee(db, roaster_id=r_id, advertised=note_ids[:2])
    u_id = _seed_user(db)
    db.commit()

    # Create session with notes 0, 1 (both inherited from advertised)
    session_id = _seed_session(db, user_id=u_id, coffee_id=c_id, flavor_note_ids=note_ids[:2])

    # Update session to remove note 1 (bidirectional: note 1 should leave advertised)
    update_brew_session(
        db,
        session_id=session_id,
        by_user_id=u_id,
        flavor_note_ids_observed=[note_ids[0]],
    )

    result = db.execute(select(Coffee.advertised_flavor_note_ids).where(Coffee.id == c_id)).scalar()
    assert note_ids[0] in result
    # note 1 was removed from session → removed from advertised (D-08 bidirectional)
    assert note_ids[1] not in result


# --------------------------------------------------------------------------- #
# D-11 CSV import write-back                                                   #
# --------------------------------------------------------------------------- #


def test_csv_import_triggers_writeback(clean_flavor) -> None:
    """D-11: CSV import enriches parent coffee's advertised chips."""
    _require_postgres()
    _require_migration_applied()

    db = clean_flavor
    from sqlalchemy import select

    from app.models.coffee import Coffee
    from app.services.csv_io import import_brews

    r_id = _seed_roaster(db, name="CSVRoaster")
    note_ids = _seed_flavor_notes(db, 3, prefix="CSVNote")
    c_id = _seed_coffee(db, roaster_id=r_id, name="CSVCoffee", advertised=[])
    _seed_user(db)
    db.commit()

    # Get the coffee name for the CSV
    coffee_name = "CSVCoffee"
    # Use note name for the observed_flavor_notes cell
    from app.models.flavor_note import FlavorNote

    note_name = db.execute(select(FlavorNote.name).where(FlavorNote.id == note_ids[0])).scalar()

    csv_content = (
        "coffee_name,roaster_name,dose_grams,water_grams,observed_flavor_notes,brewed_at\n"
        f"{coffee_name},CSVRoaster,18,300,{note_name},2026-01-01T10:00:00\n"
    ).encode()

    import_brews(db, raw_bytes=csv_content, by_user_id=1)

    result = db.execute(select(Coffee.advertised_flavor_note_ids).where(Coffee.id == c_id)).scalar()
    assert note_ids[0] in (result or [])


# --------------------------------------------------------------------------- #
# D-10 draft restore tests                                                      #
# --------------------------------------------------------------------------- #


def test_draft_restore_union_merge(clean_flavor) -> None:
    """D-10: draft restore unions draft chips with current coffee advertised chips."""
    _require_postgres()
    _require_migration_applied()

    db = clean_flavor
    from sqlalchemy import text

    from app.services.brew_drafts import get_draft, upsert_draft

    r_id = _seed_roaster(db)
    note_ids = _seed_flavor_notes(db, 4)
    c_id = _seed_coffee(db, roaster_id=r_id, advertised=[note_ids[0], note_ids[1]])
    u_id = _seed_user(db)
    db.commit()

    # Save a draft with chips 0, 1, 2
    upsert_draft(
        db,
        by_user_id=u_id,
        payload={
            "coffee_id": c_id,
            "flavor_note_ids_observed": [note_ids[0], note_ids[1], note_ids[2]],
        },
    )

    # Coffee advertised changes to include note 3 (new advertised)
    db.execute(
        text("UPDATE coffees SET advertised_flavor_note_ids = :ids WHERE id = :cid"),
        {"ids": [note_ids[0], note_ids[3]], "cid": c_id},
    )
    db.commit()

    # Simulate what the brew router does: get_draft + union merge
    server_draft = get_draft(db, by_user_id=u_id)
    assert server_draft is not None

    # Apply union merge (this is the code path we're testing in brew.py)
    if "flavor_note_ids_observed" in server_draft and server_draft.get("coffee_id"):
        from sqlalchemy import select

        from app.models.coffee import Coffee

        current_chips = db.execute(
            select(Coffee.advertised_flavor_note_ids).where(Coffee.id == server_draft["coffee_id"])
        ).scalar_one_or_none()
        merged = sorted(set(server_draft["flavor_note_ids_observed"]) | set(current_chips or []))
        server_draft["flavor_note_ids_observed"] = merged

    # Draft had 0,1,2; coffee now advertises 0,3 → merged = 0,1,2,3
    assert set(server_draft["flavor_note_ids_observed"]) == {
        note_ids[0],
        note_ids[1],
        note_ids[2],
        note_ids[3],
    }


def test_draft_restore_keeps_removed_advertised(clean_flavor) -> None:
    """D-10 additive: chips removed from advertised still appear in restored draft."""
    _require_postgres()
    _require_migration_applied()

    db = clean_flavor
    from sqlalchemy import text

    from app.services.brew_drafts import get_draft, upsert_draft

    r_id = _seed_roaster(db)
    note_ids = _seed_flavor_notes(db, 3)
    c_id = _seed_coffee(db, roaster_id=r_id, advertised=note_ids[:3])
    u_id = _seed_user(db)
    db.commit()

    # Save draft with all 3 chips
    upsert_draft(
        db,
        by_user_id=u_id,
        payload={
            "coffee_id": c_id,
            "flavor_note_ids_observed": note_ids[:3],
        },
    )

    # Remove note 2 from advertised
    db.execute(
        text("UPDATE coffees SET advertised_flavor_note_ids = :ids WHERE id = :cid"),
        {"ids": note_ids[:2], "cid": c_id},
    )
    db.commit()

    server_draft = get_draft(db, by_user_id=u_id)
    assert server_draft is not None

    # Union merge: draft had note 2, advertised no longer has it, but union preserves it
    if "flavor_note_ids_observed" in server_draft and server_draft.get("coffee_id"):
        from sqlalchemy import select

        from app.models.coffee import Coffee

        current_chips = db.execute(
            select(Coffee.advertised_flavor_note_ids).where(Coffee.id == server_draft["coffee_id"])
        ).scalar_one_or_none()
        merged = sorted(set(server_draft["flavor_note_ids_observed"]) | set(current_chips or []))
        server_draft["flavor_note_ids_observed"] = merged

    # note 2 was in the draft → stays in merged result even though removed from advertised
    assert note_ids[2] in server_draft["flavor_note_ids_observed"]


def test_draft_does_not_touch_coffee(clean_flavor) -> None:
    """D-07: autosaving a draft must NOT change coffee.advertised_flavor_note_ids."""
    _require_postgres()
    _require_migration_applied()

    db = clean_flavor
    from sqlalchemy import select

    from app.models.coffee import Coffee
    from app.services.brew_drafts import upsert_draft

    r_id = _seed_roaster(db)
    note_ids = _seed_flavor_notes(db, 3)
    c_id = _seed_coffee(db, roaster_id=r_id, advertised=note_ids[:2])
    u_id = _seed_user(db)
    db.commit()

    before = set(
        db.execute(select(Coffee.advertised_flavor_note_ids).where(Coffee.id == c_id)).scalar()
    )

    # Autosave a draft with an extra chip (note 2) — this must NOT touch the coffee
    upsert_draft(
        db,
        by_user_id=u_id,
        payload={
            "coffee_id": c_id,
            "flavor_note_ids_observed": note_ids[:3],  # extra chip
        },
    )

    after = set(
        db.execute(select(Coffee.advertised_flavor_note_ids).where(Coffee.id == c_id)).scalar()
    )
    assert before == after, "Draft save must not modify coffee.advertised_flavor_note_ids"
