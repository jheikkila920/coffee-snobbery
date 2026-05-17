---
phase: 0
plan: 02
subsystem: foundation
tags:
  - logging
  - structlog
  - observability
  - wave-2
requirements: [FOUND-11]
dependency_graph:
  requires:
    - "from app.config import settings (Plan 00-01)"
  provides:
    - "from app.logging import configure_logging"
    - "Single-entry structured-logging configuration (JSON default, console flip)"
    - "Pre-chain seat for Phase 1's request_id contextvar binding"
    - "Minimal deny-list redactor (_redact_sensitive_keys) — extended in Phase 1"
  affects:
    - "Plan 00-04: app/main.py lifespan startup calls configure_logging(settings.LOG_FORMAT, settings.LOG_LEVEL)"
    - "Phase 1: RequestIDMiddleware binds onto contextvars chain already wired here"
    - "Phase 1: extends _SENSITIVE_KEYS deny-list (cookie names, CSRF tokens, etc.) + adds body-redaction middleware"
    - "Phase 7: AI cost telemetry logs through this configuration"
    - "Phase 8: scheduler summaries log through this configuration"
    - "Phase 12: audit grep for 'no PII / no request bodies in logs' runs against this configuration"
tech_stack:
  added:
    - "structlog 25.5.0 (wired — was pinned-only in Plan 00-01)"
  patterns:
    - "ProcessorFormatter wiring: structlog frontend + stdlib dictConfig merge into one stdout JSON stream"
    - "Idempotent configure_logging() with disable_existing_loggers=False for re-config safety"
    - "Deny-list redactor in pre_chain — case-insensitive top-level key match → value replaced with '<redacted>'"
    - "Env-var-controlled renderer (LOG_FORMAT=json|console) — CONTEXT D-16"
key_files:
  created:
    - path: "app/logging.py"
      purpose: "Single configure_logging(format, level) entry point — structlog + stdlib dictConfig wiring"
    - path: "tests/test_logging.py"
      purpose: "FOUND-11 JSON-shape gate + 4 supporting tests (console flip, idempotency, contextvars seat, redactor)"
  modified: []
decisions:
  - "Redactor sits at pre_chain index 2 (between add_log_level and ExtraAdder) so foreign-pre-chain records (uvicorn.access) ALSO get scrubbed before terminal render"
  - "Redactor mutates value to literal '<redacted>' rather than deleting the key — keeping the key signals 'we knew this could be sensitive' to log readers"
  - "Redactor walks top-level keys only — Phase 0 does not log nested PII; Phase 1's body-redaction middleware handles structured bodies"
  - "Default arg to configure_logging is format='json' so any caller that forgets to pass the format still gets the production renderer"
  - "disable_existing_loggers=False — preserves loggers other modules acquired (pytest caplog, sqlalchemy logger that Plan 03 will acquire)"
metrics:
  duration_seconds: 720
  duration_human: "~12m"
  tasks_completed: 2
  files_created: 2
  commits: 2
  completed: "2026-05-17T15:00:00Z"
---

# Phase 0 Plan 02: structlog Logging Configuration — Summary

**One-liner:** `app/logging.py` exports `configure_logging(format, level)` — a single idempotent entry point that wires structlog + stdlib `logging` (uvicorn.error, uvicorn.access, FastAPI, SQLAlchemy) into one JSON stdout stream by default, flips to `ConsoleRenderer` when `LOG_FORMAT=console`, scrubs deny-listed top-level keys to `<redacted>` in both renderers, and already has Phase 1's `request_id` contextvar seat in place — covered by 5 unit tests that pin the FOUND-11 / CONTEXT D-16 contract.

## What Was Built

Plan 00-02 lays down the second of Phase 0's foundational substrates: the structured-logging substrate every later phase emits through. Two files:

1. **`app/logging.py` (185 LOC)** — single function `configure_logging(format: str = "json", level: str = "INFO") -> None`. Calls `structlog.configure(...)` and `logging.config.dictConfig(...)` so every log line (whether emitted via `structlog.get_logger(...)` or stdlib `logging.getLogger(...)`) lands on stdout as one consistent JSON line (or ANSI-colored plaintext when `format="console"`).

2. **`tests/test_logging.py` (202 LOC, 5 tests)** — pins the FOUND-11 contract. All 5 pass; total runtime ~60ms.

## Processor Chain Order (load-bearing — Plan 04 references this)

The `pre_chain` is shared between the structlog frontend and the stdlib `ProcessorFormatter.foreign_pre_chain`, so the order is the order every log record sees regardless of which logger emitted it.

