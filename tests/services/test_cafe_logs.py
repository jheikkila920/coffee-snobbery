"""Service-layer tests for plan 16-02 Task 1 — cafe_logs CRUD.

Covers the ``<behavior>`` cases from the plan:

* ``create_cafe_log`` writes a per-user row scoped by ``by_user_id``.
* ``get_cafe_log`` returns ``None`` for another user's log (IDOR sentinel).
* ``list_cafe_logs`` filters by rating range and date range; sorts DESC.
* ``update_cafe_log`` mutates the row for the owner and returns ``None``
  for a cross-user attempt without mutation.
* ``delete_cafe_log`` removes the owner's row and returns ``False`` without
  deletion for a cross-user attempt.

Mirrors the structural shape of ``tests/services/test_brew_sessions_service.py``:
real Postgres via the ``_require_postgres`` + ``_require_cafe_logs_table``
skip gates, the ``SessionLocal`` context-manager pattern, and a ``clean_cafe``
fixture that wipes this test's own rows before and after each test.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
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
        pytest.skip("Postgres not reachable — Phase 16 service test needs the DB")


def _require_cafe_logs_table() -> None:
    """Skip if the cafe_logs table is not present (p16_cafe_logs migration)."""
    try:
        from tests.conftest import _require_cafe_logs_table as _gate
    except ImportError:
        pytest.skip("_require_cafe_logs_table not importable from conftest")
    _gate()


# --------------------------------------------------------------------------- #
# Seeding helpers + clean fixture                                              #
# --------------------------------------------------------------------------- #


def _seed_user(db: object, *, username: str) -> object:
    """Insert a minimal User row (RESTRICT FK target for cafe_logs)."""
    from app.models.user import User

    user = User(username=username, password_hash="x" * 16, is_admin=False, is_active=True)
    db.add(user)
    db.flush()
    return user


_TEST_USERNAME_PREFIX = "cafe_svc_test_"


@pytest.fixture
def clean_cafe() -> Iterator[None]:
    """Wipe this test's cafe_logs rows + the seeded test users before AND after."""
    from sqlalchemy import text

    from app.db import engine

    def _reset() -> None:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM cafe_logs"))
            conn.execute(text(f"DELETE FROM users WHERE username LIKE '{_TEST_USERNAME_PREFIX}%'"))

    _reset()
    yield
    _reset()


# --------------------------------------------------------------------------- #
# Tests                                                                        #
# --------------------------------------------------------------------------- #


def test_create_cafe_log_minimal(clean_cafe: None) -> None:
    """create_cafe_log with only cafe_name + rating produces a valid row."""
    _require_postgres()
    _require_cafe_logs_table()
    from app.db import SessionLocal
    from app.services.cafe_logs import create_cafe_log

    with SessionLocal() as db:
        user = _seed_user(db, username=f"{_TEST_USERNAME_PREFIX}create_min")
        db.commit()
        uid = user.id

    with SessionLocal() as db:
        row = create_cafe_log(
            db,
            by_user_id=uid,
            cafe_name="Onyx",
            rating=Decimal("4.0"),
            roaster_id=None,
            origin_country=None,
            brew_method=None,
            flavor_note_ids=[],
            notes="",
            photo_filename=None,
            logged_at=None,
        )
        assert row.id is not None
        assert row.user_id == uid
        assert row.cafe_name == "Onyx"
        assert row.rating == Decimal("4.0")
        assert row.flavor_note_ids == []
        assert row.logged_at is not None


