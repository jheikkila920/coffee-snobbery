"""``cafe_logs`` table (CAFE-01..06) — per-user cafe tasting log.

A per-user surface capturing a coffee tasted outside the home in ~20 seconds.
Separate from ``brew_sessions`` by design: ``brew_sessions.coffee_id`` is
``NOT NULL ondelete=RESTRICT``, making a unified table architecturally
impossible (CONTEXT D-01).

FK ``ondelete`` asymmetry mirrors ``brew_sessions``:

* ``user_id`` uses ``ondelete="RESTRICT"`` — cafe history must never silently
  vanish on a user delete (mirrors BrewSession invariant, CONTEXT §Claude's
  discretion, threat T-16-01-01).
* ``roaster_id`` uses ``ondelete="SET NULL"`` — a cafe log survives a roaster
  delete (CONTEXT D-02).

``cafe_name`` and ``origin_country`` are plain ``Text``, NOT CITEXT — they are
per-user free-text fields, not shared-catalog identities (CONTEXT D-01 / D-03;
mirrors ``coffee_origins.country`` precedent).

``flavor_note_ids`` is ``BIGINT[]`` (mirrors
``brew_sessions.flavor_note_ids_observed``) rather than a join table: the GIN
index lives in the migration via raw ``op.execute`` — SQLAlchemy 2.0 + Alembic
autogenerate cannot emit ``USING GIN``, so it is NOT declared in
``__table_args__`` here.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, Numeric, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class CafeLog(Base):
    """A single cafe tasting a user logged. Per-user (NOT household-shared)."""

    __tablename__ = "cafe_logs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)

    # --- ownership (RESTRICT) -----------------------------------------------
    # ondelete="RESTRICT" — user history is precious (mirrors BrewSession.user_id)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # --- optional shared-catalog reference (SET NULL) -----------------------
    # ondelete="SET NULL" — cafe log survives a roaster delete (mirrors BrewSession optional FKs)
    roaster_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("roasters.id", ondelete="SET NULL"),
        nullable=True,
    )

    # --- required fields ----------------------------------------------------
    # plain TEXT (NOT CITEXT) — per-user free-text, not a shared catalog identity (CONTEXT D-01)
    cafe_name: Mapped[str] = mapped_column(Text, nullable=False)

    # --- optional fields (D-03 / D-05 / Claude's discretion) ---------------
    # Plain TEXT, no FK, no countries table (CONTEXT D-03)
    origin_country: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Free-text, no enum, no FK (CONTEXT D-05)
    brew_method: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- rating (same precision as BrewSession.rating) ----------------------
    # Numeric(3,2) — 0-5 in 0.25 steps; nullable for "still thinking" entries
    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)

    # --- flavor notes (GIN-indexed BIGINT[]) --------------------------------
    # NOTE: GIN on flavor_note_ids is NOT declared here.
    # SQLAlchemy 2.0 + Alembic autogenerate cannot emit `USING GIN`;
    # the migration p16_cafe_logs.py adds it via raw op.execute().
    flavor_note_ids: Mapped[list[int]] = mapped_column(
        ARRAY(BigInteger),
        nullable=False,
        server_default=text("'{}'::bigint[]"),
    )

    # --- text fields --------------------------------------------------------
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    photo_filename: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- timestamps ---------------------------------------------------------
    # logged_at is editable via form for backfilling tastings (CONTEXT §Claude's discretion)
    logged_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # List default sort: user's tastings ordered newest-first.
        Index("ix_cafe_logs_user_logged_at", "user_id", text("logged_at DESC")),
        # NOTE: GIN on flavor_note_ids is NOT declared here — see migration p16_cafe_logs.py
    )
