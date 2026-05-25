---
phase: 9
slug: admin
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-21
validated: 2026-05-21
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Seeded from `09-RESEARCH.md` § Validation Architecture. Per-task IDs are filled
> once plans exist (the requirement→test map below is the source).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio + respx (HTTP mock for SDK probes) |
| **Config file** | `pyproject.toml` (existing) |
| **Quick run command** | `docker compose exec coffee-snobbery python -m pytest tests/phase_09/ -q -rs` |
| **Full suite command** | `docker compose exec coffee-snobbery python -m pytest -q -rs` |
| **Estimated runtime** | ~30s (phase subset); full suite TBD |

> NOTE (project invariants): pytest is **not** baked into the production image —
> Wave 0 installs it (`pip install --user pytest pytest-asyncio respx`) or a dev
> image is used. The image has **no source bind-mount**; changed test/source files
> must be `docker compose cp`'d in (file-level, not dir-level — dir cp nests) or the
> image rebuilt before a run is trustworthy. Always run with `-rs` so `pytest.skip`
> on missing seed data shows up as a gap, not a silent green.

---

## Sampling Rate

- **After every task commit:** Run `docker compose exec coffee-snobbery python -m pytest tests/phase_09/ -q -rs`
- **After every plan wave:** Run `docker compose exec coffee-snobbery python -m pytest -q -rs`
- **Before `/gsd-verify-work`:** Full suite must be green with **0 skips** for phase-9 tests
- **Max feedback latency:** ~30 seconds

---

## Per-Task Verification Map

> Post-execution audited map (State A, 2026-05-21). Each behavior is bound to the
> concrete pytest node ID that proves it and the plan that shipped it. Node IDs are
> runnable as `docker compose exec coffee-snobbery python -m pytest "tests/phase_09/<node-id>"`.

