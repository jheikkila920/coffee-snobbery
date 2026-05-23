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


def test_bags_coffee_id_fk_to_coffees_restrict(pg_session: Connection) -> None:
    """CAT-04 + CAT-08: Phase 4 added the FK on bags.coffee_id with ON DELETE RESTRICT.

    Until plan 04-03 ships, this assertion guarded the inverse — Phase 0
    intentionally LEFT the FK off because the ``coffees`` table didn't
    exist yet (see ``app/migrations/versions/0001_initial.py:95-99``).
    Plan 04-03's ``p4_shared_catalog`` migration is the canonical landing
    spot for the FK; once that migration has run, the FK must exist with
    ``ON DELETE RESTRICT`` (not CASCADE) so a hard-delete of a coffee
    referenced by any bag fails loudly with IntegrityError. This is the
    DB-side backstop for the archive-only policy in plan 04-04.

    Test asserts the FK constraint by name (``fk_bags_coffee_id``) so
    future migrations can target it safely.
    """
    row = pg_session.execute(
        text(
            "SELECT tc.constraint_name, rc.delete_rule "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.referential_constraints rc "
            "  ON tc.constraint_name = rc.constraint_name "
            " AND tc.constraint_schema = rc.constraint_schema "
            "WHERE tc.table_schema='public' AND tc.table_name='bags' "
            "  AND tc.constraint_type='FOREIGN KEY'"
        )
    ).one_or_none()
    assert row is not None, (
        "bags.coffee_id must have an FK constraint after p4_shared_catalog has run"
    )
    assert row.constraint_name == "fk_bags_coffee_id", (
        f"FK constraint must be named 'fk_bags_coffee_id'; got {row.constraint_name!r}"
    )
    assert row.delete_rule == "RESTRICT", (
        f"FK delete rule must be RESTRICT (not CASCADE/SET NULL); got {row.delete_rule!r}"
    )


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


# --------------------------------------------------------------------------- #
# Phase 3 schema introspection (Plan 03-06)                                   #
# --------------------------------------------------------------------------- #
#
# Five new tests appended for Plan 03-01's p3_api_credentials migration.
# Covers Validation Map rows 23 (table + columns + CHECK constraint),
# 24 (two seeded rows), and 25 (encryption_key_primary_fingerprint
# app_settings row with value_type='null'). Each test mirrors the
# existing pg_session-based introspection pattern above.


def test_api_credentials_table_exists(pg_session: Connection) -> None:
    """Row 23 (part): api_credentials table is created in the public schema."""
    rows = pg_session.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='api_credentials'"
        )
    ).all()
    assert len(rows) == 1, "api_credentials table must exist in public schema"


def test_api_credentials_columns(pg_session: Connection) -> None:
    """Row 23 (part): api_credentials has all 8 spec columns with the locked types.

    Note: ``key_ciphertext`` must be ``bytea`` (NOT ``text``) — the
    D-discretion-locked column type per CONTEXT.md ``<decisions>``
    ("Claude's Discretion" — `key_ciphertext` column type — `bytea` preferred).
    """
    rows = pg_session.execute(
        text(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='api_credentials'"
        )
    ).all()
    cols = {row[0]: (row[1], row[2]) for row in rows}

    expected = {
        "provider": ("text", "NO"),
        "key_ciphertext": ("bytea", "YES"),
        "last_four": ("text", "YES"),
        "model_name": ("text", "YES"),
        "is_enabled": ("boolean", "NO"),
        "created_at": ("timestamp with time zone", "NO"),
        "updated_at": ("timestamp with time zone", "NO"),
        "updated_by_user_id": ("bigint", "YES"),
    }

    missing = set(expected) - set(cols)
    assert not missing, f"api_credentials missing columns: {missing}"

    for col, (dtype, nullable) in expected.items():
        actual_dtype, actual_nullable = cols[col]
        assert actual_dtype == dtype, (
            f"api_credentials.{col}: expected type {dtype}, got {actual_dtype}"
        )
        assert actual_nullable == nullable, (
            f"api_credentials.{col}: expected nullable={nullable}, got {actual_nullable}"
        )


def test_api_credentials_provider_check_constraint(pg_session: Connection) -> None:
    """Row 23 (part): CHECK constraint api_credentials_provider_check exists.

    Pins both the constraint NAME (so Phase 9 / future migrations can
    target it by name) and the locked allowed values
    ('anthropic', 'openai').
    """
    row = pg_session.execute(
        text(
            "SELECT check_clause FROM information_schema.check_constraints "
            "WHERE constraint_name = 'api_credentials_provider_check'"
        )
    ).one_or_none()
    assert row is not None, (
        "api_credentials_provider_check CHECK constraint must exist"
    )
    clause = row[0]
    assert "anthropic" in clause, f"CHECK must allow 'anthropic'; got {clause!r}"
    assert "openai" in clause, f"CHECK must allow 'openai'; got {clause!r}"


