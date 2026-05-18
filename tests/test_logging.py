"""FOUND-11: structlog emits JSON with ``event``, ``timestamp_iso``, ``level``.

These tests pin the CONTEXT D-16 contract and prove the Phase 1
``request_id`` binding seat is in place. Removing any of the load-bearing
processors (``contextvars.merge_contextvars``, ``add_log_level``,
``_redact_sensitive_keys``, ``ExtraAdder``, ``TimeStamper(key="timestamp_iso")``)
from ``app/logging.py`` causes one of these tests to fail with a precise
diagnostic.

Each test captures emitted log records by attaching an in-memory
:class:`logging.StreamHandler` (wrapping an :class:`io.StringIO`) to the
root logger. The handler is given the formatter from the configured
``stdout`` handler so it sees the same structured / JSON output that
production stdout receives, without forcing the test to read from the real
stdout stream.
"""

from __future__ import annotations

import io
import json
import logging
import re
from collections.abc import Iterator

import pytest
import structlog

from app.logging import configure_logging

# Loose ISO-8601 check — ``2026-05-17T14:58:21.532208Z`` matches; full
# RFC-3339 strictness isn't required because structlog's TimeStamper always
# emits ``YYYY-MM-DDTHH:MM:SS...``.
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def _attach_capture_handler() -> tuple[io.StringIO, logging.Handler]:
    """Attach an in-memory handler to the root logger.

    Returns the buffer and the handler so the caller can read the buffer
    and remove the handler when finished. The handler reuses the formatter
    from the first configured root handler so structured / JSON output is
    preserved.
    """
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    root = logging.getLogger()
    # Copy the configured structured formatter from the existing handler so
    # the captured output matches what stdout would see in production.
    for existing in root.handlers:
        if existing.formatter is not None:
            handler.setFormatter(existing.formatter)
            break
    root.addHandler(handler)
    return buf, handler


@pytest.fixture(autouse=True)
def _clean_logging_state() -> Iterator[None]:
    """Reset logging + structlog contextvars state between tests.

    Without this fixture, a test that binds ``request_id`` could leak that
    binding into the next test's emit. The fixture also strips capture
    handlers that previous tests left attached — ``configure_logging``
    rebuilds the dictConfig-owned handlers each call, but capture handlers
    added via ``_attach_capture_handler`` persist.
    """
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()
    # Drop any StringIO-backed handlers a test forgot to detach.
    root = logging.getLogger()
    for h in list(root.handlers):
        if isinstance(h, logging.StreamHandler) and isinstance(h.stream, io.StringIO):
            root.removeHandler(h)


def _last_json_record(buf: io.StringIO) -> dict[str, object]:
    """Parse the last non-empty line of ``buf`` as JSON."""
    lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
    assert lines, "no log lines captured"
    return json.loads(lines[-1])


def test_json_renderer_shape() -> None:
    """Every JSON emit carries event, timestamp_iso, level + extra kwargs."""
    configure_logging(format="json", level="INFO")
    buf, _ = _attach_capture_handler()

    structlog.get_logger("test").info("hello world", extra_key="x")

    record = _last_json_record(buf)
    assert record["event"] == "hello world"
    assert record["level"] == "info"  # structlog convention — lower-case
    assert "timestamp_iso" in record
    assert isinstance(record["timestamp_iso"], str)
    assert _ISO_RE.match(record["timestamp_iso"]), (
        f"timestamp_iso not ISO-8601: {record['timestamp_iso']!r}"
    )
    # Proves ExtraAdder + structlog kwargs both make it through pre_chain.
    assert record["extra_key"] == "x"


def test_console_renderer_when_format_is_console() -> None:
    """LOG_FORMAT=console produces ANSI/plaintext, NOT JSON."""
    configure_logging(format="console", level="INFO")
    buf, _ = _attach_capture_handler()

    structlog.get_logger("test").info("console mode")

    lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
    assert lines, "no log lines captured"
    # ConsoleRenderer emits ANSI-coded plaintext — parsing as JSON must fail.
    with pytest.raises(json.JSONDecodeError):
        json.loads(lines[-1])


def test_configure_logging_is_idempotent() -> None:
    """Two consecutive configure_logging calls do not duplicate emits."""
    configure_logging("json", "INFO")
    configure_logging("json", "INFO")
    buf, _ = _attach_capture_handler()

    structlog.get_logger("test").info("solo")

    lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
    # Exactly one JSON record — not two. A duplicate-handler regression
    # (caused e.g. by a missing disable_existing_loggers=False) would show
    # up here as len(lines) == 2.
    assert len(lines) == 1, f"expected 1 emit, got {len(lines)}: {lines!r}"
    parsed = json.loads(lines[0])
    assert parsed["event"] == "solo"


def test_contextvars_processor_present_in_chain() -> None:
    """Phase 1's request_id binding flows through to the JSON output.

    This proves ``structlog.contextvars.merge_contextvars`` is wired into
    ``pre_chain``. Removing that processor causes the bound ``request_id``
    to silently drop, which this test catches.
    """
    configure_logging("json", "INFO")
    buf, _ = _attach_capture_handler()

    try:
        structlog.contextvars.bind_contextvars(request_id="abc-123")
        structlog.get_logger("test").info("with-rid")
    finally:
        structlog.contextvars.clear_contextvars()

    record = _last_json_record(buf)
    assert record["request_id"] == "abc-123"
    assert record["event"] == "with-rid"


