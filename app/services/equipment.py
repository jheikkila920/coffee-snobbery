"""Equipment CRUD service — CAT-05.

Sync :class:`Session` per Phase 3 D-07; kwargs API per Phase 1 D-14 /
Phase 3 D-08; audit events per Phase 1 D-14 taxonomy.

Mirrors :mod:`app.services.roasters` (plan 04-04) structurally — same
shape, same kwarg conventions, same single-commit-per-write rule, same
audit-event emission at end of write transaction. Differences:

* List ordering is ``(type, brand, model)`` — the page groups by ``type``
  via a server-side ordered dict (UI-SPEC §"Equipment — `/equipment`").
* The function parameter ``type_`` uses a trailing underscore to avoid
  shadowing the Python builtin ``type``; the ORM column is still
  ``Equipment.type``.
* No ``search_by_prefix`` helper — equipment is intentionally NOT
  autocompleted from any other form. Equipment is selected by id on
  Phase 5's brew-session form via a native ``<select>``, not by
  free-text autocomplete.

Public surface (consumed by :mod:`app.routers.equipment`):

* :func:`create_equipment` — INSERT + commit + ``catalog.equipment.created``.
* :func:`get_equipment` — single-row fetch by id; returns ``None`` if missing.
* :func:`list_equipment` — full list ordered by ``(type, brand, model)``;
  archived filter.
* :func:`list_equipment_grouped_by_type` — ordered dict of
  ``{type: [Equipment, ...]}`` built from the same query; the page
  template iterates the dict keys for type-group headings.
* :func:`update_equipment` — UPDATE + commit + ``catalog.equipment.updated``.
* :func:`archive_equipment` — soft-delete (``archived=True``) +
  ``catalog.equipment.archived``. Phase 4 ships archive-only per CONTEXT.

Audit-event kwarg names use ``user_id`` (NOT ``by_user_id``) per Phase 1
D-14 taxonomy alignment (matches :mod:`app.services.roasters`).

The 6-value type enum (brewer, grinder, kettle, scale, water_filter,
other) is enforced at three layers:

1. Pydantic schema regex (``app/schemas/equipment.py``).
2. Postgres CHECK constraint (``app/models/equipment.py``).
3. Native ``<select>`` dropdown in the form template (UI MOB-07 short-list).

``usage_count`` is the denormalized counter (Phase 4 default 0; Phase 5
increments on brew-session insert). This service does NOT touch it — it
ships at the model's ``server_default=0`` for new rows and stays
unchanged on update/archive.
"""

from __future__ import annotations

from collections import OrderedDict

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.events import (
    CATALOG_EQUIPMENT_ARCHIVED,
    CATALOG_EQUIPMENT_CREATED,
    CATALOG_EQUIPMENT_UPDATED,
)
from app.models.equipment import Equipment

log = structlog.get_logger(__name__)


def create_equipment(
    db: Session,
    *,
    type_: str,
    brand: str,
    model: str,
    notes: str,
    by_user_id: int,
) -> Equipment:
    """Insert a new equipment row and emit ``catalog.equipment.created``.

    ORM instantiate → ``add`` → ``flush`` (populate id) → ``commit``.
    The ``flush`` is what makes ``equipment.id`` available for the
    audit event before we return.

    ``type_`` is the param name to avoid shadowing the Python builtin
    ``type``; the ORM column is ``Equipment.type``.
    """
    equipment = Equipment(
        type=type_,
        brand=brand,
        model=model,
        notes=notes,
    )
    db.add(equipment)
    db.flush()
    db.commit()
    log.info(
        CATALOG_EQUIPMENT_CREATED,
        equipment_id=equipment.id,
        type=type_,
        brand=brand,
        model=model,
        user_id=by_user_id,
    )
    return equipment


def get_equipment(db: Session, *, equipment_id: int) -> Equipment | None:
    """Return the equipment row with *equipment_id*, or ``None`` if missing."""
    return db.execute(select(Equipment).where(Equipment.id == equipment_id)).scalar_one_or_none()


def list_equipment(db: Session, *, include_archived: bool = False) -> list[Equipment]:
    """Return equipment ordered by ``(type, brand, model)``.

    Archived rows filtered out by default. The ``type`` sort key is what
    makes :func:`list_equipment_grouped_by_type` cheap — Postgres returns
    the rows already grouped by type and the helper just walks them
    once into an ordered dict.
    """
    stmt = select(Equipment).order_by(Equipment.type, Equipment.brand, Equipment.model)
    if not include_archived:
        stmt = stmt.where(Equipment.archived.is_(False))
    return list(db.execute(stmt).scalars().all())


def list_equipment_grouped_by_type(
    db: Session, *, include_archived: bool = False
) -> OrderedDict[str, list[Equipment]]:
    """Return an ordered ``{type: [Equipment, ...]}`` mapping.

    Keys appear in the order their rows first surface from the
    ``(type, brand, model)``-sorted query — i.e., alphabetically by
    type, which happens to land in a sensible UI order
    (brewer, grinder, kettle, other, scale, water_filter).

    The page template iterates the dict keys for the group headings
    (UI-SPEC §"Equipment — `/equipment`": "Grouped by `type`. Each group
    renders as a labeled section.").
    """
    rows = list_equipment(db, include_archived=include_archived)
    groups: OrderedDict[str, list[Equipment]] = OrderedDict()
    for row in rows:
        groups.setdefault(row.type, []).append(row)
    return groups


def update_equipment(
    db: Session,
    *,
    equipment_id: int,
    type_: str,
    brand: str,
    model: str,
    notes: str,
    by_user_id: int,
) -> Equipment:
    """UPDATE the row, commit, re-fetch, emit ``catalog.equipment.updated``.

    Core ``update()`` so we can stamp ``updated_at = func.now()`` in
    the same statement (mirrors :func:`app.services.roasters.update_roaster`).
    """
    db.execute(
        update(Equipment)
        .where(Equipment.id == equipment_id)
        .values(
            type=type_,
            brand=brand,
            model=model,
            notes=notes,
            updated_at=func.now(),
        )
    )
    db.commit()
    equipment = db.execute(select(Equipment).where(Equipment.id == equipment_id)).scalar_one()
    log.info(
        CATALOG_EQUIPMENT_UPDATED,
        equipment_id=equipment_id,
        type=type_,
        brand=brand,
        model=model,
        user_id=by_user_id,
    )
    return equipment


def archive_equipment(db: Session, *, equipment_id: int, by_user_id: int) -> None:
    """Soft-delete equipment (``archived=True``) and emit the event.

    Phase 4 ships archive-only — hard-delete is reserved per CONTEXT
    discretion. Once Phase 5 lands, brew sessions reference equipment
    via FK and a hard-delete would fail at the DB anyway once any
    session references the row.
    """
    db.execute(
        update(Equipment)
        .where(Equipment.id == equipment_id)
        .values(archived=True, updated_at=func.now())
    )
    db.commit()
    log.info(
        CATALOG_EQUIPMENT_ARCHIVED,
        equipment_id=equipment_id,
        user_id=by_user_id,
    )


__all__ = [
    "archive_equipment",
    "create_equipment",
    "get_equipment",
    "list_equipment",
    "list_equipment_grouped_by_type",
    "update_equipment",
]