| Requirement | Behavior | Type | Test (pytest node ID) | Plan | Status |
|-------------|----------|------|-----------------------|------|--------|
| ADMIN-01 | User list renders | smoke | `test_admin_users.py::TestListUsers::test_list_users` | 09-02 | ✅ green |
| ADMIN-01 | User create succeeds | unit | `test_admin_users.py::TestCreateUser::test_create_user` | 09-02 | ✅ green |
| ADMIN-01 | Create fails < 12-char password | unit | `test_admin_users.py::TestCreateUserValidation::test_create_user_short_password` | 09-02 | ✅ green |
| ADMIN-01 | Last-admin delete/demote/deactivate blocked (D-16) | unit | `test_admin_users.py::TestDeleteUserGuards::test_delete_last_admin_blocked` | 09-02 | ✅ green |
| ADMIN-01 | Self-lockout (demote/deactivate self) blocked (D-16) | unit | `test_admin_users.py::TestDeleteUserGuards::test_self_demote_blocked` | 09-02 | ✅ green |
| ADMIN-01 | Hard-delete user with brew_sessions blocked (D-15, FK RESTRICT) | unit | `test_admin_users.py::TestDeleteUserGuards::test_delete_user_with_sessions_blocked` | 09-02 | ✅ green |
| ADMIN-01 | Hard-delete empty/never-used user succeeds (D-15) | unit | `test_admin_users.py::TestDeleteUserGuards::test_delete_empty_user` | 09-02 | ✅ green |
| ADMIN-01 | is_admin toggle invalidates target's sessions (async delete) | unit | `test_admin_users.py::TestToggleAdmin::test_toggle_admin_invalidates_sessions` | 09-02 | ✅ green |
| ADMIN-02 | Set credential encrypts; last_four shown; key absent from response | unit | `test_admin_credentials.py::TestSetCredentialMasked::test_set_credential_masked` | 09-03 | ✅ green |
| ADMIN-02 | Decrypted key never in response/template ctx (SEC-6) | unit (behavioral) | `test_admin_credentials.py::TestSetCredentialMasked::test_set_credential_masked` (asserts full key + prefix absent from body) | 09-03 | ✅ green |
| ADMIN-02 | Per-provider enable/disable + model select persists | unit | `test_admin_credentials.py::TestProviderToggleModel::test_provider_toggle_model` (+ `::test_toggle_enable`) | 09-03 | ✅ green |
| ADMIN-03 | Settings editor renders all rows (read-only set flagged, D-04) | smoke | `test_admin_settings.py::TestSettingsList::test_settings_list_admin_200` (+ `::test_settings_list_contains_known_keys`) | 09-04 | ✅ green |
| ADMIN-03 | Editable row save calls set_setting + invalidates cache (D-06) | unit | `test_admin_settings.py::TestSettingSave::test_setting_save_persists` (+ `::test_setting_save_cache_invalidated`) | 09-04 | ✅ green |
| ADMIN-03 | Read-only/system rows reject edits (D-04) | unit | `test_admin_settings.py::TestReadonlyRowsRejected::test_setup_completed_rejected` (+ `test_last_backup_status_rejected`, `test_encryption_key_fingerprint_rejected`) | 09-04 | ✅ green |
| ADMIN-04 | Backup list renders retained files (size + timestamp) | smoke | `test_admin_backups.py::TestBackupList::test_backup_list_admin_sees_file` | 09-05 | ✅ green |
| ADMIN-04 | Backup download — valid filename serves file | unit | `test_admin_backups.py::TestBackupDownload::test_download_valid_sql` (+ `::test_download_valid_tar_gz`) | 09-05 | ✅ green |
| ADMIN-04 | Backup download — path traversal blocked (D-08) | unit | `test_admin_backups.py::TestBackupDownload::test_download_path_traversal_encoded` (+ `::test_download_path_traversal_raw`) | 09-05 | ✅ green |
| ADMIN-04 | "Run backup now" (sync def) returns BackupResult (D-07) | integration | `test_admin_backups.py::TestRunBackupNow::test_run_backup_now_returns_result_fragment` (+ `::test_run_backup_handler_is_sync_def`) | 09-05 | ✅ green |
| ADMIN-05 | System info renders version/storage/sessions/last-backup (D-09) | smoke | `test_admin_system.py::TestSystemInfo::test_system_info` | 09-06 | ✅ green |
| ADMIN-06 | Health panel reads last_ai_run_status via RAW DB query (cache-pop gotcha) | unit | `test_admin_system.py::TestHealthPanel::test_health_panel_raw_db` | 09-06 | ✅ green |
| ADMIN-06 | Health panel surfaces per-provider last error + last 5 errors (D-10) | unit | `test_admin_system.py::TestHealthPanel::test_health_panel_errors` | 09-06 | ✅ green |
| SEC | `require_admin` on every admin route → non-admin 403 | unit | `test_admin_security.py::TestRequireAdmin::test_non_admin_403` (+ per-feature `*_non_admin_403` in every file) | 09-01 | ✅ green |
| SEC | CSRF required on every state-changing admin form | unit | `test_admin_security.py::TestCsrf::test_csrf_required` (+ `test_admin_users.py::TestDeactivateRequiresCsrf::test_deactivate_requires_csrf`) | 09-01/02 | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/phase_09/__init__.py`
- [x] `tests/phase_09/test_admin_users.py` — ADMIN-01 + D-15/D-16 guards (10 tests)
- [x] `tests/phase_09/test_admin_credentials.py` — ADMIN-02 + SEC-6 (6 tests)
- [x] `tests/phase_09/test_admin_settings.py` — ADMIN-03 + D-04 read-only set (13 tests)
- [x] `tests/phase_09/test_admin_backups.py` — ADMIN-04 + D-07/D-08 (14 tests)
- [x] `tests/phase_09/test_admin_system.py` — ADMIN-05/06 + raw-DB-query gotcha (17 tests)
- [x] `tests/phase_09/test_admin_security.py` — require_admin + CSRF coverage (4 tests)
- [x] Shared fixtures: admin user + regular user + brew_session rows + sessions rows — **self-seeding** in `conftest.py` (zero pytest.skip on missing data)
- [x] `respx` installed for the credential "Test connection" probe mocks

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Mobile-first layout at 375px (admin section nav collapses, no horizontal scroll) | D-01/D-02, project hard rule | Visual responsive check; not worth a Playwright run at this scale | Open each `/admin/*` page in DevTools at 375×667; confirm section nav usable, forms reachable, no horizontal scroll |
| "Force refresh all" actually re-bills every eligible user | D-13 | Live billing side effect; automated test mocks the SDK so cannot prove real spend | On VPS with real keys, click once, confirm `ai_recommendations` rows written with `generated_by="admin_force"` for each eligible user |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s (phase suite ~18s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** Validated 2026-05-21 — 64/64 phase-9 tests green, 0 skips, 0 gaps.

---

## Validation Audit 2026-05-21

State A audit (post-execution). All 6 plans had shipped their tests during
execution; this pass reconciled the stale pre-execution map against the real suite.
Test files were synced into the running container (file-level `docker compose cp`)
and run with `-rs` so any `pytest.skip` would surface as a gap, not a silent green.

| Metric | Count |
|--------|-------|
| Behavior rows mapped | 23 |
| COVERED (green) | 23 |
| PARTIAL | 0 |
| MISSING | 0 |
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

**Run:** `docker compose exec coffee-snobbery python -m pytest tests/phase_09/ -q -rs`
→ **64 passed, 0 skipped** (17.93s). The 64 passing tests equal the 64 collected
test functions — no pass-by-skip masking. The Plan 09-01 `test_csrf_required`
guarded skip ("no admin POST routes yet") is now a real assertion (POST routes exist)
and passes.

No `gsd-nyquist-auditor` spawned — zero gaps to fill. SEC-6 (decrypted key never in
response/template context) is proven behaviorally by `test_set_credential_masked`
(asserts the full key and its leading prefix are absent from the response body),
which supersedes the originally-planned static grep.
