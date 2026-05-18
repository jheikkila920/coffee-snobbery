---
phase: 02-auth
plan: 02
subsystem: auth
tags:
  - argon2
  - argon2id
  - argon2-cffi
  - password-hashing
  - timing-defense
  - user-enumeration

# Dependency graph
requires:
  - phase: 00-foundation
    provides: argon2-cffi>=25.1,<26 pinned in requirements.txt (Plan 00-02)
  - phase: 01-middleware
    provides: structlog redactor (D-15) referenced by dummy_verify rationale
provides:
  - hash_password(plaintext) → argon2id-encoded hash (~97 chars MCF)
  - verify_password(stored_hash, candidate) → bool, no exceptions escape
  - dummy_verify(candidate) → None, constant-time user-not-found defense
  - Module-level _ph PasswordHasher singleton (m=65536, t=3, p=4, type=ID) — pinned via test_password_hasher_params
  - Module-level _DUMMY_HASH precomputed at import (RESEARCH Pitfall 2 defense)
affects:
  - 02-auth Plan 02-07 (login route) — calls dummy_verify on user-not-found branch
  - 02-auth Plan 02-04 (setup flow) — calls hash_password for first admin
  - 09-admin (user CRUD + rehash-on-login) — calls hash_password / verify_password / _ph.check_needs_rehash

# Tech tracking
tech-stack:
  added:
    - argon2-cffi 25.1 (already pinned in requirements.txt; first runtime consumer)
  patterns:
    - "Pure-function service module mirroring app/signing.py: from __future__ import annotations → imports → module-level singletons → pure functions with narrow try/except → __all__ block"
    - "Documentation-as-code parameter pinning: hyper-parameters passed as explicit kwargs even when library defaults match, with a regression test asserting each one"
    - "Module-level precomputed defense values (_DUMMY_HASH) so cost amortizes to once-per-process, not once-per-call (RESEARCH Pitfall 2)"

key-files:
  created:
    - app/services/auth.py (~110 LOC, three public helpers + two private singletons)
    - tests/services/test_auth.py (~130 LOC, 4 tests covering AUTH-04 + AUTH-03 + defensive)
  modified: []

key-decisions:
  - "Use public PasswordHasher attribute names (memory_cost, time_cost, parallelism, type) in test_password_hasher_params — argon2-cffi 25.1 does not expose leading-underscore aliases; plan <action> note explicitly authorized this fallback"
  - "Add a warm-up call before the timing measurement loop so first-call JIT / page-fault tax doesn't skew the ratio"
  - "List dummy_verify before hash_password in __all__ (ruff RUF022 sort order); existing app/signing.py uses the same sorted ordering"

patterns-established:
  - "Lazy-import + pytest.skip helper (_require_auth_service) — copy-paste analog of tests/services/test_sessions.py for tests that depend on a same-plan module"
  - "Wall-clock ratio gate as the regression test for timing-channel pitfalls (not absolute thresholds, which would be host-dependent)"

requirements-completed:
  - AUTH-04
  - AUTH-03

# Metrics
duration: 5min
completed: 2026-05-18
---

# Phase 02 Plan 02: argon2 password service Summary

**argon2-cffi wrapper with hash_password / verify_password / dummy_verify, parameter-pinned PasswordHasher singleton (m=65536, t=3, p=4, type=ID), and module-level precomputed dummy hash that closes the user-not-found timing channel.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-05-18T00:55:16Z
- **Completed:** 2026-05-18T01:00Z
- **Tasks:** 2 (TDD: RED + GREEN; no REFACTOR commit — code shipped clean first time)
- **Files modified:** 2 (both new)

## Accomplishments

