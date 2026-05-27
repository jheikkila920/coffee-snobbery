"""Cafe-log form router — dedicated add/edit page + origin-country autocomplete.

Mirrors :mod:`app.routers.brew` (the canonical SEC-06 / D-04 router) with the
Phase-16 divergences locked by 16-CONTEXT / 16-PATTERNS:

* **Dedicated page routes (D-10).** ``GET /cafe-logs/new`` and
  ``GET /cafe-logs/{id}/edit`` render the full ``pages/cafe_log_form.html``
  page (extends ``base.html``); the success path responds ``HX-Redirect`` to
  the cafe tab of the sessions list.
* **Per-user scoping (architectural invariant, T-16-02-03 IDOR).** Every cafe
  log read / write is scoped by ``request.state.user.id`` via the service
  layer; a cross-user ``cafe_log_id`` returns 404 (the service sentinel
  ``None`` mapped to ``HTTPException(404)``) — existence non-leak, not 403.
* **Mass-assignment defense (T-16-02-01).** ``_parse_form_payload`` NEVER reads
  ``user_id`` or ``photo_filename`` from the form; ``CafeLogCreate``'s
  ``extra="forbid"`` folds any extra into the ``_form`` sentinel and re-renders
  at HTTP 200.
* **Origin-country autocomplete (D-03).** ``GET /origin-country-autocomplete``
  returns merged distinct values from ``coffee_origins.country`` + a seeded
  country list. No ``+ Create new`` affordance (free-text field, not a FK).
* **No draft autosave.** Cafe form is short; no server-side draft table needed
  (CONTEXT Claude's-discretion No-at-v1 default).
* **No audit-log events.** Per CONTEXT Claude's-discretion default the
  household-scale audit posture is "auth + admin events".

Endpoints (LITERAL paths declared BEFORE ``/{cafe_log_id}`` — route-order
gotcha: Starlette's int matcher would otherwise capture ``/new`` and
``/origin-country-autocomplete``):

* ``GET  /cafe-logs/new``                          — create-mode form.
* ``GET  /cafe-logs/origin-country-autocomplete``  — autocomplete suggestions.
* ``POST /cafe-logs``                              — create. ValidationError → 200 + re-render.
* ``GET  /cafe-logs/{id}/edit``                    — edit-mode form, 404 on IDOR.
* ``POST /cafe-logs/{id}``                         — update or delete (_method=DELETE).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.dependencies.auth import require_user
from app.dependencies.db import get_session
from app.models.coffee_origin import CoffeeOrigin
from app.models.user import User
from app.schemas.cafe_log import CafeLogCreate, CafeLogUpdate
from app.services import cafe_logs as cafe_logs_service
from app.services import coffees as coffees_service
from app.services import photos
from app.services import roasters as roasters_service
from app.services.form_validation import errors_by_field
from app.templates_setup import templates

router = APIRouter(prefix="/cafe-logs")

# Post-save destination (CONTEXT D-11).
_LIST_URL = "/brew?tab=cafe"

# Form fields the cafe-log template renders error paragraphs for. Any
# ValidationError landing outside this set folds into ``_form`` so the
# user still sees it rendered.
_FORM_FIELDS = {
    "cafe_name",
    "rating",
    "roaster_id",
    "origin_country",
    "brew_method",
    "flavor_note_ids",
    "notes",
    "logged_at",
}

# Optional scalar / text fields where an empty string from the browser means
# "no value" and must become ``None`` before Pydantic validation.
_EMPTY_TO_NONE_FIELDS = {
    "rating",
    "roaster_id",
    "origin_country",
    "brew_method",
    "logged_at",
}

# Integer FK fields the router casts before handing to the schema.
_INT_FIELDS = {"roaster_id"}

# Form keys added by the autocomplete / chip widgets that are NOT schema fields.
# Stripping them keeps extra=forbid from tripping on a false positive.
# CRITICAL: "layout" MUST be here (Pitfall 2 — ?layout=desktop driver field
# trips extra="forbid" when the hidden input mirrors the query param).
# CRITICAL: "photo" MUST be here — it is an UploadFile, not a string, and the
# router reads it directly from form_data AFTER schema validation; passing it
# to CafeLogCreate would trip extra="forbid" with an UploadFile value.
_NON_SCHEMA_FORM_KEYS = {
    "X-CSRF-Token",
    "roaster_query",
    "flavor_note_query",
    # D-03 origin_country fix: the visible input now posts directly as
    # `origin_country` (no separate _query input + hidden id), so there is
    # nothing to strip here. Keeping the explanatory comment for future readers.
    "layout",  # D-21: desktop layout param; stripped before Pydantic sees payload
    "_method",  # POST + _method=DELETE pattern (HTMX 2.x convention)
    "photo",  # file upload — handled separately by the router, not a schema field
}

# Seeded country list for the origin-country autocomplete (RESEARCH Pattern 5).
# Source: common single-origin coffee-producing countries worldwide.
_SEEDED_COUNTRIES = (
    "Ethiopia",
    "Kenya",
    "Colombia",
    "Brazil",
    "Guatemala",
    "Costa Rica",
    "Honduras",
    "Panama",
    "Peru",
    "Mexico",
    "Indonesia",
    "Yemen",
    "Rwanda",
    "Burundi",
    "Tanzania",
    "El Salvador",
    "Nicaragua",
    "Ecuador",
    "Bolivia",
)


# --------------------------------------------------------------------------- #
# Internal helpers                                                              #
# --------------------------------------------------------------------------- #


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


def _parse_form_payload(form_data: Any) -> tuple[dict[str, object], dict[str, object]]:
    """Convert raw FormData → ``(raw_view, schema_input)``.

    ``raw_view`` echoes the user's submission for a validation re-render.
    ``schema_input`` is the dict handed to the Pydantic schema: empty optional
    strings coerce to ``None``, FK ids cast to ``int``, and
    ``flavor_note_ids`` is collected via ``getlist`` → ``list[int]``.

    ``user_id`` and ``photo_filename`` are NEVER read from the form
    (T-16-02-01 mass-assignment defense) — if posted, they fall through to the
    schema's ``extra="forbid"`` and fold into ``_form``.
    """
    raw_view: dict[str, object] = {}
    schema_input: dict[str, object] = {}

    seen_keys: set[str] = set()
    for key, _ in form_data.multi_items():
        if key in seen_keys:
            continue
        seen_keys.add(key)
        if key in _NON_SCHEMA_FORM_KEYS:
            continue
        if key == "flavor_note_ids":
            values = form_data.getlist(key)
            id_strs = [v for v in values if isinstance(v, str) and v != ""]
            raw_view[key] = id_strs
            try:
                schema_input[key] = [int(v) for v in id_strs]
            except (TypeError, ValueError):
                schema_input[key] = [0]
            continue

        value = form_data.get(key)
        raw_view[key] = value
        if isinstance(value, str) and value == "" and key in _EMPTY_TO_NONE_FIELDS:
            schema_input[key] = None
        elif key in _INT_FIELDS and isinstance(value, str) and value:
            try:
                schema_input[key] = int(value)
            except ValueError:
                schema_input[key] = value
        else:
            schema_input[key] = value

    return raw_view, schema_input


def _resolve_flavor_notes(db: Session, ids: list[int]) -> list[dict[str, object]]:
    """Return ``[{id, name}]`` for the given flavor note ids (chip pre-hydration)."""
    if not ids:
        return []
    name_map = coffees_service.flavor_note_name_map(db, ids=ids)
    return [{"id": fid, "name": name_map.get(fid, str(fid))} for fid in ids if fid in name_map]


def _resolve_roaster_name(db: Session, roaster_id: int | None) -> str:
    """Return the roaster name string for the given id, or ""."""
    if roaster_id is None:
        return ""
    roaster = roasters_service.get_roaster(db, roaster_id=roaster_id)
    return roaster.name if roaster else ""


def _num_str(value: Decimal | None) -> str:
    """Render a Decimal as a clean form-input string ("" for None)."""
    if value is None:
        return ""
    try:
        return format(value.normalize(), "f") if isinstance(value, Decimal) else str(value)
    except (InvalidOperation, ValueError):
        return str(value)


def _hydrate_form_context(
    db: Session,
    *,
    user: User,
    values: dict[str, object],
    errors: dict[str, str],
    mode: str,
    cafe_log_id: int | None = None,
    layout: str | None = None,
) -> dict[str, object]:
    """Build the cafe-log form page context.

    D-21 dual-Edit-button dispatch:
    * layout="desktop" + edit → target="#cafe-form-mount" / swap="innerHTML"
    * edit without layout  → target="closest [data-row]" / swap="outerHTML"
    * create              → target="#cafe-form-mount" / swap="innerHTML"
    """
    # Seeded observed chips (per-log) — resolved server-side so chips render
    # before Alpine hydrates. NEVER from advertised_flavor_note_ids.
    observed_raw = values.get("flavor_note_ids") or []
    observed_ids: list[int] = []
    if isinstance(observed_raw, list):
        for v in observed_raw:
            try:
                observed_ids.append(int(v))
            except (TypeError, ValueError):
                continue
    selected_flavor_notes = _resolve_flavor_notes(db, observed_ids)

    # Determine the roaster name for the autocomplete pre-fill.
    roaster_id_raw = values.get("roaster_id")
    roaster_name = ""
    if roaster_id_raw:
        try:
            roaster_name = _resolve_roaster_name(db, int(str(roaster_id_raw)))
        except (TypeError, ValueError):
            roaster_name = ""

    # D-21 HTMX target/swap dispatch.
    if mode == "edit" and layout == "desktop":
        hx_target = "#cafe-form-mount"
        hx_swap = "innerHTML"
    elif mode == "edit":
        hx_target = "closest [data-row]"
        hx_swap = "outerHTML"
    else:
        hx_target = "#cafe-form-mount"
        hx_swap = "innerHTML"

    form_action = f"/cafe-logs/{cafe_log_id}" if mode == "edit" else "/cafe-logs"

    return {
        "values": values,
        "errors": errors,
        "mode": mode,
        "cafe_log_id": cafe_log_id,
        "layout": layout,
        "selected_flavor_notes": selected_flavor_notes,
        "roaster_name": roaster_name,
        "hx_target": hx_target,
        "hx_swap": hx_swap,
        "form_action": form_action,
    }


def _render_form_error(
    request: Request,
    db: Session,
    *,
    user: User,
    raw_view: dict[str, object],
    exc: ValidationError,
    mode: str,
    cafe_log_id: int | None = None,
    layout: str | None = None,
) -> Response:
    """Re-render the cafe-log form at HTTP 200 with errors (SEC-06, not 422)."""
    context = _hydrate_form_context(
        db,
        user=user,
        values=raw_view,
        errors=_normalize_errors(errors_by_field(exc)),
        mode=mode,
        cafe_log_id=cafe_log_id,
        layout=layout,
    )
    return templates.TemplateResponse(
        request=request,
        name="pages/cafe_log_form.html",
        context=context,
        status_code=200,
    )


# --------------------------------------------------------------------------- #
# LITERAL paths declared BEFORE /{cafe_log_id} — route-order gotcha           #
# --------------------------------------------------------------------------- #


@router.get("/new", response_class=HTMLResponse)
def new_cafe_log_form(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Create-mode cafe-log form (D-10, D-11).

    Autofocus is a template concern (autofocus attr on cafe_name input).
    """
    context = _hydrate_form_context(
        db,
        user=user,
        values={},
        errors={},
        mode="create",
        layout=None,
    )
    return templates.TemplateResponse(
        request=request, name="pages/cafe_log_form.html", context=context
    )


