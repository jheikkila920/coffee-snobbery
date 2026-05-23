"""Brew-session form router — dedicated add/edit page + dynamic re-prefill (D-01).

Mirrors :mod:`app.routers.coffees` (the canonical SEC-06 / D-04 router) with the
Phase-5 divergences locked by 05-CONTEXT / 05-UI-SPEC / 05-PATTERNS:

* **Dedicated page routes (D-01), not inline fragments.** ``GET /brew/new`` and
  ``GET /brew/{id}/edit`` render the full ``pages/brew_form.html`` page (extends
  ``base.html``); the success path responds ``HX-Redirect`` to the sessions
  list rather than swapping a row fragment.
* **Per-user scoping (architectural invariant, T-05-05 IDOR).** Every brew read
  / write is scoped by ``request.state.user.id`` via the service layer; a
  cross-user ``session_id`` returns 404 (the service sentinel ``None`` mapped to
  ``HTTPException(404)``) — existence non-leak, not 403.
* **Mass-assignment defense (T-05-16).** ``_parse_form_payload`` NEVER reads
  ``extraction_yield_pct`` (GENERATED) or ``user_id`` (server-owned) from the
  form; ``BrewSessionCreate``'s ``extra="forbid"`` folds any extra into the
  ``_form`` sentinel and re-renders at HTTP 200.
* **Prefill engine (D-04/D-05/D-06/D-08).** The router calls
  :func:`app.services.brew_sessions.resolve_prefill` (no prefill logic is
  duplicated here) and layers the per-field touched-state map + pill captions +
  the D-11 advertised quick-add chips on top.
* **Draft autosave (BREW-07).** ``POST /brew/draft`` upserts the one-per-user
  draft under CSRF (NOT exempt); ``clear_draft`` fires on a successful create.
  Drafts apply to ``/brew/new`` ONLY — the edit form is never draft-backed.

Endpoints (LITERAL paths declared BEFORE ``/{session_id}`` — the route-order
gotcha: Starlette's int matcher would otherwise capture ``/new`` etc.):

* ``GET  /brew/new``            — create-mode form, prefilled (D-04/D-05/D-06/D-08).
* ``GET  /brew/prefill``        — dynamic re-prefill FRAGMENT (D-04/D-05/D-11).
* ``POST /brew/draft``          — autosave the per-user draft (BREW-07).
* ``POST /brew``                — create. ValidationError → 200 + re-render.
* ``GET  /brew/{id}/edit``      — edit-mode form, actual stored values, 404 on IDOR.
* ``POST /brew/{id}``           — update. 404 on IDOR; HX-Redirect on success.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.config import settings
from app.dependencies.auth import require_user
from app.dependencies.db import get_session
from app.models.user import User
from app.schemas.brew_session import BrewSessionCreate, BrewSessionUpdate
from app.services import brew_drafts as brew_drafts_service
from app.services import brew_sessions as brew_sessions_service
from app.services import coffees as coffees_service
from app.services import csv_io as csv_io_service
from app.services import equipment as equipment_service
from app.services import recipes as recipes_service
from app.services.form_validation import errors_by_field
from app.templates_setup import templates

router = APIRouter(prefix="/brew")

# The sessions list (Plan 06) lives at /brew. Success redirects here.
_LIST_URL = "/brew"

# Field keys the brew form template renders error paragraphs for. Any
# ValidationError landing outside this set (e.g. the extra=forbid rejection on
# a posted ``extraction_yield_pct`` / ``user_id``) folds into ``_form`` so the
# user still sees the error rendered (matches coffees.py:_normalize_errors).
_FORM_FIELDS = {
    "coffee_id",
    "bag_id",
    "recipe_id",
    "brewer_id",
    "grinder_id",
    "kettle_id",
    "water_type",
    "dose_grams_actual",
    "water_grams_actual",
    "yield_grams_actual",
    "tds_pct",
    "water_temp_c_actual",
    "grind_setting_actual",
    "rating",
    "flavor_note_ids_observed",
    "notes",
    "brewed_at",
    "brew_time_seconds",
}

# Optional scalar FK / text fields where an empty string from the browser means
# "no value" and must become ``None`` before Pydantic validation. ``coffee_id``
# is required (blank → desired error); ``notes`` / ``water_type`` /
# ``grind_setting_actual`` legitimately accept ``""``.
_EMPTY_TO_NONE_FIELDS = {
    "bag_id",
    "recipe_id",
    "brewer_id",
    "grinder_id",
    "kettle_id",
    "yield_grams_actual",
    "tds_pct",
    "water_temp_c_actual",
    "rating",
    "brewed_at",
    "brew_time_seconds",
}

# Integer FK fields the router casts before handing to the schema (so a bad int
# surfaces as a clean field error, not a 500).
_INT_FIELDS = {"coffee_id", "bag_id", "recipe_id", "brewer_id", "grinder_id", "kettle_id"}

# Form keys added by the autocomplete / chip widgets that are NOT schema fields.
# Stripping them keeps extra=forbid from tripping on a false positive.
_NON_SCHEMA_FORM_KEYS = {
    "X-CSRF-Token",
    "flavor_note_query",  # the observed-note autocomplete text input
}

# The four prefill-template fields D-05 lets a recipe overwrite — used to tag
# "from recipe" captions on the dynamic re-prefill path.
_RECIPE_TEMPLATE_FIELDS = (
    "dose_grams_actual",
    "water_grams_actual",
    "water_temp_c_actual",
    "grind_setting_actual",
)


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
    ``flavor_note_ids_observed`` is collected via ``getlist`` → ``list[int]``.

    ``extraction_yield_pct`` and ``user_id`` are NEVER read from the form
    (T-05-16 mass-assignment defense) — if posted, they fall through to the
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
        if key == "flavor_note_ids_observed":
            values = form_data.getlist(key)
            id_strs = [v for v in values if isinstance(v, str) and v != ""]
            raw_view[key] = id_strs
            try:
                schema_input[key] = [int(v) for v in id_strs]
            except (TypeError, ValueError):
                # Sentinel trips the schema's ge=1 field_validator.
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
                schema_input[key] = value  # let Pydantic complain on coercion
        else:
            schema_input[key] = value

    return raw_view, schema_input


def _name_map(rows: list[Any]) -> dict[int, str]:
    """Build a ``{id: label}`` map for equipment rows (brand/model display)."""
    out: dict[int, str] = {}
    for row in rows:
        label = f"{row.brand} {row.model}".strip()
        out[row.id] = label or str(row.id)
    return out


def _advertised_chips(db: Session, *, coffee_id: int | None) -> list[dict[str, object]]:
    """The D-11 advertised quick-add chips for the selected coffee.

    Reads ``coffees.advertised_flavor_note_ids`` (per-coffee, roaster-advertised)
    — NEVER conflated with ``flavor_note_ids_observed`` (per-session). Returns a
    list of ``{id, name}`` so the template renders one suggestion chip per note.
    """
    if coffee_id is None:
        return []
    coffee = coffees_service.get_coffee(db, coffee_id=coffee_id)
    if coffee is None:
        return []
    ids = coffee.advertised_flavor_note_ids or []
    if not ids:
        return []
    name_map = coffees_service.flavor_note_name_map(db, ids=ids)
    return [{"id": fid, "name": name_map.get(fid, str(fid))} for fid in ids if fid in name_map]


def _prefill_pill_sources(*, recipe_selected: bool, from_brew: bool) -> dict[str, str]:
    """Per-field pill caption source for the prefill-untouched indicator.

    Caption copy is locked by UI-SPEC: "from last brew" (D-04 default),
    "from recipe" (the four D-05 template fields when a recipe drove them), and
    "from this brew" (D-08 brew-again).
    """
    default = "from this brew" if from_brew else "from last brew"
    sources: dict[str, str] = {field: default for field in brew_sessions_service._CARRYABLE_FIELDS}
    if recipe_selected:
        for field in _RECIPE_TEMPLATE_FIELDS:
            sources[field] = "from recipe"
    return sources


def _stringify_prefill(prefill: dict[str, Any]) -> dict[str, object]:
    """Coerce a prefill dict into template-friendly strings (None → "")."""
    out: dict[str, object] = {}
    for key, value in prefill.items():
        if key == "flavor_note_ids_observed":
            out[key] = [str(v) for v in (value or [])]
        elif value is None:
            out[key] = ""
        else:
            out[key] = str(value)
    return out


def _selectables(db: Session) -> dict[str, object]:
    """The shared-catalog dropdown sources for the brew form selects."""
    equipment = equipment_service.list_equipment(db)
    grouped: dict[str, list[Any]] = {}
    for eq in equipment:
        grouped.setdefault(eq.type, []).append(eq)
    return {
        "coffees": coffees_service.list_coffees(db),
        "recipes": recipes_service.list_recipes(db),
        "brewers": grouped.get("brewer", []),
        "grinders": grouped.get("grinder", []),
        "kettles": grouped.get("kettle", []),
        "equipment_name_map": _name_map(equipment),
    }


def _hydrate_form_context(
    db: Session,
    *,
    user: User,
    values: dict[str, object],
    errors: dict[str, str],
    mode: str,
    session_id: int | None = None,
    prefill: dict[str, Any] | None = None,
    touched: dict[str, bool] | None = None,
    pill_sources: dict[str, str] | None = None,
    server_draft: dict | None = None,
    coffee_id_for_chips: int | None = None,
) -> dict[str, object]:
    """Build the brew-form page context.

    The locked context contract (so Plan 05's ``pages/brew_form.html`` renders
    against it — see 05-04-SUMMARY):

    * ``values``: dict — form field name → submitted/prefilled string (or
      ``list[str]`` for ``flavor_note_ids_observed``).
    * ``errors``: dict — field name → message.
    * ``mode``: ``"create" | "edit"``.
    * ``session_id``: int (edit mode only).
    * ``touched``: ``{field: bool}`` — per-field touched-state seeded ``False``
      (prefilled-untouched drives the pills); empty in edit mode (no ghosting).
    * ``pill_sources``: ``{field: caption}`` — "from last brew" / "from recipe"
      / "from this brew".
    * ``advertised_chips``: ``list[{id, name}]`` — D-11 quick-add chips.
    * ``selected_flavor_notes``: ``list[{id, name}]`` — seeded observed chips.
    * ``coffees`` / ``recipes`` / ``brewers`` / ``grinders`` / ``kettles``:
      dropdown sources; ``equipment_name_map`` for label lookups.
    * ``server_draft``: dict | None — exposed for client reconciliation
      (create mode only; ``/brew/new`` is the only draft-backed surface).
    * ``form_action``: POST target (``/brew`` or ``/brew/{id}``).
    """
    coffee_for_chips = coffee_id_for_chips
    if coffee_for_chips is None:
        raw = values.get("coffee_id")
        if isinstance(raw, str) and raw:
            try:
                coffee_for_chips = int(raw)
            except ValueError:
                coffee_for_chips = None
        elif isinstance(raw, int):
            coffee_for_chips = raw

    # Seeded observed chips (per-session) — resolved server-side so chips render
    # before Alpine hydrates. NEVER from advertised_flavor_note_ids.
    observed_raw = values.get("flavor_note_ids_observed") or []
    observed_ids: list[int] = []
    if isinstance(observed_raw, list):
        for v in observed_raw:
            try:
                observed_ids.append(int(v))
            except (TypeError, ValueError):
                continue
    selected_flavor_notes = (
        [
            {"id": fid, "name": name}
            for fid, name in coffees_service.flavor_note_name_map(db, ids=observed_ids).items()
        ]
        if observed_ids
        else []
    )

    context: dict[str, object] = {
        "values": values,
        "errors": errors,
        "mode": mode,
        "session_id": session_id,
        "touched": touched or {},
        "pill_sources": pill_sources or {},
        "advertised_chips": _advertised_chips(db, coffee_id=coffee_for_chips),
        "selected_flavor_notes": selected_flavor_notes,
        "server_draft": server_draft,
        "server_draft_json": json.dumps(server_draft) if server_draft is not None else "",
        "form_action": f"/brew/{session_id}" if mode == "edit" else "/brew",
        **_selectables(db),
    }
    return context


# --------------------------------------------------------------------------- #
# Sessions list + CSV export/import (BREW-10 / BREW-11)                         #
# (LITERAL paths declared BEFORE /{session_id} — route-order gotcha)          #
# --------------------------------------------------------------------------- #

# The six list/export filter query params, shared by GET /brew and
# GET /brew/export so the export is exactly the currently-filtered view.
_LIST_FILTER_KEYS = (
    "coffee_id",
    "brewer_id",
    "rating_min",
    "rating_max",
    "date_from",
    "date_to",
)


def _decimal_or_none(value: object) -> Decimal | None:
    """Best-effort Decimal coercion; ``None`` on empty / non-numeric."""
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _date_or_none(value: object, *, end_of_day: bool = False) -> datetime | None:
    """Parse a ``YYYY-MM-DD`` (or ISO datetime) filter bound to tz-aware UTC.

    A bare date as ``date_to`` is widened to the end of that day so an
    inclusive ``<=`` upper bound captures the whole day's sessions.
    """
    if value is None or value == "":
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d")  # noqa: DTZ007 — tz set below
        except ValueError:
            return None
    if end_of_day and parsed.hour == 0 and parsed.minute == 0 and parsed.second == 0:
        parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_list_filters(qp: Any) -> dict[str, Any]:
    """Parse the list/export query params into typed service kwargs.

    Returns only the keys with a non-``None`` value so the service applies
    each filter solely when provided. All clauses are parameterized in the
    service ``select()`` (SQLi defense T-05-25).
    """
    parsed: dict[str, Any] = {
        "coffee_id": _int_or_none(qp.get("coffee_id")),
        "brewer_id": _int_or_none(qp.get("brewer_id")),
        "rating_min": _decimal_or_none(qp.get("rating_min")),
        "rating_max": _decimal_or_none(qp.get("rating_max")),
        "date_from": _date_or_none(qp.get("date_from")),
        "date_to": _date_or_none(qp.get("date_to"), end_of_day=True),
    }
    return {k: v for k, v in parsed.items() if v is not None}


def _raw_filters(qp: Any) -> dict[str, str]:
    """Echo the raw filter strings back to the template (selected state + chips)."""
    return {key: (qp.get(key) or "") for key in _LIST_FILTER_KEYS}


def _local_dt(value: datetime | None) -> datetime | None:
    """Render a stored-UTC timestamp in ``APP_TIMEZONE`` for display."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    try:
        return value.astimezone(ZoneInfo(settings.APP_TIMEZONE))
    except Exception:  # noqa: BLE001 — bad tz config must not break the list
        return value.astimezone(UTC)


