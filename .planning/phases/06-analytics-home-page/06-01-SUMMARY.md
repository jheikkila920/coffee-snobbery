---
phase: "06-analytics-home-page"
plan: "01"
subsystem: "analytics"
tags: ["analytics", "home-page", "sql", "performance", "signature"]
dependency_graph:
  requires:
    - "05-brew-sessions: brew_sessions table + indexes"
    - "04-shared-catalog: coffees, bags, equipment, recipes, flavor_notes, roasters tables"
    - "00-foundation: SessionLocal, Postgres connection pool"
  provides:
    - "app/services/analytics.py: all HOME-01..05/07/08 derivations + compute_input_signature"
  affects:
    - "06-02, 06-03: home router + fragment endpoints import from this module"
    - "Phase 7 AI service: reads compute_input_signature for stale-data gate"
tech_stack:
  added: []
  patterns:
    - "Pure-SQL GROUP BY / HAVING over per-user brew sessions (no Python aggregation loops)"
    - "Postgres implicit lateral unnest (FROM bs, unnest(...) AS note_id) for array aggregation"
    - "SHA256 over canonical JSON (json.dumps + hashlib) for deterministic content signature"
    - "raw text() for unnest queries where column_valued() lateral join fails at runtime"
key_files:
  created:
    - "app/services/analytics.py"
    - "tests/services/test_analytics.py"
    - "tests/services/test_analytics_perf.py"
  modified: []
decisions:
  - "Used raw SQL text() for get_flavor_descriptors and get_cold_start_counts unnest queries because func.unnest().column_valued() lateral join fails at runtime with SQLAlchemy 2.0.49 ORM layer (Assumption A2 from RESEARCH.md confirmed)"
  - "Resolved RESEARCH Open Question 1: sweet spots requires both brewer_id AND recipe_id non-null (INNER JOIN, documented v1 behavior per Pitfall 7)"
  - "Resolved RESEARCH Open Question 2: one preference-profile fragment, four queries in service, returned as dict keyed by dimension"
  - "No Alembic migration added — all 9 queries pass <50ms budget with existing Phase 5 indexes"
metrics:
  duration: "16 minutes"
  completed: "2026-05-20T20:08:26Z"
  tasks_completed: 4
  tasks_total: 4
  files_created: 3
  files_modified: 0
---

# Phase 6 Plan 1: Analytics Service (Home Page Brain) Summary

Pure-SQL analytics service implementing nine read-only query functions over the user's brew log, plus `compute_input_signature` for Phase 7's stale-data gate. All derivations run <50ms against a 1000-session seed using existing Phase 5 indexes.

## What Was Built

### `app/services/analytics.py` (409 lines)

The "home page brain" per CLAUDE.md. Nine public functions:

| Function | Card | Key Constraint |
|---|---|---|
| `get_top_coffees` | HOME-01 | avg rating DESC, HAVING count>=2, NULL ratings excluded |
| `get_preference_profile` | HOME-02 | Four separate GROUP BYs (origin/process/roaster/roast_level), HAVING count>=2 per D-06 |
| `get_flavor_descriptors` | HOME-03 | Unnests observed array (NOT advertised), rated>=4.0, HAVING count>=2 per D-07 |
| `get_roast_freshness_buckets` | HOME-04 | Reads bags.roast_date ONLY (never coffees.roast_date), CASE bucketing, HAVING count>=2 |
| `get_sweet_spots` | HOME-05 | Single GROUP BY over 4 dimensions, HAVING count>=3, no Python loops |
| `get_recent_brews` | HOME-07 | Last 10 sessions, coffee join, no rating requirement |
| `get_unrated_coffees` | HOME-08 | Coffee.archived==False enforced, NOT IN brewed coffee_ids |
| `get_cold_start_counts` | Gate | LIVE counts including unrated sessions (D-02 vs D-09 distinction) |
| `compute_input_signature` | Phase 7 | SHA256 of rated-only sessions ordered by id, _EMPTY_SIGNATURE sentinel |

