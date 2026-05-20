"""Flavor notes CRUD router — HTMX inline-expand fragments + Pydantic-v2 form validation.

Mirrors :mod:`app.routers.roasters` (plan 04-04) — the universal Phase 4
catalog template. Differences:

* URL prefix is ``/flavor-notes`` (hyphen — matches plan 04-04 SUMMARY's
  cross-plan readiness note + UI-SPEC).
* The autocomplete endpoint is ``GET /flavor-notes/datalist`` (not
  ``/list``) per plan + CONTEXT D-14 wording.
* Form fields are ``name`` + ``category`` only. No website/location/notes.
* Category is enforced at three layers (schema regex, DB CHECK, native
  ``<select>``) — the form template hard-codes the 9-value option set.

Endpoints
---------

* ``GET /flavor-notes`` — list page (full page or HTMX fragment).
* ``GET /flavor-notes/new`` — empty form fragment (inline or modal).
* ``GET /flavor-notes/empty-form`` — empty fragment for Cancel buttons.
* ``POST /flavor-notes`` — create. Validation errors → 200 + form
  fragment re-render with errors. ``as_modal=true`` → empty body +
  ``HX-Trigger: flavor-note-created`` header (D-15 substrate for plan
  04-11's mini-modal).
* ``GET /flavor-notes/{id}/edit`` — form fragment pre-populated.
* ``POST /flavor-notes/{id}`` — update. Same validation re-render pattern.
* ``POST /flavor-notes/{id}/archive`` — soft-delete; returns updated row.
* ``GET /flavor-notes/datalist`` — D-13 autocomplete fragment. Empty body
  if ``len(q) < 2``; otherwise an ``<ul role="listbox">`` reusing the
  shared ``fragments/autocomplete_list.html`` from plan 04-04.

HX-Trigger payload (D-15)
-------------------------

POST ``/flavor-notes?as_modal=true`` (or ``as_modal=true`` form field)
on successful create returns an empty body + this header::

    HX-Trigger: {"flavor-note-created": {"flavor_note_id": <int>, "name": <str>}}

Locked for plan 04-11 to consume (mirrors the ``roaster-created``
contract from plan 04-04).
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
from app.schemas.flavor_note import FlavorNoteCreate
from app.services import flavor_notes as flavor_notes_service
from app.services.form_validation import DuplicateNameError, errors_by_field
from app.templates_setup import templates

router = APIRouter(prefix="/flavor-notes")

# The 9-value category enum — locked in plan 04-02 (schema regex) + plan
# 04-03 (DB CHECK). Passed to the form template so the native ``<select>``
# can pre-select the right ``<option>`` on edit.
FLAVOR_NOTE_CATEGORIES: tuple[str, ...] = (
    "fruit",
    "floral",
    "sweet",
    "chocolate",
    "nutty",
    "spice",
    "savory",
    "fermented",
    "other",
)

# Field keys the inline form template renders error paragraphs for. Any
# ValidationError landing on a key outside this set (e.g., the extra-field
# rejection on ``is_admin`` from a T-04-MASS probe) is folded into the
# ``_form`` sentinel so the user still sees the error rendered.
_FORM_FIELDS = {"name", "category"}


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
def list_flavor_notes(
    request: Request,
    include_archived: bool = False,
    user: User = Depends(require_user),  # noqa: B008 — FastAPI canonical Form 1.
    db: Session = Depends(get_session),  # noqa: B008 — FastAPI canonical Form 1.
) -> Response:
    """List page. HTMX swap → fragment; full GET → page template.

    Service returns ``(FlavorNote, usage_count)`` tuples; the template
    iterates them as ``flavor_note, usage_count``.
    """
    rows = flavor_notes_service.list_flavor_notes(db, include_archived=include_archived)
    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request,
            name="fragments/flavor_note_list.html",
            context={"flavor_notes": rows, "include_archived": include_archived},
        )
    return templates.TemplateResponse(
        request=request,
        name="pages/flavor_notes.html",
        context={"flavor_notes": rows, "include_archived": include_archived},
    )


# --------------------------------------------------------------------------- #
# Create — form GET + POST                                                    #
# --------------------------------------------------------------------------- #


@router.get("/new", response_class=HTMLResponse)
def new_flavor_note_form(
    request: Request,
    as_modal: bool = False,
    prefill: str = "",
    user: User = Depends(require_user),  # noqa: B008
) -> Response:
    """Empty form fragment. ``as_modal=true`` → the modal-chrome variant.

    ``prefill`` (plan 04-11): parallel to the roasters/new endpoint —
    the autocomplete's "+ Create new" affordance sends the typed text
    here so the modal opens with the Name input pre-populated. Bounded
    at 80 chars (matches FlavorNoteCreate.name max_length).
    """
    name = "fragments/flavor_note_modal.html" if as_modal else "fragments/flavor_note_form.html"
    return templates.TemplateResponse(
        request=request,
        name=name,
        context={
            "values": {},
            "errors": {},
            "mode": "modal" if as_modal else "create",
            "categories": FLAVOR_NOTE_CATEGORIES,
            "prefill": (prefill or "")[:80],
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
async def create_flavor_note(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Create a flavor note. Validation errors → 200 + form re-render.

    Reads the raw form via ``await request.form()`` (per plan 04-04's
    canonical pattern) so that unknown/mass-assignment fields reach the
    Pydantic schema and trip ``extra="forbid"`` (T-04-MASS).
    """
    form_data = await request.form()
    skip = {"X-CSRF-Token", "as_modal"}
    raw = {k: v for k, v in form_data.items() if k not in skip}
    as_modal_raw = form_data.get("as_modal")
    as_modal = isinstance(as_modal_raw, str) and as_modal_raw.lower() in (
        "true",
        "on",
        "1",
    )
    try:
        form = FlavorNoteCreate(**raw)
    except ValidationError as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/flavor_note_form.html",
            context={
                "values": raw,
                "errors": _normalize_errors(errors_by_field(exc)),
                "mode": "modal" if as_modal else "create",
                "categories": FLAVOR_NOTE_CATEGORIES,
            },
            status_code=200,
        )

    try:
        flavor_note = flavor_notes_service.create_flavor_note(
            db,
            name=form.name,
            category=form.category,
            by_user_id=user.id,
        )
    except DuplicateNameError:
        # UNIQUE CITEXT name collision → friendly inline name error (not a 500),
        # re-rendered via the SAME path the ValidationError branch uses (D-04).
        # categories must stay in context so the <select> still renders.
        return templates.TemplateResponse(
            request=request,
            name="fragments/flavor_note_form.html",
            context={
                "values": raw,
                "errors": _normalize_errors({"name": "Name already exists."}),
                "mode": "modal" if as_modal else "create",
                "categories": FLAVOR_NOTE_CATEGORIES,
            },
            status_code=200,
        )

    if as_modal:
        # D-15 / D-16 substrate: empty body + HX-Trigger header. Locked
        # event-name + payload shape for plan 04-11's mini-modal listener.
        response = templates.TemplateResponse(
            request=request,
            name="fragments/empty.html",
            context={},
        )
        response.headers["HX-Trigger"] = json.dumps(
            {
                "flavor-note-created": {
                    "flavor_note_id": flavor_note.id,
                    "name": flavor_note.name,
                }
            }
        )
        return response

    return templates.TemplateResponse(
        request=request,
        name="fragments/flavor_note_row.html",
        context={
            "flavor_note": flavor_note,
            "usage_count": 0,
            "mode": "row",
            "include_oob_form_clear": True,
        },
    )


