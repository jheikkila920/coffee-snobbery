"""Per-user brew-session CRUD + prefill resolution (BREW-01, BREW-02, BREW-09).

The first per-user service in the app. Mirrors the sync-service shape of
:mod:`app.services.equipment` (kwargs API after a leading ``*``, single commit
per write, structlog audit at end of transaction) with three Phase-5 additions:

1. **Per-user scoping (T-05-05 IDOR defense).** Every read / update / delete is
   filtered by ``user_id``. ``update`` / ``get`` return ``None`` and ``delete``
   returns ``False`` for a session not owned by the caller — the router maps the
   sentinel to a 404 so a bare ``session_id`` never grants cross-user access.

2. **``equipment.usage_count`` maintenance (Pitfall 6).** Phase 4 shipped the
   counter at 0 and explicitly deferred the increment to Phase 5. In the SAME
   transaction as the session write this service: ``+1`` each non-null of
   (brewer, grinder, kettle) on create; diffs old-vs-new and ``±1`` per changed
   FK on update; ``-1`` each non-null FK on delete. All three FKs are handled
   together so the counter never drifts from reality.

3. **Prefill resolution (D-04/D-05/D-06/D-08).** The <30s logging engine. See
   :func:`resolve_prefill` and its three component queries below.

``extraction_yield_pct`` is a Postgres GENERATED column — it is NEVER set or
updated here (it is absent from every writable schema and from the writable
field set below). ``brewed_at`` defaults to a tz-aware UTC ``now()`` when the
caller passes ``None`` (store UTC; the router/template renders in
``APP_TIMEZONE``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.events import (
    BREW_SESSION_CREATED,
    BREW_SESSION_DELETED,
    BREW_SESSION_UPDATED,
)
from app.models.bag import Bag
from app.models.brew_session import BrewSession
from app.models.equipment import Equipment
from app.models.recipe import Recipe

log = structlog.get_logger(__name__)


def _sync_coffee_flavor_notes(
    db: Session,
    *,
    coffee_id: int,
    old_session_ids: list[int],
    new_session_ids: list[int],
) -> None:
    """Bidirectional sync of session chips to coffees.advertised_flavor_note_ids (D-07/D-08).

    Computes ``(current | added) - removed`` where:
    - ``current`` = coffee's existing advertised set
    - ``added``   = chips in new_session_ids but not in old_session_ids
    - ``removed`` = chips in old_session_ids but not in new_session_ids

    Does NOT call ``db.commit()`` — caller is responsible for the transaction.
    Handles ``None`` or empty array on the coffee gracefully (treats as empty set).
    """
    from app.models.coffee import Coffee  # local import to avoid circular

    coffee = db.execute(select(Coffee).where(Coffee.id == coffee_id)).scalar_one()
    current = set(coffee.advertised_flavor_note_ids or [])
    added = set(new_session_ids) - set(old_session_ids)
    removed = set(old_session_ids) - set(new_session_ids)
    updated = (current | added) - removed
    db.execute(
        update(Coffee)
        .where(Coffee.id == coffee_id)
        .values(advertised_flavor_note_ids=sorted(updated), updated_at=func.now())
    )
    # caller commits


# The four recipe-template fields D-05 lets a selected recipe override on the
# brew form. Mapped from the recipe's own column names in :func:`recipe_targets`.
_RECIPE_TEMPLATE_FIELDS = (
    "dose_grams_actual",
    "water_grams_actual",
    "water_temp_c_actual",
    "grind_setting_actual",
)

# The three per-attempt fields D-08 brew-again explicitly blanks (a new brew is
# a fresh attempt — rating / observed notes / notes are never carried over).
_PER_ATTEMPT_FIELDS = ("rating", "flavor_note_ids_observed", "notes")

# Writable session columns the update path may set. extraction_yield_pct
# (GENERATED) and user_id (server-owned) are deliberately absent.
_WRITABLE_FIELDS = frozenset(
    {
        "coffee_id",
        "bag_id",
        "recipe_id",
        "brewer_id",
        "grinder_id",
        "kettle_id",
        "water_type",
        "dose_grams_actual",
        "water_grams_actual",
        "yield_grams_actual",
        "tds_pct",
        "water_temp_c_actual",
        "grind_setting_actual",
        "rating",
        "flavor_note_ids_observed",
        "notes",
        "brewed_at",
        "brew_time_seconds",
    }
)

# The fields prefill carries forward from a source session (everything except
# the per-attempt fields, which are always blanked on /brew/new).
_CARRYABLE_FIELDS = (
    "coffee_id",
    "bag_id",
    "recipe_id",
    "brewer_id",
    "grinder_id",
    "kettle_id",
    "water_type",
    "dose_grams_actual",
    "water_grams_actual",
    "yield_grams_actual",
    "tds_pct",
    "water_temp_c_actual",
    "grind_setting_actual",
)


def _adjust_usage_counts(db: Session, *, deltas: dict[int, int]) -> None:
    """Apply ``usage_count += delta`` for each equipment id in *deltas*.

    Groups ids by delta so each distinct delta is one ``UPDATE ... WHERE id IN``
    — the same parameterized Core ``update()`` the brew write uses. A delta of 0
    is skipped (a net-unchanged FK on an edit). Runs in the caller's open
    transaction (no commit here) so the counter moves atomically with the
    session row.
    """
    by_delta: dict[int, list[int]] = {}
    for eq_id, delta in deltas.items():
        if delta:
            by_delta.setdefault(delta, []).append(eq_id)
    for delta, ids in by_delta.items():
        db.execute(
            update(Equipment)
            .where(Equipment.id.in_(ids))
            .values(usage_count=Equipment.usage_count + delta)
        )


def _equipment_deltas_for_change(
    old: tuple[int | None, int | None, int | None],
    new: tuple[int | None, int | None, int | None],
) -> dict[int, int]:
    """Net per-equipment delta for an edit changing the three equipment FKs.

    Each slot (brewer, grinder, kettle) contributes -1 to the old id and +1 to
    the new id when they differ; an unchanged slot contributes nothing. Deltas
    accumulate so re-pointing two slots at the same equipment nets correctly.
    """
    deltas: dict[int, int] = {}
    for old_id, new_id in zip(old, new, strict=True):
        if old_id == new_id:
            continue
        if old_id is not None:
            deltas[old_id] = deltas.get(old_id, 0) - 1
        if new_id is not None:
            deltas[new_id] = deltas.get(new_id, 0) + 1
    return deltas


# --------------------------------------------------------------------------- #
# CRUD                                                                         #
# --------------------------------------------------------------------------- #


def create_brew_session(
    db: Session,
    *,
    by_user_id: int,
    coffee_id: int,
    bag_id: int | None,
    recipe_id: int | None,
    brewer_id: int | None,
    grinder_id: int | None,
    kettle_id: int | None,
    water_type: str | None,
    dose_grams_actual: Decimal,
    water_grams_actual: Decimal,
    yield_grams_actual: Decimal | None,
    tds_pct: Decimal | None,
    water_temp_c_actual: Decimal | None,
    grind_setting_actual: str | None,
    rating: Decimal | None,
    flavor_note_ids_observed: list[int],
    notes: str,
    brewed_at: datetime | None,
    brew_time_seconds: int | None = None,
) -> BrewSession:
    """Insert a per-user brew session, bump equipment usage, emit the audit event.

    ``extraction_yield_pct`` is NEVER set — it is GENERATED in Postgres.
    ``brewed_at`` defaults to tz-aware UTC ``now()`` when ``None``. The three
    equipment ``usage_count`` increments happen in the same transaction before
    commit (Pitfall 6).
    """
    session = BrewSession(
        user_id=by_user_id,
        coffee_id=coffee_id,
        bag_id=bag_id,
        recipe_id=recipe_id,
        brewer_id=brewer_id,
        grinder_id=grinder_id,
        kettle_id=kettle_id,
        water_type=water_type,
        dose_grams_actual=dose_grams_actual,
        water_grams_actual=water_grams_actual,
        yield_grams_actual=yield_grams_actual,
        tds_pct=tds_pct,
        water_temp_c_actual=water_temp_c_actual,
        grind_setting_actual=grind_setting_actual,
        rating=rating,
        flavor_note_ids_observed=flavor_note_ids_observed,
        notes=notes,
        brewed_at=brewed_at if brewed_at is not None else datetime.now(UTC),
        brew_time_seconds=brew_time_seconds,
    )
    db.add(session)
    # +1 each non-null equipment FK, same transaction (before commit).
    _adjust_usage_counts(
        db,
        deltas={eq_id: 1 for eq_id in (brewer_id, grinder_id, kettle_id) if eq_id is not None},
    )
    db.flush()  # populate id for the audit event
    # D-07/D-08: write-back chips to parent coffee in the SAME transaction.
    _sync_coffee_flavor_notes(
        db,
        coffee_id=coffee_id,
        old_session_ids=[],
        new_session_ids=flavor_note_ids_observed,
    )
    db.commit()
    log.info(BREW_SESSION_CREATED, session_id=session.id, user_id=by_user_id)
    return session


def update_brew_session(
    db: Session,
    *,
    session_id: int,
    by_user_id: int,
    **fields: Any,
) -> BrewSession | None:
    """Update a user-owned session, diff usage_count, emit ``brew.session.updated``.

    Returns ``None`` (no mutation) when the session is missing or owned by a
    different user (IDOR defense — the router maps to 404). Only declared
    writable fields are applied; ``extraction_yield_pct`` and ``user_id`` can
    never be set. ``usage_count`` is diffed across the three equipment FKs in
    the same transaction (Pitfall 6).
    """
    session = db.execute(
        select(BrewSession).where(BrewSession.id == session_id, BrewSession.user_id == by_user_id)
    ).scalar_one_or_none()
    if session is None:
        return None

    old_equipment = (session.brewer_id, session.grinder_id, session.kettle_id)
    # D-08: capture old chips before update for bidirectional sync diff.
    old_flavor_note_ids = list(session.flavor_note_ids_observed or [])

    # Apply only declared writable fields the caller actually passed.
    values: dict[str, Any] = {k: v for k, v in fields.items() if k in _WRITABLE_FIELDS}

    new_equipment = (
        values.get("brewer_id", session.brewer_id),
        values.get("grinder_id", session.grinder_id),
        values.get("kettle_id", session.kettle_id),
    )
    deltas = _equipment_deltas_for_change(old_equipment, new_equipment)
    _adjust_usage_counts(db, deltas=deltas)

    if values:
        values["updated_at"] = func.now()
        db.execute(
            update(BrewSession)
            .where(BrewSession.id == session_id, BrewSession.user_id == by_user_id)
            .values(**values)
        )
    # D-07/D-08: write-back to parent coffee in the SAME transaction.
    new_flavor_note_ids = list(values.get("flavor_note_ids_observed", old_flavor_note_ids) or [])
    _sync_coffee_flavor_notes(
        db,
        coffee_id=session.coffee_id,
        old_session_ids=old_flavor_note_ids,
        new_session_ids=new_flavor_note_ids,
    )
    db.commit()
    refreshed = db.execute(
        select(BrewSession).where(BrewSession.id == session_id, BrewSession.user_id == by_user_id)
    ).scalar_one()
    log.info(BREW_SESSION_UPDATED, session_id=session_id, user_id=by_user_id)
    return refreshed


def delete_brew_session(db: Session, *, session_id: int, by_user_id: int) -> bool:
    """Delete a user-owned session, decrement usage_count, emit the audit event.

    Returns ``False`` when the session is missing or owned by another user
    (IDOR defense). On success each non-null equipment FK is decremented by 1 in
    the same transaction (Pitfall 6).
    """
    session = db.execute(
        select(BrewSession).where(BrewSession.id == session_id, BrewSession.user_id == by_user_id)
    ).scalar_one_or_none()
    if session is None:
        return False

    _adjust_usage_counts(
        db,
        deltas={
            eq_id: -1
            for eq_id in (session.brewer_id, session.grinder_id, session.kettle_id)
            if eq_id is not None
        },
    )
    db.delete(session)
    db.commit()
    log.info(BREW_SESSION_DELETED, session_id=session_id, user_id=by_user_id)
    return True


# --------------------------------------------------------------------------- #
# Read helpers (all scoped by user_id)                                         #
# --------------------------------------------------------------------------- #


def get_brew_session(db: Session, *, session_id: int, by_user_id: int) -> BrewSession | None:
    """Return the user-owned session, or ``None`` (missing OR not owned)."""
    return db.execute(
        select(BrewSession).where(BrewSession.id == session_id, BrewSession.user_id == by_user_id)
    ).scalar_one_or_none()


def list_brew_sessions(
    db: Session,
    *,
    by_user_id: int,
    coffee_id: int | None = None,
    brewer_id: int | None = None,
    rating_min: Decimal | None = None,
    rating_max: Decimal | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[BrewSession]:
    """Return the user's sessions newest-first, with optional filters applied.

    Default sort ``brewed_at DESC`` (Claude's Discretion). Every filter is
    applied only when provided; all clauses are parameterized ``select()`` —
    no string SQL (SQLi defense T-05-06). Uses the
    ``(user_id, brewed_at DESC)`` / ``(user_id, coffee_id, brewed_at DESC)``
    indexes from Plan 01.
    """
    stmt = select(BrewSession).where(BrewSession.user_id == by_user_id)
    if coffee_id is not None:
        stmt = stmt.where(BrewSession.coffee_id == coffee_id)
    if brewer_id is not None:
        stmt = stmt.where(BrewSession.brewer_id == brewer_id)
    if rating_min is not None:
        stmt = stmt.where(BrewSession.rating >= rating_min)
    if rating_max is not None:
        stmt = stmt.where(BrewSession.rating <= rating_max)
    if date_from is not None:
        stmt = stmt.where(BrewSession.brewed_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(BrewSession.brewed_at <= date_to)
    stmt = stmt.order_by(BrewSession.brewed_at.desc())
    return list(db.execute(stmt).scalars().all())


# --------------------------------------------------------------------------- #
# Prefill resolution (D-04 / D-05 / D-06 / D-08)                              #
# --------------------------------------------------------------------------- #


def latest_session(
    db: Session, *, by_user_id: int, coffee_id: int | None = None
) -> BrewSession | None:
    """Most recent session for the user (D-04 hybrid).

    Omit ``coffee_id`` for the open-form default (the user's single most-recent
    session); pass it to re-source from the last session WITH that coffee when
    the user switches coffees. Uses the ``(user_id, coffee_id, brewed_at DESC)``
    index from Plan 01.
    """
    stmt = select(BrewSession).where(BrewSession.user_id == by_user_id)
    if coffee_id is not None:
        stmt = stmt.where(BrewSession.coffee_id == coffee_id)
    stmt = stmt.order_by(BrewSession.brewed_at.desc()).limit(1)
    return db.execute(stmt).scalars().first()


def newest_open_bag_id(db: Session, *, coffee_id: int) -> int | None:
    """Id of the coffee's newest OPEN bag (D-06), or ``None`` when none open.

    Open = ``finished_at IS NULL``. Ordered ``opened_at DESC NULLS LAST,
    created_at DESC`` (mirrors :func:`app.services.bags.list_bags_for_coffee`).
    """
    return db.execute(
        select(Bag.id)
        .where(Bag.coffee_id == coffee_id, Bag.finished_at.is_(None))
        .order_by(Bag.opened_at.desc().nulls_last(), Bag.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def recipe_targets(db: Session, *, recipe_id: int) -> dict[str, Any] | None:
    """The four D-05 template fields from a recipe, or ``None`` if missing.

    Maps the recipe's ``dose_grams`` / ``water_grams`` / ``water_temp_c`` /
    ``grind_setting`` onto the session field names so the caller can splat them
    over last-session values (recipe-wins).
    """
    recipe = db.execute(select(Recipe).where(Recipe.id == recipe_id)).scalar_one_or_none()
    if recipe is None:
        return None
    return {
        "dose_grams_actual": recipe.dose_grams,
        "water_grams_actual": recipe.water_grams,
        "water_temp_c_actual": recipe.water_temp_c,
        "grind_setting_actual": recipe.grind_setting,
    }


def resolve_prefill(
    db: Session,
    *,
    by_user_id: int,
    from_session_id: int | None = None,
    coffee_id: int | None = None,
    recipe_id: int | None = None,
) -> dict[str, Any]:
    """Resolve the /brew/new prefill dict (D-04/D-05/D-06/D-08).

    Single entry point the router calls. Logic order:

    1. **Source (D-08 brew-again vs D-04 hybrid).** When ``from_session_id`` is
       set, source the carryable fields from that user's session (scoped by
       ``user_id``; a bag that is no longer active drops to ``None``) — D-08
       overrides D-04. Otherwise apply the D-04 hybrid: the user's last session,
       optionally the last session WITH ``coffee_id`` when the caller passed it.
    2. **D-06 default bag.** When a coffee is resolved and ``bag_id`` is unset,
       default to that coffee's newest open bag.
    3. **D-05 recipe-wins.** When ``recipe_id`` is selected, the four template
       fields come from the recipe, overriding last-session values.
    4. **Always blank the per-attempt fields** (rating / observed notes / notes)
       — every /brew/new is a fresh attempt.

    Returns a plain dict the template can render; the router layers on the
    per-field touched-state and pill captions.
    """
    prefill: dict[str, Any] = {field: None for field in _CARRYABLE_FIELDS}

    # 1. Source the carryable fields.
    source: BrewSession | None
    if from_session_id is not None:
        # D-08: source from the named session, scoped by user (IDOR defense).
        source = get_brew_session(db, session_id=from_session_id, by_user_id=by_user_id)
    else:
        # D-04 hybrid: last session, optionally with the given coffee.
        source = latest_session(db, by_user_id=by_user_id, coffee_id=coffee_id)

    if source is not None:
        for field in _CARRYABLE_FIELDS:
            prefill[field] = getattr(source, field)
        # D-08: drop a bag that is no longer active (finished or deleted).
        if from_session_id is not None and prefill.get("bag_id") is not None:
            still_open = db.execute(
                select(Bag.id).where(Bag.id == prefill["bag_id"], Bag.finished_at.is_(None))
            ).scalar_one_or_none()
            if still_open is None:
                prefill["bag_id"] = None

    # An explicit coffee_id from the caller wins over the source's coffee
    # (the user changed the coffee selector) and re-triggers D-06.
    if coffee_id is not None:
        prefill["coffee_id"] = coffee_id

    # 2. D-06: default bag to the coffee's newest open bag when unset.
    resolved_coffee = prefill.get("coffee_id")
    if resolved_coffee is not None and prefill.get("bag_id") is None:
        prefill["bag_id"] = newest_open_bag_id(db, coffee_id=resolved_coffee)

    # 3. D-05 recipe-wins for the four template fields.
    if recipe_id is not None:
        prefill["recipe_id"] = recipe_id
        targets = recipe_targets(db, recipe_id=recipe_id)
        if targets is not None:
            prefill.update({k: targets[k] for k in _RECIPE_TEMPLATE_FIELDS})

    # 4. Always blank the per-attempt fields on /brew/new.
    prefill["rating"] = None
    # D-06/D-12: prefill chips from the parent coffee's advertised set ONLY.
    # Do NOT also pull the user's most-recent session chips (those surface
    # via the existing prefill summary separately).
    if resolved_coffee is not None:
        from app.models.coffee import Coffee  # local import to avoid circular

        coffee_row = db.execute(
            select(Coffee.advertised_flavor_note_ids).where(Coffee.id == resolved_coffee)
        ).scalar_one_or_none()
        prefill["flavor_note_ids_observed"] = list(coffee_row or [])
    else:
        prefill["flavor_note_ids_observed"] = []
    prefill["notes"] = ""

    return prefill


__all__ = [
    "create_brew_session",
    "delete_brew_session",
    "get_brew_session",
    "latest_session",
    "list_brew_sessions",
    "newest_open_bag_id",
    "recipe_targets",
    "resolve_prefill",
    "update_brew_session",
]
