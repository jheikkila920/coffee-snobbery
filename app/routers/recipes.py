"""Recipes CRUD router — HTMX inline-expand + Alpine step-builder + D-12 duplicate.

Implements the universal Phase 4 catalog template (D-01..D-04 inline-expand
pattern, SEC-06 form-validation re-render at HTTP 200) plus three Phase 4
firsts:

* **First live Alpine CSP-build component on the wire** — the form
  fragment mounts ``x-data="recipeStepBuilder"`` which is registered in
  ``app/static/js/alpine-components/recipe-step-builder.js`` (Phase 1
  D-01 / docs/decisions/0001).
* **JSON-as-hidden-input form payload (D-09)** — the step builder
  serialises its local ``steps`` array via ``JSON.stringify`` into a
  hidden ``<input name="steps">``. This router parses ``json.loads``
  before constructing :class:`RecipeCreate`, and folds JSON-decode
  errors into the form re-render with an ``_steps`` banner. The schema
  layer (``StepSchema``) is the authoritative per-step validator;
  client-side Alpine is convenience only.
* **HX-Redirect (D-12)** — ``POST /recipes/{id}/duplicate`` returns
  ``200`` with header ``HX-Redirect: /recipes/{new_id}/edit`` and an
  empty body. HTMX 2.0 consumes the header and performs a full
  ``window.location`` navigation — same-tab, fresh page, edit form
  pre-populated. The pattern is locked for Phase 5+ cross-page
  navigation flows.

Endpoints
---------

* ``GET /recipes`` — list page (full HTML for non-HTMX, fragment for HTMX).
* ``GET /recipes/new`` — empty form fragment, seeds the Alpine builder
  with one "Bloom" step via ``steps_json``.
* ``GET /recipes/empty-form`` — empty fragment served to Cancel.
* ``POST /recipes`` — create. Validation errors → 200 + form re-render.
* ``GET /recipes/{id}/row`` — row fragment; used by Cancel button in edit mode.
* ``GET /recipes/{id}/edit`` — form fragment pre-populated; seeds the
  Alpine builder via ``data-initial-steps="{{ recipe.steps | tojson }}"``.
* ``POST /recipes/{id}`` — update. Same validation re-render pattern.
* ``POST /recipes/{id}/duplicate`` — D-12 deep copy + ``HX-Redirect``.
* ``POST /recipes/{id}/archive`` — soft-delete; returns updated row.

Per-step error handling decision (documented in SUMMARY)
--------------------------------------------------------

Pydantic returns nested ``loc=("steps", 2, "water_grams")`` for per-step
errors. The shared ``errors_by_field`` helper takes the last non-integer
loc component, which would produce ``"water_grams"`` and collide with
hypothetical top-level fields. Phase 4 ships a banner-only approach:
any error whose root loc is ``"steps"`` is folded into the ``_steps``
sentinel rendered as one banner above the step builder. Per-step ring
highlighting (UI-SPEC ``ring-1 ring-red-300``) is a plan 04-11 follow-up.

CSRF (T-04-CSRF)
----------------

Every form template renders the hidden ``X-CSRF-Token`` input from
``request.cookies.get('csrftoken', '')``. The ``CSRFFormFieldShim``
(Phase 2 D-15) hoists the field into the ``X-CSRF-Token`` header before
``CSRFMiddleware`` runs. The duplicate POST is an HTMX request and
carries the header via the global ``htmx:configRequest`` listener
(``app/static/js/htmx-listeners.js``).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.dependencies.auth import require_user
from app.dependencies.db import get_session
from app.models.user import User
from app.schemas.recipe import RecipeCreate
from app.services import recipes as recipes_service
from app.services.recipes import RecipeNotFound
from app.templates_setup import templates

router = APIRouter(prefix="/recipes")

# Field keys the inline form template renders error paragraphs for.
# Anything outside this set (a T-04-MASS extra field, or a per-step
# nested loc) is folded into ``_form`` or ``_steps`` so the user still
# sees the error.
_FORM_FIELDS = {
    "name",
    "dose_grams",
    "water_grams",
    "water_temp_c",
    "grind_setting",
}


def _parse_step_count(value: object) -> int | None:
    """Best-effort parse for the optional integer count fields."""
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _normalize_errors(exc: ValidationError) -> dict[str, str]:
    """Pivot the ValidationError and fold non-rendered keys into banners.

    Per-step errors (``loc=("steps", N, "field")``) → ``_steps`` banner.
    Mass-assignment / unknown fields → ``_form`` banner.
    All other recognised fields render under their own field key.
    """
    out: dict[str, str] = {}
    step_msgs: list[str] = []
    form_msgs: list[str] = []
    for err in exc.errors():
        loc = err.get("loc", ())
        msg = err.get("msg", "Invalid value")
        # Per-step errors land under "steps" at loc[0]; emit a single
        # banner pointing the user at the step builder rather than try
        # to surface per-step inline messages in Phase 4 (per-step
        # highlight is a 04-11 follow-up).
        if loc and loc[0] == "steps":
            # Render index + leaf field if available for diagnostic help.
            label = "steps"
            if len(loc) >= 2 and isinstance(loc[1], int):
                label = f"steps[{loc[1]}]"
                if len(loc) >= 3:
                    label = f"{label}.{loc[2]}"
            step_msgs.append(f"{label}: {msg}")
            continue
        # Use last non-int component as field name.
        field = next(
            (str(p) for p in reversed(loc) if not isinstance(p, int)),
            "_form",
        )
        if field in _FORM_FIELDS or field == "_form":
            out[field] = msg
        else:
            form_msgs.append(f"{field}: {msg}")
    if step_msgs:
        out["_steps"] = "; ".join(step_msgs)
    if form_msgs:
        existing = out.get("_form")
        joined = "; ".join(form_msgs)
        out["_form"] = joined if existing is None else f"{existing}; {joined}"
    return out


def _coerce_numeric(raw: dict[str, object]) -> dict[str, object]:
    """Coerce the numeric form fields from str to int where possible.

    The HTML form ships every value as a string. Pydantic v2 with
    ``Field(..., ge=1)`` will accept a numeric string under
    ``model_config`` defaults, but explicit coercion here keeps the
    error path predictable when the user types a non-numeric value
    (Pydantic emits ``int_parsing`` which we render as the field's
    own error).
    """
    out = dict(raw)
    for key in ("dose_grams", "water_grams", "water_temp_c"):
        if key in out and isinstance(out[key], str) and out[key].strip() != "":
            try:
                out[key] = int(out[key])  # type: ignore[arg-type]
            except ValueError:
                # Leave as-is; Pydantic will reject with int_parsing.
                pass
    return out


# --------------------------------------------------------------------------- #
# List page + HTMX fragment                                                   #
# --------------------------------------------------------------------------- #


@router.get("", response_class=HTMLResponse)
def list_recipes(
    request: Request,
    include_archived: bool = False,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """List page. HTMX swap → fragment; full GET → page template."""
    rows = recipes_service.list_recipes(db, include_archived=include_archived)
    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request,
            name="fragments/recipe_list.html",
            context={"recipes": rows, "include_archived": include_archived},
        )
    return templates.TemplateResponse(
        request=request,
        name="pages/recipes.html",
        context={"recipes": rows, "include_archived": include_archived},
    )


# --------------------------------------------------------------------------- #
# Create — form GET + POST                                                    #
# --------------------------------------------------------------------------- #


# UI-SPEC §"Recipe Step Builder" — pre-load the empty form with one Bloom
# step so the user has a starting point (zero-step state is otherwise
# valid but disorienting).
_DEFAULT_NEW_STEPS = [{"water_grams": 50, "time_seconds": 45, "label": "Bloom"}]


@router.get("/new", response_class=HTMLResponse)
def new_recipe_form(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
) -> Response:
    """Empty form fragment seeded with one Bloom step."""
    return templates.TemplateResponse(
        request=request,
        name="fragments/recipe_form.html",
        context={
            "values": {},
            "errors": {},
            "mode": "create",
            "steps_json": json.dumps(_DEFAULT_NEW_STEPS),
        },
    )


@router.get("/empty-form", response_class=HTMLResponse)
def empty_form(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
) -> Response:
    """Empty fragment served to the Cancel button (CSP-safe — no inline JS)."""
    return templates.TemplateResponse(
        request=request,
        name="fragments/empty.html",
        context={},
    )


@router.post("", response_class=HTMLResponse)
async def create_recipe(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Create a recipe. Validation errors → 200 + form re-render.

    Reads raw form via ``await request.form()`` so unknown fields reach
    the schema's ``extra='forbid'`` defense (T-04-MASS).

    The ``steps`` field is a JSON-stringified array produced by the
    Alpine builder. We ``json.loads`` it before constructing the
    schema — a JSONDecodeError is folded into the ``_steps`` banner.
    """
    form_data = await request.form()
    skip = {"X-CSRF-Token"}
    raw: dict[str, object] = {k: v for k, v in form_data.items() if k not in skip}

    # Parse the steps JSON before handing to the schema. A decode failure
    # is a user-visible error (banner above the step builder).
    steps_raw = raw.pop("steps", "[]")
    try:
        steps_list = json.loads(steps_raw) if isinstance(steps_raw, str) else steps_raw
        if not isinstance(steps_list, list):
            raise ValueError("steps must be a JSON array")
    except (ValueError, TypeError):
        return templates.TemplateResponse(
            request=request,
            name="fragments/recipe_form.html",
            context={
                "values": raw,
                "errors": {"_steps": "Invalid step data — please re-enter your pour timeline."},
                "mode": "create",
                "steps_json": "[]",
            },
            status_code=200,
        )

    coerced = _coerce_numeric(raw)
    coerced["steps"] = steps_list
    try:
        form = RecipeCreate(**coerced)
    except ValidationError as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/recipe_form.html",
            context={
                "values": raw,
                "errors": _normalize_errors(exc),
                "mode": "create",
                # Re-seed the step builder with what the user submitted so
                # they don't lose their step data on re-render.
                "steps_json": json.dumps(steps_list),
            },
            status_code=200,
        )

    recipe = recipes_service.create_recipe(
        db,
        name=form.name,
        dose_grams=form.dose_grams,
        water_grams=form.water_grams,
        water_temp_c=form.water_temp_c,
        grind_setting=form.grind_setting,
        steps=[s.model_dump() for s in form.steps],
        by_user_id=user.id,
    )

    return templates.TemplateResponse(
        request=request,
        name="fragments/recipe_row.html",
        context={
            "recipe": recipe,
            "mode": "row",
            "include_oob_form_clear": True,
        },
    )