def test_create_cafe_log_full_enrichment(clean_cafe: None) -> None:
    """create_cafe_log with all fields stores all enrichment values."""
    _require_postgres()
    _require_cafe_logs_table()
    from app.db import SessionLocal
    from app.services.cafe_logs import create_cafe_log

    with SessionLocal() as db:
        user = _seed_user(db, username=f"{_TEST_USERNAME_PREFIX}create_full")
        db.commit()
        uid = user.id

    logged = datetime(2025, 1, 15, 10, 30, tzinfo=UTC)
    with SessionLocal() as db:
        row = create_cafe_log(
            db,
            by_user_id=uid,
            cafe_name="Counter Culture Hologram",
            rating=Decimal("4.75"),
            roaster_id=None,
            origin_country="Ethiopia",
            brew_method="Pour-over",
            flavor_note_ids=[],
            notes="Floral and bright",
            photo_filename=None,
            logged_at=logged,
        )
        assert row.cafe_name == "Counter Culture Hologram"
        assert row.rating == Decimal("4.75")
        assert row.origin_country == "Ethiopia"
        assert row.brew_method == "Pour-over"
        assert row.notes == "Floral and bright"


def test_get_cafe_log_owner_returns_row(clean_cafe: None) -> None:
    """Owner read returns the row."""
    _require_postgres()
    _require_cafe_logs_table()
    from app.db import SessionLocal
    from app.services.cafe_logs import create_cafe_log, get_cafe_log

    with SessionLocal() as db:
        user = _seed_user(db, username=f"{_TEST_USERNAME_PREFIX}get_owner")
        db.commit()
        uid = user.id

    with SessionLocal() as db:
        row = create_cafe_log(
            db,
            by_user_id=uid,
            cafe_name="TestCafe",
            rating=Decimal("4.0"),
            roaster_id=None,
            origin_country=None,
            brew_method=None,
            flavor_note_ids=[],
            notes="",
            photo_filename=None,
            logged_at=None,
        )
        row_id = row.id

    with SessionLocal() as db:
        found = get_cafe_log(db, cafe_log_id=row_id, by_user_id=uid)
        assert found is not None
        assert found.id == row_id


def test_get_cafe_log_cross_user_returns_none(clean_cafe: None) -> None:
    """IDOR sentinel — cross-user read returns None."""
    _require_postgres()
    _require_cafe_logs_table()
    from app.db import SessionLocal
    from app.services.cafe_logs import create_cafe_log, get_cafe_log

    with SessionLocal() as db:
        owner = _seed_user(db, username=f"{_TEST_USERNAME_PREFIX}idor_owner")
        other = _seed_user(db, username=f"{_TEST_USERNAME_PREFIX}idor_other")
        db.commit()
        owner_id = owner.id
        other_id = other.id

    with SessionLocal() as db:
        row = create_cafe_log(
            db,
            by_user_id=owner_id,
            cafe_name="OwnerCafe",
            rating=Decimal("3.5"),
            roaster_id=None,
            origin_country=None,
            brew_method=None,
            flavor_note_ids=[],
            notes="",
            photo_filename=None,
            logged_at=None,
        )
        row_id = row.id

    with SessionLocal() as db:
        result = get_cafe_log(db, cafe_log_id=row_id, by_user_id=other_id)
        assert result is None


def test_list_cafe_logs_rating_filter(clean_cafe: None) -> None:
    """rating_min=4.0 filters out rows with rating < 4.0."""
    _require_postgres()
    _require_cafe_logs_table()
    from app.db import SessionLocal
    from app.services.cafe_logs import create_cafe_log, list_cafe_logs

    with SessionLocal() as db:
        user = _seed_user(db, username=f"{_TEST_USERNAME_PREFIX}rating_filter")
        db.commit()
        uid = user.id

    base_time = datetime(2025, 6, 1, tzinfo=UTC)
    with SessionLocal() as db:
        for i, rating in enumerate([Decimal("3.0"), Decimal("4.0"), Decimal("5.0")]):
            create_cafe_log(
                db,
                by_user_id=uid,
                cafe_name=f"Cafe{i}",
                rating=rating,
                roaster_id=None,
                origin_country=None,
                brew_method=None,
                flavor_note_ids=[],
                notes="",
                photo_filename=None,
                logged_at=base_time + timedelta(hours=i),
            )

    with SessionLocal() as db:
        rows = list_cafe_logs(db, by_user_id=uid, rating_min=Decimal("4.0"))
        assert len(rows) == 2
        for row in rows:
            assert row.rating >= Decimal("4.0")


