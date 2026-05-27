"""Roasters CRUD router — HTMX inline-expand fragments + Pydantic-v2 form validation.

Implements the universal Phase 4 catalog template (D-01..D-04 inline-expand
pattern, SEC-06 form-validation re-render at HTTP 200, D-13/D-14 autocomplete
endpoint with HX-4 race mitigation, D-15 mini-modal substrate via the
``HX-Trigger`` response header).

Endpoints
---------

* ``GET /roasters`` — list page (full HTML for non-HTMX, fragment for HTMX).
* ``GET /roasters/new`` — empty form fragment (inline or modal flavor).
* ``GET /roasters/empty-form`` — empty fragment used by Cancel buttons.
* ``POST /roasters`` — create. Validation errors → 200 + form-fragment
  re-render with errors. ``as_modal=true`` → empty body + ``HX-Trigger``
  ``roaster-created`` header (D-15 substrate for plan 04-11's mini-modal).
* ``GET /roasters/{id}/row`` — row fragment; used by Cancel button in edit mode.
* ``GET /roasters/{id}/edit`` — form fragment pre-populated with the row.
* ``POST /roasters/{id}`` — update. Same validation re-render pattern.
* ``POST /roasters/{id}/archive`` — soft-delete; returns updated row.
* ``GET /roasters/list`` — D-13 autocomplete fragment. Empty body if
  ``len(q) < 2``; otherwise an ``<ul role="listbox">`` with match-highlight
  + "+ Create new" affordance when there's no exact match.

Form validation contract (SEC-06)
---------------------------------

Every state-changing POST catches :class:`pydantic.ValidationError` and
re-renders the form fragment at HTTP 200 with two context keys:

* ``values``: dict of the raw form params the user submitted (preserved
  so the user doesn't have to retype).
* ``errors``: ``{field_name: message}`` from
  :func:`app.services.form_validation.errors_by_field`.

D-04 says HTTP 200 (NOT 422) because HTMX swaps the response body into
the form mount regardless of status code, and 422 would trip the
``htmx:responseError`` event chain.

HX-Trigger payload (D-15)
-------------------------

POST ``/roasters?as_modal=true`` (or ``as_modal=true`` form field) on
successful create returns an empty body + this header::

    HX-Trigger: {"roaster-created": {"roaster_id": <int>, "name": <str>}}

The Alpine listener in plan 04-11 (mini-modal.js) consumes this event to
pre-select the new roaster in the parent coffee form and close the modal.

CSRF (T-04-CSRF)
----------------

Every form template renders the hidden ``X-CSRF-Token`` input from
``request.cookies.get('csrftoken', '')``. The ``CSRFFormFieldShim``
(Phase 2 D-15) hoists the field into the ``X-CSRF-Token`` header before
``CSRFMiddleware`` runs. POSTs without a valid CSRF token receive 403
from the middleware — exercised by ``test_csrf_missing_returns_403``.
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
from app.schemas.roaster import RoasterCreate
from app.services import roasters as roasters_service
from app.services.form_validation import DuplicateNameError, errors_by_field
from app.templates_setup import templates

router = APIRouter(prefix="/roasters")

# Field keys the inline form template renders error paragraphs for. Any
# ValidationError landing on a key outside this set (e.g., the extra-field
# rejection on ``is_admin`` from a T-04-MASS probe) is folded into the
# ``_form`` sentinel so the user still sees the error rendered.
_FORM_FIELDS = {"name", "location", "website", "notes"}

# Fields where an empty form-string is semantically "no value" — coerce to
# ``None`` before handing to the Pydantic schema so an empty website input
# doesn't trip ``HttpUrl`` validation, and a blank location stays as
# ``str | None = None`` rather than the empty string. ``name`` and
# ``notes`` are deliberately NOT in this set: name is required (min_length=1
# trips on the empty value, which is the desired error), and notes has a
# legitimate ``""`` default that is meaningful as "no extra notes".
_EMPTY_TO_NONE_FIELDS = {"location", "website"}


def _coerce_empty_to_none(raw: dict[str, str]) -> dict[str, object]:
    """Map ``""`` → ``None`` for optional fields whose schema type rejects ``""``."""
    out: dict[str, object] = dict(raw)
    for key in _EMPTY_TO_NONE_FIELDS:
        if out.get(key) == "":
            out[key] = None
    return out


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
        # Preserve any existing _form message by joining.
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
def list_roasters(
    request: Request,
    include_archived: bool = False,
    user: User = Depends(require_user),  # noqa: B008 — FastAPI canonical Form 1.
    db: Session = Depends(get_session),  # noqa: B008 — FastAPI canonical Form 1.
) -> Response:
    """List page. HTMX swap → fragment; full GET → page template."""
    rows = roasters_service.list_roasters(db, include_archived=include_archived)
    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request,
            name="fragments/roaster_list.html",
            context={"roasters": rows, "include_archived": include_archived},
        )
    return templates.TemplateResponse(
        request=request,
        name="pages/roasters.html",
        context={"roasters": rows, "include_archived": include_archived},
    )


# --------------------------------------------------------------------------- #
# Create — form GET + POST                                                    #
# --------------------------------------------------------------------------- #


@router.get("/new", response_class=HTMLResponse)
def new_roaster_form(
    request: Request,
    as_modal: bool = False,
    prefill: str = "",
    user: User = Depends(require_user),  # noqa: B008
) -> Response:
    """Empty form fragment. ``as_modal=true`` → the modal-chrome variant.

    ``prefill`` (plan 04-11): when the user clicks "+ Create new roaster"
    on the coffee form's autocomplete dropdown, the parent autocomplete_list
    fragment hx-gets ``/roasters/new?as_modal=true&prefill=<typed-text>``
    so the modal's Name input opens pre-populated. Bounded at 200 chars
    (matches the schema's max_length) to defeat junk-URL DoS shapes.
    """
    name = "fragments/roaster_modal.html" if as_modal else "fragments/roaster_form.html"
    return templates.TemplateResponse(
        request=request,
        name=name,
        context={
            "values": {},
            "errors": {},
            "mode": "modal" if as_modal else "create",
            "prefill": (prefill or "")[:200],
            "layout": None,
            "form_target": "#roaster-form-mount",
            "form_swap": "innerHTML",
        },
    )


@router.get("/empty-form", response_class=HTMLResponse)
def empty_form(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
) -> Response:
    """Empty fragment served to the Cancel button.

    Per CSP (Phase 1 D-04) we cannot use ``onclick="..."`` to clear the
    form mount; the Cancel button does ``hx-get /roasters/empty-form``
    and the server returns an empty ``<div></div>``. Keeps the server
    as the single source of truth and matches the inline-expand pattern
    philosophy.
    """
    return templates.TemplateResponse(
        request=request,
        name="fragments/empty.html",
        context={},
    )


@router.post("", response_class=HTMLResponse)
async def create_roaster(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Create a roaster. Validation errors → 200 + form re-render.

    Reads the raw form via ``await request.form()`` (not individual
    ``Form(...)`` params) so that extra/mass-assignment fields reach the
    Pydantic schema and trip ``extra="forbid"`` (T-04-MASS). Per
    FastAPI's docs, ``Form(...)`` params would silently drop unknown
    fields — leaving the mass-assignment defense to the schema layer
    alone — which a probe with no header-set assertions might miss.
    """
    form_data = await request.form()
    # Filter out CSRF substrate + flow flag before handing to the schema.
    skip = {"X-CSRF-Token", "as_modal"}
    raw = {k: v for k, v in form_data.items() if k not in skip}
    as_modal_raw = form_data.get("as_modal")
    as_modal = isinstance(as_modal_raw, str) and as_modal_raw.lower() in (
        "true",
        "on",
        "1",
    )
    coerced = _coerce_empty_to_none(raw)
    try:
        form = RoasterCreate(**coerced)
    except ValidationError as exc:
        # Preserve the user's submitted text on re-render (D-04).
        return templates.TemplateResponse(
            request=request,
            name="fragments/roaster_form.html",
            context={
                "values": raw,
                "errors": _normalize_errors(errors_by_field(exc)),
                "mode": "modal" if as_modal else "create",
                "layout": None,
                "form_target": "#roaster-form-mount",
                "form_swap": "innerHTML",
            },
            status_code=200,
        )

    try:
        roaster = roasters_service.create_roaster(
            db,
            name=form.name,
            location=form.location,
            website=str(form.website) if form.website else None,
            notes=form.notes,
            by_user_id=user.id,
        )
    except DuplicateNameError:
        # UNIQUE CITEXT name collision → friendly inline name error (not a 500),
        # re-rendered via the SAME path the ValidationError branch uses (D-04).
        return templates.TemplateResponse(
            request=request,
            name="fragments/roaster_form.html",
            context={
                "values": raw,
                "errors": _normalize_errors({"name": "Name already exists."}),
                "mode": "modal" if as_modal else "create",
                "layout": None,
                "form_target": "#roaster-form-mount",
                "form_swap": "innerHTML",
            },
            status_code=200,
        )

    if as_modal:
        # D-15 / D-16 substrate: empty body + HX-Trigger header. The
        # Alpine miniModal listener (plan 04-11) consumes the
        # ``roaster-created`` event to pre-select the new roaster and
        # close the modal.
        response = templates.TemplateResponse(
            request=request,
            name="fragments/empty.html",
            context={},
        )
        response.headers["HX-Trigger"] = json.dumps(
            {"roaster-created": {"roaster_id": roaster.id, "name": roaster.name}}
        )
        return response

    return templates.TemplateResponse(
        request=request,
        name="fragments/roaster_row.html",
        context={
            "roaster": roaster,
            "mode": "row",
            "include_oob_form_clear": True,
        },
    )


# --------------------------------------------------------------------------- #
# Edit / Update / Archive                                                     #
# --------------------------------------------------------------------------- #


@router.get("/{roaster_id}/row", response_class=HTMLResponse)
def roaster_row(
    roaster_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Row fragment served to the Cancel button in edit mode."""
    roaster = roasters_service.get_roaster(db, roaster_id=roaster_id)
    if roaster is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request=request,
        name="fragments/roaster_row.html",
        context={"roaster": roaster, "mode": "row"},
    )


@router.get("/{roaster_id}/edit", response_class=HTMLResponse)
def edit_roaster_form(
    roaster_id: int,
    request: Request,
    layout: str | None = None,  # D-21: "desktop" or None
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Pre-populated form fragment for inline edit (swaps the row).

    ``layout="desktop"`` renders the form targeting #roaster-form-mount;
    without it the form targets closest [data-row]. T-15.1-29: only the
    literal "desktop" value is accepted; any other value falls back to mobile.
    """
    # T-15.1-29: only accept the literal "desktop" value.
    if layout != "desktop":
        layout = None
    roaster = roasters_service.get_roaster(db, roaster_id=roaster_id)
    if roaster is None:
        raise HTTPException(status_code=404)
    values = {
        "name": roaster.name,
        "location": roaster.location or "",
        "website": roaster.website or "",
        "notes": roaster.notes or "",
    }
    if layout == "desktop":
        form_target, form_swap = "#roaster-form-mount", "innerHTML"
    else:
        form_target, form_swap = "closest [data-row]", "outerHTML"
    return templates.TemplateResponse(
        request=request,
        name="fragments/roaster_form.html",
        context={
            "values": values,
            "errors": {},
            "mode": "edit",
            "roaster_id": roaster_id,
            "layout": layout,
            "form_target": form_target,
            "form_swap": form_swap,
        },
    )


@router.post("/{roaster_id}", response_class=HTMLResponse)
async def update_roaster_handler(
    roaster_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Update a roaster. Validation errors → 200 + form re-render.

    Same raw-form-read pattern as :func:`create_roaster` so the schema's
    ``extra="forbid"`` defense is exercised on the update path too.
    """
    existing = roasters_service.get_roaster(db, roaster_id=roaster_id)
    if existing is None:
        raise HTTPException(status_code=404)

    form_data = await request.form()
    skip = {"X-CSRF-Token", "as_modal"}
    raw = {k: v for k, v in form_data.items() if k not in skip}
    # D-21: read layout from hidden form field; only "desktop" is accepted (T-15.1-29).
    layout = raw.pop("layout", None)
    if layout != "desktop":
        layout = None
    if layout == "desktop":
        form_target, form_swap = "#roaster-form-mount", "innerHTML"
    else:
        form_target, form_swap = "closest [data-row]", "outerHTML"
    coerced = _coerce_empty_to_none(raw)
    try:
        form = RoasterCreate(**coerced)
    except ValidationError as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/roaster_form.html",
            context={
                "values": raw,
                "errors": _normalize_errors(errors_by_field(exc)),
                "mode": "edit",
                "roaster_id": roaster_id,
                "layout": layout,
                "form_target": form_target,
                "form_swap": form_swap,
            },
            status_code=200,
        )

    try:
        roaster = roasters_service.update_roaster(
            db,
            roaster_id=roaster_id,
            name=form.name,
            location=form.location,
            website=str(form.website) if form.website else None,
            notes=form.notes,
            by_user_id=user.id,
        )
    except DuplicateNameError:
        # Renaming onto an existing name → friendly inline name error (not 500).
        return templates.TemplateResponse(
            request=request,
            name="fragments/roaster_form.html",
            context={
                "values": raw,
                "errors": _normalize_errors({"name": "Name already exists."}),
                "mode": "edit",
                "roaster_id": roaster_id,
                "layout": layout,
                "form_target": form_target,
                "form_swap": form_swap,
            },
            status_code=200,
        )
    if layout == "desktop":
        return templates.TemplateResponse(
            request=request,
            name="fragments/roaster_row.html",
            context={"roaster": roaster, "mode": "row", "include_desktop_oob": True},
        )
    return templates.TemplateResponse(
        request=request,
        name="fragments/roaster_row.html",
        context={"roaster": roaster, "mode": "row"},
    )


@router.post("/{roaster_id}/archive", response_class=HTMLResponse)
def archive_roaster_handler(
    roaster_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Soft-delete a roaster; re-render the row with archived styling."""
    existing = roasters_service.get_roaster(db, roaster_id=roaster_id)
    if existing is None:
        raise HTTPException(status_code=404)
    roasters_service.archive_roaster(db, roaster_id=roaster_id, by_user_id=user.id)
    roaster = roasters_service.get_roaster(db, roaster_id=roaster_id)
    return templates.TemplateResponse(
        request=request,
        name="fragments/roaster_row.html",
        context={"roaster": roaster, "mode": "row"},
    )


# --------------------------------------------------------------------------- #
# Autocomplete (D-13 / HX-4)                                                  #
# --------------------------------------------------------------------------- #


@router.get("/list", response_class=HTMLResponse)
def roaster_autocomplete(
    request: Request,
    roaster_query: str = "",
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """D-13 autocomplete dropdown fragment.

    Empty body when ``len(q) < 2`` to keep the client-side debounce
    cheap. Otherwise an ``<ul role="listbox">`` with up to 50 matches.
    Appends a "+ Create new roaster" affordance when no exact match
    exists, opening the mini-modal substrate path.

    The query param is ``roaster_query`` — the coffee form's autocomplete
    input is ``name="roaster_query"`` so HTMX sends it under that key.
    """
    q = roaster_query
    if len(q) < 2:
        return HTMLResponse("", status_code=200)
    matches = roasters_service.search_by_prefix(db, query=q)
    exact_match = any(r.name.lower() == q.lower() for r in matches)
    return templates.TemplateResponse(
        request=request,
        name="fragments/autocomplete_list.html",
        context={
            "items": matches,
            "query": q,
            "entity": "roaster",
            "exact_match": exact_match,
            "create_new_endpoint": "/roasters/new?as_modal=true",
        },
    )


__all__ = ["router"]
