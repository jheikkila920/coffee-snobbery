"""Chart query helpers for VIZ-01 (plan 19-05).

Two per-user query helpers for the Trends card on ``/ai``:

- ``rating_over_time`` — brew + cafe UNION of ratings over the last 90 days
- ``flavor_distribution`` — top-15 flavor descriptors by count, no rating floor

Both return plain Python dicts so the route can serialise them as JSON without
additional transformation.  Both are per-user scoped on user_id (T-19-18).

D-17 chart details:
  1. Rating over time — line chart, UNION brew_sessions.rating + cafe_logs.rating,
     last 90 days, ordered by date.
  2. Flavor distribution — horizontal bar, top-15 descriptors by appearance count
     across brew + cafe sessions.  NO >= 4.0 rating floor (distinct from
     analytics.get_flavor_descriptors which uses a 4.0+ filter for AI preference
     derivation).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# VIZ-01 Chart 1: Rating over time
# ---------------------------------------------------------------------------


def rating_over_time(db: Session, user_id: int) -> list[dict]:
    """Return {date, rating} rows for brew + cafe sessions in the last 90 days.

    D-17: UNION brew_session.rating + cafe_log.rating, per-user, last 90 days,
    ordered by date ascending. NULL ratings are excluded. Dates serialised as
    ISO-8601 strings (YYYY-MM-DD) for Chart.js x-axis consumption.

    T-19-18: per-user scoped on user_id — no cross-user leakage possible.
    """
    since = datetime.now(UTC) - timedelta(days=90)

    # Build UNION of brew + cafe ratings via raw SQL for clean date casting.
    # Uses bound :user_id parameter (T-19-18, no string interpolation).
    stmt = text(
        """
        SELECT
            date_trunc('day', session_date)::date AS date,
            rating
        FROM (
            SELECT brewed_at AS session_date, rating
            FROM brew_sessions
            WHERE user_id = :user_id
              AND rating IS NOT NULL
              AND brewed_at >= :since
            UNION ALL
            SELECT logged_at AS session_date, rating
            FROM cafe_logs
            WHERE user_id = :user_id
              AND rating IS NOT NULL
              AND logged_at >= :since
        ) AS combined
        ORDER BY date ASC
        """
    )
    rows: list[Row] = db.execute(stmt, {"user_id": user_id, "since": since}).all()
    return [{"date": str(row.date), "rating": float(row.rating)} for row in rows]


# ---------------------------------------------------------------------------
# VIZ-01 Chart 2: Flavor distribution
# ---------------------------------------------------------------------------


def flavor_distribution(db: Session, user_id: int) -> list[dict]:
    """Return top-15 {descriptor, count} rows by appearance across brew + cafe sessions.

    D-17: UNION brew_session.flavor_note_ids_observed + cafe_log.flavor_note_ids.
    NO rating floor — counts ALL sessions regardless of rating (distinct from
    analytics.get_flavor_descriptors which requires rating >= 4.0 for AI use).
    Capped at N=15 for readability.

    T-19-18: per-user scoped — both UNION sides carry user_id = :user_id.
    """
    stmt = text(
        """
        SELECT fn.name AS descriptor, COUNT(*) AS count
        FROM (
            SELECT note_id
            FROM brew_sessions bs, unnest(bs.flavor_note_ids_observed) AS note_id
            WHERE bs.user_id = :user_id
            UNION ALL
            SELECT note_id
            FROM cafe_logs cl, unnest(cl.flavor_note_ids) AS note_id
            WHERE cl.user_id = :user_id
        ) AS notes
        JOIN flavor_notes fn ON fn.id = notes.note_id
        GROUP BY fn.name
        ORDER BY count DESC
        LIMIT 15
        """
    )
    rows: list[Row] = db.execute(stmt, {"user_id": user_id}).all()
    return [{"descriptor": row.descriptor, "count": int(row.count)} for row in rows]
