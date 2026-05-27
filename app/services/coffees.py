"""Coffees CRUD service — CAT-03.

Sync :class:`Session` per Phase 3 D-07; kwargs API per Phase 1 D-14 /
Phase 3 D-08; audit events per Phase 1 D-14 taxonomy.

Mirrors :mod:`app.services.roasters` (plan 04-04) structurally — same
shape, same kwarg conventions, same single-commit-per-write rule, same
audit-event emission at end of write transaction. Differences:

* ``list_coffees`` accepts four filter kwargs (``roaster_id``,
  ``country``, ``process``, ``archived``) so the CAT-07 filter bar
  (``hx-push-url=true``) can serve any combination.
* ``archived=True`` filters to archived rows ONLY (NOT a union with
  active rows) — UI-SPEC §"Filter Bar (coffees only — CAT-07)" lock.
  The default ``archived=False`` shows only non-archived rows.
* ``advertised_flavor_note_ids`` is an ``ARRAY(BigInteger)`` round-trip;
  SQLAlchemy 2.0 + psycopg 3 handle the Postgres array natively.
* :func:`get_coffee_with_bags` returns the coffee row + its bags ordered
  ``opened_at DESC NULLS LAST, created_at DESC`` for the detail page.
* :func:`list_distinct_countries` queries the distinct non-null country
  values for the filter-bar dropdown; the 6 process values are exported
  as a module-level constant tuple (matches the schema regex).
* :func:`flavor_note_name_map` returns a ``{id: name}`` dict for the
  list template to resolve advertised-flavor-note pills (UI-SPEC pill
  rendering up to 3 + "+N more").

Public surface (consumed by :mod:`app.routers.coffees`):

* :func:`create_coffee` — INSERT + commit + ``catalog.coffee.created``.
* :func:`get_coffee` — single-row fetch by id; returns ``None`` if missing.
* :func:`get_coffee_with_bags` — ``(Coffee, list[Bag])`` for the detail
  page; bags ordered by ``opened_at`` desc nulls last, then ``created_at``
  desc.
* :func:`list_coffees` — filtered list (roaster_id / country / process /
  archived) ordered by ``Coffee.name`` (CITEXT case-insensitive natural
  order).
* :func:`update_coffee` — UPDATE + commit + ``catalog.coffee.updated``.
* :func:`archive_coffee` — soft-delete + ``catalog.coffee.archived``.
* :func:`list_distinct_countries` — distinct non-null country values for
  the filter-bar dropdown.
* :func:`flavor_note_name_map` — ``{flavor_note_id: name}`` over a set of
  ids (used by the list template to render pill names).

Audit-event kwarg names use ``user_id`` (NOT ``by_user_id``) per Phase 1
D-14 taxonomy alignment (matches :mod:`app.services.roasters` and
:mod:`app.services.flavor_notes`).
"""

from __future__ import annotations

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.events import (
    CATALOG_COFFEE_ARCHIVED,
    CATALOG_COFFEE_CREATED,
    CATALOG_COFFEE_UPDATED,
)
from app.models.bag import Bag
from app.models.coffee import Coffee
from app.models.coffee_origin import CoffeeOrigin
from app.models.flavor_note import FlavorNote
from app.models.varietal import Varietal

log = structlog.get_logger(__name__)


# Locked 6-value process enum (matches the Pydantic regex in plan 04-02
# and the DB CHECK in plan 04-03). Exported so the router can hand the
# tuple to the page template's filter <select> + form <select>.
COFFEE_PROCESSES: tuple[str, ...] = (
    "washed",
    "natural",
    "honey",
    "anaerobic",
    "experimental",
    "unknown",
)

# 8-value roast-level enum (CATALOG-04: ultra-light + nordic-light added).
COFFEE_ROAST_LEVELS: tuple[str, ...] = (
    "ultra-light",
    "nordic-light",
    "light",
    "medium-light",
    "medium",
    "medium-dark",
    "dark",
    "unknown",
)


