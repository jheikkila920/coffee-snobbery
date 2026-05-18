"""Wave 2 tests for AUTH-01 + AUTH-02 — first-admin atomic transaction.

Covers the per-task verification map rows from
``.planning/phases/02-auth/02-VALIDATION.md`` (service-level slices):

- AUTH-01 happy path                        → ``test_create_first_admin_happy_path``
- AUTH-02 FOR UPDATE held across INSERT+UPDATE in one TX → ``test_for_update_atomic``
- AUTH-02 race-lost branch                  → ``test_create_first_admin_race_lost``
- AUTH-04 argon2id-hashed password at INSERT time → ``test_create_first_admin_uses_hashed_password``
- Service enforces is_admin/is_active flags → ``test_create_first_admin_sets_admin_active``

The HTTP-level concurrent-race test (asyncio.gather + async_client POST /setup)
belongs to Plan 02-07 — this plan ships the service-level proof only.

Plan 02-05 Task 2 lands ``app.services.setup``. Until then the lazy-import
gate makes every test skip cleanly (analog: ``tests/services/test_auth.py``).
"""

from __future__ import annotations

import pytest


def _require_setup_service() -> None:
    """Skip cleanly while Plan 02-05 Task 2 has not yet shipped the module."""
    try:
        from app.services.setup import create_first_admin  # noqa: F401
    except ImportError:
        pytest.skip("Wave 2 dependency: app.services.setup (Plan 02-05 Task 2)")


def _require_postgres() -> None:
    """Skip when Postgres is unreachable — service tests need a real DB.

    Mirrors the autouse ``fresh_db`` fixture's reachability probe so tests
    that hit the DB skip cleanly on host-only pytest runs (no docker).
    """
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — service test needs the DB")


@pytest.mark.asyncio
async def test_create_first_admin_happy_path() -> None:
    """AUTH-01: clean DB → returns User, side effects committed.

    Preconditions (from autouse ``fresh_db``): zero users, setup_completed='false'.
    Postconditions: returns User with id; users table has exactly 1 row;
    app_settings.setup_completed flipped to 'true'.
    """
    _require_setup_service()
    _require_postgres()

    from sqlalchemy import select

    from app.main import async_session_factory
    from app.models.app_setting import AppSetting
    from app.models.user import User
    from app.services.auth import verify_password
    from app.services.setup import create_first_admin

    async with async_session_factory() as db:
        user = await create_first_admin(
            db,
            username="admin",
            email="admin@example.com",
            plaintext_password="twelve-chars-min-password",
        )

    assert user is not None, "happy path must return a User row"
    assert user.id is not None, "User.id must be populated via flush() before return"
    assert user.username == "admin"
    assert user.email == "admin@example.com"
    assert user.is_admin is True, "first user is always admin (service-enforced)"
    assert user.is_active is True, "first user must be active"
    assert verify_password(user.password_hash, "twelve-chars-min-password"), (
        "password_hash must verify against the plaintext via argon2"
    )

    # Verify side effects in a FRESH session (proves the commit landed).
    async with async_session_factory() as db:
        result = await db.execute(select(User))
        users = result.scalars().all()
        assert len(users) == 1, f"exactly one user row expected; found {len(users)}"

        setting = (
            await db.execute(
                select(AppSetting).where(AppSetting.key == "setup_completed")
            )
        ).scalar_one()
        assert setting.value == "true", (
            f"setup_completed must be 'true' after success; got {setting.value!r}"
        )


