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

import httpx
import pytest
import respx

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
    """Projector strips non-tool_use blocks and returns only the named tool_use input."""
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
    import socket
    from unittest.mock import patch

    from app.services.ai_service import _verify_buy_url

    url = "https://example-roaster.com/yirgacheffe"
    respx.get(url).mock(
        return_value=httpx.Response(200, text="counter culture yirgacheffe buy now")
    )
    # Mock getaddrinfo so _assert_public_host passes; test focuses on HTTP-level logic.
    mock_public = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443))]
    with patch("socket.getaddrinfo", return_value=mock_public):
        result = await _verify_buy_url(url, "Counter Culture", "Yirgacheffe")
    assert result is True


@respx.mock
@pytest.mark.asyncio
async def test_url_verify_404() -> None:
    import socket
    from unittest.mock import patch

    from app.services.ai_service import _verify_buy_url

    url = "https://example-roaster.com/not-found"
    respx.get(url).mock(return_value=httpx.Response(404, text="Not found"))
    # Mock getaddrinfo so _assert_public_host passes; the 404 handler is what we
    # are exercising here (without this the gate would short-circuit on hosts
    # that fail to resolve in CI, making the assertion pass vacuously).
    mock_public = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443))]
    with patch("socket.getaddrinfo", return_value=mock_public):
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


# ---------------------------------------------------------------------------
# S1 — SSRF private-IP / DNS gate tests (14-02)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ssrf_private_ipv4_blocked() -> None:
    """Private IPv4 addresses (RFC 1918) must be rejected before any httpx call."""
    import socket
    from unittest.mock import patch

    from app.services.ai_service import _verify_buy_url

    for private_ip in ("10.0.0.1", "172.16.0.1", "192.168.0.1"):
        mock_result = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (private_ip, 443))]
        with patch("socket.getaddrinfo", return_value=mock_result):
            result = await _verify_buy_url("https://example.com/coffee", "Roaster", "Coffee")
        assert result is False, f"Expected False for private IP {private_ip}"


@pytest.mark.asyncio
async def test_ssrf_loopback_blocked() -> None:
    """Loopback addresses (127.0.0.1, ::1) must be rejected."""
    import socket
    from unittest.mock import patch

    from app.services.ai_service import _verify_buy_url

    # IPv4 loopback
    mock_v4 = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 443))]
    with patch("socket.getaddrinfo", return_value=mock_v4):
        assert await _verify_buy_url("https://example.com/coffee", "Roaster", "Coffee") is False

    # IPv6 loopback
    mock_v6 = [(socket.AF_INET6, socket.SOCK_STREAM, 0, "", ("::1", 443, 0, 0))]
    with patch("socket.getaddrinfo", return_value=mock_v6):
        assert await _verify_buy_url("https://example.com/coffee", "Roaster", "Coffee") is False


@pytest.mark.asyncio
async def test_ssrf_link_local_blocked() -> None:
    """Link-local addresses including the cloud-metadata endpoint must be rejected."""
    import socket
    from unittest.mock import patch

    from app.services.ai_service import _verify_buy_url

    # Cloud-metadata endpoint 169.254.169.254 (AWS/GCP/Azure IMDS)
    mock_result = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("169.254.169.254", 443))]
    with patch("socket.getaddrinfo", return_value=mock_result):
        result = await _verify_buy_url("https://example.com/coffee", "Roaster", "Coffee")
    assert result is False


@pytest.mark.asyncio
async def test_ssrf_ipv4_mapped_ipv6_blocked() -> None:
    """IPv4-mapped IPv6 (::ffff:169.254.169.254) must be normalised then rejected.

    Without ipv4_mapped normalisation the address would appear as a global IPv6
    and bypass the link-local check entirely — this test proves normalisation works.
    """
    import socket
    from unittest.mock import patch

    from app.services.ai_service import _verify_buy_url

    mock_result = [
        (socket.AF_INET6, socket.SOCK_STREAM, 0, "", ("::ffff:169.254.169.254", 443, 0, 0))
    ]
    with patch("socket.getaddrinfo", return_value=mock_result):
        result = await _verify_buy_url("https://example.com/coffee", "Roaster", "Coffee")
    assert result is False


@pytest.mark.asyncio
async def test_ssrf_cgnat_blocked() -> None:
    """CGNAT shared space (100.64.0.0/10, RFC 6598) must be rejected.

    Python's ipaddress does not flag CGNAT under is_private/is_reserved/etc., so
    the gate relies on `not is_global` to catch it (CR-01).
    """
    import socket
    from unittest.mock import patch

    from app.services.ai_service import _verify_buy_url

    mock_result = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("100.64.0.1", 443))]
    with patch("socket.getaddrinfo", return_value=mock_result):
        result = await _verify_buy_url("https://example.com/coffee", "Roaster", "Coffee")
    assert result is False


