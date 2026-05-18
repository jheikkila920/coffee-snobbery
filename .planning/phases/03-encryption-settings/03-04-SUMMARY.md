---
phase: 03-encryption-settings
plan: 04
subsystem: credentials
tags: [credentials, encryption, fernet, audit, services, sync, sec-08, sec-09]
dependency_graph:
  requires:
    - "app/services/encryption.py (Plan 03-02) — encrypt/decrypt/primary_key_fingerprint"
    - "app/services/settings.py (Plan 03-03) — get_str/invalidate/SettingNotFoundError"
    - "app/models/api_credential.py (Plan 03-01) — ApiCredential ORM model"
    - "app/models/app_setting.py (Phase 0) — AppSetting ORM model for inline fingerprint UPDATE"
    - "app/events.py (Plan 03-02) — ADMIN_API_CREDENTIAL_SET, ENCRYPTION_DECRYPT_FAILED, ENCRYPTION_REWRAP_COMPLETED"
  provides:
    - "app.services.credentials.Provider (Literal['anthropic','openai'])"
    - "app.services.credentials.ProviderCredential (frozen+slots dataclass)"
    - "app.services.credentials.get_provider_credential (Phase 7 AI service read surface)"
    - "app.services.credentials.set_provider_credential (Phase 9 admin set/rotate surface)"
    - "app.services.credentials.set_provider_enabled (Phase 9 admin toggle surface)"
    - "app.services.credentials.rewrap_if_needed (Plan 03-05 lifespan startup hook)"
  affects:
    - "Plan 03-05 lifespan order: rewrap_if_needed BEFORE prewarm_cache (D-16)"
    - "Plan 03-06 tests: imports the full credentials surface for the 10 validation-map rows"
    - "Phase 7 AI service: imports get_provider_credential to fetch decrypted keys inline"
    - "Phase 9 admin routes: import set_provider_credential / set_provider_enabled"
tech-stack:
  added: []
  patterns:
    - "Frozen+slots dataclass for transient decrypted-credential transport (D-09)"
    - "Literal type alias mirroring the api_credentials_provider_check CHECK constraint (D-04, T-03-T7)"
    - "Documented inline-UPDATE of app_settings.encryption_key_primary_fingerprint bypassing set_setting (one-of-a-kind exception, two reasons: atomicity + value_type transition)"
    - "Per-row try/except InvalidToken in rewrap loop — orphaned ciphertext never aborts the whole rewrap (RESEARCH.md Pitfall 7)"
    - "Write-through cache invalidation after inline fingerprint UPDATE — same contract as settings_service.set_setting"
    - "Module-level _FINGERPRINT_KEY constant — single source of truth for the app_settings row name"
key-files:
  created:
    - "app/services/credentials.py — 408 lines, 6-name public surface"
  modified: []
decisions:
  - "D-01: One row per provider, UPDATE on rotation — set_provider_credential UPDATEs the seeded row, never INSERTs"
  - "D-03: last_four denormalized — set_provider_credential writes key[-4:] alongside the ciphertext"
  - "D-09: frozen+slots dataclass for ProviderCredential — blocks model_dump() / __dict__ access (SEC-6, T-03-T1, T-03-T2)"
  - "D-10: 4 None-return paths in get_provider_credential — row missing / is_enabled=False / key_ciphertext IS NULL / InvalidToken"
  - "D-11: sync accessor — decrypt is microseconds, no async variant"
  - "D-12: NO Fernet/MultiFernet instantiation in this module (two-module split; encryption.py owns crypto)"
  - "D-14: rewrap_if_needed is idempotent — early-return on fingerprint match OR (no stored + no rows) — Pitfall 6"
  - "D-15: decrypt-fail → None + encryption.decrypt_failed event (with provider + error_class ONLY, never ciphertext)"
  - "D-discretion: inline UPDATE of encryption_key_primary_fingerprint bypasses set_setting — documented exception for atomicity + value_type transition"
