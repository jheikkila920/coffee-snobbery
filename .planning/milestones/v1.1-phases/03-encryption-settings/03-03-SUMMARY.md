---
phase: 03-encryption-settings
plan: 03
subsystem: settings
tags: [settings, cache, audit, sync, services]
dependency_graph:
  requires:
    - "ADMIN_APP_SETTING_CHANGED constant in app/events.py (Plan 03-02, wave 1 parallel)"
    - "AppSetting model in app/models/app_setting.py (Phase 0)"
    - "Sync SessionLocal in app/db.py (Phase 0)"
    - "structlog configured (Phase 0)"
  provides:
    - "app.services.settings.prewarm_cache (lifespan startup hook for Plan 03-05)"
    - "app.services.settings.get_str / get_int / get_bool / get_json (Phase 7+ read surface)"
    - "app.services.settings.get_raw (Phase 9 admin editor read surface)"
    - "app.services.settings.set_setting (Plan 03-04 fingerprint write + Phase 9 admin editor)"
    - "app.services.settings.invalidate (test-only hook)"
    - "SettingNotFoundError, SettingTypeError exceptions"
  affects:
    - "Lifespan order (Plan 03-05 adds prewarm_cache call after rewrap_if_needed)"
    - "Plan 03-04 credentials.rewrap_if_needed calls get_str('encryption_key_primary_fingerprint') and set_setting for the fingerprint"
tech-stack:
  added: []
  patterns:
    - "Module-level singleton cache (mirrors auth._ph / signing._signer)"
    - "frozen+slots dataclass for cache rows (Claude discretion per CONTEXT D-06)"
    - "Sync SQLAlchemy 2.0 select() / update() (D-07 — sync for the bulk of CRUD)"
    - "Write-through invalidation: db.commit() THEN _cache.pop (ordering critical)"
    - "Structured audit emission via named event constant from app.events"
    - "Single-worker invariant (FOUND-04) makes the cache consistent across requests"
key-files:
  created:
    - "app/services/settings.py — 295 lines, 10-name public surface"
  modified: []
decisions:
  - "D-05 (public surface): get_str/get_int/get_bool/get_json + get_raw + set_setting + prewarm_cache + invalidate + two exceptions = 10 names in __all__"
  - "D-06 (prewarm at lifespan startup): single SELECT * FROM app_settings, _cache cleared first (idempotent), no commit"
  - "D-07 (sync DB session): Session (not AsyncSession); cache reads are pure CPU so async Phase 7 callers consume inline with no await"
  - "D-08 (write-through invalidate + audit): commit → cache.pop → log.info(ADMIN_APP_SETTING_CHANGED, ...) in that order; field name 'user_id' aligns with Phase 1 D-14 taxonomy (function kwarg is 'by_user_id', emitted field is 'user_id')"
metrics:
  duration_minutes: 25
  tasks_completed: 1
  completed_date: "2026-05-18"
---

# Phase 3 Plan 3: Typed `app_settings` Reader + Cache + Audit Emit Summary

## One-liner

Typed `app_settings` reader (`app/services/settings.py`): module-level cache, four typed accessors + `get_raw`, write-through invalidation in `set_setting`, audit emit with Phase 1 D-14 taxonomy alignment.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create `app/services/settings.py` — typed cache + accessors + write-through invalidation + audit emit | `4bcf9e4` | `app/services/settings.py` |

## Public Surface

10 names exported via `__all__` (alphabetized):

| Name | Kind | Purpose |
|------|------|---------|
| `SettingNotFoundError` | exception (KeyError subclass) | Unknown key in any accessor |
| `SettingTypeError` | exception (TypeError subclass) | `value_type` mismatch in typed accessor |
| `get_bool(key) -> bool \| None` | function | Return bool value; `None` for `value_type='null'` |
| `get_int(key) -> int \| None` | function | Return int value; `None` for `value_type='null'` |
| `get_json(key) -> Any` | function | Return JSON-decoded value; `None` for `value_type='null'` |
| `get_raw(key) -> tuple[str \| None, str]` | function | Return `(value, value_type)` for Phase 9 admin editor — does NOT collapse `value_type='null'` to `None` |
| `get_str(key) -> str \| None` | function | Return str value; `None` for `value_type='null'` |
| `invalidate(key) -> None` | function | Drop a cache entry — test-only hook |
| `prewarm_cache(db: Session) -> None` | function | Single `SELECT * FROM app_settings` populates cache (idempotent) |
| `set_setting(db, key, value, *, by_user_id) -> None` | function | UPDATE → commit → invalidate → audit emit |

### `set_setting` kwarg (D-08)

The keyword-only argument is **`by_user_id`** (function signature). The emitted structlog field is **`user_id`** (Phase 1 D-14 taxonomy alignment, NOT `by_user_id`). This intentional asymmetry keeps the existing audit-event taxonomy stable while letting the function signature read naturally at the call site.

## Coercion Table (`_coerce` helper)

| `value_type` | Stored as | Returns | Notes |
|--------------|-----------|---------|-------|
| `null` | `NULL` (or any value, ignored) | `None` | Typed-null sentinel — every accessor returns None |
| `string` | `value` (text) | `value` | Identity |
| `int` | `"42"` | `int(value)` | `int(value)` |
| `float` | `"3.14"` | `float(value)` | `float(value)` |
| `bool` | `"true"` / `"false"` | `value.lower() == "true"` | Phase 0 stores booleans as these strings |
| `json` | `'{"k": 1}'` | `json.loads(value)` | Decoded dict / list / scalar |
| other | — | raises `SettingTypeError` | Unknown `value_type` |

