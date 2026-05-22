"""Phase 10: Add 'dripper' to equipment_type_check constraint.

Revision ID: p10_equipment_type_dripper
Revises: p10_search_indexes
Create Date: 2026-05-22

A dripper (e.g. Hario V60, Chemex, Kalita Wave) is a distinct category of
pour-over brewing equipment. The Phase 4 check constraint omitted it because
the initial 6-value vocabulary used 'brewer' as a catch-all. Phase 10 search
tests treat drippers as a first-class type; this migration adds 'dripper' to
the constraint to reflect that reality.

This is an ADDITIVE, non-lossy change: existing 'brewer' rows remain valid.
No data migration required.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "p10_equipment_type_dripper"
down_revision: str | Sequence[str] | None = "p10_search_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # DROP and re-ADD the check constraint to include 'dripper'.
    # PostgreSQL does not support ALTER CHECK CONSTRAINT directly.
    op.execute("ALTER TABLE equipment DROP CONSTRAINT IF EXISTS equipment_type_check")
    op.execute(
        "ALTER TABLE equipment ADD CONSTRAINT equipment_type_check "
        "CHECK (type IN ('brewer','dripper','grinder','kettle','scale','water_filter','other'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE equipment DROP CONSTRAINT IF EXISTS equipment_type_check")
    op.execute(
        "ALTER TABLE equipment ADD CONSTRAINT equipment_type_check "
        "CHECK (type IN ('brewer','grinder','kettle','scale','water_filter','other'))"
    )
