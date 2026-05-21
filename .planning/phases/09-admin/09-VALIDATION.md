---
phase: 9
slug: admin
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-21
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

> Task IDs (`9-NN-NN`) are assigned by the planner. Until then, this is the
> requirement→behavior→command map from `09-RESEARCH.md`; the planner/executor
> binds each row to a concrete task ID and wave.

| Requirement | Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|----------|-----------|-------------------|-------------|--------|
| ADMIN-01 | User list renders | smoke | `pytest tests/phase_09/test_admin_users.py::test_list_users -x` | ❌ W0 | ⬜ pending |
| ADMIN-01 | User create succeeds | unit | `pytest tests/phase_09/test_admin_users.py::test_create_user -x` | ❌ W0 | ⬜ pending |
| ADMIN-01 | Create fails < 12-char password | unit | `pytest tests/phase_09/test_admin_users.py::test_create_user_short_password -x` | ❌ W0 | ⬜ pending |
| ADMIN-01 | Last-admin delete/demote/deactivate blocked (D-16) | unit | `pytest tests/phase_09/test_admin_users.py::test_delete_last_admin_blocked -x` | ❌ W0 | ⬜ pending |
| ADMIN-01 | Self-lockout (demote/deactivate self) blocked (D-16) | unit | `pytest tests/phase_09/test_admin_users.py::test_self_demote_blocked -x` | ❌ W0 | ⬜ pending |
| ADMIN-01 | Hard-delete user with brew_sessions blocked (D-15, FK RESTRICT) | unit | `pytest tests/phase_09/test_admin_users.py::test_delete_user_with_sessions_blocked -x` | ❌ W0 | ⬜ pending |
| ADMIN-01 | Hard-delete empty/never-used user succeeds (D-15) | unit | `pytest tests/phase_09/test_admin_users.py::test_delete_empty_user -x` | ❌ W0 | ⬜ pending |
| ADMIN-01 | is_admin toggle invalidates target's sessions (async delete) | unit | `pytest tests/phase_09/test_admin_users.py::test_toggle_admin_invalidates_sessions -x` | ❌ W0 | ⬜ pending |
| ADMIN-02 | Set credential encrypts; last_four shown; key absent from response | unit | `pytest tests/phase_09/test_admin_credentials.py::test_set_credential_masked -x` | ❌ W0 | ⬜ pending |
| ADMIN-02 | Decrypted key never in Pydantic model/template ctx (SEC-6) | static/grep | CI grep: no decrypted-key field in template context | ❌ W0 | ⬜ pending |
| ADMIN-02 | Per-provider enable/disable + model select persists | unit | `pytest tests/phase_09/test_admin_credentials.py::test_provider_toggle_model -x` | ❌ W0 | ⬜ pending |
| ADMIN-03 | Settings editor renders all rows (read-only set flagged, D-04) | smoke | `pytest tests/phase_09/test_admin_settings.py::test_settings_list -x` | ❌ W0 | ⬜ pending |
| ADMIN-03 | Editable row save calls set_setting + invalidates cache (D-06) | unit | `pytest tests/phase_09/test_admin_settings.py::test_setting_save -x` | ❌ W0 | ⬜ pending |
| ADMIN-03 | Read-only/system rows reject edits (D-04) | unit | `pytest tests/phase_09/test_admin_settings.py::test_readonly_rows_rejected -x` | ❌ W0 | ⬜ pending |
| ADMIN-04 | Backup list renders retained files (size + timestamp) | smoke | `pytest tests/phase_09/test_admin_backups.py::test_backup_list -x` | ❌ W0 | ⬜ pending |
| ADMIN-04 | Backup download — valid filename serves file | unit | `pytest tests/phase_09/test_admin_backups.py::test_download_valid -x` | ❌ W0 | ⬜ pending |
| ADMIN-04 | Backup download — path traversal blocked (D-08) | unit | `pytest tests/phase_09/test_admin_backups.py::test_download_path_traversal -x` | ❌ W0 | ⬜ pending |
| ADMIN-04 | "Run backup now" (sync def) returns BackupResult (D-07) | integration | `pytest tests/phase_09/test_admin_backups.py::test_run_backup_now -x` | ❌ W0 | ⬜ pending |
| ADMIN-05 | System info renders version/storage/sessions/last-backup (D-09) | smoke | `pytest tests/phase_09/test_admin_system.py::test_system_info -x` | ❌ W0 | ⬜ pending |
| ADMIN-06 | Health panel reads last_ai_run_status via RAW DB query (cache-pop gotcha) | unit | `pytest tests/phase_09/test_admin_system.py::test_health_panel_raw_db -x` | ❌ W0 | ⬜ pending |
| ADMIN-06 | Health panel surfaces per-provider last error + last 5 errors (D-10) | unit | `pytest tests/phase_09/test_admin_system.py::test_health_panel_errors -x` | ❌ W0 | ⬜ pending |
| SEC | `require_admin` on every admin route → non-admin 403 | unit | `pytest tests/phase_09/test_admin_security.py::test_non_admin_403 -x` | ❌ W0 | ⬜ pending |
| SEC | CSRF required on every state-changing admin form | unit | `pytest tests/phase_09/test_admin_security.py::test_csrf_required -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/phase_09/__init__.py`
- [ ] `tests/phase_09/test_admin_users.py` — ADMIN-01 + D-15/D-16 guards
- [ ] `tests/phase_09/test_admin_credentials.py` — ADMIN-02 + SEC-6
- [ ] `tests/phase_09/test_admin_settings.py` — ADMIN-03 + D-04 read-only set
- [ ] `tests/phase_09/test_admin_backups.py` — ADMIN-04 + D-07/D-08
- [ ] `tests/phase_09/test_admin_system.py` — ADMIN-05/06 + raw-DB-query gotcha
- [ ] `tests/phase_09/test_admin_security.py` — require_admin + CSRF coverage
- [ ] Shared fixtures: admin user + regular user + brew_session rows + sessions rows — **self-seeding** (do not skip on missing data), extend existing `conftest.py`
- [ ] `respx` installed for the credential "Test connection" probe mocks

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Mobile-first layout at 375px (admin section nav collapses, no horizontal scroll) | D-01/D-02, project hard rule | Visual responsive check; not worth a Playwright run at this scale | Open each `/admin/*` page in DevTools at 375×667; confirm section nav usable, forms reachable, no horizontal scroll |
| "Force refresh all" actually re-bills every eligible user | D-13 | Live billing side effect; automated test mocks the SDK so cannot prove real spend | On VPS with real keys, click once, confirm `ai_recommendations` rows written with `generated_by="admin_force"` for each eligible user |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
