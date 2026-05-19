"""Pydantic v2 form schema for /equipment — SEC-06 universal validation pattern.

One class:

* ``EquipmentCreate`` — used by the inline create-form fragment on
  ``/equipment``.

Validation rules:

* ``type``: required; must match the 6-value enum from CAT-05
  (text+CHECK precedent from Phase 3 D-01). Regex acts as defense-in-depth
  alongside the DB check.
* ``brand`` / ``model``: required, 1-200 chars each.
* ``notes``: optional, default empty string; max 4000 chars.

Mass-assignment defense (T-04-MASS): ``ConfigDict(extra="forbid")`` rejects
any field not declared above.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EquipmentCreate(BaseModel):
    """Equipment form. Validation errors → 200 + form-fragment re-render (D-04)."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(
        ...,
        pattern=r"^(brewer|grinder|kettle|scale|water_filter|other)$",
    )
    brand: str = Field(..., min_length=1, max_length=200)
    model: str = Field(..., min_length=1, max_length=200)
    notes: str = Field("", max_length=4000)


__all__ = ["EquipmentCreate"]