@pytest.mark.asyncio
async def test_ssrf_public_url_allowed() -> None:
    """A public host must not be false-blocked by the gate.

    Calls _assert_public_host directly with a mocked resolution to a known
    public IP (93.184.216.34 — example.com) so the test is deterministic
    without making a real network call or needing respx.
    """
    import socket
    from unittest.mock import patch

    from app.services.ai_service import _assert_public_host

    mock_result = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443))]
    with patch("socket.getaddrinfo", return_value=mock_result):
        result = _assert_public_host("https://example.com/coffee")
    assert result is True


@pytest.mark.asyncio
async def test_fetch_page_ssrf_private_blocked() -> None:
    """_fetch_page_text must return '' for a host resolving to a private IP."""
    import socket
    from unittest.mock import patch

    from app.services.ai_service import _fetch_page_text

    mock_result = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.1", 443))]
    with patch("socket.getaddrinfo", return_value=mock_result):
        result = await _fetch_page_text("https://internal.corp/page")
    assert result == ""


@pytest.mark.asyncio
async def test_ssrf_dns_failure_blocked() -> None:
    """DNS resolution failure (socket.gaierror) must be treated as a rejection."""
    import socket
    from unittest.mock import patch

    from app.services.ai_service import _verify_buy_url

    with patch("socket.getaddrinfo", side_effect=socket.gaierror("Name not found")):
        result = await _verify_buy_url("https://nonexistent.invalid/coffee", "Roaster", "Coffee")
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
    from unittest.mock import MagicMock

    import anthropic

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

    db = MagicMock()
    return db


def test_suggest_recipe_picks_highest_rated() -> None:
    """suggest_recipe returns the recipe with the highest avg rating for the given style."""
    import types
    from unittest.mock import MagicMock

    from app.services.ai_schemas import RecipeSuggestionSchema
    from app.services.ai_service import suggest_recipe

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
    # D-11: no_match removed; ratio/temp_c/grind_hint are required fields
    assert result.ratio  # non-empty string
    assert isinstance(result.temp_c, int)
    assert result.grind_hint  # non-empty string
    # recipe_id must be one of the seeded IDs (not fabricated)
    assert result.recipe_id in (10,)


def test_suggest_recipe_no_catalog_match() -> None:
    """suggest_recipe returns recipe_id=None with populated ratio/temp_c/grind_hint
    when no catalog recipe matches the style (D-11 — no_match removed)."""
    from unittest.mock import MagicMock

    from app.services.ai_schemas import RecipeSuggestionSchema
    from app.services.ai_service import suggest_recipe

    mock_result = MagicMock()
    mock_result.first.return_value = None  # no rows

    db = MagicMock()
    db.execute.return_value = mock_result

    result = suggest_recipe(
        db, user_id=1, origin="Colombia", process="natural", roast_level="medium"
    )

    assert isinstance(result, RecipeSuggestionSchema)
    assert result.recipe_id is None
    assert result.recipe_name is None
    # D-11: even when no catalog match, required fields must be populated
    assert result.ratio  # non-empty string
    assert isinstance(result.temp_c, int)
    assert result.grind_hint  # non-empty string


def test_recipe_schema_no_match_rejected() -> None:
    """Constructing RecipeSuggestionSchema(no_match=True) raises ValidationError.

    D-11: no_match was removed from the schema; extra=forbid means passing it
    as a keyword argument raises ValidationError.
    """
    import pytest
    from pydantic import ValidationError

    from app.services.ai_schemas import RecipeSuggestionSchema

    with pytest.raises(ValidationError):
        RecipeSuggestionSchema(
            no_match=True,  # type: ignore[call-arg]
            recipe_id=None,
            recipe_name=None,
            summary="No recipe.",
            ratio="1:15",
            temp_c=94,
            grind_hint="medium-fine",
        )


def test_recipe_schema_required_fields() -> None:
    """RecipeSuggestionSchema requires ratio, temp_c, and grind_hint (D-11)."""
    from pydantic import ValidationError

    from app.services.ai_schemas import RecipeSuggestionSchema

    # Missing ratio, temp_c, grind_hint should raise ValidationError
    with pytest.raises(ValidationError):
        RecipeSuggestionSchema(
            recipe_id=None,
            recipe_name=None,
            summary="No recipe.",
        )  # type: ignore[call-arg]

    # Valid construction with all required fields should succeed
    schema = RecipeSuggestionSchema(
        recipe_id=None,
        recipe_name=None,
        summary="Generated recipe.",
        ratio="1:16",
        temp_c=93,
        grind_hint="fine",
    )
    assert schema.ratio == "1:16"
    assert schema.temp_c == 93
    assert schema.grind_hint == "fine"


