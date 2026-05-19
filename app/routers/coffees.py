"""Coffees CRUD router — HTMX inline-expand fragments + filter bar with hx-push-url.

Mirrors :mod:`app.routers.roasters` (plan 04-04) — the universal Phase 4
catalog template. Differences specific to CAT-03 + CAT-07:

* The list page renders a desktop table at ``md:`` and collapses to a
  card list at ``<md`` (CAT-07 / UI-SPEC §"List-vs-Card Layout").
* The list page ships a four-dimension filter bar (``roaster_id``,
  ``country``, ``process``, ``archived``) that fires
  ``hx-get="/coffees"`` with ``hx-push-url="true"`` (D-03) so the
  browser URL reflects the active filters and back/forward replays
  them.
* The form embeds two autocomplete fields:
  - roaster (``/roasters/list`` from plan 04-04)
  - flavor-note chip-builder (``/flavor-notes/datalist`` from plan
    04-05; the chip-add/remove behavior is wired in plan 04-11)
* ``GET /coffees/{id}`` is a dedicated detail page rendering the coffee
  + its bags + an "Open new bag" affordance (plan 04-09 wires the bag
  form/CRUD).
* The ``advertised_flavor_note_ids`` form field is a list of ints:
  hidden inputs named ``advertised_flavor_note_ids`` are emitted by
  the chip-builder (one per selected id). FastAPI's ``await
  request.form()`` returns repeated keys via ``form_data.getlist()``;
  the router casts every entry to ``int`` before handing to the
  Pydantic schema.

Endpoints
---------

* ``GET /coffees`` — list page (full page or HTMX fragment), four filter
  query params: ``roaster_id``, ``country``, ``process``, ``archived``.
* ``GET /coffees/new`` — empty form fragment.
* ``GET /coffees/empty-form`` — empty fragment for Cancel buttons.
* ``POST /coffees`` — create. Validation errors → 200 + form-fragment
  re-render with errors.
* ``GET /coffees/{id}`` — coffee detail page (renders bags + "Open new
  bag" affordance).
* ``GET /coffees/{id}/edit`` — form fragment pre-populated with row.
* ``POST /coffees/{id}`` — update. Same validation re-render pattern.
* ``POST /coffees/{id}/archive`` — soft-delete; returns updated row.
* ``GET /coffees/filters-panel`` — HTMX-fetched filter dropdown panel
  (roaster list + distinct countries + 6 process values). Used when a
  new roaster or country surfaces without a full page reload.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.dependencies.auth import require_user
from app.dependencies.db import get_session
from app.models.user import User
from app.schemas.coffee import CoffeeCreate
from app.services import coffees as coffees_service
from app.services import flavor_notes as flavor_notes_service
from app.services import roasters as roasters_service
from app.services.coffees import COFFEE_PROCESSES, COFFEE_ROAST_LEVELS
from app.services.form_validation import errors_by_field
from app.templates_setup import templates

router = APIRouter(prefix="/coffees")

# Field keys the inline form template renders error paragraphs for. Any
# ValidationError landing on a key outside this set (e.g., the extra-field
# rejection on ``is_admin`` from a T-04-MASS probe) is folded into the
# ``_form`` sentinel so the user still sees the error rendered.
_FORM_FIELDS = {
    "name",
    "roaster_id",
    "country",
    "origin",
    "process",
    "roast_level",
    "varietal",
    "notes",
    "advertised_flavor_note_ids",
}

# Form keys where an empty string from the browser is semantically "no
# value" and must become ``None`` before Pydantic validation. ``name``
# is required (blank → desired error), ``notes`` legitimately accepts
# ``""``, and ``advertised_flavor_note_ids`` is handled separately as a
# repeated list.
_EMPTY_TO_NONE_FIELDS = {
    "roaster_id",
    "country",
    "origin",
    "process",
    "roast_level",
    "varietal",
}

# Form keys that the chip-builder + autocomplete inputs add on top of
# the canonical schema fields. The router strips these before handing
# to the schema; they are NOT in CoffeeCreate, and leaving them in
# would trip ``extra='forbid'`` and re-render the form with a false
# error.
_NON_SCHEMA_FORM_KEYS = {
    "X-CSRF-Token",
    "roaster_query",  # autocomplete text input next to roaster_id
    "flavor_note_query",  # autocomplete text input for chip-builder
}


def _normalize_errors(errors: dict[str, str]) -> dict[str, str]:
    """Fold any error keys outside the rendered form fields into ``_form``."""
    normalized: dict[str, str] = {}
    leftovers: list[str] = []
    for key, msg in errors.items():
        if key in _FORM_FIELDS or key == "_form":
            normalized[key] = msg
        else:
            leftovers.append(f"{key}: {msg}")
    if leftovers:
        existing = normalized.get("_form")
        combined = (
            "; ".join(leftovers)
            if existing is None
            else f"{existing}; {'; '.join(leftovers)}"
        )
        normalized["_form"] = combined
    return normalized


def _parse_form_payload(form_data: object) -> tuple[dict[str, object], dict[str, object]]:
    """Convert raw form data → ``(raw_view, schema_input)``.

    ``raw_view`` is the dict handed back to the form template on
    validation failure so the user's submitted text is preserved on
    re-render. It carries strings for every scalar field and the
    raw list for ``advertised_flavor_note_ids``.

    ``schema_input`` is the dict handed to :class:`CoffeeCreate`. Empty
    optional strings are coerced to ``None``; ``advertised_flavor_note_ids``
    is collected via ``getlist`` and cast to ``list[int]``. Non-int chip
    values raise ``ValueError`` which the caller re-shapes into a
    field-level error.
    """
    # ``form_data`` is starlette.datastructures.FormData; .getlist is
    # the canonical way to read repeated keys.
    raw_view: dict[str, object] = {}
    schema_input: dict[str, object] = {}

    # Collect every key/value pair, treating repeated keys via getlist.
    seen_keys: set[str] = set()
    for key, _ in form_data.multi_items():  # type: ignore[attr-defined]
        if key in seen_keys:
            continue
        seen_keys.add(key)
        if key in _NON_SCHEMA_FORM_KEYS:
            continue
        if key == "advertised_flavor_note_ids":
            values = form_data.getlist(key)  # type: ignore[attr-defined]
            # Strip empty strings (a chip-builder render may include an
            # empty hidden input for the typed-but-not-confirmed value).
            id_strs = [v for v in values if isinstance(v, str) and v != ""]
            raw_view[key] = id_strs
            try:
                schema_input[key] = [int(v) for v in id_strs]
            except (TypeError, ValueError):
                # Sentinel triggers a ValidationError in the schema's
                # field_validator (ge=1) path; surfaces as the
                # "advertised_flavor_note_ids must be positive integers"
                # message.
                schema_input[key] = [0]
        else:
            value = form_data.get(key)  # type: ignore[attr-defined]
            raw_view[key] = value
            if isinstance(value, str) and value == "" and key in _EMPTY_TO_NONE_FIELDS:
                schema_input[key] = None
            elif key == "roaster_id" and isinstance(value, str) and value:
                try:
                    schema_input[key] = int(value)
                except ValueError:
                    # Bad int → let Pydantic complain on the int coercion.
                    schema_input[key] = value
            else:
                schema_input[key] = value

    return raw_view, schema_input


def _hydrate_form_context(
    db: Session,
    *,
    values: dict[str, object],
    errors: dict[str, str],
    mode: str,
    coffee_id: int | None = None,
) -> dict[str, object]:
    """Build the form-template context with the lookup lists hydrated.

    Resolves the selected roaster's name (so the autocomplete text input
    is seeded on edit/re-render) and the names for any selected flavor
    notes (so seeded chips render before Alpine boots — plan 04-11).
    """
    roaster_id_raw = values.get("roaster_id")
    roaster_name = ""
    if roaster_id_raw:
        try:
            rid = int(roaster_id_raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            rid = None
        if rid is not None:
            roaster = roasters_service.get_roaster(db, roaster_id=rid)
            if roaster is not None:
                roaster_name = roaster.name

    fn_ids_raw = values.get("advertised_flavor_note_ids") or []
    fn_ids: list[int] = []
    if isinstance(fn_ids_raw, list):
        for v in fn_ids_raw:
            try:
                fn_ids.append(int(v))
            except (TypeError, ValueError):
                continue
    selected_flavor_notes = (
        [
            {"id": fid, "name": name}
            for fid, name in coffees_service.flavor_note_name_map(db, ids=fn_ids).items()
        ]
        if fn_ids
        else []
    )

    return {
        "values": values,
        "errors": errors,
        "mode": mode,
        "coffee_id": coffee_id,
        "processes": COFFEE_PROCESSES,
        "roast_levels": COFFEE_ROAST_LEVELS,
        "roaster_name": roaster_name,
        "selected_flavor_notes": selected_flavor_notes,
    }


# --------------------------------------------------------------------------- #
# List page + HTMX fragment + filter bar                                      #
# --------------------------------------------------------------------------- #


@router.get("", response_class=HTMLResponse)
def list_coffees(
    request: Request,
    roaster_id: int | None = None,
    country: str | None = None,
    process: str | None = None,
    archived: bool = False,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """List page or fragment, filtered by query params (D-03 + CAT-07)."""
    rows = coffees_service.list_coffees(
        db,
        roaster_id=roaster_id,
        country=country if country else None,
        process=process if process else None,
        archived=archived,
    )
    # Build the {id: name} map for advertised-flavor-note pills across
    # all rows in one query (avoids N+1 in the template).
    all_ids: list[int] = []
    for c in rows:
        all_ids.extend(c.advertised_flavor_note_ids or [])
    flavor_note_names = coffees_service.flavor_note_name_map(db, ids=all_ids)

    # Resolve roaster names in one query for the pill / row.
    roaster_ids = [c.roaster_id for c in rows if c.roaster_id is not None]
    roaster_name_map: dict[int, str] = {}
    if roaster_ids:
        for roaster in roasters_service.list_roasters(db, include_archived=True):
            if roaster.id in roaster_ids:
                roaster_name_map[roaster.id] = roaster.name

    filters = {
        "roaster_id": roaster_id,
        "country": country,
        "process": process,
        "archived": archived,
    }

    list_context = {
        "coffees": rows,
        "filters": filters,
        "flavor_note_names": flavor_note_names,
        "roaster_name_map": roaster_name_map,
    }

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request,
            name="fragments/coffee_list.html",
            context=list_context,
        )

    # Full-page render also needs the filter-bar dropdown source data.
    roasters = roasters_service.list_roasters(db, include_archived=False)
    countries = coffees_service.list_distinct_countries(db)
    return templates.TemplateResponse(
        request=request,
        name="pages/coffees.html",
        context={
            **list_context,
            "roasters": roasters,
            "countries": countries,
            "processes": COFFEE_PROCESSES,
        },
    )


# --------------------------------------------------------------------------- #
# Create — form GET + POST                                                    #
# --------------------------------------------------------------------------- #


@router.get("/new", response_class=HTMLResponse)
def new_coffee_form(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Empty form fragment for the inline-expand create flow."""
    context = _hydrate_form_context(
        db,
        values={"advertised_flavor_note_ids": []},
        errors={},
        mode="create",
    )
    return templates.TemplateResponse(
        request=request,
        name="fragments/coffee_form.html",
        context=context,
    )


