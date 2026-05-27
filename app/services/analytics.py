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
from typing import Any

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session, aliased

from app.models.brew_session import BrewSession
from app.models.coffee import Coffee
from app.models.coffee_origin import CoffeeOrigin
from app.models.equipment import Equipment
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

    # Origin dimension joins coffee_origins (D-01). A blend with N origins
    # contributes N rows per session — every origin a coffee has counts
    # toward that origin's aggregate. Intentional: the user's "what origins
    # do I like" question wants both halves of a Yirg+Bourbon blend counted.
    origin_stmt = (
        select(
            CoffeeOrigin.country.label("label"),
            func.avg(BrewSession.rating).label("avg_rating"),
            func.count(BrewSession.id).label("session_count"),
        )
        .join(Coffee, BrewSession.coffee_id == Coffee.id)
        .join(CoffeeOrigin, CoffeeOrigin.coffee_id == Coffee.id)
        .where(
            BrewSession.user_id == user_id,
            BrewSession.rating.is_not(None),
        )
        .group_by(CoffeeOrigin.country)
        .having(func.count(BrewSession.id) >= 2)
        .order_by(func.avg(BrewSession.rating).desc(), func.count(BrewSession.id).desc())
    )

    return {
        "origin": db.execute(origin_stmt).all(),
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
    coffees.advertised_flavor_note_ids, Pitfall 2).

    Uses raw SQL for the unnest + implicit lateral join pattern because
    func.unnest().column_valued() produces a TableValuedColumn that SQLAlchemy's
    ORM join layer cannot resolve (Assumption A2 from RESEARCH.md, confirmed at
    runtime). The bound :user_id parameter prevents SQL injection (T-06-03).
    """
    stmt = text(
        """
        SELECT fn.id, fn.name, count(*) AS session_count
        FROM brew_sessions bs, unnest(bs.flavor_note_ids_observed) AS note_id
        JOIN flavor_notes fn ON fn.id = note_id
        WHERE bs.user_id = :user_id
          AND bs.rating IS NOT NULL
          AND bs.rating >= 4.0
        GROUP BY fn.id, fn.name
        HAVING count(*) >= 2
        ORDER BY session_count DESC
        LIMIT 10
        """
    )
    return db.execute(stmt, {"user_id": user_id}).all()


# --------------------------------------------------------------------------- #
# HOME-05: Sweet spots                                                         #
# --------------------------------------------------------------------------- #


def get_sweet_spots(db: Session, user_id: int) -> list[Row]:
    """Top 3 (origin x process x brewer x recipe) combos, min 3 rated sessions.

    Uses a single GROUP BY over all five dimension columns. Sessions with NULL
    brewer_id or recipe_id are excluded by INNER JOIN — this is the documented
    v1 behavior (Pitfall 7). No Python loops; pure SQL aggregation.

    Origin now joins coffee_origins (D-01); a blend session contributes one
    row per origin so the per-origin sweet-spot stays truthful.
    """
    brewer = aliased(Equipment, name="brewer")

    stmt = (
        select(
            CoffeeOrigin.country.label("origin"),
            Coffee.process.label("process"),
            brewer.model.label("brewer_name"),
            Recipe.name.label("recipe_name"),
            func.avg(BrewSession.rating).label("avg_rating"),
            func.count(BrewSession.id).label("session_count"),
        )
        .join(Coffee, BrewSession.coffee_id == Coffee.id)
        .join(CoffeeOrigin, CoffeeOrigin.coffee_id == Coffee.id)
        .join(brewer, BrewSession.brewer_id == brewer.id)
        .join(Recipe, BrewSession.recipe_id == Recipe.id)
        .where(
            BrewSession.user_id == user_id,
            BrewSession.rating.is_not(None),
        )
        .group_by(
            CoffeeOrigin.country,
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

    # Per-coffee comma-joined origin string (e.g. "Ethiopia, Brazil") so the
    # unrated-coffees card stays one row per coffee even for blends (D-22).
    # Ordered by sort_order so the primary origin comes first.
    origin_subq = (
        select(
            func.array_to_string(
                func.array_agg(aggregate_order_by(CoffeeOrigin.country, CoffeeOrigin.sort_order)),
                ", ",
            )
        )
        .where(CoffeeOrigin.coffee_id == Coffee.id)
        .correlate(Coffee)
        .scalar_subquery()
        .label("origin")
    )

    stmt = (
        select(Coffee.id, Coffee.name, origin_subq, Coffee.roast_level)
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
        db.scalar(select(func.count(BrewSession.id)).where(BrewSession.user_id == user_id)) or 0
    )

    # Use raw SQL for unnest — column_valued() lateral join is not supported
    # in this SQLAlchemy 2.0 + ORM context (Assumption A2, RESEARCH.md fallback).
    # JOIN flavor_notes so only LIVE notes count toward the gate, matching
    # get_flavor_descriptors (the card this gate unlocks). flavor_note_ids_observed
    # is a BIGINT[] with no FK, so dangling IDs (note deleted post-session) must
    # not open the gate on a card that would then render empty (WR-01). D-02
    # semantics preserved: still counts across ALL sessions, including unrated.
    note_count_row = db.execute(
        text(
            """
            SELECT count(DISTINCT note_id) AS cnt
            FROM brew_sessions bs, unnest(bs.flavor_note_ids_observed) AS note_id
            JOIN flavor_notes fn ON fn.id = note_id
            WHERE bs.user_id = :user_id
            """
        ),
        {"user_id": user_id},
    ).first()
    note_count: int = (note_count_row.cnt if note_count_row else 0) or 0

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
    recipe_id, brewer_id).

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
        )
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
        ]

    payload = [_serialize_row(r) for r in rows]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
