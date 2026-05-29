"""Wave 0 contract tests for GBREW-06 StepSchema extension (Phase 20, Plan 01).

These tests assert the LOCKED schema shape AFTER the extension migration in
Plan 20-02. They are EXPECTED to fail RED until Plan 20-02 adds:
  - StepSchema.type (str literal: "Bloom" | "Pour" | "Wait" | "Action")
  - StepSchema.water_temp_c (Optional[int], ge=50, le=100)
  - StepSchema.note (Optional[str], max_length=200)
  - StepSchema.water_grams becomes Optional[int] (to allow Wait steps with no water)

Requirement traceability:
  GBREW-06 (D-04, D-05, D-06, D-07, D-09)

No pytest.skip for missing data — these tests fail RED now and turn GREEN in
Wave 1 when Plan 20-02 lands the schema extension.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_backward_compat_no_type() -> None:
    """D-04 / A3: old step dicts without `type` still validate after extension.

    An existing JSONB row: {"water_grams": 100, "time_seconds": 45, "label": "Bloom"}
    must still validate without error. The extended schema must supply a default
    for `type` rather than requiring it, so historical data survives the extension.

    Expected post-Plan-20-02 behavior: .type defaults to "Pour" (the most common
    step type and a safe default-at-read — no DB backfill needed).
    """
    from app.schemas.recipe import StepSchema

    old_dict = {"water_grams": 100, "time_seconds": 45, "label": "Bloom"}
    step = StepSchema.model_validate(old_dict)
    # type must default to "Pour" when absent (D-04 backward-compat, no backfill)
    assert step.type == "Pour"  # type: ignore[attr-defined]
    assert step.water_grams == 100
    assert step.time_seconds == 45
    assert step.label == "Bloom"


def test_wait_step_no_water() -> None:
    """D-07 / GBREW-06: Wait step validates with water_grams=None.

    After the extension, water_grams becomes Optional so timed actions (Wait,
    Action) do not require specifying a pour target.
    """
    from app.schemas.recipe import StepSchema

    step = StepSchema(type="Wait", time_seconds=30, label="Drawdown")  # type: ignore[call-arg]
    assert step.water_grams is None


def test_step_water_temp_range() -> None:
    """D-06 / GBREW-06: per-step water_temp_c must be in [50, 100] °C.

    - 94 °C (typical pour-over) → valid
    - 49 °C (below minimum) → ValidationError
    - 101 °C (above maximum) → ValidationError
    """
    from app.schemas.recipe import StepSchema

    # Valid: 94 °C is a common pour-over temperature
    step = StepSchema(  # type: ignore[call-arg]
        type="Pour",
        water_grams=150,
        time_seconds=30,
        label="Main pour",
        water_temp_c=94,
    )
    assert step.water_temp_c == 94  # type: ignore[attr-defined]

    # Too cold
    with pytest.raises(ValidationError):
        StepSchema(  # type: ignore[call-arg]
            type="Pour",
            water_grams=150,
            time_seconds=30,
            label="Too cold",
            water_temp_c=49,
        )

    # Too hot (steam)
    with pytest.raises(ValidationError):
        StepSchema(  # type: ignore[call-arg]
            type="Pour",
            water_grams=150,
            time_seconds=30,
            label="Too hot",
            water_temp_c=101,
        )


def test_coaching_line_by_type() -> None:
    """D-09: data contract invariants that drive the JS coachingLine per step type.

    The coaching string itself is composed in Alpine JS (client-side, manually
    verified). This test pins the SERVER-SIDE data contract the JS reads:
    - A Bloom step preserves type="Bloom" and has a water target (water_grams).
    - A Pour step preserves type="Pour" with cumulative water_grams target.
    - A Wait step accepts water_grams=None (no pour target during drawdown).
    """
    from app.schemas.recipe import StepSchema

    # Bloom: has explicit type + water target
    bloom = StepSchema(  # type: ignore[call-arg]
        type="Bloom", water_grams=40, time_seconds=45, label="Bloom"
    )
    assert bloom.type == "Bloom"  # type: ignore[attr-defined]
    assert bloom.water_grams == 40

    # Pour: cumulative water target preserved
    pour = StepSchema(  # type: ignore[call-arg]
        type="Pour", water_grams=200, time_seconds=60, label="Main pour"
    )
    assert pour.type == "Pour"  # type: ignore[attr-defined]
    assert pour.water_grams == 200

    # Wait: no water target — JS coachingLine shows "Hold, drawdown" style prompt
    wait = StepSchema(type="Wait", time_seconds=120, label="Drawdown")  # type: ignore[call-arg]
    assert wait.type == "Wait"  # type: ignore[attr-defined]
    assert wait.water_grams is None


def test_extra_field_rejected() -> None:
    """T-V5 / T-20-01: ConfigDict(extra='forbid') still rejects unknown fields.

    Mass-assignment guard — an attacker posting an unknown field (e.g.
    `is_admin`, `user_id`) to a step must be rejected with ValidationError.
    """
    from app.schemas.recipe import StepSchema

    with pytest.raises(ValidationError):
        StepSchema(  # type: ignore[call-arg]
            type="Pour",
            water_grams=100,
            time_seconds=30,
            label="Pour",
            unknown_field="attacker_value",
        )


def test_recipe_roundtrip_wait_action() -> None:
    """GBREW-06 / Plan 20-04: round-trip for UI-produced step shapes.

    Builds a RecipeCreate-shaped steps list containing four step types and
    asserts that all new fields (type, note, water_temp_c, water_grams=None)
    survive StepSchema validation — proving the step-builder UI output
    persists correctly through the server-side schema.
    """
    from app.schemas.recipe import RecipeCreate, StepSchema

    steps = [
        StepSchema(  # type: ignore[call-arg]
            type="Bloom",
            water_grams=50,
            time_seconds=45,
            label="Bloom",
        ),
        StepSchema(  # type: ignore[call-arg]
            type="Pour",
            water_grams=150,
            time_seconds=90,
            label="Main pour",
            water_temp_c=94,
        ),
        StepSchema(  # type: ignore[call-arg]
            type="Wait",
            time_seconds=150,
            label="Drawdown",
        ),
        StepSchema(  # type: ignore[call-arg]
            type="Action",
            time_seconds=165,
            label="Open Switch",
            note="Hario Switch closed for immersion",
        ),
    ]

    recipe = RecipeCreate(
        name="Test Recipe",
        dose_grams=15,
        water_grams=250,
        water_temp_c=94,
        grind_setting="22 clicks",
        steps=steps,
    )

    assert len(recipe.steps) == 4

    # Bloom step: type preserved, has water_grams
    bloom = recipe.steps[0]
    assert bloom.type == "Bloom"
    assert bloom.water_grams == 50

    # Pour step: water_temp_c round-trips correctly
    pour = recipe.steps[1]
    assert pour.type == "Pour"
    assert pour.water_temp_c == 94

    # Wait step: water_grams is None (D-07 — no pour target for timed hold)
    wait = recipe.steps[2]
    assert wait.type == "Wait"
    assert wait.water_grams is None

    # Action step: note round-trips correctly (T-20-13 data contract)
    action = recipe.steps[3]
    assert action.type == "Action"
    assert action.note == "Hario Switch closed for immersion"