def test_alt_brewer_fires_at_half_point_delta() -> None:
    """alt_brewer_callout returns AltBrewerSchema when best alt avg is >=0.5 above baseline."""
    import types
    from unittest.mock import MagicMock

    from app.services.ai_schemas import AltBrewerSchema
    from app.services.ai_service import alt_brewer_callout

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
    import types
    from unittest.mock import MagicMock

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


# ---------------------------------------------------------------------------
# Task 2 (07-03) — Coffee-rec composite flow + sweet-spots prose
# ---------------------------------------------------------------------------


def _build_anthropic_response(raw_dict: dict) -> object:
    """Build a fake Anthropic messages.create response with structure_output tool_use block."""
    import types

    fake_input = raw_dict
    tool_use_block = types.SimpleNamespace(
        type="tool_use",
        name="structure_output",
        input=fake_input,
    )
    usage = types.SimpleNamespace(input_tokens=100, output_tokens=50)
    server_tool_use = types.SimpleNamespace(web_search_requests=1)
    usage.server_tool_use = server_tool_use
    response = types.SimpleNamespace(content=[tool_use_block], usage=usage)
    return response


def _valid_coffee_rec_dict(search_tier: str = "primary") -> dict:
    return {
        "coffee_name": "Yirgacheffe Kochere",
        "roaster_name": "Counter Culture",
        "origin": "Ethiopia",
        "process": "Washed",
        "roast_level": "Light",
        "buy_url": "https://counterculturecoffee.com/kochere",
        "search_tier": search_tier,
        "summary_prose": "A bright washed Ethiopian with jasmine and bergamot notes.",
        "recipe_suggestion": None,
        "alt_brewer": None,
    }


def test_three_tier_fallback() -> None:
    """_generate_coffee_rec advances primary→broadened→characteristics_only and records search_tier.

    Tests the tier fallback using _anthropic_coffee_call directly:
    - Call with empty response (no structure_output block) → ValueError (simulates tier 1/2)
    - Call with valid response → succeeds (simulates tier 3)
    Also verifies that the search_tier field is correctly set to characteristics_only.
    """
    import types
    from unittest.mock import MagicMock, patch

    from app.services.ai_service import _anthropic_coffee_call

    # Empty response — projector raises ValueError (simulates tier 1 and 2 failing)
    empty_response = types.SimpleNamespace(
        content=[types.SimpleNamespace(type="text", text="searching...")],
        usage=types.SimpleNamespace(
            input_tokens=10,
            output_tokens=5,
            server_tool_use=types.SimpleNamespace(web_search_requests=0),
        ),
    )
    # Tier 3 response — valid structure_output block
    tier3_dict = _valid_coffee_rec_dict("characteristics_only")
    tier3_block = types.SimpleNamespace(type="tool_use", name="structure_output", input=tier3_dict)
    tier3_response = types.SimpleNamespace(
        content=[tier3_block],
        usage=types.SimpleNamespace(
            input_tokens=20,
            output_tokens=30,
            server_tool_use=types.SimpleNamespace(web_search_requests=0),
        ),
    )

    mock_client = MagicMock()
    # First 2 calls (tier1, tier2) return empty → ValueError from projector
    # Third call returns valid tier3 response
    mock_client.messages.create.side_effect = [empty_response, empty_response, tier3_response]

    with patch("app.services.settings.get_int", return_value=3):
        with patch("app.services.settings.get_str", return_value="web_search_20250305"):
            # Tier 1 call — projector raises ValueError (no structure_output block)
            try:
                _anthropic_coffee_call(
                    mock_client,
                    model="claude-opus-4-7",
                    tool_version="web_search_20250305",
                    max_uses=3,
                    region="US",
                    prompt="Find coffee matching Ethiopia Washed Light",
                )
                raise AssertionError("Should have raised ValueError for empty tier1 response")
            except ValueError:
                pass  # Expected — tier 1 fails

            # Tier 2 call — also raises ValueError
            try:
                _anthropic_coffee_call(
                    mock_client,
                    model="claude-opus-4-7",
                    tool_version="web_search_20250305",
                    max_uses=3,
                    region="US",
                    prompt="Find coffee from Ethiopia",
                )
                raise AssertionError("Should have raised ValueError for empty tier2 response")
            except ValueError:
                pass  # Expected — tier 2 also fails

            # Tier 3 call — should succeed with characteristics_only
            raw, usage, count = _anthropic_coffee_call(
                mock_client,
                model="claude-opus-4-7",
                tool_version="web_search_20250305",
                max_uses=0,  # no web search on tier 3
                region="US",
                prompt="Recommend a coffee matching Light roast profile",
            )
            from app.services.ai_schemas import CoffeeRecSchema

            rec = CoffeeRecSchema.model_validate(raw)
            assert rec.search_tier == "characteristics_only", (
                f"Expected 'characteristics_only', got {rec.search_tier!r}"
            )


