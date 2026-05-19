"""Shared catalog flavor note (CAT-02).

9-value category CHECK matches Pydantic schema regex (plan 04-02) for
defense in depth: a direct SQL ``INSERT INTO flavor_notes (name, category)
VALUES ('foo', 'bogus')`` bypassing the schema layer still fails at the DB
boundary. The category set is fixed for Phase 4; expanding it is a CHECK
swap migration plus a schema-regex change, not a type migration.

``name`` is ``CITEXT UNIQUE`` — ``"Citrus"`` and ``"citrus"`` collide. This
is the load-bearing assumption for plan 04-11's flavor-note autocomplete
("create-if-missing" must never produce two near-duplicate notes).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Identity, Text, text
from sqlalchemy.dialects.postgresql import CITEXT, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class FlavorNote(Base):
    """A flavor descriptor (e.g. 'blueberry', 'jasmine'). Shared across the household."""

    __tablename__ = "flavor_notes"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    name: Mapped[str] = mapped_column(CITEXT(), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "category IN ('fruit','floral','sweet','chocolate','nutty',"
            "'spice','savory','fermented','other')",
            name="flavor_notes_category_check",
        ),
    )
