"""Plan 01-02 alias for :mod:`app.logging` — structlog + stdlib configuration.

Plan 01-02 ``<interfaces>`` documents the symbols under the
``app.logging_config`` module path:

- :func:`configure_logging` — the single entry point that wires the
  structlog frontend, the :class:`structlog.stdlib.ProcessorFormatter`
  foreign chain, the redaction processor, and the stdlib root / uvicorn
  handlers. Owned by Phase 0 (Plan 00-02) and lives in :mod:`app.logging`.
- :func:`_redact_sensitive_fields` — the redaction processor for the
  AUTH-10 deny-list. Phase 0 ships the same function as
  :func:`app.logging._redact_sensitive_keys`; Plan 01-02 surfaces it under
  the planned name without renaming the original (preserves Phase 0 test
  coverage at ``tests/test_logging.py`` while making the planned import
  path work).
- :data:`SENSITIVE_KEYS` — the canonical 14-key deny-list (10 Phase 0 keys
  + 4 Plan 01-02 AUTH-10 additions: ``session_token``,
  ``api_key_encrypted``, ``x-csrf-token``, ``csrftoken``).

This module is a thin re-export shim — it intentionally adds no logic so
that ``app.logging`` remains the single source of truth for the logging
contract. Downstream plans (03, 04, 06, 07, 09) may import from either
path; the symbols are the same object identity.

Why a shim rather than a rename?
--------------------------------
Plan 01-01's SUMMARY (Wave 0) recorded the path / suffix drift between the
Phase 1 plan (``app.logging_config._redact_sensitive_fields``) and the
Phase 0 implementation (``app.logging._redact_sensitive_keys``). Renaming
the Phase 0 module would force every Phase 0 caller (``app/main.py``,
``tests/test_logging.py``, the conftest env-bootstrap, etc.) into a
mass-rename commit with no functional benefit. The shim costs one file and
preserves both Phase 0 and Plan 01-02 acceptance criteria simultaneously.

CLAUDE.md "no os.environ outside app/config.py" is honored — neither this
file nor ``app/logging.py`` reads the process environment directly. The
``level`` argument to :func:`configure_logging` is the only configuration
input; ``app/main.py``'s lifespan passes ``settings.LOG_LEVEL`` (and the
existing ``settings.LOG_FORMAT``) at startup.
"""

from __future__ import annotations

from app.logging import (
    SENSITIVE_KEYS,
    _redact_sensitive_fields,
    _redact_sensitive_keys,
    configure_logging,
)

__all__ = [
    "SENSITIVE_KEYS",
    "_redact_sensitive_fields",
    "_redact_sensitive_keys",
    "configure_logging",
]
