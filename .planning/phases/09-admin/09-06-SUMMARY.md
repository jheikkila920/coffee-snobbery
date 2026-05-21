---
phase: "09-admin"
plan: "06"
subsystem: admin
tags: [admin, system-info, api-health, ai-refresh, test-connection, security, tdd]
dependency_graph:
  requires:
    - phase: "09-01"
      provides: "app.routers.admin sub-package with import-guarded include loop; admin_base.html; Phase 9 conftest fixtures"
    - phase: "09-03"
      provides: "admin_test_result.html fragment; credentials page Test-Connection button targeting this plan's route"
  provides:
    - "app/routers/admin/system.py — GET /admin/system, POST /admin/system/ai-refresh, POST /admin/system/test-connection/{provider}"
    - "app/templates/pages/admin_system.html — System Info + API Health combined page"
    - "app/templates/fragments/admin_ai_refresh_result.html — AI refresh result fragment"
    - "tests/phase_09/test_admin_system.py — ADMIN-05/06 + D-12 test suite (16 tests, 0 skips)"
  affects:
    - "09-03 credentials page — Test-Connection button (POST /admin/system/test-connection/{provider}) now resolves (no 404)"
tech_stack:
  added: []
  patterns:
    - "Raw select(AppSetting...) for last_ai_run_status + last_backup_status — never get_str (Pitfall 2 / T-09-25)"
    - "Error truncation at 200 chars before template render — T-09-26 prevents XSS + readability"
    - "async def run_ai_refresh reuses scheduler._get_eligible_user_ids(db) — cost-control invariant preserved"
    - "sync def test_connection with del client in finally — key never in template context or logs (SEC-6 / T-09-31)"
    - "TDD: RED commit (test) followed by GREEN commit (feat) — gate compliance satisfied"
key_files:
  created:
    - app/routers/admin/system.py
    - app/templates/pages/admin_system.html
    - app/templates/fragments/admin_ai_refresh_result.html
    - tests/phase_09/test_admin_system.py
  modified: []
decisions:
  - "pyproject.toml fallback for pkg_version — container runs without pip install -e; tomllib reads version directly from /app/pyproject.toml when PackageNotFoundError is raised"
  - "All four tasks folded into two commits (TDD RED + GREEN) — Tasks 1-4 are additive route additions to a single router file; splitting further would produce commits with no independently runnable state"
  - "respx.mock().calls (not .call_count) for no-SDK-call assertion — respx 0.23.1 uses .calls list, not .call_count attribute"
  - "test_connection handler catches exceptions via isinstance() after-the-fact import to avoid circular import issues at module level"
metrics:
  duration: "7 minutes"
  completed: "2026-05-21T23:33:00Z"
  tasks_completed: 4
  tasks_total: 4
  files_created: 4
  files_modified: 0
---

# Phase 09 Plan 06: Admin System + API Health Summary

**One-liner:** Combined /admin/system page with cache-pop-safe raw DB reads for System Info + API Health panels, both AI-refresh modes reusing Phase 8 cost-control filter, and the single canonical test-connection probe that authenticates saved keys without writing recommendations or leaking key material.

## What Was Built