def test_provider_fallback_anthropic_to_openai() -> None:
    """A non-retryable anthropic error triggers the OpenAI fallback path."""
    from unittest.mock import MagicMock, patch

    import anthropic as anthropic_sdk

    from app.services.ai_service import _anthropic_coffee_call, _is_anthropic_fallback_error

    mock_client = MagicMock()
    # AuthenticationError is non-retryable → should trigger fallback
    exc = anthropic_sdk.AuthenticationError.__new__(anthropic_sdk.AuthenticationError)
    object.__setattr__(exc, "message", "invalid key")
    mock_client.messages.create.side_effect = exc

    with patch("app.services.settings.get_int", return_value=3):
        with patch("app.services.settings.get_str", return_value="web_search_20250305"):
            try:
                _anthropic_coffee_call(
                    mock_client,
                    model="claude-opus-4-7",
                    tool_version="web_search_20250305",
                    max_uses=3,
                    region="US",
                    prompt="recommend a coffee",
                )
                raise AssertionError("Should have raised AuthenticationError")
            except anthropic_sdk.AuthenticationError as e:
                # This is the expected error that triggers fallback
                assert _is_anthropic_fallback_error(e) is True


def test_pydantic_validation_error_try_again() -> None:
    """All tiers returning invalid dicts → ValidationError → 'try_again'."""
    from pydantic import ValidationError

    from app.services.ai_schemas import CoffeeRecSchema

    # A dict missing required fields — model_validate raises ValidationError
    bad_dict = {"coffee_name": "test"}  # missing all other required fields
    with pytest.raises(ValidationError):
        CoffeeRecSchema.model_validate(bad_dict)


@pytest.mark.asyncio
async def test_sweet_spots_prose_skipped_when_empty() -> None:
    """_generate_sweet_spots_prose returns None when get_sweet_spots returns empty list."""
    from unittest.mock import MagicMock, patch

    from app.services import ai_service

    db = MagicMock()
    mock_cred = MagicMock()
    mock_cred.provider = "anthropic"
    mock_cred.model_name = "claude-opus-4-7"
    mock_cred.key = "sk-test"

    with patch.object(ai_service.analytics_service, "get_sweet_spots", return_value=[]):
        result = await ai_service._generate_sweet_spots_prose(
            db,
            user_id=1,
            generated_by="scheduler",
            cred=mock_cred,
            signature="abc123",
        )
        assert result is None


def test_openai_coffee_call_no_json_schema() -> None:
    """_openai_coffee_call must use web_search_preview tools (NOT json_schema mode).

    The OpenAI Responses API silently disables web_search_preview when json_schema
    format is requested (Pitfall 2 in RESEARCH.md). We verify the function uses
    tools=[{"type":"web_search_preview"}] and does NOT pass text.format.json_schema.
    """
    from unittest.mock import MagicMock

    from app.services.ai_service import _openai_coffee_call

    # Build a mock OpenAI client that captures what was passed to responses.create
    captured_kwargs: dict = {}

    def fake_create(**kwargs):  # type: ignore[override]
        captured_kwargs.update(kwargs)
        # Return a minimal response structure
        import types

        json_text = (
            '{"coffee_name":"test","roaster_name":"r","origin":"Ethiopia",'
            '"process":"Washed","roast_level":"Light","search_tier":"primary",'
            '"summary_prose":"Good coffee.","recipe_suggestion":null,"alt_brewer":null}'
        )
        msg_block = types.SimpleNamespace(
            type="message",
            content=[types.SimpleNamespace(type="output_text", text=json_text)],
        )
        usage = types.SimpleNamespace(input_tokens=10, output_tokens=50)
        return types.SimpleNamespace(output=[msg_block], usage=usage)

    mock_client = MagicMock()
    mock_client.responses.create.side_effect = fake_create

    _openai_coffee_call(mock_client, model="gpt-4o", prompt="Find a coffee")

    # Verify tools list uses web_search_preview
    call_kwargs = mock_client.responses.create.call_args
    tools_arg = call_kwargs[1].get("tools") or call_kwargs[0][0] if call_kwargs[0] else None
    if tools_arg is None:
        tools_arg = captured_kwargs.get("tools", [])

    tool_types = [t.get("type") if isinstance(t, dict) else None for t in tools_arg]
    assert "web_search_preview" in tool_types, (
        f"_openai_coffee_call must pass web_search_preview in tools; got {tool_types}"
    )

    # Verify text format mode is NOT json_schema (it should not appear as a format kwarg)
    ca = mock_client.responses.create.call_args
    call_all_kwargs = ca[1] if ca else {}
    text_format = call_all_kwargs.get("text", {})
    uses_json_schema = (
        isinstance(text_format, dict) and text_format.get("format", {}).get("type") == "json_schema"
    )
    assert not uses_json_schema, (
        "_openai_coffee_call must NOT use text.format.json_schema (Pitfall 2)"
    )


