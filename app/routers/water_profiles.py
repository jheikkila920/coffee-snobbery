"""Water profiles router — HTMX inline-create + list (GBREW-04, D-02).

Mirrors :mod:`app.routers.flavor_notes` — the universal Phase 4 catalog
template. Differences:

* URL prefix is ``/water-profiles``.
* POST always returns JSON errors (not an HTML fragment re-render) because
  the create form is Alpine-managed (waterProfileSelect component).
* No edit/archive/autocomplete endpoints — Phase 20 ships create + list only.

Endpoints
---------

* ``GET /water-profiles`` — list all profiles (JSON or HTML fragment).
* ``POST /water-profiles`` — create. Validation errors → 422 JSON.
  Success → empty body + ``HX-Trigger: water-profile-created`` header (D-02).

HX-Trigger payload (D-02)
--------------------------

POST ``/water-profiles`` on successful create returns an empty body + this
header::

    HX-Trigger: {"water-profile-created": {"water_profile_id": <int>, "name": <str>}}

Locked for ``waterProfileSelect`` Alpine component to consume (mirrors the
``flavor-note-created`` contract from plan 04-11).

CSRF compliance (T-20-03)
--------------------------
starlette-csrf middleware covers this router; the POST handler strips
``X-CSRF-Token`` from form data before Pydantic validation. The
``as_modal`` key is also stripped (UI bookkeeping, not a domain field).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.dependencies.auth import require_user
from app.dependencies.db import get_session
from app.models.user import User
from app.schemas.water_profile import WaterProfileCreate
from app.services import water_profiles as water_profiles_service
from app.services.form_validation import DuplicateNameError, errors_by_field
from app.templates_setup import templates

router = APIRouter(prefix="/water-profiles")


@router.get("", response_class=HTMLResponse)
def list_water_profiles(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008 — FastAPI canonical Form 1.
    db: Session = Depends(get_session),  # noqa: B008 — FastAPI canonical Form 1.
) -> Response:
    """List all water profiles. HTMX request → JSON list; full GET → JSON list.

    Returns a JSON array for the Alpine waterProfileSelect component to
    consume. Future plans may add an HTML list fragment variant.
    """
    profiles = water_profiles_service.list_water_profiles(db)
    return JSONResponse(
        [{"id": p.id, "name": p.name} for p in profiles]
    )


@router.post("", response_class=HTMLResponse)
async def create_water_profile(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008 — FastAPI canonical Form 1.
    db: Session = Depends(get_session),  # noqa: B008 — FastAPI canonical Form 1.
) -> Response:
    """Create a water profile. Validation errors → 422 JSON; success → HX-Trigger.

    Reads the raw form via ``await request.form()`` so unknown/mass-assignment
    fields reach the Pydantic schema and trip ``extra="forbid"`` (T-20-04).

    On success: returns empty fragment + HX-Trigger header (D-02). The
    ``water-profile-created`` event carries ``{water_profile_id, name}`` so
    the Alpine waterProfileSelect component can add the new profile to its list
    and select it without a page reload.
    """
    form_data = await request.form()
    # Strip CSRF token and UI bookkeeping keys before Pydantic validation.
    skip = {"X-CSRF-Token", "as_modal"}
    raw = {k: v for k, v in form_data.items() if k not in skip}

    try:
        form = WaterProfileCreate(**raw)
    except ValidationError as exc:
        return JSONResponse({"errors": errors_by_field(exc)}, status_code=422)

    try:
        profile = water_profiles_service.create_water_profile(
            db,
            name=form.name,
            notes=form.notes,
            by_user_id=user.id,
        )
    except DuplicateNameError:
        return JSONResponse(
            {"errors": {"name": "Profile name already exists."}},
            status_code=422,
        )

    # D-02 / HX-Trigger: empty body + event header. Locked contract for
    # waterProfileSelect Alpine component (mirrors flavor-note-created).
    response = templates.TemplateResponse(
        request=request,
        name="fragments/empty.html",
        context={},
    )
    response.headers["HX-Trigger"] = json.dumps(
        {
            "water-profile-created": {
                "water_profile_id": profile.id,
                "name": profile.name,
            }
        }
    )
    return response


__all__ = ["router"]
