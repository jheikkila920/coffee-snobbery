"""Roasters CRUD service — CAT-01.

Sync :class:`Session` per Phase 3 D-07; kwargs API per Phase 1 D-14 /
Phase 3 D-08; audit events per Phase 1 D-14 taxonomy.

Mirrors the structural template of :mod:`app.services.credentials`:
sync ``Session``, kwargs-only API after a leading ``*``, single commit
per write, audit-event emission at the end of each write transaction.

Public surface (consumed by :mod:`app.routers.roasters`):

* :func:`create_roaster` — INSERT + commit + ``catalog.roaster.created``.
* :func:`get_roaster` — single-row fetch by id; returns ``None`` if missing.
* :func:`list_roasters` — full list ordered by name; archived filter.
* :func:`update_roaster` — UPDATE + commit + ``catalog.roaster.updated``.
* :func:`archive_roaster` — soft-delete (``archived=True``) +
  ``catalog.roaster.archived``. Phase 4 ships archive-only per the
  CONTEXT discretion note; hard-delete is reserved for future admin work.
* :func:`search_by_prefix` — D-13 autocomplete helper, prefix match on
  the CITEXT name column (case-insensitive natively, no ``func.lower``
  wrapper needed).

Audit-event kwarg names: every log line uses ``user_id`` (NOT
``by_user_id`` — Phase 1 D-14 taxonomy alignment, see comment at
``credentials.py:196-197``).

The website column accepts ``str | None``; the router is responsible for
converting the schema-layer ``HttpUrl`` to ``str`` before calling here
(``str(form.website) if form.website else None``).
"""

from __future__ import annotations

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.events import (
    CATALOG_ROASTER_ARCHIVED,
    CATALOG_ROASTER_CREATED,
    CATALOG_ROASTER_UPDATED,
)
from app.models.roaster import Roaster

log = structlog.get_logger(__name__)


def create_roaster(
    db: Session,
    *,
    name: str,
    location: str | None,
    website: str | None,
    notes: str,
    by_user_id: int,
) -> Roaster:
    """Insert a new roaster row and emit ``catalog.roaster.created``.

    ORM instantiate → ``add`` → ``flush`` (populate id) → ``commit``.
    The ``flush`` is what makes ``roaster.id`` available for the audit
    event AND for the router's HX-Trigger payload before we return.
    """
    roaster = Roaster(
        name=name,
        location=location,
        website=website,
        notes=notes,
    )
    db.add(roaster)
    db.flush()
    db.commit()
    log.info(
        CATALOG_ROASTER_CREATED,
        roaster_id=roaster.id,
        user_id=by_user_id,
    )
    return roaster


def get_roaster(db: Session, *, roaster_id: int) -> Roaster | None:
    """Return the roaster with *roaster_id*, or ``None`` if missing."""
    return db.execute(
        select(Roaster).where(Roaster.id == roaster_id)
    ).scalar_one_or_none()


def list_roasters(db: Session, *, include_archived: bool = False) -> list[Roaster]:
    """Return roasters ordered by name; archived filtered out by default.

    Phase 4 ships archive-only soft-delete; the list page hides archived
    rows unless the user opts in via the ``include_archived`` query
    param (UI-SPEC §"Show archived" toggle).
    """
    stmt = select(Roaster).order_by(Roaster.name)
    if not include_archived:
        stmt = stmt.where(Roaster.archived.is_(False))
    return list(db.execute(stmt).scalars().all())


def update_roaster(
    db: Session,
    *,
    roaster_id: int,
    name: str,
    location: str | None,
    website: str | None,
    notes: str,
    by_user_id: int,
) -> Roaster:
    """UPDATE the row, commit, re-fetch, emit ``catalog.roaster.updated``.

    Core ``update()`` is used (analog ``credentials.set_provider_credential``)
    because it bypasses the ORM's ``onupdate`` hook hash and lets us
    explicitly stamp ``updated_at = func.now()`` in the same statement.
    Returning the re-fetched row keeps the router's response shape
    identical between create and update paths.
    """
    db.execute(
        update(Roaster)
        .where(Roaster.id == roaster_id)
        .values(
            name=name,
            location=location,
            website=website,
            notes=notes,
            updated_at=func.now(),
        )
    )
    db.commit()
    roaster = db.execute(
        select(Roaster).where(Roaster.id == roaster_id)
    ).scalar_one()
    log.info(
        CATALOG_ROASTER_UPDATED,
        roaster_id=roaster_id,
        user_id=by_user_id,
    )
    return roaster


def archive_roaster(db: Session, *, roaster_id: int, by_user_id: int) -> None:
    """Soft-delete a roaster (``archived=True``) and emit the event.

    Phase 4 ships archive-only — hard-delete is reserved per CONTEXT
    discretion. The bag/coffee FK chain (RESTRICT) means a hard-delete
    would fail at the DB anyway once the row has any referencing bags.
    """
    db.execute(
        update(Roaster)
        .where(Roaster.id == roaster_id)
        .values(archived=True, updated_at=func.now())
    )
    db.commit()
    log.info(
        CATALOG_ROASTER_ARCHIVED,
        roaster_id=roaster_id,
        user_id=by_user_id,
    )


def search_by_prefix(db: Session, *, query: str, limit: int = 50) -> list[Roaster]:
    """D-13 autocomplete prefix-match helper.

    Returns up to *limit* non-archived roasters whose name starts with
    *query*. Ordered by name. CITEXT on ``Roaster.name`` makes ``ilike``
    case-insensitive natively — no ``func.lower()`` wrapper needed.

    Caller (the router) decides the ``len(query) >= 2`` gate; this
    helper happily takes any string and returns whatever Postgres
    finds.
    """
    stmt = (
        select(Roaster)
        .where(Roaster.archived.is_(False))
        .where(Roaster.name.ilike(f"{query}%"))
        .order_by(Roaster.name)
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


__all__ = [
    "archive_roaster",
    "create_roaster",
    "get_roaster",
    "list_roasters",
    "search_by_prefix",
    "update_roaster",
]