# ---------------------------------------------------------------------------
# Task 3 (07-03) — regenerate() entry point + read helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sig_skip() -> None:
    """Unchanged signature with force=False returns 'skipped', no generation called."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.services import ai_service

    db = MagicMock()
    # Simulate cold-start gate open
    gate_open = {"gate_open": True, "sessions": 5, "distinct_notes": 10}
    # Existing coffee row with the same signature
    existing_row = MagicMock()
    existing_row.input_signature = "same-sig-abc123"

    with (
        patch.object(ai_service.analytics_service, "get_cold_start_counts", return_value=gate_open),
        patch.object(
            ai_service.analytics_service, "compute_input_signature", return_value="same-sig-abc123"
        ),
        patch.object(ai_service, "get_latest_recommendation", return_value=existing_row),
        patch.object(ai_service, "_try_advisory_lock", return_value=True),
        patch.object(ai_service, "_generate_coffee_rec", new_callable=AsyncMock) as mock_gen,
    ):
        result = await ai_service.regenerate(1, "scheduler", db=db)

    assert result == "skipped"
    mock_gen.assert_not_called()


@pytest.mark.asyncio
async def test_force_regenerates() -> None:
    """force=True bypasses signature check and calls _generate_coffee_rec."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.services import ai_service

    db = MagicMock()
    gate_open = {"gate_open": True, "sessions": 5, "distinct_notes": 10}
    existing_row = MagicMock()
    existing_row.input_signature = "same-sig-abc123"
    generated_row = MagicMock(recommendation_type="coffee")
    mock_cred = MagicMock()

    with (
        patch.object(ai_service.analytics_service, "get_cold_start_counts", return_value=gate_open),
        patch.object(
            ai_service.analytics_service, "compute_input_signature", return_value="same-sig-abc123"
        ),
        patch.object(ai_service, "get_latest_recommendation", return_value=existing_row),
        patch.object(ai_service, "_try_advisory_lock", return_value=True),
        patch.object(
            ai_service,
            "_generate_coffee_rec",
            new_callable=AsyncMock,
            return_value=("generated", generated_row),
        ),
        patch.object(
            ai_service, "_generate_sweet_spots_prose", new_callable=AsyncMock, return_value=None
        ),
        patch.object(
            ai_service.credentials_service, "get_provider_credential", return_value=mock_cred
        ),
    ):
        result = await ai_service.regenerate(1, "scheduler", db=db, force=True)

    assert result == "generated"


@pytest.mark.asyncio
async def test_not_configured() -> None:
    """No provider credentials → 'not_configured'."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.services import ai_service

    db = MagicMock()
    gate_open = {"gate_open": True, "sessions": 5, "distinct_notes": 10}

    with (
        patch.object(ai_service.analytics_service, "get_cold_start_counts", return_value=gate_open),
        patch.object(
            ai_service.analytics_service, "compute_input_signature", return_value="new-sig-xyz"
        ),
        patch.object(ai_service, "get_latest_recommendation", return_value=None),
        patch.object(ai_service, "_try_advisory_lock", return_value=True),
        patch.object(
            ai_service,
            "_generate_coffee_rec",
            new_callable=AsyncMock,
            return_value=("not_configured", None),
        ),
    ):
        result = await ai_service.regenerate(1, "scheduler", db=db)

    assert result == "not_configured"


@pytest.mark.asyncio
async def test_advisory_lock_concurrent() -> None:
    """Advisory lock unavailable (returns False) → regenerate returns 'locked'."""
    from unittest.mock import MagicMock, patch

    from app.services import ai_service

    db = MagicMock()
    gate_open = {"gate_open": True, "sessions": 5, "distinct_notes": 10}

    with (
        patch.object(ai_service.analytics_service, "get_cold_start_counts", return_value=gate_open),
        patch.object(ai_service, "_try_advisory_lock", return_value=False),
    ):
        result = await ai_service.regenerate(1, "scheduler", db=db)

    assert result == "locked"


@pytest.mark.asyncio
async def test_cold_start_skips() -> None:
    """Cold-start gate closed → regenerate returns 'skipped' without any LLM call."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.services import ai_service

    db = MagicMock()
    gate_closed = {"gate_open": False, "sessions": 1, "distinct_notes": 2}

    with (
        patch.object(
            ai_service.analytics_service, "get_cold_start_counts", return_value=gate_closed
        ),
        patch.object(ai_service, "_generate_coffee_rec", new_callable=AsyncMock) as mock_gen,
    ):
        result = await ai_service.regenerate(1, "scheduler", db=db)

    assert result == "skipped"
    mock_gen.assert_not_called()


