---
phase: 09-admin
verified: 2026-05-21T00:00:00Z
status: human_needed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification: null
deferred:
  - truth: "json→textarea mapping per ROADMAP SC-3 wording"
    addressed_in: "D-05 design decision, acknowledged in 09-04-PLAN.md"
    evidence: "No 'json' value_type exists in app_settings DB (SELECT DISTINCT value_type confirms: bool, float, int, null, string). Plan D-05 explicitly documents this and maps null/JSON-in-string status rows to read-only monospace display — intentional design, not a gap."
human_verification:
  - test: "Navigate /admin/users at 375px viewport; create a user, reset password, toggle is_admin, deactivate, reactivate, and delete an empty user"
    expected: "All actions succeed; no horizontal scroll; forms readable at 375px; inline errors display correctly; action buttons have >=44px tap targets"
    why_human: "Mobile layout, tap target size, and inline-error UX cannot be verified programmatically"
  - test: "Navigate /admin/credentials; set an Anthropic key, verify only last-4 displays; click 'Test connection'; disable the provider"
    expected: "Full key never visible; last-4 shown after save; test result fragment renders ok/invalid_key; toggle persists"
    why_human: "Visual masking behavior and real-provider auth probe require live UI + a real or test API key"
  - test: "Navigate /admin/settings; edit min_sessions_for_ai; attempt to save setup_completed"
    expected: "Editable row saves and shows 'Saved' confirmation; setup_completed save is rejected (403); description visible as helper text; type-appropriate input controls"
    why_human: "Visual input-type rendering (checkbox vs number vs text) and helper-text legibility require visual inspection"
  - test: "Navigate /admin/backups; click 'Run backup now'; download a produced file; attempt path-traversal in URL"
    expected: "Backup runs and result card appears; file downloads with correct content-type; traversal attempt returns 404"
    why_human: "Real pg_dump execution and file download behavior require live container verification"
  - test: "Navigate /admin/system; confirm all system info fields populated; confirm API health panel shows per-provider and per-rec-type rows after any AI run"
    expected: "App version, DB version, storage sizes, session count, last backup status all present; API health panel renders last AI run summary and per-provider blocks; no SettingNotFoundError after a backup/AI run"
    why_human: "Real runtime data and post-run cache-pop safety require live VPS or container with actual AI/backup history"
  - test: "Navigate /admin/system; click 'Refresh (respect signatures)' and 'Force refresh all' AI buttons"
    expected: "'admin' vs 'admin_force' generated_by tags in ai_recommendations; only eligible users refreshed; force path labeled as expensive"
    why_human: "Requires real AI credentials + eligible user with >=3 sessions on VPS; telemetry row verification requires DB inspection"
---

# Phase 9: Admin — Verification Report

**Phase Goal:** A `/admin` area gated by `is_admin` lets the admin manage users, set/update encrypted API credentials per provider (Anthropic, OpenAI) with last-4 display, edit any row in `app_settings` via a `value_type`-driven input, view + download retained backups + trigger a manual backup, see system info (versions, storage, sessions, last backup), and read an API health panel that surfaces silent failures (deprecated model, revoked key, quota hit) from the cost-telemetry rows the scheduler writes.

