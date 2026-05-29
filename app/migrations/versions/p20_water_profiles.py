"""Phase 20: water_profiles table + seed from water_type + brew_session timing columns.

Revision ID: p20_water_profiles
Revises: p19_ai_research_predict
Create Date: 2026-05-29

Five steps in a single transaction:
1. CREATE TABLE water_profiles (id, name UNIQUE, notes, timestamps).
2. INSERT DISTINCT INITCAP(TRIM(water_type)) from brew_sessions (dedup + normalize).
3. ADD COLUMN brew_sessions.water_profile_id (BigInteger FK SET NULL, nullable).
4. UPDATE brew_sessions: link each row to the matching water_profile via INITCAP(TRIM).
5. ADD COLUMN brew_sessions.first_drip_seconds (Integer nullable).
   ADD COLUMN brew_sessions.bloom_time_seconds (Integer nullable).

Data migration semantics (D-03):
  - Only non-NULL, non-blank water_type values create water_profiles rows.
  - INITCAP(TRIM(water_type)) normalizes casing + trims whitespace: "tap", "Tap",
    "TAP" all collapse to "Tap" (one profile row).
  - Brew sessions with NULL or blank water_type get water_profile_id = NULL.
    No "Unknown" / "Unspecified" placeholder profile is created (A2).

water_type column is RETAINED (deprecated) — it is NOT dropped this phase.
New sessions will use water_profile_id; water_type stays for backward compat (D-12).

Alembic-safe convention: this migration body does NOT import from app.models.
Schema is described inline with sa.Column / sa.ForeignKey so a future model
rename does not invalidate this migration.

Requirements traceability:
  D-01  — water_profiles table (shared catalog)
  D-03  — seed from distinct normalized water_type values; link historical sessions
  D-12  — water_type retained (deprecated); water_profile_id nullable FK
  GBREW-04 — water profile catalog available for brew form
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "p20_water_profiles"
down_revision: str | Sequence[str] | None = "p19_ai_research_predict"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create water_profiles, seed from brew_sessions.water_type, add FK + timing columns."""

    # 1. Create the water_profiles shared-catalog table (D-01).
    op.create_table(
        "water_profiles",
        sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column("notes", sa.Text, nullable=True),
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
    op.create_index("ix_water_profiles_name", "water_profiles", ["name"])

    # 2. Seed from distinct normalized water_type values (D-03).
    #    INITCAP(TRIM(water_type)) normalizes casing and trims whitespace.
    #    Blank/NULL water_type values produce zero rows — no Unknown profile (A2).
    op.execute("""
        INSERT INTO water_profiles (name)
        SELECT DISTINCT INITCAP(TRIM(water_type)) AS name
        FROM brew_sessions
        WHERE water_type IS NOT NULL
          AND TRIM(water_type) != ''
        ORDER BY INITCAP(TRIM(water_type))
    """)

    # 3. Add water_profile_id FK column to brew_sessions (nullable, SET NULL on delete).
    op.add_column(
        "brew_sessions",
        sa.Column(
            "water_profile_id",
            sa.BigInteger,
            sa.ForeignKey("water_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_brew_sessions_water_profile_id",
        "brew_sessions",
        ["water_profile_id"],
    )

    # 4. Link historical brew sessions to matching water_profile rows (D-03).
    #    Sessions with NULL/blank water_type stay NULL (no Unknown profile, A2).
    op.execute("""
        UPDATE brew_sessions bs
        SET water_profile_id = wp.id
        FROM water_profiles wp
        WHERE INITCAP(TRIM(bs.water_type)) = wp.name
          AND bs.water_type IS NOT NULL
          AND TRIM(bs.water_type) != ''
    """)

    # 5. Add brew timing columns (GBREW-03 / D-12..D-14).
    #    water_type column is RETAINED (deprecated) — NOT dropped this phase.
    op.add_column("brew_sessions", sa.Column("first_drip_seconds", sa.Integer, nullable=True))
    op.add_column("brew_sessions", sa.Column("bloom_time_seconds", sa.Integer, nullable=True))


def downgrade() -> None:
    """Reverse the upgrade in reverse order — drop timing, drop FK, drop table."""
    op.drop_column("brew_sessions", "bloom_time_seconds")
    op.drop_column("brew_sessions", "first_drip_seconds")
    op.drop_index("ix_brew_sessions_water_profile_id", table_name="brew_sessions")
    op.drop_column("brew_sessions", "water_profile_id")
    op.drop_index("ix_water_profiles_name", table_name="water_profiles")
    op.drop_table("water_profiles")
