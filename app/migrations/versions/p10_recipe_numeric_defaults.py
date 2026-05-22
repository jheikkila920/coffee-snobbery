"""Phase 10: Add server defaults (0) to recipes numeric columns.

Revision ID: p10_recipe_numeric_defaults
Revises: p10_flavor_note_category_default
Create Date: 2026-05-22

The ``recipes.dose_grams``, ``recipes.water_grams``, and ``recipes.water_temp_c``
columns are NOT NULL but had no server defaults. Test seed helpers that insert
Recipe rows with only name and grind_setting fail with NotNullViolation.

Adding server_default=0 to all three numeric columns allows minimal recipe seeds
(name + grind_setting only) to succeed. The value 0 signals "not specified" in
the domain and aligns with the existing grind_setting="" empty-string default.

This is ADDITIVE and non-lossy: existing rows with explicit values are unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "p10_recipe_numeric_defaults"
down_revision: str | Sequence[str] | None = "p10_flavor_note_category_default"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("recipes", "dose_grams", server_default=sa.text("0"), nullable=False)
    op.alter_column("recipes", "water_grams", server_default=sa.text("0"), nullable=False)
    op.alter_column("recipes", "water_temp_c", server_default=sa.text("0"), nullable=False)


def downgrade() -> None:
    op.alter_column("recipes", "dose_grams", server_default=None, nullable=False)
    op.alter_column("recipes", "water_grams", server_default=None, nullable=False)
    op.alter_column("recipes", "water_temp_c", server_default=None, nullable=False)
