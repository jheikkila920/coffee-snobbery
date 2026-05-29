"""Phase 19: ai_coffee_research_cache + ai_rating_predictions + quota settings (D-06/D-07/D-08).

Revision ID: p19_ai_research_predict
Revises: p16_cafe_logs
Create Date: 2026-05-28

Creates:
  ai_coffee_research_cache  — shared world-view research cache (D-06)
  ai_rating_predictions     — per-user signature-versioned rating predictions (D-07)

Adds to app_settings:
  ai.research_daily_quota      = 20  (int)  — per-user rolling 24h cap (D-08)
  ai.improve_brew_daily_quota  = 20  (int)  — separate cap for improve-brew (D-08)

Alembic-safe convention (mirrors p16_cafe_logs.py): this migration body does
NOT import from app.models.  Schema is described inline with sa.Column /
sa.ForeignKey so a future model rename does not invalidate this migration.

Indexes:
  ix_ai_research_cache_expires_at  — B-tree on ai_coffee_research_cache.expires_at
                                     (supports lazy eviction DELETE, D-06)

Constraints:
  uq_ai_rating_pred_user_cache_key — UNIQUE(user_id, research_cache_key) on
                                     ai_rating_predictions (D-07, T-19-02)

Requirements traceability:
  D-06  — ai_coffee_research_cache table (shared, TTL 30 days)
  D-07  — ai_rating_predictions table (per-user, TTL 7 days, UNIQUE constraint)
  D-08  — quota app_settings rows (ai.research_daily_quota, ai.improve_brew_daily_quota)
  AIX-04 — cache prevents duplicate web-search charges
  T-19-02 — user_id FK + UNIQUE constraint prevent cross-user row writes
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "p19_ai_research_predict"
down_revision: str | Sequence[str] | None = "p16_cafe_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create both cache tables, indexes, and seed quota app_settings rows."""
    # ------------------------------------------------------------------
    # 1. ai_coffee_research_cache — shared world-view research cache (D-06)
    # ------------------------------------------------------------------
    op.create_table(
        "ai_coffee_research_cache",
        # PK: normalised key (lower+strip of coffee_name + '|' + roaster_name)
        sa.Column("cache_key", sa.Text, primary_key=True),
        # Full CoffeeResearchSchema payload as JSONB
        sa.Column(
            "response_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        # Cited source URLs list (list[str] — URL strings per CoffeeResearchSchema.sources; WR-06)
        sa.Column(
            "cited_sources",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # TTL 30 days — lazy eviction at read time
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    # B-tree index on expires_at for the lazy-evict sweep DELETE
    op.create_index(
        "ix_ai_research_cache_expires_at",
        "ai_coffee_research_cache",
        ["expires_at"],
    )

    # ------------------------------------------------------------------
    # 2. ai_rating_predictions — per-user signature-versioned predictions (D-07)
    # ------------------------------------------------------------------
    op.create_table(
        "ai_rating_predictions",
        sa.Column(
            "id",
            sa.BigInteger,
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "research_cache_key",
            sa.Text,
            sa.ForeignKey("ai_coffee_research_cache.cache_key", ondelete="CASCADE"),
            nullable=False,
        ),
        # RatingPredictionSchema fields stored flat
        sa.Column("predicted_low", sa.Numeric(3, 2), nullable=False),
        sa.Column("predicted_high", sa.Numeric(3, 2), nullable=False),
        # 'Low' | 'Medium' | 'High' — application-validated; no DB enum needed
        sa.Column("confidence", sa.Text, nullable=False),
        sa.Column("reasoning", sa.Text, nullable=False),
        # Brew-session history signature; stale if mismatched (Pattern 5)
        sa.Column("input_signature", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # TTL 7 days
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        # One prediction per (user, coffee) — upsert path is unambiguous
        sa.UniqueConstraint(
            "user_id",
            "research_cache_key",
            name="uq_ai_rating_pred_user_cache_key",
        ),
    )

    # ------------------------------------------------------------------
    # 3. Seed quota app_settings rows (D-08)
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            "INSERT INTO app_settings (key, value, value_type, description) "
            "VALUES "
            "('ai.research_daily_quota', '20', 'int', "
            " 'Per-user rolling 24h cap for coffee research LLM calls'), "
            "('ai.improve_brew_daily_quota', '20', 'int', "
            " 'Per-user rolling 24h cap for improve-brew LLM calls') "
            "ON CONFLICT (key) DO NOTHING"
        )
    )


def downgrade() -> None:
    """Reverse upgrade in FK-safe order: predictions first (references cache), then cache."""
    # Remove quota settings rows
    op.execute(
        sa.text(
            "DELETE FROM app_settings "
            "WHERE key IN ('ai.research_daily_quota', 'ai.improve_brew_daily_quota')"
        )
    )

    # Drop predictions table first (has FK referencing cache table)
    op.drop_table("ai_rating_predictions")

    # Drop cache index then cache table
    op.drop_index("ix_ai_research_cache_expires_at", table_name="ai_coffee_research_cache")
    op.drop_table("ai_coffee_research_cache")