**Verified:** 2026-05-21
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Admin can list/create/edit (reset password, toggle is_admin, deactivate)/delete users; toggling is_admin regenerates the target's session; non-admins hitting /admin get 403 | VERIFIED | `app/routers/admin/__init__.py` gates hub via `Depends(require_admin)`; `users.py` implements all mutations; D-15 brew-session count guard at line 490; D-16 last-admin/self guards in all 3 mutating handlers; `_delete_user_sessions` called on is_admin change + deactivate + delete + password reset; 63 phase_09 tests pass (0 skipped) |
| 2 | API-credentials page sets/updates Anthropic + OpenAI keys (encrypted via services/encryption.py MultiFernet), enable/disable per provider, model per provider; after save only last 4 chars shown; decrypted key never in a Pydantic model | VERIFIED | `credentials.py` POST handler keeps `api_key` as a local variable only; `set_provider_credential` stores `last_four = key[-4:]`; template `admin_credential_row.html` renders `....{{ last_four }}` only; `ProviderCredential` dataclass never passed to template context; WR-06 fix: blank key is a no-op; WR-04 fix: model_name-only updates don't force-enable provider |
| 3 | app_settings editor renders one input per row driven by value_type (string→text, integer→number, boolean→checkbox, json→textarea); description as helper text; save persists immediately + invalidates the in-memory cache | VERIFIED (see deferred note on json→textarea) | `settings_editor.py` reads via raw `select(AppSetting...)`, not `get_str`; `_input_kind()` maps int→number_int, float→number_float, bool→checkbox, string→text, null→readonly; `admin_setting_row.html` renders correct HTML input per kind with CSRF; `set_setting` called for saves (handles coercion + cache invalidation); read-only guard returns 403 before `set_setting` for protected keys |
| 4 | Backups page lists every retained file (size + timestamp), per-file download, and a "Run backup now" that synchronously invokes the same services/backup.py entry point the scheduler uses | VERIFIED | `backups.py` `list_backups` uses `_BACKUP_FILENAME_RE` regex filter + newest-first sort; `download_backup` has dual path-traversal defense (regex FIRST + `Path.resolve().is_relative_to()` containment); `run_backup_now` is `sync def` (threadpool, D-07); calls `run_backup(db, by_user_id=user.id)` — same function the scheduler uses |
| 5 | System info panel shows app version, DB version, photo + backup storage, active session count, last backup status+timestamp; API health panel shows last AI run timestamp+status per recommendation type, last success/error per provider, last 5 error messages per provider | VERIFIED | `system.py` gathers all 6 system info data points; API health: last_ai_run_status + last_backup_status via raw `select(AppSetting...)` (not `get_str`); per-provider last success/error/last-5-errors queries present; per-rec-type last run via window function (`func.row_number().over(partition_by=..., order_by=generated_at.desc())`); WR-03 fix confirmed (no `func.max(error_status)`) |

**Score:** 5/5 truths verified

---

### Deferred Items

