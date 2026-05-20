---
phase: 05-brew-sessions
plan: 02
subsystem: api
tags: [sqlalchemy, postgres, service-layer, idor, usage-count, prefill, upsert, structlog]

# Dependency graph
requires:
  - phase: 05-brew-sessions (plan 01)
    provides: BrewSession + BrewDraft ORM models (GENERATED extraction_yield_pct, user_id RESTRICT), brew.* event constants, BrewSessionCreate/Update schemas
  - phase: 04-shared-catalog
    provides: coffees / bags / recipes / equipment tables + the equipment.usage_count column shipped at 0 (increment deferred to Phase 5)
  - phase: 02-auth
    provides: users table (RESTRICT FK target), request.state.user per-user scoping convention
provides:
  - "app/services/brew_sessions.py — per-user CRUD (create/update/delete/get/list) scoped by user_id, with brew.session.* audit events and single-commit transactions"
  - "equipment.usage_count maintenance: +1 per non-null FK on create, ±1 diff on edit, -1 on delete — all three FKs (brewer/grinder/kettle) in the session write transaction"
  - "Prefill resolution (resolve_prefill + latest_session / newest_open_bag_id / recipe_targets) implementing D-04 hybrid, D-05 recipe-wins, D-06 newest-open-bag, D-08 brew-again"
  - "app/services/brew_drafts.py — one-draft-per-user upsert/get/clear via INSERT ... ON CONFLICT, keyed by user_id (T-05-08)"
affects: [brew-router, brew-csv-import, brew-prefill-ui, brew-drafts-ui, analytics, ai-recommendations]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-user-scoped service: every read/update/delete filtered by user_id; update→None / delete→False sentinel for non-owned ids (router maps to 404) — first per-user service in the app (T-05-05 IDOR defense)"
    - "Same-transaction denormalized-counter maintenance: usage_count moves atomically with the session row; an edit diffs old-vs-new across the three equipment FKs (Pitfall 6 no-drift)"
    - "Atomic single-row upsert via sqlalchemy.dialects.postgresql.insert().on_conflict_do_update(index_elements=[...]) against a UNIQUE column (no read-then-write race)"

key-files:
  created:
    - app/services/brew_sessions.py
    - app/services/brew_drafts.py
    - tests/services/test_brew_sessions_service.py
    - tests/services/test_brew_prefill.py
    - tests/services/test_brew_drafts.py
  modified: []

key-decisions:
  - "resolve_prefill returns a flat dict the router renders; the four D-05 recipe-template fields overwrite last-session values only when a recipe is selected; per-attempt fields (rating/observed/notes) are ALWAYS blanked on the /brew/new path"
  - "brew-again (D-08) sources the named session scoped by user_id and drops a bag whose finished_at is no longer NULL — D-08 overrides the D-04 hybrid default"
  - "brew_drafts upsert uses Postgres INSERT ... ON CONFLICT (user_id) DO UPDATE rather than a read-then-write, so a double-blur autosave can never create a second row"

patterns-established:
  - "Per-user service scoping with None/False sentinels for cross-user access (the router-404 contract)"
  - "Denormalized counter (usage_count) diffed across multiple FKs inside the same write transaction"
  - "ON CONFLICT DO UPDATE single-row upsert keyed by a UNIQUE column for one-per-user stores"

requirements-completed: [BREW-01, BREW-02, BREW-06, BREW-07, BREW-09]

# Metrics
duration: ~8min
completed: 2026-05-20
---

# Phase 5 Plan 02: Brew-Session Service Layer Summary

**Per-user brew CRUD with brew.session.* audit events, same-transaction equipment.usage_count maintenance across all three FKs, the D-04/D-05/D-06/D-08 prefill-resolution engine, and a one-draft-per-user ON-CONFLICT upsert store — 21 service tests green in-container, full suite 342 passed.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-05-20T01:52:57Z
- **Completed:** 2026-05-20T02:01:07Z
- **Tasks:** 3 of 3
- **Files modified:** 5 (5 created, 0 modified)

## Accomplishments

- `brew_sessions` service: create/update/delete/get/list, the app's first per-user service. Every query is scoped by `user_id`; `update`/`get` return `None` and `delete` returns `False` for a session not owned by the caller (T-05-05 IDOR defense — the router maps the sentinel to 404). `extraction_yield_pct` (GENERATED) and `user_id` (server-owned) are never written.
- `equipment.usage_count` maintenance (the increment Phase 4 deferred): +1 per non-null of (brewer/grinder/kettle) on create, an old-vs-new ±1 diff on edit (incl. null→value and value→null flips), and -1 per non-null FK on delete — all inside the same transaction as the session write so the counter never drifts (Pitfall 6).
- Prefill resolution: `resolve_prefill` plus `latest_session` / `newest_open_bag_id` / `recipe_targets` implement D-04 (hybrid: last session, or last session with a given coffee), D-05 (recipe-wins on the four template fields), D-06 (newest open bag, `finished_at IS NULL`, `opened_at DESC NULLS LAST`), and D-08 (brew-again sources a specific session, blanks per-attempt fields, drops a finished bag, and is user-scoped).
- `brew_drafts` service: `upsert_draft` / `get_draft` / `clear_draft`, one row per user via `INSERT ... ON CONFLICT (user_id) DO UPDATE` (no read-then-write race). Per-user keyed (T-05-08); `clear_draft` is a safe no-op when absent (called on submit + logout). The payload is opaque JSON the service never interprets.
- All `brew.session.*` and `brew.draft.*` audit events are emitted via the imported `app/events.py` constants (no literal strings).