### Task 1: System Info panel (ADMIN-05)
Created `app/routers/admin/system.py` with `GET /system` (sync def). Gathers:
- App version via `importlib.metadata.version("coffee-snobbery")` with pyproject.toml fallback (container doesn't pip-install the package)
- DB version via `SELECT version()`
- Active session count via `SELECT COUNT(*) FROM sessions WHERE expires_at > now()`
- Photo + backup storage via `Path.rglob("*")` disk walk with `_human_size()` formatter
- Last backup status via raw `select(AppSetting.value)` — **never `get_str()`** (Pitfall 2)

Created `app/templates/pages/admin_system.html` extending `admin_base.html`. System Info panel uses a responsive `grid-cols-1 sm:grid-cols-2` layout that stacks at 375px.

### Task 2: API Health panel (ADMIN-06)
Extended the GET handler to also gather:
- `last_ai_run_status` via raw `select(AppSetting.value)` — **never `get_str()`** (Pitfall 2). Returns fields: users_processed, regenerations, skips, errors, token totals, timestamp.
- Per-provider (anthropic/openai): last success row, last error row, last 5 error rows. Error status truncated to 200 chars before rendering.
- Per-recommendation-type last run via GROUP BY recommendation_type (ROADMAP success #5).

Template section renders gracefully when no AI runs exist (empty state).

### Task 3: Run AI refresh now — respect-signature + force-all (D-13/D-14)
Added `POST /system/ai-refresh` (async def — Pitfall 4: regenerate is async). Steps:
1. Parse `force` from form; `generated_by = "admin_force" if force else "admin"`.
2. `_get_eligible_user_ids(db)` — REUSED from `app.services.scheduler`, not re-implemented. Returns `list[int]` (is_active AND >= 3 brew_sessions).
3. Sequential `await ai_service.regenerate(uid, generated_by, db=db, force=force)` per eligible user.
4. Emits `ADMIN_AI_REFRESH_TRIGGERED` with force flag + counts (no secrets).
5. Returns `admin_ai_refresh_result.html` fragment with tally + per-user status list.

The force-refresh button is labeled "re-bills every eligible user" in the UI (T-09-27).
Created `app/templates/fragments/admin_ai_refresh_result.html` with status badges per user + tally summary.

### Task 4: Test connection probe (D-12) — canonical location
Added `POST /system/test-connection/{provider}` (sync def). Steps:
1. `get_provider_credential(db, provider)` — returns `None` for disabled/keyless → renders not_configured without SDK call.
2. Builds SDK client with `api_key=cred.key` (local scope only).
3. Calls `client.models.list()` — cheapest auth-only probe, no tokens billed.
4. Exception mapping: auth errors → `invalid_key`; connection errors → `network`; other → `unknown`.
5. `del client` in `finally` block — drops key reference (SEC-6 / T-09-31).
6. Emits `ADMIN_PROVIDER_TEST` with provider + result status only (no key).
7. Returns `admin_test_result.html` fragment (created by Plan 03).

Provider is validated in `_VALID_PROVIDERS`; unknown provider returns 404.

## Verification Results

```
tests/phase_09/test_admin_system.py::TestSystemInfo - 3 passed
tests/phase_09/test_admin_system.py::TestHealthPanel - 3 passed
tests/phase_09/test_admin_system.py::TestAiRefresh - 4 passed
tests/phase_09/test_admin_system.py::TestTestConnection - 6 passed

16 passed, 0 failed, 0 skipped — no /admin/system assertion skips in -rs summary

Phase 09 full suite: 63 passed, 0 failed, 0 skipped
```

Cross-plan contract verified:
- `POST /admin/system/test-connection/{provider}` route resolves (no 404)
- No test-connection route exists in credentials.py (grep confirms)
- `admin_test_result.html` fragment (Plan 03) returned correctly

## TDD Gate Compliance

- RED commit: `94d4a30` — `test(09-06): add failing tests for system/health page, AI refresh, test-connection probe`
- GREEN commit: `37ef819` — `feat(09-06): implement system/health page, AI refresh, test-connection probe`

Both gates satisfied.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] PackageNotFoundError for coffee-snobbery package version**
- **Found during:** Task 1 verification
- **Issue:** `importlib.metadata.version("coffee-snobbery")` raises `PackageNotFoundError` in the container because the package is copied into `/app` but not installed via `pip install -e .` (no `.egg-info`).
- **Fix:** Wrapped in `try/except PackageNotFoundError`; fallback reads `version` from `/app/pyproject.toml` via stdlib `tomllib`. Matches the actual value (`"0.1.0"`) and works in production where the package IS installed.
- **Files modified:** `app/routers/admin/system.py` (the handler), `tests/phase_09/test_admin_system.py` (test assertion updated to use fallback)
- **Commit:** `37ef819`

**2. [Rule 1 - Bug] respx MockRouter uses `.calls` not `.call_count`**
- **Found during:** Task 4 verification
- **Issue:** `mock.call_count` attribute does not exist in respx 0.23.1; the correct attribute is `mock.calls` (a list).
- **Fix:** Changed `assert mock.call_count == 0` to `assert len(mock.calls) == 0`.
- **Files modified:** `tests/phase_09/test_admin_system.py`
- **Commit:** `37ef819` (fixed before final GREEN commit)

## Known Stubs

None. All six system-info data points render from real data. The "no AI runs yet" placeholder is a valid empty state, not a stub — it disappears once the scheduler or admin refresh runs.

## Threat Flags

No new threat surface beyond what the plan's threat model covers:
- T-09-25 (cache-pop DoS): mitigated — raw select(AppSetting...) used for both status rows
- T-09-26 (XSS from error_status): mitigated — Jinja autoescape ON + `_truncate_error()` at 200 chars
- T-09-27 (force-refresh cost abuse): mitigated — force button explicitly labeled; distinct tag
- T-09-28 (async loop blocking): mitigated — async def handler + awaited regenerate
- T-09-29 (non-admin access): mitigated — require_admin on all three routes
- T-09-30 (ineligible user rebill): mitigated — _get_eligible_user_ids reused (not reimplemented)
- T-09-31 (key leak in probe): mitigated — del client in finally; key never in context/logs

## Self-Check: PASSED

Files created:
- app/routers/admin/system.py — FOUND
- app/templates/pages/admin_system.html — FOUND
- app/templates/fragments/admin_ai_refresh_result.html — FOUND
- tests/phase_09/test_admin_system.py — FOUND

Commits:
- 94d4a30 (test: RED phase) — FOUND
- 37ef819 (feat: GREEN phase) — FOUND

Test results: 16 passed, 0 failed, 0 skipped (phase_09 suite: 63 passed, 0 skipped)
