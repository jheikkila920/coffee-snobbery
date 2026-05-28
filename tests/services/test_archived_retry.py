"""Tests for D-14: _verify_buy_url 404/410 rejection and archived-coffee retry logic."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import respx
import httpx


@pytest.mark.asyncio
@respx.mock
async def test_verify_url_rejects_404() -> None:
    """_verify_buy_url returns False when the server responds with HTTP 404."""
    from app.services.ai_service import _verify_buy_url

    respx.get("https://example.com/coffee/some-lot").mock(
        return_value=httpx.Response(404)
    )
    with patch("app.services.ai_service._assert_public_host", return_value=True):
        result = await _verify_buy_url(
            "https://example.com/coffee/some-lot",
            roaster_name="Example Roastery",
            coffee_name="Some Lot",
        )
    assert result is False


@pytest.mark.asyncio
@respx.mock
async def test_verify_url_rejects_410() -> None:
    """_verify_buy_url returns False when the server responds with HTTP 410 (Gone)."""
    from app.services.ai_service import _verify_buy_url

    respx.get("https://example.com/coffee/archived-lot").mock(
        return_value=httpx.Response(410)
    )
    with patch("app.services.ai_service._assert_public_host", return_value=True):
        result = await _verify_buy_url(
            "https://example.com/coffee/archived-lot",
            roaster_name="Example Roastery",
            coffee_name="Archived Lot",
        )
    assert result is False


@pytest.mark.asyncio
@respx.mock
async def test_verify_url_accepts_200_with_name() -> None:
    """_verify_buy_url returns True for a 200 response containing the coffee name."""
    from app.services.ai_service import _verify_buy_url

    respx.get("https://example.com/coffee/kenya-aa").mock(
        return_value=httpx.Response(200, text="Buy Kenya AA from Example Roastery today")
    )
    with patch("app.services.ai_service._assert_public_host", return_value=True):
        result = await _verify_buy_url(
            "https://example.com/coffee/kenya-aa",
            roaster_name="Example Roastery",
            coffee_name="Kenya AA",
        )
    assert result is True


@pytest.mark.asyncio
async def test_archived_retry_logic() -> None:
    """When first buy_url fails verification, _generate_coffee_rec fires a second LLM call
    with broadened-search instruction before returning the no-recommendation path."""
    import json

    from app.services.ai_service import _generate_coffee_rec

    # Minimal CoffeeRecSchema-compatible dict for the second (retry) LLM call
    # Note: price_usd and tasting_notes are NOT CoffeeRecSchema fields (extra=forbid)
    retry_rec_raw: dict[str, Any] = {
        "coffee_name": "Ethiopia Yirgacheffe",
        "roaster_name": "Blue Bottle Coffee",
        "origin": "Ethiopia",
        "process": "washed",
        "roast_level": "light",
        "buy_url": "https://bluebottle.com/ethiopia-yirgacheffe",
        "search_tier": "broadened",
        "summary_prose": "A bright, floral Ethiopian.",
    }

    call_count = 0

    def make_mock_anthropic_response(raw: dict[str, Any]) -> Any:
        """Build a minimal mock Anthropic response."""
        block = MagicMock()
        block.type = "tool_use"
        block.name = "structure_output"
        block.input = raw
        response = MagicMock()
        response.content = [block]
        response.usage = MagicMock()
        response.usage.input_tokens = 100
        response.usage.output_tokens = 50
        response.usage.server_tool_use = None
        return response

    def mock_messages_create(**kwargs: Any) -> Any:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call: return a rec with a buy_url that will fail verification
            first_rec: dict[str, Any] = {
                "coffee_name": "Archived Lot",
                "roaster_name": "Old Roaster",
                "origin": "Ethiopia",
                "process": "natural",
                "roast_level": "medium",
                "buy_url": "https://oldroaster.com/archived-lot",
                "search_tier": "primary",
                "summary_prose": "Archived coffee.",
            }
            return make_mock_anthropic_response(first_rec)
        else:
            # Second call (retry with broadened instruction): return valid rec
            return make_mock_anthropic_response(retry_rec_raw)

    mock_db = MagicMock()
    mock_db.execute.return_value.first.return_value = None
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    mock_db.execute.return_value.all.return_value = []

    mock_cred = MagicMock()
    mock_cred.provider = "anthropic"
    mock_cred.model_name = "claude-3-haiku-20240307"
    mock_cred.key = "test-key"

    with (
        patch("app.services.ai_service.credentials_service.get_provider_credential") as mock_get_cred,
        patch("app.services.ai_service.analytics_service.get_preference_profile", return_value={}),
        patch("app.services.ai_service.analytics_service.get_sweet_spots", return_value=[]),
        patch("app.services.ai_service.settings_service.get_int", return_value=3),
        patch("app.services.ai_service.settings_service.get_str", return_value="US"),
        patch("app.services.ai_service._build_anthropic_client") as mock_build_client,
        patch("app.services.ai_service._verify_buy_url") as mock_verify,
        patch("app.services.ai_service.suggest_recipe") as mock_suggest,
        patch("app.services.ai_service.alt_brewer_callout", return_value=None),
        patch("app.services.ai_service._write_recommendation_row") as mock_write,
    ):
        mock_get_cred.side_effect = lambda db, provider: mock_cred if provider == "anthropic" else None

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = mock_messages_create
        mock_build_client.return_value = mock_client

        # First URL fails verification; second succeeds
        mock_verify.side_effect = [False, True]

        mock_suggest.return_value = MagicMock(
            recipe_id=None,
            recipe_name=None,
            summary="No matching recipe.",
            ratio="1:15",
            temp_c=94,
            grind_hint="medium-fine",
        )
        mock_write.return_value = MagicMock()

        status, row = await _generate_coffee_rec(
            mock_db,
            user_id=1,
            generated_by="test",
            signature="sig-test",
        )

    # Two LLM calls were made: primary tier (1st attempt) + retry with broadened instruction
    assert call_count == 2, f"Expected 2 LLM calls, got {call_count}"
    # The retry broadened instruction should be in the second call
    second_call_kwargs = mock_client.messages.create.call_args_list[1][1]
    messages_content = second_call_kwargs.get("messages", [{}])[0].get("content", "")
    assert "broaden" in messages_content.lower() or any(
        "broaden" in str(arg).lower()
        for arg in mock_client.messages.create.call_args_list[1]
    ), "Second LLM call should contain the broadened-search instruction"


def test_for_sale_only_clause_in_prompts() -> None:
    """The coffee rec prompt includes the for-sale-only clause (D-14)."""
    import re
    import pathlib

    src = pathlib.Path("app/services/ai_service.py").read_text(encoding="utf-8")
    # Check for the D-14 for-sale-only instruction in the prompt builders
    assert re.search(
        r"(currently.{0,20}for sale|archived|sold.out|discontinued)",
        src,
        re.IGNORECASE,
    ), "ai_service.py must include for-sale-only / archived-coffee language per D-14"


def test_broadened_search_instruction_present() -> None:
    """The broadened-search retry instruction string is present in ai_service.py."""
    import pathlib

    src = pathlib.Path("app/services/ai_service.py").read_text(encoding="utf-8")
    assert "broaden" in src.lower(), (
        "ai_service.py must contain the broadened-search retry instruction"
    )
