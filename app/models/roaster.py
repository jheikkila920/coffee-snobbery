"""Shared catalog roaster (CAT-01) — household-shared, no user_id.

Phase 4 lands the five new household-shared catalog entities (roasters,
flavor_notes, coffees, equipment, recipes) per CONTEXT D-01. Every Phase 4
catalog model omits ``user_id`` deliberately — these tables are visible to
every household member; per-user state lives on ``brew_sessions`` (Phase 5)
and ``ai_recommendations`` (Phase 7).

Column choices for ``roasters`` (per 04-PATTERNS.md §roaster):

* ``name`` is ``CITEXT UNIQUE`` so ``"Onyx"`` and ``"onyx"`` collide — the
  household never accidentally ends up with two near-duplicate roaster
  cards. The CITEXT type is installed by ``0001_initial.py:59-61`` before
  Phase 4 references it.
* ``website`` is plain ``Text`` — the ``HttpUrl`` validation lives in the
  Pydantic schema layer (plan 04-02). The DB stores whatever the form
  layer accepted; we never trust the column on read.
* ``archived`` defaults to ``false`` and is the universal soft-delete
  signal for every Phase 4 entity. Hard delete is reserved for admin
  operations (plan 04-04+) and is gated on zero referencing rows.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Identity, Text, text
from sqlalchemy.dialects.postgresql import CITEXT, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class Roaster(Base):
    """A roaster the household buys coffee from. Shared across all users."""

    __tablename__ = "roasters"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    name: Mapped[str] = mapped_column(CITEXT(), nullable=False, unique=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
