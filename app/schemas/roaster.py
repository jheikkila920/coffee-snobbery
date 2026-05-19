"""Pydantic v2 form schema for /roasters — SEC-06 universal validation pattern.

One class:

* ``RoasterCreate`` — used by the inline create-form fragment and by the
  D-15 "+ Create new roaster" mini-modal flow (UI-SPEC §"Roaster mini-modal").

Validation rules:

* ``name``: required, 1-200 chars. CITEXT unique enforced by DB constraint.
* ``location``: optional, max 200 chars (free text — city/state/country).
* ``website``: optional, validated via Pydantic v2 ``HttpUrl`` (Phase 4
  PATTERNS line 426). Router stores ``str(form.website)`` in the
  ``roasters.website`` Text column.
* ``notes``: optional, default empty string; max 4000 chars.

Mass-assignment defense (T-04-MASS): ``ConfigDict(extra="forbid")`` rejects
any field not declared above.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class RoasterCreate(BaseModel):
    """Roaster form. Validation errors → 200 + form-fragment re-render (D-04)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=200)
    location: str | None = Field(None, max_length=200)
    website: HttpUrl | None = None
    notes: str = Field("", max_length=4000)


__all__ = ["RoasterCreate"]
