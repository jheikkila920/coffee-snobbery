"""Equipment CRUD router — HTMX inline-expand fragments + Pydantic-v2 form validation.

Mirrors :mod:`app.routers.roasters` (plan 04-04) — the universal Phase 4
catalog template. Differences:

* URL prefix is ``/equipment``.
* No autocomplete endpoint (equipment is NOT picked from inside the
  coffee form — Phase 5's brew-session form uses a native ``<select>``).
* No mini-modal — equipment creation lives only on the ``/equipment``
  page, so there is no ``as_modal=true`` substrate and no
  ``HX-Trigger: equipment-created`` event.
* List view groups rows by ``type`` (UI-SPEC §"Equipment — `/equipment`")
  via the service helper :func:`list_equipment_grouped_by_type`.
* The ``type`` form field uses FastAPI's Form-alias trick — the HTML
  field name stays ``type`` but the Python identifier is ``type_`` to
  avoid shadowing the builtin. The raw-form-read pattern from plan 04-04
  means this manifests as a ``raw["type"]`` lookup that we forward as
  ``EquipmentCreate(type=...)``.

Endpoints
---------

* ``GET /equipment`` — list page (full HTML for non-HTMX, fragment for HTMX).
* ``GET /equipment/new`` — empty form fragment.
* ``GET /equipment/empty-form`` — empty fragment used by Cancel buttons.
* ``POST /equipment`` — create. Validation errors → 200 + form-fragment
  re-render with errors.
* ``GET /equipment/{id}/edit`` — form fragment pre-populated with the row.
* ``POST /equipment/{id}`` — update. Same validation re-render pattern.
* ``POST /equipment/{id}/archive`` — soft-delete; returns updated row.

Form validation contract (SEC-06)
---------------------------------

Same as roasters: catch :class:`pydantic.ValidationError`, re-render the
form fragment at HTTP 200 with two context keys (``values`` + ``errors``).

CSRF (T-04-CSRF)
----------------

Every form template renders the hidden ``X-CSRF-Token`` input from
``request.cookies.get('csrftoken', '')``. The ``CSRFFormFieldShim``
(Phase 2 D-15) hoists the field into the ``X-CSRF-Token`` header before
``CSRFMiddleware`` runs. POSTs without a valid CSRF token receive 403
from the middleware.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.dependencies.auth import require_user
from app.dependencies.db import get_session
from app.models.user import User
from app.schemas.equipment import EquipmentCreate
from app.services import equipment as equipment_service
from app.services.form_validation import errors_by_field
from app.templates_setup import templates

router = APIRouter(prefix="/equipment")

# The 6-value type enum — locked in plan 04-02 (schema regex) + plan
# 04-03 (DB CHECK). Passed to the form template so the native ``<select>``
# renders the right ``<option>`` set and pre-selects on edit.
EQUIPMENT_TYPES: tuple[str, ...] = (
    "brewer",
    "grinder",
    "kettle",
    "scale",
    "water_filter",
    "other",
)

# Field keys the inline form template renders error paragraphs for. Any
# ValidationError landing on a key outside this set (e.g., the extra-field
# rejection on ``is_admin`` from a T-04-MASS probe) is folded into the
# ``_form`` sentinel so the user still sees the error rendered.
_FORM_FIELDS = {"type", "brand", "model", "notes"}


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
            "; ".join(leftovers) if existing is None else f"{existing}; {'; '.join(leftovers)}"
        )
        normalized["_form"] = combined
    return normalized


# --------------------------------------------------------------------------- #
# List page + HTMX fragment                                                   #
# --------------------------------------------------------------------------- #


@router.get("", response_class=HTMLResponse)
def list_equipment(
    request: Request,
    include_archived: bool = False,
    user: User = Depends(require_user),  # noqa: B008 — FastAPI canonical Form 1.
    db: Session = Depends(get_session),  # noqa: B008 — FastAPI canonical Form 1.
) -> Response:
    """List page. HTMX swap → fragment; full GET → page template.

    Server-side grouping: the service returns an ordered
    ``{type: [Equipment, ...]}`` dict that the template iterates by key
    for section headings. Alternative considered: Jinja's ``groupby`` filter
    on a flat list. Chose server-side dict to keep the template simple
    and the group ordering explicit.
    """
    groups = equipment_service.list_equipment_grouped_by_type(db, include_archived=include_archived)
    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request,
            name="fragments/equipment_list.html",
            context={"groups": groups, "include_archived": include_archived},
        )
    return templates.TemplateResponse(
        request=request,
        name="pages/equipment.html",
        context={"groups": groups, "include_archived": include_archived},
    )


# --------------------------------------------------------------------------- #
# Create — form GET + POST                                                    #
# --------------------------------------------------------------------------- #


@router.get("/new", response_class=HTMLResponse)
def new_equipment_form(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
) -> Response:
    """Empty form fragment. Inline-expand only — no modal variant
    because equipment isn't picked from another form.
    """
    return templates.TemplateResponse(
        request=request,
        name="fragments/equipment_form.html",
        context={
            "values": {},
            "errors": {},
            "mode": "create",
            "types": EQUIPMENT_TYPES,
        },
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
async def create_equipment(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Create equipment. Validation errors → 200 + form re-render.

    Reads the raw form via ``await request.form()`` (per plan 04-04's
    canonical pattern) so that unknown/mass-assignment fields reach the
    Pydantic schema and trip ``extra="forbid"`` (T-04-MASS).

    The HTML form field name is ``type``; the service-layer param is
    ``type_`` (avoids shadowing the builtin). The raw-form-read pattern
    means we pass ``raw["type"]`` straight into the schema, and only
    rename to ``type_`` at the service call site.
    """
    form_data = await request.form()
    skip = {"X-CSRF-Token"}
    raw = {k: v for k, v in form_data.items() if k not in skip}
    try:
        form = EquipmentCreate(**raw)
    except ValidationError as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/equipment_form.html",
            context={
                "values": raw,
                "errors": _normalize_errors(errors_by_field(exc)),
                "mode": "create",
                "types": EQUIPMENT_TYPES,
            },
            status_code=200,
        )

    equipment = equipment_service.create_equipment(
        db,
        type_=form.type,
        brand=form.brand,
        model=form.model,
        notes=form.notes,
        by_user_id=user.id,
    )
    return templates.TemplateResponse(
        request=request,
        name="fragments/equipment_row.html",
        context={
            "equipment": equipment,
            "mode": "row",
            "include_oob_form_clear": True,
        },
    )