def create_coffee(
    db: Session,
    *,
    name: str,
    roaster_id: int | None,
    process: str | None,
    roast_level: str | None,
    notes: str,
    advertised_flavor_note_ids: list[int],
    origins: list[tuple[str, str | None]] | None = None,
    varietal_ids: list[int] | None = None,
    by_user_id: int,
) -> Coffee:
    """Insert a new coffee row and emit ``catalog.coffee.created``.

    ORM instantiate → ``add`` → ``flush`` (populate id) → add CoffeeOrigin rows
    + assign varietal m2m → ``commit``. Origins are a list of ``(country, region)``
    tuples (D-22). varietal_ids are FK references to the varietals table (CATALOG-05).

    SQLAlchemy 2.0 + psycopg 3 handle the ``ARRAY(BigInteger)`` round-
    trip natively — pass the list straight to the column.
    """
    coffee = Coffee(
        name=name,
        roaster_id=roaster_id,
        process=process,
        roast_level=roast_level,
        notes=notes,
        advertised_flavor_note_ids=list(advertised_flavor_note_ids),
    )
    db.add(coffee)
    db.flush()  # populate coffee.id for FK on origin rows + m2m assignment

    # Insert origin rows in sort_order sequence (D-22).
    for i, (country, region) in enumerate(origins or []):
        db.add(
            CoffeeOrigin(
                coffee_id=coffee.id,
                country=country,
                region=region,
                sort_order=i,
            )
        )

    # Assign varietal m2m (CATALOG-05). Load Varietal objects by ID and assign
    # to the relationship; SQLAlchemy handles the join-table inserts.
    if varietal_ids:
        varietals = list(
            db.execute(select(Varietal).where(Varietal.id.in_(varietal_ids))).scalars().all()
        )
        coffee.varietals = varietals

    db.commit()
    log.info(
        CATALOG_COFFEE_CREATED,
        coffee_id=coffee.id,
        roaster_id=roaster_id,
        user_id=by_user_id,
    )
    return coffee


def get_coffee(db: Session, *, coffee_id: int) -> Coffee | None:
    """Return the coffee with *coffee_id*, or ``None`` if missing."""
    return db.execute(select(Coffee).where(Coffee.id == coffee_id)).scalar_one_or_none()


def get_coffee_with_bags(db: Session, *, coffee_id: int) -> tuple[Coffee, list[Bag]] | None:
    """Return ``(Coffee, list[Bag])`` for the detail page, or ``None``.

    Bags ordered by ``opened_at DESC NULLS LAST, created_at DESC`` so the
    most-recently-opened bag tops the list while never-opened bags fall
    to the end (Postgres ``NULLS LAST`` ordering hint).
    """
    coffee = db.execute(select(Coffee).where(Coffee.id == coffee_id)).scalar_one_or_none()
    if coffee is None:
        return None
    bags = list(
        db.execute(
            select(Bag)
            .where(Bag.coffee_id == coffee_id)
            .order_by(Bag.opened_at.desc().nulls_last(), Bag.created_at.desc())
        )
        .scalars()
        .all()
    )
    return coffee, bags


def list_coffees(
    db: Session,
    *,
    roaster_id: int | None = None,
    country: str | None = None,
    process: str | None = None,
    archived: bool = False,
) -> list[Coffee]:
    """Return coffees matching the four filter dimensions.

    Ordering: ``Coffee.name`` (CITEXT case-insensitive natural order).

    Filter semantics:

    * ``archived=False`` (default) → only non-archived rows.
    * ``archived=True`` → only archived rows (UI-SPEC lock — NOT a union).
    * ``roaster_id`` → exact match (FK).
    * ``country`` → exact match against coffee_origins.country (D-05:
      country column moved to coffee_origins join table; URL param name
      ``country`` is preserved for URL stability per plan 15.1-01).
    * ``process`` → exact match against the 6-value enum.

    All filter params are bound via SQLAlchemy parameterized ``where``
    clauses — no string concatenation, no SQLi exposure.
    """
    stmt = select(Coffee).distinct()
    if archived:
        stmt = stmt.where(Coffee.archived.is_(True))
    else:
        stmt = stmt.where(Coffee.archived.is_(False))
    if roaster_id is not None:
        stmt = stmt.where(Coffee.roaster_id == roaster_id)
    if country:
        # Join coffee_origins to filter by origin country (D-05).
        stmt = stmt.join(CoffeeOrigin, CoffeeOrigin.coffee_id == Coffee.id).where(
            CoffeeOrigin.country == country
        )
    if process:
        stmt = stmt.where(Coffee.process == process)
    stmt = stmt.order_by(Coffee.name)
    return list(db.execute(stmt).scalars().all())


