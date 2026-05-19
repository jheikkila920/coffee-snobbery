"""Bags CRUD router — coffee-nested + standalone /bags surface + photo upload.

Mirrors the universal Phase 4 catalog router template (plan 04-04) with
two CAT-08 specifics:

* Coffee-nested route prefix for create + open-new-bag form:
  ``GET /coffees/{coffee_id}/bags/new`` returns the empty form fragment;
  ``POST /coffees/{coffee_id}/bags`` validates and creates the bag.
* Standalone ``/bags/{id}`` routes for edit / update / archive / photo
  lifecycle. The coffee_id is implicit from the bag row — the user
  reaches these via the coffee detail page so a path with the coffee_id
  in it would be redundant (and would duplicate the contract surface).

Photo upload (``POST /bags/{bag_id}/photo``)
-------------------------------------------

The handler is ``async def`` because :meth:`UploadFile.read` is
asynchronous. Inside the async body the sync :mod:`app.services.bags`
calls are direct — per Phase 0 D-08 / 04-RESEARCH SH-3 the short sync
calls are fine at household scale (the work is fast and bounded).

Defense-in-depth order:

1. **Content-Length pre-check** — reject obvious oversize uploads before
   the body is read into memory (saves the Pillow allocation on attacks
   that announce their payload size honestly).
2. **Post-read len check** — some clients omit Content-Length; the
   post-read length is the canonical authority.
3. **Magic-byte + Pillow decode** — runs inside
   :func:`app.services.photos.process_and_save`, which raises
   :class:`PhotoRejected` on any of: bad magic, Pillow decode failure,
   decompression bomb. The router catches and re-renders the upload zone
   with the friendly message verbatim from the exception.

All four photo-pipeline rejection branches collapse to **HTTP 200 +
``fragments/photo_upload_zone.html``** with an ``error`` context key.
HTMX swaps the body regardless of status code; 200 keeps the
``htmx:responseError`` event chain quiet (D-04).

Form-validation re-render (CAT-08 + SEC-06)
-------------------------------------------

Bag form errors mirror the roasters pattern: catch
:class:`pydantic.ValidationError`, ``errors_by_field``, normalize
unknown keys into the ``_form`` sentinel, re-render the form fragment
at HTTP 200 with both ``values`` (preserved) and ``errors``.

Bag-row response shape
----------------------

Successful POST ``/coffees/{coffee_id}/bags`` returns the new bag row
fragment for the ``#bag-list`` mount, plus an out-of-band swap clearing
the ``#bag-form-mount`` div. Successful photo upload returns the
``fragments/photo_upload_zone.html`` fragment scoped to
``#bag-photo-zone-{bag_id}`` (only the upload zone re-renders to surface
the new thumbnail; the rest of the row is untouched).
"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.dependencies.auth import require_user
from app.dependencies.db import get_session
from app.models.user import User
from app.schemas.bag import BagCreate
from app.services import bags as bags_service
from app.services import coffees as coffees_service
from app.services import photos as photos_service
from app.services.form_validation import errors_by_field
from app.templates_setup import templates

router = APIRouter()

# Form keys that the bag form template renders error paragraphs for. Any
# ValidationError landing on a key outside this set folds into ``_form``
# via :func:`_normalize_errors` so the user still sees the error rendered.
_FORM_FIELDS = {
    "coffee_id",
    "roast_date",
    "weight_grams",
    "opened_at",
    "finished_at",
    "notes",
}

# Form keys where an empty form-string is semantically "no value" and must
# coerce to ``None`` before Pydantic validation. The bag schema's date /
# datetime / int fields reject the empty string; only ``notes`` legitimately
# accepts ``""`` (its default).
_EMPTY_TO_NONE_FIELDS = {
    "roast_date",
    "weight_grams",
    "opened_at",
    "finished_at",
}


def _coerce_empty_to_none(raw: dict[str, str]) -> dict[str, object]:
    """Map ``""`` → ``None`` for optional date/int fields whose schema rejects ``""``."""
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
        existing = normalized.get("_form")
        combined = (
            "; ".join(leftovers) if existing is None else f"{existing}; {'; '.join(leftovers)}"
        )
        normalized["_form"] = combined
    return normalized


# --------------------------------------------------------------------------- #
# Create — GET form + POST                                                    #
# --------------------------------------------------------------------------- #


@router.get("/coffees/{coffee_id}/bags/new", response_class=HTMLResponse)
def new_bag_form(
    coffee_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008 — FastAPI canonical Form 1.
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Empty bag form fragment. 404 when the coffee doesn't exist."""
    coffee = coffees_service.get_coffee(db, coffee_id=coffee_id)
    if coffee is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request=request,
        name="fragments/bag_form.html",
        context={
            "values": {},
            "errors": {},
            "mode": "create",
            "coffee_id": coffee_id,
        },
    )


