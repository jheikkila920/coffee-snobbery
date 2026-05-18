---
phase: 3
slug: encryption-settings
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-18
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source of truth: `03-RESEARCH.md` "## Validation Architecture" section.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (already installed via Phase 0 / Phase 2 test infra) |
| **Config file** | `pyproject.toml` (pytest section); `tests/conftest.py` |
| **Quick run command** | `docker compose exec coffee-snobbery pytest tests/test_encryption.py tests/test_settings.py tests/test_credentials.py -x` |
| **Full suite command** | `docker compose exec coffee-snobbery pytest` |
| **Estimated runtime** | Quick ~3s · Full ~25s |

---

## Sampling Rate

- **After every task commit:** Run quick command (the three Phase 3 test files)
- **After every plan wave:** Run full suite (catches cross-phase regressions — e.g., Phase 2 raw-SQL setup_completed read site)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

> Populated by the planner during plan generation. Rows below are the Nyquist-derived test universe from RESEARCH.md "## Validation Architecture". The planner maps each `{N}-{plan}-{task}` task ID into the rows it satisfies.

| # | Plan | Wave | Requirement | Decision | Secure Behavior | Test Type | Automated Command | Status |
|---|------|------|-------------|----------|-----------------|-----------|-------------------|--------|
| 1 | 02 (impl) + 06 (test) | 1 | SEC-08 | D-09, D-12 | `decrypt(encrypt(b"x")) == b"x"` round-trip | unit | `pytest tests/services/test_encryption.py::test_encrypt_decrypt_roundtrip` | ✅ |
| 2 | 02 (impl) + 06 (test) | 1 | SEC-08 | D-09 | Token encrypted under primary key K1 decrypts after rotation `(K2, K1)` (K1 now secondary) | unit | `pytest tests/services/test_encryption.py::test_rotation_decrypts_old_token` | ✅ |
| 3 | 02 (impl) + 06 (test) | 1 | SEC-08 | D-12 | Token encrypted under K1 fails to decrypt when MultiFernet has only `[K3]` (`InvalidToken`) | unit | `pytest tests/services/test_encryption.py::test_unknown_key_raises_invalid_token` | ✅ |
| 4 | 02 (impl) + 06 (test) | 1 | SEC-09 | D-13 | `startup_check()` raises `EncryptionStartupError` when `APP_ENCRYPTION_KEY` is empty/malformed | unit | `pytest tests/services/test_encryption.py::test_startup_check_fails_loudly_on_empty_key` | ✅ |
| 5 | 02 (impl) + 06 (test) | 1 | SEC-09 | D-13 | `startup_check()` returns None and emits `event=ENCRYPTION_STARTUP_OK` on healthy key | unit | `pytest tests/services/test_encryption.py::test_startup_check_emits_ok_event` | ✅ |
| 6 | 02 (impl) + 06 (test) | 1 | SEC-08 | D-14 | `primary_key_fingerprint()` returns deterministic SHA-256 hex of first key string | unit | `pytest tests/services/test_encryption.py::test_fingerprint_stable_and_hex` | ✅ |
| 7 | 03 (impl) + 06 (test) | 1 | (substrate) | D-06 | `prewarm_cache(db)` loads every `app_settings` row into `_cache` with coerced values | unit | `pytest tests/services/test_settings.py::test_prewarm_loads_all_rows` | ✅ |
| 8 | 03 (impl) + 06 (test) | 1 | (substrate) | D-05 | `get_str` / `get_int` / `get_bool` / `get_json` return coerced values; `'null'` rows → `None` | unit | `pytest tests/services/test_settings.py::test_typed_accessors_coerce` | ✅ |
| 9 | 03 (impl) + 06 (test) | 1 | (substrate) | D-05 | Accessor type mismatch raises `SettingTypeError` (e.g., `get_int` on a string row) | unit | `pytest tests/services/test_settings.py::test_type_mismatch_raises` | ✅ |
| 10 | 03 (impl) + 06 (test) | 1 | (substrate) | D-08 | `set_setting(db, key, value, *, by_user_id)` UPDATEs row, invalidates cache, next read returns new value | unit | `pytest tests/services/test_settings.py::test_write_through_invalidate` | ✅ |
| 11 | 03 (impl) + 06 (test) | 1 | (substrate) | D-08 | `set_setting` emits structured event `ADMIN_APP_SETTING_CHANGED` with `setting_key`, `value_type`, `user_id` | unit | `pytest tests/services/test_settings.py::test_emits_admin_app_setting_changed_event` | ✅ |
| 12 | 03 (impl) + 06 (test) | 1 | (substrate) | D-05 | Unknown key raises `SettingNotFoundError` | unit | `pytest tests/services/test_settings.py::test_unknown_key_raises_not_found` | ✅ |
| 13 | 04 (impl) + 06 (test) | 2 | SEC-08 | D-01, D-03 | `set_provider_credential(db, 'anthropic', key='sk-x', ...)` UPDATEs row with `key_ciphertext` (encrypted), `last_four='sk-x'[-4:]`, `is_enabled` unchanged unless explicitly set | unit | `pytest tests/services/test_credentials.py::test_set_provider_credential_writes_ciphertext_and_last_four` | ✅ |
| 14 | 04 (impl) + 06 (test) | 2 | SEC-08 | D-09, D-11 | `get_provider_credential(db, 'anthropic')` returns `ProviderCredential` with decrypted `key`, `model_name`, `last_four`; `frozen=True, slots=True` enforced | unit | `pytest tests/services/test_credentials.py::test_get_returns_frozen_dataclass` | ✅ |
| 15 | 04 (impl) + 06 (test) | 2 | SEC-08 | D-04, D-10 | Seeded empty row (`is_enabled=false, key_ciphertext=NULL`) → `get_provider_credential` returns None | unit | `pytest tests/services/test_credentials.py::test_disabled_or_empty_returns_none` | ✅ |
| 16 | 04 (impl) + 06 (test) | 2 | SEC-08 | D-10 | Row with `is_enabled=false` and populated ciphertext still returns None | unit | `pytest tests/services/test_credentials.py::test_disabled_with_ciphertext_returns_none` | ✅ |
| 17 | 04 (impl) + 06 (test) | 2 | SEC-08, SEC-09 | D-15 | Orphaned ciphertext (key removed from `APP_ENCRYPTION_KEY`) → `get_provider_credential` returns None AND emits `ENCRYPTION_DECRYPT_FAILED` event | unit | `pytest tests/services/test_credentials.py::test_orphan_ciphertext_returns_none_and_emits` | ✅ |
| 18 | 04 (impl) + 06 (test) | 2 | SEC-08 | D-01 | Rotating an existing provider (`set_provider_credential` again) overwrites all four fields atomically; old ciphertext no longer present | unit | `pytest tests/services/test_credentials.py::test_rotation_overwrites_in_place` | ✅ |
| 19 | 04 (impl) + 06 (test) | 2 | SEC-08 | D-08 | `set_provider_credential` emits `ADMIN_API_CREDENTIAL_SET` with `provider`, `last_four`, `model_name`, `by_user_id` — never logs `key` or `key_ciphertext` | unit | `pytest tests/services/test_credentials.py::test_set_emits_event_without_key` | ✅ |
| 20 | 04 (impl) + 06 (test) | 2 | SEC-08 | D-14 | `rewrap_if_needed(db)` on first deploy with empty credentials no-ops, leaves fingerprint NULL | unit | `pytest tests/services/test_credentials.py::test_rewrap_no_credentials_noop` | ✅ |
| 21 | 04 (impl) + 06 (test) | 2 | SEC-08 | D-14 | `rewrap_if_needed(db)` when fingerprint matches current primary no-ops (idempotent) | unit | `pytest tests/services/test_credentials.py::test_rewrap_idempotent_when_fingerprint_matches` | ✅ |
| 22 | 04 (impl) + 06 (test) | 2 | SEC-08 | D-14 | `rewrap_if_needed(db)` on key rotation re-encrypts every populated row under new primary, writes new fingerprint, emits `ENCRYPTION_REWRAP_COMPLETED` with `row_count` | integration | `pytest tests/services/test_credentials.py::test_rewrap_rotates_ciphertexts_and_writes_fingerprint` | ✅ |
| 23 | 01 (impl) + 06 (test) | 1 | SEC-08 | D-04 | Alembic `upgrade head` creates `api_credentials` table with `(provider, key_ciphertext bytea, last_four, model_name, is_enabled, created_at, updated_at, updated_by_user_id)` and CHECK `provider IN ('anthropic','openai')` | integration | `pytest tests/test_migrations.py::test_api_credentials_table_exists tests/test_migrations.py::test_api_credentials_columns tests/test_migrations.py::test_api_credentials_provider_check_constraint` | ✅ |
| 24 | 01 (impl) + 06 (test) | 1 | SEC-08 | D-04 | Migration seeds two `api_credentials` rows: `('anthropic', NULL, NULL, NULL, false, ...)` and `('openai', NULL, NULL, NULL, false, ...)` | integration | `pytest tests/test_migrations.py::test_api_credentials_seeded_with_two_rows` | ✅ |
| 25 | 01 (impl) + 06 (test) | 1 | SEC-08 | (specifics) | Migration adds `encryption_key_primary_fingerprint` row to `app_settings` with `value_type='null'`, `value=NULL` | integration | `pytest tests/test_migrations.py::test_app_settings_has_encryption_key_primary_fingerprint_row` | ✅ |
| 26 | 05 (impl) + 06 (test) | 3 | SEC-09 | D-16 | App startup executes `encryption.startup_check()` → `credentials.rewrap_if_needed(db)` → `settings.prewarm_cache(db)` in order; bad key short-circuits before DB I/O | integration | `pytest tests/test_lifespan_phase3.py::test_phase3_hooks_run_in_order` | ✅ |
| 27 | 04 (impl) + 06 (test) | — | SEC-08 (SEC-6) | (CLAUDE.md) | No Pydantic model in `app/` has `api_key` or decrypted-key field; `ApiCredential` model does not expose `key_ciphertext` to API responses | unit | `pytest tests/services/test_credentials.py::test_no_pydantic_carries_decrypted_key` (placeholder — Phase 12 owns the formal grep test per ROADMAP §3 Notes) | ✅ |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/services/test_encryption.py` — new file; covers rows 1–6 (Plan 03-06 Task 2)
- [x] `tests/services/test_settings.py` — new file; covers rows 7–12 (Plan 03-06 Task 3)
- [x] `tests/services/test_credentials.py` — new file; covers rows 13–22, 27 (Plan 03-06 Task 4)
- [x] `tests/test_migrations.py` — extended; covers rows 23–25 (Plan 03-06 Task 5)
- [x] `tests/test_lifespan_phase3.py` — new file; covers row 26 (Plan 03-06 Task 6)
- [x] `tests/conftest.py` — extended with `fernet_key`, `fernet_key_str`, `monkeypatched_app_encryption_key` fixtures (Plan 03-06 Task 1)
- [x] No new framework install — pytest 9.x already present from Phase 0

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Operator key-rotation runbook end-to-end | SEC-08 | Requires real container restart cycle; depends on docker-compose orchestration | 1) Set `APP_ENCRYPTION_KEY=K1`, start container, manually set an `anthropic` key via Python REPL into the DB. 2) Stop container. 3) Set `APP_ENCRYPTION_KEY=K2,K1` (new primary, old as secondary). 4) Start container. 5) Confirm `ENCRYPTION_REWRAP_COMPLETED` log with `row_count=1`. 6) Confirm `get_provider_credential(db, 'anthropic')` still returns decrypted key. 7) Stop container, set `APP_ENCRYPTION_KEY=K2`, start. 8) Confirm still works (fingerprint matches, no-op). |
| Docker-compose healthcheck flips unhealthy on bad APP_ENCRYPTION_KEY | SEC-09 | Requires docker-compose health-check interaction outside the pytest harness | 1) Set `APP_ENCRYPTION_KEY=invalid-not-base64`. 2) `docker compose up coffee-snobbery`. 3) Confirm container exits non-zero with `EncryptionStartupError` in logs and healthcheck status is unhealthy. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (5 new test files + conftest extensions)
- [x] No watch-mode flags
- [x] Feedback latency < 30s (quick command < 3s, full suite < 25s)
- [x] `nyquist_compliant: true` set in frontmatter after planner maps task IDs into the Per-Task Verification Map

**Approval:** approved 2026-05-18 (Plan 03-06 — every Validation Map row now has an automated test).
