"""Analytics service — the home page brain (HOME-01..05, HOME-07, HOME-08).

All nine public functions are pure read-only SQL derivations over the user's own
brew log. Every function takes ``(db: Session, user_id: int)`` and returns rows
or a dict. No side effects, no structlog emits (reads carry no audit weight).

Per-user scoping (T-06-01 IDOR defense): the first WHERE clause on every query
is ``BrewSession.user_id == user_id``. user_id is always a typed function arg,
never a global or request param.

``compute_input_signature`` is the Phase 7 stale-data plumbing: SHA256 hex over
the canonical JSON of the user's RATED sessions' AI-input fields (D-08/D-09,
COST-4). Returns ``_EMPTY_SIGNATURE`` when the user has zero rated sessions.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import Date as SaDate
from sqlalchemy import case, cast, func, literal, select
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session, aliased

from app.models.bag import Bag
from app.models.brew_session import BrewSession
from app.models.coffee import Coffee
from app.models.equipment import Equipment
from app.models.flavor_note import FlavorNote
from app.models.recipe import Recipe
from app.models.roaster import Roaster

log = structlog.get_logger(__name__)

# Stable sentinel returned when the user has zero RATED sessions (D-09).
# Phase 7 compares against this to skip a re-generation for new users.
_EMPTY_SIGNATURE: str = hashlib.sha256(b"[]").hexdigest()


# --------------------------------------------------------------------------- #
# HOME-01: Top coffees                                                         #
# --------------------------------------------------------------------------- #


def get_top_coffees(db: Session, user_id: int) -> list[Row]:
    """Return <=5 coffees ranked by the user's avg rating, min 2 rated sessions.

    Excludes NULL ratings (Pitfall 1). Tie-broken avg_rating DESC, then
    session_count DESC (Claude's Discretion).
    """
    stmt = (
        select(
            Coffee.id,
            Coffee.name,
            func.avg(BrewSession.rating).label("avg_rating"),
            func.count(BrewSession.id).label("session_count"),
        )
        .join(Coffee, BrewSession.coffee_id == Coffee.id)
        .where(
            BrewSession.user_id == user_id,
            BrewSession.rating.is_not(None),
        )
        .group_by(Coffee.id, Coffee.name)
        .having(func.count(BrewSession.id) >= 2)
        .order_by(func.avg(BrewSession.rating).desc(), func.count(BrewSession.id).desc())
        .limit(5)
    )
    return db.execute(stmt).all()


# --------------------------------------------------------------------------- #
# HOME-02: Preference profile                                                  #
# --------------------------------------------------------------------------- #


def get_preference_profile(db: Session, user_id: int) -> dict[str, list[Row]]:
    """Return a dict with keys origin/process/roaster/roast_level.

    Each value is a list of (label, avg_rating, session_count) rows with
    session_count >= 2 (D-06). NULL ratings excluded. Four separate GROUP BY
    queries executed in this service; results returned as a dict so the
    template / router can render all four dimensions in one fragment.
    """

    def _dim_query(label_col: Any, group_col: Any) -> list[Row]:
        stmt = (
            select(
                label_col.label("label"),
                func.avg(BrewSession.rating).label("avg_rating"),
                func.count(BrewSession.id).label("session_count"),
            )
            .join(Coffee, BrewSession.coffee_id == Coffee.id)
            .where(
                BrewSession.user_id == user_id,
                BrewSession.rating.is_not(None),
                group_col.is_not(None),
            )
            .group_by(group_col)
            .having(func.count(BrewSession.id) >= 2)
            .order_by(func.avg(BrewSession.rating).desc(), func.count(BrewSession.id).desc())
        )
        return db.execute(stmt).all()

    # Roaster dimension needs a JOIN to roasters for the name
    roaster_stmt = (
        select(
            Roaster.name.label("label"),
            func.avg(BrewSession.rating).label("avg_rating"),
            func.count(BrewSession.id).label("session_count"),
        )
        .join(Coffee, BrewSession.coffee_id == Coffee.id)
        .join(Roaster, Coffee.roaster_id == Roaster.id)
        .where(
            BrewSession.user_id == user_id,
            BrewSession.rating.is_not(None),
        )
        .group_by(Roaster.name)
        .having(func.count(BrewSession.id) >= 2)
        .order_by(func.avg(BrewSession.rating).desc(), func.count(BrewSession.id).desc())
    )

    return {
        "origin": _dim_query(Coffee.origin, Coffee.origin),
        "process": _dim_query(Coffee.process, Coffee.process),
        "roaster": db.execute(roaster_stmt).all(),
        "roast_level": _dim_query(Coffee.roast_level, Coffee.roast_level),
    }


# --------------------------------------------------------------------------- #
# HOME-03: Flavor descriptors                                                  #
# --------------------------------------------------------------------------- #


def get_flavor_descriptors(db: Session, user_id: int) -> list[Row]:
    """Top-10 flavor descriptors from the user's 4.0+ rated sessions, min 2 (D-07).

    Unnests brew_sessions.flavor_note_ids_observed (the OBSERVED array — never
    coffees.advertised_flavor_note_ids, Pitfall 2) via func.unnest().column_valued().
    """
    unnested = func.unnest(BrewSession.flavor_note_ids_observed).column_valued("note_id")

    stmt = (
        select(
            FlavorNote.id,
            FlavorNote.name,
            func.count().label("session_count"),
        )
        .select_from(BrewSession)
        .join(unnested, literal(True))
        .join(FlavorNote, FlavorNote.id == unnested.c.note_id)
        .where(
            BrewSession.user_id == user_id,
            BrewSession.rating.is_not(None),
            BrewSession.rating >= Decimal("4.0"),
        )
        .group_by(FlavorNote.id, FlavorNote.name)
        .having(func.count() >= 2)
        .order_by(func.count().desc())
        .limit(10)
    )
    return db.execute(stmt).all()


# --------------------------------------------------------------------------- #
# HOME-04: Roast freshness buckets                                             #
# --------------------------------------------------------------------------- #


def get_roast_freshness_buckets(db: Session, user_id: int) -> list[Row]:
    """Freshness buckets (0-3, 4-7, 8-14, 15-21, 22+ days) using bags.roast_date.

    Hard rule: reads bags.roast_date ONLY, never coffees.roast_date (Pitfall 4).
    Sessions without a bag or with roast_date=NULL are excluded by INNER JOIN.
    Buckets require >=2 rated sessions each (D-07).
    """
    days_expr = cast(BrewSession.brewed_at, SaDate) - Bag.roast_date

    bucket_expr = case(
        (days_expr <= 3, "0-3 days"),
        (days_expr <= 7, "4-7 days"),
        (days_expr <= 14, "8-14 days"),
        (days_expr <= 21, "15-21 days"),
        else_="22+ days",
    ).label("freshness_bucket")

    bucket_order_expr = case(
        (days_expr <= 3, 1),
        (days_expr <= 7, 2),
        (days_expr <= 14, 3),
        (days_expr <= 21, 4),
        else_=5,
    )

    stmt = (
        select(
            bucket_expr,
            func.avg(BrewSession.rating).label("avg_rating"),
            func.count(BrewSession.id).label("session_count"),
            func.min(bucket_order_expr).label("bucket_order"),
        )
        .join(Bag, BrewSession.bag_id == Bag.id)
        .where(
            BrewSession.user_id == user_id,
            BrewSession.rating.is_not(None),
            Bag.roast_date.is_not(None),
        )
        .group_by(bucket_expr)
        .having(func.count(BrewSession.id) >= 2)
        .order_by(func.min(bucket_order_expr))
    )
    return db.execute(stmt).all()


# --------------------------------------------------------------------------- #
# HOME-05: Sweet spots                                                         #
# --------------------------------------------------------------------------- #


def get_sweet_spots(db: Session, user_id: int) -> list[Row]:
    """Top 3 (origin x process x brewer x recipe) combos, min 3 rated sessions.

    Uses a single GROUP BY over all four dimension columns. Sessions with NULL
    brewer_id or recipe_id are excluded by INNER JOIN — this is the documented
    v1 behavior (Pitfall 7). No Python loops; pure SQL aggregation.
    """
    brewer = aliased(Equipment, name="brewer")

    stmt = (
        select(
            Coffee.origin.label("origin"),
            Coffee.process.label("process"),
            brewer.model.label("brewer_name"),
            Recipe.name.label("recipe_name"),
            func.avg(BrewSession.rating).label("avg_rating"),
            func.count(BrewSession.id).label("session_count"),
        )
        .join(Coffee, BrewSession.coffee_id == Coffee.id)
        .join(brewer, BrewSession.brewer_id == brewer.id)
        .join(Recipe, BrewSession.recipe_id == Recipe.id)
        .where(
            BrewSession.user_id == user_id,
            BrewSession.rating.is_not(None),
        )
        .group_by(
            Coffee.origin,
            Coffee.process,
            brewer.model,
            Recipe.name,
        )
        .having(func.count(BrewSession.id) >= 3)
        .order_by(func.avg(BrewSession.rating).desc(), func.count(BrewSession.id).desc())
        .limit(3)
    )
    return db.execute(stmt).all()


# --------------------------------------------------------------------------- #
# HOME-07: Recent brews                                                        #
# --------------------------------------------------------------------------- #


def get_recent_brews(db: Session, user_id: int) -> list[Row]:
    """Last 10 brew sessions joined to coffee, ordered brewed_at DESC.

    Does NOT require a rating — includes unrated sessions.
    """
    stmt = (
        select(
            BrewSession.id,
            BrewSession.brewed_at,
            BrewSession.rating,
            BrewSession.coffee_id,
            Coffee.name.label("coffee_name"),
        )
        .join(Coffee, BrewSession.coffee_id == Coffee.id)
        .where(BrewSession.user_id == user_id)
        .order_by(BrewSession.brewed_at.desc())
        .limit(10)
    )
    return db.execute(stmt).all()


# --------------------------------------------------------------------------- #
# HOME-08: Unrated coffees                                                     #
# --------------------------------------------------------------------------- #


def get_unrated_coffees(db: Session, user_id: int) -> list[Row]:
    """Non-archived coffees this user has never brewed.

    Excludes archived coffees (Coffee.archived == False) — an archived coffee
    must never appear as a "what to try next" suggestion (HOME-08 requirement).
    """
    brewed_subq = (
        select(BrewSession.coffee_id)
        .where(BrewSession.user_id == user_id)
        .distinct()
        .scalar_subquery()
    )

    stmt = (
        select(Coffee.id, Coffee.name, Coffee.origin, Coffee.roast_level)
        .where(
            Coffee.archived == False,  # noqa: E712
            Coffee.id.not_in(brewed_subq),
        )
        .order_by(Coffee.name)
    )
    return db.execute(stmt).all()


# --------------------------------------------------------------------------- #
# Cold-start gate counts                                                       #
# --------------------------------------------------------------------------- #


def get_cold_start_counts(db: Session, user_id: int) -> dict[str, Any]:
    """Return live counts for the cold-start gate (D-02).

    Counts ALL sessions including unrated (not the signature, which is D-09).
    gate_open = sessions >= 3 AND distinct_notes >= 5.
    """
    session_count: int = (
        db.scalar(
            select(func.count(BrewSession.id)).where(BrewSession.user_id == user_id)
        )
        or 0
    )

    unnested = func.unnest(BrewSession.flavor_note_ids_observed).column_valued("note_id")
    note_count: int = (
        db.scalar(
            select(func.count(func.distinct(unnested.c.note_id)))
            .select_from(BrewSession)
            .join(unnested, literal(True))
            .where(BrewSession.user_id == user_id)
        )
        or 0
    )

    return {
        "sessions": session_count,
        "distinct_notes": note_count,
        "gate_open": session_count >= 3 and note_count >= 5,
        "sessions_needed": max(0, 3 - session_count),
        "notes_needed": max(0, 5 - note_count),
    }


# --------------------------------------------------------------------------- #
# Signature computation (Phase 7 stale-data plumbing)                         #
# --------------------------------------------------------------------------- #


def compute_input_signature(db: Session, user_id: int) -> str:
    """SHA256 hex over this user's RATED sessions' AI-input fields (D-08/D-09, COST-4).

    Inputs per session: (coffee_id, float(rating), sorted flavor_note_ids_observed,
    recipe_id, brewer_id, bag roast_date isoformat-or-None).

    Free-text notes and timestamps are EXCLUDED so a notes typo-fix never
    invalidates the recommendation.

    Rows ordered by BrewSession.id (ascending, stable monotonic IDs) for
    determinism (Pitfall 5). Returns _EMPTY_SIGNATURE when zero rated sessions.

    COST-4: scope is strictly this user's OWN sessions; never shared catalog
    counts like equipment_count/recipe_count.
    """
    stmt = (
        select(
            BrewSession.id,
            BrewSession.coffee_id,
            BrewSession.rating,
            BrewSession.flavor_note_ids_observed,
            BrewSession.recipe_id,
            BrewSession.brewer_id,
            Bag.roast_date,
        )
        .outerjoin(Bag, BrewSession.bag_id == Bag.id)
        .where(
            BrewSession.user_id == user_id,
            BrewSession.rating.is_not(None),  # D-09: rated sessions only
        )
        .order_by(BrewSession.id)  # deterministic sort (Pitfall 5)
    )
    rows = db.execute(stmt).all()

    if not rows:
        return _EMPTY_SIGNATURE

    def _serialize_row(row: Row) -> list:  # type: ignore[type-arg]
        return [
            row.coffee_id,
            float(row.rating),  # Decimal → float for JSON
            sorted(row.flavor_note_ids_observed or []),
            row.recipe_id,
            row.brewer_id,
            row.roast_date.isoformat() if row.roast_date else None,
        ]

    payload = [_serialize_row(r) for r in rows]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
