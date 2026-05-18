---
phase: 03-encryption-settings
verified: 2026-05-18T12:00:00Z
status: human_needed
score: 4/4 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 2/4
  gaps_closed:
    - "CR-01: updated_at now advances on every Core UPDATE — onupdate removed from model, updated_at=func.now() added to set_provider_credential and set_provider_enabled .values() blocks, row.updated_at=func.now() added to rewrap_if_needed ORM loop; regression test test_updated_at_advances_on_set_and_toggle passes."
    - "CR-02: fingerprint baseline write is now unconditional in set_provider_credential — conditional if stored_fp is None guard removed; regression test test_fingerprint_baseline_rewritten_on_every_set passes."
  gaps_remaining: []
  regressions: []
follow_ups:
  - id: WR-01
    file: "app/services/credentials.py"
    lines: "345-362"
    description: "FOR UPDATE lock acquired before early-return fingerprint check in rewrap_if_needed. On the common no-op path (stored_fp == new_fp), the lock is held until the session context manager triggers rollback. No deadlock risk at single-worker scale, but the lock is held unnecessarily. Move fingerprint comparison before the SELECT FOR UPDATE."
    severity: warning
    target_phase: 9
  - id: WR-02
    file: "tests/conftest.py"
    lines: "422-445"
    description: "monkeypatched_app_encryption_key fixture does not restore _multi_fernet after test; module-level singleton retains the test key. Safe because every Phase 3 test requests the fixture, but fragile if test ordering changes. Add importlib.reload(enc_mod) in a yield-then-reload teardown."
    severity: warning
    target_phase: 12
  - id: WR-03
    file: "app/services/settings.py"
    lines: "199-244"
    description: "set_setting accepts value: Any without checking type coherence against value_type. A caller can silently write a non-numeric string into an int row; the next get_int() raises unhandled ValueError. Exploitable only from authenticated admin paths (Phase 9 scope)."
    severity: warning
    target_phase: 9
human_verification:
  - test: "Docker healthcheck fails loudly on bad APP_ENCRYPTION_KEY"
    expected: "Container exits non-zero with EncryptionStartupError in logs; docker compose ps shows the service as unhealthy or exited"
    why_human: "Requires a live docker-compose lifecycle. startup_check fast-fail is verified by unit test; the container-level healthcheck flip requires a running container with a corrupted env var."
  - test: "Key rotation runbook end-to-end across container restart"
    expected: "After setting K1, stopping, setting APP_ENCRYPTION_KEY=K2,K1, restarting — ENCRYPTION_REWRAP_COMPLETED log appears with row_count=1 and get_provider_credential still decrypts correctly."
    why_human: "Requires a real docker-compose restart cycle with a persistent volume. The rewrap logic is unit-tested but the full lifecycle (env var change -> restart -> rewrap -> prewarm in order) requires an operator smoke."
---

# Phase 3: Encryption + Settings Verification Report