@router.get("/empty-form", response_class=HTMLResponse)
def empty_form(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
) -> Response:
    """Empty fragment served to the Cancel button (CSP-safe round-trip)."""
    return templates.TemplateResponse(
        request=request,
        name="fragments/empty.html",
        context={},
    )


@router.post("", response_class=HTMLResponse)
async def create_coffee(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Create a coffee. Validation errors → 200 + form re-render.

    Uses ``await request.form()`` + ``getlist`` so repeated
    ``advertised_flavor_note_ids`` keys are collected as a list before
    the Pydantic schema sees them — per plan 04-04's raw-form-read
    pattern (T-04-MASS defense exercised at the router boundary).
    """
    form_data = await request.form()
    raw_view, schema_input = _parse_form_payload(form_data)
    try:
        form = CoffeeCreate(**schema_input)
    except ValidationError as exc:
        context = _hydrate_form_context(
            db,
            values=raw_view,
            errors=_normalize_errors(errors_by_field(exc)),
            mode="create",
        )
        return templates.TemplateResponse(
            request=request,
            name="fragments/coffee_form.html",
            context=context,
            status_code=200,
        )

    coffee = coffees_service.create_coffee(
        db,
        name=form.name,
        roaster_id=form.roaster_id,
        country=form.country,
        origin=form.origin,
        process=form.process,
        roast_level=form.roast_level,
        varietal=form.varietal,
        notes=form.notes,
        advertised_flavor_note_ids=form.advertised_flavor_note_ids,
        by_user_id=user.id,
    )

    # Row response needs the lookup dicts the list endpoint also builds.
    flavor_note_names = coffees_service.flavor_note_name_map(
        db, ids=coffee.advertised_flavor_note_ids or []
    )
    roaster_name_map: dict[int, str] = {}
    if coffee.roaster_id is not None:
        roaster = roasters_service.get_roaster(db, roaster_id=coffee.roaster_id)
        if roaster is not None:
            roaster_name_map[coffee.roaster_id] = roaster.name
    return templates.TemplateResponse(
        request=request,
        name="fragments/coffee_row.html",
        context={
            "coffee": coffee,
            "mode": "row",
            "flavor_note_names": flavor_note_names,
            "roaster_name_map": roaster_name_map,
            "include_oob_form_clear": True,
        },
    )


# --------------------------------------------------------------------------- #
# Filters-panel refresh (declared BEFORE /{coffee_id} so the literal path     #
# doesn't get captured by the int param matcher — Starlette resolves routes  #
# in declaration order).                                                     #
# --------------------------------------------------------------------------- #


@router.get("/filters-panel", response_class=HTMLResponse)
def filters_panel(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """HTMX-fetched filter dropdown panel (roaster list + distinct countries).

    Useful when a new roaster is created via the mini-modal and the
    filter dropdowns need refreshing without a full page reload.
    Returns the inline filter form markup (same shape as the page).
    Recommended in 04-RESEARCH Open Question 2.
    """
    roasters = roasters_service.list_roasters(db, include_archived=False)
    countries = coffees_service.list_distinct_countries(db)
    return templates.TemplateResponse(
        request=request,
        name="fragments/coffee_filters_panel.html",
        context={
            "roasters": roasters,
            "countries": countries,
            "processes": COFFEE_PROCESSES,
            "filters": {
                "roaster_id": None,
                "country": None,
                "process": None,
                "archived": False,
            },
        },
    )


# --------------------------------------------------------------------------- #
# Detail page                                                                 #
# --------------------------------------------------------------------------- #


@router.get("/{coffee_id}", response_class=HTMLResponse)
def coffee_detail(
    coffee_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Render the coffee detail page + its bags + 'Open new bag' affordance.

    Plan 04-09 wires the bag form + CRUD against the ``#bag-form-mount``
    div + the ``/coffees/{id}/bags/new`` endpoint. Until then the button
    + mount div + a placeholder ship here so the contract is concrete.
    """
    result = coffees_service.get_coffee_with_bags(db, coffee_id=coffee_id)
    if result is None:
        raise HTTPException(status_code=404)
    coffee, bags = result

    roaster = None
    if coffee.roaster_id is not None:
        roaster = roasters_service.get_roaster(db, roaster_id=coffee.roaster_id)

    flavor_note_names = coffees_service.flavor_note_name_map(
        db, ids=coffee.advertised_flavor_note_ids or []
    )

    return templates.TemplateResponse(
        request=request,
        name="pages/coffee_detail.html",
        context={
            "coffee": coffee,
            "bags": bags,
            "roaster": roaster,
            "flavor_note_names": flavor_note_names,
        },
    )


# --------------------------------------------------------------------------- #
# Edit / Update / Archive                                                     #
# --------------------------------------------------------------------------- #


@router.get("/{coffee_id}/edit", response_class=HTMLResponse)
def edit_coffee_form(
    coffee_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Pre-populated form fragment for inline edit (swaps the row)."""
    coffee = coffees_service.get_coffee(db, coffee_id=coffee_id)
    if coffee is None:
        raise HTTPException(status_code=404)
    values: dict[str, object] = {
        "name": coffee.name,
        "roaster_id": str(coffee.roaster_id) if coffee.roaster_id is not None else "",
        "country": coffee.country or "",
        "origin": coffee.origin or "",
        "process": coffee.process or "",
        "roast_level": coffee.roast_level or "",
        "varietal": coffee.varietal or "",
        "notes": coffee.notes or "",
        "advertised_flavor_note_ids": [
            str(i) for i in (coffee.advertised_flavor_note_ids or [])
        ],
    }
    context = _hydrate_form_context(
        db,
        values=values,
        errors={},
        mode="edit",
        coffee_id=coffee_id,
    )
    return templates.TemplateResponse(
        request=request,
        name="fragments/coffee_form.html",
        context=context,
    )


@router.post("/{coffee_id}", response_class=HTMLResponse)
async def update_coffee_handler(
    coffee_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Update a coffee. Validation errors → 200 + form re-render."""
    existing = coffees_service.get_coffee(db, coffee_id=coffee_id)
    if existing is None:
        raise HTTPException(status_code=404)

    form_data = await request.form()
    raw_view, schema_input = _parse_form_payload(form_data)
    try:
        form = CoffeeCreate(**schema_input)
    except ValidationError as exc:
        context = _hydrate_form_context(
            db,
            values=raw_view,
            errors=_normalize_errors(errors_by_field(exc)),
            mode="edit",
            coffee_id=coffee_id,
        )
        return templates.TemplateResponse(
            request=request,
            name="fragments/coffee_form.html",
            context=context,
            status_code=200,
        )

    coffee = coffees_service.update_coffee(
        db,
        coffee_id=coffee_id,
        name=form.name,
        roaster_id=form.roaster_id,
        country=form.country,
        origin=form.origin,
        process=form.process,
        roast_level=form.roast_level,
        varietal=form.varietal,
        notes=form.notes,
        advertised_flavor_note_ids=form.advertised_flavor_note_ids,
        by_user_id=user.id,
    )

    flavor_note_names = coffees_service.flavor_note_name_map(
        db, ids=coffee.advertised_flavor_note_ids or []
    )
    roaster_name_map: dict[int, str] = {}
    if coffee.roaster_id is not None:
        roaster = roasters_service.get_roaster(db, roaster_id=coffee.roaster_id)
        if roaster is not None:
            roaster_name_map[coffee.roaster_id] = roaster.name
    return templates.TemplateResponse(
        request=request,
        name="fragments/coffee_row.html",
        context={
            "coffee": coffee,
            "mode": "row",
            "flavor_note_names": flavor_note_names,
            "roaster_name_map": roaster_name_map,
        },
    )


@router.post("/{coffee_id}/archive", response_class=HTMLResponse)
def archive_coffee_handler(
    coffee_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Soft-delete a coffee; re-render the row with archived styling."""
    existing = coffees_service.get_coffee(db, coffee_id=coffee_id)
    if existing is None:
        raise HTTPException(status_code=404)
    coffees_service.archive_coffee(db, coffee_id=coffee_id, by_user_id=user.id)
    coffee = coffees_service.get_coffee(db, coffee_id=coffee_id)

    flavor_note_names = coffees_service.flavor_note_name_map(
        db, ids=coffee.advertised_flavor_note_ids or []
    ) if coffee else {}
    roaster_name_map: dict[int, str] = {}
    if coffee and coffee.roaster_id is not None:
        roaster = roasters_service.get_roaster(db, roaster_id=coffee.roaster_id)
        if roaster is not None:
            roaster_name_map[coffee.roaster_id] = roaster.name
    return templates.TemplateResponse(
        request=request,
        name="fragments/coffee_row.html",
        context={
            "coffee": coffee,
            "mode": "row",
            "flavor_note_names": flavor_note_names,
            "roaster_name_map": roaster_name_map,
        },
    )


__all__ = ["router"]
