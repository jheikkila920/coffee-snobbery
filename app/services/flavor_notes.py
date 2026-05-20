"""Flavor notes CRUD service — CAT-02.

Sync :class:`Session` per Phase 3 D-07; kwargs API per Phase 1 D-14 /
Phase 3 D-08; audit events per Phase 1 D-14 taxonomy.

Mirrors :mod:`app.services.roasters` (plan 04-04) structurally — same
shape, same kwarg conventions, same single-commit-per-write rule, same
audit-event emission at end of write transaction.

Public surface (consumed by :mod:`app.routers.flavor_notes`):

* :func:`create_flavor_note` — INSERT + commit + ``catalog.flavor_note.created``.
* :func:`get_flavor_note` — single-row fetch by id; returns ``None`` if missing.
* :func:`list_flavor_notes` — full list with an "advertised usage count"
  per row (count of non-archived coffees referencing the flavor note via
  ``coffees.advertised_flavor_note_ids``). Ordered by category, name.
* :func:`update_flavor_note` — UPDATE + commit + ``catalog.flavor_note.updated``.
* :func:`archive_flavor_note` — soft-delete (``archived=True``) +
  ``catalog.flavor_note.archived``. Phase 4 ships archive-only per CONTEXT.
* :func:`search_by_prefix` — D-13 autocomplete helper. CITEXT-native
  case-insensitive prefix match (no ``func.lower`` wrapper needed).

Audit-event kwarg names use ``user_id`` (NOT ``by_user_id``) per Phase 1
D-14 taxonomy alignment (matches :mod:`app.services.roasters`).

The 9-value category enum is enforced at three layers:

1. Pydantic schema regex (``app/schemas/flavor_note.py``).
2. Postgres CHECK constraint (``app/models/flavor_note.py``).
3. Native ``<select>`` dropdown in the form template (UI MOB-07 short-list).

The service trusts whatever ``category`` value the router hands it — the
schema layer is responsible for validation; the DB CHECK is the last-resort
defense.
"""

from __future__ import annotations

import structlog
from sqlalchemy import any_, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.events import (
    CATALOG_FLAVOR_NOTE_ARCHIVED,
    CATALOG_FLAVOR_NOTE_CREATED,
    CATALOG_FLAVOR_NOTE_UPDATED,
)
from app.models.coffee import Coffee
from app.models.flavor_note import FlavorNote
from app.services.form_validation import DuplicateNameError

log = structlog.get_logger(__name__)


def create_flavor_note(
    db: Session,
    *,
    name: str,
    category: str,
    by_user_id: int,
) -> FlavorNote:
    """Insert a new flavor note row and emit ``catalog.flavor_note.created``.

    ORM instantiate → ``add`` → ``flush`` (populate id) → ``commit``.
    The ``flush`` is what makes ``flavor_note.id`` available for the
    audit event AND for the router's HX-Trigger payload.
    """
    flavor_note = FlavorNote(name=name, category=category)
    db.add(flavor_note)
    try:
        db.flush()
        db.commit()
    except IntegrityError as exc:
        # UNIQUE CITEXT name collision (incl. case-variant). Roll back the
        # poisoned session so a subsequent valid write succeeds, then re-raise
        # the typed sentinel the router maps to a friendly inline name error.
        db.rollback()
        raise DuplicateNameError from exc
    log.info(
        CATALOG_FLAVOR_NOTE_CREATED,
        flavor_note_id=flavor_note.id,
        category=category,
        user_id=by_user_id,
    )
    return flavor_note


def get_flavor_note(db: Session, *, flavor_note_id: int) -> FlavorNote | None:
    """Return the flavor note with *flavor_note_id*, or ``None`` if missing."""
    return db.execute(
        select(FlavorNote).where(FlavorNote.id == flavor_note_id)
    ).scalar_one_or_none()


