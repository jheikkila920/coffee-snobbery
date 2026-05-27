"""Phase 15.1: Replace coffees.country/origin with coffee_origins join table (D-01/D-05).

Revision ID: p15_1_multi_origin
Revises: p11_brew_time_seconds
Create Date: 2026-05-27

Three steps in a single transaction:
1. CREATE TABLE coffee_origins with FK CASCADE on coffee_id.
2. INSERT data from coffees.country/origin using COALESCE (D-05 semantics).
3. DROP coffees.country and coffees.origin columns.

Data migration semantics (D-05):
  country = COALESCE(NULLIF(country, ''), NULLIF(origin, ''), 'Unknown')
  → coffees where both columns are NULL get NO coffee_origins row (correct:
    coffee can have unknown origin; downstream code handles empty origins list).

This is a forward-only migration (no rollback path) per project policy.
downgrade() is a no-op per the same convention as p4_shared_catalog.py.

Alembic-safe convention (mirrors p11_brew_time_seconds.py): this migration
body does NOT import from app.models. Schema is described inline with
sa.Column / sa.ForeignKey. A future model rename does not invalidate
this migration.

Requirements traceability:
* CATALOG-02 — coffees.country removed via safe migration
* CATALOG-03 — multi-origin as structured rows; coffee_origins join table
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "p15_1_multi_origin"
down_revision: str | Sequence[str] | None = "p11_brew_time_seconds"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create coffee_origins table, migrate data from coffees, drop old columns."""
    # 1. Create the coffee_origins join table (D-01).
    op.create_table(
        "coffee_origins",
        sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
        sa.Column(
            "coffee_id",
            sa.BigInteger,
            sa.ForeignKey("coffees.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("country", sa.Text, nullable=False),
        sa.Column("region", sa.Text, nullable=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_coffee_origins_coffee_id", "coffee_origins", ["coffee_id"])

    # 2. Migrate existing country/origin data from coffees table (D-05).
    #    COALESCE(NULLIF(country,''), NULLIF(origin,''), 'Unknown'):
    #    - If country is set (non-empty): use country.
    #    - Else if origin is set (non-empty): use origin.
    #    - Else: use 'Unknown' (but only for rows where at least one was not null).
    #    Coffees with BOTH country IS NULL AND origin IS NULL get NO row.
    op.execute("""
        INSERT INTO coffee_origins (coffee_id, country, region, sort_order)
        SELECT id,
               COALESCE(NULLIF(country, ''), NULLIF(origin, ''), 'Unknown') AS country,
               NULL AS region,
               0 AS sort_order
        FROM coffees
        WHERE country IS NOT NULL OR origin IS NOT NULL
    """)

    # 3. Drop the source columns — forward-only (no data preservation; pg_dump is recovery).
    op.drop_column("coffees", "country")
    op.drop_column("coffees", "origin")


def downgrade() -> None:
    """Forward-only migration — no rollback path per project policy."""
    # Per project convention: forward-only migrations are no-ops in downgrade().
    op.execute("SELECT 1")
