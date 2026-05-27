"""Varietals CRUD service — CATALOG-05.

Mirrors :mod:`app.services.flavor_notes` API surface exactly:

* :func:`create_varietal` — INSERT + commit + ``catalog.varietal.created``.
  Uses IntegrityError → DuplicateNameError pattern for CITEXT UNIQUE collisions.
  Supports ``commit=False`` for batch paths (CSV importer, future bulk ops).
* :func:`search_by_prefix` — CITEXT ilike prefix match for autocomplete.
  No ``archived`` filter — Varietal has no archived column.

The ``create_varietal`` function mirrors :func:`app.services.flavor_notes.create_flavor_note`
structurally: same flush/commit semantics, same DuplicateNameError pattern,
same audit-event emission at end of successful write.

Audit-event kwarg names use ``user_id`` (NOT ``by_user_id``) per Phase 1
D-14 taxonomy alignment (matches :mod:`app.services.flavor_notes`).

CATALOG-05 threat notes:
* T-15.1-16: CITEXT collision → DuplicateNameError (SAVEPOINT rollback implicit
  in db.rollback(); router maps to friendly inline error — mirrors flavor_notes pattern).
* T-15.1-20: structlog audit event emits varietal_id + user_id at create time.
"""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.events import CATALOG_VARIETAL_CREATED
from app.models.varietal import Varietal
from app.services.form_validation import DuplicateNameError

log = structlog.get_logger(__name__)


def create_varietal(
    db: Session,
    *,
    name: str,
    by_user_id: int,
    commit: bool = True,
) -> Varietal:
    """Insert a new varietal row and emit ``catalog.varietal.created``.

    ``commit=False`` makes this a no-commit path: only flushes so the caller's
    open transaction can own the single commit. On the no-commit path the caller
    is responsible for handling a UNIQUE-citext IntegrityError.

    Mirrors :func:`app.services.flavor_notes.create_flavor_note` exactly
    (minus the category param — varietals have only name).
    """
    varietal = Varietal(name=name)
    db.add(varietal)
    if commit:
        try:
            db.flush()
            db.commit()
        except IntegrityError as exc:
            # UNIQUE CITEXT name collision (incl. case-variant). Roll back the
            # poisoned session so a subsequent valid write succeeds, then re-raise
            # the typed sentinel the router maps to a friendly inline name error.
            db.rollback()
            raise DuplicateNameError from exc
    else:
        db.flush()
    log.info(
        CATALOG_VARIETAL_CREATED,
        varietal_id=varietal.id,
        user_id=by_user_id,
    )
    return varietal


def search_by_prefix(db: Session, *, query: str, limit: int = 50) -> list[Varietal]:
    """Autocomplete prefix-match helper.

    Returns up to *limit* varietals whose name starts with *query*.
    Ordered by name. CITEXT on ``Varietal.name`` makes ``ilike``
    case-insensitive natively — no ``func.lower()`` wrapper needed.

    No ``archived`` filter — Varietal has no archived column (D-02).

    Caller (the router) decides the ``len(query) >= 2`` gate; this helper
    happily takes any string and returns whatever Postgres finds.
    """
    stmt = (
        select(Varietal)
        .where(Varietal.name.ilike(f"{query}%"))
        .order_by(Varietal.name)
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


__all__ = [
    "create_varietal",
    "search_by_prefix",
]
