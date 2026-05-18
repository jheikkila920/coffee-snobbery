"""Canonical event-name constants for structlog calls.

Source of truth for the D-14 taxonomy and the ``auth.login_attempt``
addendum. Future plans MUST import from here rather than hard-coding event
strings — a hard-coded ``log.info("auth.logged_in", ...)`` (note the typo)
silently fragments downstream queries; the constants give the type system
and grep a single place to catch drift.

Taxonomy
========

The names follow ``<category>.<action>`` (dot-separated, lower-case,
underscore-joined verbs). Three categories live in this file:

- ``auth.*`` — authentication lifecycle (Phase 2 wires real auth verifiers;
  Plan 07 emits ``auth.login_attempt`` on the stub /login route).
- ``admin.*`` — admin actions on users (Phase 9 wires).
- ``csp.*`` / ``rate_limit.*`` — operational counters (Plan 03 wires
  ``csp.violation`` on /csp-report; Plan 07 wires ``rate_limit.exceeded``).

CONTEXT D-14 taxonomy lists the auth + admin + csp events. CONTEXT D-15
locks the failed-login username policy. ``auth.login_attempt`` is NOT in
the D-14 taxonomy as originally written but IS in ROADMAP Phase 1 success
criterion 4 — RESEARCH §6 recommends adding it; this module ships it.
``docs/decisions/0003`` ADR (Plan 10) formalizes the amendment.

Why string constants rather than :class:`enum.Enum`?
----------------------------------------------------
structlog passes the event positional arg straight through to the
renderer; an :class:`enum.Enum` member would serialize as
``"AUTH_LOGIN_SUCCEEDED"`` (the member name) or require every call site to
write ``.value``. String constants serialize correctly with zero
ceremony and grep-cleanly across the codebase.
"""

from __future__ import annotations

# --- auth.* (Phase 2 wires verifiers; Plan 07 emits attempt on stub) -------
AUTH_LOGIN_ATTEMPT = "auth.login_attempt"
AUTH_LOGIN_SUCCEEDED = "auth.login_succeeded"
AUTH_LOGIN_FAILED = "auth.login_failed"
AUTH_LOGOUT = "auth.logout"

# --- admin.* (Phase 9 wires) ----------------------------------------------
ADMIN_USER_CREATED = "admin.user_created"
ADMIN_USER_DELETED = "admin.user_deleted"
ADMIN_PASSWORD_RESET = "admin.password_reset"  # noqa: S105 — event name, not a credential
ADMIN_IS_ADMIN_TOGGLED = "admin.is_admin_toggled"
# Phase 3 D-08: emitted by ``services/settings.set_setting`` on every
# write to ``app_settings``. Field shape per CONTEXT D-08:
# ``setting_key``, ``old_value``, ``new_value``, ``value_type``, ``user_id``.
ADMIN_APP_SETTING_CHANGED = "admin.app_setting_changed"
# Phase 3 D-08: emitted by ``services/credentials.set_provider_credential``
# when an admin sets or rotates an AI provider key. Field shape:
# ``provider``, ``last_four``, ``user_id``. The raw key is NEVER logged
# (CLAUDE.md "never log API keys"); only the denormalized ``last_four``.
ADMIN_API_CREDENTIAL_SET = "admin.api_credential_set"  # noqa: S105 — event name, not a credential

# --- encryption.* (Phase 3) -----------------------------------------------
# Lifespan-emitted events have no request_id (no request context); per
# CONTEXT <specifics> "use request_id=None or omit". Operational events
# the admin/operator reads to confirm key rotation and decrypt failures.
ENCRYPTION_STARTUP_OK = "encryption.startup_ok"
ENCRYPTION_REWRAP_COMPLETED = "encryption.rewrap_completed"
ENCRYPTION_DECRYPT_FAILED = "encryption.decrypt_failed"

# --- operational counters --------------------------------------------------
# CSP violation report — emitted by ``app.routers.csp_report`` on every POST
# to ``/csp-report`` (one log line per report; the dual-content-type handler
# emits one event per item in the ``application/reports+json`` array).
# Event fields (per D-06): ``blocked_uri``, ``violated_directive``, ``line``,
# ``source_file``, ``ip``. Other fields in the browser-supplied payload are
# stripped before emission to limit PII surface (threat T-03-07).
CSP_VIOLATION = "csp.violation"
RATE_LIMIT_EXCEEDED = "rate_limit.exceeded"


__all__ = [
    "ADMIN_API_CREDENTIAL_SET",
    "ADMIN_APP_SETTING_CHANGED",
    "ADMIN_IS_ADMIN_TOGGLED",
    "ADMIN_PASSWORD_RESET",
    "ADMIN_USER_CREATED",
    "ADMIN_USER_DELETED",
    "AUTH_LOGIN_ATTEMPT",
    "AUTH_LOGIN_FAILED",
    "AUTH_LOGIN_SUCCEEDED",
    "AUTH_LOGOUT",
    "CSP_VIOLATION",
    "ENCRYPTION_DECRYPT_FAILED",
    "ENCRYPTION_REWRAP_COMPLETED",
    "ENCRYPTION_STARTUP_OK",
    "RATE_LIMIT_EXCEEDED",
]
