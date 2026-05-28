"""Wave 0 schema tests for Phase 19 BrewImproveSchema + BrewParameterChangeSchema.

Requirements traceability:
  AIX-12 — BrewImproveSchema + BrewParameterChangeSchema validate and reject
            extra fields; parameter Literal enforced
"""

from __future__ import annotations

import pytest


def test_brew_improve_schema() -> None:
    """AIX-12: BrewImproveSchema validates; parameter Literal enforced; extra rejected."""
    from pydantic import ValidationError

    from app.services.ai_schemas import BrewImproveSchema, BrewParameterChangeSchema

    # Valid BrewParameterChangeSchema
    change = BrewParameterChangeSchema(
        parameter="grind",
        suggested_value="medium-fine (~20 clicks Encore)",
        rationale="Your last session's sour notes suggest under-extraction.",
    )
    assert change.parameter == "grind"

    # All valid parameter literals
    for param in ("grind", "ratio", "temp_c", "brewer", "recipe"):
        c = BrewParameterChangeSchema(
            parameter=param,
            suggested_value="some value",
            rationale="Some rationale.",
        )
        assert c.parameter == param

    # Invalid parameter literal
    with pytest.raises(ValidationError):
        BrewParameterChangeSchema(
            parameter="water_volume",  # type: ignore[arg-type]
            suggested_value="300g",
            rationale="Not a valid parameter.",
        )

    # extra=forbid on BrewParameterChangeSchema (T-19-01)
    with pytest.raises(ValidationError):
        BrewParameterChangeSchema(
            parameter="grind",
            suggested_value="coarser",
            rationale="Bitter notes.",
            injected_field="malicious",
        )

    # Valid BrewImproveSchema
    result = BrewImproveSchema(
        summary_prose="Your grind is too fine for this Ethiopia. Back off 2 clicks.",
        unchanged_parameters=["ratio", "temp_c"],
        next_try=[
            BrewParameterChangeSchema(
                parameter="grind",
                suggested_value="2 clicks coarser",
                rationale="Bitter/dry finish indicates over-extraction.",
            )
        ],
    )
    assert result.summary_prose != ""
    assert "ratio" in result.unchanged_parameters
    assert len(result.next_try) == 1
    assert result.next_try[0].parameter == "grind"

    # empty next_try is valid
    BrewImproveSchema(
        summary_prose="Your brew looks dialed in.",
        unchanged_parameters=[],
        next_try=[],
    )

    # extra=forbid on BrewImproveSchema (T-19-01)
    with pytest.raises(ValidationError):
        BrewImproveSchema(
            summary_prose="Some coaching.",
            unchanged_parameters=[],
            next_try=[],
            injected_field="bad",
        )


# ---------------------------------------------------------------------------
# Placeholder for prior-sessions loading test (filled in 19-04)
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="filled in 19-04: prior brew sessions loaded for improve-brew context")
def test_prior_sessions_loaded_for_improve_brew() -> None:
    pass
