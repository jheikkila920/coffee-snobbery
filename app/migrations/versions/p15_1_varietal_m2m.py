"""Phase 15.1: varietal m2m tables + 14-row seed + drop coffees.varietal (CATALOG-05).

Revision ID: p15_1_varietal_m2m
Revises: p15_1_roast_level_enum
Create Date: 2026-05-27

Creates:
  varietals (id BIGINT IDENTITY PK, name CITEXT UNIQUE NOT NULL, created_at TIMESTAMP)
  coffee_varietals (coffee_id FK CASCADE, varietal_id FK RESTRICT, composite PK)

Seeds 14 common varietals per D-04 in the exact specified order.

Drops coffees.varietal (the free-text single-value column) — replaced by the
coffee_varietals join table. No data preservation (the column was free text;
structured data now lives in the varietals catalog).

This migration is forward-only for the DROP COLUMN step. The table creations
have a corresponding downgrade that drops the tables.

Alembic-safe convention (mirrors p4_shared_catalog.py): this migration body
does NOT import from app.models. Schema described inline via sa.Column etc.

Requirements traceability:
* CATALOG-05 -- varietal m2m with autocomplete and create-on-the-fly UX
* D-02 -- varietals (id, name CITEXT UNIQUE, created_at) + coffee_varietals join table
* D-03 -- any authenticated user can create a new varietal on the fly
* D-04 -- bulk seed 14 varietals in exact order specified
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "p15_1_varietal_m2m"
down_revision: str | Sequence[str] | None = "p15_1_roast_level_enum"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create varietals table.
    op.create_table(
        "varietals",
        sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
        sa.Column("name", postgresql.CITEXT(), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # 2. Create coffee_varietals join table.
    op.create_table(
        "coffee_varietals",
        sa.Column(
            "coffee_id",
            sa.BigInteger,
            sa.ForeignKey("coffees.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "varietal_id",
            sa.BigInteger,
            sa.ForeignKey("varietals.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
    )

    # 3. Seed 14 common varietals per D-04 in exact specified order.
    varietals_t = sa.table(
        "varietals",
        sa.column("name", postgresql.CITEXT()),
        sa.column("created_at", sa.TIMESTAMP(timezone=True)),
    )
    op.bulk_insert(
        varietals_t,
        [
            {"name": "Bourbon", "created_at": sa.func.now()},
            {"name": "Typica", "created_at": sa.func.now()},
            {"name": "Caturra", "created_at": sa.func.now()},
            {"name": "Catuai", "created_at": sa.func.now()},
            {"name": "Geisha", "created_at": sa.func.now()},
            {"name": "Pacamara", "created_at": sa.func.now()},
            {"name": "SL28", "created_at": sa.func.now()},
            {"name": "SL34", "created_at": sa.func.now()},
            {"name": "Mundo Novo", "created_at": sa.func.now()},
            {"name": "Pacas", "created_at": sa.func.now()},
            {"name": "Heirloom", "created_at": sa.func.now()},
            {"name": "Maragogype", "created_at": sa.func.now()},
            {"name": "Castillo", "created_at": sa.func.now()},
            {"name": "Catimor", "created_at": sa.func.now()},
        ],
    )

    # 4. Drop coffees.varietal (replaced by the join table above).
    # The column was free-text; no data migration needed (D-02).
    op.drop_column("coffees", "varietal")


def downgrade() -> None:
    # Drop tables (the DROP COLUMN for coffees.varietal is not reversed
    # since that would require recreating the column with lost data).
    op.drop_table("coffee_varietals")
    op.drop_table("varietals")
