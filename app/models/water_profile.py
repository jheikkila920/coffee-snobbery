"""Shared-catalog water profile (GBREW-04, D-01).

Household-shared: all users see the same water profiles catalog.
No per-user ownership gate — mirrors flavor_notes, coffees, equipment, etc.

``name`` is plain ``Text`` with a UNIQUE constraint. The migration handles
deduplication via INITCAP(TRIM(water_type)) normalization rather than using
CITEXT, because the normalization is a one-time migration operation and new
profiles are created via the validated form (WaterProfileCreate ensures
consistent casing at the app layer).

No ``archived`` column: water profiles are not soft-deleted in Phase 20.
No ``category`` or ``CheckConstraint``: profiles are free-text names.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Identity, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class WaterProfile(Base):
    """Household-shared water profile catalog (GBREW-04, D-01)."""

    __tablename__ = "water_profiles"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
