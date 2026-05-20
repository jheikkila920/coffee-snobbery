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
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Max value representable by the GENERATED ``extraction_yield_pct`` column
# (``numeric(5,2)`` → 999.99). The DB computes EY exactly as below; if the
# computed value exceeds this the INSERT raises "numeric field overflow" and
# would surface as an unhandled 500 (CR-02). Validate the combo up front so the
# error routes through ValidationError → friendly form re-render / per-row CSV
# refusal instead.
_EY_MAX = Decimal("999.99")


def validate_extraction_yield(
    *,
    dose_grams_actual: Decimal | None,
    yield_grams_actual: Decimal | None,
    tds_pct: Decimal | None,
) -> None:
    """Reject dose/yield/tds combos whose computed EY overflows numeric(5,2).

    Mirrors the GENERATED column expression exactly (tds is whole-percent):
    ``EY = (yield * tds / 100) / dose * 100``. Only checks when all three
    operands are present and ``dose > 0`` (any NULL operand → EY is NULL in the
    DB, no overflow). Raises ``ValueError`` (→ pydantic ``ValidationError``)
    when EY would exceed 999.99 or be negative. Shared by the form schema and
    the CSV-row schema so both import paths refuse the overflow identically.
    """
    if dose_grams_actual is None or yield_grams_actual is None or tds_pct is None:
        return
    if dose_grams_actual <= 0:
        return  # field bounds already reject dose <= 0; avoid div-by-zero here
    ey = (yield_grams_actual * tds_pct / Decimal("100")) / dose_grams_actual * Decimal("100")
    if ey > _EY_MAX or ey < 0:
        msg = "extraction yield out of range for these dose/yield/TDS values"
        raise ValueError(msg)


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

    @model_validator(mode="after")
    def _reject_ey_overflow(self) -> Self:
        # CR-02: bound the COMPUTED extraction yield so a small-dose / large
        # yield+tds combo can't overflow the GENERATED numeric(5,2) column and
        # crash the INSERT with a 500. Routes through ValidationError → SEC-06
        # 200 form re-render instead.
        validate_extraction_yield(
            dose_grams_actual=self.dose_grams_actual,
            yield_grams_actual=self.yield_grams_actual,
            tds_pct=self.tds_pct,
        )
        return self


class BrewSessionUpdate(BrewSessionCreate):
    """Same shape as ``BrewSessionCreate`` at v1.

    The class split is intentional: keeping the names distinct lets a future
    Update path diverge from Create (e.g. drop required fields for a PATCH-style
    edit) without churning Create call sites.
    """


__all__ = ["BrewSessionCreate", "BrewSessionUpdate"]
