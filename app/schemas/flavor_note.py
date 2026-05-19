"""Pydantic v2 form schema for /flavor-notes — SEC-06 universal validation pattern.

One class:

* ``FlavorNoteCreate`` — used by the inline create-form fragment and by the
  D-15 "+ Create new flavor note" mini-modal flow (UI-SPEC §"Flavor-note
  mini-modal").

Validation rules:

* ``name``: required, 1-80 chars. CITEXT unique enforced by DB constraint.
* ``category``: required; must match the 9-value enum from CAT-02
  (text+CHECK precedent from Phase 3 D-01). Regex acts as defense-in-depth
  alongside the DB check.

Mass-assignment defense (T-04-MASS): ``ConfigDict(extra="forbid")`` rejects
any field not declared above.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FlavorNoteCreate(BaseModel):
    """Flavor-note form. Validation errors → 200 + form-fragment re-render (D-04)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=80)
    category: str = Field(
        ...,
        pattern=r"^(fruit|floral|sweet|chocolate|nutty|spice|savory|fermented|other)$",
    )


__all__ = ["FlavorNoteCreate"]
