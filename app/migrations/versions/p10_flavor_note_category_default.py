"""Phase 10: Add server_default 'other' to flavor_notes.category.

Revision ID: p10_flavor_note_category_default
Revises: p10_equipment_type_dripper
Create Date: 2026-05-22

The ``flavor_notes.category`` column is NOT NULL but had no server default.
This caused test seed helpers that insert FlavorNote rows without specifying
a category to fail with a NotNullViolation. Adding server_default='other'
makes the column self-describing: uncategorised flavor notes fall into the
'other' bucket, which is already a valid category per the CHECK constraint.

This is an ADDITIVE, non-lossy change: existing rows with an explicit
category are unaffected.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "p10_flavor_note_category_default"
down_revision: str | Sequence[str] | None = "p10_equipment_type_dripper"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "flavor_notes",
        "category",
        server_default=sa.text("'other'"),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "flavor_notes",
        "category",
        server_default=None,
        nullable=False,
    )