def _brew_ratio(dose: Decimal | None, water: Decimal | None) -> str:
    """``water / dose`` to 2 dp; em dash when dose is 0/null (never NaN/Inf)."""
    if not dose or water is None:
        return "—"
    try:
        return str((Decimal(water) / Decimal(dose)).quantize(Decimal("0.01")))
    except (InvalidOperation, ZeroDivisionError):
        return "—"


def _session_view_rows(db: Session, sessions: list[Any]) -> list[dict[str, object]]:
    """Resolve each session's display fields (names, local date, ratio).

    Builds id→name caches in one query per entity type (no N+1 in the
    template), reusing the same resolution shape as the CSV exporter.
    """
    caches = csv_io_service._build_name_caches(db, sessions)
    rows: list[dict[str, object]] = []
    for s in sessions:
        coffee_name, roaster_name = caches["coffee"].get(s.coffee_id, ("", ""))
        rows.append(
            {
                "id": s.id,
                "brewed_at_local": _local_dt(s.brewed_at),
                "coffee_name": coffee_name or "—",
                "roaster_name": roaster_name or "",
                "brewer_name": caches["equipment"].get(s.brewer_id, "") if s.brewer_id else "",
                "recipe_name": caches["recipe"].get(s.recipe_id, "") if s.recipe_id else "",
                "ratio": _brew_ratio(s.dose_grams_actual, s.water_grams_actual),
                "rating": s.rating,
            }
        )
    return rows