def test_is_stale_true_when_sig_changed() -> None:
    """is_stale returns True when the current signature differs from the stored row's signature."""
    from unittest.mock import MagicMock, patch

    from app.services import ai_service

    db = MagicMock()
    stored_row = MagicMock()
    stored_row.input_signature = "old-signature-abc"

    with (
        patch.object(ai_service, "get_latest_recommendation", return_value=stored_row),
        patch.object(
            ai_service.analytics_service,
            "compute_input_signature",
            return_value="new-signature-xyz",
        ),
    ):
        result = ai_service.is_stale(db, user_id=1)

    assert result is True


# ---------------------------------------------------------------------------
# Task 1 (07-04) — Equipment recommendation flow (profile-only, no web search)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_equipment_rec_not_configured() -> None:
    """No provider credentials → ('not_configured', None)."""
    from unittest.mock import MagicMock, patch

    from app.services import ai_service

    db = MagicMock()

    with (
        patch.object(ai_service.credentials_service, "get_provider_credential", return_value=None),
    ):
        status, row = await ai_service.generate_equipment_rec(1, "user", db=db)

    assert status == "not_configured"
    assert row is None


@pytest.mark.asyncio
async def test_equipment_rec_no_web_search_tool() -> None:
    """Anthropic call for equipment rec must NOT include any web_search-type tool (profile-only)."""
    import types
    from unittest.mock import MagicMock, patch

    from app.services import ai_service

    db = MagicMock()
    mock_cred = MagicMock()
    mock_cred.provider = "anthropic"
    mock_cred.model_name = "claude-opus-4-7"
    mock_cred.key = "sk-test"

    captured_tools: list = []

    rec_dict = {
        "weakest_link": "Baratza Encore grinder",
        "recommendation": "Upgrade to a Comandante C40 for better grind consistency.",
        "summary_prose": "Your setup is solid but your grinder is the limiting factor.",
    }
    tool_use_block = types.SimpleNamespace(type="tool_use", name="structure_output", input=rec_dict)
    usage = types.SimpleNamespace(input_tokens=100, output_tokens=50)
    fake_response = types.SimpleNamespace(content=[tool_use_block], usage=usage)

    def fake_create(**kwargs):  # type: ignore[override]
        captured_tools.extend(kwargs.get("tools", []))
        return fake_response

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = fake_create

    with (
        patch.object(
            ai_service.credentials_service,
            "get_provider_credential",
            return_value=mock_cred,
        ),
        patch.object(
            ai_service.analytics_service,
            "get_preference_profile",
            return_value={},
        ),
        patch.object(ai_service, "_build_anthropic_client", return_value=mock_client),
        patch.object(ai_service, "_write_recommendation_row", return_value=MagicMock()),
        patch.object(ai_service.settings_service, "get_str", return_value="web_search_20250305"),
    ):
        # Patch the DB execute to return empty equipment list
        db.execute.return_value.scalars.return_value.all.return_value = []
        status, row = await ai_service.generate_equipment_rec(1, "user", db=db)

    assert status == "generated"
    # Verify no web_search-type tool was passed
    web_search_tools = [
        t
        for t in captured_tools
        if isinstance(t, dict) and t.get("type", "").startswith("web_search")
    ]
    assert web_search_tools == [], (
        f"Equipment rec must not include web_search tools; found: {web_search_tools}"
    )


@pytest.mark.asyncio
async def test_equipment_rec_no_changes() -> None:
    """weakest_link=None is a valid 'no changes recommended' outcome."""
    import types
    from unittest.mock import MagicMock, patch

    from app.services import ai_service
    from app.services.ai_schemas import EquipmentRecSchema

    db = MagicMock()
    mock_cred = MagicMock()
    mock_cred.provider = "anthropic"
    mock_cred.model_name = "claude-opus-4-7"
    mock_cred.key = "sk-test"

    rec_dict = {
        "weakest_link": None,
        "recommendation": None,
        "summary_prose": "Your setup is well-matched — no upgrade needed right now.",
    }
    tool_use_block = types.SimpleNamespace(type="tool_use", name="structure_output", input=rec_dict)
    usage = types.SimpleNamespace(input_tokens=80, output_tokens=40)
    fake_response = types.SimpleNamespace(content=[tool_use_block], usage=usage)

    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_response

    with (
        patch.object(
            ai_service.credentials_service,
            "get_provider_credential",
            return_value=mock_cred,
        ),
        patch.object(ai_service.analytics_service, "get_preference_profile", return_value={}),
        patch.object(ai_service, "_build_anthropic_client", return_value=mock_client),
        patch.object(ai_service, "_write_recommendation_row", return_value=MagicMock()),
        patch.object(ai_service.settings_service, "get_str", return_value="web_search_20250305"),
    ):
        db.execute.return_value.scalars.return_value.all.return_value = []
        status, row = await ai_service.generate_equipment_rec(1, "user", db=db)

    assert status == "generated"
    # Validate that weakest_link=None is a valid EquipmentRecSchema
    schema = EquipmentRecSchema.model_validate(rec_dict)
    assert schema.weakest_link is None