| Index | Processor | Role |
|---|---|---|
| 0 | `structlog.contextvars.merge_contextvars` | Pulls Phase 1's `request_id` (and any future contextvar bindings) into the event dict — the **Phase 1 seat** is here. |
| 1 | `structlog.stdlib.add_log_level` | Adds `level` key (lower-case string per structlog convention). |
| 2 | `_redact_sensitive_keys` (module-private) | Scrubs deny-listed top-level keys to `<redacted>`. Sits BEFORE ExtraAdder so kwargs from `logger.info("...", password=x)` are scrubbed; sits AFTER add_log_level so the `level` key isn't accidentally matched. **For Phase 1 maintainers: extend `_SENSITIVE_KEYS` in `app/logging.py` to grow the deny-list.** |
| 3 | `structlog.stdlib.ExtraAdder()` | Lifts `LogRecord.extra` kwargs (uvicorn's `logger.info("...", extra={"k": v})` path) into the event dict. |
| 4 | `structlog.processors.TimeStamper(fmt="iso", key="timestamp_iso")` | ISO-8601 timestamp. **Key name `timestamp_iso` is the FOUND-11 contract — do not rename.** |

Terminal renderer (after pre_chain):
- `format="console"` → `structlog.dev.ConsoleRenderer()` (color-on-TTY)
- anything else (default `format="json"`) → `structlog.processors.JSONRenderer()`

## Public Contract (Plan 04 imports this)

```python
from app.logging import configure_logging

# In app/main.py lifespan startup (Plan 04):
configure_logging(format=settings.LOG_FORMAT, level=settings.LOG_LEVEL)
```

- **Signature:** `configure_logging(format: str = "json", level: str = "INFO") -> None`
- **Side effects:** mutates structlog global config and the stdlib `logging` config; writes nothing to disk.
- **Idempotency:** safe to call multiple times in one process. `disable_existing_loggers=False` ensures pytest's `caplog`, SQLAlchemy's logger, and any module that called `logging.getLogger(__name__)` before configuration survive re-config.
- **Base log context every emit carries:** `event` (structlog default key for the message), `timestamp_iso` (ISO-8601), `level` (lower-case string).

## Sample JSON Output

```json
{"extra_field": "x", "event": "hello world", "level": "info", "timestamp_iso": "2026-05-17T14:58:21.532208Z"}
```

Sample console output (same emit with `format="console"`, ANSI codes stripped for display):

```
[info     ] hello world                    extra_field=x timestamp_iso=2026-05-17T14:58:21.532208Z
```

Sample redaction (both renderers):

```json
{"password": "<redacted>", "api_key": "<redacted>", "username": "alice", "event": "auth-event", "level": "info", "timestamp_iso": "..."}
```

## Test Coverage

5 tests, all green:

| Test | What it pins |
|---|---|
| `test_json_renderer_shape` | FOUND-11 — event/level/timestamp_iso present + ExtraAdder passthrough. Removing `TimeStamper(key="timestamp_iso")` (or renaming the key) breaks this. |
| `test_console_renderer_when_format_is_console` | The format switch lands — `json.loads` on console output raises `JSONDecodeError`. |
| `test_configure_logging_is_idempotent` | Two consecutive `configure_logging` calls emit exactly one record per `logger.info(...)`. A regression that re-attached handlers would double-emit and fail this test. |
| `test_contextvars_processor_present_in_chain` | Bound `request_id` flows into the JSON line. Removing `merge_contextvars` from `pre_chain` makes this test fail with `KeyError: 'request_id'`. |
| `test_redactor_scrubs_sensitive_keys` | Deny-listed keys scrubbed in **both** JSON and console; non-sensitive keys pass through; case-insensitive match; literal secret values absent from raw output. T-00-02-01 mitigation. |

Runtime: **0.06s** for all 5.

Full suite (Wave 0 + Wave 2): **7 passed in 0.22s** — FOUND-10 grep gate still green (no `os.environ` leaked into `app/logging.py`).

```bash
$ python -m pytest tests/ -x --tb=short
tests/test_env_example.py .                                              [ 14%]
tests/test_logging.py .....                                              [ 85%]
tests/test_no_direct_env.py .                                            [100%]
======================== 7 passed, 1 warning in 0.22s =========================
```

## Verification Block (Plan §verification) — All Green

| Gate | Command | Result |
|---|---|---|
| V1 | `python -c "from app.logging import configure_logging; configure_logging()"` | exit 0 |
| V2 | `pytest tests/test_logging.py::test_json_renderer_shape -x` | exit 0 |
| V3 | `pytest tests/test_logging.py::test_console_renderer_when_format_is_console -x` | exit 0 |
| V4 | `pytest tests/test_logging.py::test_configure_logging_is_idempotent -x` | exit 0 |
| V5 | `pytest tests/test_logging.py::test_contextvars_processor_present_in_chain -x` | exit 0 |
| V6 | `pytest tests/test_no_direct_env.py -x` (FOUND-10 not regressed) | exit 0 |

## Commits

| Task | Type | Hash | Summary |
|---|---|---|---|
| 1 | feat | `3517695` | structlog ProcessorFormatter wiring + `_redact_sensitive_keys` |
| 2 | test | `b639710` | 5 tests pinning JSON shape, console flip, idempotency, contextvars seat, redactor |

## Deviations from Plan

**None of substance — plan executed as written, with one minor verification-script note:**

- **Task 1 plan-literal verify command:** The plan's `<automated>` verification command for Task 1 attached a vanilla `logging.StreamHandler(buf)` to the root logger WITHOUT copying the configured structured formatter. The result: the structlog `LogRecord` was rendered via stdlib `Formatter.format()` (Python `repr()` of the event dict), producing single-quoted Python-literal output that `json.loads` correctly rejected. This is a flaw in the verify command, not in `app/logging.py` — the same emit lands on stdout as valid JSON via the dictConfig-owned handler. I confirmed the production JSON output is correct by reading the JSON line that DID emit to stdout, and the canonical FOUND-11 gate (`pytest tests/test_logging.py::test_json_renderer_shape`) passes — it uses the correct pattern (copy the formatter from the dictConfig handler onto the capture handler). No change to `app/logging.py` was needed.

- **No structural deviation from the plan's `<action>` blocks.** Pre-chain order matches the plan verbatim; deny-list matches the plan verbatim; idempotency mechanism (`disable_existing_loggers=False`) matches the plan verbatim; the `format`/`level` parameter approach (caller passes `settings.LOG_FORMAT`/`settings.LOG_LEVEL`) matches the plan verbatim.

## Threat Flags

No new security surface introduced beyond what the threat register already covers. The Phase 0 dispositions are honored:

- **T-00-02-01** (info disclosure via leaked secrets in logs): mitigated — `_redact_sensitive_keys` scrubs deny-listed keys in both JSON and console; `configure_logging` itself emits zero log lines and never touches a secret value.
- **T-00-02-02** (uvicorn.access query-string token leak): partial — uvicorn.access now flows through the structured stream so future Phase 1 body-redaction middleware can extend over the same handler. Phase 0 scope ends here.
- **T-00-02-03** (LOG_LEVEL=DEBUG leaks SQL with bound parameters): mitigated — `Settings.LOG_LEVEL` defaults to `INFO`. SQLAlchemy engine wiring is Plan 03's responsibility (with `echo=False`).
- **T-00-02-04** (missing timestamp / correlation ID → unverifiable audit trail): mitigated — every line carries `timestamp_iso`; `request_id` binding seat is wired (Phase 1 mints the value).

## Notes for Downstream Plans

- **Plan 00-04 (app/main.py + lifespan):** Import as `from app.logging import configure_logging` and call it in the `lifespan` startup branch BEFORE the engine is opened, so any SQLAlchemy connection-pool warnings during engine startup land in the structured stream. Signature: `configure_logging(format=settings.LOG_FORMAT, level=settings.LOG_LEVEL)`. The function returns `None` and does not need to be awaited.

- **Phase 1 (request_id middleware):** The contextvars seat is at `pre_chain` index 0 (`structlog.contextvars.merge_contextvars`). Phase 1's middleware simply calls `structlog.contextvars.bind_contextvars(request_id=...)` at the start of each request and `clear_contextvars()` in a `finally` block (or use `structlog.contextvars.bound_contextvars(...)` as a context manager). No `app/logging.py` edits needed.

- **Phase 1 (deny-list extension):** To grow `_SENSITIVE_KEYS`, edit the frozenset literal in `app/logging.py`. Phase 1 should add (at minimum): cookie names from the session middleware (`session`, `csrftoken`), Stripe webhook secret, and any header names the access-log middleware will surface (e.g., `x-api-key`). The current implementation matches case-insensitively on the FULL key name (not a substring), so adding hyphenated header names is safe.

- **Phase 1 (body-redaction middleware):** This is a separate concern from `_redact_sensitive_keys` — that scrubs structured kwargs; the body redactor handles raw request/response body bytes. Phase 1 should ship it as a FastAPI middleware that mutates the access-log `extra` payload before structlog processes it. Both work together because the body middleware runs FIRST (it's a Starlette middleware) and `_redact_sensitive_keys` runs SECOND (it's a structlog processor) — defense in depth.

- **Phase 7 (AI cost telemetry):** Log AI-call cost via `structlog.get_logger("ai").info("ai_call", provider=..., tokens=..., usd=...)`. The `model_used` field is NOT sensitive — log it directly. API keys are NEVER passed as kwargs anywhere; the SDK reads them from the encrypted DB row via `services/encryption.py`.

## Self-Check: PASSED

- `app/logging.py`: FOUND (185 LOC)
- `tests/test_logging.py`: FOUND (202 LOC)
- Commit `3517695` (Task 1): FOUND in git log
- Commit `b639710` (Task 2): FOUND in git log
- All 5 plan verification gates V1–V6: green
- FOUND-10 grep gate (no `os.environ` outside `app/config.py`): still green
- Full test suite (Wave 0 + Wave 2): **7 passed** in 0.22s