def list_flavor_notes(
    db: Session, *, include_archived: bool = False
) -> list[tuple[FlavorNote, int]]:
    """Return ``(FlavorNote, usage_count)`` tuples ordered by category, name.

    ``usage_count`` is the count of non-archived ``coffees`` that reference
    this flavor note via the ``advertised_flavor_note_ids`` array (UI-SPEC
    §"Flavor notes" — "count of coffees referencing it via
    ``advertised_flavor_note_ids``"). Phase 4 ships the "advertised" subset;
    Phase 5 adds the "observed" subset (from brew sessions) using the same
    column in the list template.

    Implementation: a correlated scalar subquery using Postgres ``= ANY()``
    on the array column. Cheaper than a LATERAL JOIN at household scale and
    keeps the result shape as a single row per flavor note.
    """
    usage_count = (
        select(func.count(Coffee.id))
        .where(FlavorNote.id == any_(Coffee.advertised_flavor_note_ids))
        .where(Coffee.archived.is_(False))
        .correlate(FlavorNote)
        .scalar_subquery()
    )
    stmt = select(FlavorNote, usage_count.label("usage_count")).order_by(
        FlavorNote.category, FlavorNote.name
    )
    if not include_archived:
        stmt = stmt.where(FlavorNote.archived.is_(False))
    rows = db.execute(stmt).all()
    return [(row[0], int(row[1] or 0)) for row in rows]


def update_flavor_note(
    db: Session,
    *,
    flavor_note_id: int,
    name: str,
    category: str,
    by_user_id: int,
) -> FlavorNote:
    """UPDATE the row, commit, re-fetch, emit ``catalog.flavor_note.updated``.

    Core ``update()`` so we can stamp ``updated_at = func.now()`` in the
    same statement (mirrors :func:`app.services.roasters.update_roaster`).
    """
    try:
        db.execute(
            update(FlavorNote)
            .where(FlavorNote.id == flavor_note_id)
            .values(
                name=name,
                category=category,
                updated_at=func.now(),
            )
        )
        db.commit()
    except IntegrityError as exc:
        # Renaming onto an existing flavor note's name → UNIQUE CITEXT collision.
        db.rollback()
        raise DuplicateNameError from exc
    flavor_note = db.execute(select(FlavorNote).where(FlavorNote.id == flavor_note_id)).scalar_one()
    log.info(
        CATALOG_FLAVOR_NOTE_UPDATED,
        flavor_note_id=flavor_note_id,
        category=category,
        user_id=by_user_id,
    )
    return flavor_note


def archive_flavor_note(db: Session, *, flavor_note_id: int, by_user_id: int) -> None:
    """Soft-delete a flavor note (``archived=True``) and emit the event.

    Phase 4 ships archive-only — hard-delete is reserved per CONTEXT
    discretion. Archived flavor notes no longer appear in autocomplete
    (``search_by_prefix`` filters them out) but historical references
    on coffees stay valid (the ARRAY column carries the bare id, not an FK).
    """
    db.execute(
        update(FlavorNote)
        .where(FlavorNote.id == flavor_note_id)
        .values(archived=True, updated_at=func.now())
    )
    db.commit()
    log.info(
        CATALOG_FLAVOR_NOTE_ARCHIVED,
        flavor_note_id=flavor_note_id,
        user_id=by_user_id,
    )


def search_by_prefix(db: Session, *, query: str, limit: int = 50) -> list[FlavorNote]:
    """D-13 autocomplete prefix-match helper.

    Returns up to *limit* non-archived flavor notes whose name starts with
    *query*. Ordered by name. CITEXT on ``FlavorNote.name`` makes ``ilike``
    case-insensitive natively — no ``func.lower()`` wrapper needed.

    Caller (the router) decides the ``len(query) >= 2`` gate; this helper
    happily takes any string and returns whatever Postgres finds.
    """
    stmt = (
        select(FlavorNote)
        .where(FlavorNote.archived.is_(False))
        .where(FlavorNote.name.ilike(f"{query}%"))
        .order_by(FlavorNote.name)
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


__all__ = [
    "archive_flavor_note",
    "create_flavor_note",
    "get_flavor_note",
    "list_flavor_notes",
    "search_by_prefix",
    "update_flavor_note",
]
