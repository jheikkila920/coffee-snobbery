---
phase: 02-auth
plan: 08
subsystem: auth
tags: [admin, fastapi, depends, require_admin, jinja2, htmx-base, csp]

# Dependency graph
requires:
  - phase: 02-auth (Plan 02-01)
    provides: "tests/conftest.py fixtures: seeded_admin_user, seeded_regular_user, fresh_db, async_client"
  - phase: 02-auth (Plan 02-02)
    provides: "app.services.auth.hash_password — argon2id password hasher used by seed fixtures"
  - phase: 02-auth (Plan 02-03)
    provides: "app.dependencies.auth.require_admin — Form 1 dependency the /admin handler accepts"
  - phase: 02-auth (Plan 02-06)
    provides: "SessionMiddleware D-09 — request.state.user is a fresh User row, not the {'user_id': int} dict"
  - phase: 01-middleware (Plan 01-06)
    provides: "base.html — CSP-nonce + Tailwind + HTMX + Alpine scaffolding inherited by pages/admin.html"
provides:
  - "GET /admin route handler (app/routers/admin.py) using Depends(require_admin) Form 1"
  - "pages/admin.html 5-line stub template extending base.html with the D-13 literal body"
  - "tests/routers/test_admin.py — three-state gate + isolated D-13 body assertion (4 tests)"
affects: [02-09, 02-10, 09-admin]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "FastAPI Depends Form 1: ``user: User = Depends(require_admin)`` in handler signature (parameter, not decorator)"
    - "Runtime-xfail for cross-wave timing: ``if r.status_code == 404: pytest.xfail(...)`` keeps the suite green between Wave 4 (router file lands) and Wave 5 (Plan 02-10 wires include_router into app.main)"
    - "Per-line ``# noqa: B008`` on FastAPI Depends-default — surgical exemption preferred over a per-file pyproject ignore until the pattern repeats"

key-files:
  created:
    - "app/routers/admin.py — single GET /admin route, Depends(require_admin) Form 1, renders pages/admin.html"
    - "app/templates/pages/admin.html — 5-line stub extending base.html, D-13 literal body"
    - "tests/routers/test_admin.py — three-state gate (anon/non-admin/admin) + isolated D-13 body assertion (4 tests, all xfail until Plan 02-10 wires the router)"
  modified: []

key-decisions:
  - "Form 1 (parameter) chosen over Form 2 (decorator dependencies kwarg) per plan + 02-RESEARCH §407-459: Phase 9's admin expansion will read user.username/user.is_admin/user.email directly in the same handler shape, so receiving the User object today buys zero-friction forward compatibility"
  - "B008 silenced via per-line noqa rather than per-file pyproject entry — the canonical FastAPI Depends-default idiom will repeat across every Phase 4+ router; the right time to fold into [tool.ruff.lint.per-file-ignores] is when the second router needs it, not now (YAGNI)"

patterns-established:
  - "Admin stub shape: one route, one literal body line, no logic — Phase 9 expands the surface; v1 just proves the gate works"
  - "Runtime-xfail across wave boundaries: when Plan A lands a router and Plan B wires it into app.main, tests use ``if r.status_code == 404: pytest.xfail(...)`` so the suite stays green during the Plan-A-to-Plan-B window"

requirements-completed: [AUTH-09]

# Metrics
duration: ~4min
completed: 2026-05-17
---

# Phase 02 Plan 08: /admin route stub Summary

**Single ``GET /admin`` handler gated by ``Depends(require_admin)`` Form 1 + 5-line Jinja stub template + four-test three-state gate coverage; router not yet wired into app.main (Plan 02-10 owns that line).**

## Performance

- **Duration:** ~4 minutes
- **Started:** 2026-05-17T20:31:40Z (Task 1 RED commit timestamp)
- **Completed:** 2026-05-17T20:35:11Z (B008 fix commit timestamp)
- **Tasks:** 3 (Task 1 RED tests + Task 2 router + Task 3 template; one auto-fix appended)
- **Files created:** 3
- **Files modified:** 0

## Accomplishments

