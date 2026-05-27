"""Phase 15.1: widen coffees_roast_level_check with ultra-light + nordic-light (CATALOG-04).

Revision ID: p15_1_roast_level_enum
Revises: p15_1_drop_roast_date
Create Date: 2026-05-27

Drops and recreates the coffees_roast_level_check CHECK constraint to add
'ultra-light' and 'nordic-light' at the lighter end of the spectrum.

All six original values remain valid. Existing data is untouched.

Alembic-safe convention (mirrors p4_shared_catalog.py): this migration body
does NOT import from app.models. Schema described inline via op.execute.

Requirements traceability:
* CATALOG-04 -- roast-level enum widening (Claude's discretion per CONTEXT.md)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa  # noqa: F401 — kept for consistency with peer migrations
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "p15_1_roast_level_enum"
down_revision: str | Sequence[str] | None = "p15_1_drop_roast_date"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop the six-value constraint, then recreate with eight values.
    # op.execute is unambiguous on all dialects and avoids Alembic's
    # dialect-sensitive op.drop_constraint path (PATTERNS.md CATALOG-04).
    op.execute("ALTER TABLE coffees DROP CONSTRAINT coffees_roast_level_check")
    op.execute(
        "ALTER TABLE coffees ADD CONSTRAINT coffees_roast_level_check "
        "CHECK (roast_level IS NULL OR roast_level IN "
        "('ultra-light','nordic-light','light','medium-light','medium','medium-dark','dark','unknown'))"
    )


def downgrade() -> None:
    # Restore the original six-value constraint.
    op.execute("ALTER TABLE coffees DROP CONSTRAINT coffees_roast_level_check")
    op.execute(
        "ALTER TABLE coffees ADD CONSTRAINT coffees_roast_level_check "
        "CHECK (roast_level IS NULL OR roast_level IN "
        "('light','medium-light','medium','medium-dark','dark','unknown'))"
    )
