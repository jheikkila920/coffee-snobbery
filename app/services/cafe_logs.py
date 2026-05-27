"""Per-user cafe-log CRUD (CAFE-01, CAFE-02, CAFE-06).

Mirrors the sync-service shape of :mod:`app.services.brew_sessions` (kwargs
API after a leading ``*``, single commit per write) with the following
simplifications:

1. **No equipment counters.** Cafe logs have no brewer/grinder/kettle FKs —
   no usage_count maintenance needed.
2. **No coffee flavor-notes sync.** Cafe logs are per-user free-text entries
   not linked to the shared ``coffees`` catalog (CONTEXT D-01).
3. **No structlog audit events.** Per CONTEXT Claude's-discretion default the
   household-scale audit posture is "auth + admin events"; cafe log churn is
   user-content noise. No CAFE_LOG_* constants added to app/events.py.

Per-user scoping (T-16-02-03 IDOR defense): every read / update / delete is
filtered by ``user_id``. ``get`` / ``update`` return ``None`` and ``delete``
returns ``False`` for a log not owned by the caller — the router maps the
sentinel to 404 (existence non-leak, never 403).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cafe_log import CafeLog

# --------------------------------------------------------------------------- #
# CRUD                                                                         #
# --------------------------------------------------------------------------- #


def create_cafe_log(
    db: Session,
    *,
    by_user_id: int,
    cafe_name: str,
    rating: Decimal | None,
    roaster_id: int | None,
    origin_country: str | None,
    brew_method: str | None,
    flavor_note_ids: list[int],
    notes: str,
    photo_filename: str | None,
    logged_at: datetime | None,
) -> CafeLog:
    """Insert a per-user cafe log row and return it.

    ``logged_at`` defaults to tz-aware UTC ``now()`` when ``None`` (backfilling
    support — the form lets users set a past date/time).
    """
    row = CafeLog(
        user_id=by_user_id,
        cafe_name=cafe_name,
        rating=rating,
        roaster_id=roaster_id,
        origin_country=origin_country,
        brew_method=brew_method,
        flavor_note_ids=flavor_note_ids or [],
        notes=notes or "",
        photo_filename=photo_filename,
        logged_at=logged_at if logged_at is not None else datetime.now(UTC),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_cafe_log(db: Session, *, cafe_log_id: int, by_user_id: int) -> CafeLog | None:
    """Return the user-owned cafe log, or ``None`` (missing OR not owned).

    IDOR sentinel — the router maps ``None`` → 404, never 403.
    """
    return db.execute(
        select(CafeLog).where(CafeLog.id == cafe_log_id, CafeLog.user_id == by_user_id)
    ).scalar_one_or_none()


def list_cafe_logs(
    db: Session,
    *,
    by_user_id: int,
    rating_min: Decimal | None = None,
    rating_max: Decimal | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[CafeLog]:
    """Return the user's cafe logs newest-first, with optional filters applied.

    Every filter is applied only when provided; all clauses are parameterized
    ``select()`` — no string SQL (SQLi defense T-16-02-06).
    """
    stmt = select(CafeLog).where(CafeLog.user_id == by_user_id)
    if rating_min is not None:
        stmt = stmt.where(CafeLog.rating >= rating_min)
    if rating_max is not None:
        stmt = stmt.where(CafeLog.rating <= rating_max)
    if date_from is not None:
        stmt = stmt.where(CafeLog.logged_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(CafeLog.logged_at <= date_to)
    stmt = stmt.order_by(CafeLog.logged_at.desc())
    return list(db.execute(stmt).scalars().all())


# Writable cafe log columns the update path may set. user_id and photo_filename
# (server-set) are deliberately absent (T-16-02-01 mass-assignment defense).
_WRITABLE_FIELDS = frozenset(
    {
        "cafe_name",
        "rating",
        "roaster_id",
        "origin_country",
        "brew_method",
        "flavor_note_ids",
        "notes",
        "photo_filename",
        "logged_at",
    }
)


def update_cafe_log(
    db: Session,
    *,
    cafe_log_id: int,
    by_user_id: int,
    **fields: object,
) -> CafeLog | None:
    """Update a user-owned cafe log and return it.

    Returns ``None`` (no mutation) when the row is missing or owned by a
    different user (IDOR defense — the router maps to 404). Only declared
    writable fields are applied.
    """
    row = get_cafe_log(db, cafe_log_id=cafe_log_id, by_user_id=by_user_id)
    if row is None:
        return None

    for key, value in fields.items():
        if key in _WRITABLE_FIELDS:
            setattr(row, key, value)
    row.updated_at = func.now()  # type: ignore[assignment]
    db.commit()
    db.refresh(row)
    return row


def delete_cafe_log(db: Session, *, cafe_log_id: int, by_user_id: int) -> bool:
    """Delete a user-owned cafe log.

    Returns ``False`` when the row is missing or owned by another user
    (IDOR defense). Returns ``True`` on success.
    """
    row = get_cafe_log(db, cafe_log_id=cafe_log_id, by_user_id=by_user_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
