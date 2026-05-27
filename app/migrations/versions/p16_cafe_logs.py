"""Phase 16: create cafe_logs table + DESC B-tree + GIN indexes (CAFE-01..06).

Revision ID: p16_cafe_logs
Revises: p15_1_varietal_m2m
Create Date: 2026-05-27

Creates:
  cafe_logs — per-user cafe tasting log (CONTEXT D-01..D-05 + Claude's discretion)

Hand-edited DDL (autogenerate cannot emit it — Pitfall 1 from RESEARCH.md):

* ``CREATE INDEX ix_cafe_logs_user_logged_at ON cafe_logs (user_id, logged_at DESC)``
  — raw SQL to carry the DESC sort direction reliably (list default sort).
* ``CREATE INDEX ix_cafe_logs_flavor_note_ids ON cafe_logs USING GIN (flavor_note_ids)``
  — hand-edited (autogenerate cannot emit USING GIN for ARRAY columns, Pitfall 1).

Column shapes locked per CONTEXT D-01..D-05 + Claude's discretion:
  - cafe_name TEXT NOT NULL (plain Text, NOT CITEXT — per-user free-text)
  - rating Numeric(3,2) NULL (0-5 in 0.25 steps, mirrors brew_sessions.rating)
  - roaster_id BIGINT NULL FK ondelete=SET NULL (CONTEXT D-02)
  - origin_country TEXT NULL (no FK, no countries table — CONTEXT D-03)
  - flavor_note_ids BIGINT[] NOT NULL DEFAULT '{}' + GIN (CONTEXT D-04)
  - brew_method TEXT NULL (free-text, no enum — CONTEXT D-05)

Alembic-safe convention (mirrors p4_shared_catalog.py): this migration body
does NOT import from app.models. Schema is described inline with sa.Column /
sa.ForeignKey. A future model rename does not invalidate this migration.

Requirements traceability:
* CAFE-01 -- ~20-second log path requiring only cafe_name + rating
* CAFE-02 -- optional brand/roaster, origin, brew method, notes, flavor notes, photo
* CAFE-03 -- per-user, listed/viewable (user_id FK + ix_cafe_logs_user_logged_at)
* CAFE-04 -- cafe ratings, flavor notes, origin/roaster feed preference derivation (GIN index)
* CAFE-05 -- cafe logs excluded from brew-parameter analytics (no recipe_id / dose / yield fields)
* CAFE-06 -- user can edit and delete their own cafe logs (no immutable constraints)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "p16_cafe_logs"
# IMPORTANT: Phase 15.1 introduced four migrations. Current head is
# p15_1_varietal_m2m. Verified with `docker compose exec coffee-snobbery alembic heads`
# (Pitfall 4 from RESEARCH.md — down_revision must point to the current head).
down_revision: str | Sequence[str] | None = "p15_1_varietal_m2m"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create cafe_logs table + DESC B-tree + GIN indexes."""
    op.create_table(
        "cafe_logs",
        sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
        # Ownership — RESTRICT (user history is precious, mirrors brew_sessions.user_id)
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        # Optional shared-catalog reference — SET NULL (cafe log outlives the roaster)
        sa.Column(
            "roaster_id",
            sa.BigInteger,
            sa.ForeignKey("roasters.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Required field — plain TEXT (NOT CITEXT), per-user free-text (CONTEXT D-01)
        sa.Column("cafe_name", sa.Text, nullable=False),
        # Optional fields (CONTEXT D-03, D-05, Claude's discretion)
        sa.Column("origin_country", sa.Text, nullable=True),
        sa.Column("brew_method", sa.Text, nullable=True),
        # Rating: Numeric(3,2), 0-5 in 0.25 steps, mirrors brew_sessions.rating
        sa.Column("rating", sa.Numeric(3, 2), nullable=True),
        # Flavor notes: BIGINT[] NOT NULL DEFAULT '{}' (CONTEXT D-04)
        # GIN index is added below via op.execute (Pitfall 1: autogenerate cannot emit USING GIN)
        sa.Column(
            "flavor_note_ids",
            postgresql.ARRAY(sa.BigInteger),
            nullable=False,
            server_default=sa.text("'{}'::bigint[]"),
        ),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.Column("photo_filename", sa.Text, nullable=True),
        # logged_at is editable via form for backfilling tastings (Claude's discretion)
        sa.Column(
            "logged_at",
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

    # B-tree (DESC on logged_at) — raw SQL to carry the sort direction reliably.
    op.execute("CREATE INDEX ix_cafe_logs_user_logged_at ON cafe_logs (user_id, logged_at DESC)")
    # GIN — hand-edited (Pitfall 1: autogenerate cannot emit USING GIN for ARRAY columns).
    op.execute("CREATE INDEX ix_cafe_logs_flavor_note_ids ON cafe_logs USING GIN (flavor_note_ids)")


def downgrade() -> None:
    """Reverse the upgrade in FK-safe order.

    Drop indexes (raw GIN/B-tree with IF EXISTS for idempotency) before the
    table drop (mirrors p5_brew_sessions.py downgrade ordering).
    """
    op.execute("DROP INDEX IF EXISTS ix_cafe_logs_flavor_note_ids")
    op.execute("DROP INDEX IF EXISTS ix_cafe_logs_user_logged_at")
    op.drop_table("cafe_logs")