@router.get("/origin-country-autocomplete", response_class=HTMLResponse)
def origin_country_autocomplete(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Country suggestions for the cafe form (D-03, RESEARCH Pattern 5).

    Sources: distinct ``coffee_origins.country`` values UNION the seeded list.
    NOT a create-on-the-fly entity — free-text autocomplete with suggestions
    only. ``create_new_endpoint=""`` disables the ``+ Create new`` affordance.
    """
    query = (request.query_params.get("q") or "").strip()
    if len(query) < 2:
        return templates.TemplateResponse(
            request=request,
            name="fragments/autocomplete_list.html",
            context={
                "items": [],
                "query": query,
                "entity": "country",
                "exact_match": True,
                "create_new_endpoint": "",
            },
        )

    # Distinct existing values from the shared coffee catalog.
    db_countries = (
        db.execute(
            select(CoffeeOrigin.country)
            .where(CoffeeOrigin.country.ilike(f"{query}%"))
            .distinct()
            .order_by(CoffeeOrigin.country)
            .limit(50)
        )
        .scalars()
        .all()
    )

    # Merge with seeded list, dedupe, prefix-match, limit to 20.
    candidates = set(db_countries) | {
        c for c in _SEEDED_COUNTRIES if c.lower().startswith(query.lower())
    }
    items = [{"id": c, "name": c} for c in sorted(candidates)][:20]

    return templates.TemplateResponse(
        request=request,
        name="fragments/autocomplete_list.html",
        context={
            "items": items,
            "query": query,
            "entity": "country",
            "exact_match": any(i["name"].lower() == query.lower() for i in items),
            "create_new_endpoint": "",  # no "+ Create new" — free text (D-03)
        },
    )


@router.post("", response_class=HTMLResponse)
async def create_cafe_log(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Create a cafe log (SEC-06). ValidationError → 200 + form re-render.

    On success the server sets ``user_id`` from ``request.state.user.id``
    (never the form) and responds ``HX-Redirect`` to the cafe tab.
    """
    form_data = await request.form()
    raw_view, schema_input = _parse_form_payload(form_data)
    try:
        form = CafeLogCreate(**schema_input)
    except ValidationError as exc:
        return _render_form_error(request, db, user=user, raw_view=raw_view, exc=exc, mode="create")

    # Photo handling (optional).
    photo_filename: str | None = None
    photo_field = form_data.get("photo")
    if isinstance(photo_field, UploadFile) and photo_field.filename:
        raw_bytes = await photo_field.read()
        if raw_bytes:
            try:
                photo_filename = photos.process_and_save(raw_bytes)
            except photos.PhotoRejected as exc:
                raw_view["photo"] = None
                raw_view_with_err = dict(raw_view)
                err_msg = str(exc) or "Photo must be JPEG, PNG, or WebP under 10 MB."
                try:
                    # Re-raise as ValidationError shape so _render_form_error normalizes it.
                    from pydantic import ValidationError as PydanticVE
                    from pydantic_core import InitErrorDetails

                    raise PydanticVE.from_exception_data(
                        "CafeLogCreate",
                        [
                            InitErrorDetails(
                                type="value_error",
                                loc=("photo",),
                                input=raw_bytes,
                                ctx={"error": ValueError(err_msg)},
                            )
                        ],
                    ) from exc
                except Exception:
                    # Fallback: build errors dict manually and re-render.
                    context = _hydrate_form_context(
                        db,
                        user=user,
                        values=raw_view_with_err,
                        errors={"photo": err_msg},
                        mode="create",
                    )
                    return templates.TemplateResponse(
                        request=request,
                        name="pages/cafe_log_form.html",
                        context=context,
                        status_code=200,
                    )

    cafe_logs_service.create_cafe_log(
        db,
        by_user_id=user.id,
        cafe_name=form.cafe_name,
        rating=form.rating,
        roaster_id=form.roaster_id,
        origin_country=form.origin_country,
        brew_method=form.brew_method,
        flavor_note_ids=form.flavor_note_ids,
        notes=form.notes,
        photo_filename=photo_filename,
        logged_at=form.logged_at,
    )
    return Response(status_code=204, headers={"HX-Redirect": _LIST_URL})


# --------------------------------------------------------------------------- #
# Edit / Update (declared AFTER the literal paths above)                       #
# --------------------------------------------------------------------------- #


@router.get("/{cafe_log_id}/edit", response_class=HTMLResponse)
def edit_cafe_log_form(
    cafe_log_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Edit-mode form with the log's actual stored values.

    404 (not 403) on a non-owned id (IDOR existence non-leak T-16-02-03).
    Reads optional ``?layout=desktop`` query param for the D-21 dual-Edit
    pattern — desktop renders as a fragment into ``#cafe-form-mount``, mobile
    renders inline (``outerHTML`` of ``closest [data-row]``).
    """
    row = cafe_logs_service.get_cafe_log(db, cafe_log_id=cafe_log_id, by_user_id=user.id)
    if row is None:
        raise HTTPException(status_code=404)

    layout = request.query_params.get("layout")

    values: dict[str, object] = {
        "cafe_name": row.cafe_name or "",
        "rating": _num_str(row.rating),
        "roaster_id": str(row.roaster_id) if row.roaster_id is not None else "",
        "origin_country": row.origin_country or "",
        "brew_method": row.brew_method or "",
        "flavor_note_ids": [str(i) for i in (row.flavor_note_ids or [])],
        "notes": row.notes or "",
        "logged_at": row.logged_at.strftime("%Y-%m-%dT%H:%M") if row.logged_at else "",
        "photo_filename": row.photo_filename or "",
    }
    context = _hydrate_form_context(
        db,
        user=user,
        values=values,
        errors={},
        mode="edit",
        cafe_log_id=cafe_log_id,
        layout=layout,
    )
    return templates.TemplateResponse(
        request=request, name="pages/cafe_log_form.html", context=context
    )


@router.post("/{cafe_log_id}", response_class=HTMLResponse)
async def update_cafe_log_handler(
    cafe_log_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Update or delete an owned cafe log.

    Branches on ``form._method == "DELETE"`` (HTMX 2.x POST + hidden field
    convention per CLAUDE.md §3.2). Returns 404 on IDOR for both paths.
    """
    form_data = await request.form()
    _method = form_data.get("_method")

    # --- DELETE branch -------------------------------------------------------
    if _method == "DELETE":
        ok = cafe_logs_service.delete_cafe_log(db, cafe_log_id=cafe_log_id, by_user_id=user.id)
        if not ok:
            raise HTTPException(status_code=404)
        # Empty response — HTMX removes the element via hx-target / hx-swap on success.
        return HTMLResponse(content="", status_code=200)

    # --- UPDATE branch -------------------------------------------------------
    layout = request.query_params.get("layout") or str(form_data.get("layout") or "")
    raw_view, schema_input = _parse_form_payload(form_data)
    try:
        form = CafeLogUpdate(**schema_input)
    except ValidationError as exc:
        return _render_form_error(
            request,
            db,
            user=user,
            raw_view=raw_view,
            exc=exc,
            mode="edit",
            cafe_log_id=cafe_log_id,
            layout=layout or None,
        )

    # Photo handling (optional — only replace if a new file was submitted).
    photo_filename: str | None = None
    photo_field = form_data.get("photo")
    if isinstance(photo_field, UploadFile) and photo_field.filename:
        raw_bytes = await photo_field.read()
        if raw_bytes:
            try:
                photo_filename = photos.process_and_save(raw_bytes)
            except photos.PhotoRejected as exc:
                err_msg = str(exc) or "Photo must be JPEG, PNG, or WebP under 10 MB."
                context = _hydrate_form_context(
                    db,
                    user=user,
                    values=raw_view,
                    errors={"photo": err_msg},
                    mode="edit",
                    cafe_log_id=cafe_log_id,
                    layout=layout or None,
                )
                return templates.TemplateResponse(
                    request=request,
                    name="pages/cafe_log_form.html",
                    context=context,
                    status_code=200,
                )

    update_fields: dict[str, object] = {
        "cafe_name": form.cafe_name,
        "rating": form.rating,
        "roaster_id": form.roaster_id,
        "origin_country": form.origin_country,
        "brew_method": form.brew_method,
        "flavor_note_ids": form.flavor_note_ids,
        "notes": form.notes,
    }
    # Only overwrite logged_at when the user explicitly submitted a date.
    # Omitting it on the form (empty string → None) preserves the stored value.
    # Avoids NOT NULL violation when the date input is blank during an update.
    if form.logged_at is not None:
        update_fields["logged_at"] = form.logged_at
    if photo_filename is not None:
        update_fields["photo_filename"] = photo_filename

    updated = cafe_logs_service.update_cafe_log(
        db, cafe_log_id=cafe_log_id, by_user_id=user.id, **update_fields
    )
    if updated is None:
        raise HTTPException(status_code=404)
    return Response(status_code=204, headers={"HX-Redirect": _LIST_URL})