# --------------------------------------------------------------------------- #
# Edit / Update / Archive                                                     #
# --------------------------------------------------------------------------- #


@router.get("/{equipment_id}/edit", response_class=HTMLResponse)
def edit_equipment_form(
    equipment_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Pre-populated form fragment for inline edit (swaps the row)."""
    equipment = equipment_service.get_equipment(db, equipment_id=equipment_id)
    if equipment is None:
        raise HTTPException(status_code=404)
    values = {
        "type": equipment.type,
        "brand": equipment.brand,
        "model": equipment.model,
        "notes": equipment.notes or "",
    }
    return templates.TemplateResponse(
        request=request,
        name="fragments/equipment_form.html",
        context={
            "values": values,
            "errors": {},
            "mode": "edit",
            "equipment_id": equipment_id,
            "types": EQUIPMENT_TYPES,
        },
    )


@router.post("/{equipment_id}", response_class=HTMLResponse)
async def update_equipment_handler(
    equipment_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Update equipment. Validation errors → 200 + form re-render.

    Same raw-form-read pattern as :func:`create_equipment` so the schema's
    ``extra="forbid"`` defense is exercised on the update path too.
    """
    existing = equipment_service.get_equipment(db, equipment_id=equipment_id)
    if existing is None:
        raise HTTPException(status_code=404)

    form_data = await request.form()
    skip = {"X-CSRF-Token"}
    raw = {k: v for k, v in form_data.items() if k not in skip}
    try:
        form = EquipmentCreate(**raw)
    except ValidationError as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/equipment_form.html",
            context={
                "values": raw,
                "errors": _normalize_errors(errors_by_field(exc)),
                "mode": "edit",
                "equipment_id": equipment_id,
                "types": EQUIPMENT_TYPES,
            },
            status_code=200,
        )

    equipment = equipment_service.update_equipment(
        db,
        equipment_id=equipment_id,
        type_=form.type,
        brand=form.brand,
        model=form.model,
        notes=form.notes,
        by_user_id=user.id,
    )
    return templates.TemplateResponse(
        request=request,
        name="fragments/equipment_row.html",
        context={"equipment": equipment, "mode": "row"},
    )


@router.post("/{equipment_id}/archive", response_class=HTMLResponse)
def archive_equipment_handler(
    equipment_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Soft-delete equipment; re-render the row with archived styling."""
    existing = equipment_service.get_equipment(db, equipment_id=equipment_id)
    if existing is None:
        raise HTTPException(status_code=404)
    equipment_service.archive_equipment(db, equipment_id=equipment_id, by_user_id=user.id)
    equipment = equipment_service.get_equipment(db, equipment_id=equipment_id)
    return templates.TemplateResponse(
        request=request,
        name="fragments/equipment_row.html",
        context={"equipment": equipment, "mode": "row"},
    )


__all__ = ["router"]
