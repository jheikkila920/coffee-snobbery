---
phase: quick-260519-ql9
plan: 01
subsystem: shared-catalog + ops + security-docs
tags: [bugfix, integrityerror, csrf-docs, makefile-smoke, codex-bucket-a]
requires: []
provides:
  - "Duplicate catalog-name writes (roasters + flavor notes, create + update) return a friendly inline 'Name already exists.' at HTTP 200 instead of a 500"
  - "DuplicateNameError sentinel in app/services/form_validation.py"
  - "make smoke head assertion that is revision-id-agnostic"
  - "accurate CSRF enforcement-scope docstring"
affects:
  - app/services/form_validation.py
  - app/services/roasters.py
  - app/services/flavor_notes.py
  - app/routers/roasters.py
  - app/routers/flavor_notes.py
  - Makefile
  - app/csrf.py
tech-stack:
  added: []
  patterns:
    - "service raises typed sentinel (DuplicateNameError) -> router catches -> existing errors_by_field re-render path (mirrors the ValidationError convention)"
    - "catch sqlalchemy.exc.IntegrityError narrowly (not generic Exception), rollback, re-raise typed sentinel"
key-files:
  created: []
  modified:
    - app/services/form_validation.py
    - app/services/roasters.py
    - app/services/flavor_notes.py
    - app/routers/roasters.py
    - app/routers/flavor_notes.py
    - tests/phase_04/test_routers_roasters.py
    - tests/phase_04/test_routers_flavor_notes.py
    - Makefile
    - app/csrf.py
decisions:
  - "Placed DuplicateNameError in form_validation.py (the existing shared catalog seam both routers already import) rather than inventing a new error module"
  - "Caught IntegrityError narrowly per task — other DB errors keep surfacing as a (correct) 500"
metrics:
  duration: ~25m
  completed: 2026-05-20
---

# Quick Task 260519-ql9: Codex Bucket-A Fixes Summary

Closed three independent, verified Codex bucket-A findings with surgical, scope-contained changes: a real user-facing 500 on duplicate catalog names, a stale smoke-test migration-head assertion, and a factually wrong CSRF docstring. Three atomic commits (fix / chore / docs); no schema, dependency, env-var, or CSRF behavior changes.

## What Changed

### Task 1 — Duplicate-name IntegrityError → friendly inline error (commit e37cdf3)

- **`app/services/form_validation.py`**: added `class DuplicateNameError(Exception)` (typed sentinel) and exported it in `__all__`. Chosen home because it is the existing shared seam both catalog routers already import `errors_by_field` from — no new import source.
- **`app/services/roasters.py`** + **`app/services/flavor_notes.py`**: imported `from sqlalchemy.exc import IntegrityError` and `DuplicateNameError`. Wrapped the `create_*` (`add`/`flush`/`commit`) and `update_*` (core `update().values(...)` + `commit`) write paths in `try/except IntegrityError` → `db.rollback()` → `raise DuplicateNameError from exc`. Catch is narrow (only `IntegrityError`) so other DB failures still surface as a correct 500. The `log.info` audit lines stay after `commit`, so they are naturally skipped on the failure path. Rollback guarantees a subsequent valid write in the same session succeeds.
- **`app/routers/roasters.py`** + **`app/routers/flavor_notes.py`**: imported `DuplicateNameError` alongside `errors_by_field`. Wrapped the four service `create`/`update` calls in `try/except DuplicateNameError`, re-rendering the SAME form fragment at `status_code=200` with `errors=_normalize_errors({"name": "Name already exists."})` and `values=raw`. Context shape preserved exactly per handler: roasters create keeps `mode="modal" if as_modal else "create"`; roasters update keeps `mode="edit"` + `roaster_id`; flavor notes both keep `categories=FLAVOR_NOTE_CATEGORIES` (so the `<select>` still renders) plus `mode`/`flavor_note_id`.
- **Tests** (authored, not executed here — see "Test Execution" below): four new tests matching `tests/phase_04` conventions (`_require_postgres` + `_require_p4_migration_applied` guards, `_prime_csrf`, clean fixtures, existing `_seed_roaster` / `_seed_flavor_note` helpers):
  - `test_create_roaster_duplicate_name_returns_friendly_error` — seeds "Onyx", POSTs case-variant "onyx" → asserts 200 + `text-red-700` + "Name already exists."; then asserts a follow-up valid create still succeeds (rollback proof).
  - `test_update_roaster_duplicate_name_returns_friendly_error` — seeds two roasters, renames one onto the other → 200 + friendly error.
  - `test_create_flavor_note_duplicate_name_returns_friendly_error` — parallel, plus asserts `<select` still renders (categories context preserved) + rollback follow-up.
  - `test_update_flavor_note_duplicate_name_returns_friendly_error` — parallel rename case.

