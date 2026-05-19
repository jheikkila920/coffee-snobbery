"""Shared catalog equipment (CAT-05) — brewers, grinders, kettles, scales, etc.

``type`` CHECK constraint matches the Pydantic regex in plan 04-02. The
6-value vocabulary covers every gear category the household actively
tracks; "other" is the escape hatch for one-offs (filter holder, dripper
shower screen) that don't deserve their own category.

``usage_count`` is a denormalized counter that ships at ``0`` in Phase 4
and is incremented by Phase 5's brew-session service when a session
references the equipment. The denormalization is the load-bearing
optimization for the home page's "most-used grinder" widget — recomputing
from ``brew_sessions`` on every page load would scan the whole table.

Like every Phase 4 catalog model, ``Equipment`` is household-shared (no
``user_id``). Multiple household members borrowing the same kettle is the
common case, not the exception.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Identity,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class Equipment(Base):
    """A piece of brewing gear. Household-shared catalog row."""

    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # Denormalized counter; Phase 5 brew-session service increments on insert.
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "type IN ('brewer','grinder','kettle','scale','water_filter','other')",
            name="equipment_type_check",
        ),
        Index("ix_equipment_type", "type"),
    )
