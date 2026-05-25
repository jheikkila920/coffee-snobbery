---
phase: 14-audit-remediation
plan: "01"
subsystem: admin/user-management
tags: [bugfix, dead-code, tdd, security, admin]
dependency_graph:
  requires: []
  provides: [fixed-admin-last-admin-guard, multi-admin-regression-tests]
  affects: [app/routers/admin/users.py, tests/phase_09/test_admin_users.py]
tech_stack:
  added: []
  patterns: [sqlalchemy-subquery-count-with-for-update]
key_files:
  created: []
  modified:
    - app/routers/admin/users.py
    - tests/phase_09/test_admin_users.py
decisions:
  - "FOR UPDATE applied on inner subquery (SELECT User.id ... WITH FOR UPDATE), not on the outer COUNT — this is the only Postgres-legal way to retain row locking on a count query"
  - "Dead duplicate guard in update_user deleted outright; two remaining 'Cannot demote yourself.' strings are both live (one in update_user D-16 guard, one in toggle_admin D-16 guard) — plan's grep-count-1 acceptance criterion was a planning error that didn't account for toggle_admin"
metrics:
  duration_minutes: 4
  completed_date: "2026-05-25"
  tasks_completed: 3
  files_modified: 2
---

# Phase 14 Plan 01: Fix _count_active_admins subquery COUNT + dead guard (B1, B4) Summary

**One-liner:** Replaced FOR-UPDATE-on-aggregate crash in `_count_active_admins` with a locked subquery COUNT; deleted unreachable duplicate self-demote guard in `update_user`; added 4 multi-admin regression tests covering all call sites.

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Author multi-admin regression tests (B1) — RED | 859c3f3 | tests/phase_09/test_admin_users.py |
| 2 | Fix `_count_active_admins` subquery COUNT (B1) — GREEN | ceced9b | app/routers/admin/users.py |
| 3 | Delete dead duplicate self-demote guard (B4) | 2ed5055 | app/routers/admin/users.py |

## RED -> GREEN Confirmation

**RED (Task 1, commit 859c3f3):** All 4 new `TestMultiAdminOperations` tests were synced into the container and run against the buggy `_count_active_admins`. All 4 failed with:

```
psycopg.errors.FeatureNotSupported: FOR UPDATE is not allowed with aggregate functions
[SQL: SELECT COUNT(*) FROM users WHERE is_admin = true AND is_active = true FOR UPDATE]
```

This is the exact B1 crash. The 10 pre-existing tests continued passing (they don't hit the multi-admin path).

**GREEN (Task 2, commit ceced9b):** After applying the subquery COUNT fix and syncing app code:
- All 4 new multi-admin tests pass
- All 10 pre-existing guard/CSRF tests pass
- 14/14 total in `tests/phase_09/test_admin_users.py`

## Fix Details

### B1 — `_count_active_admins` subquery COUNT

**Before (buggy):**
```python
def _count_active_admins(db: Session) -> int:
    """Count active admin users with a FOR UPDATE row lock (Pitfall 7)."""
    return db.execute(
        text("SELECT COUNT(*) FROM users WHERE is_admin = true AND is_active = true FOR UPDATE")
    ).scalar_one()
```

**After (fixed):**
```python
def _count_active_admins(db: Session) -> int:
    """Count active admin users with a FOR UPDATE row lock (Pitfall 7).

    The lock is applied to the inner subquery (on individual User rows), not
    to the outer COUNT — PostgreSQL does not allow FOR UPDATE on aggregates.
    This serializes concurrent admin-demotion transactions at the DB level.
    """
    locked_subq = (
        select(User.id)
        .where(User.is_admin.is_(True), User.is_active.is_(True))
        .with_for_update()
        .subquery()
    )
    return db.execute(select(func.count()).select_from(locked_subq)).scalar_one()
```

`text` import removed (was only used in the buggy query).

### B4 — Dead duplicate self-demote guard deleted

Removed 3-line block from `update_user` (comment + if statement). The removed code:
```python
# Self-lockout guard on is_admin demotion
if target.is_admin and not new_is_admin_raw and target_id == admin_user.id:
    return _render_error_fragment(request, "Cannot demote yourself.", 409)
```

This was unreachable because the preceding D-16 guard at lines 299-305 checks `target.is_admin and not new_is_admin_raw` as the outer condition, and then `target_id == admin_user.id` as an inner check — identical condition, earlier in the same code path.

## Broader Verification

Plan's verification suite (80 tests across 4 files):
```
tests/test_scheduler.py tests/phase_09/test_admin_users.py tests/services/test_ai_service.py tests/test_search.py
80 passed in 12.89s
```

Ruff clean on both modified files:
```
ruff check app/routers/admin/users.py tests/phase_09/test_admin_users.py  -> All checks passed!
ruff format --check app/routers/admin/users.py tests/phase_09/test_admin_users.py -> 2 files already formatted
```

## Deviations from Plan

### Plan acceptance criteria deviation: grep -c "demote yourself" returns 2 not 1

The plan's Task 3 acceptance criterion stated `grep -c "demote yourself" app/routers/admin/users.py` returns 1. It returns 2.

**Why:** The plan's count didn't account for the `toggle_admin` handler, which has its own live (non-duplicate) D-16 self-demote guard: `return _render_error_fragment(request, "Cannot demote yourself.", 409)` at line 374. This guard was there before the plan ran and is not dead code.

**What was deleted:** Exactly the one unreachable duplicate in `update_user` described in the plan (lines 298-300 in the original, renumbered after Task 2). The behavioral spec of the plan is satisfied: one dead duplicate removed, no live guard removed.

**Classification:** Planning error in the acceptance criterion (forgot to count `toggle_admin`), not a code bug. No behavioral impact.

## Known Stubs

None. All code paths are fully wired.

## Threat Flags

No new security-relevant surface introduced. B1 fix closes T-V4-01 (the 500-on-other-admin crash). B4 fix closes T-V4-03 (dead code removal). T-V4-02 (row lock retained) confirmed by `with_for_update()` on the subquery.

## Self-Check: PASSED

- `app/routers/admin/users.py` exists and contains `with_for_update()` and `select(func.count()).select_from(`
- `tests/phase_09/test_admin_users.py` exists and contains `test_demote_other_admin_succeeds`
- Commits 859c3f3, ceced9b, 2ed5055 all present in git log
- `text` import removed from users.py import line 40
- No `FOR UPDATE` inside any `text(` call in users.py (text import removed entirely)
- 14/14 admin user tests green; 80/80 plan verification suite green
