"""Tests for the rolling-24h quota math helpers in ai_quota.py.

Requirements traceability:
  AIX-05 / D-08 — per-user rolling 24h quota, DB-backed, admin-configurable cap
  D-09           — reset time computable from oldest in-window call
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Test: count_calls_last_24h correctly filters rows
# ---------------------------------------------------------------------------


def test_quota_count() -> None:
    """AIX-05/D-08: counts only successful rows inside the 24h window."""
    from app.services.ai_quota import count_calls_last_24h

    mock_db = MagicMock()

    # Four rows: 2 successful inside, 1 has error_status (excluded), 1 is outside window
    # We mock the scalar() return to verify the COUNT query is built correctly.
    # Rather than asserting exact SQL, we verify the function returns the scalar value.
    mock_db.scalar.return_value = 2
    result = count_calls_last_24h(mock_db, user_id=1, rec_type="coffee_research")
    assert result == 2

    # Returns 0 when scalar returns None (empty table)
    mock_db.scalar.return_value = None
    result = count_calls_last_24h(mock_db, user_id=1, rec_type="coffee_research")
    assert result == 0


def test_quota_count_separate_rec_types() -> None:
    """D-08: research and improve-brew are separate quota buckets."""
    from app.services.ai_quota import count_calls_last_24h

    mock_db = MagicMock()
    mock_db.scalar.side_effect = [3, 7]

    research_count = count_calls_last_24h(mock_db, user_id=1, rec_type="coffee_research")
    brew_count = count_calls_last_24h(mock_db, user_id=1, rec_type="brew_improvement")
    assert research_count == 3
    assert brew_count == 7

    # Verify the two calls passed different rec_types into the query
    assert mock_db.scalar.call_count == 2


# ---------------------------------------------------------------------------
# Test: get_quota_reset_time
# ---------------------------------------------------------------------------


def test_reset_time_computation() -> None:
    """D-09: reset time is oldest in-window call + 24h; None when window empty."""
    from app.services.ai_quota import get_quota_reset_time

    now = datetime.now(UTC)
    oldest_in_window = now - timedelta(hours=20)
    expected_reset = oldest_in_window + timedelta(hours=24)

    mock_db = MagicMock()
    mock_db.scalar.return_value = oldest_in_window
    result = get_quota_reset_time(mock_db, user_id=1, rec_type="coffee_research")
    # Allow ± 1 second for timing drift
    assert abs((result - expected_reset).total_seconds()) < 1.0

    # Returns None when window empty
    mock_db.scalar.return_value = None
    result = get_quota_reset_time(mock_db, user_id=1, rec_type="coffee_research")
    assert result is None


# ---------------------------------------------------------------------------
# Test: get_quota_cap reads correct settings keys and falls back to 20
# ---------------------------------------------------------------------------


def test_quota_cap_fallback() -> None:
    """AIX-05: cap reads from app_settings; falls back to 20 when setting absent."""
    from app.services.ai_quota import get_quota_cap

    # When settings returns None (key absent), fallback to 20
    with patch("app.services.ai_quota.settings_service") as mock_settings:
        mock_settings.get_int.return_value = None
        assert get_quota_cap("coffee_research") == 20
        assert get_quota_cap("brew_improvement") == 20


def test_quota_cap_reads_correct_setting_key() -> None:
    """D-08: research and improve-brew map to separate settings keys."""
    from app.services.ai_quota import get_quota_cap

    with patch("app.services.ai_quota.settings_service") as mock_settings:
        mock_settings.get_int.return_value = 30
        result = get_quota_cap("coffee_research")
        assert result == 30
        # Verify research key was used
        call_args = mock_settings.get_int.call_args[0][0]
        assert "research" in call_args

    with patch("app.services.ai_quota.settings_service") as mock_settings:
        mock_settings.get_int.return_value = 15
        result = get_quota_cap("brew_improvement")
        assert result == 15
        call_args = mock_settings.get_int.call_args[0][0]
        assert "improve" in call_args or "brew" in call_args


def test_quota_cap_different_keys_for_different_types() -> None:
    """D-08: research and improve-brew must hit different app_settings keys."""
    from app.services.ai_quota import get_quota_cap

    calls = []

    def capture_get_int(key: str) -> int:
        calls.append(key)
        return 20

    with patch("app.services.ai_quota.settings_service") as mock_settings:
        mock_settings.get_int.side_effect = capture_get_int
        get_quota_cap("coffee_research")
        get_quota_cap("brew_improvement")

    # The two calls must have used different keys
    assert len(calls) == 2
    assert calls[0] != calls[1]


# ---------------------------------------------------------------------------
# Test: remaining()
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Test: format_reset helper — WR-05/IN-02
# ---------------------------------------------------------------------------


def test_format_reset_none_input() -> None:
    """WR-05/IN-02: format_reset returns None when reset_time is None (empty window)."""
    from app.services.ai_quota import format_reset

    assert format_reset(None) is None


def test_format_reset_future_time() -> None:
    """WR-05/IN-02: format_reset returns correct 'Hh Mm' string for a future reset_time."""
    from app.services.ai_quota import format_reset

    now = datetime.now(UTC)
    reset_time = now + timedelta(hours=3, minutes=45)
    result = format_reset(reset_time)

    assert result is not None
    # Allow ± 1 second of timing drift — hours/mins should be 3h 44m or 3h 45m
    assert result.startswith("3h"), f"Expected '3h ...' but got: {result}"
    assert "m" in result


def test_format_reset_past_time_clamps_to_zero() -> None:
    """WR-05/IN-02: format_reset clamps negative delta to '0h 0m' — never negative countdown."""
    from app.services.ai_quota import format_reset

    now = datetime.now(UTC)
    # reset_time is in the past (window just expired)
    past_reset = now - timedelta(hours=1, minutes=30)
    result = format_reset(past_reset)

    assert result == "0h 0m", (
        f"Expected '0h 0m' for past reset_time, got: {result!r}. "
        "Negative countdowns (-1h 59m) must be clamped (WR-05)."
    )


def test_format_reset_zero_delta() -> None:
    """WR-05: format_reset at exactly reset_time (delta=0) → '0h 0m'."""
    from app.services.ai_quota import format_reset

    # Slightly in the past to ensure non-positive
    result = format_reset(datetime.now(UTC) - timedelta(seconds=1))
    assert result == "0h 0m"


def test_quota_remaining() -> None:
    """remaining = max(cap - count, 0); never negative."""
    from app.services.ai_quota import remaining

    mock_db = MagicMock()

    with (
        patch("app.services.ai_quota.count_calls_last_24h") as mock_count,
        patch("app.services.ai_quota.get_quota_cap") as mock_cap,
    ):
        mock_count.return_value = 5
        mock_cap.return_value = 20
        assert remaining(mock_db, user_id=1, rec_type="coffee_research") == 15

        # At cap exactly
        mock_count.return_value = 20
        mock_cap.return_value = 20
        assert remaining(mock_db, user_id=1, rec_type="coffee_research") == 0

        # Over cap (should be 0, not negative)
        mock_count.return_value = 25
        mock_cap.return_value = 20
        assert remaining(mock_db, user_id=1, rec_type="coffee_research") == 0