def update_coffee(
    db: Session,
    *,
    coffee_id: int,
    name: str,
    roaster_id: int | None,
    process: str | None,
    roast_level: str | None,
    notes: str,
    advertised_flavor_note_ids: list[int],
    origins: list[tuple[str, str | None]] | None = None,
    varietal_ids: list[int] | None = None,
    by_user_id: int,
) -> Coffee:
    """UPDATE the row, commit, re-fetch, emit ``catalog.coffee.updated``.

    Core ``update()`` so we can stamp ``updated_at = func.now()`` in the
    same statement (mirrors :func:`app.services.roasters.update_roaster`).
    The array column is overwritten wholesale on every update — Postgres
    array assignment replaces the entire value, not a merge.

    Origins use a replace strategy: delete all existing coffee_origins rows
    for the coffee, then insert the new set. Both ops happen in the same
    transaction as the Coffee row update (D-22 implicit blend promotion).

    Varietals use the ORM relationship assignment: load the existing coffee
    object, replace coffee.varietals with the new Varietal objects. SQLAlchemy
    handles the join-table deletes and inserts within the same transaction
    (CATALOG-05).
    """
    db.execute(
        update(Coffee)
        .where(Coffee.id == coffee_id)
        .values(
            name=name,
            roaster_id=roaster_id,
            process=process,
            roast_level=roast_level,
            notes=notes,
            advertised_flavor_note_ids=list(advertised_flavor_note_ids),
            updated_at=func.now(),
        )
    )

    # Replace origin rows (delete-then-insert within the same transaction).
    from sqlalchemy import delete as sql_delete

    db.execute(sql_delete(CoffeeOrigin).where(CoffeeOrigin.coffee_id == coffee_id))
    for i, (country, region) in enumerate(origins or []):
        db.add(
            CoffeeOrigin(
                coffee_id=coffee_id,
                country=country,
                region=region,
                sort_order=i,
            )
        )

    # Replace varietal m2m (CATALOG-05). Load the coffee object and reassign
    # the varietals relationship — SQLAlchemy syncs the join table.
    coffee = db.execute(select(Coffee).where(Coffee.id == coffee_id)).scalar_one()
    if varietal_ids is not None:
        new_varietals = list(
            db.execute(select(Varietal).where(Varietal.id.in_(varietal_ids))).scalars().all()
        )
        coffee.varietals = new_varietals

    db.commit()
    # Re-fetch to pick up all relationship data (origins + varietals).
    db.expire(coffee)
    coffee = db.execute(select(Coffee).where(Coffee.id == coffee_id)).scalar_one()
    log.info(
        CATALOG_COFFEE_UPDATED,
        coffee_id=coffee_id,
        roaster_id=roaster_id,
        user_id=by_user_id,
    )
    return coffee


def archive_coffee(db: Session, *, coffee_id: int, by_user_id: int) -> None:
    """Soft-delete a coffee (``archived=True``) and emit the event."""
    db.execute(
        update(Coffee).where(Coffee.id == coffee_id).values(archived=True, updated_at=func.now())
    )
    db.commit()
    log.info(
        CATALOG_COFFEE_ARCHIVED,
        coffee_id=coffee_id,
        user_id=by_user_id,
    )


def list_distinct_countries(db: Session) -> list[str]:
    """Return distinct country values from coffee_origins for the filter-bar dropdown.

    Ordered ascending. The dropdown is rebuilt on every list-page render
    so new coffees with new countries surface immediately; the optional
    ``GET /filters-panel`` endpoint reuses this for a partial refresh.

    Queries coffee_origins.country (D-05: coffees.country column removed,
    origin data lives in the join table). Function name preserved for URL
    stability and minimal call-site churn.
    """
    stmt = select(CoffeeOrigin.country).distinct().order_by(CoffeeOrigin.country)
    return [row for row in db.execute(stmt).scalars().all() if row]


def list_distinct_processes() -> tuple[str, ...]:
    """Return the locked 6-value process enum (module-level constant)."""
    return COFFEE_PROCESSES


def flavor_note_name_map(db: Session, *, ids: list[int]) -> dict[int, str]:
    """Return ``{flavor_note_id: name}`` for the given ids.

    Used by the list template to render advertised-flavor-note pills.
    Empty input → empty dict (no DB hit). Unknown ids are silently
    omitted (the historical ARRAY column carries bare ids — an archived
    or deleted flavor note id stays in the array but won't resolve to
    a pill).
    """
    if not ids:
        return {}
    stmt = select(FlavorNote.id, FlavorNote.name).where(FlavorNote.id.in_(ids))
    return {row.id: row.name for row in db.execute(stmt).all()}


__all__ = [
    "COFFEE_PROCESSES",
    "COFFEE_ROAST_LEVELS",
    "archive_coffee",
    "create_coffee",
    "flavor_note_name_map",
    "get_coffee",
    "get_coffee_with_bags",
    "list_coffees",
    "list_distinct_countries",
    "list_distinct_processes",
    "update_coffee",
]
