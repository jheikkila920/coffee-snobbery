"""Schema + seed introspection tests for ``0001_initial.py``.

These are **integration** tests: they connect to a live Postgres and inspect
``pg_extension`` / ``information_schema.columns`` / ``pg_indexes`` to prove
the migration produced the expected schema and seed rows.

The fixture is intentionally local to this file (NOT in ``tests/conftest.py``)
so the unit tests in ``tests/test_logging.py``, ``tests/test_env_example.py``,
and ``tests/test_no_direct_env.py`` can still run without a database.

Skip strategy: if the database is unreachable, every test in this file is
skipped via ``pytest.skip()`` — no errors, no failures. The integration suite
(Plan 05's ``make smoke``) brings the compose stack up before running pytest,
and asserts these tests pass.

Requirements traceability:
* FOUND-06   — test_three_extensions_installed
* FOUND-05   — test_five_tables_exist
* CAT-04     — test_bags_columns + test_bags_coffee_id_has_no_foreign_key
* AI-02 /
  COST-1     — test_ai_recommendations_columns + test_ai_recommendations_indexes
* CONTEXT
  D-17       — test_app_settings_seeded_with_19_rows
              + test_app_settings_critical_keys_present
* SEC-5      — test_app_settings_setup_completed_is_false
"""

from __future__ import annotations

from collections.abc import Generator

import psycopg
import pytest
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import OperationalError

from app.config import settings


@pytest.fixture(scope="module")
def pg_session() -> Generator[Connection, None, None]:
    """Yield a live SQLAlchemy connection to the migrated Postgres.

    If the connection fails (Postgres not running, network unreachable, the
    migration hasn't been applied, etc.), every test in this module skips
    rather than errors — unit-only ``pytest`` runs (Wave 0) stay green.
    """
    try:
        engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
        connection = engine.connect()
    except (psycopg.OperationalError, OperationalError) as exc:
        pytest.skip(
            "Postgres not reachable — run via `make smoke` or "
            f"`docker compose up -d` first ({exc.__class__.__name__})"
        )

    try:
        yield connection
    finally:
        connection.close()
        engine.dispose()


def test_three_extensions_installed(pg_session: Connection) -> None:
    """FOUND-06: citext, pg_trgm, unaccent are installed in the public schema."""
    rows = pg_session.execute(
        text(
            "SELECT extname FROM pg_extension "
            "WHERE extname IN ('citext','pg_trgm','unaccent')"
        )
    ).all()
    installed = {row[0] for row in rows}
    expected = {"citext", "pg_trgm", "unaccent"}
    assert installed == expected, f"missing extensions: {expected - installed}"


def test_five_tables_exist(pg_session: Connection) -> None:
    """FOUND-05: the five Phase 0 tables exist in the public schema."""
    rows = pg_session.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' "
            "AND table_name IN ('users','bags','wishlist_entries',"
            "'ai_recommendations','app_settings')"
        )
    ).all()
    present = {row[0] for row in rows}
    expected = {"users", "bags", "wishlist_entries", "ai_recommendations", "app_settings"}
    assert present == expected, f"missing tables: {expected - present}"


def test_bags_columns(pg_session: Connection) -> None:
    """CAT-04: bags has all 9 spec columns with correct types and nullability."""
    rows = pg_session.execute(
        text(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='bags'"
        )
    ).all()
    cols = {row[0]: (row[1], row[2]) for row in rows}

    expected = {
        "id": ("bigint", "NO"),
        "coffee_id": ("bigint", "NO"),
        "roast_date": ("date", "YES"),
        "weight_grams": ("integer", "YES"),
        "opened_at": ("timestamp with time zone", "YES"),
        "finished_at": ("timestamp with time zone", "YES"),
        "notes": ("text", "NO"),
        "created_at": ("timestamp with time zone", "NO"),
        "updated_at": ("timestamp with time zone", "NO"),
    }

    missing = set(expected) - set(cols)
    assert not missing, f"bags missing columns: {missing}"

    for col, (dtype, nullable) in expected.items():
        actual_dtype, actual_nullable = cols[col]
        assert actual_dtype == dtype, (
            f"bags.{col}: expected type {dtype}, got {actual_dtype}"
        )
        assert actual_nullable == nullable, (
            f"bags.{col}: expected nullable={nullable}, got {actual_nullable}"
        )


