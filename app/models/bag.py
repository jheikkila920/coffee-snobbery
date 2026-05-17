"""``bags`` table — physical coffee bags users own.

CAT-04 traceability: this table ships in Phase 0 even though the ``coffees``
catalog table doesn't exist until Phase 4. CONTEXT D-01 + planner discretion:
``coffee_id`` is ``BIGINT NOT NULL`` with NO ``ForeignKey`` constraint in
Phase 0. Phase 4's migration adds the FK once ``coffees`` exists.

The single-column index ``ix_bags_coffee_id`` supports the eventual
"bags of this coffee" reverse-lookup that Phase 4 / Phase 5 will need.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, Identity, Index, Integer, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class Bag(Base):
    """A physical bag of coffee. ``coffee_id`` FK lands in Phase 4."""

    __tablename__ = "bags"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    # coffee_id FK constraint is DEFERRED to Phase 4 when `coffees` exists.
    # Ship as NOT NULL BigInteger so Phase 4 can add the FK without
    # re-tightening nullability on a populated table.
    coffee_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    roast_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    weight_grams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_bags_coffee_id", "coffee_id"),)
