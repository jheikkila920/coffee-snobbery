"""Phase 5 brew sessions: create brew_sessions + brew_drafts (BREW-01, BREW-06/07).

Revision ID: p5_brew_sessions
Revises: p4_shared_catalog
Create Date: 2026-05-20

One migration per logical change (CONTEXT D-02) — the two Phase 5 data tables
(``brew_sessions`` + ``brew_drafts``) land together so the wave-2+ service /
router plans run against the full target schema from one ``alembic upgrade head``.

Tables created:

1. ``brew_sessions`` — the first per-user table. FK -> users / coffees (RESTRICT),
   bags / recipes / equipment (SET NULL). Holds the GENERATED extraction_yield_pct.
2. ``brew_drafts``   — one row per user (UNIQUE user_id, CASCADE), JSONB payload.

Hand-edited DDL (autogenerate cannot emit it — Pitfall 1):

* ``extraction_yield_pct numeric(5,2) GENERATED ALWAYS AS (...) STORED`` — added
  via raw ``op.execute`` ALTER TABLE after the table create. Task 0 resolved the
  unit: ``tds_pct`` is a WHOLE PERCENT (1.35 = 1.35%), so the expression divides
  tds by 100 and re-multiplies the ratio by 100 to emit a whole-percent EY:
  ``(yield_grams_actual * tds_pct / 100.0) / dose_grams_actual * 100``.
  NULL propagates automatically when any operand is NULL.
* ``CREATE INDEX ... USING GIN (flavor_note_ids_observed)`` — raw, mirrors the
  GIN hand-edit in p4_shared_catalog.py (autogenerate cannot emit USING GIN).
* The two B-tree indexes are ``(user_id, brewed_at DESC)`` and
  ``(user_id, coffee_id, brewed_at DESC)`` — added via raw SQL to carry the DESC
  sort direction reliably (list default sort + per-coffee prefill / dedup probe).

NO UNIQUE on ``(user_id, coffee_id, brewed_at)`` — CONTEXT defers it; CSV import
dedup is a service-layer probe, not a DB constraint.

Alembic-safe convention (mirrors p4_shared_catalog.py:32-35): this migration body
does NOT import from ``app.models``. Schema is described inline with ``sa.Column``
/ ``sa.ForeignKey``. A future model rename does not invalidate this migration.

Requirements traceability:

* BREW-01 — brew_sessions table + GENERATED extraction_yield_pct + ARRAY observed
* BREW-06/07 — brew_drafts server backstop (one per user, JSONB)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "p5_brew_sessions"
down_revision: str | Sequence[str] | None = "p4_shared_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Task 0 resolved: tds_pct is a WHOLE PERCENT, so EY divides tds by 100 and
# re-multiplies the ratio by 100 to emit a whole-percent extraction yield.
_EY_EXPRESSION = "(yield_grams_actual * tds_pct / 100.0) / dose_grams_actual * 100"


def upgrade() -> None:
    """Create brew_sessions (+ GENERATED EY, GIN, B-tree indexes) and brew_drafts."""
    # ---- brew_sessions (BREW-01) -----------------------------------------
    # extraction_yield_pct is added AFTER the create via raw ALTER TABLE so the
    # GENERATED ALWAYS AS ... STORED clause is emitted verbatim (Pitfall 1).
    op.create_table(
        "brew_sessions",
        sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
        # Ownership + denormalized coffee — both RESTRICT (history is precious).
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "coffee_id",
            sa.BigInteger,
            sa.ForeignKey("coffees.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        # Optional references — all SET NULL (a brew outlives the thing it used).
        sa.Column(
            "bag_id",
            sa.BigInteger,
            sa.ForeignKey("bags.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "recipe_id",
            sa.BigInteger,
            sa.ForeignKey("recipes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "brewer_id",
            sa.BigInteger,
            sa.ForeignKey("equipment.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "grinder_id",
            sa.BigInteger,
            sa.ForeignKey("equipment.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "kettle_id",
            sa.BigInteger,
            sa.ForeignKey("equipment.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Brew parameters.
        sa.Column("water_type", sa.Text, nullable=True),
        sa.Column("dose_grams_actual", sa.Numeric, nullable=False),
        sa.Column("water_grams_actual", sa.Numeric, nullable=False),
        sa.Column("yield_grams_actual", sa.Numeric, nullable=True),
        sa.Column("tds_pct", sa.Numeric, nullable=True),
        # extraction_yield_pct added below via raw ALTER (GENERATED).
        sa.Column("water_temp_c_actual", sa.Numeric, nullable=True),
        sa.Column("grind_setting_actual", sa.Text, nullable=True),
        sa.Column("rating", sa.Numeric(3, 2), nullable=True),
        sa.Column(
            "flavor_note_ids_observed",
            postgresql.ARRAY(sa.BigInteger),
            nullable=False,
            server_default=sa.text("'{}'::bigint[]"),
        ),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        # Timestamps.
        sa.Column(
            "brewed_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # GENERATED column — hand-edited (Pitfall 1: autogenerate drops the clause).
    op.execute(
        "ALTER TABLE brew_sessions ADD COLUMN extraction_yield_pct numeric(5,2) "
        f"GENERATED ALWAYS AS ({_EY_EXPRESSION}) STORED"
    )

    # B-tree indexes (DESC on brewed_at) — raw SQL to carry the sort direction.
    op.execute(
        "CREATE INDEX ix_brew_sessions_user_brewed_at ON brew_sessions (user_id, brewed_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_brew_sessions_user_coffee_brewed_at "
        "ON brew_sessions (user_id, coffee_id, brewed_at DESC)"
    )
    # GIN index — hand-edited (autogenerate cannot emit USING GIN), mirrors p4.
    op.execute(
        "CREATE INDEX ix_brew_sessions_flavor_note_ids_observed "
        "ON brew_sessions USING GIN (flavor_note_ids_observed)"
    )

    # ---- brew_drafts (BREW-06/07) ----------------------------------------
    # One row per user (UNIQUE user_id). CASCADE: a draft dies with its user
    # (the one place CASCADE is correct in Phase 5).
    op.create_table(
        "brew_drafts",
        sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    """Reverse the upgrade in FK-safe order.

    brew_drafts has no inbound FKs; brew_sessions is referenced by nothing yet.
    Drop indexes (raw GIN/B-tree with IF EXISTS for idempotency) before the
    table, then both tables.
    """
    op.drop_table("brew_drafts")

    op.execute("DROP INDEX IF EXISTS ix_brew_sessions_flavor_note_ids_observed")
    op.execute("DROP INDEX IF EXISTS ix_brew_sessions_user_coffee_brewed_at")
    op.execute("DROP INDEX IF EXISTS ix_brew_sessions_user_brewed_at")
    op.drop_table("brew_sessions")
