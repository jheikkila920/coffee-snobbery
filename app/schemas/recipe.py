"""Pydantic v2 form schemas for /recipes — SEC-06 universal validation pattern.

Two classes:

* ``StepSchema`` — one entry in the JSONB ``recipes.steps`` array
  (water_grams ge=0 le=2000, time_seconds ge=0 le=3600, label max=80 per
  Phase 4 CONTEXT ``<specifics>`` + D-10).
* ``RecipeCreate`` — top-level form (UI-SPEC + D-09).

Validation rules (numeric SEC-06):

* ``dose_grams``: 1-200 grams.
* ``water_grams``: 1-3000 grams.
* ``water_temp_c``: 0-100 °C (matches ROADMAP Phase 4 success criterion #5
  verbatim: "temp 0–100°C").
* ``grind_setting``: free-form text per CAT-06; max 200 chars.
* ``steps``: list of ``StepSchema`` (each step ranges validated independently).

D-09 — submit convention
------------------------
The step-builder is a CSP-build Alpine component. On form submit the local
``steps`` array is serialised into a hidden ``<input name="steps" value="...">``
as JSON. The router parses the string via ``json.loads(steps_str)`` BEFORE
constructing ``RecipeCreate(...)``, or uses ``RecipeCreate.model_validate_json``
to do both in one step. ValidationError inside any step → 200 + form-fragment
re-render with the offending step highlighted (UI-SPEC).

Mass-assignment defense (T-04-MASS): ``ConfigDict(extra="forbid")`` on both
classes rejects any field not declared.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StepSchema(BaseModel):
    """One step in a recipe's JSONB ``steps`` array (D-10)."""

    model_config = ConfigDict(extra="forbid")

    water_grams: int = Field(..., ge=0, le=2000)
    time_seconds: int = Field(..., ge=0, le=3600)
    label: str = Field("", max_length=80)


class RecipeCreate(BaseModel):
    """Recipe form. Validation errors → 200 + form-fragment re-render (D-04)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=200)
    dose_grams: int = Field(..., ge=1, le=200)
    water_grams: int = Field(..., ge=1, le=3000)
    water_temp_c: int = Field(..., ge=0, le=100)
    grind_setting: str = Field("", max_length=200)
    steps: list[StepSchema] = Field(default_factory=list)


__all__ = ["RecipeCreate", "StepSchema"]