- `hash_password` produces argon2id strings matching the exact AUTH-04 header `$argon2id$v=19$m=65536,t=3,p=4$` (verified in `test_argon2_roundtrip`).
- `verify_password` returns False (no exception) on both `VerifyMismatchError` (wrong password) and `InvalidHashError` (malformed column value); other exceptions propagate so genuine bugs surface.
- `dummy_verify` wall-clock matched a real failed `verify_password` within the (0.5x, 2.0x) gate — proof that `_DUMMY_HASH` is precomputed at import time and the user-enumeration timing channel (T-02-02-01, ASVS V2.2.5) is closed.
- PasswordHasher kwargs pinned by `test_password_hasher_params`, so the AUTH-04 floor cannot drift from library defaults without a code change visible in code review (T-02-02-02 mitigation).

## Task Commits

Each task was committed atomically; TDD gate sequence verified in git log:

1. **Task 1 (RED): tests/services/test_auth.py** — `a4e40d0` (test)
2. **Task 2 (GREEN): app/services/auth.py + format tests** — `3410708` (feat)

No REFACTOR commit needed — the GREEN code already matched the RESEARCH §argon2-cffi canonical body verbatim, ruff lint + format passed, and no clean-up changes surfaced.

**Plan metadata:** to be added by orchestrator post-merge (worktree mode).

## Files Created/Modified

- `app/services/auth.py` — three public helpers (`hash_password`, `verify_password`, `dummy_verify`) wrapping `argon2.PasswordHasher` 25.1; module-level `_ph` singleton + `_DUMMY_HASH` precomputed string. Mirrors `app/signing.py` skeleton (from-future-imports → imports → singletons → functions → `__all__`).
- `tests/services/test_auth.py` — 4 tests: roundtrip + format, parameter pins, dummy_verify timing ratio gate, invalid-hash defensive case.

## Decisions Made

- **Public attribute names in test introspection.** argon2-cffi 25.1's `PasswordHasher` exposes `memory_cost` / `time_cost` / `parallelism` / `type` as public properties; the plan body's `_memory_cost` (leading-underscore) form raised `AttributeError: 'PasswordHasher' object has no attribute '_memory_cost'`. The plan's `<action>` note explicitly authorized falling back to the hash-string assertion, but the public-attribute form is cleaner and tests the actual instance state.
- **Warm-up call before the timing-test loop.** First call sometimes pays an extra JIT / page-fault / argon2-thread-spinup cost. The plan body's 5-sample median dampens this, but adding a single discarded warm-up call before the measurement loop makes the ratio significantly more stable.
- **`__all__` ordering: `dummy_verify` before `hash_password`.** Ruff RUF022 alphabetises `__all__`; `app/signing.py` follows the same convention (`["load_session_id", "session_signer", "sign_session_id"]`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug in plan body] PasswordHasher private attributes do not exist on argon2-cffi 25.1**
- **Found during:** Task 1 (writing the parameter introspection test).
- **Issue:** The plan's `test_password_hasher_params` scaffold reaches into `_ph._memory_cost`, `_ph._time_cost`, `_ph._parallelism`, `_ph._type` — none of which exist on argon2-cffi 25.1.0. A quick probe (`docker compose exec coffee-snobbery python -c "..."`) confirmed: `AttributeError: 'PasswordHasher' object has no attribute '_memory_cost'. Did you mean: 'memory_cost'?`
- **Fix:** Used the public attribute names (`memory_cost`, `time_cost`, `parallelism`, `type`). The plan body anticipated this exact case in its closing note: *"If the executor finds the attribute names have changed in the installed version, fall back to asserting the hash string format itself..."*. Public attributes are a stronger gate than the hash-string fallback because they test the live instance state, not a derived encoding.
- **Files modified:** `tests/services/test_auth.py`
- **Verification:** `test_password_hasher_params` passes; ruff lint clean; the `noqa: PLC2701` comment retained to document sanctioned test-side reach into the private module.
- **Committed in:** `a4e40d0` (Task 1).

---

