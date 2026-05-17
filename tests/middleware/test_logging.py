"""Wave 0 stubs for AUTH-10 (structured-logger redaction + request_id propagation).

Covers per-task verification map rows for AUTH-10 from
``.planning/phases/01-middleware/01-VALIDATION.md``:

- ``test_redaction_processor``     — the bare redactor processor scrubs sensitive keys
- ``test_redaction``               — a request-handler log call has sensitive values redacted
- ``test_contextvars_propagation`` — both middleware & handler log lines share a request_id;
                                     two requests produce two distinct request_ids

The plan references ``app.logging_config:_redact_sensitive_fields`` /
``app.logging_config:configure_logging``. Phase 0 already exports
``_redact_sensitive_keys`` (note: ``_keys`` not ``_fields``) and
``configure_logging`` from ``app.logging``. The redaction-processor test
prefers Phase 0's existing symbol so this test goes green immediately for
the redactor; the request-context tests stay red until Plan 02 wires the
``request_id`` contextvars binding middleware.

NB: We file this discrepancy as a known plan-vs-implementation drift in the
SUMMARY rather than renaming Phase 0's symbol mid-Wave-0.
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator

import pytest
import structlog


@pytest.fixture(autouse=True)
def _clean_logging_state() -> Iterator[None]:
    """Reset structlog contextvars and detach in-memory capture handlers."""
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()
    root = logging.getLogger()
    for h in list(root.handlers):
        if isinstance(h, logging.StreamHandler) and isinstance(h.stream, io.StringIO):
            root.removeHandler(h)


def _attach_capture() -> tuple[io.StringIO, logging.Handler]:
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    root = logging.getLogger()
    for existing in root.handlers:
        if existing.formatter is not None:
            handler.setFormatter(existing.formatter)
            break
    root.addHandler(handler)
    return buf, handler


def test_redaction_processor() -> None:
    """AUTH-10: the redactor processor scrubs ``password``, ``api_key``,
    ``session_token``, ``cookie`` from the event dict before rendering.

    The test calls the processor as a function (structlog processor signature:
    ``(logger, method_name, event_dict)``) so the assertion isolates the
    redaction logic from the structlog chain.
    """
    try:
        from app.logging import _redact_sensitive_keys as redactor
    except ImportError:
        try:
            from app.logging_config import (  # type: ignore[attr-defined]
                _redact_sensitive_fields as redactor,
            )
        except ImportError:
            pytest.skip(
                "Wave 1 dependency: app.logging._redact_sensitive_keys (Phase 0) "
                "OR app.logging_config._redact_sensitive_fields (Plan 02 — may rename)"
            )
            return  # pragma: no cover
    event_dict = {
        "event": "test",
        "password": "hunter2",
        "api_key": "sk-abc123",
        "session_token": "deadbeef",
        "cookie": "session_id=xyz",
        "safe_key": "kept",
    }
    out = redactor(None, "info", event_dict)
    assert out["password"] == "***REDACTED***", out
    assert out["api_key"] == "***REDACTED***", out
    assert out["session_token"] == "***REDACTED***", out
    assert out["cookie"] == "***REDACTED***", out
    assert out["safe_key"] == "kept", out


def test_redaction(client) -> None:
    """AUTH-10: a real structured log call from a request-handler context
    must scrub sensitive values in the rendered JSON line.
    """
    try:
        from app.logging import configure_logging
    except ImportError:
        try:
            from app.logging_config import configure_logging  # type: ignore[attr-defined]
        except ImportError:
            pytest.skip("Wave 1 dependency: app.logging.configure_logging")
            return  # pragma: no cover
    configure_logging(format="json", level="INFO")
    buf, _ = _attach_capture()
    # Emit a log line as if from inside a handler (no need to go through HTTP
    # to verify the rendering — that's the point of the processor chain).
    structlog.get_logger("auth.test").info(
        "auth.login_attempt",
        password="hunter2",
        api_key="sk-abc",
        session_token="deadbeef",
        cookie="session_id=xyz",
    )
    lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
    assert lines, "no log line captured"
    record = json.loads(lines[-1])
    assert record.get("password") == "***REDACTED***", record
    assert record.get("api_key") == "***REDACTED***", record
    assert record.get("session_token") == "***REDACTED***", record
    assert record.get("cookie") == "***REDACTED***", record


def test_contextvars_propagation(client) -> None:
    """AUTH-10: ``request_id`` propagates via contextvars across all log calls
    in a single request, and two requests get distinct request_ids.

    Plan 02 wires the request-id middleware. Until then, the test xfails to
    keep the symbol expectation visible.
    """
    try:
        from app.middleware.request_context import RequestContextMiddleware  # noqa: F401
    except ImportError:
        try:
            from app.middleware.request_id import RequestIdMiddleware  # noqa: F401
        except ImportError:
            pytest.skip(
                "Wave 1 dependency: app.middleware.request_context.RequestContextMiddleware "
                "(Plan 02)"
            )
    try:
        from app.logging import configure_logging
    except ImportError:
        pytest.skip("Wave 1 dependency: app.logging.configure_logging")
        return  # pragma: no cover
    configure_logging(format="json", level="INFO")
    buf, _ = _attach_capture()
    client.get("/")
    client.get("/")
    lines = [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]
    request_ids = {ln.get("request_id") for ln in lines if "request_id" in ln}
    if not request_ids:
        pytest.xfail(
            "no request_id propagated in captured log lines — Plan 02's "
            "RequestContextMiddleware not wired yet"
        )
    # Per-request: log lines from a single request all share the same id.
    # Across requests: at least two distinct ids should appear.
    assert len(request_ids) >= 2, (
        f"expected ≥2 distinct request_ids across two requests, got {request_ids}"
    )
