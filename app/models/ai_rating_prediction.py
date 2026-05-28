"""``ai_rating_predictions`` table — per-user signature-versioned rating predictions (D-07).

Separate from ``ai_recommendations``: predictions are tied to a specific research
cache entry (``research_cache_key``) and are regenerated when the user's input
signature changes OR the 7-day TTL expires.

Uniqueness invariant: one prediction row per (user_id, research_cache_key).
This is enforced by a UNIQUE constraint so the upsert path is unambiguous.

``input_signature`` encodes the user's brew-session history at prediction time.
Stale-on-mismatch: if the signature on the stored row differs from the current
derived signature, the row is regenerated before display (Pattern 5 in RESEARCH.md).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Identity, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class AIRatingPrediction(Base):
    """One per-user rating prediction tied to a shared research cache row."""

    __tablename__ = "ai_rating_predictions"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    research_cache_key: Mapped[str] = mapped_column(
        Text,
        ForeignKey("ai_coffee_research_cache.cache_key", ondelete="CASCADE"),
        nullable=False,
    )

    # RatingPredictionSchema fields stored flat for easy query access
    predicted_low: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    predicted_high: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    # 'Low' | 'Medium' | 'High' — application-validated Literal (no DB enum)
    confidence: Mapped[str] = mapped_column(Text, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)

    # Signature of the user's brew-session history at prediction time.
    # Stale if current derived signature differs (Pattern 5 in RESEARCH.md).
    input_signature: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    # TTL 7 days — regenerated on expiry or signature mismatch
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "research_cache_key",
            name="uq_ai_rating_pred_user_cache_key",
        ),
    )