### Task 2 — make smoke live-head assertion (commit e9184c2)

- **`Makefile`**: replaced the hardcoded `alembic current | grep -E '^0001_initial \(head\)'` with the revision-id-agnostic `alembic current | grep -E '\(head\)'`. `alembic current` appends ` (head)` only when the applied revision IS the live head, so the marker check asserts "DB is at head" without ever naming a revision — it will not rot when the next migration lands. Added a one-line comment explaining this; surrounding `curl /healthz`, `@echo`, and `smoke: OK` lines unchanged; no other target touched. No `0001_initial` and no hardcoded `p4_shared_catalog` remain anywhere in the file.

### Task 3 — CSRF docstring correction (commit 9678787)

- **`app/csrf.py`**: rewrote the `CSRF_SENSITIVE_COOKIES` `#:` docstring. Removed the false claim that an unauthenticated POST carrying the `csrftoken` cookie "still gets checked because the double-submit pattern remains intact." New text states accurately: enforcement is scoped to requests carrying the `session_id` cookie (authenticated sessions); `/login` and `/setup` carry no `session_id` cookie and are intentionally NOT CSRF-enforced; this is a deliberate `sensitive_cookies` design choice and the residual login-CSRF exposure is an accepted, low-impact household-scale exception (no public registration; admin-provisioned users only).
- **DOCUMENTATION ONLY**: `CSRF_SENSITIVE_COOKIES` value is unchanged (`{"session_id"}`); `csrf_middleware_kwargs` and all runtime code are byte-for-byte unchanged (verified via `git diff` — only comment lines changed).

## Required Output Statements (per plan `<output>`)

**(a) Test execution.** The four new duplicate-name tests were **authored but NOT executed in this environment** — pytest is not in the production image and there is no running container/DB here. They are written to match the existing `tests/phase_04` conventions and will skip cleanly (via `_require_postgres` / `_require_p4_migration_applied`) when the DB is absent. To run them on a host with the stack up (per CLAUDE.md):

```bash
docker compose cp tests/ coffee-snobbery:/app/tests/
docker compose exec coffee-snobbery pip install --user pytest pytest-asyncio respx
docker compose exec coffee-snobbery python -m pytest -q tests/phase_04/test_routers_roasters.py tests/phase_04/test_routers_flavor_notes.py -k duplicate
```

**(b) htmx-listeners.js.** Verified **already correct** — lines 30-33 already state "an unauthenticated request without a CSRF token is not enforced." No change made.

**(c) CSRF runtime behavior.** Confirmed **not altered**. `CSRF_SENSITIVE_COOKIES` stays `{"session_id"}`; `csrf_middleware_kwargs` and the `CSRFFormFieldShim` are untouched. The Task 3 change is comment-only.

## Deviations from Plan

None affecting the three task items. The plan tagged Task 1 `tdd="true"`; the RED/GREEN cycle could not be run here (no pytest/DB/container), so tests were authored alongside the implementation and validated only by static review + ruff, per the environment notes.

## Deferred Issues (out of scope — logged, not fixed)

- **Pre-existing `S110` lint** (`try`-`except`-`pass`) in `tests/phase_04/test_routers_flavor_notes.py` → `test_name_unique_citext_returns_validation_error`. Confirmed pre-existing on the committed file (`git stash` + `ruff check`); that test was neither authored nor modified here. The block carries `# noqa: BLE001` but not `# noqa: S110`. Outside this task's scope boundary. Logged in `deferred-items.md`; appropriate for the Phase 12 "tighten ruff" pass or a future cleanup.

## Verification

- ruff format + ruff check: **clean** on all touched files I authored/modified (`app/services/*.py`, `app/routers/*.py`, `app/csrf.py`, `tests/phase_04/test_routers_roasters.py`). The only `ruff check` finding is the pre-existing S110 noted above.
- `make smoke` head assertion: revision-id-agnostic (`MARKER_OK` from the plan's verify command — no `0001_initial`, no `p4_shared_catalog`).
- CSRF docstring: `DOCSTRING_FIXED` from the plan's verify command; runtime constant + kwargs unchanged.
- Three atomic conventional commits: `fix:` / `chore:` / `docs:`.

## Commits

- `e37cdf3` fix: return friendly inline error on duplicate catalog name instead of 500
- `e9184c2` chore: assert live alembic head in make smoke instead of stale revision id
- `9678787` docs: correct CSRF enforcement-scope docstring for sensitive_cookies

## Self-Check: PASSED

- All 9 touched files exist on disk.
- All 3 commit hashes present in `git log`.
- No file deletions across the 3 commits.
