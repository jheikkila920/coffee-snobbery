"""Wave 0 schema tests for Phase 19 AI research schemas.

Tests in this file:
  - test_coffee_research_schema_validates  (Task 1 / AIX-01)
  - test_rating_prediction_schema          (Task 1 / D-02)
  - Skipped placeholders for cache/SSE/quota tests (filled in 19-03)

Requirements traceability:
  AIX-01 — CoffeeResearchSchema validates and rejects extra fields
  D-02   — RatingPredictionSchema carries range + confidence, never single number
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Schema validation tests (Task 1 — Wave 0)
# ---------------------------------------------------------------------------


def test_coffee_research_schema_validates() -> None:
    """AIX-01: CoffeeResearchSchema validates a complete payload and rejects extra fields."""
    from pydantic import ValidationError

    from app.services.ai_schemas import CoffeeResearchSchema

    # Valid complete payload
    result = CoffeeResearchSchema(
        coffee_name="Yirgacheffe Kochere",
        roaster_name="Counter Culture",
        origin="Ethiopia",
        process="Washed",
        roast_level="Light",
        tasting_notes=["jasmine", "bergamot", "lemon curd"],
        buy_url="https://counterculturecoffee.com/yirgacheffe",
        sources=["https://counterculturecoffee.com"],
        summary_prose="A bright, floral Yirgacheffe with classic bergamot and citrus notes.",
    )
    assert result.coffee_name == "Yirgacheffe Kochere"
    assert result.roaster_name == "Counter Culture"
    assert result.origin == "Ethiopia"
    assert len(result.tasting_notes) == 3
    assert result.buy_url is not None
    assert len(result.sources) == 1
    assert result.summary_prose != ""

    # Minimal payload (optional fields null/empty)
    minimal = CoffeeResearchSchema(
        coffee_name="Mystery Coffee",
        summary_prose="A mysterious coffee.",
    )
    assert minimal.roaster_name is None
    assert minimal.origin is None
    assert minimal.process is None
    assert minimal.roast_level is None
    assert minimal.tasting_notes == []
    assert minimal.buy_url is None
    assert minimal.sources == []

    # extra=forbid: injected field raises ValidationError (T-19-01 prompt-injection defence)
    with pytest.raises(ValidationError):
        CoffeeResearchSchema(
            coffee_name="Injected Coffee",
            summary_prose="Some prose.",
            injected_field="malicious value",
        )


def test_rating_prediction_schema() -> None:
    """D-02: RatingPredictionSchema carries range + confidence, never single number."""
    from pydantic import ValidationError

    from app.services.ai_schemas import RatingPredictionSchema

    # Valid range
    result = RatingPredictionSchema(
        predicted_low=3.5,
        predicted_high=4.25,
        confidence="High",
        reasoning="Strong flavor alignment with your Ethiopia preference.",
    )
    assert result.predicted_low == 3.5
    assert result.predicted_high == 4.25
    assert result.confidence == "High"
    assert result.reasoning != ""

    # All confidence levels valid
    for conf in ("Low", "Medium", "High"):
        r = RatingPredictionSchema(
            predicted_low=2.0,
            predicted_high=3.5,
            confidence=conf,
            reasoning="Some reasoning.",
        )
        assert r.confidence == conf

    # Boundary: 0.0 and 5.0 are valid
    RatingPredictionSchema(
        predicted_low=0.0,
        predicted_high=5.0,
        confidence="Low",
        reasoning="Full range.",
    )

    # Out-of-range predicted_low
    with pytest.raises(ValidationError):
        RatingPredictionSchema(
            predicted_low=-0.1,
            predicted_high=4.0,
            confidence="Medium",
            reasoning="Invalid low.",
        )

    # Out-of-range predicted_high
    with pytest.raises(ValidationError):
        RatingPredictionSchema(
            predicted_low=3.0,
            predicted_high=5.1,
            confidence="Medium",
            reasoning="Invalid high.",
        )

    # Invalid confidence literal
    with pytest.raises(ValidationError):
        RatingPredictionSchema(
            predicted_low=3.0,
            predicted_high=4.0,
            confidence="VeryHigh",  # type: ignore[arg-type]
            reasoning="Bad confidence.",
        )

    # extra=forbid
    with pytest.raises(ValidationError):
        RatingPredictionSchema(
            predicted_low=3.0,
            predicted_high=4.0,
            confidence="Medium",
            reasoning="Some reasoning.",
            extra_field="injected",
        )


# ---------------------------------------------------------------------------
# Placeholders for cache/SSE/quota tests (filled in 19-03)
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="filled in 19-03: cache key normalization service")
def test_cache_key_normalization() -> None:
    pass


@pytest.mark.skip(reason="filled in 19-03: lazy expired cache row eviction")
def test_expired_cache_eviction() -> None:
    pass


@pytest.mark.skip(reason="filled in 19-03: cache miss triggers LLM call")
def test_cache_miss_calls_llm() -> None:
    pass


@pytest.mark.skip(reason="filled in 19-03: cache hit skips LLM call")
def test_cache_hit_skips_llm() -> None:
    pass


@pytest.mark.skip(reason="filled in 19-03: SSE event contract (message/complete/error)")
def test_sse_event_contract() -> None:
    pass


@pytest.mark.skip(reason="filled in 19-03: advisory lock prevents duplicate charge on reconnect")
def test_advisory_lock_blocks_duplicate() -> None:
    pass


@pytest.mark.skip(reason="filled in 19-03: duration_ms written to ai_recommendations row")
def test_duration_ms_written() -> None:
    pass