@pytest.mark.asyncio
async def test_for_update_atomic() -> None:
    """AUTH-02: single transaction containing SELECT FOR UPDATE → INSERT → UPDATE → 1 COMMIT.

    Captures executed SQL via a ``before_cursor_execute`` event listener on
    the async engine's underlying sync engine. Asserts:

    1. The captured SQL stream contains a SELECT that includes the literal
       ``FOR UPDATE`` clause.
    2. Statement order is SELECT (FOR UPDATE) → INSERT users → UPDATE app_settings.
    3. The ``commit`` core event fires exactly once for the transaction
       containing those three statements.

    This is the AUTH-02 race-protection proof at the service layer; the
    full HTTP concurrency test belongs to Plan 02-07.
    """
    _require_setup_service()
    _require_postgres()

    from sqlalchemy import event

    from app.main import _async_engine, async_session_factory
    from app.services.setup import create_first_admin

    statements: list[str] = []
    commits: list[int] = []
    sync_engine = _async_engine.sync_engine

    def _record(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001, ARG001
        statements.append(statement)

    def _commit(conn):  # noqa: ANN001, ARG001
        commits.append(1)

    event.listen(sync_engine, "before_cursor_execute", _record)
    event.listen(sync_engine, "commit", _commit)
    try:
        async with async_session_factory() as db:
            user = await create_first_admin(
                db,
                username="atomic-admin",
                email="atomic@example.com",
                plaintext_password="twelve-chars-min-password",
            )
        assert user is not None, "happy path precondition for atomic test"
    finally:
        event.remove(sync_engine, "before_cursor_execute", _record)
        event.remove(sync_engine, "commit", _commit)

    # Find the SELECT that contains FOR UPDATE — it MUST exist.
    select_for_update_idx: int | None = None
    insert_users_idx: int | None = None
    update_settings_idx: int | None = None
    for idx, sql in enumerate(statements):
        upper = sql.upper()
        # SQLAlchemy emits "FOR UPDATE" verbatim in psycopg dialect output.
        if "SELECT" in upper and "FOR UPDATE" in upper and "APP_SETTINGS" in upper:
            if select_for_update_idx is None:
                select_for_update_idx = idx
        elif (
            insert_users_idx is None
            and upper.lstrip().startswith("INSERT")
            and "USERS" in upper
        ):
            insert_users_idx = idx
        elif (
            update_settings_idx is None
            and upper.lstrip().startswith("UPDATE")
            and "APP_SETTINGS" in upper
        ):
            update_settings_idx = idx

    assert select_for_update_idx is not None, (
        f"no SELECT ... FOR UPDATE on app_settings observed; statements="
        f"{[s[:80] for s in statements]}"
    )
    assert insert_users_idx is not None, (
        f"no INSERT into users observed; statements={[s[:80] for s in statements]}"
    )
    assert update_settings_idx is not None, (
        f"no UPDATE on app_settings observed; statements="
        f"{[s[:80] for s in statements]}"
    )

    assert insert_users_idx > select_for_update_idx, (
        f"INSERT users (idx={insert_users_idx}) must come AFTER "
        f"SELECT ... FOR UPDATE (idx={select_for_update_idx}); "
        f"statements={[s[:80] for s in statements]}"
    )
    assert update_settings_idx > insert_users_idx, (
        f"UPDATE app_settings (idx={update_settings_idx}) must come AFTER "
        f"INSERT users (idx={insert_users_idx}); "
        f"statements={[s[:80] for s in statements]}"
    )

    # Exactly one commit — the SELECT FOR UPDATE, INSERT, and UPDATE
    # share a single transaction. (Other test scaffolding commits — e.g.,
    # the autouse fresh_db DELETE — happen BEFORE the listener is attached,
    # so they are not counted here.)
    assert len(commits) == 1, (
        f"exactly one commit expected (atomic transaction); got {len(commits)}. "
        f"statements={[s[:80] for s in statements]}"
    )


@pytest.mark.asyncio
async def test_create_first_admin_race_lost() -> None:
    """AUTH-02 race-lost: setup_completed already 'true' → returns None, no insert."""
    _require_setup_service()
    _require_postgres()

    from sqlalchemy import select, text

    from app.main import async_session_factory
    from app.models.user import User
    from app.services.setup import create_first_admin

    # Pre-flip the setting to simulate "another concurrent setup already won".
    async with async_session_factory() as db:
        await db.execute(
            text("UPDATE app_settings SET value='true' WHERE key='setup_completed'")
        )
        await db.commit()

    # Now call create_first_admin — should return None and NOT insert.
    async with async_session_factory() as db:
        result = await create_first_admin(
            db,
            username="loser",
            email="loser@example.com",
            plaintext_password="twelve-chars-min-password",
        )
    assert result is None, "race-lost path must return None per D-01"

    async with async_session_factory() as db:
        users = (await db.execute(select(User))).scalars().all()
        assert len(users) == 0, (
            f"no user row must be inserted on race-lost path; found {len(users)}"
        )


@pytest.mark.asyncio
async def test_create_first_admin_uses_hashed_password() -> None:
    """AUTH-04: returned user.password_hash is argon2id-encoded and verifies."""
    _require_setup_service()
    _require_postgres()

    from app.main import async_session_factory
    from app.services.auth import verify_password
    from app.services.setup import create_first_admin

    async with async_session_factory() as db:
        user = await create_first_admin(
            db,
            username="hashcheck",
            email="hashcheck@example.com",
            plaintext_password="twelve-chars-min-password",
        )

    assert user is not None
    assert user.password_hash.startswith("$argon2id$"), (
        f"password_hash must be argon2id-encoded; got prefix "
        f"{user.password_hash[:20]!r}"
    )
    # The hash header should contain the AUTH-04 parameter pins.
    assert "m=65536,t=3,p=4" in user.password_hash, (
        "password_hash header must carry the AUTH-04 argon2 params; "
        f"got {user.password_hash[:60]!r}"
    )
    assert verify_password(user.password_hash, "twelve-chars-min-password") is True
    assert verify_password(user.password_hash, "wrong-password") is False


@pytest.mark.asyncio
async def test_create_first_admin_sets_admin_active() -> None:
    """Service enforces is_admin=True and is_active=True (NOT taken from input).

    The function signature has no is_admin / is_active parameter — the
    first user is always an active admin. Phase 9's admin-create surface
    is the only path that can mint a non-admin.
    """
    _require_setup_service()
    _require_postgres()

    from app.main import async_session_factory
    from app.services.setup import create_first_admin

    async with async_session_factory() as db:
        user = await create_first_admin(
            db,
            username="enforced",
            email="enforced@example.com",
            plaintext_password="twelve-chars-min-password",
        )

    assert user is not None
    assert user.is_admin is True, (
        "first user must always be admin (service-enforced, not input)"
    )
    assert user.is_active is True, "first user must always be active"