**Phase Goal:** `services/encryption.py` exposes `MultiFernet` round-trip from day one (so a future key rotation doesn't orphan stored API keys), `app_settings` is queryable via a typed reader with in-memory cache + write-through invalidation, and `api_credentials` rows persist encrypted at rest. This is the substrate for Phase 7 (AI service) and Phase 9 (admin).
**Verified:** 2026-05-18 (re-verification after gap closure commit fafd6d8)
**Status:** human_needed
**Re-verification:** Yes — after CR-01 and CR-02 gap closure

---

## Re-verification Summary

Previous status: `gaps_found` (score 2/4). Two blockers identified:

- **CR-01**: `updated_at` permanently frozen at `created_at` because `onupdate=func.now()` is ignored by Core UPDATE callers.
- **CR-02**: Fingerprint baseline write guarded by `if stored_fp is None` — skipped on second set after mid-session key change.

Both have been resolved in commit `fafd6d8`. All four success criteria now verify PASS. Two human smoke tests remain from the initial verification and are unchanged.

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `services/encryption.py` constructs `MultiFernet([Fernet(primary), Fernet(secondary)])` from `APP_ENCRYPTION_KEY`; round-trip works after rotation | VERIFIED | CR-02 closed: `set_provider_credential` now unconditionally rewrites the fingerprint to `encryption.primary_key_fingerprint()` after every set (lines 244-254 of `credentials.py`). The `if stored_fp is None` guard is gone. `test_fingerprint_baseline_rewritten_on_every_set` (line 672) confirms the invariant "fingerprint == key the ciphertext is encrypted under" holds after a mid-session key change + second set. |
| 2 | Missing/malformed `APP_ENCRYPTION_KEY` causes startup to fail loudly | VERIFIED | Unchanged from initial: `_build_multi_fernet` raises `ValueError` at import on empty key; `startup_check()` raises `EncryptionStartupError`; lifespan calls it first (main.py line 154). Unit test `test_startup_check_fails_loudly_on_empty_key` passes. |
| 3 | `app_settings` queryable via `services/settings.py` with `value_type`-aware coercion; cached in-memory, invalidated on write | VERIFIED | Unchanged from initial: `settings.py` 295 lines, all four typed accessors, `prewarm_cache`, `set_setting` with cache pop after commit. 6 unit tests pass. |
| 4 | `api_credentials` rows persist key material only as ciphertext; reading returns a transient `frozen+slots` dataclass (no Pydantic model carries decrypted `api_key`) | VERIFIED | CR-01 closed: `onupdate=func.now()` removed from `ApiCredential.updated_at` (model now carries explanatory comment at lines 67-69); `updated_at=func.now()` explicitly included in `set_provider_credential` `.values()` (line 228), `set_provider_enabled` `.values()` (line 289), and `row.updated_at = func.now()` in the `rewrap_if_needed` ORM loop (line 381). `test_updated_at_advances_on_set_and_toggle` (line 614) asserts the timestamp advances on both a set and a toggle. `test_no_pydantic_carries_decrypted_key` passes. |

**Score:** 4/4 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/services/encryption.py` | MultiFernet primitives + startup_check + fingerprint | VERIFIED | 162 lines. `_build_multi_fernet`, `startup_check`, `primary_key_fingerprint`. Module-level singleton. |
| `app/services/settings.py` | Typed reader + cache + write-through invalidation | VERIFIED | 295 lines. All four typed accessors, prewarm, set, invalidate. |
| `app/services/credentials.py` | CRUD + ProviderCredential dataclass + rewrap | VERIFIED | 407 lines. All five public functions. CR-01 and CR-02 fixes applied. |
| `app/models/api_credential.py` | ApiCredential ORM model — no onupdate | VERIFIED | 87 lines. `onupdate=func.now()` removed; comment at line 67-69 explains why. `server_default=func.now()` retained for initial row creation. |
| `app/migrations/versions/p3_api_credentials.py` | Migration creating `api_credentials` + seeding + fingerprint row | VERIFIED | Creates table with CHECK constraint, seeds 2 provider rows, inserts fingerprint row with `value_type='null'`. |
| `tests/services/test_encryption.py` | 6 encryption unit tests | VERIFIED | Round-trip, rotation, orphan InvalidToken, startup fail-loud, startup ok event, fingerprint stability. |
| `tests/services/test_settings.py` | 6 settings unit tests | VERIFIED | Prewarm, coercion, type mismatch, write-through, audit event, unknown key. |
| `tests/services/test_credentials.py` | 11 credentials tests + SEC-6 placeholder + 2 regression tests | VERIFIED | Original 11 tests pass. `test_updated_at_advances_on_set_and_toggle` (CR-01 regression) at line 614 and `test_fingerprint_baseline_rewritten_on_every_set` (CR-02 regression) at line 672 are present and substantive. |
| `tests/test_lifespan_phase3.py` | 3 lifespan integration tests | VERIFIED | Hook order spy (D-16), bad-key short-circuit (T-03-T3), post-lifespan cache population. |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `app/main.py` lifespan | `encryption.startup_check` | `encryption_startup_check()` line 154 | WIRED | First call in lifespan; propagates `EncryptionStartupError` → uvicorn exits. |
| `app/main.py` lifespan | `credentials.rewrap_if_needed` | `credentials.rewrap_if_needed(db)` line 156 | WIRED | Called after startup_check, before prewarm_cache (D-16 order). |
| `app/main.py` lifespan | `settings_service.prewarm_cache` | `settings_service.prewarm_cache(db)` line 157 | WIRED | Called last in lifespan so rewrap's new fingerprint lands in cache (T-03-T5). |
| `credentials.py` | `encryption.py` | `encryption.encrypt()` / `encryption.decrypt()` | WIRED | Only module that touches Fernet per CLAUDE.md invariant. No other `app/` file imports from `cryptography.fernet`. |
| `credentials.py` | `settings.py` | `settings_service.get_str(_FINGERPRINT_KEY)`, `settings_service.invalidate()` | WIRED | Fingerprint read/write coordination. `set_provider_credential` unconditional fingerprint update (lines 244-254) + `rewrap_if_needed` (lines 388-393). |
| `set_provider_credential` | `app_settings.encryption_key_primary_fingerprint` | Direct Core UPDATE (documented exception) | WIRED | CR-02 resolved: unconditional `update(AppSetting).values(value=encryption.primary_key_fingerprint(), ...)` on every call; no longer conditional on `stored_fp is None`. |

---

### Data-Flow Trace (Level 4)

Not applicable — Phase 3 is a services/infrastructure phase with no UI rendering components.

---

### Behavioral Spot-Checks

Step 7b skipped: Phase 3 has no runnable API endpoints or CLI entry points. All behaviors are exercised through the test suite.

---

### Probe Execution

No `scripts/*/tests/probe-*.sh` probes defined or referenced for Phase 3. Step 7c: SKIPPED (no probe files).

---

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SEC-08 | 03-01, 03-02, 03-04, 03-06 | API keys encrypted at rest with `MultiFernet` (rotation-ready from day one); never logged; admin UI shows only last 4 characters | SATISFIED | Encryption and storage correct. `last_four` denormalization verified. API keys never logged (audit events carry only `last_four` and `provider`). Admin UI last-4 display is Phase 9 scope. CR-01 (`updated_at` stale) and CR-02 (fingerprint conditional) both closed. |
| SEC-09 | 03-02, 03-05, 03-06 | `APP_ENCRYPTION_KEY` documented; absent or malformed key crashes startup loudly | SATISFIED | `.env.example` and `app/config.py` document the var. `_build_multi_fernet` raises `ValueError` on empty key at import time. `startup_check` provides belt-and-suspenders. Lifespan calls it first. |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `app/services/credentials.py` | 345-362 | FOR UPDATE lock acquired before early-return fingerprint check (WR-01) | WARNING | Lock held on common no-op path until session `__exit__` triggers rollback. No deadlock at single-worker scale. Tracked as follow-up WR-01. |
| `tests/conftest.py` | 422-445 | `monkeypatched_app_encryption_key` does not restore `_multi_fernet` after test (WR-02) | WARNING | Module singleton retains test key. Safe given current test ordering; fragile to ordering changes. Tracked as follow-up WR-02. |
| `app/services/settings.py` | 199-244 | `set_setting` accepts `value: Any` without type coherence check against `value_type` (WR-03) | WARNING | Authenticated admin can silently write non-numeric string into an `int` row; next `get_int()` raises unhandled `ValueError`. Phase 9 scope. Tracked as follow-up WR-03. |

**Debt marker gate:** No `TBD`, `FIXME`, or `XXX` markers found in Phase 3 files. Gate: PASS.

---

### Human Verification Required

#### 1. Docker healthcheck container exit

**Test:** Set `APP_ENCRYPTION_KEY=invalid-not-base64` in `.env`. Run `docker compose up coffee-snobbery`. Wait for startup.
**Expected:** Container exits non-zero. Logs show `EncryptionStartupError`. `docker compose ps` shows the service as unhealthy or exited.
**Why human:** Requires a live docker-compose lifecycle that pytest cannot replicate in-process.

#### 2. Key rotation runbook smoke (container restart cycle)

**Test:** (1) Set `APP_ENCRYPTION_KEY=K1`, start container, use admin to set an Anthropic key. (2) Stop container. (3) Set `APP_ENCRYPTION_KEY=K2,K1`. (4) Restart container. (5) Inspect logs for `encryption.rewrap_completed` with `row_count=1`. (6) Confirm the AI key is still retrievable.
**Expected:** `rewrap_completed` emitted once with `row_count=1`. `get_provider_credential` returns the original key under the new primary encryption.
**Why human:** Full docker-compose restart cycle with persistent volume data; cannot be simulated in the in-process pytest suite without a running DB container.

---

### Follow-Up Items (Advisory — Not Blocking)

These three warnings from the original code review are acknowledged. None blocks phase completion. They are tracked here for Phase 9 planning.

| ID | File | Issue | Target Phase |
|----|------|-------|-------------|
| WR-01 | `app/services/credentials.py:345-362` | FOR UPDATE lock held on common early-return path in `rewrap_if_needed`; move fingerprint check before SELECT FOR UPDATE | 9 |
| WR-02 | `tests/conftest.py:422-445` | `monkeypatched_app_encryption_key` does not restore `_multi_fernet` singleton after test; add `importlib.reload(enc_mod)` in teardown | 12 |
| WR-03 | `app/services/settings.py:199-244` | `set_setting` accepts `value: Any` without type coherence validation; add `isinstance` checks before serialization | 9 |

---

### Gap Closure Verification Detail

**CR-01 (closed):**

`app/models/api_credential.py` lines 67-74 — `onupdate=func.now()` is removed. The column now reads:
```
updated_at: Mapped[datetime] = mapped_column(
    TIMESTAMP(timezone=True),
    nullable=False,
    server_default=func.now(),
)
```
with an explanatory comment at lines 67-69.

`app/services/credentials.py`:
- Line 228: `updated_at=func.now()` in `set_provider_credential` `.values()` block — PRESENT.
- Line 289: `updated_at=func.now()` in `set_provider_enabled` `.values()` block — PRESENT.
- Line 381: `row.updated_at = func.now()` in `rewrap_if_needed` ORM loop — PRESENT. (ORM-style is correct here since rewrap already uses ORM attribute assignment for `key_ciphertext`.)

Regression test `test_updated_at_advances_on_set_and_toggle` (lines 614-669) exercises all three write paths and asserts timestamps advance strictly.

**CR-02 (closed):**

`app/services/credentials.py` lines 232-254 — the conditional `if stored_fp is None` block is replaced with an unconditional `db.execute(update(AppSetting).where(...).values(value=encryption.primary_key_fingerprint(), value_type="string", ...))`. An explanatory comment (lines 232-243) documents the rationale. `settings_service.invalidate(_FINGERPRINT_KEY)` at line 254 maintains write-through cache coherence.

Regression test `test_fingerprint_baseline_rewritten_on_every_set` (lines 672-738) simulates a mid-session key change by directly patching `cfg.APP_ENCRYPTION_KEY` and reloading the encryption module, then confirms the second `set_provider_credential` call writes the new primary's fingerprint — not the old one.

---

_Verified: 2026-05-18_
_Verifier: Claude (gsd-verifier)_
_Re-verification after commit fafd6d8 (fix(03): CR-01 updated_at, CR-02 unconditional fingerprint)_
