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

# --- catalog.* (Phase 4) ---------------------------------------------------
# Shared-catalog write events. Per D-14 taxonomy ``<category>.<action>``;
# the catalog category groups the five shared entities (coffee, roaster,
# flavor_note, equipment, recipe) plus bag lifecycle and the photo
# pipeline. Emitted by per-entity service modules (Phase 4 plans 04-04
# through 04-10) at the end of each successful write transaction.
#
# Field shapes the downstream JSON-log queries depend on:
# - ``catalog.<entity>.created/updated/archived`` carry ``<entity>_id``
#   (e.g. ``coffee_id``) and ``user_id``.
# - ``catalog.recipe.duplicated`` adds ``source_id`` to the
#   ``recipe.created`` shape.
# - ``catalog.bag.photo_uploaded`` / ``.photo_deleted`` carry
#   ``bag_id``, ``filename``, ``user_id``.
# - ``catalog.photo.orphan_swept`` is operator-facing (no user_id);
#   emitted by ``app.services.photos.sweep_orphans`` with ``count`` +
#   ``total_on_disk`` fields.
CATALOG_COFFEE_CREATED = "catalog.coffee.created"
CATALOG_COFFEE_UPDATED = "catalog.coffee.updated"
CATALOG_COFFEE_ARCHIVED = "catalog.coffee.archived"
CATALOG_ROASTER_CREATED = "catalog.roaster.created"
CATALOG_ROASTER_UPDATED = "catalog.roaster.updated"
CATALOG_ROASTER_ARCHIVED = "catalog.roaster.archived"
CATALOG_FLAVOR_NOTE_CREATED = "catalog.flavor_note.created"
CATALOG_FLAVOR_NOTE_UPDATED = "catalog.flavor_note.updated"
CATALOG_FLAVOR_NOTE_ARCHIVED = "catalog.flavor_note.archived"
CATALOG_EQUIPMENT_CREATED = "catalog.equipment.created"
CATALOG_EQUIPMENT_UPDATED = "catalog.equipment.updated"
CATALOG_EQUIPMENT_ARCHIVED = "catalog.equipment.archived"
CATALOG_RECIPE_CREATED = "catalog.recipe.created"
CATALOG_RECIPE_UPDATED = "catalog.recipe.updated"
CATALOG_RECIPE_ARCHIVED = "catalog.recipe.archived"
CATALOG_RECIPE_DUPLICATED = "catalog.recipe.duplicated"
CATALOG_BAG_CREATED = "catalog.bag.created"
CATALOG_BAG_UPDATED = "catalog.bag.updated"
CATALOG_BAG_ARCHIVED = "catalog.bag.archived"
CATALOG_BAG_PHOTO_UPLOADED = "catalog.bag.photo_uploaded"
CATALOG_BAG_PHOTO_DELETED = "catalog.bag.photo_deleted"
CATALOG_PHOTO_ORPHAN_SWEPT = "catalog.photo.orphan_swept"

# --- brew.* (Phase 5) ------------------------------------------------------
# Per-user brew-session lifecycle + the localStorage-backstop draft store +
# the CSV import/export flows. Same ``<category>.<action>`` taxonomy as the
# catalog block. Emitted by the Phase 5 service modules (plans 05-02..05-05)
# at the end of each successful write transaction.
#
# Field shapes the downstream JSON-log queries depend on:
# - ``brew.session.created/updated/deleted`` carry ``session_id`` + ``user_id``.
# - ``brew.draft.saved/cleared`` carry ``user_id`` (one draft per user).
# - ``brew.csv.imported`` carries ``user_id`` + the per-run counts
#   (``inserted``, ``skipped``, ``refused``); ``brew.csv.exported`` carries
#   ``user_id`` + ``row_count``.
BREW_SESSION_CREATED = "brew.session.created"
BREW_SESSION_UPDATED = "brew.session.updated"
BREW_SESSION_DELETED = "brew.session.deleted"
BREW_DRAFT_SAVED = "brew.draft.saved"
BREW_DRAFT_CLEARED = "brew.draft.cleared"
BREW_CSV_IMPORTED = "brew.csv.imported"
BREW_CSV_EXPORTED = "brew.csv.exported"