# --------------------------------------------------------------------------- #
# Edit / Update / Archive / Duplicate                                         #
# --------------------------------------------------------------------------- #


@router.get("/{recipe_id}/row", response_class=HTMLResponse)
def recipe_row(
    recipe_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Row fragment served to the Cancel button in edit mode."""
    recipe = recipes_service.get_recipe(db, recipe_id=recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request=request,
        name="fragments/recipe_row.html",
        context={"recipe": recipe, "mode": "row"},
    )


@router.get("/{recipe_id}/edit", response_class=HTMLResponse)
def edit_recipe_form(
    recipe_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Pre-populated form fragment for inline edit (swaps the row)."""
    recipe = recipes_service.get_recipe(db, recipe_id=recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404)
    values = {
        "name": recipe.name,
        "dose_grams": recipe.dose_grams,
        "water_grams": recipe.water_grams,
        "water_temp_c": recipe.water_temp_c,
        "grind_setting": recipe.grind_setting or "",
    }
    return templates.TemplateResponse(
        request=request,
        name="fragments/recipe_form.html",
        context={
            "values": values,
            "errors": {},
            "mode": "edit",
            "recipe_id": recipe_id,
            "steps_json": json.dumps(recipe.steps or []),
        },
    )


@router.post("/{recipe_id}", response_class=HTMLResponse)
async def update_recipe_handler(
    recipe_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Update a recipe. Validation errors → 200 + form re-render."""
    existing = recipes_service.get_recipe(db, recipe_id=recipe_id)
    if existing is None:
        raise HTTPException(status_code=404)

    form_data = await request.form()
    skip = {"X-CSRF-Token"}
    raw: dict[str, object] = {k: v for k, v in form_data.items() if k not in skip}
    steps_raw = raw.pop("steps", "[]")
    try:
        steps_list = json.loads(steps_raw) if isinstance(steps_raw, str) else steps_raw
        if not isinstance(steps_list, list):
            raise ValueError("steps must be a JSON array")
    except (ValueError, TypeError):
        return templates.TemplateResponse(
            request=request,
            name="fragments/recipe_form.html",
            context={
                "values": raw,
                "errors": {"_steps": "Invalid step data — please re-enter your pour timeline."},
                "mode": "edit",
                "recipe_id": recipe_id,
                "steps_json": "[]",
            },
            status_code=200,
        )

    coerced = _coerce_numeric(raw)
    coerced["steps"] = steps_list
    try:
        form = RecipeCreate(**coerced)
    except ValidationError as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/recipe_form.html",
            context={
                "values": raw,
                "errors": _normalize_errors(exc),
                "mode": "edit",
                "recipe_id": recipe_id,
                "steps_json": json.dumps(steps_list),
            },
            status_code=200,
        )

    recipe = recipes_service.update_recipe(
        db,
        recipe_id=recipe_id,
        name=form.name,
        dose_grams=form.dose_grams,
        water_grams=form.water_grams,
        water_temp_c=form.water_temp_c,
        grind_setting=form.grind_setting,
        steps=[s.model_dump() for s in form.steps],
        by_user_id=user.id,
    )
    return templates.TemplateResponse(
        request=request,
        name="fragments/recipe_row.html",
        context={"recipe": recipe, "mode": "row"},
    )


@router.post("/{recipe_id}/archive", response_class=HTMLResponse)
def archive_recipe_handler(
    recipe_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Soft-delete a recipe; re-render the row with archived styling."""
    existing = recipes_service.get_recipe(db, recipe_id=recipe_id)
    if existing is None:
        raise HTTPException(status_code=404)
    recipes_service.archive_recipe(db, recipe_id=recipe_id, by_user_id=user.id)
    recipe = recipes_service.get_recipe(db, recipe_id=recipe_id)
    return templates.TemplateResponse(
        request=request,
        name="fragments/recipe_row.html",
        context={"recipe": recipe, "mode": "row"},
    )


@router.post("/{recipe_id}/duplicate", response_class=HTMLResponse)
def duplicate_recipe_handler(
    recipe_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """D-12 deep copy of *recipe_id*; HX-Redirect to the new edit form.

    Returns ``200`` with an empty body + ``HX-Redirect: /recipes/{new_id}/edit``.
    HTMX 2.0 consumes the header and performs a full ``window.location``
    navigation — the user lands on the edit form of the new recipe in
    the same tab. This pattern is locked for Phase 5+ cross-page
    navigation flows triggered from HTMX swaps.
    """
    try:
        copy = recipes_service.duplicate_recipe(db, source_id=recipe_id, by_user_id=user.id)
    except RecipeNotFound as exc:
        raise HTTPException(status_code=404) from exc
    return Response(
        status_code=200,
        headers={"HX-Redirect": f"/recipes/{copy.id}/edit"},
    )


__all__ = ["router"]