def test_list_cafe_logs_date_filter(clean_cafe: None) -> None:
    """date_from/date_to filters narrow by logged_at range."""
    _require_postgres()
    _require_cafe_logs_table()
    from app.db import SessionLocal
    from app.services.cafe_logs import create_cafe_log, list_cafe_logs

    with SessionLocal() as db:
        user = _seed_user(db, username=f"{_TEST_USERNAME_PREFIX}date_filter")
        db.commit()
        uid = user.id

    dates = [
        datetime(2025, 1, 1, tzinfo=UTC),
        datetime(2025, 6, 15, tzinfo=UTC),
        datetime(2025, 12, 31, tzinfo=UTC),
    ]
    with SessionLocal() as db:
        for i, d in enumerate(dates):
            create_cafe_log(
                db,
                by_user_id=uid,
                cafe_name=f"DateCafe{i}",
                rating=Decimal("4.0"),
                roaster_id=None,
                origin_country=None,
                brew_method=None,
                flavor_note_ids=[],
                notes="",
                photo_filename=None,
                logged_at=d,
            )

    with SessionLocal() as db:
        rows = list_cafe_logs(
            db,
            by_user_id=uid,
            date_from=datetime(2025, 6, 1, tzinfo=UTC),
            date_to=datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC),
        )
        assert len(rows) == 2
        for row in rows:
            assert row.logged_at >= datetime(2025, 6, 1, tzinfo=UTC)


def test_list_cafe_logs_default_sort_desc(clean_cafe: None) -> None:
    """Default sort is logged_at DESC (newest first)."""
    _require_postgres()
    _require_cafe_logs_table()
    from app.db import SessionLocal
    from app.services.cafe_logs import create_cafe_log, list_cafe_logs

    with SessionLocal() as db:
        user = _seed_user(db, username=f"{_TEST_USERNAME_PREFIX}sort_desc")
        db.commit()
        uid = user.id

    base_time = datetime(2025, 3, 1, tzinfo=UTC)
    with SessionLocal() as db:
        for i in range(3):
            create_cafe_log(
                db,
                by_user_id=uid,
                cafe_name=f"SortCafe{i}",
                rating=Decimal("4.0"),
                roaster_id=None,
                origin_country=None,
                brew_method=None,
                flavor_note_ids=[],
                notes="",
                photo_filename=None,
                logged_at=base_time + timedelta(days=i),
            )

    with SessionLocal() as db:
        rows = list_cafe_logs(db, by_user_id=uid)
        assert len(rows) == 3
        # Newest first
        for i in range(len(rows) - 1):
            assert rows[i].logged_at >= rows[i + 1].logged_at


def test_update_cafe_log_owner_updates(clean_cafe: None) -> None:
    """Owner update mutates the row and returns the updated row."""
    _require_postgres()
    _require_cafe_logs_table()
    from app.db import SessionLocal
    from app.services.cafe_logs import create_cafe_log, update_cafe_log

    with SessionLocal() as db:
        user = _seed_user(db, username=f"{_TEST_USERNAME_PREFIX}update_owner")
        db.commit()
        uid = user.id

    with SessionLocal() as db:
        row = create_cafe_log(
            db,
            by_user_id=uid,
            cafe_name="Original",
            rating=Decimal("3.0"),
            roaster_id=None,
            origin_country=None,
            brew_method=None,
            flavor_note_ids=[],
            notes="",
            photo_filename=None,
            logged_at=None,
        )
        row_id = row.id

    with SessionLocal() as db:
        updated = update_cafe_log(
            db,
            cafe_log_id=row_id,
            by_user_id=uid,
            cafe_name="Updated Name",
            rating=Decimal("4.5"),
            notes="Updated notes",
        )
        assert updated is not None
        assert updated.cafe_name == "Updated Name"
        assert updated.rating == Decimal("4.5")
        assert updated.notes == "Updated notes"


