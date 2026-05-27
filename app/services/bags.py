"""Bags CRUD service — CAT-08.

Sync :class:`Session` per Phase 3 D-07; kwargs API per Phase 1 D-14 /
Phase 3 D-08; audit events per Phase 1 D-14 taxonomy. Mirrors the
structural template of :mod:`app.services.roasters` and
:mod:`app.services.coffees` (plans 04-04 / 04-07): sync ``Session``,
kwargs-only API after a leading ``*``, single commit per write,
audit-event emission at end of write.

Plan 04-09 adds the photo-lifecycle surface on top of the universal
catalog shape. :func:`attach_or_replace_photo` composes
:mod:`app.services.photos` (plan 04-01) — never decodes image bytes
itself. Order is locked by D-07 ("write-new-then-delete-old"): the
photos service writes the NEW file first, the service then commits the
new ``photo_filename`` to the DB row, and only THEN unlinks the old
file via :func:`app.services.photos.replace_photo`. Reversing the order
risks pointing the DB at a missing file if the unlink succeeds but the
DB write fails — D-07 names that as the load-bearing footgun.

Public surface (consumed by :mod:`app.routers.bags`):

* :func:`create_bag` — INSERT + commit + ``catalog.bag.created``.
* :func:`get_bag` — single-row fetch by id; returns ``None`` if missing.
* :func:`list_bags_for_coffee` — ordered by ``opened_at DESC NULLS LAST,
  created_at DESC`` (matches :func:`app.services.coffees.get_coffee_with_bags`).
* :func:`update_bag` — UPDATE + commit + ``catalog.bag.updated``.
* :func:`archive_bag` — sets ``finished_at = now()`` (the locked archive
  semantic — bags have no ``archived`` column; ``finished_at IS NOT NULL``
  is the archive surrogate per the plan-04-09 lock). Emits
  ``catalog.bag.archived``.
* :func:`attach_or_replace_photo` — composes photos service +
  ``write-new-then-delete-old``; emits ``catalog.bag.photo_uploaded`` with
  ``replaced=True|False``. Raises :class:`app.services.photos.PhotoRejected`
  on any byte-level rejection (the router catches → 200 + zone re-render).
* :func:`delete_photo` — clears ``photo_filename`` + unlinks the old pair;
  emits ``catalog.bag.photo_deleted``.

Domain exception
----------------

A ``BagNotFound`` exception is intentionally NOT defined here. The router
catches the ``None`` from :func:`get_bag` and raises ``HTTPException(404)``
itself — mirroring the roasters / coffees routers, which do the same with
their own service-layer ``None`` returns.
"""

from __future__ import annotations

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.events import (
    CATALOG_BAG_ARCHIVED,
    CATALOG_BAG_CREATED,
    CATALOG_BAG_PHOTO_DELETED,
    CATALOG_BAG_PHOTO_UPLOADED,
    CATALOG_BAG_UPDATED,
)
from app.models.bag import Bag
from app.services import photos as photos_service

log = structlog.get_logger(__name__)


# --------------------------------------------------------------------------- #
# CRUD                                                                        #
# --------------------------------------------------------------------------- #


def create_bag(
    db: Session,
    *,
    coffee_id: int,
    weight_grams: int | None = None,
    opened_at=None,
    finished_at=None,
    notes: str = "",
    by_user_id: int,
) -> Bag:
    """Insert a new bag row and emit ``catalog.bag.created``.

    The FK constraint on ``coffee_id`` is ``ondelete="RESTRICT"`` (plan
    04-03). Inserting a bag for a coffee_id that doesn't exist raises
    :class:`sqlalchemy.exc.IntegrityError`; the router pre-checks
    coffee existence via :func:`app.services.coffees.get_coffee` and
    returns 404 before the INSERT runs.
    """
    bag = Bag(
        coffee_id=coffee_id,
        weight_grams=weight_grams,
        opened_at=opened_at,
        finished_at=finished_at,
        notes=notes,
    )
    db.add(bag)
    db.flush()
    db.commit()
    log.info(
        CATALOG_BAG_CREATED,
        bag_id=bag.id,
        coffee_id=coffee_id,
        user_id=by_user_id,
    )
    return bag


def get_bag(db: Session, *, bag_id: int) -> Bag | None:
    """Return the bag with *bag_id*, or ``None`` if missing."""
    return db.execute(select(Bag).where(Bag.id == bag_id)).scalar_one_or_none()