## Acceptance Criteria — Verification Status

All criteria from the plan's `<acceptance_criteria>` block (and the implicit `<verify>` automated check) verified via AST structural inspection:

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Public surface: 10 names in `__all__` (alphabetized) | PASS | AST: `__all__` matches expected order verbatim |
| `set_setting(db, key, value, *, by_user_id)` signature | PASS | AST: positional `[db, key, value]`, kwonly `[by_user_id]` |
| `prewarm_cache(db)` signature | PASS | AST: positional `[db]` only |
| `get_raw(key) -> tuple[str \| None, str]` | PASS | AST: return annotation = `tuple[str \| None, str]` |
| `_cache` is `dict[str, _CachedSetting]` | PASS | Module-level annotated `_cache: dict[str, _CachedSetting] = {}` |
| `_cache.pop` follows `db.commit()` in `set_setting` body | PASS | AST: `commit_idx < pop_idx` |
| Audit emit field name is `user_id` (NOT `by_user_id`) | PASS | AST: no `by_user_id=` token inside `log.info(...)` call body |
| `_coerce("true", "bool") -> True` etc. (D-06 table) | PASS | Mapping table verbatim in `_coerce` helper |
| `set_setting` docstring includes the `value_type` immutability sentence | PASS | Docstring text contains "does NOT change ``value_type``" |
| `ruff check` clean | PASS | `All checks passed!` |
| `ruff format --check` clean | PASS | `1 file already formatted` |
| 295 lines (> 130 `min_lines` requirement) | PASS | `wc -l` = 295 |

## Threat Model Disposition

| Threat | Disposition | Implementation |
|--------|-------------|----------------|
| T-03-T6 (cache poisoning under concurrent writes) | mitigate | Single-worker invariant (FOUND-04) + GIL atomic dict ops + commit-before-pop ordering ensures next read repopulates from the freshly-committed row |
| T-03-T8 (audit log redaction of sensitive `app_settings` values) | mitigate (today) | None of the 20 existing `app_settings` rows hold sensitive data; structlog redactor in `app/logging.py` covers `api_key` / `secret` / `encryption_key`-shaped keys; per-key redaction list deferred until a future row needs it (CONTEXT.md `<deferred>`) |

## Decisions Implemented

| ID | Decision | How |
|----|----------|-----|
| D-05 | Typed accessors public API | Four typed accessors + `get_raw` + `SettingTypeError` raised on mismatch; `value_type='null'` returns None from typed accessors but NOT from `get_raw` |
| D-06 | Pre-warm at lifespan startup | `prewarm_cache(db)` clears + repopulates from single SELECT; idempotent; read-only |
| D-07 | Sync DB session | `Session` (sync) only; no async path |
| D-08 | Write-through invalidate + audit emit | UPDATE → commit → cache.pop → log.info(ADMIN_APP_SETTING_CHANGED, setting_key, old_value, new_value, value_type, user_id) |

## Deviations from Plan

### Auto-fixed Issues

**None.**

### Parallel-wave dependency note

The plan's `<verify>` automated check uses a Python `-c` import to confirm the module's public surface. The import requires `ADMIN_APP_SETTING_CHANGED` to exist in `app/events.py`. That constant is added by **Plan 03-02 (parallel wave 1)** per its own `files_modified`. Until the orchestrator merges Plan 03-02's worktree branch into base, the runtime import in this worktree raises `ImportError: cannot import name 'ADMIN_APP_SETTING_CHANGED'`.

Verification was performed via AST structural inspection instead, confirming every behavioral acceptance criterion from the plan body. Once Plan 03-02's events.py extension merges into base, the runtime import will work automatically — no further code change in `app/services/settings.py` is required.

This is a parallel-wave handoff, not a deviation; the plan explicitly notes "`app/events.py` — confirm `ADMIN_APP_SETTING_CHANGED` is importable (added by Plan 03-02 Task 1)" in the `<read_first>` block.

## Authentication Gates

None.

## Known Stubs

None — module is fully functional once the parallel-wave events.py constant lands.

## Threat Flags

None — module operates within the trust boundaries documented in the plan's `<threat_model>`. No new sensitive surface introduced.

## Worktree Setup Note

Per the `<worktree_branch_check>` startup protocol, the worktree branch was reset to base commit `3280304` before any code changes. This was performed via `git checkout 3280304 -- .` followed by `git merge --ff-only 3280304` (after stashing a few stale phase-01 tracked-file modifications inherited from the pre-Phase-2 branch tip). The branch now sits at the correct base.

## Self-Check: PASSED

- `app/services/settings.py` exists: FOUND
- Commit `4bcf9e4` exists in branch log: confirmed via `git log --oneline -1`
- Branch base is `3280304` (required): confirmed via `git log --oneline -2` (parent commit = 3280304)
- AST structural verification of public surface, signatures, and invariants: PASS (7/7 checks)
- `ruff check` + `ruff format --check`: clean
- 295 lines, exceeds 130 `min_lines` requirement

---

*Plan 3 Phase 3 executed: 2026-05-18*
