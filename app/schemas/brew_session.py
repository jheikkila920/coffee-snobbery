"""Pydantic v2 form schemas for /brew — SEC-06 universal validation pattern.

Two classes:

* ``BrewSessionCreate`` — the brew-log form field set.
* ``BrewSessionUpdate(BrewSessionCreate)`` — same shape today; the class split
  lets a future Update path diverge without churning Create call sites
  (matches the ``CoffeeCreate`` / ``CoffeeUpdate`` convention).

Validation rules (numeric SEC-06 ranges):

* ``rating``: ``Decimal`` (NOT float — Pitfall 2: float rounding admits/rejects
  the wrong quarter values), 0-5 in 0.25 steps via ``multiple_of=Decimal("0.25")``.
* ``dose_grams_actual``: 0 < x <= 200.
* ``water_grams_actual``: 0 < x <= 3000.
* ``yield_grams_actual``: 0 <= x <= 3000 (D-02 advanced refractometer field).
* ``tds_pct``: 0 <= x <= 100 (whole percent per Task 0).
* ``water_temp_c_actual``: 0-100 °C.
* ``flavor_note_ids_observed``: list of FK ids (each >= 1).

Mass-assignment / Tampering defense (T-05-01, T-04-MASS): ``ConfigDict(
extra="forbid")`` rejects any field not declared — a posted
``extraction_yield_pct`` or ``user_id`` raises ``ValidationError`` rather than
being silently dropped. Two fields are deliberately ABSENT:

* ``extraction_yield_pct`` — GENERATED in Postgres, render-only (RESEARCH
  anti-pattern). Never app-written.
* ``user_id`` — the server sets it from ``request.state.user.id`` (the router),
  never the client.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BrewSessionCreate(BaseModel):
    """Brew-log form. Validation errors → 200 + form re-render (SEC-06 / D-04)."""

    model_config = ConfigDict(extra="forbid")

    # --- references (user_id is server-set, NOT a field) ------------------
    coffee_id: int = Field(..., ge=1)
    bag_id: int | None = Field(None, ge=1)
    recipe_id: int | None = Field(None, ge=1)
    brewer_id: int | None = Field(None, ge=1)
    grinder_id: int | None = Field(None, ge=1)
    kettle_id: int | None = Field(None, ge=1)

    # --- brew parameters --------------------------------------------------
    water_type: str = Field("", max_length=100)
    dose_grams_actual: Decimal = Field(..., gt=0, le=200)
    water_grams_actual: Decimal = Field(..., gt=0, le=3000)
    yield_grams_actual: Decimal | None = Field(None, ge=0, le=3000)
    tds_pct: Decimal | None = Field(None, ge=0, le=100)
    water_temp_c_actual: Decimal | None = Field(None, ge=0, le=100)
    grind_setting_actual: str = Field("", max_length=200)
    # Decimal (NOT float) so 0.25 quarter-steps validate exactly (Pitfall 2).
    rating: Decimal | None = Field(None, ge=0, le=5, multiple_of=Decimal("0.25"))
    flavor_note_ids_observed: list[int] = Field(default_factory=list)
    notes: str = Field("", max_length=5000)

    # --- timing -----------------------------------------------------------
    # Server stores tz-aware UTC; a None default lets the column server_default
    # (now()) apply when the form omits an explicit brewed_at.
    brewed_at: datetime | None = None

    @field_validator("flavor_note_ids_observed")
    @classmethod
    def _all_ids_positive(cls, v: list[int]) -> list[int]:
        if not all(i >= 1 for i in v):
            msg = "flavor_note_ids_observed must be positive integers (>= 1)"
            raise ValueError(msg)
        return v


class BrewSessionUpdate(BrewSessionCreate):
    """Same shape as ``BrewSessionCreate`` at v1.

    The class split is intentional: keeping the names distinct lets a future
    Update path diverge from Create (e.g. drop required fields for a PATCH-style
    edit) without churning Create call sites.
    """


__all__ = ["BrewSessionCreate", "BrewSessionUpdate"]
