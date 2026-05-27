"""Migration smoke test for p16_cafe_logs (Plan 16-01).

Exercises the post-upgrade state of the cafe_logs table: confirms the table
exists, both indexes are present, and the GIN index uses the ``gin`` access
method (proves Pitfall 1 fix — autogenerate cannot emit USING GIN).

Does NOT execute ``alembic downgrade -1`` then ``upgrade head`` mid-suite —
that mutates DB state for parallel tests. The round-trip check was performed
manually in Task 1's verify step; this file only inspects the post-upgrade
state via read-only queries.

Requires:
- Postgres reachable (``_require_postgres`` gate).
- ``cafe_logs`` table present (``_require_cafe_logs_table`` gate — migration
  p16_cafe_logs applied). If missing, every test in this file skips with a
  message naming the revision (project memory: tests-pass-by-skip-mask-green).

Run with: ``pytest tests/migrations/test_cafe_logs_migration.py -x -v -rs``
"""

from __future__ import annotations

import pytest

# --------------------------------------------------------------------------- #
# Skip gates                                                                   #
# --------------------------------------------------------------------------- #


def _require_postgres() -> None:
    """Skip if Postgres is not reachable."""
    try:
        from tests.conftest import _postgres_reachable
    except ImportError:
        pytest.skip("postgres reachability probe missing from conftest")
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable — migration smoke test needs the DB")


# --------------------------------------------------------------------------- #
# Tests                                                                         #
# --------------------------------------------------------------------------- #


def test_cafe_logs_migration_upgrade() -> None:
    """Smoke test: p16_cafe_logs upgrade state is correct.

    Asserts:
    1. cafe_logs table exists (to_regclass returns non-NULL).
    2. Both expected indexes are present in pg_indexes.
    3. ix_cafe_logs_flavor_note_ids uses the ``gin`` access method (Pitfall 1 fix).
    4. Postgres 16+ is active (stack pin assertion).

    Does NOT run alembic downgrade/upgrade — that mutates shared DB state.
    """
    _require_postgres()

    try:
        from tests.conftest import _require_cafe_logs_table
    except ImportError:
        pytest.skip("_require_cafe_logs_table missing from conftest")
    _require_cafe_logs_table()

    try:
        from sqlalchemy import text

        from app.db import engine
    except ImportError:
        pytest.skip("app.db not importable")

    with engine.connect() as conn:
        # 1. Confirm cafe_logs table exists.
        table_oid = conn.execute(text("SELECT to_regclass('public.cafe_logs')")).scalar()
        assert table_oid is not None, "cafe_logs table not found (to_regclass returned NULL)"

        # 2. Both expected indexes must be present.
        idx_rows = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes WHERE tablename = 'cafe_logs' ORDER BY indexname"
            )
        ).fetchall()
        index_names = {row[0] for row in idx_rows}
        assert "ix_cafe_logs_user_logged_at" in index_names, (
            f"ix_cafe_logs_user_logged_at missing; found: {index_names}"
        )
        assert "ix_cafe_logs_flavor_note_ids" in index_names, (
            f"ix_cafe_logs_flavor_note_ids missing; found: {index_names}"
        )

        # 3. GIN access method check — proves Pitfall 1 fix landed.
        # pg_indexes does not expose the AM directly; join through pg_class + pg_am.
        gin_am = conn.execute(
            text(
                "SELECT pg_am.amname"
                " FROM pg_indexes"
                " JOIN pg_class ON pg_class.relname = pg_indexes.indexname"
                " JOIN pg_am ON pg_am.oid = pg_class.relam"
                " WHERE pg_indexes.indexname = 'ix_cafe_logs_flavor_note_ids'"
            )
        ).scalar()
        assert gin_am == "gin", (
            f"ix_cafe_logs_flavor_note_ids access method is '{gin_am}', expected 'gin'; "
            "this means the hand-edited USING GIN clause was not applied (Pitfall 1)"
        )

        # 4. Postgres version gate: stack pin requires PG 16+ (postgres:16-alpine image).
        pg_version_num = conn.execute(
            text("SELECT current_setting('server_version_num')::int")
        ).scalar()
        if pg_version_num is not None and pg_version_num < 160000:
            pytest.skip(
                f"Postgres version {pg_version_num} < 160000 — "
                "stack pin requires Postgres 16 (postgres:16-alpine)"
            )
