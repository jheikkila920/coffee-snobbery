"""``coffee_origins`` join table — structured origin rows per coffee (D-01).

One row per origin entry. A single-origin coffee has one row; a blend has
>=2. ``is_blend`` is DERIVED from ``len(coffee.origins) > 1`` — there is
NO stored boolean column (D-22).

``country`` is plain ``Text`` (NOT ``CITEXT UNIQUE``): multiple coffees
legitimately share country names, unlike flavor_note names. No ``percent``
column in v1 (D-02-orig).

``ondelete="CASCADE"`` on ``coffee_id``: origin rows die with their coffee.
The index ``ix_coffee_origins_coffee_id`` supports the common reverse lookup
"what origins does this coffee have?".

Migration: ``app/migrations/versions/p15_1_multi_origin.py``
"""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CoffeeOrigin(Base):
    """One origin entry in a coffee's origin list. Shared catalog row."""

    __tablename__ = "coffee_origins"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    coffee_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("coffees.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Plain Text — multiple coffees share country names (unlike flavor_notes CITEXT UNIQUE).
    country: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    __table_args__ = (Index("ix_coffee_origins_coffee_id", "coffee_id"),)
