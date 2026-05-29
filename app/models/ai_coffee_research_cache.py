"""``ai_coffee_research_cache`` table — shared world-view research cache (D-06).

Shared across all users: the world-view of a coffee (origin, process, tasting
notes, buy URL, summary prose) is non-personal information intentionally shared
so repeat lookups for the same coffee by different users hit the cache and avoid
duplicate web-search charges (AIX-04).

TTL: 30 days (``expires_at`` column).  Lazy eviction at read time — no
background sweep needed at household scale.  An index on ``expires_at``
supports the lazy-evict DELETE in ``services/ai_research.py``.

``cache_key`` is the primary key, derived as:
    ``lower(coffee_name).strip() + '|' + lower(roaster_name or '').strip()``

This derivation must be identical in the write and read paths.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Index, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class AICoffeeResearchCache(Base):
    """One cached world-view research result for a (coffee_name, roaster_name) pair."""

    __tablename__ = "ai_coffee_research_cache"

    # Normalised key: lower(coffee_name).strip() + '|' + lower(roaster_name or '').strip()
    cache_key: Mapped[str] = mapped_column(Text, primary_key=True)

    # Full CoffeeResearchSchema payload serialised to JSONB
    response_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Cited source URLs extracted at write time (D-06).
    # Shape matches CoffeeResearchSchema.sources (list[str]); no migration needed —
    # annotation-only reconciliation per WR-06.
    cited_sources: Mapped[list[str]] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    # TTL 30 days — lazy eviction at read time; index supports the sweep DELETE
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (Index("ix_ai_research_cache_expires_at", "expires_at"),)
