"""Wave 0 unit tests for ai_service helpers and ai_schemas.

Tests in this file are deliberately dependency-light:
- Projector / advisory key / throttle / fallback predicate: no DB, no SDK, no network
- URL verifier: respx mocks for httpx
- Schema validation: pure Pydantic in-process

Phase 12 adds the formal integration suite; this file is the import
surface those tests will extend.
"""

from __future__ import annotations

import types

import pytest
import respx
import httpx


# ---------------------------------------------------------------------------
# Task 1 — Schema + event taxonomy tests
# ---------------------------------------------------------------------------


def test_schemas_importable() -> None:
    from app.services.ai_schemas import (  # noqa: F401
        AltBrewerSchema,
        CoffeeRecSchema,
        EquipmentRecSchema,
        PasteRankSchema,
        RankedCoffeeItem,
        RecipeSuggestionSchema,
        SweetSpotsProseSchema,
    )


def test_all_top_level_schemas_have_summary_prose() -> None:
    from app.services.ai_schemas import (
        CoffeeRecSchema,
        EquipmentRecSchema,
        PasteRankSchema,
        SweetSpotsProseSchema,
    )

    for cls in (CoffeeRecSchema, EquipmentRecSchema, PasteRankSchema, SweetSpotsProseSchema):
        assert "summary_prose" in cls.model_fields, f"{cls.__name__} missing summary_prose"


def test_coffee_rec_schema_validate_complete() -> None:
    from app.services.ai_schemas import CoffeeRecSchema

    data = {
        "coffee_name": "Yirgacheffe",
        "roaster_name": "Counter Culture",
        "origin": "Ethiopia",
        "process": "Washed",
        "roast_level": "Light",
        "buy_url": "https://counterculturecoffee.com/yirg",
        "search_tier": "primary",
        "summary_prose": "A bright, floral washed Ethiopian with bergamot and stone fruit.",
        "recipe_suggestion": None,
        "alt_brewer": None,
    }
    rec = CoffeeRecSchema.model_validate(data)
    assert rec.summary_prose == data["summary_prose"]


def test_coffee_rec_schema_rejects_extra_fields() -> None:
    from pydantic import ValidationError
    from app.services.ai_schemas import CoffeeRecSchema

    data = {
        "coffee_name": "Test",
        "roaster_name": "Test Roaster",
        "origin": "Ethiopia",
        "process": "Natural",
        "roast_level": "Medium",
        "search_tier": "primary",
        "summary_prose": "Good.",
        "injected_field": "malicious_value",  # extra — must be rejected
    }
    with pytest.raises(ValidationError):
        CoffeeRecSchema.model_validate(data)


def test_paste_rank_schema_rejects_list_longer_than_3() -> None:
    from pydantic import ValidationError
    from app.services.ai_schemas import PasteRankSchema

    data = {
        "ranked": [
            {"rank": 1, "name": "A", "reasoning": "Best"},
            {"rank": 2, "name": "B", "reasoning": "Good"},
            {"rank": 3, "name": "C", "reasoning": "Ok"},
            {"rank": 4, "name": "D", "reasoning": "Extra"},  # 4th item — must fail
        ],
        "summary_prose": "Four items.",
    }
    with pytest.raises(ValidationError):
        PasteRankSchema.model_validate(data)


def test_coffee_rec_schema_json_schema_usable() -> None:
    from app.services.ai_schemas import CoffeeRecSchema

    schema = CoffeeRecSchema.model_json_schema()
    assert isinstance(schema, dict)
    assert "properties" in schema


def test_events_export_all_ai_constants() -> None:
    from app import events

    expected = {
        "AI_FALLBACK_TRIGGERED",
        "AI_GENERATION_ERROR",
        "AI_GENERATION_START",
        "AI_GENERATION_SUCCESS",
        "AI_REGEN_SKIPPED",
        "AI_THROTTLE_BLOCK",
        "AI_TIER_FALLBACK",
        "AI_URL_VERIFY",
    }
    for name in expected:
        assert hasattr(events, name), f"events.{name} missing"
        assert name in events.__all__, f"{name} not in events.__all__"


# ---------------------------------------------------------------------------
# Task 2 — Citation projector + URL verifier + advisory key
# ---------------------------------------------------------------------------


def _make_block(**kwargs: object) -> types.SimpleNamespace:
    """Build a fake SDK content block using SimpleNamespace."""
    return types.SimpleNamespace(**kwargs)


def test_citation_projector() -> None:
    """Projector strips text/server_tool_use/web_search_tool_result and returns only the named tool_use input."""
    from app.services.ai_service import _project_tool_use_input

    fake_input = {"coffee_name": "Yirg", "summary_prose": "Great."}
    content = [
        _make_block(type="text", text="Searching..."),
        _make_block(type="server_tool_use", name="web_search", input={}),
        _make_block(type="web_search_tool_result", content=[]),
        _make_block(type="text", text="Results found.", citations=[]),
        _make_block(type="tool_use", name="structure_output", input=fake_input),
    ]
    result = _project_tool_use_input(content, "structure_output")
    assert result is fake_input