def list_bags_for_coffee(db: Session, *, coffee_id: int) -> list[Bag]:
    """Return bags for *coffee_id* ordered by ``opened_at DESC NULLS LAST, created_at DESC``.

    Matches :func:`app.services.coffees.get_coffee_with_bags` ordering so
    a list rendered via either helper looks identical.
    """
    stmt = (
        select(Bag)
        .where(Bag.coffee_id == coffee_id)
        .order_by(Bag.opened_at.desc().nulls_last(), Bag.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


def update_bag(
    db: Session,
    *,
    bag_id: int,
    weight_grams: int | None = None,
    opened_at=None,
    finished_at=None,
    notes: str = "",
    by_user_id: int,
) -> Bag:
    """UPDATE the row, commit, re-fetch, emit ``catalog.bag.updated``.

    Core ``update()`` so ``updated_at = func.now()`` stamps in the same
    statement (mirrors :func:`app.services.roasters.update_roaster`).
    """
    db.execute(
        update(Bag)
        .where(Bag.id == bag_id)
        .values(
            weight_grams=weight_grams,
            opened_at=opened_at,
            finished_at=finished_at,
            notes=notes,
            updated_at=func.now(),
        )
    )
    db.commit()
    bag = db.execute(select(Bag).where(Bag.id == bag_id)).scalar_one()
    log.info(
        CATALOG_BAG_UPDATED,
        bag_id=bag_id,
        user_id=by_user_id,
    )
    return bag


def archive_bag(db: Session, *, bag_id: int, by_user_id: int) -> None:
    """Mark the bag finished — the locked Phase 4 archive semantic.

    Bags have NO ``archived`` column (plan 04-03 schema lock). The
    archive surrogate is ``finished_at IS NOT NULL``. Downstream filters
    and list views treat ``finished_at IS NULL`` as "open bags" and
    ``finished_at IS NOT NULL`` as "finished/archived". This service
    stamps ``finished_at = func.now()`` and emits
    ``catalog.bag.archived``.
    """
    db.execute(
        update(Bag).where(Bag.id == bag_id).values(finished_at=func.now(), updated_at=func.now())
    )
    db.commit()
    log.info(
        CATALOG_BAG_ARCHIVED,
        bag_id=bag_id,
        user_id=by_user_id,
    )


# --------------------------------------------------------------------------- #
# Photo lifecycle (composes app.services.photos)                              #
# --------------------------------------------------------------------------- #


def attach_or_replace_photo(
    db: Session,
    *,
    bag_id: int,
    blob: bytes,
    by_user_id: int,
) -> Bag:
    """Save bytes via photos service, update the bag's ``photo_filename``.

    Order (D-07 write-new-then-delete-old):

    1. ``photos_service.process_and_save(blob)`` writes the NEW main +
       thumb pair to disk. May raise :class:`PhotoRejected`; the router
       catches and re-renders the upload zone with the friendly message.
    2. Read the OLD ``photo_filename`` off the bag row.
    3. UPDATE the bag row with the new filename.
    4. ``photos_service.replace_photo(old, new)`` unlinks the old pair.
       Runs AFTER the DB commit so the DB never points at a missing file
       if the unlink fails (logged-and-tolerated per the photos service).

    Returns the re-fetched bag with ``photo_filename`` set to the new value.
    """
    bag = get_bag(db, bag_id=bag_id)
    if bag is None:
        # Surfaces as 404 from the router (callers always go via
        # the router which validates bag_id first; included here as a
        # belt-and-braces guard).
        raise ValueError(f"bag {bag_id} not found")

    # Step 1: write the new file. May raise PhotoRejected — router catches.
    new_filename = photos_service.process_and_save(blob)

    # Step 2: capture the old filename BEFORE the update.
    old_filename = bag.photo_filename

    # Step 3: commit the new filename to the DB row.
    db.execute(
        update(Bag)
        .where(Bag.id == bag_id)
        .values(photo_filename=new_filename, updated_at=func.now())
    )
    db.commit()

    # Step 4: unlink the old file pair AFTER the DB update succeeds.
    # ``replace_photo`` is a no-op when ``old_filename`` is None
    # (first-photo path).
    photos_service.replace_photo(old_filename=old_filename, new_filename=new_filename)

    log.info(
        CATALOG_BAG_PHOTO_UPLOADED,
        bag_id=bag_id,
        filename=new_filename,
        replaced=old_filename is not None,
        user_id=by_user_id,
    )

    # Re-fetch and return so the row template gets a fresh photo_filename.
    return db.execute(select(Bag).where(Bag.id == bag_id)).scalar_one()


def delete_photo(db: Session, *, bag_id: int, by_user_id: int) -> Bag:
    """Clear the bag's ``photo_filename`` and unlink the on-disk pair.

    Idempotent: bags without a photo are a clean no-op (the photos
    service's :func:`unlink_safe` accepts ``None``).
    """
    bag = get_bag(db, bag_id=bag_id)
    if bag is None:
        raise ValueError(f"bag {bag_id} not found")

    old_filename = bag.photo_filename
    db.execute(
        update(Bag).where(Bag.id == bag_id).values(photo_filename=None, updated_at=func.now())
    )
    db.commit()

    photos_service.unlink_safe(old_filename)

    log.info(
        CATALOG_BAG_PHOTO_DELETED,
        bag_id=bag_id,
        filename=old_filename,
        user_id=by_user_id,
    )

    return db.execute(select(Bag).where(Bag.id == bag_id)).scalar_one()


__all__ = [
    "archive_bag",
    "attach_or_replace_photo",
    "create_bag",
    "delete_photo",
    "get_bag",
    "list_bags_for_coffee",
    "update_bag",
]