Items not yet met but either explicitly addressed in later milestone phases or accepted as intentional design decisions.

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | "json→textarea" mapping (ROADMAP SC-3 wording) | D-05 design decision | No `json` value_type exists in app_settings DB (verified: `SELECT DISTINCT value_type` returns bool, float, int, null, string only). Plan 09-04-PLAN.md D-05 explicitly documents this and maps null/JSON-in-string status rows to read-only monospace display. Intentional design, not a gap. |

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/routers/admin/__init__.py` | Admin router package; prefix='/admin'; guarded sub-router includes | VERIFIED | CR-01 fix applied: `ModuleNotFoundError` with `exc.name` check; logs warning on absent module; re-raises broken-import errors |
| `app/routers/admin/users.py` | User CRUD handlers | VERIFIED | All 8 handlers present; async for mutations; sync for reads |
| `app/routers/admin/credentials.py` | Credential set/update + enable-toggle | VERIFIED | SEC-6 invariant: `api_key` never in template context; WR-04/WR-06 fixes applied |
| `app/routers/admin/settings_editor.py` | Settings list + per-row inline save | VERIFIED | Raw DB query, `_READ_ONLY_KEYS` guard, `set_setting` delegation |
| `app/routers/admin/backups.py` | Backup list + FileResponse download + sync run-now | VERIFIED | Dual path-traversal defense; `run_backup_now` is `sync def` |
| `app/routers/admin/system.py` | System info + API health + AI-refresh + test-connection probe | VERIFIED | All four handlers present; raw DB reads; window function for per_rec_type; `del client` in finally |
| `app/schemas/admin_user.py` | `AdminUserCreate`, `AdminPasswordReset`, `AdminUserEdit` | VERIFIED | WR-02 fix applied: `AdminUserEdit` with `EmailStr | None`; `extra="ignore"` for edit path |
| `app/templates/admin_base.html` | Shared admin layout with persistent section nav | VERIFIED | Extends `base.html`; 5-link section nav; `block admin_content` |
| `app/templates/pages/admin.html` | Admin hub page | VERIFIED | Extends `admin_base.html`; `block admin_page_title "Overview"` |
| `app/templates/pages/admin_users.html` | Users page | VERIFIED | Extends `admin_base.html` |
| `app/templates/pages/admin_credentials.html` | Credentials page | VERIFIED | Extends `admin_base.html` |
| `app/templates/pages/admin_settings.html` | Settings page | VERIFIED | Extends `admin_base.html` |
| `app/templates/pages/admin_backups.html` | Backups page | VERIFIED | Extends `admin_base.html` |
| `app/templates/pages/admin_system.html` | System/health page | VERIFIED | Renders all 6 system info + API health fields |
| `app/templates/fragments/admin_user_form.html` | User create/edit form with CSRF | VERIFIED | X-CSRF-Token hidden field present |
| `app/templates/fragments/admin_user_row.html` | User list row | VERIFIED | Present |
| `app/templates/fragments/admin_user_list.html` | User list fragment | VERIFIED | Present |
| `app/templates/fragments/admin_credential_row.html` | Masked credential row with CSRF forms | VERIFIED | `....{{ last_four }}` display; api_key input `type="password" autocomplete="off"`; test-connection button targets `POST /admin/system/test-connection/{{ provider }}` |
| `app/templates/fragments/admin_test_result.html` | Test connection result | VERIFIED | Renders status/reason; no key reference |
| `app/templates/fragments/admin_setting_row.html` | Type-driven setting row with CSRF | VERIFIED | Checkbox/number_int/number_float/text/readonly inputs; CSRF hidden field |
| `app/templates/fragments/admin_backup_list.html` | Backup file list | VERIFIED | Present |
| `app/templates/fragments/admin_backup_result.html` | BackupResult status card | VERIFIED | Renders `result.status`, `result.db.*`, `result.photos.*`, `result.duration_ms`, `result.pruned_count`, `result.timestamp` |
| `app/templates/fragments/admin_ai_refresh_result.html` | AI refresh result | VERIFIED | Present |
| `app/events.py` | New admin.* audit event constants | VERIFIED | All required constants present: `ADMIN_USER_UPDATED`, `ADMIN_USER_DEACTIVATED`, `ADMIN_USER_REACTIVATED`, `ADMIN_BACKUP_TRIGGERED`, `ADMIN_AI_REFRESH_TRIGGERED`, `ADMIN_PROVIDER_TEST`; all in `__all__` |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `app/main.py` | `app/routers/admin` | `include_router(admin_router.router)` | VERIFIED | Line 231; import alias `admin_router` at line 84 |
| `app/templates/pages/admin.html` | `app/templates/admin_base.html` | `{% extends "admin_base.html" %}` | VERIFIED | Line 1 |
| `app/templates/pages/home.html` | `/admin` | `is_admin`-gated anchor | VERIFIED | Lines 12-14: `{% if request.state.user and request.state.user.is_admin %}<a href="/admin"` |
| `app/routers/admin/users.py` | `app/services/auth.hash_password` | password reset + create | VERIFIED | `from app.services.auth import hash_password`; called in `create_user` and `update_user` |
| `app/routers/admin/users.py` | sessions table | async bulk delete on is_admin toggle / deactivate / delete / password reset | VERIFIED | `_delete_user_sessions` called in all 4 mutation paths |
| `app/routers/admin/users.py` | brew_sessions count guard | D-15 hard-delete block | VERIFIED | `select(func.count()).select_from(BrewSession)` at line 490 |
| `app/routers/admin/credentials.py` | `app/services/credentials.set_provider_credential` | encrypted key write | VERIFIED | Called in `set_credential` POST handler |
| `app/routers/admin/credentials.py GET /credentials` | `app.models.api_credential.ApiCredential` | direct model query (not `get_provider_credential`) | VERIFIED | `_get_display_rows()` uses `select(ApiCredential)` |
| `app/templates/fragments/admin_credential_row.html` | `POST /admin/system/test-connection/{provider}` | Test connection button | VERIFIED | `hx-post="/admin/system/test-connection/{{ provider }}"` at line 90 |
| `app/routers/admin/settings_editor.py` | `app/services/settings.set_setting` | inline per-row save | VERIFIED | `settings_service.set_setting(db, key, value_str, by_user_id=user.id)` |
| `app/routers/admin/settings_editor.py` | `AppSetting` raw query | read without `get_str` | VERIFIED | `select(AppSetting.key, AppSetting.value, AppSetting.value_type, AppSetting.description)` |
| `app/routers/admin/backups.py` | `app/services/backup.run_backup` | "Run backup now" (sync def, threadpool) | VERIFIED | `from app.services.backup import run_backup`; `run_backup(db, by_user_id=user.id)` |
| `app/routers/admin/backups.py` | `/app/data/backups FileResponse` | download with strict regex + resolve containment | VERIFIED | `_BACKUP_FILENAME_RE.match(filename)` FIRST; `backup_path.is_relative_to(backup_dir_resolved)` second |
| `app/routers/admin/system.py` | `app_settings` raw query | status read without `get_str` | VERIFIED | `select(AppSetting.value).where(AppSetting.key == "last_backup_status")` and `...last_ai_run_status"` |
| `app/routers/admin/system.py` | `app/services/scheduler._get_eligible_user_ids` | AI refresh eligibility | VERIFIED | `from app.services.scheduler import _get_eligible_user_ids`; called at line 294 |
| `app/routers/admin/system.py` | `app/services/ai_service.regenerate` | Run AI refresh now (async) | VERIFIED | `await ai_service.regenerate(uid, generated_by, db=db, force=force)` |
| `app/routers/admin/system.py POST /system/test-connection/{provider}` | `anthropic.Anthropic / openai.OpenAI models.list()` | Test connection probe | VERIFIED | Both SDK paths present; `del client` in `finally`; no ai_recommendations written |
| `app/routers/admin/system.py` | `importlib.metadata.version` | app version | VERIFIED | `pkg_version("coffee-snobbery")` with `pyproject.toml` fallback |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `admin_system.html` | `app_version` | `importlib.metadata.version("coffee-snobbery")` | Yes — reads installed package metadata; falls back to `pyproject.toml` | FLOWING |
| `admin_system.html` | `db_version` | `db.execute(text("SELECT version()")).scalar()` | Yes — live Postgres query | FLOWING |
| `admin_system.html` | `session_count` | `SELECT COUNT(*) FROM sessions WHERE expires_at > now()` | Yes — live DB count | FLOWING |
| `admin_system.html` | `last_backup` | `select(AppSetting.value).where(key=="last_backup_status")` | Yes — raw DB read, json.loads | FLOWING |
| `admin_system.html` | `last_ai_run` | `select(AppSetting.value).where(key=="last_ai_run_status")` | Yes — raw DB read, json.loads; `"never_run"` sentinel handled | FLOWING |
| `admin_system.html` | `per_provider` | per-provider `ai_recommendations` queries | Yes — actual queries against ai_recommendations table | FLOWING |
| `admin_system.html` | `per_rec_type` | window function subquery over `ai_recommendations` | Yes — row_number() window, WR-03 fix applied | FLOWING |
| `admin_credential_row.html` | `last_four` | `select(ApiCredential)` direct DB query | Yes — reads from api_credentials table | FLOWING |
| `admin_backup_list.html` | `files` | `_BACKUP_DIR.iterdir()` disk walk | Yes — actual filesystem | FLOWING |
| `admin_user_list.html` | `users` | `select(User).order_by(User.username)` | Yes — live DB query | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase 09 test suite | `docker compose exec coffee-snobbery python -m pytest tests/phase_09/ -q -rs` | 63 passed, 0 skipped | PASS |
| Import guard (CR-01 fix) | `docker compose exec coffee-snobbery python -c "from app.routers.admin import router; print(len(router.routes))"` | (Not run; verified via source code and test suite import) | PASS (inferred from 63 passing tests) |
| Events constants | Source verified: `ADMIN_BACKUP_TRIGGERED`, `ADMIN_AI_REFRESH_TRIGGERED`, `ADMIN_PROVIDER_TEST`, `ADMIN_USER_REACTIVATED` all present in `app/events.py` and `__all__` | N/A — verified by reading source | PASS |
| Decrypted key not in template context | `grep -n "cred.key\|api_key.*context\|ProviderCredential" credentials.py` | No hits in context dicts | PASS |
| No test-connection route in credentials.py | `grep -n "test.connection\|/test" credentials.py` | No output | PASS |
| `run_backup_now` is sync def | `grep -n "def run_backup_now" backups.py` — no `async` prefix | Confirmed sync | PASS |
| Raw DB reads in system.py | `grep -n "get_str\|select(AppSetting" system.py` — no `get_str` calls | Confirmed raw queries only | PASS |
| WR-03 fix: window function | `grep -n "row_number\|func.max" system.py` — `row_number()` present, `func.max(error_status)` absent | WR-03 fixed | PASS |