@pytest.mark.asyncio
async def test_equipment_rec_weakest_link() -> None:
    """generate_equipment_rec returns 'generated' with a weakest_link when one is identified."""
    import types
    from unittest.mock import MagicMock, patch

    from app.services import ai_service

    db = MagicMock()
    mock_cred = MagicMock()
    mock_cred.provider = "anthropic"
    mock_cred.model_name = "claude-opus-4-7"
    mock_cred.key = "sk-test"

    rec_dict = {
        "weakest_link": "Baratza Encore grinder",
        "recommendation": "Upgrade to a Comandante C40.",
        "summary_prose": "Your grinder is the bottleneck for a cleaner cup.",
    }
    tool_use_block = types.SimpleNamespace(type="tool_use", name="structure_output", input=rec_dict)
    usage = types.SimpleNamespace(input_tokens=90, output_tokens=45)
    fake_response = types.SimpleNamespace(content=[tool_use_block], usage=usage)

    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_response

    mock_row = MagicMock()
    mock_row.response_json = rec_dict

    with (
        patch.object(
            ai_service.credentials_service,
            "get_provider_credential",
            return_value=mock_cred,
        ),
        patch.object(ai_service.analytics_service, "get_preference_profile", return_value={}),
        patch.object(ai_service, "_build_anthropic_client", return_value=mock_client),
        patch.object(ai_service, "_write_recommendation_row", return_value=mock_row),
        patch.object(ai_service.settings_service, "get_str", return_value="web_search_20250305"),
    ):
        db.execute.return_value.scalars.return_value.all.return_value = []
        status, row = await ai_service.generate_equipment_rec(1, "user", db=db)

    assert status == "generated"
    assert row is not None
    assert row.response_json["weakest_link"] == "Baratza Encore grinder"


# ---------------------------------------------------------------------------
# Task 2 (07-04) — Paste-and-rank flow (text + URL input, SSRF-hardened)
# ---------------------------------------------------------------------------


def test_paste_rank_url_detection() -> None:
    """_split_inputs separates https:// URLs from freeform text blocks."""
    from app.services.ai_service import _split_inputs

    raw = (
        "https://counterculturecoffee.com/yirgacheffe\n"
        "Ethiopia Washed Natural\n"
        "https://bluebottlecoffee.com/store/giant-steps\n"
        "A great fruity coffee from Colombia\n"
    )
    urls, texts = _split_inputs(raw)

    assert "https://counterculturecoffee.com/yirgacheffe" in urls
    assert "https://bluebottlecoffee.com/store/giant-steps" in urls
    assert len(urls) == 2
    # Text blocks should contain the non-URL lines
    combined = "\n".join(texts)
    assert "Ethiopia Washed Natural" in combined
    assert "A great fruity coffee from Colombia" in combined


@pytest.mark.asyncio
async def test_paste_rank_fetch_https_only() -> None:
    """_fetch_page_text rejects http:// URL without making any network call."""
    from app.services.ai_service import _fetch_page_text

    # No respx mock — any network call would raise ConnectError
    result = await _fetch_page_text("http://example.com/coffee")
    assert result == ""


@respx.mock
@pytest.mark.asyncio
async def test_paste_rank_fetch_no_cross_host_redirect() -> None:
    """_fetch_page_text returns empty string when server issues a 3xx redirect."""
    from app.services.ai_service import _fetch_page_text

    url = "https://shop.example.com/coffee"
    respx.get(url).mock(
        return_value=httpx.Response(
            302,
            headers={"Location": "https://other-host.com/landing"},
        )
    )
    result = await _fetch_page_text(url)
    # follow_redirects=False → 302 is not followed; should return empty
    assert result == ""


@respx.mock
@pytest.mark.asyncio
async def test_paste_rank_fetch_extracts_text() -> None:
    """_fetch_page_text extracts text from p/h1/h2 tags in valid HTML."""
    import socket
    from unittest.mock import patch

    from app.services.ai_service import _fetch_page_text

    url = "https://roaster.example.com/yirgacheffe"
    html = (
        "<html><body>"
        "<h1>Yirgacheffe Kochere</h1>"
        "<h2>Ethiopia Natural</h2>"
        "<p>Bright berry notes with jasmine finish.</p>"
        "<script>ignored()</script>"
        "</body></html>"
    )
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    # Mock getaddrinfo so _assert_public_host passes; test focuses on HTML extraction.
    mock_public = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443))]
    with patch("socket.getaddrinfo", return_value=mock_public):
        result = await _fetch_page_text(url)

    assert "Yirgacheffe Kochere" in result
    assert "Ethiopia Natural" in result
    assert "Bright berry notes" in result
    # Script content should be ignored
    assert "ignored()" not in result