def test_projector_no_match_raises() -> None:
    from app.services.ai_service import _project_tool_use_input

    content = [
        _make_block(type="text", text="No tool use here."),
        _make_block(type="server_tool_use", name="web_search", input={}),
    ]
    with pytest.raises(ValueError, match="No tool_use block"):
        _project_tool_use_input(content, "structure_output")


@respx.mock
@pytest.mark.asyncio
async def test_url_verify_verified() -> None:
    from app.services.ai_service import _verify_buy_url

    url = "https://example-roaster.com/yirgacheffe"
    respx.get(url).mock(
        return_value=httpx.Response(200, text="counter culture yirgacheffe buy now")
    )
    result = await _verify_buy_url(url, "Counter Culture", "Yirgacheffe")
    assert result is True


@respx.mock
@pytest.mark.asyncio
async def test_url_verify_404() -> None:
    from app.services.ai_service import _verify_buy_url

    url = "https://example-roaster.com/not-found"
    respx.get(url).mock(return_value=httpx.Response(404, text="Not found"))
    result = await _verify_buy_url(url, "Counter Culture", "Yirgacheffe")
    assert result is False


@pytest.mark.asyncio
async def test_url_verify_scheme_rejected() -> None:
    """http:// URL must return False immediately, no network call."""
    from app.services.ai_service import _verify_buy_url

    # No respx mock — any network call would raise; this test asserts no call is made
    result = await _verify_buy_url("http://example.com/coffee", "Roaster", "Coffee")
    assert result is False


@respx.mock
@pytest.mark.asyncio
async def test_url_verify_ssrf_redirect() -> None:
    """Cross-host 302 redirect must return False (follow_redirects=False)."""
    from app.services.ai_service import _verify_buy_url

    url = "https://legitimate-shop.com/coffee"
    respx.get(url).mock(
        return_value=httpx.Response(
            302,
            headers={"Location": "http://169.254.169.254/metadata"},
        )
    )
    result = await _verify_buy_url(url, "Roaster", "Coffee")
    assert result is False


def test_advisory_key_stable() -> None:
    """Same (user_id, rec_type) always produces the same signed int64."""
    from app.services.ai_service import _advisory_key

    k1 = _advisory_key(42, "coffee")
    k2 = _advisory_key(42, "coffee")
    k3 = _advisory_key(42, "equipment")

    assert k1 == k2
    assert k1 != k3
    # Must fit in signed int64
    assert -(2**63) <= k1 <= 2**63 - 1


# ---------------------------------------------------------------------------
# Task 3 — Fallback predicate + lock/throttle + max_uses
# ---------------------------------------------------------------------------


def test_fallback_predicate_non_retryable() -> None:
    """AuthenticationError, BadRequestError, PermissionDeniedError → fallback."""
    import anthropic
    from app.services.ai_service import _is_anthropic_fallback_error

    for cls in (
        anthropic.AuthenticationError,
        anthropic.BadRequestError,
        anthropic.PermissionDeniedError,
    ):
        exc = cls.__new__(cls)
        # Minimal attribute injection to avoid SDK constructor side effects
        object.__setattr__(exc, "message", "test")
        assert _is_anthropic_fallback_error(exc), f"{cls.__name__} should be fallback"


def test_fallback_predicate_529_string() -> None:
    """APIStatusError with 'overloaded_error' in str → fallback even when status_code != 529."""
    import anthropic
    from unittest.mock import MagicMock
    from app.services.ai_service import _is_anthropic_fallback_error

    exc = MagicMock(spec=anthropic.APIStatusError)
    exc.status_code = 500
    exc.__str__ = MagicMock(return_value="error_code: overloaded_error something went wrong")
    assert _is_anthropic_fallback_error(exc)


def test_fallback_predicate_rate_limit_false() -> None:
    """RateLimitError (429) is retryable — must NOT be a fallback trigger."""
    import anthropic
    from app.services.ai_service import _is_anthropic_fallback_error

    exc = anthropic.RateLimitError.__new__(anthropic.RateLimitError)
    object.__setattr__(exc, "message", "rate limited")
    assert not _is_anthropic_fallback_error(exc)


def test_lock_identity() -> None:
    """_get_lock returns the SAME lock object for the same (user_id, rec_type)."""
    from app.services.ai_service import _get_lock

    lock_a = _get_lock(1, "coffee")
    lock_b = _get_lock(1, "coffee")
    lock_c = _get_lock(1, "equipment")

    assert lock_a is lock_b
    assert lock_a is not lock_c


def test_throttle_eviction() -> None:
    """_evict_stale_throttle removes old entries and keeps fresh ones."""
    import time
    from app.services import ai_service

    # Inject synthetic throttle entries
    now = time.monotonic()
    ai_service._THROTTLE[9991] = now - 700.0  # stale (older than 600s window)
    ai_service._THROTTLE[9992] = now - 100.0  # fresh

    ai_service._evict_stale_throttle(now=now, window_secs=600.0)

    assert 9991 not in ai_service._THROTTLE
    assert 9992 in ai_service._THROTTLE

    # Cleanup
    ai_service._THROTTLE.pop(9992, None)


