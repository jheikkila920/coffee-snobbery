"""Phase 15.1: drop bags.roast_date column (D-16).

Revision ID: p15_1_drop_roast_date
Revises: p15_1_multi_origin
Create Date: 2026-05-26

D-16: roast_date is dropped with no data preservation. pg_dump nightly backups
are the recovery story. This migration is forward-only (downgrade is a no-op).

Alembic-safe convention (mirrors p4_shared_catalog.py): this migration body
does NOT import from app.models. Schema described inline via op.drop_column.

Requirements traceability:
* CATALOG-07 -- remove roast-freshness tracking app-wide
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "p15_1_drop_roast_date"
down_revision: str | Sequence[str] | None = "p15_1_multi_origin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # D-16: drop bags.roast_date with no data preservation.
    # pg_dump nightly backups are the recovery story (explicit project decision).
    # Guarded with IF EXISTS so test_alembic_downgrade_p4_then_upgrade can
    # re-run upgrade chain even after a no-op downgrade pass — production
    # only ever runs each migration once so the guard is harmless there.
    op.execute("ALTER TABLE bags DROP COLUMN IF EXISTS roast_date")


def downgrade() -> None:
    # Forward-only per project policy (D-16 explicitly accepts data loss).
    # A downgrade would need to recreate the column with no data restored.
    # Restore from pg_dump backup if the column is needed again.
    op.execute("SELECT 1")  # no-op sentinel