- Three-state admin gate test scaffold landed in ``tests/routers/test_admin.py`` (4 tests: anon→403/401, non-admin→403, admin→200+body, isolated D-13 body)
- ``app/routers/admin.py`` ships a single ``GET /admin`` route using ``Depends(require_admin)`` Form 1 — the User row flows through so Phase 9's expansion is a body-only edit
- ``app/templates/pages/admin.html`` ships the exact D-13 literal "Admin (stub) — wiring lands in Phase 9." with the Unicode em-dash (U+2014)
- AUTH-09 requirement complete (deny-by-default ASVS V4.1.2; ``require_admin`` folds anon + non-admin into the same 403 per D-13)

## Task Commits

Each task committed atomically on branch ``worktree-agent-ad16959bfe1c2a163``:

1. **Task 1: RED tests** — ``43774d0`` (``test(02-08): RED — /admin three-state gate + stub-body tests``)
2. **Task 2: /admin router** — ``7a6ef6f`` (``feat(02-08): /admin stub route — Depends(require_admin) Form 1 (AUTH-09)``)
3. **Task 3: stub template** — ``5ed5605`` (``feat(02-08): admin.html stub template — exact D-13 literal body``)
4. **Auto-fix: ruff B008** — ``ac71543`` (``fix(02-08): silence B008 on Depends() default — FastAPI Form 1 idiom``)

## Files Created/Modified

- ``app/routers/admin.py`` — single GET /admin route + Depends(require_admin) Form 1; renders pages/admin.html; the User parameter is unused in Phase 2 but pre-wired for Phase 9's expansion
- ``app/templates/pages/admin.html`` — 5-line page template extending base.html; D-13 literal body "Admin (stub) — wiring lands in Phase 9." (Unicode em-dash)
- ``tests/routers/test_admin.py`` — 4 tests covering the AUTH-09 three-state gate + the D-13 isolated body assertion; uses runtime-xfail (``if r.status_code == 404: pytest.xfail(...)``) so the suite stays green until Plan 02-10 wires the router into app.main

## Decisions Made

- **Form 1 over Form 2:** plan-mandated, but worth restating — Form 1's ``user: User = Depends(require_admin)`` parameter shape means Phase 9's expansion edits only the handler body; the dependency-injection surface is already in the right shape. Form 2 (``dependencies=[Depends(require_admin)]`` decorator kwarg) is reserved for Plan 02-09's ``/debug/proxy`` admin-gate where the User row is unused.
- **Per-line ``# noqa: B008`` over per-file pyproject ignore:** the FastAPI Depends-default-arg idiom will eventually appear in every Phase 4+ router. Folding it into ``[tool.ruff.lint.per-file-ignores]`` for ``app/routers/*`` is the correct long-term home — but doing it on the first usage is premature. When the second router needs the same exemption, that's the natural seat for the pyproject change. Until then, a per-line noqa with a comment pointing at 02-RESEARCH is the surgical fix.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] ruff B008 on ``user: User = Depends(require_admin)``**

- **Found during:** Task 2 verification (final ``ruff check app/routers/`` per ``<success_criteria>``)
- **Issue:** Ruff's ``B008`` ("Do not perform function call ``Depends`` in argument defaults") fires on the FastAPI Form 1 idiom. The plan's ``<success_criteria>`` requires ``ruff check app/routers/`` clean.
- **Fix:** Per-line ``# noqa: B008`` with an inline comment pointing at 02-RESEARCH §"FastAPI — Depends(require_admin) pattern" (Form 1 — RESEARCH lines 407-459) so the next reader sees why the rule is silenced.
- **Files modified:** ``app/routers/admin.py``
- **Verification:** ``python -m ruff check app/routers/`` → "All checks passed!"; ``from app.routers.admin import router; assert len(router.routes) == 1`` → ok; ``pytest tests/routers/test_admin.py`` → 4 xfailed (unchanged from pre-fix state — runtime behaviour identical).
- **Committed in:** ``ac71543``

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Single surgical noqa to satisfy the plan's own success criteria — no runtime behaviour change, no scope creep.

## Issues Encountered