# --------------------------------------------------------------------------- #
# Edit / Update / Archive                                                     #
# --------------------------------------------------------------------------- #


@router.get("/{flavor_note_id}/edit", response_class=HTMLResponse)
def edit_flavor_note_form(
    flavor_note_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Pre-populated form fragment for inline edit (swaps the row)."""
    flavor_note = flavor_notes_service.get_flavor_note(db, flavor_note_id=flavor_note_id)
    if flavor_note is None:
        raise HTTPException(status_code=404)
    values = {
        "name": flavor_note.name,
        "category": flavor_note.category,
    }
    return templates.TemplateResponse(
        request=request,
        name="fragments/flavor_note_form.html",
        context={
            "values": values,
            "errors": {},
            "mode": "edit",
            "flavor_note_id": flavor_note_id,
            "categories": FLAVOR_NOTE_CATEGORIES,
        },
    )


@router.post("/{flavor_note_id}", response_class=HTMLResponse)
async def update_flavor_note_handler(
    flavor_note_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Update a flavor note. Validation errors → 200 + form re-render."""
    existing = flavor_notes_service.get_flavor_note(db, flavor_note_id=flavor_note_id)
    if existing is None:
        raise HTTPException(status_code=404)

    form_data = await request.form()
    skip = {"X-CSRF-Token", "as_modal"}
    raw = {k: v for k, v in form_data.items() if k not in skip}
    try:
        form = FlavorNoteCreate(**raw)
    except ValidationError as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/flavor_note_form.html",
            context={
                "values": raw,
                "errors": _normalize_errors(errors_by_field(exc)),
                "mode": "edit",
                "flavor_note_id": flavor_note_id,
                "categories": FLAVOR_NOTE_CATEGORIES,
            },
            status_code=200,
        )

    try:
        flavor_note = flavor_notes_service.update_flavor_note(
            db,
            flavor_note_id=flavor_note_id,
            name=form.name,
            category=form.category,
            by_user_id=user.id,
        )
    except DuplicateNameError:
        # Renaming onto an existing name → friendly inline name error (not 500).
        return templates.TemplateResponse(
            request=request,
            name="fragments/flavor_note_form.html",
            context={
                "values": raw,
                "errors": _normalize_errors({"name": "Name already exists."}),
                "mode": "edit",
                "flavor_note_id": flavor_note_id,
                "categories": FLAVOR_NOTE_CATEGORIES,
            },
            status_code=200,
        )
    return templates.TemplateResponse(
        request=request,
        name="fragments/flavor_note_row.html",
        context={
            "flavor_note": flavor_note,
            "usage_count": 0,
            "mode": "row",
        },
    )


