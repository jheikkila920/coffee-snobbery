"""Rolling-24h quota math for AI research and brew-improvement flows (AIX-05/D-08/D-09).

Quota is DB-backed (never in-memory) so it survives process restart and is visible
to the admin settings UI.  Cache hits do NOT decrement quota — only successful LLM
calls (error_status IS NULL) count.

Settings keys (separate buckets per D-08):
  ai.research_daily_quota     — daily cap for coffee_research calls (default 20)
  ai.improve_brew_daily_quota — daily cap for brew_improvement calls (default 20)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ai_recommendation import AIRecommendation
from app.services import settings as settings_service

# Map rec_type → app_settings key (D-08: separate buckets)
_QUOTA_SETTINGS_KEYS: dict[str, str] = {
    "coffee_research": "ai.research_daily_quota",
    "brew_improvement": "ai.improve_brew_daily_quota",
}

_DEFAULT_QUOTA = 20
_WINDOW_HOURS = 24


def count_calls_last_24h(db: Session, user_id: int, rec_type: str) -> int:
    """COUNT of successful LLM-fired calls in the rolling 24h window.

    Excludes rows where error_status IS NOT NULL (failed calls don't count
    against quota — only successful calls that consumed API credits).
    Cache hits never write a row, so they never decrement quota (AIX-04).
    """
    since = datetime.now(UTC) - timedelta(hours=_WINDOW_HOURS)
    return (
        db.scalar(
            select(func.count(AIRecommendation.id)).where(
                AIRecommendation.user_id == user_id,
                AIRecommendation.recommendation_type == rec_type,
                AIRecommendation.error_status.is_(None),
                AIRecommendation.generated_at >= since,
            )
        )
        or 0
    )


def get_quota_reset_time(db: Session, user_id: int, rec_type: str) -> datetime | None:
    """Return when the oldest call in the window expires (quota reset time).

    D-09: reset time = oldest successful call in the window + 24h.
    Returns None when the window is empty (no calls → no reset needed).
    """
    since = datetime.now(UTC) - timedelta(hours=_WINDOW_HOURS)
    oldest_at = db.scalar(
        select(func.min(AIRecommendation.generated_at)).where(
            AIRecommendation.user_id == user_id,
            AIRecommendation.recommendation_type == rec_type,
            AIRecommendation.error_status.is_(None),
            AIRecommendation.generated_at >= since,
        )
    )
    if oldest_at is None:
        return None
    return oldest_at + timedelta(hours=_WINDOW_HOURS)


def get_quota_cap(rec_type: str) -> int:
    """Read the admin-configurable daily cap from app_settings.

    Falls back to _DEFAULT_QUOTA (20) when the setting is absent or None.
    Separate settings keys per rec_type (D-08 separate buckets).
    """
    key = _QUOTA_SETTINGS_KEYS.get(rec_type, "ai.research_daily_quota")
    value = settings_service.get_int(key)
    return value if value is not None else _DEFAULT_QUOTA


def remaining(db: Session, user_id: int, rec_type: str) -> int:
    """Remaining quota calls for this user in the rolling 24h window.

    Returns max(cap - count, 0) — never negative.
    """
    cap = get_quota_cap(rec_type)
    used = count_calls_last_24h(db, user_id, rec_type)
    return max(cap - used, 0)