@router.get("", response_class=HTMLResponse)
def list_sessions(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Per-user sessions list (BREW-10). Page or HTMX fragment, filtered.

    Returns ONLY the authed user's sessions, newest first (T-05-24 IDOR).
    With an ``HX-Request`` header → the ``#session-list`` fragment (filter
    swap); otherwise the full page. ``FragmentCacheHeadersMiddleware`` adds
    ``no-store + Vary: HX-Request`` to the fragment for free.
    """
    qp = request.query_params
    service_filters = _parse_list_filters(qp)
    sessions = brew_sessions_service.list_brew_sessions(db, by_user_id=user.id, **service_filters)
    raw_filters = _raw_filters(qp)
    list_context = {
        "rows": _session_view_rows(db, sessions),
        "filters": raw_filters,
        "active_filter_count": sum(1 for v in raw_filters.values() if v),
        "export_query": request.url.query,
    }

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request,
            name="fragments/session_list.html",
            context={**list_context, "is_fragment": True},
        )

    # Full-page render also needs the filter-bar dropdown sources.
    equipment = equipment_service.list_equipment(db)
    brewers = [eq for eq in equipment if eq.type == "brewer"]
    return templates.TemplateResponse(
        request=request,
        name="pages/sessions.html",
        context={
            **list_context,
            "coffees": coffees_service.list_coffees(db),
            "brewers": brewers,
            "equipment_name_map": _name_map(brewers),
        },
    )


@router.get("/export")
def export_sessions(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Download the currently-filtered sessions as name-resolved CSV (D-15).

    Same filter query params as ``GET /brew`` so the export mirrors the
    on-screen view. User-scoped (T-05-24); round-trip-safe + formula-injection
    neutralized by the csv_io service.
    """
    service_filters = _parse_list_filters(request.query_params)
    csv_text = csv_io_service.export_brews(db, by_user_id=user.id, **service_filters)
    filename = f"snobbery-sessions-{datetime.now(UTC).date().isoformat()}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/import", response_class=HTMLResponse)
