"""Shared catalog recipe (CAT-06) — a brewing template (dose / water / temp / grind + steps).

``steps`` is JSONB rather than a normalized ``recipe_steps`` table for the
same reason ``coffees.advertised_flavor_note_ids`` is an array: read-mostly,
write-rare, ordered list with per-step free-form fields (label, water_grams,
time_seconds, optional notes). A normalized table buys nothing at household
scale and complicates the "edit step 3" UX in plan 04-08.

The numeric columns (``dose_grams``, ``water_grams``, ``water_temp_c``,
``grind_setting``) are denormalized into the recipe row even though every
step in the JSONB list also carries water/time data. Rationale: the
top-level numbers are the *target* for the recipe; the step list is the
*pour schedule*. A user can read a recipe's headline ratio without parsing
the JSONB.

``grind_setting`` is ``Text NOT NULL`` with ``server_default=""`` because
grind settings are grinder-specific magic numbers ("Comandante click 22",
"EK43 4.2") that the household captures as free text. Plan 04-08's
schema-layer validator caps the length.

Like every Phase 4 catalog model, ``Recipe`` is household-shared (no
``user_id``).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Identity, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class Recipe(Base):
    """A brewing recipe template. Household-shared catalog row."""

    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    dose_grams: Mapped[int] = mapped_column(Integer, nullable=False)
    water_grams: Mapped[int] = mapped_column(Integer, nullable=False)
    water_temp_c: Mapped[int] = mapped_column(Integer, nullable=False)
    grind_setting: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # Ordered list of step dicts: [{label, water_grams, time_seconds, ...}, ...].
    # Per-step shape is enforced by the Pydantic schema in plan 04-02, not by
    # a JSON Schema constraint on the column (Postgres-side JSON validation
    # would duplicate Pydantic and lock the shape too early for Phase 5+ to
    # extend without a CHECK swap).
    steps: Mapped[list[dict]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