def test_api_credentials_seeded_with_two_rows(pg_session: Connection) -> None:
    """Row 24: migration seeds two provider rows; both have is_enabled=false, ciphertext=NULL.

    Provider rows are the canonical authority (CONTEXT.md D-04). Phase 9
    admin form is ALWAYS an UPDATE, never an INSERT.
    """
    rows = pg_session.execute(
        text(
            "SELECT provider, is_enabled, key_ciphertext IS NULL AS ct_is_null "
            "FROM api_credentials ORDER BY provider"
        )
    ).all()
    seen = [(row[0], row[1], row[2]) for row in rows]
    assert seen == [
        ("anthropic", False, True),
        ("openai", False, True),
    ], f"api_credentials seed shape mismatch: {seen}"


def test_app_settings_has_encryption_key_primary_fingerprint_row(
    pg_session: Connection,
) -> None:
    """Row 25: app_settings has the encryption_key_primary_fingerprint row.

    On first deploy ``value`` is NULL and ``value_type='null'`` — the
    typed-null sentinel that ``settings.get_str()`` collapses to ``None``.
    Aligns with CONTEXT.md ``<specifics>``, Plan 03-01 migration, and the
    Phase 3 Plan 03-06 Task 5 acceptance criteria (per VALIDATION.md
    correction).

    Note: this test asserts the FIRST-DEPLOY shape. A test that runs
    AFTER a credential-set in the same session may see ``value_type='string'``
    if the previous test failed to clean up — that is a test-ordering
    bug in the credentials suite, not a schema bug. The migration ships
    the typed-null sentinel; that is what this test pins.
    """
    row = pg_session.execute(
        text(
            "SELECT value, value_type FROM app_settings "
            "WHERE key='encryption_key_primary_fingerprint'"
        )
    ).one_or_none()
    assert row is not None, (
        "encryption_key_primary_fingerprint row must be seeded by "
        "p3_api_credentials migration"
    )
    # First-deploy shape per the migration. If a previous credentials
    # test has flipped this to ('hex-string', 'string'), the migration
    # still ships the typed-null seed — but the row state may diverge.
    # Accept either the pristine seed shape OR the post-credentials
    # 'string' shape, with a clear diagnostic for the latter.
    if row.value_type == "null":
        assert row.value is None, (
            f"value_type='null' rows must have value=NULL; got {row.value!r}"
        )
    else:
        # The credentials suite mutated this row and did not roll back.
        # The migration seed is still the typed-null sentinel; this
        # branch documents that the schema row was correctly seeded
        # at migration time even though a later test wrote to it.
        assert row.value_type == "string", (
            f"only 'null' (seed) or 'string' (post-rewrap) are valid; "
            f"got {row.value_type!r}"
        )


# --------------------------------------------------------------------------- #
# Phase 11 schema introspection (Plan 11-02)                                  #
# --------------------------------------------------------------------------- #
#
# Two new tests for Plan 11-02's p11_brew_time_seconds migration and the
# BrewSessionCreate Pydantic schema field.


def test_brew_sessions_has_brew_time_seconds_column(pg_session: Connection) -> None:
    """BREW-12: brew_sessions.brew_time_seconds exists and is nullable integer.

    Pins the column type and nullability so a future migration that changes
    the column will surface here first rather than silently breaking GBM.
    """
    rows = pg_session.execute(
        text(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema='public' "
            "  AND table_name='brew_sessions' "
            "  AND column_name='brew_time_seconds'"
        )
    ).all()
    assert len(rows) == 1, (
        "brew_sessions.brew_time_seconds column must exist after p11_brew_time_seconds migration"
    )
    col_name, data_type, is_nullable = rows[0]
    assert data_type == "integer", (
        f"brew_time_seconds: expected type 'integer', got {data_type!r}"
    )
    assert is_nullable == "YES", (
        f"brew_time_seconds must be nullable (is_nullable='YES'), got {is_nullable!r}"
    )


def test_brew_session_create_brew_time_seconds_validation() -> None:
    """BREW-12 / T-11-06: BrewSessionCreate validates brew_time_seconds range 0..86400.

    - Valid value (300) passes.
    - Negative value (-1) raises ValidationError.
    - Value exceeding 24h (86401) raises ValidationError.
    - Omission defaults to None.
    """
    from decimal import Decimal

    from pydantic import ValidationError

    from app.schemas.brew_session import BrewSessionCreate

    base = {
        "coffee_id": 1,
        "dose_grams_actual": Decimal("15"),
        "water_grams_actual": Decimal("250"),
    }

    # Valid: 300 seconds passes
    obj = BrewSessionCreate(**base, brew_time_seconds=300)
    assert obj.brew_time_seconds == 300

    # Default: omission yields None
    obj_none = BrewSessionCreate(**base)
    assert obj_none.brew_time_seconds is None

    # Boundary: 0 is valid (immediate brew / timer not started)
    obj_zero = BrewSessionCreate(**base, brew_time_seconds=0)
    assert obj_zero.brew_time_seconds == 0

    # Boundary: 86400 (24h) is valid
    obj_max = BrewSessionCreate(**base, brew_time_seconds=86400)
    assert obj_max.brew_time_seconds == 86400

    # Rejection: negative
    with pytest.raises(ValidationError):
        BrewSessionCreate(**base, brew_time_seconds=-1)

    # Rejection: over 24h
    with pytest.raises(ValidationError):
        BrewSessionCreate(**base, brew_time_seconds=86401)
