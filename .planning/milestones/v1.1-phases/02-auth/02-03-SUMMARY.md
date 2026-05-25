---
phase: 02-auth
plan: 03
subsystem: auth
tags: [fastapi, depends, dependency-injection, async-session, sqlalchemy, admin-gate]

# Dependency graph
requires:
  - phase: 01-middleware
    provides: SessionMiddleware populates request.state.user (stub dict today; Plan 02-06 upgrades to real User row per D-09)
  - phase: 00-foundation
    provides: User SQLAlchemy model with is_admin / is_active flags
provides:
  - app.dependencies package — canonical home for FastAPI Depends callables
  - require_user FastAPI dependency (401 if request.state.user is None)
  - require_admin FastAPI dependency (403 for both anon and non-admin per D-13)
  - get_async_session async-generator dependency yielding a fresh AsyncSession per request
affects: [02-07-login, 02-08-admin, 02-08-debug-proxy, phase-04-catalog-routes, phase-05-brew-sessions]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Lazy import inside async-generator body to break app.main → routers → app.dependencies.db → app.main cycle"
    - "Synthetic-Request unit testing (build Request from minimal ASGI scope, no TestClient round-trip)"
    - "Fold 401 into 403 on admin-gated routes to avoid 'logged-in-but-not-admin' info disclosure (ASVS V7.4.3)"

key-files:
  created:
    - app/dependencies/__init__.py
    - app/dependencies/db.py
    - app/dependencies/auth.py
    - tests/dependencies/test_auth.py
  modified: []

key-decisions:
  - "async_session_factory stays at app/main.py for Phase 2; get_async_session imports it lazily inside the generator body (resolves RESEARCH Open Q3; defers the relocation to a future Phase 0 follow-up)"
  - "require_admin folds anon-vs-non-admin into a single 403 per CONTEXT D-13 wording (ASVS V7.4.3 — no information leak); require_user keeps 401 for routes that only need 'is a user logged in'"
  - "FakeAdmin / FakeRegular dataclasses (not real User SQLAlchemy rows) drive the unit tests — DB-free; the real-row integration test lives in Plan 02-08 test_admin_gate_three_states"

patterns-established:
  - "FastAPI Depends callables live under app/dependencies/ — services live under app/services/ (convention recorded in app/dependencies/__init__.py docstring)"
  - "Async-generator dependencies (yield, not return; AsyncIterator return type) for resources that need lifecycle cleanup (DB sessions, file handles, etc.)"
  - "Synthetic Request(scope={'type': 'http', 'state': {...}}) is the canonical shape for unit-testing Depends callables without an HTTP round-trip"

requirements-completed: [AUTH-09]

# Metrics
duration: 3min
completed: 2026-05-18
---

# Phase 02 Plan 03: app.dependencies Package — require_user, require_admin, get_async_session Summary

**FastAPI Depends callables for the AUTH-09 admin gate (require_admin / require_user) plus the async-session injector (get_async_session) that every Phase-2+ route handler will use to acquire its DB session.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-05-18T00:56:54Z
- **Completed:** 2026-05-18T00:58:47Z
- **Tasks:** 3
- **Files modified:** 4 (all created)

## Accomplishments

- AUTH-09 closed at the unit level: `require_admin` raises 403 for both anonymous and non-admin (folded per D-13), returns the User row for an admin. The 3-state integration test (real User + Depends through TestClient) is queued for Plan 02-08.
- `require_user` available as a free side-effect of the same module — Phase 4+ catalog routes get an authenticated-user gate without any new code.
- `get_async_session` lands as the canonical FastAPI dependency for DB access in routes: each request gets its own `AsyncSession` with its own transaction scope, independent of `SessionMiddleware`'s already-committed session.
- The lazy-import workaround for the `app.main → routers → app.dependencies.db → app.main` cycle is in place and verified — module-level `from app.dependencies.db import get_async_session` and `from app.dependencies.auth import require_admin` both succeed without ImportError.

## Task Commits

Each task was committed atomically:

1. **Task 1: failing unit tests for require_user / require_admin (TDD RED)** — `635a84b` (test)
2. **Task 2: app.dependencies package + get_async_session** — `c674aa7` (feat)
3. **Task 3: require_user + require_admin (TDD GREEN)** — `e69b438` (feat)

TDD gate sequence (per `references/tdd.md`): `test(02-03)` → `feat(02-03)` for the implementation that turns the 5 skipped tests into 5 passes. No refactor commit — the implementation matches the canonical pattern from 02-PATTERNS.md verbatim, with nothing to clean up.

## Files Created/Modified

- `app/dependencies/__init__.py` — single-line docstring marking the package as the home of FastAPI Depends callables (1 line).
- `app/dependencies/db.py` — `get_async_session` async-generator dependency. Module docstring records the lazy-import rationale and the per-request transaction-scope rationale. (~50 lines incl. doc.)
- `app/dependencies/auth.py` — `require_user` (401) + `require_admin` (403). Module docstring records the D-13 fold + ASVS V7.4.3 rationale. `__all__` exports both. (~65 lines incl. doc.)
- `tests/dependencies/test_auth.py` — 5 synthetic-Request unit tests covering the AUTH-09 three-state matrix plus the `require_user` 401 contract. Lazy imports + `_require_dep` skip helper keep the file collectable before Task 3 lands. (~135 lines incl. doc.)

