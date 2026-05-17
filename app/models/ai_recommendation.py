"""``ai_recommendations`` table — full AI-02 column set with COST-1 telemetry.

This is the load-bearing assertion of Plan 03: every cost-observability
column lands NOW (Phase 0) even though writes don't begin until Phase 7.
Retrofitting columns onto a populated table is painful; the cost of
shipping them empty for six phases is negligible.

Cost-observability columns (PITFALL COST-1):

* ``tokens_input``           — total input tokens billed
* ``tokens_output``          — total output tokens billed
* ``tokens_input_search``    — web-search-tool billed input tokens (Anthropic
  prices these separately; tracking them lets us attribute spend to search).
* ``web_search_count``       — number of search tool invocations
* ``provider_used``          — 'anthropic' | 'openai'
* ``model_used``             — exact model ID e.g. 'claude-opus-4-7'
* ``tool_version``           — e.g. 'web_search_20250305' (AI-5)
* ``url_verified``           — null until URL-verification task runs
* ``duration_ms``            — end-to-end recommendation latency
* ``generated_by``           — 'scheduler' | 'manual_refresh'
* ``error_status``           — populated only on failure
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, ForeignKey, Identity, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class AIRecommendation(Base):
    """One AI-generated recommendation envelope. Per-user; per-recommendation-type."""

    __tablename__ = "ai_recommendations"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # enum-as-text per RESEARCH §Notes on schema choices: 'coffee' | 'equipment'
    # | 'paste_rank' | 'sweet_spots'. Application validates the value set.
    recommendation_type: Mapped[str] = mapped_column(Text, nullable=False)
    # Signature drives nightly regeneration: if the user's input signature
    # hasn't changed since the last successful run, skip the LLM call.
    input_signature: Mapped[str] = mapped_column(Text, nullable=False)
    response_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # 'anthropic' | 'openai'
    provider_used: Mapped[str] = mapped_column(Text, nullable=False)
    model_used: Mapped[str] = mapped_column(Text, nullable=False)
    # e.g. 'web_search_20250305' (Anthropic) or 'web_search' (OpenAI).
    tool_version: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Cost-observability columns (PITFALL COST-1; AI-02) ---
    tokens_input: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    tokens_output: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # Web-search-billed input tokens — Anthropic prices these as a separate
    # line on the bill; tracking them lets us attribute spend to search.
    tokens_input_search: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    web_search_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # NULL until a separate URL-verification task confirms recommended links
    # are still live. Phase 7 implements this; Phase 0 just makes the column.
    url_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    # 'scheduler' | 'manual_refresh'
    generated_by: Mapped[str] = mapped_column(Text, nullable=False)
    # NULL on success; populated with a short failure code on error.
    error_status: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_ai_recs_input_signature", "input_signature"),
        Index(
            "ix_ai_recs_user_type_generated",
            "user_id",
            "recommendation_type",
            text("generated_at DESC"),
        ),
    )
