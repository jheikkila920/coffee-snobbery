---
phase: 07-ai-services
plan: "07"
subsystem: ai-pages-ui
tags: [ai, pages, htmx, csrf, idor, wishlist, paste-rank, equipment, mobile-first]
dependency_graph:
  requires:
    - app/routers/ai.py (POST /ai/paste-rank, /ai/equipment, /ai/wishlist/* — 07-05)
    - app/services/wishlist.py (list_wishlist — 07-02)
    - app/services/ai_service.py (rank_pasted_coffees, generate_equipment_rec — 07-04)
    - app/services/ai_schemas.py (PasteRankSchema, EquipmentRecSchema — 07-01)
    - app/templates_setup.py (templates instance)
  provides:
    - app/routers/ai.py (GET /ai/paste-rank, GET /ai/wishlist page handlers)
    - app/templates/pages/paste_rank.html
    - app/templates/pages/wishlist.html
    - app/templates/fragments/ai/paste_rank_results.html
    - app/templates/fragments/home/equipment_rec.html
  affects:
    - app/templates/pages/home.html (AI tools section: links + equipment button)
    - tests/routers/test_ai_router.py (8 new tests added)
    - tests/routers/test_home.py (2 new tests added)
tech_stack:
  added: []
  patterns:
    - "HX-Request dual-render on POST /ai/paste-rank (fragment on HTMX, full page otherwise)"
    - "GET page handlers gated by require_user; user_id only from request.state.user.id (T-07-12)"
    - "CSRF hidden field on every state-changing form in new templates (T-07-11)"
    - "wishlist IDOR: list_wishlist scoped by by_user_id=user.id; cross-user action -> 404 (T-07-05)"
    - "Equipment result: EquipmentRecSchema.model_validate(_row.response_json) in router"
    - "Equipment button: generate-on-click only; #equipment-rec-result div starts empty (D-05)"
    - "No |safe on AI prose/coffee names in any new template (T-07-13)"
key_files:
  created:
    - app/templates/pages/paste_rank.html
    - app/templates/pages/wishlist.html
    - app/templates/fragments/ai/paste_rank_results.html
    - app/templates/fragments/home/equipment_rec.html
  modified:
    - app/routers/ai.py
    - app/templates/pages/home.html
    - tests/routers/test_ai_router.py
    - tests/routers/test_home.py
decisions:
  - "HX-Request dual-render on POST /ai/paste-rank: HTMX gets fragment, non-HTMX gets full page with results inlined via {% include %} — brew.py lines 484-516 pattern"
  - "EquipmentRecSchema.model_validate in the router (not template): keeps template logic-free; bare except maps to rec=None (graceful degradation)"
  - "AI tools section placed between AI hero and aggregate cards in gate-open block: links to paste-rank/wishlist always visible when gate is open"
  - "equipment result div starts empty and has no hx-trigger — only user click triggers generation (D-05 generate-on-click invariant)"
metrics:
  duration: "~30 minutes"
  completed: "2026-05-21"
  tasks_completed: 2
  files_created: 4
  files_modified: 4
requirements: [AI-08, AI-09, HOME-06]
---

# Phase 7 Plan 07: AI Pages (Paste-Rank, Wishlist, Equipment Button) Summary

**One-liner:** Dedicated paste-and-rank page (text/URL textarea, top-3 ranked results with reasoning), minimal wishlist view (list/mark-purchased/remove with IDOR guard), on-demand equipment button + result fragment, and home-page links to both pages — all CSP-clean and CSRF-protected, human-verify checkpoint approved at 375px.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | GET handlers + paste-rank page + results fragment + equipment fragment | 9f00f36 | app/routers/ai.py, pages/paste_rank.html, fragments/ai/paste_rank_results.html, fragments/home/equipment_rec.html, tests/routers/test_ai_router.py |
| 2 | Wishlist page + home-page links + equipment button | 26964cd | pages/wishlist.html, pages/home.html, tests/routers/test_home.py, tests/routers/test_ai_router.py |
| 3 | Human verify — paste-rank, wishlist, equipment button at 375px | APPROVED | verified 2026-05-21 at 375px (gate seeded open; pages, home AI-tools links, equipment-button placement, and wishlist add/purchase/remove flow confirmed; live AI ranking/equipment output deferred to provider-key configuration) |

## Verification

- `python -m pytest tests/routers/test_ai_router.py tests/routers/test_home.py -q` -> **41 passed**
- `ruff check app/routers/ai.py` -> All checks passed
- `grep "|safe"` in all new templates -> only in Jinja comments (no filter applied)
- `grep "hx-on:"` in new templates -> absent (CSP-clean)
- `grep 'hx-get="/ai/equipment"'` in home.html -> absent (D-05: generate-on-click only)

## Acceptance Criteria Status

| Criterion | Status |
|-----------|--------|
| GET /ai/paste-rank defined, gated by require_user | PASS |
| GET /ai/wishlist defined, gated by require_user, scoped via list_wishlist(by_user_id=user.id) | PASS |
| pages/paste_rank.html contains name="input_text" textarea, posts to /ai/paste-rank with X-CSRF-Token | PASS |
| fragments/ai/paste_rank_results.html renders up to 3 ranked items with reasoning, no |safe | PASS |
| fragments/home/equipment_rec.html renders equipment result incl. "no changes recommended" path | PASS |
| pages/wishlist.html mark-purchased + remove forms (CSRF), purchased badge/dim | PASS |
| home.html contains /ai/paste-rank link, /ai/wishlist link, hx-post="/ai/equipment" with #equipment-rec-result | PASS |
| test_paste_rank_page_renders passes | PASS |
| test_paste_rank_submit_returns_results passes (3-item fragment) | PASS |
| test_equipment_button_returns_fragment passes | PASS |
| test_wishlist_page_requires_auth passes | PASS |
| test_wishlist_page_lists_user_entries passes (IDOR scope) | PASS |
| test_home_links_to_ai_pages passes | PASS |
| test_home_has_equipment_button passes | PASS |
| Full pytest exits 0 (41 passed) | PASS |
| Human verify at 375px | PASS (approved 2026-05-21) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] result.ranked_coffees -> result.ranked in POST /ai/paste-rank**

- **Found during:** Task 1 implementation
- **Issue:** The 07-05 stub handler used `result.ranked_coffees` but `PasteRankSchema` defines the field as `ranked` (not `ranked_coffees`). The stub returned inline HTML so the attribute access was never exercised — but the new template-based path would have raised `AttributeError` on first real call.
- **Fix:** Changed `result.ranked_coffees` to `result.ranked` in the replaced inline handler. Field name matches `PasteRankSchema.ranked` in ai_schemas.py.
- **Files modified:** app/routers/ai.py
- **Commit:** 9f00f36

## Known Stubs

None. All new pages and fragments render real data paths. The equipment result uses `EquipmentRecSchema.model_validate(_row.response_json)` with a bare-except fallback to `rec=None` (renders the error state copy). This is a genuine graceful-degradation path, not a stub.

## Threat Surface Scan

| Flag | File | Description |
|------|------|-------------|
| Mitigated per plan | app/routers/ai.py | T-07-12 (auth): GET /ai/paste-rank + GET /ai/wishlist both gated by Depends(require_user) |
| Mitigated per plan | app/routers/ai.py | T-07-05 (IDOR): GET /ai/wishlist uses list_wishlist(by_user_id=user.id) exclusively |
| Mitigated per plan | new templates | T-07-13 (XSS): no |safe in paste_rank_results.html, equipment_rec.html, paste_rank.html, wishlist.html |
| Mitigated per plan | new templates | T-07-11 (CSRF): X-CSRF-Token hidden field on every state-changing form |

No new threat surface beyond the plan's threat register.

## Self-Check: PASSED

Files exist:
- app/templates/pages/paste_rank.html: FOUND
- app/templates/pages/wishlist.html: FOUND
- app/templates/fragments/ai/paste_rank_results.html: FOUND
- app/templates/fragments/home/equipment_rec.html: FOUND
- app/routers/ai.py: FOUND (modified)
- app/templates/pages/home.html: FOUND (modified)
- tests/routers/test_ai_router.py: FOUND (modified)
- tests/routers/test_home.py: FOUND (modified)

Commits exist:
- 9f00f36: FOUND (Task 1)
- 26964cd: FOUND (Task 2)

Tests: 41 passed, 0 failed.
