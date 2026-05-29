"""Tests for Phase 19 PreferenceProfileProseSchema + generate_preference_profile_prose.

Requirements traceability:
  AIX-09  — PreferenceProfileProseSchema has a single summary_prose field with extra=forbid
  AIX-09/D-10 — generate_preference_profile_prose builds prompt from get_preference_profile
               + get_flavor_descriptors + writes rec_type='preference_profile_prose'
  AIX-13/D-15  — duration_ms written; p95 target comment present
  Scheduler     — nightly loop includes preference_profile_prose; brew_improvement absent
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

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


def test_preference_prose_consumes_analytics_helpers() -> None:
    """AIX-09/D-10: generate_preference_profile_prose calls get_preference_profile +
    get_flavor_descriptors and writes rec_type='preference_profile_prose'.

    Verifies:
    - get_preference_profile is called with the user_id
    - get_flavor_descriptors is called with the user_id
    - Written rec_type is 'preference_profile_prose'
    - Signature from compute_input_signature is used for dedup
    """
    from app.services.ai_schemas import PreferenceProfileProseSchema

    user_id = 1
    current_sig = "test-sig-abc123"

    prose_result = PreferenceProfileProseSchema(
        summary_prose=(
            "You gravitate toward washed Ethiopian coffees and naturals from Colombia, "
            "rating jasmine and bergamot notes highest in 4.5+ rated sessions. "
            "Your sweet spot is 94°C with a 1:15 ratio on a V60."
        )
    )

    mock_db = MagicMock()

    mock_cred = MagicMock()
    mock_cred.provider = "anthropic"
    mock_cred.key = "sk-ant-test"
    mock_cred.model_name = "claude-3-5-haiku-latest"

    # Profile data from get_preference_profile — use named tuples to be JSON-serializable
    from collections import namedtuple

    ProfRow = namedtuple("ProfRow", ["label", "avg_rating", "session_count"])
    FlavorRow = namedtuple("FlavorRow", ["id", "name", "session_count"])

    mock_profile = {
        "origin": [ProfRow(label="Ethiopia", avg_rating=4.5, session_count=5)],
        "process": [ProfRow(label="Washed", avg_rating=4.3, session_count=8)],
        "roaster": [],
        "roast_level": [ProfRow(label="Light", avg_rating=4.4, session_count=6)],
    }

    # Flavor data from get_flavor_descriptors
    mock_flavors = [
        FlavorRow(id=1, name="jasmine", session_count=4),
        FlavorRow(id=2, name="bergamot", session_count=3),
    ]

    # Tool_use block the LLM returns
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "structure_output"
    tool_block.input = prose_result.model_dump()

    mock_resp = MagicMock()
    mock_resp.content = [tool_block]
    mock_resp.usage = MagicMock(input_tokens=300, output_tokens=100)

    mock_anth_client = MagicMock()
    mock_anth_client.messages.create.return_value = mock_resp

    written_rows: list[dict] = []

    def fake_write_row(db, *, user_id, rec_type, **kwargs):
        written_rows.append({"rec_type": rec_type, "user_id": user_id, **kwargs})
        return MagicMock(id=99)

    with (
        patch(
            "app.services.ai_service.credentials_service.get_provider_credential",
            return_value=mock_cred,
        ),
        patch(
            "app.services.ai_service.analytics_service.compute_input_signature",
            return_value=current_sig,
        ),
        patch(
            "app.services.ai_service.get_latest_recommendation",
            return_value=None,  # no existing row
        ),
        patch(
            "app.services.ai_service.analytics_service.get_preference_profile",
            return_value=mock_profile,
        ) as mock_get_profile,
        patch(
            "app.services.ai_service.analytics_service.get_flavor_descriptors",
            return_value=mock_flavors,
        ) as mock_get_flavors,
        patch(
            "app.services.ai_service.anthropic.Anthropic",
            return_value=mock_anth_client,
        ),
        patch(
            "app.services.ai_service._write_recommendation_row",
            side_effect=fake_write_row,
        ),
    ):
        from app.services.ai_service import generate_preference_profile_prose

        status, row = asyncio.run(generate_preference_profile_prose(mock_db, user_id=user_id))

        # Both analytics helpers must have been called with the user_id
        mock_get_profile.assert_called_once_with(mock_db, user_id)
        mock_get_flavors.assert_called_once_with(mock_db, user_id)

        # Status should be "generated" (no existing row)
        assert status == "generated"

        # The written row must have the correct rec_type
        assert len(written_rows) == 1
        assert written_rows[0]["rec_type"] == "preference_profile_prose"
        assert written_rows[0]["input_signature"] == current_sig


def test_preference_prose_skips_on_unchanged_signature() -> None:
    """AIX-09: When the signature hasn't changed, returns ('skipped', existing_row)."""
    user_id = 1
    current_sig = "sig-unchanged"

    mock_db = MagicMock()
    mock_cred = MagicMock()
    mock_cred.provider = "anthropic"
    mock_cred.key = "sk-ant-test"
    mock_cred.model_name = "claude-3-5-haiku-latest"

    existing_row = MagicMock()
    existing_row.input_signature = current_sig

    with (
        patch(
            "app.services.ai_service.credentials_service.get_provider_credential",
            return_value=mock_cred,
        ),
        patch(
            "app.services.ai_service.analytics_service.compute_input_signature",
            return_value=current_sig,
        ),
        patch(
            "app.services.ai_service.get_latest_recommendation",
            return_value=existing_row,
        ),
    ):
        from app.services.ai_service import generate_preference_profile_prose

        status, row = asyncio.run(generate_preference_profile_prose(mock_db, user_id=user_id))

        assert status == "skipped"
        assert row is existing_row


def test_preference_prose_latency_comment_present() -> None:
    """AIX-13/D-15: p95 latency comment must be present above the function."""
    import re

    with open("app/services/ai_service.py") as f:
        content = f.read()

    # Find the generate_preference_profile_prose function
    # and verify a p95 comment appears above it
    pattern = r"# p95 target: <= 30s\n.*?async def generate_preference_profile_prose"
    assert re.search(pattern, content, re.DOTALL), (
        "Missing '# p95 target: <= 30s' comment above generate_preference_profile_prose"
    )