@router.post("/{flavor_note_id}/archive", response_class=HTMLResponse)
def archive_flavor_note_handler(
    flavor_note_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Soft-delete a flavor note; re-render the row with archived styling."""
    existing = flavor_notes_service.get_flavor_note(db, flavor_note_id=flavor_note_id)
    if existing is None:
        raise HTTPException(status_code=404)
    flavor_notes_service.archive_flavor_note(db, flavor_note_id=flavor_note_id, by_user_id=user.id)
    flavor_note = flavor_notes_service.get_flavor_note(db, flavor_note_id=flavor_note_id)
    return templates.TemplateResponse(
        request=request,
        name="fragments/flavor_note_row.html",
        context={
            "flavor_note": flavor_note,
            "usage_count": 0,
            "mode": "row",
        },
    )


# --------------------------------------------------------------------------- #
# Autocomplete (D-13 / D-14 / HX-4)                                           #
# --------------------------------------------------------------------------- #


@router.get("/datalist", response_class=HTMLResponse)
def flavor_note_autocomplete(
    request: Request,
    flavor_note_query: str = "",
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """D-13 autocomplete dropdown fragment.

    Empty body when ``len(q) < 2``. Otherwise an ``<ul role="listbox">``
    with up to 50 matches; appends a "+ Create new flavor note" affordance
    when no exact match exists (opens the mini-modal substrate path via
    ``/flavor-notes/new?as_modal=true``).

    Reuses the shared ``fragments/autocomplete_list.html`` from plan
    04-04 — context shape: ``items, query, entity, exact_match,
    create_new_endpoint``.

    The query param is ``flavor_note_query`` — the coffee form's
    autocomplete input is ``name="flavor_note_query"`` so HTMX sends it
    under that key.
    """
    q = flavor_note_query
    if len(q) < 2:
        return HTMLResponse("", status_code=200)
    matches = flavor_notes_service.search_by_prefix(db, query=q)
    exact_match = any(fn.name.lower() == q.lower() for fn in matches)
    return templates.TemplateResponse(
        request=request,
        name="fragments/autocomplete_list.html",
        context={
            "items": matches,
            "query": q,
            "entity": "flavor note",
            "exact_match": exact_match,
            "create_new_endpoint": "/flavor-notes/new?as_modal=true",
        },
    )


__all__ = ["router"]