## Task Commits

Each task was committed atomically (TDD: test → feat):

1. **Task 1: brew_sessions service — CRUD + audit + usage_count**
   - `7e2f1a6` (test) [TDD RED]
   - `c2715f2` (feat) [TDD GREEN — also lands the Task 2 prefill helpers, which share this file]
2. **Task 2: Prefill resolution (D-04/05/06/08)** — `c24a7e1` (test) [verifies the prefill helpers committed in c2715f2]
3. **Task 3: brew_drafts service — upsert/get/clear**
   - `616357c` (test) [TDD RED]
   - `7cc8c32` (feat) [TDD GREEN]

_TDD gates satisfied: `test(...)` RED commits precede the `feat(...)` GREEN commits for the behavior-adding tasks (Task 1, Task 3)._

## Files Created/Modified

- `app/services/brew_sessions.py` — per-user CRUD, usage_count diff helpers, prefill resolution (`resolve_prefill` + the three component queries)
- `app/services/brew_drafts.py` — one-per-user upsert (ON CONFLICT) / get / clear
- `tests/services/test_brew_sessions_service.py` — 5 tests: create user-scoped row, usage_count (3 FKs + edit-diff + delete), null↔value flips, list user-scoping (IDOR), list filters
- `tests/services/test_brew_prefill.py` — 10 tests: D-04 carry+blank / no-history / hybrid, D-05 recipe-wins / unknown-recipe, D-06 newest-open-bag / none-open, D-08 brew-again blank / user-scoped / finished-bag-drop
- `tests/services/test_brew_drafts.py` — 6 tests: upsert-one-row, upsert-returns-row, get-none, clear-then-none, clear-no-op, per-user isolation

## Decisions Made

- **Prefill returns a flat dict, recipe overwrites last only on select.** `resolve_prefill` sources carryable fields first (D-08 named session OR D-04 last/last-with-coffee), applies D-06 default bag when a coffee is resolved and bag is unset, then layers D-05 recipe targets over the four template fields ONLY when a recipe is selected, and finally always blanks the three per-attempt fields. The router adds touched-state + pill captions on top. Matches the plan's prescribed ordering.
- **Brew-again drops a finished bag and overrides D-04.** When `from_session_id` is set, the source is that user's session (scoped, IDOR-safe); if its `bag_id` now points at a bag with a non-NULL `finished_at`, it drops to `None` (then D-06 may re-default). This is the D-08-over-D-04 precedence the CONTEXT locks.
- **Upsert via ON CONFLICT, not read-then-write.** `brew_drafts.user_id` is UNIQUE, so a single `INSERT ... ON CONFLICT (user_id) DO UPDATE` is atomic and idempotent — a rapid double autosave-on-blur can never create a second row. Chosen over a `select`-then-`add/update` for race-safety and brevity.

## Deviations from Plan

None - plan executed exactly as written.

The plan splits the prefill helpers (Task 2) and CRUD (Task 1) across the same file (`app/services/brew_sessions.py`). They were implemented together in the Task 1 GREEN commit (`c2715f2`) because they share the module; Task 2's commit (`c24a7e1`) lands the verifying prefill tests. This is the file-organization the plan's `<files>` fields prescribe, not a scope deviation.

## Issues Encountered

- **Context7 quota exhausted.** The project's mandated ctx7 lookup for the SQLAlchemy 2.0 `update().values(col=col+1)` / `on_conflict_do_update` API returned "Monthly quota exceeded" (same as Plan 01). Relied on the planner-verified patterns in 05-PATTERNS.md and the existing on-disk analogs (`equipment.py`, `bags.py`, `settings.py`), and validated the rendered behavior directly against the live Postgres via the 21 in-container service tests. All patterns are standard SQLAlchemy 2.0 Core idioms already used elsewhere in the codebase.
- **ruff / pytest not in the production image.** Per CLAUDE.md, both are manual `pip install --user` into the running container (ruff 0.15.13 to match the host); ruff needs `RUFF_CACHE_DIR=/tmp/ruff` because `/app/.ruff_cache` is not writable by the app user. Lint + format were also run on the host (matching ruff 0.15.13) to write formatter changes back, since the container files are not writable by ruff's atomic-write. New production code (`brew_sessions.py`, `brew_drafts.py`) passes `ruff check` and `ruff format --check` clean.
- **Git Bash path mangling.** `RUFF_CACHE_DIR=/tmp/ruff` and ctx7 `/org/repo` library IDs are rewritten to Windows paths by Git Bash; worked around with `MSYS_NO_PATHCONV=1`.

## Known Stubs

None — all five functions in each service are fully implemented and exercised against the live DB. The router (Wave 3) and CSV I/O (Wave 2 sibling) that consume this service are intentionally out of scope for this plan.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The brew service contract is defined and tested, so the Wave 3 router and the Wave 2 CSV-import plan can build the thin request/response layer on top of `create_brew_session` / `update_brew_session` / `delete_brew_session` / `list_brew_sessions` / `resolve_prefill` and the draft `upsert`/`get`/`clear`.
- `equipment.usage_count` now moves with brew writes — Phase 6 analytics' "most-used grinder" widget has a correct, no-drift counter from the first logged session.
- Full suite green in-container: 342 passed, 2 skipped, 10 xfailed, 0 failed.

## Self-Check: PASSED

All 5 created files exist on disk; all 5 task commits (7e2f1a6, c2715f2, c24a7e1, 616357c, 7cc8c32) present in git history; the three service test files (21 tests) pass in-container.

---
*Phase: 05-brew-sessions*
*Completed: 2026-05-20*
