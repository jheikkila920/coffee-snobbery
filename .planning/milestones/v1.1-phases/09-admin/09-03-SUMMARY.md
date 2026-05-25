---
phase: "09-admin"
plan: "03"
subsystem: admin
tags: [admin, credentials, encryption, security, fastapi, htmx, csrf]

dependency_graph:
  requires:
    - phase: "09-01"
      provides: "app.routers.admin sub-package with import-guarded include loop; admin_base.html; Phase 9 conftest fixtures"
    - phase: "03"
      provides: "services/credentials.py (set_provider_credential, set_provider_enabled, get_provider_credential, ProviderCredential); services/encryption.py MultiFernet"
  provides:
    - "app/routers/admin/credentials.py — GET /admin/credentials, POST /admin/credentials/{provider}, POST /admin/credentials/{provider}/enabled"
    - "app/templates/pages/admin_credentials.html — credentials page extending admin_base.html"
    - "app/templates/fragments/admin_credential_row.html — masked per-provider row with update form + test-connection button"
    - "app/templates/fragments/admin_test_result.html — status badge fragment for Plan 06 probe responses"
    - "tests/phase_09/test_admin_credentials.py — ADMIN-02 / SEC-6 test suite (6 tests, 0 skips)"
  affects:
    - "09-06 system.py — Plan 06 owns POST /admin/system/test-connection/{provider}; admin_test_result.html is its result fragment"

tech-stack:
  added: []
  patterns:
    - "SEC-6 credential display: direct select(ApiCredential) for display rows; get_provider_credential() reserved for probe and write-back only"
    - "SEC-6 key isolation: api_key stays as a local variable in set_credential handler; never enters template context or logs"
    - "TDD flow: failing tests committed first (test commit d7f6fee), then GREEN implementation (feat commits a0bfb41, 47597c5)"

key-files:
  created:
    - app/routers/admin/credentials.py
    - app/templates/pages/admin_credentials.html
    - app/templates/fragments/admin_credential_row.html
    - app/templates/fragments/admin_test_result.html
    - tests/phase_09/test_admin_credentials.py
  modified: []

key-decisions:
  - "GET /credentials uses direct select(ApiCredential) for both providers — never get_provider_credential() which would decrypt the key (SEC-6) and silently omit disabled rows"
  - "Test-connection button in admin_credential_row.html targets POST /admin/system/test-connection/{provider} (Plan 06 canonical route); no duplicate handler in credentials.py"
  - "Enable-toggle form uses checkbox semantics: 'on' = enabled, absent/empty = disabled; set_provider_enabled() leaves ciphertext intact"
  - "admin_test_result.html shipped now so Plan 06 (system.py) can target it without a cross-plan dependency; fragment lives in templates/fragments/ as a shared artifact"

requirements-completed: [ADMIN-02]

duration: 6min
completed: "2026-05-21"
---

# Phase 09 Plan 03: Admin Credential Vault Summary

**Fernet-encrypted API credential vault for Anthropic/OpenAI with SEC-6 masked display (last_four only), enable-toggle, and test-connection result fragment wired to Plan 06 probe handler.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-05-21T23:01:13Z
- **Completed:** 2026-05-21T23:06:28Z
- **Tasks:** 2
- **Files created:** 5

## Accomplishments

- Admin can set/update Anthropic and OpenAI API keys; keys are encrypted at rest via `services/credentials.py` through `services/encryption.py` MultiFernet — no direct Fernet calls in the router.
- After save, only the last 4 characters appear in the masked display (`....1234`); the full key and all prefixes are absent from every response body (SEC-6 verified by automated test).
- Provider enable/disable toggle preserves `last_four` and `model_name` (ciphertext untouched by `set_provider_enabled`).
- Test-connection button in the credential row targets the single canonical Plan 06 route (`POST /admin/system/test-connection/{provider}`); `admin_test_result.html` fragment ships now so Plan 06 can render into it immediately.

## Task Commits

1. **RED: Failing credential tests** - `d7f6fee` (test)
2. **Task 1: Credential vault handlers + templates** - `a0bfb41` (feat)
3. **Task 2: Test-result fragment** - `47597c5` (feat)

## Files Created/Modified

- `app/routers/admin/credentials.py` — GET list, POST set/update, POST enable-toggle; auto-included by Plan 01 import guard
- `app/templates/pages/admin_credentials.html` — credentials page extending admin_base.html
- `app/templates/fragments/admin_credential_row.html` — masked row with CSRF-protected update form and test-connection button
- `app/templates/fragments/admin_test_result.html` — ok/invalid_key/network/not_configured/unknown status badges
- `tests/phase_09/test_admin_credentials.py` — 6 tests, 0 skips, all green

## Decisions Made

- GET `/credentials` queries `ApiCredential` model directly (not `get_provider_credential`) so disabled providers remain visible in the list and no decryption occurs at display time.
- `test-connection` handler is intentionally NOT in `credentials.py`; the button targets `POST /admin/system/test-connection/{provider}` (Plan 06 system.py), keeping the probe in one canonical location.
- `admin_test_result.html` shipped as part of this plan (Plan 03) because the credentials page hosts the test-connection button mount div — Plan 06 renders into the fragment but does not need to create it.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. Both providers (anthropic, openai) render from the seeded `api_credentials` rows. The credential row template renders "not set" when `last_four` is empty — a valid state, not a stub.

## Threat Flags

No new threat surface beyond what the plan's threat model covers:
- T-09-10 (decrypted key in template context): mitigated — verified by grep and automated test
- T-09-11 (key in logs): mitigated — `log.info` emits `provider` + `last_four` only
- T-09-13 (CSRF): mitigated — hidden `X-CSRF-Token` field on all three forms per row

## Self-Check: PASSED

Files created:
- app/routers/admin/credentials.py — FOUND
- app/templates/pages/admin_credentials.html — FOUND
- app/templates/fragments/admin_credential_row.html — FOUND
- app/templates/fragments/admin_test_result.html — FOUND
- tests/phase_09/test_admin_credentials.py — FOUND

Commits:
- d7f6fee (test: RED phase) — FOUND
- a0bfb41 (feat: Task 1 GREEN) — FOUND
- 47597c5 (feat: Task 2) — FOUND

Test results: 6 passed, 0 skips (phase 09 suite: 20 passed, 0 skips)
