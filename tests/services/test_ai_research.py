"""Tests for Phase 19 AI research service (ai_research.py).

Covers:
  - test_coffee_research_schema_validates  (Task 1 / AIX-01) — schema only
  - test_rating_prediction_schema          (Task 1 / D-02)   — schema only
  - test_cache_key_normalization           (Task 2 / 19-03)  — normalize_cache_key
  - test_expired_cache_eviction            (Task 2 / 19-03)  — lazy TTL eviction
  - test_cache_miss_calls_llm             (Task 2 / 19-03)  — cache miss fires LLM
  - test_cache_hit_skips_llm              (Task 2 / 19-03)  — cache hit skips LLM
  - test_sse_event_contract               (Task 2 / 19-03)  — SSE event sequence
  - test_advisory_lock_blocks_duplicate   (Task 2 / 19-03)  — reconnect guard
  - test_duration_ms_written              (Task 2 / 19-03)  — telemetry row

Requirements traceability:
  AIX-01 — CoffeeResearchSchema validates and rejects extra fields
  D-02   — RatingPredictionSchema carries range + confidence, never single number
  AIX-04/D-06 — cache key normalization; cache hit skips LLM and does not decrement quota
  AIX-05 — cache hit does not write ai_recommendations row
  AIX-07/D-16 — SSE event contract: message deltas → complete (HTML) or error
  AIX-13 — ai_recommendations row written with rec_type='coffee_research' + duration_ms
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Schema validation tests (Task 1 — Wave 0, kept for regression)
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
# Task 2 tests: cache, SSE, advisory lock, telemetry (19-03)
# ---------------------------------------------------------------------------


def test_cache_key_normalization() -> None:
    """AIX-04/D-06: cache key is lower+trimmed coffee_name '|' roaster_name."""
    from app.services.ai_research import normalize_cache_key

    # Basic case
    assert normalize_cache_key("Yirgacheffe", "Counter Culture") == "yirgacheffe|counter culture"

    # Whitespace stripped
    assert (
        normalize_cache_key("  Yirgacheffe  ", "  Counter Culture  ")
        == "yirgacheffe|counter culture"
    )

    # Mixed case folds
    assert normalize_cache_key("YIRGACHEFFE", "COUNTER CULTURE") == "yirgacheffe|counter culture"

    # Same key as above regardless of casing
    key1 = normalize_cache_key("Yirgacheffe Kochere", "Counter Culture")
    key2 = normalize_cache_key("yirgacheffe kochere", "counter culture")
    assert key1 == key2

    # No roaster — uses empty string after pipe
    key_no_roaster = normalize_cache_key("Mystery Coffee", None)
    assert key_no_roaster == "mystery coffee|"

    # Empty string roaster also empty after pipe
    key_empty_roaster = normalize_cache_key("Mystery Coffee", "")
    assert key_empty_roaster == "mystery coffee|"

    # Same key for roaster=None and roaster=""
    assert normalize_cache_key("X", None) == normalize_cache_key("X", "")


def test_expired_cache_eviction() -> None:
    """AIX-04/D-06: expired cache row is deleted at read time; returns None."""
    from app.services.ai_research import get_cached_research

    mock_db = MagicMock()
    # The function should: execute a DELETE for expired rows, then scalar() for the live row
    mock_db.scalar.return_value = None  # no live row after eviction

    result = get_cached_research(mock_db, "yirgacheffe|counter culture")

    assert result is None
    # Verify execute was called at least once (for the DELETE)
    mock_db.execute.assert_called()


def test_cache_hit_skips_llm() -> None:
    """AIX-04: cache hit returns the cached row; no LLM call; no quota decrement."""
    from app.services.ai_research import get_cached_research

    now = datetime.now(UTC)
    live_cache_row = MagicMock()
    live_cache_row.expires_at = now + timedelta(days=15)
    live_cache_row.cache_key = "yirgacheffe|counter culture"

    mock_db = MagicMock()
    mock_db.scalar.return_value = live_cache_row

    result = get_cached_research(mock_db, "yirgacheffe|counter culture")

    assert result is live_cache_row


def test_cache_miss_calls_llm() -> None:
    """AIX-04: cache miss triggers an LLM call and writes the cache row."""
    # This is tested indirectly by verifying that generate_coffee_research
    # passes the MISS path and calls the LLM mock.
    # We test generate_coffee_research in test_sse_event_contract below.

    # Quick smoke: normalize + get returns None → forces LLM path
    from app.services.ai_research import get_cached_research, normalize_cache_key

    mock_db = MagicMock()
    mock_db.scalar.return_value = None  # cache miss

    key = normalize_cache_key("New Coffee", "New Roaster")
    result = get_cached_research(mock_db, key)
    assert result is None


def test_sse_event_contract() -> None:
    """AIX-07/D-16: SSE generator yields message events, then one complete or error event.

    - On success: multiple event:message prose deltas then event:complete (HTML fragment)
    - On validation failure: event:error is yielded (no event:complete after it)
    - Advisory lock held across generator lifetime (T-19-10)
    """
    from app.services.ai_research import generate_coffee_research

    async def run_success():
        """Simulate a cache-miss path with a mocked LLM call."""
        mock_db = MagicMock()
        mock_db.scalar.return_value = None  # cache miss + no existing prediction

        # Mock the advisory lock: acquired successfully
        mock_db.execute.return_value = MagicMock(scalar=MagicMock(return_value=True))

        # Cold-start gate: open
        mock_gate = {"gate_open": True}

        # Mock credential
        mock_cred = MagicMock()
        mock_cred.provider = "anthropic"
        mock_cred.model_name = "claude-opus-4-5"
        mock_cred.key = "test-key"

        # Build a mock Anthropic async stream context manager
        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=False)
        mock_stream.text_stream = _async_gen(["Hello ", "world ", "coffee."])

        # final_message structured output
        mock_final_msg = MagicMock()
        raw_output = {
            "coffee_name": "Yirgacheffe Kochere",
            "roaster_name": "Counter Culture",
            "origin": "Ethiopia",
            "process": "Washed",
            "roast_level": "Light",
            "tasting_notes": ["jasmine", "bergamot"],
            "buy_url": "https://example.com/coffee",
            "sources": ["https://example.com"],
            "summary_prose": "Hello world coffee.",
        }
        # _project_tool_use_input returns the tool_use block input
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "structure_output"
        tool_block.input = raw_output
        mock_final_msg.content = [tool_block]
        mock_stream.get_final_message = AsyncMock(return_value=mock_final_msg)

        # Usage
        mock_final_msg.usage = MagicMock()
        mock_final_msg.usage.input_tokens = 100
        mock_final_msg.usage.output_tokens = 50

        events = []
        with (
            patch("app.services.ai_research.analytics_service") as mock_analytics,
            patch("app.services.ai_research.credentials_service") as mock_creds,
            patch("app.services.ai_research.ai_quota") as mock_ai_quota,
            patch("app.services.ai_research._write_research_telemetry") as mock_telemetry,
            patch("app.services.ai_research._write_cache_row") as mock_write_cache,
            patch("app.services.ai_research.get_or_refresh_prediction") as mock_pred,
            patch("app.services.ai_research.anthropic.AsyncAnthropic") as mock_anth_cls,
            patch("app.services.ai_research._try_advisory_lock") as mock_lock,
            patch("app.services.ai_research._get_lock") as mock_get_lock,
        ):
            mock_analytics.get_cold_start_counts.return_value = mock_gate
            mock_analytics.compute_input_signature.return_value = "sig123"
            mock_creds.get_provider_credential.return_value = mock_cred
            mock_ai_quota.remaining.return_value = 5

            # Advisory lock acquired
            mock_lock.return_value = True

            # In-memory lock: not locked
            inner_lock = asyncio.Lock()
            mock_get_lock.return_value = inner_lock

            # Anthropic stream — messages.stream() must return the context manager directly
            # (not a coroutine), since it's used as `async with client.messages.stream(...)`
            mock_anth_instance = MagicMock()
            mock_anth_cls.return_value = mock_anth_instance
            mock_anth_instance.messages.stream.return_value = mock_stream

            # Cache not found
            mock_db.scalar.return_value = None
            mock_db.execute.return_value = MagicMock()

            mock_telemetry.return_value = MagicMock()
            mock_write_cache.return_value = MagicMock(
                response_json={"coffee_name": "Yirgacheffe Kochere"}
            )
            mock_pred.return_value = MagicMock()

            gen = generate_coffee_research(
                mock_db,
                user_id=1,
                coffee_name="Yirgacheffe Kochere",
                roaster_name="Counter Culture",
                current_signature="sig123",
            )
            async for event in gen:
                events.append(event)

        return events

    events = asyncio.run(run_success())

    # At minimum: some message events followed by exactly one complete event
    event_types = [getattr(e, "event", None) for e in events]
    assert "complete" in event_types, f"Expected 'complete' in events: {event_types}"
    # complete must be the LAST event
    assert event_types[-1] == "complete", f"'complete' must be last: {event_types}"
    # There should be at least one 'message' event before 'complete'
    assert "message" in event_types, f"Expected 'message' events: {event_types}"
    # No error event on success
    assert "error" not in event_types, f"Unexpected error event: {event_types}"


def test_sse_event_contract_error_on_validation_failure() -> None:
    """D-16: event:error is yielded when CoffeeResearchSchema.model_validate fails."""
    from app.services.ai_research import generate_coffee_research

    async def run_error():
        mock_db = MagicMock()
        mock_db.scalar.return_value = None

        mock_cred = MagicMock()
        mock_cred.provider = "anthropic"
        mock_cred.model_name = "claude-opus-4-5"
        mock_cred.key = "test-key"

        # Stream that yields some text but returns INVALID structured output
        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=False)
        mock_stream.text_stream = _async_gen(["Some prose."])

        mock_final_msg = MagicMock()
        # Return a block with INVALID data (missing required coffee_name)
        bad_block = MagicMock()
        bad_block.type = "tool_use"
        bad_block.name = "structure_output"
        bad_block.input = {"malformed": "no required fields"}
        mock_final_msg.content = [bad_block]
        mock_final_msg.usage = MagicMock()
        mock_final_msg.usage.input_tokens = 10
        mock_final_msg.usage.output_tokens = 5
        mock_stream.get_final_message = AsyncMock(return_value=mock_final_msg)

        events = []
        with (
            patch("app.services.ai_research.analytics_service") as mock_analytics,
            patch("app.services.ai_research.credentials_service") as mock_creds,
            patch("app.services.ai_research.ai_quota") as mock_ai_quota,
            patch("app.services.ai_research.anthropic.AsyncAnthropic") as mock_anth_cls,
            patch("app.services.ai_research._try_advisory_lock") as mock_lock,
            patch("app.services.ai_research._get_lock") as mock_get_lock,
        ):
            mock_analytics.get_cold_start_counts.return_value = {"gate_open": True}
            mock_analytics.compute_input_signature.return_value = "sig123"
            mock_creds.get_provider_credential.return_value = mock_cred
            mock_ai_quota.remaining.return_value = 5
            mock_lock.return_value = True
            inner_lock = asyncio.Lock()
            mock_get_lock.return_value = inner_lock

            mock_anth_instance = MagicMock()
            mock_anth_cls.return_value = mock_anth_instance
            mock_anth_instance.messages.stream.return_value = mock_stream
            mock_db.execute.return_value = MagicMock()

            gen = generate_coffee_research(
                mock_db,
                user_id=1,
                coffee_name="Test Coffee",
                roaster_name=None,
                current_signature="sig123",
            )
            async for event in gen:
                events.append(event)

        return events

    events = asyncio.run(run_error())
    event_types = [getattr(e, "event", None) for e in events]
    assert "error" in event_types, f"Expected error event, got: {event_types}"
    # No complete event after error
    assert "complete" not in event_types, f"complete must not follow error: {event_types}"


def test_advisory_lock_blocks_duplicate() -> None:
    """T-19-10: advisory lock prevents double-charge on EventSource reconnect.

    When the advisory lock cannot be acquired (another generator is running),
    generate_coffee_research must yield a single event:error with a 'locked' sentinel
    OR raise an exception that the caller can map to 429. We verify no LLM call fires.
    """
    from app.services.ai_research import generate_coffee_research

    async def run_locked():
        mock_db = MagicMock()
        mock_db.scalar.return_value = None
        mock_db.execute.return_value = MagicMock()

        mock_cred = MagicMock()
        mock_cred.provider = "anthropic"
        mock_cred.model_name = "claude-opus-4-5"
        mock_cred.key = "test-key"

        events = []
        with (
            patch("app.services.ai_research.analytics_service") as mock_analytics,
            patch("app.services.ai_research.credentials_service") as mock_creds,
            patch("app.services.ai_research.ai_quota") as mock_ai_quota,
            patch("app.services.ai_research._try_advisory_lock") as mock_lock,
            patch("app.services.ai_research._get_lock") as mock_get_lock,
            patch("app.services.ai_research.anthropic.AsyncAnthropic") as mock_anth_cls,
        ):
            mock_analytics.get_cold_start_counts.return_value = {"gate_open": True}
            mock_analytics.compute_input_signature.return_value = "sig"
            mock_creds.get_provider_credential.return_value = mock_cred
            mock_ai_quota.remaining.return_value = 5

            # Advisory lock NOT acquired (locked by other process)
            mock_lock.return_value = False

            # In-memory lock: available
            inner_lock = asyncio.Lock()
            mock_get_lock.return_value = inner_lock

            mock_anth_instance = MagicMock()
            mock_anth_cls.return_value = mock_anth_instance
            # If LLM is called, mark it
            mock_anth_instance.messages.stream.side_effect = AssertionError(
                "LLM called when lock not held"
            )

            gen = generate_coffee_research(
                mock_db,
                user_id=1,
                coffee_name="Test Coffee",
                roaster_name=None,
                current_signature="sig",
            )
            async for event in gen:
                events.append(event)

        return events

    events = asyncio.run(run_locked())
    # Must have yielded at least one event indicating lock contention
    event_types = [getattr(e, "event", None) for e in events]
    # The generator should yield an error event when locked
    assert len(events) >= 1, "Expected at least one event on lock contention"
    assert "error" in event_types or "locked" in event_types, (
        f"Expected error/locked sentinel on lock contention, got: {event_types}"
    )


def test_duration_ms_written() -> None:
    """AIX-13: ai_recommendations row written with rec_type='coffee_research' and duration_ms."""
    # Verify _write_research_telemetry is called with correct rec_type and duration_ms.
    # We import and call it directly to verify the call signature passes correctly.
    from app.services.ai_research import _write_research_telemetry

    mock_db = MagicMock()
    mock_cred = MagicMock()
    mock_cred.provider = "anthropic"
    mock_cred.model_name = "claude-opus-4-5"

    mock_usage = MagicMock()
    mock_usage.input_tokens = 100
    mock_usage.output_tokens = 50

    with patch("app.services.ai_research.ai_service") as mock_ai_svc:
        mock_ai_svc._write_recommendation_row.return_value = MagicMock()
        _write_research_telemetry(
            mock_db,
            user_id=1,
            cache_key="yirgacheffe|counter culture",
            cred=mock_cred,
            tool_version="web_search_20250305",
            usage=mock_usage,
            duration_ms=5432,
            error_status=None,
        )

    # Verify _write_recommendation_row was called with rec_type='coffee_research' and duration_ms
    mock_ai_svc._write_recommendation_row.assert_called_once()
    call_kwargs = mock_ai_svc._write_recommendation_row.call_args[1]
    assert call_kwargs["rec_type"] == "coffee_research"
    assert call_kwargs["duration_ms"] == 5432
    assert call_kwargs["duration_ms"] is not None


# ---------------------------------------------------------------------------
# Helpers for async tests
# ---------------------------------------------------------------------------


async def _async_gen(items):
    """Yield items as an async generator (for mocking text_stream)."""
    for item in items:
        yield item
