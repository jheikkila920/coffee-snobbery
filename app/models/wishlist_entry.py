"""``wishlist_entries`` table — coffees a user wants to try.

CONTEXT D-01: present from day one so Phase 7's AI rec card can write into
this table without a schema add. CRUD UI lands whenever it's needed
(Phase 4 or Phase 7).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class WishlistEntry(Base):
    """A user's want-to-try coffee. Sources: 'ai_recommendation' or 'manual'."""

    __tablename__ = "wishlist_entries"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    coffee_name: Mapped[str] = mapped_column(Text, nullable=False)
    roaster_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # e.g. "ai_recommendation" | "manual"; free-form text by design (planner
    # decided text-not-enum per RESEARCH §Notes on schema choices).
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    added_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    purchased_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (Index("ix_wishlist_entries_user_id", "user_id"),)
