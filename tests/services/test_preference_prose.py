"""Wave 0 schema tests for Phase 19 PreferenceProfileProseSchema.

Requirements traceability:
  AIX-09 — PreferenceProfileProseSchema has a single summary_prose field
            with extra=forbid
"""

from __future__ import annotations

import pytest


def test_preference_prose_schema() -> None:
    """AIX-09: PreferenceProfileProseSchema validates and rejects extra fields."""
    from pydantic import ValidationError

    from app.services.ai_schemas import PreferenceProfileProseSchema

    # Valid
    result = PreferenceProfileProseSchema(
        summary_prose=(
            "You consistently reach for washed Ethiopians and Colombian naturals, "
            "rating them highest when brewed at 94–96°C with a 1:15 ratio. "
            "Your preference for bright acidity and floral aromatics is clear."
        )
    )
    assert result.summary_prose != ""

    # extra=forbid: injected field raises ValidationError (T-19-01)
    with pytest.raises(ValidationError):
        PreferenceProfileProseSchema(
            summary_prose="Some prose.",
            injected_field="malicious value",
        )

    # Missing required field
    with pytest.raises(ValidationError):
        PreferenceProfileProseSchema()  # type: ignore[call-arg]
