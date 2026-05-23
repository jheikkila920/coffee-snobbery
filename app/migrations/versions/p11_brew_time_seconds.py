"""Phase 11: add brew_time_seconds to brew_sessions (D-10).

Revision ID: p11_brew_time_seconds
Revises: p10_search_indexes
Create Date: 2026-05-23

Additive nullable column — no data migration required. Safe to run on
production with existing data. downgrade() drops the column.

Alembic-safe convention (mirrors p5_brew_sessions.py:32-35): this
migration body does NOT import from app.models.

Requirements traceability:
* BREW-12 — brew_time_seconds column for Guided Brew Mode elapsed time
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "p11_brew_time_seconds"
down_revision: str | Sequence[str] | None = "p10_search_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable brew_time_seconds integer column to brew_sessions."""
    op.add_column(
        "brew_sessions",
        sa.Column("brew_time_seconds", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Drop brew_time_seconds column from brew_sessions."""
    op.drop_column("brew_sessions", "brew_time_seconds")