---

### Probe Execution

Step 7c: SKIPPED — no conventional `scripts/*/tests/probe-*.sh` found and phase documentation declares no probe files.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| ADMIN-01 | 09-02-PLAN.md | User management: list, create, edit (reset password, toggle admin, deactivate), delete | SATISFIED | All handlers in `app/routers/admin/users.py`; D-15/D-16 guards; session eviction; 63 tests green |
| ADMIN-02 | 09-03-PLAN.md | API credentials per provider: set/update encrypted key, select model, enable/disable, last-4 masked | SATISFIED | `credentials.py` + `services/credentials.py` MultiFernet; last_four display; SEC-6 preserved |
| ADMIN-03 | 09-04-PLAN.md | app_settings editor: type-driven inputs, description helper, immediate save | SATISFIED | `settings_editor.py` + `admin_setting_row.html`; raw query; set_setting delegation |
| ADMIN-04 | 09-05-PLAN.md | Backups page: list, download, manual backup | SATISFIED | `backups.py`; dual path-traversal defense; sync run-now |
| ADMIN-05 | 09-06-PLAN.md | System info panel: app version, DB version, storage, sessions, last backup | SATISFIED | `system.py` all 6 data points; raw DB reads |
| ADMIN-06 | 09-06-PLAN.md | API health panel: last AI run per rec type, per-provider success/error, last 5 errors | SATISFIED | `system.py` per_provider + per_rec_type queries; window function; truncation |

