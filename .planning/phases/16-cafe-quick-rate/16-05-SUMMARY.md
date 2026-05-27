---
phase: 16-cafe-quick-rate
plan: "05"
subsystem: analytics
tags: [snobbery, sqlalchemy, postgres, analytics, ai-signature, cold-start, union-all, cafe-logs]
dependency_graph:
  requires: ["16-01", "16-02"]
  provides: ["CAFE-04-analytics", "CAFE-05-guard"]
  affects: ["app/services/analytics.py", "tests/services/test_analytics.py"]
tech_stack:
  added: []
  patterns:
    - "SQLAlchemy 2.0 union_all().subquery() for per-dimension UNION aggregation"
    - "Raw SQL UNION ALL of two unnest blocks for array-column aggregation (psycopg 3 :user_id single-key multi-reference)"
    - "Two-element top-level payload list [[brew_list], [cafe_list]] for SHA256 signature namespace defense"
key_files:
  created: []
  modified:
    - app/services/analytics.py
    - tests/services/test_analytics.py
decisions:
  - "D-12: compute_input_signature payload shape changed from flat [brews] to [[brews], [cafes]] (Pitfall 3 namespace defense + Pitfall 9 one-time regen accepted)"
  - "D-13: origin + roaster dims UNION cafe data; process + roast_level stay brew-only (cafe form doesn't capture them)"
  - "D-14: get_top_coffees body UNCHANGED; guard comment added"
  - "D-15: cold-start gate counts brew + cafe together; dict keys preserved for _cold_start.html"
  - "D-16: get_sweet_spots body UNCHANGED; guard comment added"
metrics:
  duration_minutes: 45
  tasks_completed: 7
  tasks_total: 7
  files_modified: 2
  completed_date: "2026-05-27"
---

# Phase 16 Plan 05: Analytics Cafe Integration Summary

**One-liner:** Surgical extension of analytics.py to wire cafe_logs into the AI signature, preference-derivation queries, and cold-start gate — while explicitly fencing get_top_coffees and get_sweet_spots from cafe UNIONs (D-14, D-16).

## What Was Built

Five functions in `app/services/analytics.py` were extended with cafe data (D-12, D-13, D-15), two received one-line guard comments only (D-14, D-16), and `tests/services/test_analytics.py` gained 11 new cafe-aware test functions plus a `_seed_cafe_into_scenario` helper.

### Function-by-function changes

| Function | Change Type | Decision |
|---|---|---|
| `compute_input_signature` | New cafe SELECT + payload shape change: `[[brews], [cafes]]` | D-12 |
| `get_preference_profile` | origin + roaster dims UNION'd; process + roast_level brew-only | D-13 |
| `get_flavor_descriptors` | Raw SQL FROM extended with UNION ALL of two unnest blocks | D-13 |
| `get_cold_start_counts` | cafe_count scalar added; distinct-notes UNION ALL of two unnest blocks | D-15 |
| `get_top_coffees` | Comment guard added; body unchanged | D-14 |
| `get_sweet_spots` | Comment guard added; body unchanged | D-16 |

## Pitfall 9 Acknowledgement — One-Time AI Regen

The signature payload shape changed from the old flat `[brew_rows]` to the new `[[brew_rows], [cafe_rows]]`. This produces a different SHA256 for the same brew-only state. On the first nightly run post-deploy, every existing user will have their recommendation regenerated once. At household scale (~6 users), cost is less than $0.10 total. This is Option (a) from RESEARCH.md — accepted and documented here. Future comparison against the pre-deploy signature will always differ; subsequent nightly runs will produce a stable new hash.

## Test Coverage

| Test | Requirement | Status |
|---|---|---|
| `test_signature_includes_cafe_logs` | D-12: rated cafe row mutates signature | PASS |
| `test_signature_excludes_unrated_cafe` | D-12: unrated cafe row leaves signature unchanged | PASS |
| `test_preference_profile_origin_unions_cafe` | D-13: Costa Rica from cafe appears in origin dim | PASS |
| `test_preference_profile_roaster_unions_cafe` | D-13: roaster count increases across union | PASS |
| `test_preference_profile_process_brew_only` | D-13: process + roast_level unchanged after cafe insert | PASS |
| `test_flavor_descriptors_unions_cafe` | D-13: cafe-only note surfaces in descriptors | PASS |
| `test_cold_start_brew_only` | D-15: 3 brews + 5 notes → gate_open | PASS |
| `test_cold_start_cafe_only` | D-15: 3 rated cafe logs + 5 notes → gate_open | PASS |
| `test_cold_start_mixed` | D-15: 1 brew + 2 cafe → sessions==3, gate_open | PASS |
| `test_sweet_spots_excludes_cafe` | D-16: sweet_spots output bit-identical after cafe insert | PASS |
| `test_top_coffees_excludes_cafe` | D-14: top_coffees output unchanged after cafe insert | PASS |

All 11 new tests + 12 pre-existing analytics tests = **23 passed, 0 failed, 0 skipped** on the rebuilt BAKED image.

## Security / Threat Coverage

| Threat ID | Mitigation |
|---|---|
| T-16-05-01 (SQLi in raw SQL) | Bound `:user_id` parameter on all raw SQL blocks; :user_id referenced twice per UNION (psycopg 3 single-key dict); no f-string or string concatenation. |
| T-16-05-02 (IDOR info disclosure) | `CafeLog.user_id == user_id` WHERE clause on every new cafe-side SELECT. |
| T-16-05-03 (signature shape churn) | Accepted (Pitfall 9 Option (a)); documented above. |
| T-16-05-05 (future UNION addition) | Guard comments in get_top_coffees + get_sweet_spots + automated exclusion tests. |
| T-16-05-06 (namespace collision) | `[brew_list, cafe_list]` two-element top-level list; position is the namespace. |

## Deviations from Plan

None. Plan executed exactly as written. The `_seed_cafe_into_scenario` helper was implemented as a module-level function rather than inlined, per the plan's "planner's call, simpler shape preferred" guidance.

## Known Stubs

None. All analytics functions return real query results; no hardcoded empty values, placeholder text, or mock data sources.

## Self-Check

### Files exist
- `app/services/analytics.py` — modified, all 5 function changes applied
- `tests/services/test_analytics.py` — modified, 11 new tests + helper + skip gate

### Commits
- `8213199` test(16-05): add failing tests for cafe analytics integration (D-12..D-16)
- `606d850` feat(16-05): extend compute_input_signature with [brew_list, cafe_list] payload (D-12)
- `5bd931a` feat(16-05): UNION cafe into get_preference_profile origin + roaster dims (D-13)
- `2904788` feat(16-05): UNION cafe into get_flavor_descriptors raw SQL (D-13)
- `53df9ed` feat(16-05): extend get_cold_start_counts with brew+cafe combined math (D-15)
- `ba519ae` feat(16-05): add guard comments to get_top_coffees + get_sweet_spots (D-14, D-16)
- `671df2f` style(16-05): ruff format + fix lint warnings in analytics.py + test_analytics.py

## Self-Check: PASSED
