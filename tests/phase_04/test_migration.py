"""Alembic upgrade/downgrade round-trip tests for ``p4_shared_catalog``.

Replaces the Wave-0 stub. Three load-bearing assertions:

1. ``alembic upgrade head`` is idempotent — re-running it after the head
   is already at ``p4_shared_catalog`` is a no-op (no exception, head
   stays put).
2. ``alembic downgrade -1`` from ``p4_shared_catalog`` drops the catalog
   tables (``coffees`` no longer exists); a follow-up ``alembic upgrade
   head`` restores them. Round-trip clean per CONTEXT D-02.
3. The GIN index on ``coffees.advertised_flavor_note_ids`` lands with
   ``USING gin`` — the hand-edited raw ``op.execute`` worked (Pitfall 3
   in 04-RESEARCH.md; SQLAlchemy autogenerate cannot emit ``USING GIN``).

Implementation uses ``alembic.command.upgrade`` / ``downgrade`` driven
from a programmatically-built ``alembic.config.Config`` (matches the path
``alembic`` CLI takes, just without the subprocess overhead). The
``DATABASE_URL`` comes from ``app.config.settings`` so this test honors
the same env-var bootstrap as the rest of the suite.

The third test re-runs ``upgrade head`` at the top of each downgrade-
based test (defensive — the head must be ``p4_shared_catalog`` for the
downgrade direction to be the one under test). Tests are ordered to be
robust against any execution order pytest chooses.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _require_postgres() -> None:
    """Skip if Postgres is not reachable (host-only / unit-only runs)."""
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — migration round-trip needs the DB")


def _alembic_config():
    """Return an ``alembic.config.Config`` wired to the project's alembic.ini.

    Walks up from ``tests/phase_04/test_migration.py`` to the repo root so
    the config locates ``alembic.ini`` regardless of pytest's invocation
    cwd. The runtime ``DATABASE_URL`` is set by ``env.py`` from
    ``app.config.settings`` — we do NOT override it here.
    """
    from alembic.config import Config

    # tests/phase_04/test_migration.py → tests/ → repo root
    repo_root = Path(__file__).resolve().parent.parent.parent
    ini_path = repo_root / "alembic.ini"
    if not ini_path.exists():
        pytest.skip(f"alembic.ini not found at {ini_path}")
    return Config(str(ini_path))


def _ensure_head() -> None:
    """Make sure the DB is at ``p4_shared_catalog`` head before a downgrade test."""
    from alembic import command

    cfg = _alembic_config()
    command.upgrade(cfg, "head")


def test_alembic_upgrade_head_idempotent() -> None:
    """Re-running ``upgrade head`` when already at head is a clean no-op."""
    _require_postgres()
    from alembic import command

    cfg = _alembic_config()
    # First run: brings DB to head (or stays put).
    command.upgrade(cfg, "head")
    # Second run: must NOT raise — head is already at p4_shared_catalog.
    command.upgrade(cfg, "head")


def test_alembic_downgrade_p4_then_upgrade() -> None:
    """downgrade -1 drops the catalog tables; upgrade head restores them."""
    _require_postgres()
    from alembic import command
    from sqlalchemy import text

    from app.db import engine

    _ensure_head()
    cfg = _alembic_config()

    # Downgrade to the revision BELOW p4 (p3_api_credentials), which reverts
    # p4_shared_catalog (and any newer revision such as p5_brew_sessions) so
    # the coffees-dropped assertion holds regardless of the current head.
    # Targeting an explicit revision (not a moving "-1") keeps this test stable
    # as later phases add migrations on top of p4.
    command.downgrade(cfg, "p3_api_credentials")

    # coffees must no longer exist; to_regclass returns NULL for an
    # unknown relation rather than raising.
    with engine.connect() as conn:
        coffees_oid = conn.execute(text("SELECT to_regclass('public.coffees')")).scalar()
    assert coffees_oid is None, (
        f"coffees table must be dropped by p4 downgrade; to_regclass returned {coffees_oid!r}"
    )

    # Restore — leaves DB ready for subsequent tests.
    command.upgrade(cfg, "head")

    with engine.connect() as conn:
        coffees_oid_after = conn.execute(
            text("SELECT to_regclass('public.coffees')")
        ).scalar()
    assert coffees_oid_after is not None, (
        "coffees table must exist again after upgrade head"
    )


def test_alembic_p4_gin_index_present() -> None:
    """ix_coffees_advertised_flavor_note_ids was created with USING gin."""
    _require_postgres()
    from sqlalchemy import text

    from app.db import engine

    _ensure_head()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE indexname = 'ix_coffees_advertised_flavor_note_ids'"
            )
        ).one_or_none()

    assert row is not None, (
        "ix_coffees_advertised_flavor_note_ids must exist after p4 upgrade"
    )
    indexdef = row[0]
    # Postgres lower-cases USING GIN -> 'using gin' in pg_indexes.indexdef.
    assert "using gin" in indexdef.lower(), (
        f"GIN index expected; pg_indexes.indexdef = {indexdef!r}"
    )
