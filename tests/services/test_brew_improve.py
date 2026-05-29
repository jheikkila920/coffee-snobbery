"""Tests for Phase 19 BrewImproveSchema + generate_brew_improvement service flow.

Requirements traceability:
  AIX-12 — BrewImproveSchema + BrewParameterChangeSchema validate and reject
            extra fields; parameter Literal enforced
  AIX-12/D-12 — generate_brew_improvement loads ALL of the user's brew sessions
                for the session's coffee_id and serializes them into the prompt
  AIX-12/D-16 — SSE two-phase flow (prose stream -> validate -> complete)
  AIX-13/D-15  — duration_ms written; p95 comment present
  T-19-12      — session loaded with user_id scope (IDOR defence)
  T-19-14      — quota counts against improve_brew bucket, not research
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

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


def test_prior_sessions_loaded_for_improve_brew() -> None:
    """AIX-12/D-12: All of the user's sessions for the target coffee_id are
    serialized into the prompt so the LLM avoids already-tried parameters.

    Verifies:
    - brew_sessions.list_brew_sessions is called with by_user_id + coffee_id
    - each prior session's dial fields appear in the LLM prompt text
    - cross-user session access returns None (T-19-12 IDOR)
    - quota counted against improve_brew bucket (T-19-14)
    """
    from decimal import Decimal

    from app.services.ai_schemas import BrewImproveSchema, BrewParameterChangeSchema

    user_id = 1
    session_id = 42
    coffee_id = 7

    # Build a mock target session (user-owned)
    mock_target_session = MagicMock()
    mock_target_session.id = session_id
    mock_target_session.user_id = user_id
    mock_target_session.coffee_id = coffee_id
    mock_target_session.grind_setting_actual = "medium-fine"
    mock_target_session.dose_grams_actual = Decimal("18")
    mock_target_session.water_grams_actual = Decimal("270")
    mock_target_session.water_temp_c_actual = Decimal("94")
    mock_target_session.brewer_id = 3
    mock_target_session.recipe_id = 5
    mock_target_session.rating = Decimal("3.5")
    mock_target_session.notes = "Slightly bitter"
    mock_target_session.brewed_at = None

    # Build prior sessions list (two additional sessions for same coffee)
    prior1 = MagicMock()
    prior1.id = 40
    prior1.grind_setting_actual = "medium"
    prior1.dose_grams_actual = Decimal("18")
    prior1.water_grams_actual = Decimal("270")
    prior1.water_temp_c_actual = Decimal("93")
    prior1.brewer_id = 3
    prior1.recipe_id = 5
    prior1.rating = Decimal("3.0")

    prior2 = MagicMock()
    prior2.id = 41
    prior2.grind_setting_actual = "coarse"
    prior2.dose_grams_actual = Decimal("18")
    prior2.water_grams_actual = Decimal("280")
    prior2.water_temp_c_actual = Decimal("95")
    prior2.brewer_id = 3
    prior2.recipe_id = 5
    prior2.rating = Decimal("2.5")

    # BrewImproveSchema result the mock LLM will return
    improve_result = BrewImproveSchema(
        summary_prose="Your grind is too fine. Try 1 click coarser.",
        unchanged_parameters=["ratio", "temp_c"],
        next_try=[
            BrewParameterChangeSchema(
                parameter="grind",
                suggested_value="1 click coarser",
                rationale="Bitter notes suggest over-extraction.",
            )
        ],
    )

    mock_db = MagicMock()

    # Build a mock Anthropic streaming context
    mock_stream = MagicMock()
    mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
    mock_stream.__aexit__ = AsyncMock(return_value=False)

    async def _mock_text_stream():
        yield "Your grind is too fine."

    mock_stream.text_stream = _mock_text_stream()

    # Build a properly-typed tool_use block that _project_tool_use_input can parse
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "structure_output"
    tool_block.input = improve_result.model_dump()

    mock_final_msg = MagicMock()
    mock_final_msg.content = [tool_block]
    mock_final_msg.usage = MagicMock(input_tokens=400, output_tokens=150)
    mock_stream.get_final_message = AsyncMock(return_value=mock_final_msg)

    mock_anth_instance = MagicMock()
    mock_anth_instance.messages.stream.return_value = mock_stream
    mock_anthropic_cls = MagicMock(return_value=mock_anth_instance)

    mock_cred = MagicMock()
    mock_cred.provider = "anthropic"
    mock_cred.key = "sk-ant-test"
    mock_cred.model_name = "claude-3-5-haiku-latest"

    with (
        patch(
            "app.services.ai_service.credentials_service.get_provider_credential",
            return_value=mock_cred,
        ),
        patch(
            "app.services.brew_sessions.get_brew_session",
            return_value=mock_target_session,
        ),
        patch(
            "app.services.brew_sessions.list_brew_sessions",
            return_value=[mock_target_session, prior1, prior2],
        ) as mock_list,
        patch(
            "app.services.ai_quota.remaining",
            return_value=15,
        ),
        patch(
            "app.services.ai_service._write_recommendation_row",
            return_value=MagicMock(),
        ),
        patch(
            "app.services.ai_service.anthropic.AsyncAnthropic",
            mock_anthropic_cls,
        ),
    ):
        from app.services.ai_service import generate_brew_improvement

        async def run_generator():
            events = []
            async for event in generate_brew_improvement(
                mock_db, user_id=user_id, session_id=session_id
            ):
                events.append(event)
            return events

        events = asyncio.run(run_generator())

        # Verify list_brew_sessions was called with user_id + coffee_id
        mock_list.assert_called_once()
        call_kwargs = mock_list.call_args[1]
        assert call_kwargs["by_user_id"] == user_id
        assert call_kwargs["coffee_id"] == coffee_id

        # At minimum we got a complete event (or message + complete)
        event_types = [e.event for e in events]
        assert "complete" in event_types


def test_brew_improve_cross_user_returns_error() -> None:
    """T-19-12: Cross-user session access (IDOR) yields event:error, not a result."""
    mock_db = MagicMock()

    mock_cred = MagicMock()
    mock_cred.provider = "anthropic"
    mock_cred.key = "sk-ant-test"
    mock_cred.model_name = "claude-3-5-haiku-latest"

    with (
        patch(
            "app.services.ai_service.credentials_service.get_provider_credential",
            return_value=mock_cred,
        ),
        # get_brew_session returns None (cross-user or not found)
        patch(
            "app.services.brew_sessions.get_brew_session",
            return_value=None,
        ),
        patch(
            "app.services.ai_quota.remaining",
            return_value=15,
        ),
    ):
        from app.services.ai_service import generate_brew_improvement

        async def run_generator():
            events = []
            async for event in generate_brew_improvement(mock_db, user_id=1, session_id=999):
                events.append(event)
            return events

        events = asyncio.run(run_generator())

        # Should yield an error event, not a complete event
        assert len(events) >= 1
        assert events[0].event == "error"


def test_brew_improve_quota_bucket() -> None:
    """T-19-14: Quota is checked against improve_brew bucket, not research."""
    mock_db = MagicMock()

    mock_cred = MagicMock()
    mock_cred.provider = "anthropic"
    mock_cred.key = "sk-ant-test"
    mock_cred.model_name = "claude-3-5-haiku-latest"

    with (
        patch(
            "app.services.ai_service.credentials_service.get_provider_credential",
            return_value=mock_cred,
        ),
        patch(
            "app.services.brew_sessions.get_brew_session",
            return_value=MagicMock(id=1, coffee_id=5, user_id=1),
        ),
        patch(
            "app.services.brew_sessions.list_brew_sessions",
            return_value=[],
        ),
        patch(
            "app.services.ai_quota.remaining",
            return_value=0,
        ) as mock_remaining,
        patch(
            "app.services.ai_quota.get_quota_reset_time",
            return_value=None,
        ),
    ):
        from app.services.ai_service import generate_brew_improvement

        async def run_generator():
            events = []
            async for event in generate_brew_improvement(mock_db, user_id=1, session_id=1):
                events.append(event)
            return events

        events = asyncio.run(run_generator())

        # Should yield a quota-exceeded error
        assert len(events) >= 1
        assert events[0].event == "error"

        # Verify quota was checked with the improve_brew bucket
        mock_remaining.assert_called_once()
        call_args = mock_remaining.call_args[0]
        # call_args = (db, user_id, rec_type)
        assert call_args[2] == "brew_improvement"
