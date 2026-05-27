---
phase: 16-cafe-quick-rate
plan: "06"
subsystem: testing
tags: [snobbery, sqlalchemy, photo-orphan-sweep, union-all, silent-data-loss, pitfall-8]

dependency_graph:
  requires:
    - "16-01: CafeLog model + p16_cafe_logs migration + _require_cafe_logs_table() skip-gate"
  provides:
    - "sweep_orphans extended to UNION bags.photo_filename and cafe_logs.photo_filename"
    - "test_sweep_keeps_cafe_photos regression test (Pitfall 8 closure)"
  affects:
    - "Phase 16+ nightly scheduler: cafe photos no longer deleted on first sweep post-deploy"

tech_stack:
  added: []
  patterns:
    - "Lazy import of CafeLog inside sweep_orphans (mirrors existing Bag lazy-import pattern)"
    - "referenced_main |= set comprehension for second DB source (union without new sweep loop)"
    - "_require_postgres_reachable() local wrapper + _require_cafe_logs_table() import from conftest"

key_files:
  created: []
  modified:
    - app/services/photos.py
    - tests/phase_04/test_services_photos.py

key_decisions:
  - "Test appended to tests/phase_04/test_services_photos.py (not tests/services/test_photos.py) because photo_volume fixture is scoped to tests/phase_04/conftest.py"
  - "CafeLog import is lazy inside sweep_orphans function body, mirroring the Bag lazy-import at lines 381-383 per the established module pattern"
  - "Set union via |= into referenced_main — no new sweep loop, no branching, single _sweep_unreferenced call preserved"

requirements-completed: [CAFE-02]

duration: 25min
completed: 2026-05-27
---

# Phase 16 Plan 06: Photo Orphan Sweep — CafeLog Union Summary

**`sweep_orphans` extended to UNION `cafe_logs.photo_filename` into `referenced_main`, closing Pitfall 8 (silent data-loss landmine that would have deleted every cafe photo on the first nightly sweep post-deploy).**

## Performance

- **Duration:** ~25 minutes
- **Started:** 2026-05-27T17:45:00Z
- **Completed:** 2026-05-27T18:10:00Z
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments

- Extended `sweep_orphans` (+5 effective LOC): lazy `CafeLog` import + second `SELECT cafe_logs.photo_filename` + `referenced_main |= {...}` union
- Updated module docstring and function docstring to document both tables and Pitfall 8 cross-reference
- Added `test_sweep_keeps_cafe_photos` (TDD RED then GREEN): seeds a `CafeLog` row + orphan pair, runs sweep, asserts orphan pair deleted (2 files) and cafe pair survives; uses `_require_cafe_logs_table()` skip-gate per project memory `tests-pass-by-skip-mask-green`
- All 4 sweep tests (3 pre-existing Phase 4 + 1 new) pass green against the rebuilt baked image
- `ruff format --check` and `ruff check` both exit 0 on both modified files

## Task Commits

1. **Task 1 (TDD RED): test_sweep_keeps_cafe_photos** - `2772c92` (test)
2. **Task 2 (TDD GREEN): extend sweep_orphans** - `6cb6bf1` (feat)
3. **Task 3: ruff + baked image gate** - no new commit (verification only, no code change)

## Files Created/Modified

- `app/services/photos.py` - Extended `sweep_orphans`: added lazy `CafeLog` import + `cafe_rows` SELECT + `referenced_main |=` union; updated module + function docstrings
- `tests/phase_04/test_services_photos.py` - Appended `test_sweep_keeps_cafe_photos` (94 lines) with `_require_postgres_reachable()` + `_require_cafe_logs_table()` skip-gates

## Decisions Made

- **Test file location:** The plan specified `tests/services/test_photos.py` but the actual photo tests live in `tests/phase_04/test_services_photos.py` where the `photo_volume` fixture is scoped (via `tests/phase_04/conftest.py`). Appended to the correct existing file rather than creating a parallel file that would fail fixture resolution. Documented as Rule 3 deviation (blocking issue: fixture not in scope).
- **No separate commit for Task 3:** Task 3 is verification-only (ruff + baked image gate). Both modified files were already ruff-clean after Tasks 1 and 2.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Appended test to tests/phase_04/test_services_photos.py instead of tests/services/test_photos.py**
- **Found during:** Task 1 (RED test authoring)
- **Issue:** Plan specified `tests/services/test_photos.py` but that file doesn't exist. The `photo_volume` fixture is defined in `tests/phase_04/conftest.py` and is only available to tests under `tests/phase_04/`. Creating `tests/services/test_photos.py` without that fixture would cause `photo_volume` to be unresolved at collection time.
- **Fix:** Appended `test_sweep_keeps_cafe_photos` to `tests/phase_04/test_services_photos.py` where all existing sweep tests already live and `photo_volume` is in scope.
- **Files modified:** tests/phase_04/test_services_photos.py (instead of tests/services/test_photos.py)
- **Verification:** `pytest tests/phase_04/test_services_photos.py -q -rs` shows 12 passed, 0 skipped against the baked image.
- **Committed in:** 2772c92 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 3 - blocking fixture scope)
**Impact on plan:** No scope creep. The test ends up exactly where it belongs alongside the other sweep tests. The `files_modified` list in the plan frontmatter references the wrong path; the canonical location is `tests/phase_04/test_services_photos.py`.

## Issues Encountered

None beyond the fixture-scope deviation above.

## TDD Gate Compliance

- RED gate: `test_sweep_keeps_cafe_photos` fails with `deleted_count == 4` (all 4 files deleted, including cafe pair) before Task 2 implements the fix. Commit: `2772c92`.
- GREEN gate: `test_sweep_keeps_cafe_photos` passes (`deleted_count == 2`, cafe pair survives) after extending `sweep_orphans`. Commit: `6cb6bf1`.
- REFACTOR gate: not needed — diff is minimal and idiomatic.

## Known Stubs

None. This plan is a surgical fix (5 LOC + 1 regression test). No UI rendering, no data stubs.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The only surface change is the `sweep_orphans` function now queries a second DB table — this is read-only and reduces the risk of data loss (not an expansion of attack surface).

## Next Phase Readiness

- Plan 16-05 (analytics UNION for D-12/D-13) runs in parallel in this same wave and is unaffected.
- Plans 16-02/16-03/16-04 (cafe routes, templates, sessions tab) depend on 16-01 and are unblocked.
- The nightly sweep is now safe for cafe photos: deploy Phase 16 without risk of overnight photo deletion.

## Self-Check

- [x] `app/services/photos.py` modified — `grep -n "from app.models.cafe_log import CafeLog" app/services/photos.py` returns 1 line inside sweep_orphans
- [x] `tests/phase_04/test_services_photos.py` modified — `test_sweep_keeps_cafe_photos` present
- [x] Commit `2772c92` exists (RED test)
- [x] Commit `6cb6bf1` exists (GREEN implementation)
- [x] `ruff format --check` exits 0 on both files
- [x] `ruff check` exits 0 on both files
- [x] `pytest tests/phase_04/test_services_photos.py -q -rs` → 12 passed, 0 skipped against baked image

## Self-Check: PASSED