def test_update_cafe_log_cross_user_returns_none(clean_cafe: None) -> None:
    """Cross-user update returns None and the original row is unmodified."""
    _require_postgres()
    _require_cafe_logs_table()
    from app.db import SessionLocal
    from app.services.cafe_logs import create_cafe_log, get_cafe_log, update_cafe_log

    with SessionLocal() as db:
        owner = _seed_user(db, username=f"{_TEST_USERNAME_PREFIX}upd_owner")
        other = _seed_user(db, username=f"{_TEST_USERNAME_PREFIX}upd_other")
        db.commit()
        owner_id = owner.id
        other_id = other.id

    with SessionLocal() as db:
        row = create_cafe_log(
            db,
            by_user_id=owner_id,
            cafe_name="ShouldNotChange",
            rating=Decimal("4.0"),
            roaster_id=None,
            origin_country=None,
            brew_method=None,
            flavor_note_ids=[],
            notes="",
            photo_filename=None,
            logged_at=None,
        )
        row_id = row.id

    with SessionLocal() as db:
        result = update_cafe_log(
            db,
            cafe_log_id=row_id,
            by_user_id=other_id,
            cafe_name="HackedName",
        )
        assert result is None

    with SessionLocal() as db:
        original = get_cafe_log(db, cafe_log_id=row_id, by_user_id=owner_id)
        assert original is not None
        assert original.cafe_name == "ShouldNotChange"


def test_delete_cafe_log_owner_returns_true(clean_cafe: None) -> None:
    """Owner delete returns True; subsequent get_cafe_log returns None."""
    _require_postgres()
    _require_cafe_logs_table()
    from app.db import SessionLocal
    from app.services.cafe_logs import create_cafe_log, delete_cafe_log, get_cafe_log

    with SessionLocal() as db:
        user = _seed_user(db, username=f"{_TEST_USERNAME_PREFIX}del_owner")
        db.commit()
        uid = user.id

    with SessionLocal() as db:
        row = create_cafe_log(
            db,
            by_user_id=uid,
            cafe_name="ToDelete",
            rating=Decimal("3.0"),
            roaster_id=None,
            origin_country=None,
            brew_method=None,
            flavor_note_ids=[],
            notes="",
            photo_filename=None,
            logged_at=None,
        )
        row_id = row.id

    with SessionLocal() as db:
        result = delete_cafe_log(db, cafe_log_id=row_id, by_user_id=uid)
        assert result is True

    with SessionLocal() as db:
        gone = get_cafe_log(db, cafe_log_id=row_id, by_user_id=uid)
        assert gone is None


def test_delete_cafe_log_cross_user_returns_false(clean_cafe: None) -> None:
    """Cross-user delete returns False; the row still exists."""
    _require_postgres()
    _require_cafe_logs_table()
    from app.db import SessionLocal
    from app.services.cafe_logs import create_cafe_log, delete_cafe_log, get_cafe_log

    with SessionLocal() as db:
        owner = _seed_user(db, username=f"{_TEST_USERNAME_PREFIX}xdel_owner")
        other = _seed_user(db, username=f"{_TEST_USERNAME_PREFIX}xdel_other")
        db.commit()
        owner_id = owner.id
        other_id = other.id

    with SessionLocal() as db:
        row = create_cafe_log(
            db,
            by_user_id=owner_id,
            cafe_name="SurvivesDelete",
            rating=Decimal("4.0"),
            roaster_id=None,
            origin_country=None,
            brew_method=None,
            flavor_note_ids=[],
            notes="",
            photo_filename=None,
            logged_at=None,
        )
        row_id = row.id

    with SessionLocal() as db:
        result = delete_cafe_log(db, cafe_log_id=row_id, by_user_id=other_id)
        assert result is False

    with SessionLocal() as db:
        still_there = get_cafe_log(db, cafe_log_id=row_id, by_user_id=owner_id)
        assert still_there is not None
