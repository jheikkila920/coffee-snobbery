"""Service-layer tests for plan 05-02 Task 3 — brew_drafts upsert/get/clear.

Covers the ``<behavior>`` cases from the plan:

* ``upsert_draft`` twice for one user leaves exactly one row with the latest
  payload (one-draft-per-user, BREW-06/07).
* ``get_draft`` returns the stored payload; ``None`` for a user with no draft.
* ``clear_draft`` deletes the row; subsequent ``get_draft`` is ``None``; clear
  when none exists is a safe no-op (called on submit + logout, MX-5).
* A draft for user A is invisible to user B (per-user keying, T-05-08).

Real-Postgres skip-gate + clean-fixture shape from the sibling brew tests.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

# --------------------------------------------------------------------------- #
# Skip gates + seeding                                                        #
# --------------------------------------------------------------------------- #


def _require_postgres() -> None:
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — Phase 5 service test needs the DB")


def _require_p5_migration_applied() -> None:
    try:
        from sqlalchemy import text

        from app.db import engine
    except ImportError:
        pytest.skip("app.db not importable")
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT to_regclass('public.brew_drafts')")).scalar()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB unreachable: {exc.__class__.__name__}: {exc}")
    if row is None:
        pytest.skip("p5_brew_sessions migration not applied")


def _seed_user(db, *, username: str):
    from app.models.user import User

    user = User(username=username, password_hash="x" * 16, is_admin=False, is_active=True)
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def clean_drafts() -> Iterator[None]:
    """Wipe brew_drafts + the draft test users before AND after each test."""
    from sqlalchemy import text

    from app.db import engine

    def _reset() -> None:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM brew_drafts"))
            conn.execute(
                text(
                    "DELETE FROM sessions WHERE user_id IN "
                    "(SELECT id FROM users WHERE username LIKE 'draft-%')"
                )
            )
            conn.execute(text("DELETE FROM users WHERE username LIKE 'draft-%'"))

    _reset()
    yield
    _reset()


def _draft_row_count(db, user_id: int) -> int:
    from sqlalchemy import func, select

    from app.models.brew_draft import BrewDraft

    return db.execute(
        select(func.count()).select_from(BrewDraft).where(BrewDraft.user_id == user_id)
    ).scalar_one()


# --------------------------------------------------------------------------- #
# upsert idempotency to one row                                               #
# --------------------------------------------------------------------------- #


def test_upsert_keeps_one_row_latest_payload(clean_drafts: None) -> None:
    """Two upserts for the same user leave exactly one row with the latest payload."""
    _require_postgres()
    _require_p5_migration_applied()
    from app.db import SessionLocal
    from app.services import brew_drafts as svc

    with SessionLocal() as db:
        user = _seed_user(db, username="draft-upsert")
        db.commit()
        uid = user.id

    with SessionLocal() as db:
        svc.upsert_draft(db, by_user_id=uid, payload={"coffee_id": 1, "advanced_open": False})
    with SessionLocal() as db:
        svc.upsert_draft(db, by_user_id=uid, payload={"coffee_id": 2, "advanced_open": True})

    with SessionLocal() as db:
        assert _draft_row_count(db, uid) == 1
        stored = svc.get_draft(db, by_user_id=uid)
    assert stored == {"coffee_id": 2, "advanced_open": True}


def test_upsert_returns_row(clean_drafts: None) -> None:
    """upsert_draft returns the BrewDraft row carrying the payload."""
    _require_postgres()
    _require_p5_migration_applied()
    from app.db import SessionLocal
    from app.services import brew_drafts as svc

    with SessionLocal() as db:
        user = _seed_user(db, username="draft-ret")
        db.commit()
        uid = user.id

    with SessionLocal() as db:
        row = svc.upsert_draft(db, by_user_id=uid, payload={"notes": "wip"})
        assert row.user_id == uid
        assert row.payload == {"notes": "wip"}


# --------------------------------------------------------------------------- #
# get                                                                         #
# --------------------------------------------------------------------------- #


def test_get_draft_none_when_absent(clean_drafts: None) -> None:
    """get_draft returns None for a user with no draft."""
    _require_postgres()
    _require_p5_migration_applied()
    from app.db import SessionLocal
    from app.services import brew_drafts as svc

    with SessionLocal() as db:
        user = _seed_user(db, username="draft-absent")
        db.commit()
        uid = user.id

    with SessionLocal() as db:
        assert svc.get_draft(db, by_user_id=uid) is None


# --------------------------------------------------------------------------- #
# clear                                                                       #
# --------------------------------------------------------------------------- #


def test_clear_draft_deletes_then_none(clean_drafts: None) -> None:
    """clear_draft deletes the row; subsequent get_draft is None."""
    _require_postgres()
    _require_p5_migration_applied()
    from app.db import SessionLocal
    from app.services import brew_drafts as svc

    with SessionLocal() as db:
        user = _seed_user(db, username="draft-clear")
        db.commit()
        uid = user.id

    with SessionLocal() as db:
        svc.upsert_draft(db, by_user_id=uid, payload={"x": 1})
    with SessionLocal() as db:
        assert svc.get_draft(db, by_user_id=uid) == {"x": 1}

    with SessionLocal() as db:
        svc.clear_draft(db, by_user_id=uid)
    with SessionLocal() as db:
        assert svc.get_draft(db, by_user_id=uid) is None
        assert _draft_row_count(db, uid) == 0


def test_clear_draft_no_op_when_absent(clean_drafts: None) -> None:
    """clear_draft when none exists is a safe no-op."""
    _require_postgres()
    _require_p5_migration_applied()
    from app.db import SessionLocal
    from app.services import brew_drafts as svc

    with SessionLocal() as db:
        user = _seed_user(db, username="draft-noop")
        db.commit()
        uid = user.id

    with SessionLocal() as db:
        # Should not raise.
        svc.clear_draft(db, by_user_id=uid)
        assert svc.get_draft(db, by_user_id=uid) is None


# --------------------------------------------------------------------------- #
# per-user isolation (T-05-08)                                                #
# --------------------------------------------------------------------------- #


def test_draft_per_user_isolation(clean_drafts: None) -> None:
    """A draft for user A is invisible to user B; clearing A leaves B intact."""
    _require_postgres()
    _require_p5_migration_applied()
    from app.db import SessionLocal
    from app.services import brew_drafts as svc

    with SessionLocal() as db:
        user_a = _seed_user(db, username="draft-iso-a")
        user_b = _seed_user(db, username="draft-iso-b")
        db.commit()
        a_id, b_id = user_a.id, user_b.id

    with SessionLocal() as db:
        svc.upsert_draft(db, by_user_id=a_id, payload={"who": "a"})
        svc.upsert_draft(db, by_user_id=b_id, payload={"who": "b"})

    with SessionLocal() as db:
        assert svc.get_draft(db, by_user_id=a_id) == {"who": "a"}
        assert svc.get_draft(db, by_user_id=b_id) == {"who": "b"}

    # Clearing A's draft must not touch B's.
    with SessionLocal() as db:
        svc.clear_draft(db, by_user_id=a_id)
    with SessionLocal() as db:
        assert svc.get_draft(db, by_user_id=a_id) is None
        assert svc.get_draft(db, by_user_id=b_id) == {"who": "b"}
