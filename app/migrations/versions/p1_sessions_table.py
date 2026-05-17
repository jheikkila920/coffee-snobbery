"""p1_sessions: create the sessions table (AUTH-05; D-07 schema)

Revision ID: p1_sessions
Revises: 0001_initial
Create Date: 2026-05-17

Schema is locked to **exactly the five columns** in CONTEXT D-07. No
``ip``, ``user_agent``, or ``device_label`` — minimal-storage footprint is
the mitigation for T-04-05 (information disclosure from a session-table
dump). Adding columns here breaks the privacy contract; if a future phase
needs device labelling, it lands as its own migration with an explicit
decision record, not as a quiet column add.

Indexes:

* PK on ``session_id`` (UUID; Postgres builds a btree automatically).
* btree on ``user_id`` so Phase 9's "active sessions per user" admin
  query is index-served.
* btree on ``expires_at`` so the Phase 8 cleanup job
  (``DELETE FROM sessions WHERE expires_at < now()``) is index-served.

``user_id`` is ``BigInteger`` to match ``users.id`` (also BigInteger in
0001_initial). Using ``Integer`` would silently truncate at 2^31.

Requirements traceability:

* AUTH-05 — table-backed sessions, 30-day expiry, sliding refresh
* D-07    — exact column inventory (no additions)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "p1_sessions"
down_revision: str | Sequence[str] | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the sessions table per D-07 — exactly five columns."""
    op.create_table(
        "sessions",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])


def downgrade() -> None:
    """Drop the sessions table and its secondary indexes."""
    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
