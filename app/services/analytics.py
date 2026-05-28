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
from app.models.cafe_log import CafeLog
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


def get_top_coffees(db: Session, user_id: int, *, min_sessions: int = 2) -> list[Row]:
    """Return <=5 coffees ranked by the user's avg rating.

    Excludes NULL ratings (Pitfall 1). Tie-broken avg_rating DESC, then
    session_count DESC (Claude's Discretion).

    :param min_sessions: minimum rated-session count per coffee (default 2,
        preserving the historical floor used by the /home/cards/top-coffees
        fragment endpoint). Phase 17 IA-06 / D-09 introduced this parameter:
        the home shell's eager Top Coffees render calls with ``min_sessions=0``
        so single-session coffees surface. When ``min_sessions <= 0`` the
        HAVING clause is omitted entirely.
    """
    # CAFE-04 not applicable: cafe coffees have no row in coffees table by design (D-14).
    # Do not UNION cafe data into this query — a future "Top cafe tastings" widget
    # belongs in Phase 17 (IA restructure) or Phase 19 (AI page), not here.
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
    )
    if min_sessions > 0:
        stmt = stmt.having(func.count(BrewSession.id) >= min_sessions)
    stmt = stmt.order_by(
        func.avg(BrewSession.rating).desc(), func.count(BrewSession.id).desc()
    ).limit(5)
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

    CAFE-04 / D-13 — cafe contribution by dimension:
    - origin: YES. UNION cafe_logs.origin_country (per-user, rated, non-null)
      with coffee_origins.country (per-user via brew_sessions JOIN). The min >=2
      HAVING clause applies ACROSS the union — 1 brew + 1 cafe from the same
      country together satisfy the floor.
    - roaster: YES. UNION cafe roaster (via CafeLog.roaster_id JOIN to Roaster)
      with brew roaster (via Coffee.roaster_id JOIN). Same HAVING floor.
    - process: NO. Cafe form does not capture process (user doesn't reliably know
      "washed/natural/honey" at a cafe). Stays brew-only via _dim_query.
    - roast_level: NO. Same reasoning. Stays brew-only via _dim_query.

    T-16-05-02 IDOR defense: every new cafe-side SELECT carries
    CafeLog.user_id == user_id.
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

    # Roaster dimension: UNION brew roaster JOIN + cafe roaster JOIN (D-13).
    brew_roaster = (
        select(
            Roaster.name.label("name"),
            BrewSession.rating.label("rating"),
        )
        .join(Coffee, BrewSession.coffee_id == Coffee.id)
        .join(Roaster, Coffee.roaster_id == Roaster.id)
        .where(
            BrewSession.user_id == user_id,
            BrewSession.rating.is_not(None),
        )
    )
    cafe_roaster = (
        select(
            Roaster.name.label("name"),
            CafeLog.rating.label("rating"),
        )
        .join(Roaster, CafeLog.roaster_id == Roaster.id)
        .where(
            CafeLog.user_id == user_id,
            CafeLog.rating.is_not(None),
        )
    )
    roaster_union = brew_roaster.union_all(cafe_roaster).subquery()
    roaster_stmt = (
        select(
            roaster_union.c.name.label("label"),
            func.avg(roaster_union.c.rating).label("avg_rating"),
            func.count().label("session_count"),
        )
        .group_by(roaster_union.c.name)
        .having(func.count() >= 2)
        .order_by(func.avg(roaster_union.c.rating).desc(), func.count().desc())
    )

    # Origin dimension: UNION brew origin (coffee_origins JOIN) + cafe origin_country (D-13).
    # A blend with N origins contributes N rows per session — intentional (see original comment).
    brew_origin = (
        select(
            CoffeeOrigin.country.label("country"),
            BrewSession.rating.label("rating"),
        )
        .join(Coffee, BrewSession.coffee_id == Coffee.id)
        .join(CoffeeOrigin, CoffeeOrigin.coffee_id == Coffee.id)
        .where(
            BrewSession.user_id == user_id,
            BrewSession.rating.is_not(None),
        )
    )
    cafe_origin = select(
        CafeLog.origin_country.label("country"),
        CafeLog.rating.label("rating"),
    ).where(
        CafeLog.user_id == user_id,
        CafeLog.rating.is_not(None),
        CafeLog.origin_country.is_not(None),
    )
    origin_union = brew_origin.union_all(cafe_origin).subquery()
    origin_stmt = (
        select(
            origin_union.c.country.label("label"),
            func.avg(origin_union.c.rating).label("avg_rating"),
            func.count().label("session_count"),
        )
        .group_by(origin_union.c.country)
        .having(func.count() >= 2)
        .order_by(func.avg(origin_union.c.rating).desc(), func.count().desc())
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
    """Top-10 flavor descriptors from the user's 4.0+ rated brew + cafe sessions, min 2.

    CAFE-04 / D-13: UNIONs rated-4+ brew_sessions.flavor_note_ids_observed with
    rated-4+ cafe_logs.flavor_note_ids. A flavor note appearing in both a 4.0+ brew
    row AND a 4.0+ cafe row counts TWICE (once per source) — this weights notes that
    recur across taste contexts, which is the desired behavior.

    Unnest pattern: raw SQL with a UNION ALL of two unnest blocks inside a derived-table
    subquery. func.unnest().column_valued() cannot be used in this ORM context (Assumption
    A2 from RESEARCH.md). The bound :user_id parameter prevents SQL injection (T-06-03)
    and is referenced twice (once per UNION side); psycopg 3 supports a single-key dict
    referenced multiple times in the same statement.

    JOIN to flavor_notes filters dangling IDs so only LIVE notes count (matching the
    cold-start gate's live-note-only semantics — no ghost notes open the descriptors card).

    T-16-05-01 / T-16-05-02: no string interpolation; :user_id bound param only.
    """
    stmt = text(
        """
        SELECT fn.id, fn.name, count(*) AS session_count
        FROM (
            SELECT note_id
            FROM brew_sessions bs, unnest(bs.flavor_note_ids_observed) AS note_id
            WHERE bs.user_id = :user_id
              AND bs.rating IS NOT NULL
              AND bs.rating >= 4.0
            UNION ALL
            SELECT note_id
            FROM cafe_logs cl, unnest(cl.flavor_note_ids) AS note_id
            WHERE cl.user_id = :user_id
              AND cl.rating IS NOT NULL
              AND cl.rating >= 4.0
        ) AS notes
        JOIN flavor_notes fn ON fn.id = notes.note_id
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
    # NOTE (CAFE-05 / D-16): Cafe logs are intentionally excluded — they have no
    # brew-parameter fields (no recipe_id, brewer_id, dose, yield, water_temp_c,
    # or grind setting). Do not UNION cafe data into this query.
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
    """Return live counts for the cold-start gate (D-02 / D-15 / CAFE-04).

    CAFE-04 / D-15: counts brew + cafe sessions together.
    gate_open = (brew_count + cafe_count) >= 3 AND distinct_notes_across_both >= 5.

    UI-SPEC § Cold-Start Carve-Out: the template copy ("brews", "flavor notes")
    stays unchanged — only the arithmetic inputs change (Assumption A2 accepted;
    Phase 17 owns home-copy polish). The dict keys sessions / distinct_notes /
    gate_open / sessions_needed / notes_needed are preserved verbatim so
    _cold_start.html requires NO template change.

    Counts ALL sessions including unrated (not the signature, which is D-09 rated-only).
    cafe_count counts ALL rated + unrated cafe_logs rows, mirroring brew_count semantics.

    Distinct-notes query: UNION ALL of two unnest blocks (brew + cafe). JOIN to
    flavor_notes ensures only LIVE notes count (dangling IDs from deleted notes are
    filtered, matching the behavior of get_flavor_descriptors — the card this gate
    unlocks). No rating >= 4.0 filter on either side — cold-start counts ALL sessions
    including unrated (D-02 semantics preserved).

    T-16-05-01 / T-16-05-02: :user_id bound param on both UNION branches; no string
    interpolation.
    """
    brew_count: int = (
        db.scalar(select(func.count(BrewSession.id)).where(BrewSession.user_id == user_id)) or 0
    )
    cafe_count: int = (
        db.scalar(select(func.count(CafeLog.id)).where(CafeLog.user_id == user_id)) or 0
    )
    total: int = brew_count + cafe_count

    # Use raw SQL for unnest — column_valued() lateral join is not supported
    # in this SQLAlchemy 2.0 + ORM context (Assumption A2, RESEARCH.md fallback).
    # UNION ALL of brew + cafe unnest blocks; outer JOIN to flavor_notes for live-only.
    note_count_row = db.execute(
        text(
            """
            SELECT count(DISTINCT all_notes.note_id) AS cnt
            FROM (
                SELECT note_id
                FROM brew_sessions bs, unnest(bs.flavor_note_ids_observed) AS note_id
                WHERE bs.user_id = :user_id
                UNION ALL
                SELECT note_id
                FROM cafe_logs cl, unnest(cl.flavor_note_ids) AS note_id
                WHERE cl.user_id = :user_id
            ) AS all_notes
            JOIN flavor_notes fn ON fn.id = all_notes.note_id
            """
        ),
        {"user_id": user_id},
    ).first()
    note_count: int = (note_count_row.cnt if note_count_row else 0) or 0

    return {
        "sessions": total,
        "distinct_notes": note_count,
        "gate_open": total >= 3 and note_count >= 5,
        "sessions_needed": max(0, 3 - total),
        "notes_needed": max(0, 5 - note_count),
    }


# --------------------------------------------------------------------------- #
# Signature computation (Phase 7 stale-data plumbing)                         #
# --------------------------------------------------------------------------- #


def compute_input_signature(db: Session, user_id: int) -> str:
    """SHA256 hex over this user's RATED brew + cafe rows' AI-input fields (D-08/D-09/D-12, COST-4).

    Payload shape: ``[brew_list, cafe_list]`` — a list of TWO lists, NOT a flat
    concatenation. This is critical for two reasons:
    1. Pitfall 3 (namespace defense): a brew row with ``coffee_id=N`` and a cafe row
       with ``id=N`` cannot produce identical 5-tuples because they sit in different
       outer-list positions. Row-identity collision is impossible.
    2. Pitfall 9 (one-time AI regen): the shape change from the old flat ``[...brews]``
       payload to ``[[...brews], [...cafes]]`` triggers a one-time signature churn for
       every existing user on the first nightly run post-deploy. This is the accepted
       disposition (Option (a) per RESEARCH.md § Pitfall 9) — ~6 users × 1 extra AI
       call, cost <$0.10. Documented in SUMMARY.

    Brew row shape: ``[coffee_id, float(rating), sorted flavor_note_ids_observed,
    recipe_id, brewer_id]``.
    Cafe row shape: ``[cafe_log_id, float(rating), sorted flavor_note_ids,
    roaster_id, origin_country]``.

    Both row lists ordered by their own primary key ASC for determinism (Pitfall 5).
    Returns ``_EMPTY_SIGNATURE`` only when BOTH brew_rows AND cafe_rows are empty.

    COST-4: scope is strictly this user's OWN rows (WHERE user_id == user_id on both
    sides); never shared catalog counts.

    T-16-05-02 IDOR defense: CafeLog.user_id == user_id scopes the cafe SELECT to
    the requesting user. user_id is a typed function arg, never a global or request param.
    """
    brew_stmt = (
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
    brew_rows = db.execute(brew_stmt).all()

    # NEW (D-12 / CAFE-04): cafe rows as second payload sublist.
    cafe_stmt = (
        select(
            CafeLog.id,
            CafeLog.rating,
            CafeLog.flavor_note_ids,
            CafeLog.roaster_id,
            CafeLog.origin_country,
        )
        .where(
            CafeLog.user_id == user_id,
            CafeLog.rating.is_not(None),  # unrated cafe logs excluded (Pitfall 3)
        )
        .order_by(CafeLog.id)  # deterministic (Pitfall 5 applied to cafe sublist)
    )
    cafe_rows = db.execute(cafe_stmt).all()

    # Empty sentinel only when BOTH lists are empty (Pitfall 3 + Pitfall 9 defense).
    if not brew_rows and not cafe_rows:
        return _EMPTY_SIGNATURE

    def _serialize_brew(row: Row) -> list:  # type: ignore[type-arg]
        return [
            row.coffee_id,
            float(row.rating),  # Decimal → float for JSON
            sorted(row.flavor_note_ids_observed or []),
            row.recipe_id,
            row.brewer_id,
        ]

    def _serialize_cafe(row: Row) -> list:  # type: ignore[type-arg]
        return [
            row.id,  # cafe_log_id — different namespace from coffee_id (Pitfall 3)
            float(row.rating),
            sorted(row.flavor_note_ids or []),
            row.roaster_id,
            row.origin_country,  # str | None — json.dumps serializes None as null
        ]

    # Two-element top-level list: position 0 = brew, position 1 = cafe.
    payload = [
        [_serialize_brew(r) for r in brew_rows],
        [_serialize_cafe(r) for r in cafe_rows],
    ]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
