"""Wishlist CRUD service (Phase 7, D-09 minimal view).

All operations are scoped to the calling user via ``by_user_id`` (always a
kwarg-after-star, always server-set from ``request.state.user.id``).
Cross-user entry_ids return ``None`` / ``False`` sentinels — the router maps
these to 404 so entry existence is never leaked (T-07-05 IDOR defense).
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.wishlist_entry import WishlistEntry

log = structlog.get_logger(__name__)


def add_to_wishlist(
    db: Session,
    *,
    by_user_id: int,
    coffee_name: str,
    roaster_name: str | None,
    source_url: str | None,
    source: str = "ai_recommendation",
    notes: str = "",
) -> WishlistEntry:
    """Create a wishlist entry for *by_user_id* and return the new row.

    ``by_user_id`` is always server-set — never sourced from form/query (T-07-06).
    ``source`` defaults to ``"ai_recommendation"`` per D-09.
    """
    entry = WishlistEntry(
        user_id=by_user_id,
        coffee_name=coffee_name,
        roaster_name=roaster_name,
        source_url=source_url,
        source=source,
        notes=notes,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    log.info("wishlist.add", user_id=by_user_id, entry_id=entry.id, source=source)
    return entry


def list_wishlist(db: Session, *, by_user_id: int) -> list[WishlistEntry]:
    """Return all wishlist entries for *by_user_id*, newest first."""
    rows = db.execute(
        select(WishlistEntry)
        .where(WishlistEntry.user_id == by_user_id)
        .order_by(WishlistEntry.added_at.desc())
    ).scalars().all()
    return list(rows)


def get_wishlist_entry(
    db: Session, *, entry_id: int, by_user_id: int
) -> WishlistEntry | None:
    """Return the entry if it belongs to *by_user_id*; else None (IDOR sentinel).

    Cross-user ids return None — the router maps this to 404 so entry existence
    is never leaked (T-07-05).
    """
    return db.execute(
        select(WishlistEntry).where(
            WishlistEntry.id == entry_id,
            WishlistEntry.user_id == by_user_id,
        )
    ).scalar_one_or_none()


def mark_purchased(
    db: Session, *, entry_id: int, by_user_id: int
) -> WishlistEntry | None:
    """Set ``purchased_at`` and return the updated entry.

    Returns None without modifying the DB if *entry_id* does not belong to
    *by_user_id* (T-07-05 IDOR sentinel).
    """
    entry = get_wishlist_entry(db, entry_id=entry_id, by_user_id=by_user_id)
    if entry is None:
        return None
    entry.purchased_at = datetime.now(tz=UTC)
    db.commit()
    db.refresh(entry)
    log.info("wishlist.mark_purchased", user_id=by_user_id, entry_id=entry_id)
    return entry


def remove_entry(db: Session, *, entry_id: int, by_user_id: int) -> bool:
    """Delete the entry and return True.

    Returns False without touching the DB if *entry_id* does not belong to
    *by_user_id* (T-07-05 IDOR sentinel — no delete performed).
    """
    entry = get_wishlist_entry(db, entry_id=entry_id, by_user_id=by_user_id)
    if entry is None:
        return False
    db.delete(entry)
    db.commit()
    log.info("wishlist.remove", user_id=by_user_id, entry_id=entry_id)
    return True
