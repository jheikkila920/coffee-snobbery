---
phase: 10
slug: global-search
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-21
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Seeded from `10-RESEARCH.md` §"Validation Architecture". The planner assigns
> the concrete Task IDs and confirms the per-task map; Wave 0 builds the test file.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (NOT baked into prod image — `pip install --user pytest pytest-asyncio respx` into the running container first; see CLAUDE.md) |
| **Config file** | none — install before testing |
| **Quick run command** | `docker compose exec coffee-snobbery python -m pytest tests/test_search.py -x -q` |
| **Full suite command** | `docker compose exec coffee-snobbery python -m pytest tests/ -q` |
| **Estimated runtime** | quick ~5s · full ~60s |

> Iteration note (CLAUDE.md): no source bind-mount. Use `docker compose cp tests/test_search.py coffee-snobbery:/app/tests/test_search.py` (file-level, not dir-level — memory `docker-cp-into-container-nesting`) then re-run pytest, or rebuild.
> Full-suite note (memory `full-suite-test-isolation-gaps`): drop `snobbery_test` before a whole-suite run; treat skips as gaps (`-rs`).

---

## Sampling Rate

- **After every task commit:** `docker compose exec coffee-snobbery python -m pytest tests/test_search.py -x -q`
- **After every plan wave:** `docker compose exec coffee-snobbery python -m pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~5 seconds (quick run)

---

## Per-Task Verification Map

> Task IDs are assigned by the planner. Rows below are the requirement→test
> contract from research; the planner maps each to the owning task.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | — | SEARCH-01 | — | Header renders on auth'd pages, absent on `/login` + `/setup` | integration | `pytest tests/test_search.py::test_header_auth_gate -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | SEARCH-01 | — | Coffees match by name | integration | `pytest tests/test_search.py::test_search_coffees -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | SEARCH-01 | — | Roasters match by name | integration | `pytest tests/test_search.py::test_search_roasters -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | SEARCH-01 | — | Recipes match by name (name-only, D-13) | integration | `pytest tests/test_search.py::test_search_recipes -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | SEARCH-01 | — | Equipment matches by `brand \|\| ' ' \|\| model` | integration | `pytest tests/test_search.py::test_search_equipment -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | SEARCH-01 | — | Flavor notes match by name | integration | `pytest tests/test_search.py::test_search_flavor_notes -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | SEARCH-01 | — | Results grouped in fixed order (D-07) | unit | `pytest tests/test_search.py::test_result_group_order -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | SEARCH-01 | — | Each result links to correct entity URL (D-11) | unit | `pytest tests/test_search.py::test_result_links -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | SEARCH-04 | — | Query `<2` chars returns empty response | integration | `pytest tests/test_search.py::test_short_query_empty -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | SEARCH-02 | T-10-IDOR | **User A cannot see User B's brew notes** (CRITICAL) | integration | `pytest tests/test_search.py::test_brew_note_user_scoping -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | SEARCH-03 | — | User A sees shared catalog in results | integration | `pytest tests/test_search.py::test_shared_catalog_visible -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | D-06 | T-10-XSS | Highlight never uses `\|safe`; escapes user text | unit | `pytest tests/test_search.py::test_highlight_xss_safe -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | D-06 | — | Highlight wraps match in `<mark>`/`<strong>` correctly | unit | `pytest tests/test_search.py::test_highlight_markup -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | D-09 | — | Per-group cap ≤5 + "+N more" when 6th exists | unit | `pytest tests/test_search.py::test_group_cap -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | D-12/D-14 | — | Archived coffee/equipment surface with badge; archived roaster/recipe/flavor excluded | integration | `pytest tests/test_search.py::test_archived_scope -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_search.py` — all SEARCH-01..04 unit + integration tests above
- [ ] Two-user + brew-session fixtures for the cross-user scoping test (User A / User B, each with distinctive brew notes)
- [ ] `highlight_match()` helper unit test with XSS payload (`q = "<script>alert(1)</script>"`)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Input inline at ≥768px; collapses to icon → full-screen sheet at <768px | SEARCH-04 | Responsive visual layout — not assertable in pytest | Playwright/manual smoke at 375px and 768px: confirm icon→sheet expand, auto-focus, X/Esc/backdrop close, and inline desktop input |
| Debounce 250ms + `hx-sync="this:replace"` collapses rapid typing to 1–2 queries | SEARCH-04 | Timing/network behavior — observe in browser devtools | Type "ethiopia" quickly; confirm ≤2 requests fire in the Network panel |
| p95 < 100ms against seeded dataset | SEARCH-01 | Latency measurement | Seed dataset, time `/search?q=...` p95 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