## Decisions Made

- **`async_session_factory` location:** Kept at `app/main.py:95-96` for Phase 2 per 02-PATTERNS.md §`app/dependencies/db.py` recommendation; resolves RESEARCH Open Q3 with the minimum-diff path. The `app/main.py:88-95` SUMMARY note already flags this as a future Phase 0 follow-up — when that relocation happens, only `app/dependencies/db.py`'s lazy import line changes (`from app.main` → `from app.db`).
- **401-into-403 fold for `require_admin`:** Per CONTEXT D-13 ("returns 403 otherwise") and ASVS V7.4.3 (no info leak on admin gates). The AUTH-09 VALIDATION row "anon → 401 OR 403" permitted either branch; the planner's choice was 403 to keep `/admin` opaque. `require_user` keeps the 401 distinction because a route that only needs "is a user logged in" benefits from differentiating the cases.
- **No real `User` SQLAlchemy row in unit tests.** `_FakeAdmin` / `_FakeRegular` dataclasses with `is_admin` only — the dependencies read `is_admin` and identity, nothing else. Keeps the unit tests DB-free; the integration assertion (real row through `Depends` via `TestClient`) lives in Plan 02-08 `test_admin_gate_three_states` per 02-VALIDATION.md.

## Deviations from Plan

None — plan executed exactly as written. All three tasks followed the exact action blocks from the PLAN. The verification step swapped `docker compose exec coffee-snobbery pytest` for host-side `python -m pytest` because the parallel-executor worktree is at a different filesystem path than the running container (the container's bind-mount points at the main repo root, not the worktree). All five tests pass identically on the host with Python 3.14 + the project's pinned `pytest 9.0.3` / `fastapi` / `starlette` / `sqlalchemy 2.0`. The sanity-check import line from the plan's `<verification>` block (`python -c "from app.dependencies.db import get_async_session; from app.dependencies.auth import require_admin; print('ok')"`) was run on the host and printed `ok` as required.

## Issues Encountered

None.

## Known Stubs

None. The dependencies return live data (the `User` row from `request.state.user`) or raise. There are no placeholder values flowing to UI rendering and no commented-out TODOs.

## Threat Flags

None. The module's surface matches the `<threat_model>` block in 02-03-PLAN.md exactly:
- T-02-03-01 (EoP via dependency bypass) — mitigated by reading `request.state.user.is_admin` boolean populated by SessionMiddleware from a fresh DB row (D-09); covered by `test_require_admin_unit_non_admin_raises`.
- T-02-03-02 (1D via 401/403 distinction) — mitigated by the unified 403 in `require_admin`; covered by `test_require_admin_unit_anon_raises` (asserts 401 OR 403).
- T-02-03-03 / T-02-03-04 — accept dispositions, no implementation surface to add.

No new endpoints, no new auth paths beyond the plan, no schema or trust-boundary changes.

## TDD Gate Compliance

- **RED gate:** `635a84b` — `test(02-03): add unit tests for require_user / require_admin`. All 5 tests skip cleanly while `app.dependencies.auth` is absent (the Wave-0 contract — collectable, skipped, not erroring).
- **GREEN gate:** `c674aa7` (`feat(02-03): add app.dependencies package + get_async_session`) followed by `e69b438` (`feat(02-03): add require_user / require_admin FastAPI dependencies`). After `e69b438`, all 5 tests pass.
- **REFACTOR gate:** Not invoked — the pattern was copied verbatim from 02-PATTERNS.md lines 207-247, no cleanup applies.

Sequence: test → feat → feat. No `test` commit lands without a `feat` follow-up; no `feat` lands without the preceding `test` having been merged.

## User Setup Required

None — no external service configuration, no env vars, no dashboard steps.

## Next Phase Readiness

- **Plan 02-07 (login route):** Ready. `db: AsyncSession = Depends(get_async_session)` is the line every state-changing handler will write.
- **Plan 02-08 (admin route + debug/proxy hardening):** Ready. The 3-state integration test (`tests/routers/test_admin.py::test_admin_gate_three_states`) can now run real `Depends(require_admin)` through `TestClient`. `/debug/proxy` uses Form 2 (`dependencies=[Depends(require_admin)]` on the route decorator); `/admin` uses Form 1 (`user: User = Depends(require_admin)` in the signature). Both forms are documented in 02-PATTERNS.md.
- **Phase 4+ catalog routes:** Inherit `require_user` for free — no further work required in this phase.

No blockers.

## Self-Check: PASSED

Verification claims confirmed:

- `app/dependencies/__init__.py` — FOUND (1 line, docstring).
- `app/dependencies/db.py` — FOUND (`get_async_session` is an async-generator function per `inspect.isasyncgenfunction`).
- `app/dependencies/auth.py` — FOUND (`require_user`, `require_admin` exported via `__all__`).
- `tests/dependencies/test_auth.py` — FOUND, 5 tests, all PASS after Task 3.
- Commit `635a84b` (test) — FOUND in `git log`.
- Commit `c674aa7` (feat: package + db) — FOUND in `git log`.
- Commit `e69b438` (feat: auth) — FOUND in `git log`.
- Sanity import (`from app.dependencies.db import get_async_session; from app.dependencies.auth import require_admin`) prints `ok` — confirmed.

---
*Phase: 02-auth*
*Plan: 03*
*Completed: 2026-05-18*