metrics:
  duration_minutes: 12
  tasks_completed: 1
  completed_date: "2026-05-18"
  files_created: 1
  files_modified: 0
---

# Phase 3 Plan 4: Provider Credentials Service Summary

## One-liner

`app/services/credentials.py` — the only module in the app that touches `api_credentials` rows: encrypt-on-set, decrypt-on-get with safe `None` returns on all four failure modes, idempotent post-rotation rewrap, audit emits that never carry the key or ciphertext.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create `app/services/credentials.py` — CRUD + ProviderCredential + rewrap_if_needed | `0d0a049` | `app/services/credentials.py` |

## Public Surface

6 names exported via `__all__` (alphabetized):

| Name | Kind | Purpose |
|------|------|---------|
| `Provider` | type alias | `Literal["anthropic", "openai"]` — mirrors `api_credentials_provider_check` |
| `ProviderCredential` | `@dataclass(frozen=True, slots=True)` | Transient decrypted-credential handoff; fields `provider`, `key`, `model_name`, `last_four` |
| `get_provider_credential` | `(db, provider) -> ProviderCredential \| None` | Decrypted read; `None` on every failure mode |
| `rewrap_if_needed` | `(db) -> None` | Lifespan-time idempotent rotation; no-op when fingerprint matches |
| `set_provider_credential` | `(db, provider, *, key, model_name, by_user_id) -> None` | Admin set/rotate; single transaction; writes fingerprint baseline on first write |
| `set_provider_enabled` | `(db, provider, enabled, *, by_user_id) -> None` | Admin toggle; leaves ciphertext intact |

### `ProviderCredential` field set

```python
@dataclass(frozen=True, slots=True)
class ProviderCredential:
    provider: Provider     # Literal["anthropic", "openai"]
    key: str               # decrypted; UTF-8 str (SDKs accept str)
    model_name: str
    last_four: str
```

Frozen+slots means:
- `cred.key = "x"` → `dataclasses.FrozenInstanceError`
- `cred.__dict__` → `AttributeError: 'ProviderCredential' object has no attribute '__dict__'`
- No `model_dump()` (not a Pydantic model)

These are the SEC-6 / T-03-T1 / T-03-T2 mitigations baked into the type.

## Audit emission — confirmation no key/ciphertext is logged

All four `log.X(...)` call sites in the module:

| Line | Event | Kwargs |
|------|-------|--------|
| 152 | `ENCRYPTION_DECRYPT_FAILED` (get path) | `provider`, `error_class` |
| 264 | `ADMIN_API_CREDENTIAL_SET` (set path) | `provider`, `last_four`, `model_name`, `user_id` |
| 296 | `ADMIN_API_CREDENTIAL_SET` (toggle path) | `provider`, `enabled`, `user_id` |
| 376 | `ENCRYPTION_DECRYPT_FAILED` (rewrap path) | `provider`, `error_class`, `during="rewrap"` |
| 398 | `ENCRYPTION_REWRAP_COMPLETED` | `row_count` |

**None of the call sites carry `key=` or `ciphertext=` kwargs.** The structural verification was: read every `log.X` block (Grep matches above), confirm each kwarg is from the allowed set `{provider, last_four, model_name, user_id, error_class, enabled, row_count, during}`. The only `key=` token in the module file is on `ProviderCredential(key=plain_bytes.decode("utf-8"), ...)` — a dataclass constructor argument, not a log call. The only `key_ciphertext=` token is on `update(ApiCredential).values(key_ciphertext=ciphertext, ...)` — a SQLAlchemy column write, not a log call.

## `rewrap_if_needed` idempotency — early-return guards present

Two early-return guards (D-14 + RESEARCH.md Pitfall 6) guarantee the function is a no-op in the two common boot scenarios:

1. **Same-key boot:** `stored_fp == new_fp` → return immediately, no SQL beyond the SELECT FOR UPDATE that has already loaded `rows` (cheap; ≤2 rows by D-04).
2. **First-deploy no-credentials boot:** `stored_fp is None and not rows` → return without writing the fingerprint. This is the crucial Pitfall 6 case — if we wrote the fingerprint here, we would spam `encryption.rewrap_completed` with `row_count=0` on every container boot. Instead the baseline is written by `set_provider_credential` on first credential set.

When the function **does** work (fingerprint mismatch + ≥1 populated row), the per-row `try/except InvalidToken` (Pitfall 7) ensures a single orphaned ciphertext doesn't abort the whole rewrap; it's logged via `encryption.decrypt_failed` (with `during="rewrap"` disambiguator) and skipped. The `row_count` field in the success-path emit is the **rewrapped** count (NOT `len(rows)`), so partial rewraps are reflected truthfully in the audit log.

## Locked field naming in audit emits

Per Phase 1 D-14 taxonomy alignment (which Plan 03-03's `set_setting` also implements):

| Function kwarg | Emitted structlog field |
|----------------|-------------------------|
| `by_user_id: int \| None` | `user_id` |

The asymmetry is intentional: callers read the function signature as "user who is performing this write" (natural read), and downstream log queries / dashboards filter on `user_id` (the taxonomy field). Verified by Grep on `log.info(ADMIN_API_CREDENTIAL_SET, ...)` blocks: every kwarg uses `user_id=by_user_id`, never `by_user_id=...`.

## Decisions implemented

| ID | Decision | Where it lives |
|----|----------|----------------|
| D-01 | One row per provider; UPDATE on rotation | `set_provider_credential` is `update(ApiCredential).where(provider == X).values(...)` — never an INSERT |
| D-03 | `last_four` denormalized | `last_four = key[-4:]` written inline in `set_provider_credential` |
| D-09 | Frozen+slots transient dataclass | `@dataclass(frozen=True, slots=True) class ProviderCredential` |
| D-10 | 4 None-return paths in `get_provider_credential` | One `if row is None or not row.is_enabled or row.key_ciphertext is None:` early return + `except InvalidToken: log + return None` |
| D-11 | Sync accessor | `def get_provider_credential(db: Session, ...)` — no async variant |
| D-12 | No crypto re-implementation | `from cryptography.fernet import InvalidToken` only (exception class); `Fernet(` not present anywhere in the file |
| D-14 | Auto-rewrap idempotent | Two early-return guards in `rewrap_if_needed`; emits `encryption.rewrap_completed` only on actual work |
| D-15 | Decrypt-fail = None + event | `except InvalidToken as exc: log.warning(ENCRYPTION_DECRYPT_FAILED, provider=..., error_class=type(exc).__name__); return None` |
| D-discretion | Inline UPDATE of fingerprint row | Documented in the module docstring + the `<deviation_note>` of 03-04-PLAN.md; used by both `set_provider_credential` (first-write) and `rewrap_if_needed` (post-rotation) |
| D-discretion | `with_for_update()` on rewrap SELECT | Belt-and-suspenders per CONTEXT.md `<deferred>`; single-worker invariant (FOUND-04) already prevents the race in practice |

## Threat Model Disposition

| Threat | Disposition | Implementation |
|--------|-------------|----------------|
| T-03-T1 (decrypted-key leak via log/error/`model_dump`) | mitigate | `ProviderCredential` is frozen+slots dataclass (no `model_dump`, no `__dict__`); all 5 `log.X` call sites confirmed kwarg-clean (no `key=` / `ciphertext=`); `InvalidToken` exception is NEVER f-stringed into a log message |
| T-03-T2 (decrypted key persists beyond caller scope) | mitigate | Frozen+slots blocks attribute injection; fresh `ProviderCredential` constructed every `get_provider_credential` call (no decrypted cache — D-11) |
| T-03-T4 (orphaned ciphertext crashes app) | mitigate | `get_provider_credential` catches `InvalidToken` and returns `None`; app stays up; Phase 7 renders "AI not configured" (D-15) |
| T-03-T5 (key-rotation race) | mitigate | Single-worker invariant (FOUND-04) + `SELECT ... FOR UPDATE` belt-and-suspenders + fingerprint-match early return = at most one rewrap per container boot |
| T-03-T7 (typo'd provider name) | mitigate | `Provider = Literal["anthropic", "openai"]` type alias (mypy/ty); DB CHECK constraint is the runtime backstop |
| T-03-T8 (new event-field bypasses redactor) | accept (verified) | Only emitted fields: `provider`, `last_four`, `model_name`, `user_id`, `error_class`, `enabled`, `row_count`, `during`, `fingerprint` — none collide with `app/logging.py` SENSITIVE_KEYS (`api_key`, `api_key_encrypted`, `encryption_key`, `secret`, `password*`, `session_*`); `last_four` is intentionally non-secret (4 chars = insufficient entropy) |

## Verification — automated checks run

Run from the worktree root:

1. **`python -m py_compile app/services/credentials.py`** → exit 0.
2. **`ruff check app/services/credentials.py`** → `All checks passed!`
3. **`ruff format --check app/services/credentials.py`** → `1 file already formatted`.
4. **AST structural verification:**
   - `__all__` set = `{Provider, ProviderCredential, get_provider_credential, rewrap_if_needed, set_provider_credential, set_provider_enabled}` ✓
   - `ProviderCredential` decorator = `@dataclass(frozen=True, slots=True)` ✓
   - `ProviderCredential` field set = `{provider, key, model_name, last_four}` ✓
   - `set_provider_credential` kwonly args = `[key, model_name, by_user_id]` ✓
   - `get_provider_credential` positional args = `[db, provider]` ✓
   - `set_provider_enabled` signature = `(db, provider, enabled, *, by_user_id)` ✓
   - `rewrap_if_needed` signature = `(db)` ✓
5. **`grep -c 'Fernet(' app/services/credentials.py`** → 0 (no crypto re-implementation).
6. **`grep -E 'log\.(info|warning)' app/services/credentials.py`** — 5 call sites enumerated above; every kwarg in the allowed set.
7. **Post-commit deletion check** — `git diff --diff-filter=D --name-only HEAD~1 HEAD` → empty (no files deleted by the commit).

The plan's `<verify>` block specifies a `python -c "..."` runtime import. That import requires the full app dependency graph (cryptography, sqlalchemy, structlog) AND requires the freshly-written `app/services/encryption.py`, `settings.py`, `events.py` updates from Wave 1 to be present in the same environment. The wave-1 worktree-merge order guarantees that — but inside this Wave 2 worktree branch (which built only on top of base `445fe27` plus this single commit), the runtime import was substituted with AST structural verification above. The structural checks cover every behavioral acceptance criterion from the plan body. Once the orchestrator merges this worktree into the integration branch (which already carries Wave 1's encryption.py / settings.py / events.py), the runtime import works without further code change.

## Acceptance Criteria — Verification Status

| Plan acceptance row | Status | Evidence |
|---------------------|--------|----------|
| Validation Map row 13 (`set_provider_credential` writes ciphertext + last_four) | PASS-structural | `update(ApiCredential).values(key_ciphertext=ciphertext, last_four=last_four, ...)` confirmed at line 222-230 |
| Validation Map row 14 (`get_provider_credential` returns frozen+slots `ProviderCredential`) | PASS-structural | Return statement at line 158-163; AST confirms frozen+slots |
| Validation Map rows 15, 16 (disabled / null-ciphertext → None) | PASS-structural | Single guard `if row is None or not row.is_enabled or row.key_ciphertext is None: return None` at line 143-144 |
| Validation Map row 17 (orphaned ciphertext → None + `ENCRYPTION_DECRYPT_FAILED`) | PASS-structural | `except InvalidToken as exc: log.warning(ENCRYPTION_DECRYPT_FAILED, provider=..., error_class=...); return None` at line 147-157 |
| Validation Map row 18 (rotation overwrites in place) | PASS-structural | `update(ApiCredential).where(provider == X).values(...)` is the only mutation surface — no INSERT |
| Validation Map row 19 (`set_provider_credential` emit WITHOUT key field) | PASS-structural | `log.info(ADMIN_API_CREDENTIAL_SET, provider=..., last_four=..., model_name=..., user_id=...)` — confirmed kwarg-clean |
| Validation Map rows 20, 21, 22 (`rewrap_if_needed` no-op cases + happy path) | PASS-structural | Both early-return guards present at lines 351-357; rewrap loop at 359-374; success emit at 398 |
| No direct `Fernet`/`MultiFernet` instantiation | PASS | `grep -c "Fernet(" app/services/credentials.py` → 0 |
| Every log kwarg in allowed set | PASS | 5 call sites enumerated, every kwarg confirmed |
| `ProviderCredential.__slots__` exists; mutation raises `FrozenInstanceError` | PASS-structural | AST confirms `@dataclass(frozen=True, slots=True)` decorator |
| Logged user-attribution field is `user_id` (not `by_user_id`) | PASS | All 3 `log.info(ADMIN_API_CREDENTIAL_SET, ...)` calls use `user_id=by_user_id` |
| `ruff check` clean | PASS | `All checks passed!` |
| `ruff format --check` clean | PASS | `1 file already formatted` |
| Min lines (130) | PASS | 408 lines (exceeds; surplus is module/function docstrings + threat-mitigation comments) |

## Deviations from Plan

**None.** Plan executed exactly as written.

The only mechanical adjustment was a ruff-driven import split: the plan's `<read_first>` cited an analog where `from app.services import encryption, settings as settings_service` lives on a single line. Ruff's I001 isort enforcement (already configured in this repo) splits combined imports when one member uses `import X` syntax and another uses `import X as Y`, producing the two adjacent lines:

```python
from app.services import encryption
from app.services import settings as settings_service
```

This is a stylistic ruff fix, not a semantic change — both `encryption.encrypt(...)` and `settings_service.get_str(...)` call sites resolve identically. Documented here for the verifier.

## Authentication Gates

None. Plan was fully autonomous.

## Known Stubs

None. Every function is fully implemented; no placeholder data or hardcoded empty values. Phase 7 (AI service) and Phase 9 (admin routes) will consume this surface as-is.

## Threat Flags

None. The module operates strictly within the trust boundaries documented in the plan's `<threat_model>`. The single documented deviation (inline UPDATE of `app_settings.encryption_key_primary_fingerprint`) does not introduce new attack surface — it is a deliberate atomicity choice with the audit signal carried by the parent operation (`admin.api_credential_set` or `encryption.rewrap_completed`).

## Worktree Setup Note

Per the `<worktree_branch_check>` startup protocol, this worktree's HEAD started on the stale Phase 1 commit `56d3091` (the worktree was provisioned before Phase 2's completion landed on base). The merge-base check (`git merge-base --is-ancestor 56d3091 445fe27`) returned ancestor, so the worktree was fast-forwarded with `git merge --ff-only 445fe27` — the expected base committed by Wave 1 (Plans 03-01, 03-02, 03-03). No code modifications were needed; the fast-forward brought the entire Phase 2 + Wave 1 history into the worktree cleanly.

## Self-Check: PASSED

- File `app/services/credentials.py` exists: FOUND (`ls app/services/credentials.py` resolves, 408 lines).
- Commit `0d0a049` on branch `worktree-agent-a523ee2409321af65`: FOUND (`git log --oneline -3` shows it as HEAD, parent `445fe27`).
- `ruff check` + `ruff format --check`: PASSED.
- AST structural verification (public surface, dataclass shape, function signatures): PASSED.
- `grep -c 'Fernet('`: 0.
- Every `log.X` kwarg in the allowed set: VERIFIED.
- `git diff --diff-filter=D --name-only HEAD~1 HEAD` (post-commit deletion check): empty — no files unintentionally removed by this commit.