def import_form(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
) -> Response:
    """Render the CSV import upload page (before-upload empty state)."""
    return templates.TemplateResponse(
        request=request, name="pages/brew_import.html", context={"results": None}
    )


@router.post("/import", response_class=HTMLResponse)
async def import_sessions(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Single-transaction CSV import (BREW-11) → per-row result fragment.

    Layer 1 — Content-Length pre-check (T-05-27 / W-01): if the ``Content-Length``
    request header is present, all-digit, and exceeds ``MAX_CSV_BYTES``, reject
    immediately BEFORE ``await request.form()`` buffers the body. This stops the
    multipart body from being read at all for obviously oversized uploads.
    Non-digit or absent values (chunked transfer-encoding has no Content-Length)
    fall through — the post-read check below covers those cases.

    Layer 2 — Post-read size check (defense-in-depth): retained as-is. Catches
    absent or lying Content-Length headers (chunked clients, adversarial clients).

    Layer 3 — Content-type allow-list: enforced on the parsed upload object.

    CSRF-enforced (not exempt, T-05-26); ``user_id`` is server-set, never from
    the file.
    """
    cl_header = request.headers.get("content-length")
    if (
        cl_header is not None
        and cl_header.isdigit()
        and int(cl_header) > csv_io_service.MAX_CSV_BYTES
    ):
        return _render_import_results(
            request, outcomes=[], error="That file is too large to import."
        )

    form = await request.form()
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        return _render_import_results(request, outcomes=[], error="Choose a CSV file to import.")

    content_type = (upload.content_type or "").split(";")[0].strip().lower()
    if content_type not in csv_io_service.ALLOWED_CSV_CONTENT_TYPES:
        return _render_import_results(
            request, outcomes=[], error="That file is not a CSV. Export a CSV and try again."
        )

    raw_bytes = await upload.read()
    if len(raw_bytes) > csv_io_service.MAX_CSV_BYTES:
        return _render_import_results(
            request, outcomes=[], error="That file is too large to import."
        )

    outcomes = csv_io_service.import_brews(db, raw_bytes=raw_bytes, by_user_id=user.id)
    return _render_import_results(request, outcomes=outcomes, error=None)


def _render_import_results(request: Request, *, outcomes: list[Any], error: str | None) -> Response:
    """Render the per-row import outcome fragment (or an upload error)."""
    inserted = sum(1 for o in outcomes if o.status == "inserted")
    skipped = sum(1 for o in outcomes if o.status == "skipped")
    refused = sum(1 for o in outcomes if o.status == "refused")
    return templates.TemplateResponse(
        request=request,
        name="fragments/csv_import_results.html",
        context={
            "outcomes": outcomes,
            "inserted": inserted,
            "skipped": skipped,
            "refused": refused,
            "error": error,
        },
    )


# --------------------------------------------------------------------------- #
# Create — GET form + POST                                                     #
# (LITERAL paths declared BEFORE /{session_id} — route-order gotcha)          #
# --------------------------------------------------------------------------- #


@router.get("/new", response_class=HTMLResponse)
def new_brew_form(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Create-mode brew form, prefilled per D-04/D-05/D-06/D-08 (BREW-02/09).

    ``?from={id}`` brews-again from a user-owned session (D-08, IDOR-safe);
    ``?coffee_id`` / ``?recipe_id`` re-source on the open-form path. The server
    draft (if any) is exposed for client-side reconciliation — ``/brew/new`` is
    the only draft-backed surface.
    """
    qp = request.query_params
    from_session_id = _int_or_none(qp.get("from"))
    coffee_id = _int_or_none(qp.get("coffee_id"))
    recipe_id = _int_or_none(qp.get("recipe_id"))
    brew_time = _int_or_none(qp.get("brew_time"))  # GBM completion path (BREW-13)

    prefill = brew_sessions_service.resolve_prefill(
        db,
        by_user_id=user.id,
        from_session_id=from_session_id,
        coffee_id=coffee_id,
        recipe_id=recipe_id,
    )
    values = _stringify_prefill(prefill)
    # Seed brew_time_seconds from the GBM completion redirect (?brew_time=T).
    # This is a direct query-param value, not a prefill-engine field, so it's
    # applied after _stringify_prefill (T-11-13: _int_or_none + schema ge=0/le=86400).
    if brew_time is not None:
        values["brew_time_seconds"] = str(brew_time)
    # Prefilled-untouched: every prefilled field starts touched=False (drives
    # the pills); per-attempt fields are always blank, so no pill there.
    touched = {field: False for field in brew_sessions_service._CARRYABLE_FIELDS}
    pill_sources = _prefill_pill_sources(
        recipe_selected=recipe_id is not None,
        from_brew=from_session_id is not None,
    )
    server_draft = brew_drafts_service.get_draft(db, by_user_id=user.id)

    context = _hydrate_form_context(
        db,
        user=user,
        values=values,
        errors={},
        mode="create",
        prefill=prefill,
        touched=touched,
        pill_sources=pill_sources,
        server_draft=server_draft,
    )
    return templates.TemplateResponse(request=request, name="pages/brew_form.html", context=context)


@router.get("/prefill", response_class=HTMLResponse)
def prefill_fragment(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Dynamic re-prefill FRAGMENT for the coffee/recipe ``<select>`` hx-get.

    Reuses :func:`resolve_prefill` (no duplicate prefill logic) and renders ONLY
    the prefill-dependent fields + the D-11 advertised-chip region. Per-attempt
    fields (rating / observed notes / notes) are deliberately ABSENT so the
    user's in-progress entries are never clobbered by a coffee/recipe change.

    D-04 (coffee re-prefill from the user's last session with that coffee),
    D-05 (recipe-wins overwrites the four template fields), and D-11 (advertised
    chips always refresh to the selected coffee) all flow through here. Scoped to
    ``user.id`` (T-05-18b — no cross-user prefill leak). The
    FragmentCacheHeadersMiddleware applies ``no-store + Vary: HX-Request``.
    """
    qp = request.query_params
    coffee_id = _int_or_none(qp.get("coffee_id"))
    recipe_id = _int_or_none(qp.get("recipe_id"))

    prefill = brew_sessions_service.resolve_prefill(
        db, by_user_id=user.id, coffee_id=coffee_id, recipe_id=recipe_id
    )
    values = _stringify_prefill(prefill)
    touched = {field: False for field in brew_sessions_service._CARRYABLE_FIELDS}
    pill_sources = _prefill_pill_sources(recipe_selected=recipe_id is not None, from_brew=False)
    # The chips refresh to the explicitly selected coffee (D-11) even when the
    # user has never brewed it (resolve_prefill carries coffee_id forward).
    chip_coffee = coffee_id if coffee_id is not None else _int_or_none(values.get("coffee_id"))

    context = _hydrate_form_context(
        db,
        user=user,
        values=values,
        errors={},
        mode="create",
        prefill=prefill,
        touched=touched,
        pill_sources=pill_sources,
        coffee_id_for_chips=chip_coffee,
    )
    return templates.TemplateResponse(
        request=request, name="fragments/brew_prefill_fields.html", context=context
    )


@router.post("/draft")
async def save_draft(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Autosave the per-user brew draft (BREW-07) — CSRF enforced, never exempt.

    Accepts a form-encoded OR JSON payload (whatever Plan 05's brew-draft.js
    sends). The payload is opaque JSON the service stores verbatim. Returns a
    silent ``204`` (no body — autosave is silent per UI-SPEC). Drafts apply to
    ``/brew/new`` ONLY; the edit form is never draft-backed.
    """
    payload = await _read_draft_payload(request)
    brew_drafts_service.upsert_draft(db, by_user_id=user.id, payload=payload)
    return Response(status_code=204)


@router.post("/draft/clear")
def clear_draft(
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Discard the per-user brew draft on demand (UI-SPEC §Draft Persistence).

    The "Discard changes" / "Discard" affordance abandons the in-progress
    ``/brew/new`` form: brew-draft.js wipes the namespaced ``localStorage`` key
    and POSTs here to delete the server backstop draft so a later open does not
    restore stale content (BREW-07 localStorage-primary / server-fallback).
    CSRF-enforced (never exempt); per-user keyed (T-05-08). Silent ``204``.
    """
    brew_drafts_service.clear_draft(db, by_user_id=user.id)
    return Response(status_code=204)


@router.post("", response_class=HTMLResponse)
async def create_brew(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Create a brew session (SEC-06). ValidationError → 200 + form re-render.

    On success the server sets ``user_id`` from ``request.state.user.id`` (never
    the form), clears the per-user draft, and responds ``HX-Redirect`` to the
    sessions list.
    """
    form_data = await request.form()
    raw_view, schema_input = _parse_form_payload(form_data)
    try:
        form = BrewSessionCreate(**schema_input)
    except ValidationError as exc:
        return _render_form_error(request, db, user=user, raw_view=raw_view, exc=exc, mode="create")

    brew_sessions_service.create_brew_session(
        db,
        by_user_id=user.id,
        coffee_id=form.coffee_id,
        bag_id=form.bag_id,
        recipe_id=form.recipe_id,
        brewer_id=form.brewer_id,
        grinder_id=form.grinder_id,
        kettle_id=form.kettle_id,
        water_type=form.water_type,
        dose_grams_actual=form.dose_grams_actual,
        water_grams_actual=form.water_grams_actual,
        yield_grams_actual=form.yield_grams_actual,
        tds_pct=form.tds_pct,
        water_temp_c_actual=form.water_temp_c_actual,
        grind_setting_actual=form.grind_setting_actual,
        rating=form.rating,
        flavor_note_ids_observed=form.flavor_note_ids_observed,
        notes=form.notes,
        brewed_at=form.brewed_at,
        brew_time_seconds=form.brew_time_seconds,
    )
    brew_drafts_service.clear_draft(db, by_user_id=user.id)
    return Response(status_code=204, headers={"HX-Redirect": _LIST_URL})


# --------------------------------------------------------------------------- #
# Edit / Update (declared AFTER the literal paths above)                       #
# --------------------------------------------------------------------------- #


@router.get("/{session_id}/edit", response_class=HTMLResponse)
def edit_brew_form(
    session_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Edit-mode form with the session's actual stored values (no ghost-prefill).

    404 (not 403) on a non-owned id (IDOR existence non-leak). The disclosure
    auto-opens when ``yield_grams_actual`` or ``tds_pct`` is non-null.
    """
    session = brew_sessions_service.get_brew_session(db, session_id=session_id, by_user_id=user.id)
    if session is None:
        raise HTTPException(status_code=404)

    values: dict[str, object] = {
        "coffee_id": str(session.coffee_id),
        "bag_id": str(session.bag_id) if session.bag_id is not None else "",
        "recipe_id": str(session.recipe_id) if session.recipe_id is not None else "",
        "brewer_id": str(session.brewer_id) if session.brewer_id is not None else "",
        "grinder_id": str(session.grinder_id) if session.grinder_id is not None else "",
        "kettle_id": str(session.kettle_id) if session.kettle_id is not None else "",
        "water_type": session.water_type or "",
        "dose_grams_actual": _num_str(session.dose_grams_actual),
        "water_grams_actual": _num_str(session.water_grams_actual),
        "yield_grams_actual": _num_str(session.yield_grams_actual),
        "tds_pct": _num_str(session.tds_pct),
        "water_temp_c_actual": _num_str(session.water_temp_c_actual),
        "grind_setting_actual": session.grind_setting_actual or "",
        "rating": _num_str(session.rating),
        "flavor_note_ids_observed": [str(i) for i in (session.flavor_note_ids_observed or [])],
        "notes": session.notes or "",
        "brewed_at": session.brewed_at.strftime("%Y-%m-%dT%H:%M") if session.brewed_at else "",
        "brew_time_seconds": (
            str(session.brew_time_seconds) if session.brew_time_seconds is not None else ""
        ),
    }
    context = _hydrate_form_context(
        db,
        user=user,
        values=values,
        errors={},
        mode="edit",
        session_id=session_id,
    )
    context["disclosure_open"] = (
        session.yield_grams_actual is not None or session.tds_pct is not None
    )
    # Pre-hydration fallback for the read-only Extraction-yield line: the stored
    # GENERATED column (None when no yield/tds → template renders the em dash).
    # The brewRatio Alpine scope recomputes the same value live from
    # dose+yield+tds on hydration; passing it here avoids a flash of "—" before
    # Alpine boots. NEVER an input, never submitted (T-05-23).
    context["extraction_yield_pct"] = (
        _num_str(session.extraction_yield_pct) if session.extraction_yield_pct is not None else None
    )
    return templates.TemplateResponse(request=request, name="pages/brew_form.html", context=context)


@router.post("/{session_id}", response_class=HTMLResponse)
async def update_brew(
    session_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Update an owned session (SEC-06). 404 on IDOR; HX-Redirect on success.

    Edit is NOT draft-backed (the draft store is a ``/brew/new`` affordance).
    """
    existing = brew_sessions_service.get_brew_session(db, session_id=session_id, by_user_id=user.id)
    if existing is None:
        raise HTTPException(status_code=404)

    form_data = await request.form()
    raw_view, schema_input = _parse_form_payload(form_data)
    try:
        form = BrewSessionUpdate(**schema_input)
    except ValidationError as exc:
        return _render_form_error(
            request, db, user=user, raw_view=raw_view, exc=exc, mode="edit", session_id=session_id
        )

    updated = brew_sessions_service.update_brew_session(
        db,
        session_id=session_id,
        by_user_id=user.id,
        coffee_id=form.coffee_id,
        bag_id=form.bag_id,
        recipe_id=form.recipe_id,
        brewer_id=form.brewer_id,
        grinder_id=form.grinder_id,
        kettle_id=form.kettle_id,
        water_type=form.water_type,
        dose_grams_actual=form.dose_grams_actual,
        water_grams_actual=form.water_grams_actual,
        yield_grams_actual=form.yield_grams_actual,
        tds_pct=form.tds_pct,
        water_temp_c_actual=form.water_temp_c_actual,
        grind_setting_actual=form.grind_setting_actual,
        rating=form.rating,
        flavor_note_ids_observed=form.flavor_note_ids_observed,
        notes=form.notes,
        brewed_at=form.brewed_at,
        brew_time_seconds=form.brew_time_seconds,
    )
    if updated is None:  # raced delete / cross-user — IDOR non-leak.
        raise HTTPException(status_code=404)
    return Response(status_code=204, headers={"HX-Redirect": _LIST_URL})


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _render_form_error(
    request: Request,
    db: Session,
    *,
    user: User,
    raw_view: dict[str, object],
    exc: ValidationError,
    mode: str,
    session_id: int | None = None,
) -> Response:
    """Re-render the brew form at HTTP 200 with errors (SEC-06, not 422)."""
    context = _hydrate_form_context(
        db,
        user=user,
        values=raw_view,
        errors=_normalize_errors(errors_by_field(exc)),
        mode=mode,
        session_id=session_id,
    )
    return templates.TemplateResponse(
        request=request,
        name="pages/brew_form.html",
        context=context,
        status_code=200,
    )


async def _read_draft_payload(request: Request) -> dict:
    """Read the autosave payload as a plain dict (JSON or form-encoded)."""
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        try:
            body = await request.json()
        except Exception:
            return {}
        return body if isinstance(body, dict) else {"value": body}
    form = await request.form()
    return {k: v for k, v in form.multi_items() if k != "X-CSRF-Token"}


def _int_or_none(value: object) -> int | None:
    """Best-effort int coercion; returns ``None`` on empty / non-numeric."""
    if value is None or value == "":
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _num_str(value: Decimal | None) -> str:
    """Render a Decimal as a clean form-input string ("" for None)."""
    if value is None:
        return ""
    try:
        return format(value.normalize(), "f") if isinstance(value, Decimal) else str(value)
    except (InvalidOperation, ValueError):
        return str(value)


__all__ = ["router"]