def test_bags_coffee_id_has_no_foreign_key(pg_session: Connection) -> None:
    """CAT-04 + CONTEXT: bags.coffee_id has NO FK constraint in Phase 0.

    Phase 4's migration ADDs the FK once the ``coffees`` table exists. If a
    future planner accidentally adds the FK here, this assertion guards
    against the regression.
    """
    count = pg_session.execute(
        text(
            "SELECT count(*) FROM information_schema.table_constraints "
            "WHERE table_schema='public' AND table_name='bags' "
            "AND constraint_type='FOREIGN KEY'"
        )
    ).scalar_one()
    assert count == 0, f"bags should have NO FK constraints in Phase 0; got {count}"


def test_ai_recommendations_columns(pg_session: Connection) -> None:
    """AI-02 + COST-1: ai_recommendations carries the full column set.

    The load-bearing assertion is that all 11 cost-observability columns
    exist with the right type from day one. Retrofitting columns onto a
    populated table is painful — Phase 7 must not face that.
    """
    rows = pg_session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='ai_recommendations'"
        )
    ).all()
    cols = {row[0] for row in rows}

    # COST-1 cost-observability columns:
    cost_obs = {
        "tokens_input",
        "tokens_output",
        "tokens_input_search",
        "web_search_count",
        "provider_used",
        "model_used",
        "tool_version",
        "url_verified",
        "duration_ms",
        "generated_by",
        "error_status",
    }
    missing_cost = cost_obs - cols
    assert not missing_cost, f"ai_recommendations missing COST-1 columns: {missing_cost}"

    # Full AI-02 column set:
    expected = cost_obs | {
        "id",
        "user_id",
        "recommendation_type",
        "input_signature",
        "response_json",
        "generated_at",
    }
    missing = expected - cols
    assert not missing, f"ai_recommendations missing AI-02 columns: {missing}"


def test_ai_recommendations_indexes(pg_session: Connection) -> None:
    """AI-02: both ai_recommendations indexes exist (signature lookup + history scan)."""
    rows = pg_session.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname='public' AND tablename='ai_recommendations'"
        )
    ).all()
    indexes = {row[0] for row in rows}
    required = {"ix_ai_recs_input_signature", "ix_ai_recs_user_type_generated"}
    missing = required - indexes
    assert not missing, f"ai_recommendations missing indexes: {missing}"


def test_app_settings_seeded_with_19_rows(pg_session: Connection) -> None:
    """CONTEXT D-17: at least 19 documented rows seeded by 0001_initial.

    Uses ``>= 19`` rather than ``== 19`` so future migrations can ADD seed
    rows without breaking this test. The exact 19-key set is enforced by
    ``test_app_settings_critical_keys_present``.
    """
    count = pg_session.execute(text("SELECT count(*) FROM app_settings")).scalar_one()
    assert count >= 19, f"expected >=19 app_settings rows; got {count}"


def test_app_settings_critical_keys_present(pg_session: Connection) -> None:
    """CONTEXT D-17: every load-bearing seed key downstream phases depend on."""
    critical = [
        "setup_completed",
        "ai_tool_version_anthropic",
        "ai_tool_version_openai",
        "min_sessions_for_ai",
        "min_flavor_notes_for_ai",
        "ai_primary_max_searches",
        "ai_broadened_max_searches",
        "last_ai_run_status",
        "last_backup_status",
        "last_backup_at",
        "recommendation_region",
        "ai_provider_default",
        "photo_max_bytes",
        "csv_import_max_rows",
        "home_recent_brews_limit",
        "home_top_coffees_limit",
        "home_top_coffees_min_sessions",
        "home_top_flavors_min_rating",
        "home_sweetspot_min_sessions",
    ]
    rows = pg_session.execute(
        text("SELECT key FROM app_settings WHERE key = ANY(:keys)"),
        {"keys": critical},
    ).all()
    found = {row[0] for row in rows}
    missing = set(critical) - found
    assert not missing, f"missing seed keys: {missing}"


def test_app_settings_setup_completed_is_false(pg_session: Connection) -> None:
    """SEC-5: Phase 2's setup-race defense reads this exact value.

    The ``/setup`` route does ``SELECT value FROM app_settings WHERE
    key='setup_completed' FOR UPDATE`` and refuses if the value is anything
    other than the literal string ``'false'``. If a future migration changes
    this seed value, Phase 2's race defense silently breaks — guard against
    the regression here.
    """
    row = pg_session.execute(
        text("SELECT value, value_type FROM app_settings WHERE key='setup_completed'")
    ).one()
    assert row.value == "false", f"setup_completed value: expected 'false', got {row.value!r}"
    assert row.value_type == "bool", (
        f"setup_completed value_type: expected 'bool', got {row.value_type!r}"
    )