All 6 ADMIN requirements (ADMIN-01 through ADMIN-06) are SATISFIED. No orphaned requirements.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `app/routers/admin/users.py` | 295-300 | Dead code: unreachable duplicate self-demote check in `update_user` (WR-01, deferred) | Warning | Maintenance hazard; does not affect correctness; user-deferred |
| `app/routers/admin/credentials.py` | 79-85 | HTMX branch renders only first provider row (WR-05, deferred) | Warning | Latent bug; no template currently targets this branch; user-deferred |
| `app/routers/admin/backups.py` + `system.py` | 62-68, 77-85 | Duplicated `_human_size` with divergent MB/GB thresholds (WR-08, deferred) | Warning | DRY violation; inconsistent display across pages; user-deferred |

No TBD, FIXME, or XXX debt markers found in any Phase 9 files.

---

### Human Verification Required

#### 1. Admin User Management at 375px Viewport

**Test:** Open `/admin/users` on a 375px viewport device or browser DevTools. Create a user, reset the password, toggle is_admin, deactivate, reactivate, and delete an empty user.
**Expected:** All actions succeed; no horizontal scroll; forms fully readable; inline validation errors display below fields; action buttons have minimum 44px tap targets.
**Why human:** Mobile layout, tap-target sizing, and inline-error UX cannot be verified programmatically.

