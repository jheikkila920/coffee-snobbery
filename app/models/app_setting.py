"""``app_settings`` table — key/value runtime configuration.

Phase 0 seeds 19 documented rows in ``0001_initial.py`` (CONTEXT D-17).
Phase 9 ships the admin editor that mutates these rows; Phase 2 reads the
``setup_completed`` row under ``SELECT ... FOR UPDATE`` to defend against
race conditions during initial setup (SEC-5).

``value_type`` is text (not a Postgres enum) so adding a new type doesn't
require a migration. The Phase 9 admin editor will use this column to pick
the right input control. Recognised values: 'string', 'int', 'float',
'bool', 'json', 'null'.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class AppSetting(Base):
    """One row of admin-tunable runtime config."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    # NULL is valid (see seed row last_backup_at); value_type='null' encodes
    # the typed-null case the Phase 9 admin editor must render distinctly.
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_type: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
