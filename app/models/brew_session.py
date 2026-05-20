"""``brew_sessions`` table (BREW-01) — the first per-user surface in the app.

Every other table shipped through Phase 4 is household-shared (no ``user_id``);
``brew_sessions`` is the first row that belongs to a single user. The
architectural invariant (CLAUDE.md): brew sessions and AI recommendations are
per-user; coffees / equipment / recipes / roasters / flavor notes are shared.

FK ``ondelete`` asymmetry (Task 0 + 05-PATTERNS.md §brew_session):

* ``user_id`` and ``coffee_id`` use ``ondelete="RESTRICT"``. A user's brew
  history must never silently vanish on a user delete (Phase 9 ADMIN-01 must
  handle a user's logs explicitly first); and a coffee with logged brews can't
  be hard-deleted out from under them. ``coffee_id`` mirrors ``bags.coffee_id``.
* ``bag_id`` / ``recipe_id`` / ``brewer_id`` / ``grinder_id`` / ``kettle_id``
  use ``ondelete="SET NULL"`` — a brew survives the deletion of the optional
  bag/recipe/equipment it referenced; the historical session row stays, the FK
  just nulls out (mirrors ``coffees.roaster_id``).

``extraction_yield_pct`` is a Postgres GENERATED column (Task 0 unit:
``tds_pct`` is a WHOLE PERCENT, e.g. 1.35 = 1.35%), so the stored expression is::

    (yield_grams_actual * tds_pct / 100.0) / dose_grams_actual * 100

which yields a whole-percent EY. The model declares it via ``Computed(...,
persisted=True)`` (renders ``GENERATED ALWAYS AS (...) STORED``); the migration
``p5_brew_sessions.py`` owns the literal DDL. NULL propagates automatically when
any operand is NULL. The column is read-only — it is NEVER written by app code
and is absent from every Create/Update schema (RESEARCH anti-pattern).

``flavor_note_ids_observed`` is ``BIGINT[]`` (mirrors
``coffees.advertised_flavor_note_ids``) rather than a join table: the
per-session "what I actually tasted" set is read-mostly, write-rare, and Phase 6
analytics needs index-served containment queries. The GIN index lives in the
migration via raw ``op.execute`` — SQLAlchemy 2.0 + Alembic autogenerate cannot
emit ``USING GIN``, so it is NOT declared in ``__table_args__`` here.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Computed,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base

# Task 0 resolved: tds_pct is a WHOLE PERCENT, so EY divides by 100 and
# re-multiplies to emit a whole-percent extraction yield. NULL on any operand
# propagates to NULL automatically.
_EY_EXPRESSION = "(yield_grams_actual * tds_pct / 100.0) / dose_grams_actual * 100"


class BrewSession(Base):
    """A single brew a user logged. Per-user (NOT household-shared)."""

    __tablename__ = "brew_sessions"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)

    # --- ownership + denormalized coffee (both RESTRICT) ------------------
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    coffee_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("coffees.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # --- optional references (all SET NULL) ------------------------------
    bag_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("bags.id", ondelete="SET NULL"),
        nullable=True,
    )
    recipe_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("recipes.id", ondelete="SET NULL"),
        nullable=True,
    )
    brewer_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("equipment.id", ondelete="SET NULL"),
        nullable=True,
    )
    grinder_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("equipment.id", ondelete="SET NULL"),
        nullable=True,
    )
    kettle_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("equipment.id", ondelete="SET NULL"),
        nullable=True,
    )

    # --- brew parameters --------------------------------------------------
    water_type: Mapped[str | None] = mapped_column(Text, nullable=True)  # D-07 select-or-Other
    dose_grams_actual: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    water_grams_actual: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    yield_grams_actual: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)  # D-02
    tds_pct: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)  # D-02, whole percent
    # GENERATED — read-only, never app-written. Migration owns the literal DDL.
    extraction_yield_pct: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        Computed(_EY_EXPRESSION, persisted=True),
        nullable=True,
    )
    water_temp_c_actual: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)  # 0-100
    grind_setting_actual: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)  # 0-5, 0.25 steps
    flavor_note_ids_observed: Mapped[list[int]] = mapped_column(
        ARRAY(BigInteger),
        nullable=False,
        server_default=text("'{}'::bigint[]"),
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    # --- timestamps -------------------------------------------------------
    brewed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # List default sort + recent-lookups; per-coffee prefill + dedup probe.
        Index("ix_brew_sessions_user_brewed_at", "user_id", text("brewed_at DESC")),
        Index(
            "ix_brew_sessions_user_coffee_brewed_at",
            "user_id",
            "coffee_id",
            text("brewed_at DESC"),
        ),
        # NOTE: the GIN index on flavor_note_ids_observed is NOT declared here.
        # SQLAlchemy 2.0 + Alembic autogenerate cannot emit `USING GIN`;
        # the migration p5_brew_sessions.py adds it via raw op.execute().
    )
