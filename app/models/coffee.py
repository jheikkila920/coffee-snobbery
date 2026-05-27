"""Shared catalog coffee (CAT-03) — the central table of Phase 4.

``name`` is ``CITEXT`` but NOT unique — different roasters legitimately sell
coffees with the same name (every roaster has an "Ethiopia Yirgacheffe").
The de-facto identity is ``(name, roaster_id)`` and the schema-layer
duplicate check (plan 04-04) enforces that pair at the application boundary;
the DB column stays open so admin imports can land near-duplicates and
clean them up in the UI rather than failing the import.

``roaster_id`` uses ``ondelete="SET NULL"`` (NOT RESTRICT) per
04-PATTERNS.md §coffee — a coffee can outlive its roaster. The opposite
direction is ``bags.coffee_id`` with ``ondelete="RESTRICT"`` (see
``app/models/bag.py``): once a household member has a bag of a coffee,
deleting the coffee fails loudly. Asymmetry is intentional.

``advertised_flavor_note_ids`` is ``BIGINT[]`` (Postgres array of
``flavor_notes.id``) rather than a join table. Two reasons:

1. The "advertised by the roaster" relationship is read-mostly and
   write-rare; an array is a single row update vs. join-table churn.
2. Phase 4's autocomplete picker needs sub-second containment queries
   ("coffees that mention these flavors"); the GIN index on this column
   (added in the migration via raw ``USING GIN``) makes those queries
   index-served. SQLAlchemy 2.0 + Alembic autogenerate cannot emit
   ``USING GIN`` — the migration hand-edits it.

The ``process`` / ``roast_level`` CHECK constraints are ``IS NULL OR ...``
shaped because both columns are nullable (the household may not always
know the process for an old bag); a non-null value must be from the locked
vocabulary, but ``NULL`` is the universal "unknown" sentinel.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base


class Coffee(Base):
    """A coffee SKU. Household-shared catalog row; per-user state lives on brew_sessions."""

    __tablename__ = "coffees"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    # NOT unique — different roasters can share a name (see module docstring).
    name: Mapped[str] = mapped_column(CITEXT(), nullable=False)
    roaster_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("roasters.id", ondelete="SET NULL"),
        nullable=True,
    )
    # country and origin columns removed in p15_1_multi_origin migration (D-05).
    # Use coffee.origins (relationship to CoffeeOrigin) for origin data.
    process: Mapped[str | None] = mapped_column(Text, nullable=True)
    roast_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    varietal: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    advertised_flavor_note_ids: Mapped[list[int]] = mapped_column(
        ARRAY(BigInteger),
        nullable=False,
        server_default=text("'{}'::bigint[]"),
    )
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    # Origin rows — one per origin entry. A single-origin coffee has one row;
    # a blend has >=2. is_blend is derived: len(coffee.origins) > 1 (D-22).
    origins: Mapped[list["CoffeeOrigin"]] = relationship(  # type: ignore[name-defined]
        "CoffeeOrigin",
        cascade="all, delete-orphan",
        order_by="CoffeeOrigin.sort_order",
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # CHECK constraints use ``IS NULL OR`` because both columns are nullable;
        # they mirror the Pydantic regex in plan 04-02 for defense in depth.
        CheckConstraint(
            "process IS NULL OR process IN "
            "('washed','natural','honey','anaerobic','experimental','unknown')",
            name="coffees_process_check",
        ),
        CheckConstraint(
            "roast_level IS NULL OR roast_level IN "
            "('light','medium-light','medium','medium-dark','dark','unknown')",
            name="coffees_roast_level_check",
        ),
        Index("ix_coffees_roaster_id", "roaster_id"),
        Index("ix_coffees_archived", "archived"),
        # NOTE: the GIN index on advertised_flavor_note_ids is NOT declared here.
        # SQLAlchemy 2.0 + Alembic autogenerate cannot emit `USING GIN`;
        # the migration p4_shared_catalog.py adds it via raw op.execute().
    )
