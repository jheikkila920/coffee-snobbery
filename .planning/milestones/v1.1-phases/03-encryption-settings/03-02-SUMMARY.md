---
phase: 03-encryption-settings
plan: 02
subsystem: encryption
tags: [encryption, fernet, events, infrastructure, audit]
requires:
  - app/config.py:settings.APP_ENCRYPTION_KEY
  - app/events.py (Phase 1 base constants)
provides:
  - app.services.encryption.encrypt
  - app.services.encryption.decrypt
  - app.services.encryption.primary_key_fingerprint
  - app.services.encryption.startup_check
  - app.services.encryption.EncryptionStartupError
  - app.events.ADMIN_APP_SETTING_CHANGED
  - app.events.ADMIN_API_CREDENTIAL_SET
  - app.events.ENCRYPTION_STARTUP_OK
  - app.events.ENCRYPTION_REWRAP_COMPLETED
  - app.events.ENCRYPTION_DECRYPT_FAILED
affects:
  - Plan 03-03 (settings.py): imports ADMIN_APP_SETTING_CHANGED
  - Plan 03-04 (credentials.py): imports encrypt/decrypt/primary_key_fingerprint + ADMIN_API_CREDENTIAL_SET + ENCRYPTION_REWRAP_COMPLETED + ENCRYPTION_DECRYPT_FAILED
  - Plan 03-05 (lifespan): imports startup_check
  - Plan 03-06 (tests): imports the full encryption surface
tech-stack:
  added:
    - cryptography.fernet.MultiFernet (rotation-ready Fernet wrapper)
  patterns:
    - Module-level singleton constructed at import time (mirrors app/signing.py:session_signer)
    - Chained exceptions via "raise ... from exc" for operator-facing diagnostic chains
    - String-constant event taxonomy (mirrors existing app/events.py block)
key-files:
  created:
    - app/services/encryption.py (161 lines)
  modified:
    - app/events.py (+22 lines, no removals)
decisions:
  - D-12 (encryption side): two-module split — pure crypto here, CRUD in credentials.py
  - D-13: sentinel encrypt/decrypt round-trip at lifespan startup, fail-loud with chained cause
  - D-14 (helper only): primary_key_fingerprint() returns deterministic 64-char hex SHA-256
  - T-03-T1 mitigation: only the 8-char fingerprint prefix is logged, never the full hash or the raw key
  - T-03-T3 mitigation: empty/malformed APP_ENCRYPTION_KEY trips ValueError/binascii.Error at import or InvalidToken at sentinel; both surface as EncryptionStartupError out of startup_check
  - T-03-T8 mitigation: no new sensitive field name introduced; existing structlog redactor still covers the surface
metrics:
  completed: 2026-05-18
  tasks: 2
  duration: ~25 minutes
  files_created: 1
  files_modified: 1
---

# Phase 3 Plan 02: Encryption primitives + event constants

One-liner: Lands the pure-crypto `app/services/encryption.py` module (the
**only** module in the app that may instantiate `Fernet`/`MultiFernet` per
CLAUDE.md) and extends `app/events.py` with five new event constants that
Plans 03-03 / 03-04 / 03-05 depend on.

## Tasks completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Extend app/events.py with five Phase 3 constants | `e1a6335` | `app/events.py` |
| 2 | Create app/services/encryption.py (MultiFernet + 4 functions + EncryptionStartupError) | `295c02e` | `app/services/encryption.py` |

## Public surface

### `app/services/encryption.py`

```python
class EncryptionStartupError(RuntimeError): ...
def encrypt(plaintext: bytes) -> bytes: ...
def decrypt(ciphertext: bytes) -> bytes: ...
def primary_key_fingerprint() -> str: ...   # 64-char lowercase hex SHA-256
def startup_check() -> None: ...             # raises EncryptionStartupError on failure
```

`__all__ = ["EncryptionStartupError", "decrypt", "encrypt", "primary_key_fingerprint", "startup_check"]` (alphabetized).

`_multi_fernet: MultiFernet` is the module-level singleton, constructed
**exactly once** at import via `_build_multi_fernet()`. Verified via
`grep -c "MultiFernet(" app/services/encryption.py` → 1. No public call
re-instantiates Fernet/MultiFernet.

### `app/events.py` — five new constants (with exact dotted-snake strings)

| Constant | String value | Emitted by |
|----------|--------------|------------|
| `ADMIN_APP_SETTING_CHANGED` | `admin.app_setting_changed` | `services/settings.set_setting` (Plan 03-03) |
| `ADMIN_API_CREDENTIAL_SET` | `admin.api_credential_set` | `services/credentials.set_provider_credential` (Plan 03-04) |
| `ENCRYPTION_STARTUP_OK` | `encryption.startup_ok` | `services/encryption.startup_check` (this plan, success path) |
| `ENCRYPTION_REWRAP_COMPLETED` | `encryption.rewrap_completed` | `services/credentials.rewrap_if_needed` (Plan 03-04) |
| `ENCRYPTION_DECRYPT_FAILED` | `encryption.decrypt_failed` | `services/credentials.get_provider_credential` on `InvalidToken` (Plan 03-04) |

`__all__` updated alphabetically (verified by reading lines 78–94 of
`app/events.py`); the five new names slot between existing entries
without disturbing the existing ordering. The
`ADMIN_API_CREDENTIAL_SET` line carries `# noqa: S105` so Bandit does
not flag the substring "credential" as a hardcoded password.

## Decisions implemented

- **D-12 (encryption side):** Two-module split locked. This plan ships
  only the pure-crypto module; `credentials.py` (Plan 03-04) will be the
  sole consumer of `encrypt`/`decrypt` for `api_credentials`. No other
  module imports `cryptography.fernet`.
