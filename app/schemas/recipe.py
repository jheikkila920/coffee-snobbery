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

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StepSchema(BaseModel):
    """One step in a recipe's JSONB ``steps`` array (D-10, extended Phase 20).

    New fields (Phase 20 / GBREW-06) are all optional/defaulted so that old
    stored step dicts (lacking ``type``, ``note``, ``water_temp_c``) still
    validate without error — backward compatibility is critical (D-04, A3).

    * ``type``: step classification; defaults to ``"Pour"`` (most common step
      and a safe default-at-read; no DB backfill needed).
    * ``water_grams``: now Optional — Wait/Action steps do not pour (D-07).
    * ``note``: optional per-step coaching note, max 200 chars (D-05).
    * ``water_temp_c``: per-step target water temperature, 50-100 °C (D-06).
    """

    model_config = ConfigDict(extra="forbid")

    # Existing fields — water_grams is now Optional (D-07: Wait/Action steps)
    water_grams: int | None = Field(None, ge=0, le=2000)
    time_seconds: int = Field(..., ge=0, le=3600)
    label: str = Field("", max_length=80)

    # New fields (Phase 20 — all optional/defaulted for backward compat)
    type: Literal["Bloom", "Pour", "Wait", "Action"] = Field("Pour")
    note: str | None = Field(None, max_length=200)
    water_temp_c: int | None = Field(None, ge=50, le=100)


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
