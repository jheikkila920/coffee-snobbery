"""p3_api_credentials: api_credentials table + seed + new app_settings row

Revision ID: p3_api_credentials
Revises: p1_sessions
Create Date: 2026-05-18

Creates the ``api_credentials`` table (Phase 3 D-01..D-04), seeds two
provider rows (``'anthropic'``, ``'openai'``) with ``is_enabled=false``
and ``key_ciphertext=NULL`` per D-04, and inserts the new
``encryption_key_primary_fingerprint`` row into ``app_settings``
(``value=NULL``, ``value_type='null'``) so D-14's rotation detector has a
row to read on first lifespan startup.

Schema choices locked here:

* ``provider`` is ``Text`` with a CHECK constraint
  (``api_credentials_provider_check``) — the Claude's-discretion pick over a
  Postgres ENUM. Adding a third provider later is a CHECK swap, not a type
  migration.
* ``key_ciphertext`` is ``LargeBinary`` (``bytea``) — Fernet's bytes contract
  end-to-end, no base64 round-trips that could land plaintext-adjacent
  encoded blobs in log capture.
* No indexes beyond the implicit PK on ``provider`` — the table is bounded
  to two rows.
* All defaults are ``server_default`` — Postgres is the source of truth; no
  Python-side ``default=`` is used so a raw INSERT sees the same shape an
  ORM INSERT sees.

Alembic-safe convention: this migration body MUST NOT import from
``app.models``. The lightweight ``sa.table()`` + ``op.bulk_insert()``
pattern (matching ``0001_initial.py``) keeps the migration replayable even
if the ORM model is renamed in a later phase.

Requirements traceability:

* SEC-08 — Fernet-encrypted API keys at rest (MultiFernet day-one)
* SEC-09 — Fingerprint storage enables auto-rewrap on rotation
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "p3_api_credentials"
down_revision: str | Sequence[str] | None = "p1_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``api_credentials``, seed two provider rows, add new app_settings row."""
    # ---- 1) Create the table ----------------------------------------------
    op.create_table(
        "api_credentials",
        sa.Column("provider", sa.Text, primary_key=True),
        sa.Column("key_ciphertext", sa.LargeBinary, nullable=True),
        sa.Column("last_four", sa.Text, nullable=True),
        sa.Column("model_name", sa.Text, nullable=True),
        sa.Column(
            "is_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
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
        sa.Column(
            "updated_by_user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "provider IN ('anthropic', 'openai')",
            name="api_credentials_provider_check",
        ),
    )

    # ---- 2) Seed both provider rows (D-04) --------------------------------
    # Lightweight sa.table() used here so the migration body does NOT import
    # app.models (Alembic-safe pattern from 0001_initial.py:222-228). Only
    # ``provider`` and ``is_enabled`` are inserted explicitly; every other
    # column defaults to NULL or its server_default. is_enabled is set to
    # False explicitly to keep the seed intent loud — admin must opt-in.
    api_credentials_table = sa.table(
        "api_credentials",
        sa.column("provider", sa.Text),
        sa.column("is_enabled", sa.Boolean),
    )
    op.bulk_insert(
        api_credentials_table,
        [
            {"provider": "anthropic", "is_enabled": False},
            {"provider": "openai", "is_enabled": False},
        ],
    )

    # ---- 3) Insert the new app_settings row for D-14 rotation detector ----
    app_settings_table = sa.table(
        "app_settings",
        sa.column("key", sa.Text),
        sa.column("value", sa.Text),
        sa.column("value_type", sa.Text),
        sa.column("description", sa.Text),
    )
    op.bulk_insert(
        app_settings_table,
        [
            {
                "key": "encryption_key_primary_fingerprint",
                "value": None,
                "value_type": "null",
                "description": (
                    "SHA-256 hex of the current primary Fernet key; "
                    "written by credentials.rewrap_if_needed when the "
                    "key rotates (D-14)."
                ),
            },
        ],
    )


def downgrade() -> None:
    """Reverse the migration: drop the new app_settings row, then the table."""
    op.execute("DELETE FROM app_settings WHERE key = 'encryption_key_primary_fingerprint'")
    op.drop_table("api_credentials")
