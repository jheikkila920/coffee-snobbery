"""Varietal model + coffee_varietals association table (CATALOG-05).

Varietals are shared catalog items — 'Geisha', 'Bourbon', 'Typica', etc.
CITEXT UNIQUE on name collapses case variants ('Geisha'/'geisha'/'GEISHA').

coffee_varietals is a pure join table (no ORM class) — SQLAlchemy 2.0 style.
Cascade semantics:
  - coffee_id ON DELETE CASCADE: varietal join rows die with the coffee.
  - varietal_id ON DELETE RESTRICT: can't delete a varietal still in use.

No 'archived' column — varietals are managed via the join table, not soft-deleted.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Column, ForeignKey, Identity, Table
from sqlalchemy.dialects.postgresql import CITEXT, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class Varietal(Base):
    """A coffee plant variety. Shared catalog; not per-user."""

    __tablename__ = "varietals"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    name: Mapped[str] = mapped_column(CITEXT(), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


# Association table — no ORM class, just a Table object (SQLAlchemy 2.0 style).
# Cascade semantics mirror the spec (D-02):
#   coffee_id  ON DELETE CASCADE  — join rows die with the coffee
#   varietal_id ON DELETE RESTRICT — can't delete a varietal still referenced
coffee_varietals = Table(
    "coffee_varietals",
    Base.metadata,
    Column(
        "coffee_id",
        BigInteger,
        ForeignKey("coffees.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "varietal_id",
        BigInteger,
        ForeignKey("varietals.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
)
