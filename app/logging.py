"""Structured logging configuration — owned by Phase 0 (Plan 00-02).

This module exports :func:`configure_logging`, the single entry point every
process uses to set up structlog + stdlib logging. Plan 04's ``app/main.py``
lifespan startup calls it with ``settings.LOG_FORMAT`` / ``settings.LOG_LEVEL``;
nothing else should call it.

What it does
------------
- Routes structlog AND stdlib loggers (uvicorn.error, uvicorn.access,
  SQLAlchemy, FastAPI, anything else acquired via :mod:`logging`) through one
  :class:`structlog.stdlib.ProcessorFormatter` so every log line emits the same
  shape on a single stdout stream.
- Default format is JSON (``LOG_FORMAT=json`` per CONTEXT D-16); set
  ``LOG_FORMAT=console`` to swap to :class:`structlog.dev.ConsoleRenderer`
  (color-on-TTY) for developer ergonomics.
- Every emit carries ``event``, ``timestamp_iso``, and ``level`` keys
  (CONTEXT D-16, FOUND-11). Phase 1 adds a request-correlation middleware that
  binds ``request_id`` onto the contextvars chain already present here — no
  structlog re-configuration needed when that lands.

Redaction
---------
A minimal deny-list redactor (:func:`_redact_sensitive_keys`) sits in the
``pre_chain`` between :func:`structlog.stdlib.add_log_level` and
:class:`structlog.stdlib.ExtraAdder`. It scrubs top-level event-dict keys
whose name matches the Phase 0 deny-list (case-insensitive) by replacing the
value with the literal string ``"<redacted>"`` — the key is kept so reviewers
can see "we knew this field could be sensitive." This is the ASVS V7 / threat
T-00-02-01 mitigation for Phase 0. Phase 1 extends the deny-list (cookies,
CSRF tokens, Stripe webhooks, etc.) and adds a separate body-redaction
middleware for FastAPI access-log records.

NEVER log a secret value inside this module itself.
"""

from __future__ import annotations

import logging
import logging.config
import sys
from typing import Any

import structlog

# Deny-list of top-level event-dict keys whose VALUES are scrubbed before
# emission. Names are matched case-insensitively (``Password`` matches as
# readily as ``password``). The list is intentionally minimal in Phase 0;
# Phase 1 extends it in the same processor.
_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "password_hash",
        "api_key",
        "api_token",
        "authorization",
        "cookie",
        "session_id",
        "secret",
        "secret_key",
        "encryption_key",
    }
)


def _redact_sensitive_keys(
    logger: Any,  # noqa: ARG001 — structlog processor signature
    method_name: str,  # noqa: ARG001 — structlog processor signature
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Scrub deny-listed top-level keys to ``"<redacted>"``.

    Walks only the top-level keys of ``event_dict`` — Phase 0 does not log
    nested PII, and a recursive walk would risk mutating unrelated data
    structures the caller passed by reference. Phase 1's body-redaction
    middleware handles structured request/response bodies.

    Returns the (possibly mutated) ``event_dict`` so structlog continues the
    processor chain.
    """
    for key in list(event_dict.keys()):
        if key.lower() in _SENSITIVE_KEYS:
            event_dict[key] = "<redacted>"
    return event_dict


def configure_logging(format: str = "json", level: str = "INFO") -> None:  # noqa: A002 — `format` is the CONTEXT D-16 vocabulary
    """Configure structlog + stdlib logging.

    Args:
        format: Renderer selector. ``"console"`` selects
            :class:`structlog.dev.ConsoleRenderer`; any other value (default
            ``"json"``) selects :class:`structlog.processors.JSONRenderer`.
        level: Log level name (``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``)
            applied to root, ``uvicorn.error``, and ``uvicorn.access``.

    Idempotent: re-invoking this function reconfigures structlog and
    re-applies :func:`logging.config.dictConfig`. ``disable_existing_loggers``
    is ``False`` so test fixtures (pytest's ``caplog``) and any logger already
    acquired by another module survive a re-call.
    """
    # Processor chain shared between the structlog frontend and the stdlib
    # ProcessorFormatter foreign_pre_chain. Order matters:
    #   1. merge_contextvars — pulls Phase 1's request_id (and future bindings)
    #      into the event dict so downstream processors see them.
    #   2. add_log_level — adds the ``level`` key (lower-case string).
    #   3. _redact_sensitive_keys — scrubs deny-listed keys BEFORE rendering
    #      so neither JSON nor console output ever serializes a secret.
    #   4. ExtraAdder — copies ``LogRecord.extra`` kwargs (the
    #      ``logger.info("...", extra={"k": v})`` path used by uvicorn etc.)
    #      into the event dict so they appear alongside structlog kwargs.
    #   5. TimeStamper — ISO-8601 timestamp under the key ``timestamp_iso``
    #      (the key name is the FOUND-11 / CONTEXT D-16 contract).
    timestamper = structlog.processors.TimeStamper(fmt="iso", key="timestamp_iso")
    pre_chain: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        _redact_sensitive_keys,
        structlog.stdlib.ExtraAdder(),
        timestamper,
    ]

    if format == "console":
        renderer: Any = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=pre_chain
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logging.config.dictConfig(
        {
            "version": 1,
            # Keep existing loggers alive across re-config (test fixtures,
            # modules that already acquired ``logging.getLogger(__name__)``).
            "disable_existing_loggers": False,
            "formatters": {
                "structured": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    # ``remove_processors_meta`` strips structlog's internal
                    # ``_record`` / ``_from_structlog`` keys before the
                    # terminal renderer runs.
                    "processors": [
                        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                        renderer,
                    ],
                    "foreign_pre_chain": pre_chain,
                },
            },
            "handlers": {
                "stdout": {
                    "class": "logging.StreamHandler",
                    "formatter": "structured",
                    "stream": sys.stdout,
                },
            },
            "loggers": {
                # Root logger — anything not explicitly routed below ends up
                # here. ``propagate=True`` is harmless because the root has
                # its own handler.
                "": {"handlers": ["stdout"], "level": level, "propagate": True},
                # uvicorn emits two streams: ``error`` for app/server events
                # and ``access`` for per-request access logs. Both go through
                # the same structured handler so the JSON shape is uniform.
                # ``propagate=False`` prevents double-emission via root.
                "uvicorn.error": {
                    "handlers": ["stdout"],
                    "level": level,
                    "propagate": False,
                },
                "uvicorn.access": {
                    "handlers": ["stdout"],
                    "level": level,
                    "propagate": False,
                },
            },
        }
    )