**Total deviations:** 1 auto-fixed (1 plan-body bug, anticipated by the plan's own fallback note).
**Impact on plan:** Zero scope creep — fix was within the bounds the plan explicitly authorised. Strengthened the test (live attribute introspection beats string-encoding check).

## Issues Encountered

- **Worktree path not mounted into container.** `docker compose exec -w /app/.claude/worktrees/...` failed with `Cwd must be an absolute path` because the container's `/app` is **baked into the image** (no source bind mount per `docker-compose.yml`). Worked around by `docker cp tests/services/test_auth.py coffee-snobbery:/app/tests/services/test_auth.py` (and likewise for `app/services/auth.py`) before each pytest invocation. This is purely a test-iteration mechanic; the merge into main + a `docker compose build coffee-snobbery && docker compose up -d coffee-snobbery` on the VPS bakes the new code in normally.
- **`.env` missing from the worktree.** Git Bash + Compose v2 surfaced this as a noisy "POSTGRES_USER variable is not set" warning. Copied `.env` from the main repo root into the worktree (gitignored, so not staged). Future worktree-mode plans hitting Docker should pre-stage `.env` the same way.
- **Git Bash path translation.** `docker compose exec coffee-snobbery ls /app/...` was mangled to `C:/Program Files/Git/app/...`. Prefixed every container-side command with `MSYS_NO_PATHCONV=1` to disable the translation.
- **`pytest` not on container PATH.** It's installed as a Python module, not a console script. Used `python -m pytest` instead of bare `pytest`.

None of the above are blockers for downstream plans — the worktree-vs-container mechanic is a parallel-execution overhead, and the source-of-truth file (in the worktree, committed) is correctly shaped.

## User Setup Required

None — no external service configuration. The argon2-cffi runtime dependency was already pinned in `requirements.txt` from Phase 0, so no Dockerfile or environment changes are needed for `coffee-snobbery` to import this module after merge.

## Next Phase Readiness

- **Ready for Plan 02-04 (setup flow)** — `hash_password` is the call it needs to mint the first admin's hash.
- **Ready for Plan 02-07 (login route)** — `verify_password` is the match check; `dummy_verify` is the user-not-found defense. The Plan 02-07 router MUST call `dummy_verify(form_password)` on every code path where the username lookup returns `None`; skipping it reopens T-02-02-01.
- **Ready for Phase 09 (admin)** — `hash_password` is the rehash side, and `_ph.check_needs_rehash(stored_hash)` is the migration trigger when the AUTH-04 parameters change in the future. Phase 9 implements the rehash-on-login policy by importing `_ph` via sanctioned test-style access; if a public helper is preferred, add `needs_rehash(stored_hash) -> bool` to `__all__` at that time.

**Threat-model carry-forward:**
- T-02-02-01 (user-enumeration timing leak) mitigation is *available* in this module but only *active* once Plan 02-07's `/login` handler invokes `dummy_verify` on the user-not-found branch. The timing test gate proves the helper itself is correct; the route-level wiring is the next mitigation step.
- T-02-02-04 (concurrent login storms saturate event loop) was accepted at the household scale — slowapi's `LOGIN_LIMIT=5/15min` (Plan 02-08) is the cap. If usage ever grows, wrap `verify_password` in `asyncio.to_thread()` at the call site.

## Self-Check: PASSED

- `app/services/auth.py` present in worktree HEAD: YES (commit `3410708`, ~110 LOC, three public helpers + two private singletons).
- `tests/services/test_auth.py` present in worktree HEAD: YES (commit `a4e40d0`, formatted by `ruff format`, 4 tests).
- All 4 tests pass in the running container: YES (`4 passed, 1 warning in 3.26s`).
- `ruff check app/services/auth.py tests/services/test_auth.py`: All checks passed.
- `ruff format --check app/services/auth.py tests/services/test_auth.py`: 2 files already formatted.
- `hash_password("password")` output starts with `$argon2id$v=19$m=65536,t=3,p=4$`: VERIFIED in container.
- No `_ph` or `_DUMMY_HASH` exported from `__all__`: VERIFIED (file inspection).
- Commits found in worktree `git log`: `a4e40d0`, `3410708` — both present.
- TDD gate sequence: `test(02-02): ...` (a4e40d0) → `feat(02-02): ...` (3410708) — RED then GREEN, in that order, both committed.

---
*Phase: 02-auth*
*Plan: 02*
*Completed: 2026-05-18*