def test_redactor_scrubs_sensitive_keys() -> None:
    """Deny-listed keys are scrubbed in BOTH JSON and console renderers."""
    # --- JSON renderer ---
    configure_logging("json", "INFO")
    buf, _ = _attach_capture_handler()

    structlog.get_logger("test").info(
        "auth-event",
        password="secret123",
        api_key="sk-abc",
        username="alice",
    )

    record = _last_json_record(buf)
    assert record["password"] == "***REDACTED***"
    assert record["api_key"] == "***REDACTED***"
    # Non-sensitive keys pass through untouched — the redactor must NOT
    # over-match.
    assert record["username"] == "alice"
    # And the literal secret values must not appear ANYWHERE in the raw
    # JSON line — defense against e.g. a value-side leak.
    raw = buf.getvalue()
    assert "secret123" not in raw, "redactor leaked password value into JSON output"
    assert "sk-abc" not in raw, "redactor leaked api_key value into JSON output"

    # --- Console renderer ---
    configure_logging("console", "INFO")
    buf2, _ = _attach_capture_handler()

    structlog.get_logger("test").info(
        "auth-event-console",
        password="secret123",
        api_key="sk-abc",
        username="alice",
    )
    console_out = buf2.getvalue()
    assert "***REDACTED***" in console_out
    assert "secret123" not in console_out, (
        "redactor leaked password value into console output"
    )
    assert "sk-abc" not in console_out, (
        "redactor leaked api_key value into console output"
    )
    # Case-insensitivity check — uppercase key names should also be scrubbed.
    buf3, _ = _attach_capture_handler()
    structlog.get_logger("test").info("upper", PASSWORD="UPPER-SECRET")
    assert "UPPER-SECRET" not in buf3.getvalue()


# --------------------------------------------------------------------------- #
# Plan 02-10 — D-15 reason-field assertions for the real /login handler       #
# --------------------------------------------------------------------------- #
#
# These tests were originally Task 5 of Plan 02-07; they were lifted into
# Plan 02-10 during plan-checker revision so 02-07 stays under the 5-task
# threshold. They target the real ``/login`` handler (Plan 02-07 Task 2)
# so they cannot run until 02-07 is merged — which is the case in Wave 5.
#
# D-15 logging policy (Phase 1 carried, asserted here on the real handler):
#   * auth.login_failed reason=user_not_found  → NO user_id, NO attempted_username
#   * auth.login_failed reason=bad_password    → user_id, NO attempted_username
#   * auth.login_failed reason=inactive        → user_id, NO attempted_username
#
# The handler emits the lines via ``log.info(AUTH_LOGIN_FAILED, ...)`` per
# the contract in ``app/routers/auth.py`` module docstring.


def test_login_failed_no_username_on_user_not_found(client) -> None:
    """D-15: ``reason=user_not_found`` has NO ``user_id`` and NO ``attempted_username``."""
    try:
        from app.routers.auth import router  # noqa: F401
    except ImportError:
        pytest.skip("Wave 4 dep: app.routers.auth (Plan 02-07)")
    configure_logging(format="json", level="INFO")
    buf, _ = _attach_capture_handler()
    # Prime the CSRF cookie via a safe GET so the POST is not blocked by
    # CSRFMiddleware before the handler runs (sensitive_cookies only fires
    # when session_id is present, but priming covers both code paths).
    primer = client.get("/")
    token = primer.cookies.get("csrftoken")
    if not token:
        pytest.skip("CSRF cookie not primed by GET /")
    client.post(
        "/login",
        data={
            "X-CSRF-Token": token,
            "username": "no-such-user-exists",
            "password": "twelve-chars-min-password",
        },
        headers={"X-CSRF-Token": token},
        cookies={"csrftoken": token},
    )
    # Find the auth.login_failed line emitted by the handler.
    lines = [
        json.loads(ln)
        for ln in buf.getvalue().splitlines()
        if ln.strip() and "auth.login_failed" in ln
    ]
    assert lines, f"no auth.login_failed event captured; raw buf: {buf.getvalue()!r}"
    record = lines[-1]
    assert record["event"] == "auth.login_failed"
    assert record["reason"] == "user_not_found"
    assert "user_id" not in record, (
        "D-15: user_not_found branch must NOT log user_id; "
        f"got record: {record!r}"
    )
    assert "attempted_username" not in record, (
        "D-15: never log attempted_username; "
        f"got record: {record!r}"
    )


def test_login_failed_includes_user_id_on_bad_password(
    client, seeded_regular_user
) -> None:
    """D-15: ``reason=bad_password`` DOES include ``user_id`` (NO ``attempted_username``)."""
    try:
        from app.routers.auth import router  # noqa: F401
    except ImportError:
        pytest.skip("Wave 4 dep: app.routers.auth (Plan 02-07)")
    configure_logging(format="json", level="INFO")
    buf, _ = _attach_capture_handler()
    primer = client.get("/")
    token = primer.cookies.get("csrftoken")
    if not token:
        pytest.skip("CSRF cookie not primed by GET /")
    client.post(
        "/login",
        data={
            "X-CSRF-Token": token,
            "username": seeded_regular_user["user"].username,
            "password": "WRONG-password-12345",
        },
        headers={"X-CSRF-Token": token},
        cookies={"csrftoken": token},
    )
    lines = [
        json.loads(ln)
        for ln in buf.getvalue().splitlines()
        if ln.strip() and "auth.login_failed" in ln
    ]
    assert lines, f"no auth.login_failed event captured; raw buf: {buf.getvalue()!r}"
    record = lines[-1]
    assert record["event"] == "auth.login_failed"
    assert record["reason"] == "bad_password"
    assert record.get("user_id") == seeded_regular_user["user"].id, (
        f"D-15: bad_password branch must log user_id; got record: {record!r}"
    )
    assert "attempted_username" not in record, (
        "D-15: never log attempted_username; "
        f"got record: {record!r}"
    )