Every query's first WHERE clause is `BrewSession.user_id == user_id` (T-06-01 IDOR defense).

### `tests/services/test_analytics.py` (13 tests)

Full seeded-DB unit test suite covering all derivations, signature determinism, archived-coffee exclusion, and the all-unrated edge case (D-05).

### `tests/services/test_analytics_perf.py` (1 test)

1000-session seed (5 coffees, 700 rated + 300 unrated sessions, varied freshness/flavor/equipment spread) + per-query latency assertion. All 9 functions pass <50ms budget.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `func.unnest().column_valued()` lateral join fails at runtime (Assumption A2)**

- **Found during:** Task 3 (first test run)
- **Issue:** `func.unnest(BrewSession.flavor_note_ids_observed).column_valued("note_id")` produces a `TableValuedColumn` that SQLAlchemy 2.0.49's ORM join layer cannot resolve. Error: `Join target, typically a FROM expression... got <TableValuedColumn note_id>`. This was documented as "Assumption A2" (MEDIUM confidence) in RESEARCH.md with a `text()` fallback prescribed.
- **Fix:** Replaced `get_flavor_descriptors` and `get_cold_start_counts` unnest JOIN with raw SQL `text()` using PostgreSQL's implicit lateral join syntax: `FROM brew_sessions bs, unnest(bs.flavor_note_ids_observed) AS note_id`. Bound parameter `:user_id` maintained to satisfy T-06-03 (no SQL injection via user input).
- **Files modified:** `app/services/analytics.py`
- **Commits:** d1543a8 (initial), 474d67f (fix)

**2. [Rule 1 - Bug] Date calculation bug in perf seed helper**

- **Found during:** Task 4 (first perf test run)
- **Issue:** `date(2026, 3, 10 - day_offset)` produced invalid dates (day=0 or negative) when `day_offset` >= 10.
- **Fix:** Replaced with `brew_ref - timedelta(days=days_fresh)` using proper date arithmetic.
- **Files modified:** `tests/services/test_analytics_perf.py`
- **Commit:** bdfe0c5

## Performance Results

All 9 queries ran under budget with existing Phase 5 indexes. No new Alembic migration was added.

| Query | Existing Index Used | Result |
|---|---|---|
| get_top_coffees | ix_brew_sessions_user_coffee_brewed_at | <50ms |
| get_preference_profile | ix_brew_sessions_user_brewed_at | <50ms |
| get_flavor_descriptors | ix_brew_sessions_user_brewed_at | <50ms |
| get_roast_freshness_buckets | ix_brew_sessions_user_brewed_at | <50ms |
| get_sweet_spots | ix_brew_sessions_user_brewed_at | <50ms |
| get_recent_brews | ix_brew_sessions_user_brewed_at | <50ms |
| get_unrated_coffees | ix_coffees_archived | <50ms |
| get_cold_start_counts | ix_brew_sessions_user_brewed_at | <50ms |
| compute_input_signature | ix_brew_sessions_user_brewed_at | <50ms |

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The analytics service is a pure read layer; all security surface was planned (T-06-01, T-06-02, T-06-03 in the plan threat model). Per-user scoping (T-06-01) verified in test_unrated_coffees and test_all_unrated_returns_empty by checking correct data isolation.

## Known Stubs

None. All functions return live DB data. The service layer is complete and ready for Phase 6 Plan 02 (home router + fragment endpoints).

## Self-Check: PASSED

- `app/services/analytics.py` exists and imports cleanly
- `tests/services/test_analytics.py` exists with 13 tests
- `tests/services/test_analytics_perf.py` exists with 1 test
- Commits verified: 52e0fd4, d1543a8, 474d67f, bdfe0c5
- All 14 tests pass (13 unit + 1 perf)
- ruff check passes on analytics.py
- No Coffee.roast_date, no advertised_flavor_note_ids in code, no db.query() legacy API
- Coffee.archived == False present in get_unrated_coffees (line 305)
- _EMPTY_SIGNATURE defined at module level (line 41)
- No new migration added (verified: git status app/migrations/)