- **D-13:** Sentinel `decrypt(encrypt(b"snobbery-startup-check"))` runs
  inside `startup_check()`. On `(InvalidToken, ValueError, TypeError)` →
  `raise EncryptionStartupError(...) from exc` so the operator sees the
  chained root cause in the structured log. On integrity mismatch
  (round-trip returned wrong bytes) → raise without `from` because no
  underlying exception exists. The empty-key path actually trips at
  module import time via `_build_multi_fernet()` raising `ValueError`,
  which propagates out of the `import app.services.encryption` inside
  the lifespan body (Plan 03-05) — same operator outcome: uvicorn exits
  non-zero, docker healthcheck flips unhealthy.
- **D-14 (helper only):** `primary_key_fingerprint()` returns
  deterministic 64-char lowercase hex SHA-256 of the first parsed key.
  `_parse_keys()` is the single conversion point so the fingerprint
  helper and `_build_multi_fernet` see the exact same key list.

## Verification — automated checks run

Run inside the live `coffee-snobbery` container (cryptography 48 + structlog 25 installed):

1. **Five constants importable with exact strings.**
   ```
   python -c "from app.events import ENCRYPTION_STARTUP_OK, ENCRYPTION_REWRAP_COMPLETED,
                                     ENCRYPTION_DECRYPT_FAILED, ADMIN_APP_SETTING_CHANGED,
                                     ADMIN_API_CREDENTIAL_SET; print('OK')"
   ```
   → `OK`.

2. **Round-trip + fingerprint + startup_check happy path** (using a
   freshly generated `Fernet.generate_key()`):
   ```
   ct = encrypt(b'snobbery-test'); assert decrypt(ct) == b'snobbery-test'
   fp = primary_key_fingerprint()    # → 64 hex chars
   startup_check()                    # → emits encryption.startup_ok fingerprint=<8 hex>
   ```
   → `OK roundtrip + fingerprint + startup_check` and the structured
   log line `info encryption.startup_ok fingerprint=6810f08c`.

3. **Empty `APP_ENCRYPTION_KEY` → `ValueError` at import** with the
   exact message `"APP_ENCRYPTION_KEY is empty after splitting on
   commas"`. This is the D-13 fail-loud path before any DB I/O.

4. **Single MultiFernet construction site.** `grep -c "MultiFernet("
   app/services/encryption.py` → `1` (the call inside
   `_build_multi_fernet`).

5. **Lint clean.** `ruff check app/services/encryption.py app/events.py`
   → `All checks passed!`. `ruff format` applied (collapsed two
   multi-line strings; no behavior change).

6. **Syntax compiles.** `python -m py_compile app/events.py
   app/services/encryption.py` → exit 0.

## Threat surface confirmed

- **T-03-T1 (key disclosure in logs):** the startup-success log emits
  `fingerprint=primary_key_fingerprint()[:8]` only — 8 hex chars of a
  SHA-256 hash, never the raw key, never the full hash. The
  `EncryptionStartupError` message names the env var but never includes
  the key value. The existing structlog deny-list (`app/logging.py:55-75`)
  covers `api_key`, `secret`, `encryption_key`, etc.; this plan does not
  introduce a field name that bypasses the deny-list.
- **T-03-T3 (silent ciphertext):** any of (empty key list, malformed
  base64, round-trip integrity failure) raises
  `EncryptionStartupError` or `ValueError` out of the import / lifespan
  chain — uvicorn exits non-zero, docker healthcheck flips unhealthy.
- **T-03-T8 (audit redaction completeness):** the only emitted field on
  the new event is `fingerprint` (8-char prefix). No new sensitive-key
  spelling introduced.

## Deviations from plan

None — both tasks executed exactly as written. The plan's verified
RESEARCH.md code example was followed structurally; the only diff vs the
example is `import structlog` and `from app.events import
ENCRYPTION_STARTUP_OK` moved to module scope (rather than inside
`startup_check`) to align with the established `app/signing.py` and
`app/logging.py` pattern of module-level `log = structlog.get_logger(...)`.
This is consistent with PATTERNS.md §"Structlog audit emission" which
specifies module-level logger acquisition.

## Worktree note

This worktree's git HEAD started one commit behind the orchestrator's
expected base (`3280304`); the planning artifacts were restored via
`git restore --source=3280304 -- .planning/` without resetting HEAD (the
hard reset path was denied in this environment). Both touched files
(`app/events.py`, `app/services/encryption.py`) live cleanly above the
current HEAD and will merge into the orchestrator's integration branch
without conflict — `events.py` modifications are additive only;
`encryption.py` is new.

## Self-Check: PASSED

- File `app/services/encryption.py` exists: FOUND.
- File `app/events.py` modified (no removals): FOUND (verified by `git
  diff --diff-filter=D --name-only HEAD~2 HEAD` → empty).
- Commit `e1a6335` (Task 1) exists in `git log --oneline --all`: FOUND.
- Commit `295c02e` (Task 2) exists in `git log --oneline --all`: FOUND.
- All five event constants importable from `app.events` with exact
  dotted-snake strings: VERIFIED in container.
- Round-trip `encrypt`→`decrypt` returns input bytes: VERIFIED.
- `primary_key_fingerprint()` returns 64 hex chars: VERIFIED.
- `startup_check()` emits `encryption.startup_ok` on success: VERIFIED.
- `_multi_fernet` is module-level and constructed exactly once: VERIFIED
  via grep.
- `ruff check` clean on both files: VERIFIED.
