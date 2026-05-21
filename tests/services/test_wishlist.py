"""Wishlist service tests (Phase 7, Plan 02).

Covers the ``<behavior>`` cases from 07-02-PLAN.md:

* ``add_to_wishlist`` creates a user-scoped row with source defaulting to
  "ai_recommendation" and returns the new entry.
* ``list_wishlist`` returns only the calling user's rows, newest first.
* ``get_wishlist_entry`` returns None for a cross-user entry_id (IDOR sentinel).
* ``mark_purchased`` sets ``purchased_at`` for the owner; returns None for a
  cross-user id and leaves the row unmodified.
* ``remove_entry`` returns False and leaves the row intact for a cross-user id;
  returns True and deletes the row for the owner.

Mirrors the structural shape of tests/services/test_brew_sessions_service.py:
real Postgres via skip gates, SessionLocal context-manager pattern, and a
``clean_wishlist`` fixture that wipes Phase-7 wishlist rows around each test.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest


# --------------------------------------------------------------------------- #
# Skip gates (mirror tests/services/test_brew_sessions_service.py)            #
# --------------------------------------------------------------------------- #


def _require_postgres() -> None:
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — wishlist service test needs the DB")


def _require_wishlist_table() -> None:
    try:
        from sqlalchemy import text

        from app.db import engine
    except ImportError:
        pytest.skip("app.db not importable")
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT to_regclass('public.wishlist_entries')")).scalar()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB unreachable: {exc.__class__.__name__}: {exc}")
    if row is None:
        pytest.skip("wishlist_entries table not found — migration not applied")


# --------------------------------------------------------------------------- #
# Seeding helpers + clean fixture                                              #
# --------------------------------------------------------------------------- #


def _seed_user(db, *, username: str):
    """Insert a minimal User row (FK target for wishlist_entries.user_id)."""
    from app.models.user import User

    user = User(username=username, password_hash="x" * 16, is_admin=False, is_active=True)
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def clean_wishlist() -> Iterator[None]:
    """Wipe wishlist rows + test users before AND after each test."""
    from sqlalchemy import text

    from app.db import engine

    def _reset() -> None:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM wishlist_entries"))
            conn.execute(
                text(
                    "DELETE FROM sessions WHERE user_id IN "
                    "(SELECT id FROM users WHERE username LIKE 'wltest-%')"
                )
            )
            conn.execute(text("DELETE FROM users WHERE username LIKE 'wltest-%'"))

    _reset()
    yield
    _reset()


# --------------------------------------------------------------------------- #
# Tests                                                                       #
# --------------------------------------------------------------------------- #


def test_add_and_list_scoped_to_user(clean_wishlist: None) -> None:
    """add_to_wishlist creates a row for the given user; list_wishlist returns
    only that user's rows (not another user's)."""
    _require_postgres()
    _require_wishlist_table()
    from app.db import SessionLocal
    from app.services import wishlist as svc

    with SessionLocal() as db:
        user_a = _seed_user(db, username="wltest-a1")
        user_b = _seed_user(db, username="wltest-b1")
        db.commit()
        uid_a, uid_b = user_a.id, user_b.id

    with SessionLocal() as db:
        svc.add_to_wishlist(db, by_user_id=uid_a, coffee_name="Kenya AA", roaster_name="Blue Bottle", source_url=None)
        svc.add_to_wishlist(db, by_user_id=uid_a, coffee_name="Ethiopia Yirgacheffe", roaster_name=None, source_url=None)
        svc.add_to_wishlist(db, by_user_id=uid_b, coffee_name="Colombia Huila", roaster_name="Stumptown", source_url=None)

    with SessionLocal() as db:
        entries_a = svc.list_wishlist(db, by_user_id=uid_a)
        entries_b = svc.list_wishlist(db, by_user_id=uid_b)

    assert len(entries_a) == 2
    assert len(entries_b) == 1
    assert all(e.user_id == uid_a for e in entries_a)
    assert entries_b[0].user_id == uid_b
    assert entries_b[0].coffee_name == "Colombia Huila"


def test_list_order_newest_first(clean_wishlist: None) -> None:
    """list_wishlist returns entries ordered by added_at desc (newest first)."""
    _require_postgres()
    _require_wishlist_table()
    import time

    from app.db import SessionLocal
    from app.services import wishlist as svc

    with SessionLocal() as db:
        user = _seed_user(db, username="wltest-order")
        db.commit()
        uid = user.id

    # Insert with tiny sleeps to guarantee distinct added_at timestamps
    with SessionLocal() as db:
        svc.add_to_wishlist(db, by_user_id=uid, coffee_name="First", roaster_name=None, source_url=None)
    time.sleep(0.05)
    with SessionLocal() as db:
        svc.add_to_wishlist(db, by_user_id=uid, coffee_name="Second", roaster_name=None, source_url=None)
    time.sleep(0.05)
    with SessionLocal() as db:
        svc.add_to_wishlist(db, by_user_id=uid, coffee_name="Third", roaster_name=None, source_url=None)

    with SessionLocal() as db:
        entries = svc.list_wishlist(db, by_user_id=uid)

    assert [e.coffee_name for e in entries] == ["Third", "Second", "First"]


def test_add_defaults_source_ai_recommendation(clean_wishlist: None) -> None:
    """add_to_wishlist defaults source to 'ai_recommendation' (D-09)."""
    _require_postgres()
    _require_wishlist_table()
    from app.db import SessionLocal
    from app.services import wishlist as svc

    with SessionLocal() as db:
        user = _seed_user(db, username="wltest-src")
        db.commit()
        uid = user.id

    with SessionLocal() as db:
        entry = svc.add_to_wishlist(db, by_user_id=uid, coffee_name="Sumatra", roaster_name=None, source_url=None)
        eid = entry.id

    with SessionLocal() as db:
        fetched = svc.get_wishlist_entry(db, entry_id=eid, by_user_id=uid)
    assert fetched is not None
    assert fetched.source == "ai_recommendation"


def test_get_wishlist_entry_cross_user_returns_none(clean_wishlist: None) -> None:
    """get_wishlist_entry returns None when entry_id belongs to a different user (IDOR sentinel)."""
    _require_postgres()
    _require_wishlist_table()
    from app.db import SessionLocal
    from app.services import wishlist as svc

    with SessionLocal() as db:
        user_a = _seed_user(db, username="wltest-idor-a")
        user_b = _seed_user(db, username="wltest-idor-b")
        db.commit()
        uid_a, uid_b = user_a.id, user_b.id

    with SessionLocal() as db:
        entry = svc.add_to_wishlist(db, by_user_id=uid_a, coffee_name="Burundi", roaster_name=None, source_url=None)
        eid = entry.id

    with SessionLocal() as db:
        # User B tries to access user A's entry — must get None
        result = svc.get_wishlist_entry(db, entry_id=eid, by_user_id=uid_b)
    assert result is None

    with SessionLocal() as db:
        # Sanity: user A can still retrieve it
        result = svc.get_wishlist_entry(db, entry_id=eid, by_user_id=uid_a)
    assert result is not None


def test_mark_purchased_sets_timestamp(clean_wishlist: None) -> None:
    """mark_purchased sets purchased_at to a non-null timestamp for the owner."""
    _require_postgres()
    _require_wishlist_table()
    from app.db import SessionLocal
    from app.services import wishlist as svc

    with SessionLocal() as db:
        user = _seed_user(db, username="wltest-purch")
        db.commit()
        uid = user.id

    with SessionLocal() as db:
        entry = svc.add_to_wishlist(db, by_user_id=uid, coffee_name="Panama Geisha", roaster_name=None, source_url=None)
        eid = entry.id

    with SessionLocal() as db:
        result = svc.mark_purchased(db, entry_id=eid, by_user_id=uid)
    assert result is not None
    assert result.purchased_at is not None


def test_mark_purchased_cross_user_none(clean_wishlist: None) -> None:
    """mark_purchased returns None for a cross-user id; purchased_at stays null."""
    _require_postgres()
    _require_wishlist_table()
    from app.db import SessionLocal
    from app.services import wishlist as svc

    with SessionLocal() as db:
        user_a = _seed_user(db, username="wltest-purch-a")
        user_b = _seed_user(db, username="wltest-purch-b")
        db.commit()
        uid_a, uid_b = user_a.id, user_b.id

    with SessionLocal() as db:
        entry = svc.add_to_wishlist(db, by_user_id=uid_a, coffee_name="Rwanda", roaster_name=None, source_url=None)
        eid = entry.id

    with SessionLocal() as db:
        # User B tries to mark user A's entry — must return None
        result = svc.mark_purchased(db, entry_id=eid, by_user_id=uid_b)
    assert result is None

    with SessionLocal() as db:
        # Confirm the row is unchanged
        fetched = svc.get_wishlist_entry(db, entry_id=eid, by_user_id=uid_a)
    assert fetched is not None
    assert fetched.purchased_at is None


def test_remove_cross_user_false_keeps_row(clean_wishlist: None) -> None:
    """remove_entry returns False for a cross-user id; the row still exists."""
    _require_postgres()
    _require_wishlist_table()
    from app.db import SessionLocal
    from app.services import wishlist as svc

    with SessionLocal() as db:
        user_a = _seed_user(db, username="wltest-rm-a")
        user_b = _seed_user(db, username="wltest-rm-b")
        db.commit()
        uid_a, uid_b = user_a.id, user_b.id

    with SessionLocal() as db:
        entry = svc.add_to_wishlist(db, by_user_id=uid_a, coffee_name="Tanzania Peaberry", roaster_name=None, source_url=None)
        eid = entry.id

    with SessionLocal() as db:
        result = svc.remove_entry(db, entry_id=eid, by_user_id=uid_b)
    assert result is False

    with SessionLocal() as db:
        fetched = svc.get_wishlist_entry(db, entry_id=eid, by_user_id=uid_a)
    assert fetched is not None, "Row must survive a cross-user delete attempt"


def test_remove_owner_true(clean_wishlist: None) -> None:
    """remove_entry returns True for the owner and the row no longer exists."""
    _require_postgres()
    _require_wishlist_table()
    from app.db import SessionLocal
    from app.services import wishlist as svc

    with SessionLocal() as db:
        user = _seed_user(db, username="wltest-rm-owner")
        db.commit()
        uid = user.id

    with SessionLocal() as db:
        entry = svc.add_to_wishlist(db, by_user_id=uid, coffee_name="Costa Rica", roaster_name=None, source_url=None)
        eid = entry.id

    with SessionLocal() as db:
        result = svc.remove_entry(db, entry_id=eid, by_user_id=uid)
    assert result is True

    with SessionLocal() as db:
        fetched = svc.get_wishlist_entry(db, entry_id=eid, by_user_id=uid)
    assert fetched is None, "Row must be gone after owner removes it"
