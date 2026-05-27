"""Pydantic v2 per-row schema for CSV brew import (BREW-11).

Mirrors ``app/schemas/recipe.py::StepSchema`` — a focused per-row model with
``extra="forbid"`` and per-field numeric ranges. The CSV importer (Plan 03's
``app/services/csv_io.py``) validates each parsed row against this schema BEFORE
resolving names → ids and inserting; a row that fails validation is refused with
the field error rather than aborting the whole import.

Name fields (``coffee_name``, ``roaster_name``, ``brewer``, ``grinder``,
``kettle``) stay as RAW STRINGS here. Id resolution (citext match against the
shared catalog, D-12 coffee match, ambiguity → refused row) is the importer's
job, not the schema's — keeping it out of the schema lets the importer build a
precise per-row refusal reason ("coffee not in catalog").

The ``rating`` constraint is identical to ``BrewSessionCreate``: ``Decimal``
(NOT float — Pitfall 2), 0-5 in 0.25 steps. ``extraction_yield_pct`` is NOT a
field — it is GENERATED on insert from the imported dose/yield/tds.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.brew_session import validate_extraction_yield


class BrewCsvRow(BaseModel):
    """One parsed CSV row awaiting name→id resolution + insert (BREW-11)."""

    model_config = ConfigDict(extra="forbid")

    # --- name fields (resolved to ids by csv_io, Plan 03) ----------------
    coffee_name: str = Field(..., min_length=1, max_length=200)
    roaster_name: str = Field("", max_length=200)
    brewer: str = Field("", max_length=200)
    grinder: str = Field("", max_length=200)
    kettle: str = Field("", max_length=200)

    # --- brew parameters (same ranges as BrewSessionCreate) --------------
    water_type: str = Field("", max_length=100)
    dose_grams_actual: Decimal = Field(..., gt=0, le=200)
    water_grams_actual: Decimal = Field(..., gt=0, le=3000)
    yield_grams_actual: Decimal | None = Field(None, ge=0, le=3000)
    tds_pct: Decimal | None = Field(None, ge=0, le=100)
    water_temp_c_actual: Decimal | None = Field(None, ge=0, le=100)
    grind_setting_actual: str = Field("", max_length=200)
    # Decimal (NOT float) so 0.25 quarter-steps validate exactly (Pitfall 2).
    rating: Decimal | None = Field(None, ge=0, le=5, multiple_of=Decimal("0.25"))
    notes: str = Field("", max_length=5000)

    @model_validator(mode="after")
    def _reject_ey_overflow(self) -> Self:
        # CR-02: same EY-overflow guard as BrewSessionCreate so an imported row
        # whose dose/yield/TDS would overflow the GENERATED numeric(5,2) column
        # is refused per-row (ValidationError) instead of crashing the import
        # with an unhandled 500.
        validate_extraction_yield(
            dose_grams_actual=self.dose_grams_actual,
            yield_grams_actual=self.yield_grams_actual,
            tds_pct=self.tds_pct,
        )
        return self


__all__ = ["BrewCsvRow"]