#### 2. API Credentials: Live Key Masking + Test Connection

**Test:** Open `/admin/credentials`. Set an Anthropic or OpenAI API key. Verify the form post-save shows only last-4 characters. Click "Test connection". Disable the provider using the toggle.
**Expected:** Full key never visible in page source or rendered HTML; `....XXXX` display after save; test result fragment renders `ok`, `invalid_key`, or `network` as appropriate; provider enable/disable toggle persists independently.
**Why human:** Visual key-masking requires UI inspection; real or mocked auth probe requires live interaction.

#### 3. Settings Editor: Type-Driven Inputs + Read-Only Guard

**Test:** Open `/admin/settings`. Confirm `min_sessions_for_ai` (int) renders a number input; confirm a bool setting renders a checkbox; confirm `recommendation_region` (string) renders a text input. Edit `min_sessions_for_ai` and save. Attempt to POST directly to `/admin/settings/setup_completed`.
**Expected:** Editable row saves and shows "Saved" confirmation; subsequent read returns new value; description visible as helper text; `setup_completed` POST returns 403 with no mutation.
**Why human:** Input-type visual rendering and helper-text legibility require visual inspection.

#### 4. Backups: Run Now + Download + Path Traversal Defense

**Test:** Open `/admin/backups`. Click "Run backup now". After completion, download the produced backup file via the download button. Manually attempt `/admin/backups/../../etc/passwd` in the URL bar.
**Expected:** Backup result card appears with status and file details; file downloads with correct content-type; traversal attempt returns 404.
**Why human:** Real `pg_dump` execution and file download behavior require live container verification.

#### 5. System Info + API Health Panel: Live Data

**Test:** Open `/admin/system` on a VPS with AI credentials configured and at least one AI run having occurred. Check all fields are populated. Trigger a backup and reload to confirm last-backup status updates (not cached stale value).
**Expected:** App version, DB version, storage sizes, session count, last backup status+timestamp all present; API health panel shows last AI run summary and per-provider blocks; no SettingNotFoundError after backup run.
**Why human:** Real runtime data requires live VPS + actual AI/backup history; post-run cache-pop safety requires DB inspection.

#### 6. AI Refresh Modes: generated_by Tag Verification

**Test:** On VPS with eligible users (is_active AND >=3 brew sessions), click "Refresh (respect signatures)" then "Force refresh all" on `/admin/system`.
**Expected:** `ai_recommendations` rows written with `generated_by = "admin"` and `"admin_force"` respectively; only eligible users refreshed; force path labeled distinctly in the UI.
**Why human:** Requires real AI credentials + eligible users on VPS; telemetry row verification requires DB query.

---

### Known-Deferred Review Findings (Not Blockers)

The following findings from `09-REVIEW.md` were explicitly accepted as deferred by the user:

- **WR-01**: Dead code in `update_user` (unreachable duplicate self-demote check at lines 295-300); inconsistent guard ordering across handlers. Maintenance hazard only.
- **WR-05**: `list_credentials` HTMX branch renders only first provider and passes malformed context. No template currently targets this path.
- **WR-08**: Duplicated `_human_size` function in `backups.py` and `system.py` with divergent thresholds. DRY violation.
- **IN-01 through IN-06**: All info-level findings (nav active state, `never_run` sentinel asymmetry, magic numbers, inline imports, `_render_error_fragment` default status code, dead `context` in `admin_user_deleted.html`).

---

### Gaps Summary

No blockers found. All 5 success criteria are verified in the codebase. The 6 human verification items are standard UI/live-data checks that cannot be performed programmatically — they do not indicate missing implementation.

The `json→textarea` wording in ROADMAP SC-3 does not match the implementation, but this is an acknowledged design decision documented in Plan 09-04-PLAN.md D-05: no `json` value_type exists in `app_settings`, and JSON-in-string status rows are correctly rendered as read-only monospace blocks.

---

_Verified: 2026-05-21_
_Verifier: Claude (gsd-verifier)_
