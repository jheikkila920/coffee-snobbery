"""Phase 9 (Admin) shared test fixtures.

Wave 0 contract: every Phase 9 test file is collectable after this plan ships,
even if most tests are skipped or red. All fixtures SELF-SEED real rows via
the same ``asyncio.run + async_session_factory`` pattern used in
``tests/conftest.py:_seed_user``. No ``pytest.skip`` on missing seed data —
that masks failures (project history documented in MEMORY.md).

Fixtures exported:
- ``admin_session``: thin wrapper around root ``seeded_admin_user``; returns
  cookie dict ready for ``client.get(..., cookies=...)``
- ``regular_session``: same shape for a non-admin user
- ``user_with_brews``: user + coffee + >=1 brew_sessions rows (D-15 block test)
- ``user_no_brews``: user with zero brew_sessions (D-15 succeed test)
- ``user_with_sessions``: user + 2 live session rows (is_admin-toggle invalidation)
- ``two_admins``: exactly two active admins (demotion succeeds)
- ``single_admin``: exactly one active admin (last-admin guard blocks)
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from typing import Any

import pytest

from tests.conftest import _seed_user

# ---------------------------------------------------------------------------
# Cookie-ready session fixtures — thin wrappers around root fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_session(seeded_admin_user: dict[str, Any]) -> dict[str, str]:
    """Admin session cookie dict for ``client.get(..., cookies=admin_session)``."""
    return {"session_id": seeded_admin_user["signed_cookie"]}


@pytest.fixture
def regular_session(seeded_regular_user: dict[str, Any]) -> dict[str, str]:
    """Regular-user session cookie dict for ``client.get(..., cookies=regular_session)``."""
    return {"session_id": seeded_regular_user["signed_cookie"]}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_brew_for_user(user_id: int) -> int:
    """Create one coffee + one brew_session for ``user_id``.

    Returns the brew_session id. Satisfies the NOT-NULL FKs:
    - brew_sessions.coffee_id RESTRICT -> seeds a coffee row first
    - dose_grams_actual / water_grams_actual are required Numeric columns

    Runs via asyncio.run + async_session_factory (mirrors root _seed_user).
    """
    from app.main import async_session_factory
    from app.models.brew_session import BrewSession
    from app.models.coffee import Coffee

    async def _do() -> int:
        async with async_session_factory() as db:
            suffix = uuid.uuid4().hex[:6]
            coffee = Coffee(
                name=f"Test Coffee {suffix}",
                notes="",
            )
            db.add(coffee)
            await db.flush()
            brew = BrewSession(
                user_id=user_id,
                coffee_id=coffee.id,
                dose_grams_actual=Decimal("18.0"),
                water_grams_actual=Decimal("300.0"),
            )
            db.add(brew)
            await db.commit()
            await db.refresh(brew)
            return brew.id

    return asyncio.run(_do())


def _seed_extra_session(user_id: int) -> uuid.UUID:
    """Create an additional session row for ``user_id``.

    Used by ``user_with_sessions`` to seed the extra row (the primary session
    is already created by _seed_user). Returns the new session_id UUID.
    """
    from app.main import async_session_factory
    from app.services.sessions import regenerate_session

    async def _do() -> uuid.UUID:
        async with async_session_factory() as db:
            return await regenerate_session(db, None, user_id)

    return asyncio.run(_do())


# ---------------------------------------------------------------------------
# D-15 hard-delete guard fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def user_with_brews() -> dict[str, Any]:
    """Seed a user with >=1 brew_sessions rows.

    D-15: hard-delete must be blocked because of the RESTRICT FK on
    brew_sessions.user_id. Returns ``{user_id, brew_session_id, signed_cookie}``.
    """
    seeded = _seed_user(is_admin=False)
    user = seeded["user"]
    brew_id = _seed_brew_for_user(user.id)
    return {
        "user_id": user.id,
        "brew_session_id": brew_id,
        "signed_cookie": seeded["signed_cookie"],
    }


@pytest.fixture
def user_no_brews() -> dict[str, Any]:
    """Seed a user with zero brew_sessions.

    D-15: hard-delete must succeed. Returns ``{user_id, signed_cookie}``.
    """
    seeded = _seed_user(is_admin=False)
    return {
        "user_id": seeded["user"].id,
        "signed_cookie": seeded["signed_cookie"],
    }


# ---------------------------------------------------------------------------
# Session-invalidation fixture (is_admin toggle D-16)
# ---------------------------------------------------------------------------


@pytest.fixture
def user_with_sessions() -> dict[str, Any]:
    """Seed a user with 2 live sessions.

    The toggle-admin test asserts that after toggling is_admin, the target
    user's session rows are all deleted. Returns
    ``{user_id, session_count, signed_cookie}``.

    The primary session is created by _seed_user; _seed_extra_session adds
    a second so the test can assert count drops from 2 to 0.
    """
    seeded = _seed_user(is_admin=False)
    user = seeded["user"]
    _seed_extra_session(user.id)
    return {
        "user_id": user.id,
        "session_count": 2,
        "signed_cookie": seeded["signed_cookie"],
    }


# ---------------------------------------------------------------------------
# Last-admin guard fixtures (D-16)
# ---------------------------------------------------------------------------


@pytest.fixture
def two_admins() -> dict[str, Any]:
    """Seed exactly two active admin users.

    One can be demoted; the other remains as the surviving admin.
    Returns ``{admin1_id, admin2_id}``.
    """
    a1 = _seed_user(is_admin=True)
    a2 = _seed_user(is_admin=True)
    return {
        "admin1_id": a1["user"].id,
        "admin1_cookie": a1["signed_cookie"],
        "admin2_id": a2["user"].id,
        "admin2_cookie": a2["signed_cookie"],
    }


@pytest.fixture
def single_admin(seeded_admin_user: dict[str, Any]) -> dict[str, Any]:
    """Exactly one active admin (the seeded_admin_user from root conftest).

    The last-admin guard must block demotion / deactivation / delete of this
    user. Returns ``{user_id, signed_cookie}``.
    """
    return {
        "user_id": seeded_admin_user["user"].id,
        "signed_cookie": seeded_admin_user["signed_cookie"],
    }
