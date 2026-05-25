---
phase: 07-ai-services
plan: "02"
subsystem: wishlist-service
tags: [wishlist, idor, tdd, user-scoped-crud]
dependency_graph:
  requires: []
  provides: [app/services/wishlist.py]
  affects: [07-05-router, 07-07-pages]
tech_stack:
  added: []
  patterns: [kwarg-after-star user scoping, None/False IDOR sentinel, structlog audit on writes]
key_files:
  created:
    - app/services/wishlist.py
    - tests/services/test_wishlist.py
  modified: []
decisions:
  - "mark_purchased uses datetime.now(tz=UTC) rather than func.now() — avoids a round-trip and keeps the Python layer in control of timestamp type (tz-aware datetime object returned to callers immediately after commit)"
  - "get_wishlist_entry is a shared internal fetch used by both mark_purchased and remove_entry — single filter point for the IDOR guard"
metrics:
  duration_minutes: 12
  completed_date: "2026-05-21"
  tasks_completed: 2
  files_created: 2
  files_modified: 0
requirements: [AI-13]
---

# Phase 7 Plan 02: Wishlist Service Summary

User-scoped wishlist CRUD service with full IDOR defense — add / list / get / mark-purchased / remove, all filtered by `by_user_id` (kwarg-after-star, server-set), with None/False sentinels for cross-user access attempts.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Failing wishlist service tests | 2f90a8b | tests/services/test_wishlist.py |
| 2 (GREEN) | Wishlist service implementation | 0afae46 | app/services/wishlist.py |

## TDD Gate Compliance

RED gate: `test(07-02)` commit 2f90a8b — 8 tests written before any implementation.
GREEN gate: `feat(07-02)` commit 0afae46 — all 8 tests pass.
REFACTOR: no cleanup required; implementation was clean on first pass.

## What Was Built

`app/services/wishlist.py` with five functions:

- `add_to_wishlist(db, *, by_user_id, coffee_name, roaster_name, source_url, source="ai_recommendation", notes="")` — inserts a user-scoped row, commits, returns the entry. Structlog `wishlist.add` on success.
- `list_wishlist(db, *, by_user_id) -> list[WishlistEntry]` — `select()` filtered by `WishlistEntry.user_id == by_user_id`, ordered by `added_at desc`.
- `get_wishlist_entry(db, *, entry_id, by_user_id) -> WishlistEntry | None` — `scalar_one_or_none` with dual filter `id == entry_id AND user_id == by_user_id`; cross-user returns None (T-07-05).
- `mark_purchased(db, *, entry_id, by_user_id) -> WishlistEntry | None` — delegates to `get_wishlist_entry`; if None returns None; else sets `purchased_at = datetime.now(tz=UTC)`, commits, returns refreshed row. Structlog `wishlist.mark_purchased`.
- `remove_entry(db, *, entry_id, by_user_id) -> bool` — delegates to `get_wishlist_entry`; if None returns False; else `db.delete`, commits, returns True. Structlog `wishlist.remove`.

`tests/services/test_wishlist.py` with 8 tests:

- `test_add_and_list_scoped_to_user` — list isolation between two users.
- `test_list_order_newest_first` — ordering by `added_at desc`.
- `test_add_defaults_source_ai_recommendation` — D-09 default source.
- `test_get_wishlist_entry_cross_user_returns_none` — IDOR sentinel (T-07-05).
- `test_mark_purchased_sets_timestamp` — happy path.
- `test_mark_purchased_cross_user_none` — IDOR, row stays unmodified.
- `test_remove_cross_user_false_keeps_row` — IDOR, row survives.
- `test_remove_owner_true` — happy path, row gone after delete.

## Deviations from Plan

None — plan executed exactly as written.

## Threat Surface Scan

No new network endpoints, auth paths, or file access patterns introduced. Service layer only; threat mitigations T-07-05 and T-07-06 implemented as planned.

## Self-Check

Files exist:
- app/services/wishlist.py: FOUND
- tests/services/test_wishlist.py: FOUND

Commits exist:
- 2f90a8b: FOUND (RED)
- 0afae46: FOUND (GREEN)

Tests: 8 passed, 0 failed.

## Self-Check: PASSED
