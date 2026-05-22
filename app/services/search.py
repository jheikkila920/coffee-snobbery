"""Global search service — Phase 10.

Executes six sync per-entity ILIKE queries against the pg_trgm GIN-indexed
columns. Results are dataclass-typed and ready for the Jinja fragment.

Security invariants:
  - T-10-IDOR: brew-note query has ``BrewSession.user_id == user_id`` as
    the FIRST WHERE clause. ``user_id`` is always a typed function arg,
    never a global or request param.
  - T-10-XSS: ``highlight()`` escapes every text fragment with
    ``markupsafe.escape()`` before composing the Markup. No ``|safe`` filter
    is used anywhere in this module.
  - T-10-SQLI: ``pattern = f"%{query}%"`` is passed ONLY via
    ``Column.ilike(pattern)`` (bound parameter). Never interpolated into
    a raw ``text()`` call.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog
from markupsafe import Markup, escape
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.brew_session import BrewSession
from app.models.coffee import Coffee
from app.models.equipment import Equipment
from app.models.flavor_note import FlavorNote
from app.models.recipe import Recipe
from app.models.roaster import Roaster

log = structlog.get_logger(__name__)

# Fetch 6 rows per group; show 5; if 6 returned, the 6th triggers "+N more".
_GROUP_LIMIT = 6


# --------------------------------------------------------------------------- #
# Result dataclasses                                                            #
# --------------------------------------------------------------------------- #


@dataclass
class SearchResult:
    """A single search hit, ready for the results fragment."""

    id: int
    primary: str | Markup        # Highlighted name (Markup) or plain str
    context: str | Markup        # Secondary context line — Markup for brew notes
    link: str                    # Full-page navigation URL (D-11)
    archived: bool = False


@dataclass
class SearchResults:
    """All six entity groups in fixed D-07 order."""

    coffees: list[SearchResult] = field(default_factory=list)
    roasters: list[SearchResult] = field(default_factory=list)
    recipes: list[SearchResult] = field(default_factory=list)
    equipment: list[SearchResult] = field(default_factory=list)
    flavor_notes: list[SearchResult] = field(default_factory=list)
    brew_notes: list[SearchResult] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Highlight helper (T-10-XSS mitigation)                                       #
# --------------------------------------------------------------------------- #


def highlight(text: str, query: str) -> Markup:  # noqa: A002 — intentional shadow
    """Escape text and wrap the first case-insensitive match in <strong>.

    Every text fragment is passed through ``markupsafe.escape()`` before
    composition so Jinja2 never receives raw user content. The returned
    ``Markup`` is trusted by Jinja and will not be double-escaped.

    T-10-XSS: the only raw HTML emitted is the literal ``<strong>`` tag.
    """
    lower_text = text.lower()
    lower_query = query.lower()
    idx = lower_text.find(lower_query)
    if idx == -1:
        return escape(text)
    before = escape(text[:idx])
    matched = escape(text[idx : idx + len(query)])
    after = escape(text[idx + len(query) :])
    return Markup(f"{before}<strong class='font-semibold'>{matched}</strong>{after}")


# --------------------------------------------------------------------------- #
# Brew-note snippet helper                                                      #
# --------------------------------------------------------------------------- #


def _brew_snippet(notes: str, query: str, window: int = 40) -> str:
    """Return a ±window-char window around the first match in notes.

    Adds leading/trailing ellipsis when the window is truncated.
    """
    idx = notes.lower().find(query.lower())
    if idx == -1:
        return notes[:window * 2]
    start = max(0, idx - window)
    end = min(len(notes), idx + len(query) + window)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(notes) else ""
    return f"{prefix}{notes[start:end]}{suffix}"


# --------------------------------------------------------------------------- #
# Main search function                                                          #
# --------------------------------------------------------------------------- #


def run_search(db: Session, query: str, user_id: int) -> SearchResults:
    """Run all six per-entity ILIKE queries and return grouped results.

    Args:
        db:      Sync SQLAlchemy session (FastAPI threadpool path).
        query:   User search string (already stripped; caller enforces >=2 chars).
        user_id: The requesting user's ID. Brew-note query is scoped to this ID.

    Returns:
        ``SearchResults`` with up to 6 rows per group (5 shown + "+N more").
    """
    pattern = f"%{query}%"
    results = SearchResults()

    # ------------------------------------------------------------------ #
    # 1. Coffees — include archived (D-12); JOIN Roaster for context      #
    # ------------------------------------------------------------------ #
    coffee_stmt = (
        select(
            Coffee.id,
            Coffee.name,
            Coffee.origin,
            Coffee.archived,
            Roaster.name.label("roaster_name"),
        )
        .outerjoin(Roaster, Coffee.roaster_id == Roaster.id)
        .where(Coffee.name.ilike(pattern))
        .order_by(Coffee.id.desc())
        .limit(_GROUP_LIMIT)
    )
    for row in db.execute(coffee_stmt).all():
        context_parts = [p for p in [row.roaster_name, row.origin] if p]
        context = " · ".join(context_parts)
        results.coffees.append(
            SearchResult(
                id=row.id,
                primary=highlight(row.name, query),
                context=context,
                link=f"/coffees/{row.id}",
                archived=bool(row.archived),
            )
        )

    # ------------------------------------------------------------------ #
    # 2. Roasters — exclude archived (D-14)                               #
    # ------------------------------------------------------------------ #
    roaster_stmt = (
        select(Roaster.id, Roaster.name)
        .where(
            Roaster.name.ilike(pattern),
            Roaster.archived == False,  # noqa: E712
        )
        .order_by(Roaster.id.desc())
        .limit(_GROUP_LIMIT)
    )
    for row in db.execute(roaster_stmt).all():
        results.roasters.append(
            SearchResult(
                id=row.id,
                primary=highlight(row.name, query),
                context="",
                link=f"/roasters/{row.id}/edit",
                archived=False,
            )
        )

    # ------------------------------------------------------------------ #
    # 3. Recipes — name-only (D-13); exclude archived (D-14)              #
    # ------------------------------------------------------------------ #
    recipe_stmt = (
        select(Recipe.id, Recipe.name, Recipe.grind_setting)
        .where(
            Recipe.name.ilike(pattern),
            Recipe.archived == False,  # noqa: E712
        )
        .order_by(Recipe.id.desc())
        .limit(_GROUP_LIMIT)
    )
    for row in db.execute(recipe_stmt).all():
        results.recipes.append(
            SearchResult(
                id=row.id,
                primary=highlight(row.name, query),
                context=row.grind_setting or "",
                link=f"/recipes/{row.id}/edit",
                archived=False,
            )
        )

    # ------------------------------------------------------------------ #
    # 4. Equipment — brand||model per-token match (D-14; no name column) #
    #    Include archived (D-12).                                         #
    #    Split query into tokens so "Hario V60" matches equipment with    #
    #    brand="Hario abc" model="V60-02" (each token checked against     #
    #    both brand and model via OR; all tokens must match via AND).     #
    # ------------------------------------------------------------------ #
    equip_concat = func.concat(Equipment.brand, " ", Equipment.model)
    equip_tokens = query.split()
    equip_token_conds = [
        or_(Equipment.brand.ilike(f"%{t}%"), Equipment.model.ilike(f"%{t}%"))
        for t in equip_tokens
    ] if equip_tokens else [equip_concat.ilike(pattern)]
    equip_stmt = (
        select(
            Equipment.id,
            Equipment.brand,
            Equipment.model,
            Equipment.type,
            Equipment.archived,
        )
        .where(and_(*equip_token_conds))
        .order_by(Equipment.id.desc())
        .limit(_GROUP_LIMIT)
    )
    for row in db.execute(equip_stmt).all():
        display_name = f"{row.brand} {row.model}"
        results.equipment.append(
            SearchResult(
                id=row.id,
                primary=highlight(display_name, query),
                context=row.type or "",
                link=f"/equipment/{row.id}/edit",
                archived=bool(row.archived),
            )
        )

    # ------------------------------------------------------------------ #
    # 5. Flavor notes — exclude archived (D-14)                          #
    # ------------------------------------------------------------------ #
    fn_stmt = (
        select(FlavorNote.id, FlavorNote.name, FlavorNote.category)
        .where(
            FlavorNote.name.ilike(pattern),
            FlavorNote.archived == False,  # noqa: E712
        )
        .order_by(FlavorNote.id.desc())
        .limit(_GROUP_LIMIT)
    )
    for row in db.execute(fn_stmt).all():
        results.flavor_notes.append(
            SearchResult(
                id=row.id,
                primary=highlight(row.name, query),
                context=row.category or "",
                link=f"/flavor-notes/{row.id}/edit",
                archived=False,
            )
        )

    # ------------------------------------------------------------------ #
    # 6. Brew notes — T-10-IDOR: user_id FIRST; then notes ILIKE         #
    # ------------------------------------------------------------------ #
    brew_stmt = (
        select(
            BrewSession.id,
            BrewSession.notes,
            BrewSession.brewed_at,
            Coffee.name.label("coffee_name"),
        )
        .join(Coffee, BrewSession.coffee_id == Coffee.id)
        .where(
            BrewSession.user_id == user_id,  # ALWAYS first — T-10-IDOR
            BrewSession.notes.ilike(pattern),
            BrewSession.notes != "",
        )
        .order_by(BrewSession.brewed_at.desc())
        .limit(_GROUP_LIMIT)
    )
    for row in db.execute(brew_stmt).all():
        snippet = _brew_snippet(row.notes, query)
        snippet_markup = highlight(snippet, query)
        date_str = row.brewed_at.strftime("%Y-%m-%d") if row.brewed_at else ""
        if date_str:
            context: str | Markup = Markup(f"{escape(date_str)} · {snippet_markup}")
        else:
            context = snippet_markup
        results.brew_notes.append(
            SearchResult(
                id=row.id,
                primary=Markup(escape(row.coffee_name)),
                context=context,
                link=f"/brew/{row.id}/edit",
                archived=False,
            )
        )

    return results
