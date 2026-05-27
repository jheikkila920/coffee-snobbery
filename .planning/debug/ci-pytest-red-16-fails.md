---
slug: ci-pytest-red-16-fails
status: resolved
trigger: |
  GitHub Actions Pytest full-suite gate is red on main with 16 failures (1149 pass, 3 skip,
  10 xfailed). Local container test gate stayed green because of source-tree vs baked-image
  divergence (memory: ci-source-tree-vs-baked-image-divergence.md). All 16 failures trace
  to Phase 15.1 / Phase 16 schema and template changes that did not get reflected in the
  test corpus. Surfaced via CI run on 2026-05-27 after the Phase 16 security audit commit
  (70e29c3) landed on main.
created: 2026-05-27
updated: 2026-05-27
---

# Debug: CI pytest red — 16 failures from Phase 15.1/16 schema+template debt

## Symptoms

- **Expected:** Pytest full-suite GitHub Action passes (was green before Phase 15.1).
- **Actual:** 16 test failures in CI on 2026-05-27, four categories.

## Root cause

All 16 failures traced to Phase 15.1 / Phase 16 changes that landed without
updating the test corpus, plus one real D-04 spec violation introduced by the
multi-origin row template:

- **CATEGORY 1 (10 failures, stale tests):** Phase 15.1 CATALOG-03 dropped
  `coffees.origin` and moved to multi-origin via `coffee_origins`; three test
  helpers (`tests/test_search.py::_seed_shared_catalog`,
  `tests/services/test_analytics_perf.py::_seed_1000_sessions`,
  `tests/routers/test_home.py::_seed_gate_cleared_no_sweet_spots`) still passed
  `origin=` to the `Coffee(...)` constructor.
- **CATEGORY 2 (1 failure, stale test):** Phase 15.1 CATALOG-07 dropped
  `bags.roast_date`; `tests/test_migrations.py::test_bags_columns` still asserted
  the column was present and never added the Phase 4 `photo_filename` column.
- **CATEGORY 3 (2 failures, stale tests):** Phase 15.1 CATALOG-07 deleted the
  `/home/cards/roast-freshness` endpoint, the `get_roast_freshness_buckets`
  analytics service function, and the 400ms aggregate-card slot in the home
  shell; `test_roast_freshness_fragment_headers`,
  `test_home_shell_staggered_lazy_load`, and the `test_analytics_query_latency`
  checklist were stale.
- **CATEGORY 4a (1 failure, REAL spec violation):** Phase 15.1 CATALOG-03's
  `app/templates/fragments/coffee_origin_row.html` used `hx-on:click` on the
  Remove button — banned by D-04 (requires CSP `'unsafe-eval'`). The grep test
  `tests/ci/test_no_unsafe_jinja.py[template_path43]` correctly flagged it.
- **CATEGORY 4b/4c (2 failures, stale assertions + 1 stale fixture):**
  - Phase 15.1-05 dual-mount split (commit 58ce3b8) added desktop Edit buttons
    that carry `hx-target="#{equipment,coffee}-form-mount"`. The success
    fragment for `POST /equipment` and `POST /coffees` now legitimately
    contains those bare target references via the OOB list, so the broad
    `"*-form-mount" not in body` assertion was over-strict. Tightened to
    forbid only a NEW `id="*-form-mount"` div declaration (the actually
    self-referential shape).
  - Phase 15.1-03's `T-15.1-03` rejection of zero-origin POSTs meant
    `test_coffee_create_returns_list_fragment` was sending a payload with no
    `origins_country` and silently landing on the form-validation error path
    (which has no OOB swap div). Updated the test payload to include a valid
    `origins_country` value.

## Fix

Categories 1–3 + 4b/4c: 5 test files updated (no production code changes).
Category 4a: production template + JS file updated to use event delegation
(D-04-compliant pattern documented in the CONTEXT for plan 01).

Files modified:
- `tests/test_search.py` — `_seed_shared_catalog`: `origin=` → multi-origin row.
- `tests/services/test_analytics_perf.py` — `_seed_1000_sessions`: multi-origin
  + drop stale `Bag(roast_date=...)` + remove `get_roast_freshness_buckets`
  from the latency checklist; unused `date` import removed.
- `tests/routers/test_home.py` — `_seed_gate_cleared_no_sweet_spots`:
  multi-origin; delete `test_roast_freshness_fragment_headers`; update
  `test_home_shell_staggered_lazy_load` to assert `{100,200,300,500}`.
- `tests/test_migrations.py` — `test_bags_columns`: drop `roast_date`, add
  `photo_filename`.
- `tests/routers/test_equipment_create_fragment.py` — tighten
  `*-form-mount not in body` assertions to `id="*-form-mount" not in body`;
  add `origins_country` to the coffee success payload.
- `app/templates/fragments/coffee_origin_row.html` — `hx-on:click` removed;
  replaced with `data-action="remove-origin-row"` for event delegation (D-04).
- `app/static/js/htmx-listeners.js` — added delegated `click` listener on
  `[data-action="remove-origin-row"]` that removes the closest
  `[data-origin-row]` ancestor. Same client-side outcome, no eval.

## Verification

Full pytest suite (against source tree in container, matching CI environment):

```
1164 passed, 13 skipped, 10 xfailed, 158 warnings in 141.75s
```

- Before: 16 failed, 1149 passed, 3 skipped, 10 xfailed
- After: 0 failed, 1164 passed, 13 skipped, 10 xfailed

The additional 10 skips vs CI baseline come from the e2e/playwright suite
which `pytest.skip`s on missing `playwright` (Plan 12-05 dev image only); CI
also skips these so the deltas reconcile.

Ruff format and lint both clean:

```
$ python -m ruff format --check .
223 files already formatted

$ python -m ruff check .
All checks passed!
```

## Specialist hints

- general: nothing exotic — Python+SQLAlchemy test hygiene + one Jinja+HTMX
  template fix + one event-delegation JS addition. Standard tooling.
