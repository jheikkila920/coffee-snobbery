"""``bags`` table — physical coffee bags users own.

CAT-04 traceability: this table ships in Phase 0 with ``coffee_id`` as a
plain ``BigInteger NOT NULL`` (no FK constraint) because the ``coffees``
catalog table doesn't exist until Phase 4. Phase 4 added the FK constraint
per CONTEXT canonical_refs once ``coffees`` was created — the FK uses
``ondelete="RESTRICT"`` (NOT CASCADE): once a household member has a bag
of a coffee, hard-deleting the coffee fails loudly with an IntegrityError.
This pairs with the archive-only policy from plan 04-04 (coffees should be
soft-deleted, not hard-deleted, in normal admin flows); RESTRICT is the DB
boundary that backstops the policy if it ever slips.

``photo_filename`` (CAT-08) was added in plan 04-03 — a UUID-shaped
basename (e.g. ``8f0a..-...-d3b1.jpg``) that the photos serving route
(plan 04-10) resolves against ``PHOTOS_DIR`` after passing the safe-
filename regex from ``app.services.photos``. The column is NULLABLE: a
bag may not have a photo. The photos service's orphan sweep (plan 04-01
+ Phase 8 scheduler) queries this column to compute the
``{filesystem set} - {referenced set}`` diff.

The single-column index ``ix_bags_coffee_id`` supports both the "bags of
this coffee" reverse lookup AND the implicit B-tree the FK constraint
creates — Postgres does NOT auto-index FK source columns, so this index
is still load-bearing.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, Integer, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class Bag(Base):
    """A physical bag of coffee. Phase 4 added the FK to ``coffees`` + ``photo_filename``."""

    __tablename__ = "bags"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    # Phase 4 added the FK constraint with ondelete='RESTRICT' — hard-delete
    # of a referenced coffee fails loudly with IntegrityError. Combined with
    # the archive-only policy in plan 04-04, coffees are never hard-deleted
    # in practice; RESTRICT is the load-bearing backstop if the policy slips.
    coffee_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("coffees.id", ondelete="RESTRICT"),
        nullable=False,
    )
    weight_grams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # CAT-08: UUID-shaped basename validated by app.services.photos._is_safe_photo_filename.
    # NULL = bag has no photo. Orphan sweep (Phase 8) joins on this column.
    photo_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_bags_coffee_id", "coffee_id"),)