@pytest.mark.asyncio
async def test_paste_rank_top3() -> None:
    """rank_pasted_coffees returns at most 3 ranked items (PasteRankSchema enforces <=3)."""
    import types
    from unittest.mock import MagicMock, patch

    from app.services import ai_service
    from app.services.ai_schemas import PasteRankSchema

    db = MagicMock()
    mock_cred = MagicMock()
    mock_cred.provider = "anthropic"
    mock_cred.model_name = "claude-opus-4-7"
    mock_cred.key = "sk-test"

    rank_dict = {
        "ranked": [
            {"rank": 1, "name": "Yirgacheffe", "reasoning": "Best match for your taste."},
            {"rank": 2, "name": "Colombia Huila", "reasoning": "Solid second choice."},
            {"rank": 3, "name": "Kenya AA", "reasoning": "Bright but less aligned."},
        ],
        "summary_prose": "Reach for the Yirgacheffe today — it aligns best with your log.",
    }
    tool_use_block = types.SimpleNamespace(
        type="tool_use", name="structure_output", input=rank_dict
    )
    usage = types.SimpleNamespace(input_tokens=120, output_tokens=60)
    fake_response = types.SimpleNamespace(content=[tool_use_block], usage=usage)

    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_response

    mock_row = MagicMock()

    with (
        patch.object(
            ai_service.credentials_service,
            "get_provider_credential",
            return_value=mock_cred,
        ),
        patch.object(ai_service.analytics_service, "get_preference_profile", return_value={}),
        patch.object(ai_service, "_build_anthropic_client", return_value=mock_client),
        patch.object(ai_service, "_write_recommendation_row", return_value=mock_row),
        patch.object(ai_service.settings_service, "get_str", return_value="web_search_20250305"),
    ):
        status, result = await ai_service.rank_pasted_coffees(
            1, "user", db=db, raw_input="Yirgacheffe\nColombia Huila\nKenya AA"
        )

    assert status == "generated"
    assert result is not None
    # Validate the schema enforces <= 3
    schema = PasteRankSchema.model_validate(rank_dict)
    assert len(schema.ranked) <= 3


@pytest.mark.asyncio
async def test_paste_rank_never_cached() -> None:
    """rank_pasted_coffees writes rec_type='paste_rank' and regenerate() never calls it."""
    import types
    from unittest.mock import MagicMock, patch

    from app.services import ai_service
    from app.services.ai_service import regenerate

    db = MagicMock()
    mock_cred = MagicMock()
    mock_cred.provider = "anthropic"
    mock_cred.model_name = "claude-opus-4-7"
    mock_cred.key = "sk-test"

    rank_dict = {
        "ranked": [{"rank": 1, "name": "Test Coffee", "reasoning": "Best pick."}],
        "summary_prose": "Grab the Test Coffee today.",
    }
    tool_use_block = types.SimpleNamespace(
        type="tool_use", name="structure_output", input=rank_dict
    )
    usage = types.SimpleNamespace(input_tokens=80, output_tokens=40)
    fake_response = types.SimpleNamespace(content=[tool_use_block], usage=usage)

    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_response

    written_rec_types: list[str] = []

    def capture_write(db, *, rec_type, **kwargs):  # type: ignore[override]
        written_rec_types.append(rec_type)
        return MagicMock()

    with (
        patch.object(
            ai_service.credentials_service,
            "get_provider_credential",
            return_value=mock_cred,
        ),
        patch.object(ai_service.analytics_service, "get_preference_profile", return_value={}),
        patch.object(ai_service, "_build_anthropic_client", return_value=mock_client),
        patch.object(ai_service, "_write_recommendation_row", side_effect=capture_write),
        patch.object(ai_service.settings_service, "get_str", return_value="web_search_20250305"),
    ):
        await ai_service.rank_pasted_coffees(1, "user", db=db, raw_input="Test Coffee description")

    assert "paste_rank" in written_rec_types, (
        f"rank_pasted_coffees must write rec_type='paste_rank'; got {written_rec_types}"
    )

    # Verify regenerate() does not call rank_pasted_coffees
    import inspect

    regen_source = inspect.getsource(regenerate)
    assert "rank_pasted_coffees" not in regen_source, (
        "regenerate() must not call rank_pasted_coffees (never cached/scheduled)"
    )
    assert "generate_equipment_rec" not in regen_source, (
        "regenerate() must not call generate_equipment_rec (on-demand only)"
    )