# --- ai.* (Phase 7) -------------------------------------------------------
# AI generation lifecycle. Field shapes the downstream JSON-log queries depend on:
# - AI_GENERATION_START: user_id, rec_type, generated_by
# - AI_GENERATION_SUCCESS: user_id, rec_type, provider, model, tier,
#   tokens_input, tokens_output, duration_ms
# - AI_GENERATION_ERROR: user_id, rec_type, error_class, error_status
# - AI_FALLBACK_TRIGGERED: user_id, rec_type, from_provider, reason
# - AI_TIER_FALLBACK: user_id, from_tier, to_tier, reason
# - AI_URL_VERIFY: user_id, rec_id, verified (bool)
# - AI_THROTTLE_BLOCK: user_id, seconds_remaining
# - AI_REGEN_SKIPPED: user_id, rec_type, reason="sig_unchanged"
AI_FALLBACK_TRIGGERED = "ai.fallback.triggered"
AI_GENERATION_ERROR = "ai.generation.error"
AI_GENERATION_START = "ai.generation.start"
AI_GENERATION_SUCCESS = "ai.generation.success"
AI_REGEN_SKIPPED = "ai.regen.skipped"
AI_THROTTLE_BLOCK = "ai.throttle.block"
AI_TIER_FALLBACK = "ai.tier.fallback"
AI_URL_VERIFY = "ai.url.verify"


__all__ = [
    "ADMIN_API_CREDENTIAL_SET",
    "ADMIN_APP_SETTING_CHANGED",
    "ADMIN_IS_ADMIN_TOGGLED",
    "ADMIN_PASSWORD_RESET",
    "ADMIN_USER_CREATED",
    "ADMIN_USER_DELETED",
    "AI_FALLBACK_TRIGGERED",
    "AI_GENERATION_ERROR",
    "AI_GENERATION_START",
    "AI_GENERATION_SUCCESS",
    "AI_REGEN_SKIPPED",
    "AI_THROTTLE_BLOCK",
    "AI_TIER_FALLBACK",
    "AI_URL_VERIFY",
    "AUTH_LOGIN_ATTEMPT",
    "AUTH_LOGIN_FAILED",
    "AUTH_LOGIN_SUCCEEDED",
    "AUTH_LOGOUT",
    "BREW_CSV_EXPORTED",
    "BREW_CSV_IMPORTED",
    "BREW_DRAFT_CLEARED",
    "BREW_DRAFT_SAVED",
    "BREW_SESSION_CREATED",
    "BREW_SESSION_DELETED",
    "BREW_SESSION_UPDATED",
    "CATALOG_BAG_ARCHIVED",
    "CATALOG_BAG_CREATED",
    "CATALOG_BAG_PHOTO_DELETED",
    "CATALOG_BAG_PHOTO_UPLOADED",
    "CATALOG_BAG_UPDATED",
    "CATALOG_COFFEE_ARCHIVED",
    "CATALOG_COFFEE_CREATED",
    "CATALOG_COFFEE_UPDATED",
    "CATALOG_EQUIPMENT_ARCHIVED",
    "CATALOG_EQUIPMENT_CREATED",
    "CATALOG_EQUIPMENT_UPDATED",
    "CATALOG_FLAVOR_NOTE_ARCHIVED",
    "CATALOG_FLAVOR_NOTE_CREATED",
    "CATALOG_FLAVOR_NOTE_UPDATED",
    "CATALOG_PHOTO_ORPHAN_SWEPT",
    "CATALOG_RECIPE_ARCHIVED",
    "CATALOG_RECIPE_CREATED",
    "CATALOG_RECIPE_DUPLICATED",
    "CATALOG_RECIPE_UPDATED",
    "CATALOG_ROASTER_ARCHIVED",
    "CATALOG_ROASTER_CREATED",
    "CATALOG_ROASTER_UPDATED",
    "CSP_VIOLATION",
    "ENCRYPTION_DECRYPT_FAILED",
    "ENCRYPTION_REWRAP_COMPLETED",
    "ENCRYPTION_STARTUP_OK",
    "RATE_LIMIT_EXCEEDED",
]