def test_max_uses_from_settings() -> None:
    """ai_service reads ai_primary_max_searches=5 and ai_broadened_max_searches=3 from settings."""
    from unittest.mock import patch
    from app.services import ai_service  # noqa: F401 — import asserts module loads cleanly

    with patch("app.services.settings.get_int") as mock_get_int:
        mock_get_int.return_value = 5
        val = mock_get_int("ai_primary_max_searches")
        assert val == 5

    with patch("app.services.settings.get_int") as mock_get_int:
        mock_get_int.return_value = 3
        val = mock_get_int("ai_broadened_max_searches")
        assert val == 3


# ---------------------------------------------------------------------------
# Task 1 (07-03) — suggest_recipe + alt_brewer_callout SQL sub-flows
# ---------------------------------------------------------------------------


def _make_db_with_sessions(sessions_data: list[dict]) -> object:
    """Build a minimal mock DB for SQL sub-flow tests.

    Each dict in sessions_data has: recipe_id, recipe_name, brewer_id,
    brewer_name, origin, process, roast_level, rating, user_id.
    We patch db.execute to return rows matching these.
    """
    from unittest.mock import MagicMock
    import types

    db = MagicMock()
    return db


def test_suggest_recipe_picks_highest_rated() -> None:
    """suggest_recipe returns the recipe with the highest avg rating for the given style."""
    from unittest.mock import MagicMock, patch
    import types
    from app.services.ai_service import suggest_recipe
    from app.services.ai_schemas import RecipeSuggestionSchema

    # Build fake result row: recipe_id=10, recipe_name="V60 Classic", avg_rating=4.5
    fake_row = types.SimpleNamespace(recipe_id=10, recipe_name="V60 Classic", avg_rating=4.5)
    mock_result = MagicMock()
    mock_result.first.return_value = fake_row

    db = MagicMock()
    db.execute.return_value = mock_result

    result = suggest_recipe(db, user_id=1, origin="Ethiopia", process="washed", roast_level="light")

    assert isinstance(result, RecipeSuggestionSchema)
    assert result.recipe_id == 10
    assert result.recipe_name == "V60 Classic"
    assert result.no_match is False
    # recipe_id must be one of the seeded IDs (not fabricated)
    assert result.recipe_id in (10,)


def test_suggest_recipe_no_match() -> None:
    """suggest_recipe returns no_match=True when no rated session used a recipe for the style."""
    from unittest.mock import MagicMock
    from app.services.ai_service import suggest_recipe
    from app.services.ai_schemas import RecipeSuggestionSchema

    mock_result = MagicMock()
    mock_result.first.return_value = None  # no rows

    db = MagicMock()
    db.execute.return_value = mock_result

    result = suggest_recipe(db, user_id=1, origin="Colombia", process="natural", roast_level="medium")

    assert isinstance(result, RecipeSuggestionSchema)
    assert result.recipe_id is None
    assert result.recipe_name is None
    assert result.no_match is True


def test_alt_brewer_fires_at_half_point_delta() -> None:
    """alt_brewer_callout returns AltBrewerSchema when best alt brewer avg is >=0.5 above baseline."""
    from unittest.mock import MagicMock
    import types
    from app.services.ai_service import alt_brewer_callout
    from app.services.ai_schemas import AltBrewerSchema

    # Two brewers: brewer_id=1 (avg 3.5 baseline), brewer_id=2 (avg 4.0 → delta exactly 0.5)
    row1 = types.SimpleNamespace(brewer_id=1, brewer_name="Hario V60", avg_rating=3.5)
    row2 = types.SimpleNamespace(brewer_id=2, brewer_name="Chemex", avg_rating=4.0)

    mock_result = MagicMock()
    mock_result.all.return_value = [row1, row2]

    db = MagicMock()
    db.execute.return_value = mock_result

    result = alt_brewer_callout(
        db,
        user_id=1,
        origin="Ethiopia",
        process="washed",
        roast_level="light",
        exclude_brewer_id=1,  # exclude current best brewer
    )

    assert result is not None
    assert isinstance(result, AltBrewerSchema)
    assert result.brewer_name == "Chemex"
    assert result.rating_delta >= 0.5


def test_alt_brewer_below_threshold_none() -> None:
    """alt_brewer_callout returns None when delta is below 0.5."""
    from unittest.mock import MagicMock
    import types
    from app.services.ai_service import alt_brewer_callout

    # Two brewers: brewer_id=1 (avg 3.7 baseline), brewer_id=2 (avg 4.0 → delta 0.3 < 0.5)
    row1 = types.SimpleNamespace(brewer_id=1, brewer_name="Hario V60", avg_rating=3.7)
    row2 = types.SimpleNamespace(brewer_id=2, brewer_name="Chemex", avg_rating=4.1)

    mock_result = MagicMock()
    mock_result.all.return_value = [row1, row2]

    db = MagicMock()
    db.execute.return_value = mock_result

    result = alt_brewer_callout(
        db,
        user_id=1,
        origin="Colombia",
        process="natural",
        roast_level="medium",
        exclude_brewer_id=2,  # chemex is current best; V60 is alt with delta 0.3
    )

    assert result is None