@router.post("/coffees/{coffee_id}/bags", response_class=HTMLResponse)
async def create_bag_handler(
    coffee_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Create a bag nested under the given coffee.

    Raw-form-read pattern (T-04-MASS): unknown fields reach the Pydantic
    schema and trip ``extra='forbid'``. Validation errors → 200 + form
    re-render with the user's submitted text preserved (D-04). The
    coffee_id from the URL path is the source of truth; any
    user-submitted ``coffee_id`` form field is discarded to prevent a
    mismatch attack.
    """
    coffee = coffees_service.get_coffee(db, coffee_id=coffee_id)
    if coffee is None:
        raise HTTPException(status_code=404)

    form_data = await request.form()
    # Filter out the CSRF substrate + the user-submitted coffee_id field
    # (the URL path is authoritative).
    skip = {"X-CSRF-Token", "coffee_id"}
    raw = {k: v for k, v in form_data.items() if k not in skip}
    coerced = _coerce_empty_to_none(raw)
    # The URL path is the source of truth for coffee_id — re-inject so
    # the schema sees it on every request.
    coerced["coffee_id"] = coffee_id

    try:
        form = BagCreate(**coerced)
    except ValidationError as exc:
        # Preserve the user's submitted text on re-render (D-04). The
        # ``raw`` dict (not ``coerced``) holds the original strings so
        # an empty weight_grams stays "" rather than echoing "None".
        return templates.TemplateResponse(
            request=request,
            name="fragments/bag_form.html",
            context={
                "values": raw,
                "errors": _normalize_errors(errors_by_field(exc)),
                "mode": "create",
                "coffee_id": coffee_id,
            },
            status_code=200,
        )

    bag = bags_service.create_bag(
        db,
        coffee_id=form.coffee_id,
        roast_date=form.roast_date,
        weight_grams=form.weight_grams,
        opened_at=form.opened_at,
        finished_at=form.finished_at,
        notes=form.notes,
        by_user_id=user.id,
    )

    return templates.TemplateResponse(
        request=request,
        name="fragments/bag_row.html",
        context={
            "bag": bag,
            "include_oob_form_clear": True,
        },
    )


# --------------------------------------------------------------------------- #
# Edit — GET form + POST update                                               #
# --------------------------------------------------------------------------- #


@router.get("/bags/{bag_id}/edit", response_class=HTMLResponse)
def edit_bag_form(
    bag_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Pre-populated bag form fragment for inline edit (swaps the row)."""
    bag = bags_service.get_bag(db, bag_id=bag_id)
    if bag is None:
        raise HTTPException(status_code=404)
    values = {
        "roast_date": bag.roast_date.isoformat() if bag.roast_date else "",
        "weight_grams": str(bag.weight_grams) if bag.weight_grams is not None else "",
        # datetime-local needs YYYY-MM-DDTHH:MM (no seconds, no tz).
        "opened_at": (bag.opened_at.strftime("%Y-%m-%dT%H:%M") if bag.opened_at else ""),
        "finished_at": (bag.finished_at.strftime("%Y-%m-%dT%H:%M") if bag.finished_at else ""),
        "notes": bag.notes or "",
    }
    return templates.TemplateResponse(
        request=request,
        name="fragments/bag_form.html",
        context={
            "values": values,
            "errors": {},
            "mode": "edit",
            "bag_id": bag_id,
            "coffee_id": bag.coffee_id,
        },
    )


@router.post("/bags/{bag_id}", response_class=HTMLResponse)
async def update_bag_handler(
    bag_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Update a bag. Validation errors → 200 + form re-render (D-04)."""
    existing = bags_service.get_bag(db, bag_id=bag_id)
    if existing is None:
        raise HTTPException(status_code=404)

    form_data = await request.form()
    skip = {"X-CSRF-Token", "coffee_id"}
    raw = {k: v for k, v in form_data.items() if k not in skip}
    coerced = _coerce_empty_to_none(raw)
    coerced["coffee_id"] = existing.coffee_id

    try:
        form = BagCreate(**coerced)
    except ValidationError as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/bag_form.html",
            context={
                "values": raw,
                "errors": _normalize_errors(errors_by_field(exc)),
                "mode": "edit",
                "bag_id": bag_id,
                "coffee_id": existing.coffee_id,
            },
            status_code=200,
        )

    bag = bags_service.update_bag(
        db,
        bag_id=bag_id,
        roast_date=form.roast_date,
        weight_grams=form.weight_grams,
        opened_at=form.opened_at,
        finished_at=form.finished_at,
        notes=form.notes,
        by_user_id=user.id,
    )
    return templates.TemplateResponse(
        request=request,
        name="fragments/bag_row.html",
        context={"bag": bag},
    )


# --------------------------------------------------------------------------- #
# Archive                                                                     #
# --------------------------------------------------------------------------- #


@router.post("/bags/{bag_id}/archive", response_class=HTMLResponse)
def archive_bag_handler(
    bag_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Mark a bag finished — the Phase 4 archive surrogate.

    Locked semantic: bags have no ``archived`` column; ``finished_at IS
    NOT NULL`` is the archive surrogate. The handler stamps
    ``finished_at = func.now()`` and re-renders the bag row so the
    "Mark finished" affordance disappears.
    """
    existing = bags_service.get_bag(db, bag_id=bag_id)
    if existing is None:
        raise HTTPException(status_code=404)
    bags_service.archive_bag(db, bag_id=bag_id, by_user_id=user.id)
    bag = bags_service.get_bag(db, bag_id=bag_id)
    return templates.TemplateResponse(
        request=request,
        name="fragments/bag_row.html",
        context={"bag": bag},
    )


# --------------------------------------------------------------------------- #
# Photo upload + delete                                                       #
# --------------------------------------------------------------------------- #


def _zone_response(
    request: Request,
    bag,  # noqa: ANN001 — Bag model imported through bags_service
    error: str | None = None,
    *,
    status_code: int = 200,
) -> Response:
    """Render ``fragments/photo_upload_zone.html`` with optional error.

    All photo-upload error paths funnel through this helper so the
    response shape is uniform (T-04-DOS oversize, T-04-POLY magic-byte
    reject, decompression-bomb / decode failure all share the same
    ``error=...`` re-render).
    """
    return templates.TemplateResponse(
        request=request,
        name="fragments/photo_upload_zone.html",
        context={"bag": bag, "error": error},
        status_code=status_code,
    )


@router.post("/bags/{bag_id}/photo", response_class=HTMLResponse)
async def upload_photo(
    bag_id: int,
    request: Request,
    photo: UploadFile = File(...),  # noqa: B008
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Multipart photo upload. All rejections → 200 + zone re-render.

    Defense-in-depth order:

    1. ``bag_id`` lookup → 404 if missing.
    2. Content-Length pre-check (cheap; before body is read).
    3. ``await photo.read()`` then post-read len check (some clients
       skip Content-Length).
    4. :func:`app.services.bags.attach_or_replace_photo` →
       :func:`app.services.photos.process_and_save` does magic-byte +
       Pillow decode + re-encode + EXIF strip. Any rejection raises
       :class:`PhotoRejected` and the router renders the friendly
       message in the upload zone.

    Success path: the upload zone re-renders with the new thumbnail
    visible (template branches on ``bag.photo_filename``); no full row
    re-render is needed.
    """
    bag = bags_service.get_bag(db, bag_id=bag_id)
    if bag is None:
        raise HTTPException(status_code=404)

    # Step 1: Content-Length pre-check (cheap). Some clients omit the
    # header — fall through to the post-read len check below.
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > photos_service.MAX_BYTES:
        return _zone_response(request, bag, error="Photo too large (max 5MB).")

    # Step 2: read the body + post-read size check.
    raw = await photo.read()
    if len(raw) > photos_service.MAX_BYTES:
        return _zone_response(request, bag, error="Photo too large (max 5MB).")
    if len(raw) == 0:
        return _zone_response(request, bag, error="No file uploaded.")

    # Step 3: hand to the service. PhotoRejected covers bad magic,
    # decode failure, decompression bomb — all surface as a 200 +
    # zone re-render with the friendly message verbatim.
    try:
        bag = bags_service.attach_or_replace_photo(db, bag_id=bag_id, blob=raw, by_user_id=user.id)
    except photos_service.PhotoRejected as exc:
        return _zone_response(request, bag, error=str(exc))

    return _zone_response(request, bag)


@router.post("/bags/{bag_id}/photo/delete", response_class=HTMLResponse)
def delete_photo_handler(
    bag_id: int,
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """Delete the bag's photo. Re-renders the upload zone (no thumbnail)."""
    bag = bags_service.get_bag(db, bag_id=bag_id)
    if bag is None:
        raise HTTPException(status_code=404)
    bag = bags_service.delete_photo(db, bag_id=bag_id, by_user_id=user.id)
    return _zone_response(request, bag)


# Silence unused-import linting: imports kept for forward type hints in
# the service kwargs (`roast_date`, `opened_at`).
_ = date
_ = datetime


__all__ = ["router"]
