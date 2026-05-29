"""Pydantic v2 form schema for /water-profiles — SEC-06 universal validation pattern.

One class:

* ``WaterProfileCreate`` — used by the inline create-form fragment and the
  Alpine waterProfileSelect component (brew_prefill_fields.html).

Validation rules:

* ``name``: required, 1-80 chars. Uniqueness enforced by DB UNIQUE constraint.
* ``notes``: optional, max 500 chars.

Mass-assignment defense (T-20-04): ``ConfigDict(extra="forbid")`` rejects
any field not declared above.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class WaterProfileCreate(BaseModel):
    """Water-profile inline-create form. Validation errors returned as JSON (422)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=80)
    notes: str | None = Field(None, max_length=500)


__all__ = ["WaterProfileCreate"]