- **Worktree base lag:** the spawn-time base in the orchestrator prompt was ``ef40d72`` (Plan 02-01 fix-up), but my worktree branch was created at ``56d3091`` (Phase 1 xfail commit), 22 commits behind ``ef40d72``. Fast-forwarded via ``git merge ef40d72 --ff-only`` (no destructive reset, ancestor-only merge) so all the Wave-1/2/3 plans (02-01 fixtures, 02-02 argon2, 02-03 require_admin, 02-04 CSRF shim, 02-06 SessionMiddleware) were present before this plan's tasks executed. Filed as an information-only note for the orchestrator — the worktree creation step likely needs to pin against the correct base commit.

## Threat Flags

None — the only new network surface (``GET /admin``) is fully covered by the plan's existing ``<threat_model>`` register (T-02-08-01..04).

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| `<p>Admin (stub) — wiring lands in Phase 9.</p>` | `app/templates/pages/admin.html` | **Intentional per D-13.** Plan 02-08 is wholly about shipping the AUTH-09 gate (the *route exists*, the *gate works*); the admin surface itself is Phase 9's work. The template's stub content IS the deliverable, not a placeholder for missing work. |
| `user` parameter unused inside ``admin_stub`` | `app/routers/admin.py` (line 36) | **Intentional per plan §interfaces.** Form 1 signature is forward-compatible with Phase 9 — the handler body will read ``user.username`` / ``user.is_admin`` / ``user.email`` directly. Keeping the parameter today eliminates a signature change in Phase 9. |

## User Setup Required

None.

## Self-Check: PASSED

**Files verified:**
- `app/routers/admin.py` — exists, imports cleanly (verified in container after ``docker cp app/dependencies app/routers``), ``len(router.routes) == 1``.
- `app/templates/pages/admin.html` — exists, renders without Jinja error against a mock request+user, output contains the D-13 literal body.
- `tests/routers/test_admin.py` — exists, collects 4 tests; all 4 xfail with the router-not-wired pytext message (expected per plan).

**Commits verified:**
- ``43774d0`` (Task 1 RED) — in ``git log``.
- ``7a6ef6f`` (Task 2 router) — in ``git log``.
- ``5ed5605`` (Task 3 template) — in ``git log``.
- ``ac71543`` (Auto-fix B008) — in ``git log``.

**Verification commands run inside container (per CLAUDE.md docker convention):**
- `pytest tests/routers/test_admin.py -v` → 4 xfailed (runtime-xfail pattern engaged because admin router not yet in app.main; Plan 02-10 turns these green).
- `pytest tests/ci/test_no_unsafe_jinja.py -v` → 2 passed (index.html + admin.html both pass the |safe / hx-on: / hx-vals='js:' / hx-headers='js:' forbidden-pattern scan).
- `python -c "from app.routers.admin import router; assert len(router.routes) == 1"` → ok.
- Jinja render smoke: `templates.env.get_template('pages/admin.html').render(...)` succeeds + D-13 literal body present in output.
- `python -m ruff check app/routers/` (host) → "All checks passed!".

**Regression scan:**
- `pytest tests/routers/ tests/ci/` → 5 passed, 6 xfailed, 3 xpassed. The xpassed entries are pre-existing in ``test_auth_stub.py`` and unrelated to this plan's changes.

## Next Phase Readiness

- **Plan 02-09 (debug-proxy admin-gate, D-14):** unblocked. Plan 02-08 originally bundled the ``/debug/proxy`` Depends-Form-2 wrap; that work was split into Plan 02-09 by the plan-checker. 02-09 only needs the existing ``app/dependencies/auth.require_admin`` symbol (already in the worktree from Plan 02-03 merge) plus a 2-line edit to ``app/routers/debug.py``.
- **Plan 02-10 (app.main wiring):** unblocked for this plan's contribution. 02-10's task list adds ``from app.routers import admin as admin_router; app.include_router(admin_router.router)`` to ``app/main.py``. The moment that lands, all 4 tests in ``tests/routers/test_admin.py`` flip from xfail to pass (the runtime-xfail branch is skipped because the route returns 200/403/401 instead of 404).
- **Phase 9 (admin app):** the import path (``app.routers.admin.router``), the dependency gate (``Depends(require_admin)`` Form 1), and the template hierarchy (``pages/admin.html`` extends ``base.html``) are all in place. Phase 9 adds sub-routes (ADMIN-01..06 — user CRUD, API keys, app_settings editor, backups, system info, API health) under the same router and the same gate.

---
*Phase: 02-auth*
*Completed: 2026-05-17*
