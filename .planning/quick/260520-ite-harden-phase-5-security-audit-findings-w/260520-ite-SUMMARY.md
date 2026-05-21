---
quick_task: 260520-ite
title: Harden Phase 5 security audit findings (W-01, W-02)
date: "2026-05-20"
duration_minutes: 15
tasks_completed: 2
files_modified: 3
commits:
  - e4f1cf5
  - ccf98f3
tags: [security, hardening, csv-import, jinja-safety, tests]
---

# Quick Task 260520-ite: Harden Phase 5 Security Audit Findings (W-01, W-02)

**One-liner:** Content-Length pre-check on CSV import rejects oversized uploads before body buffering (W-01); Jinja safety CI test widened from pages/ to all of app/templates/ (W-02).

## Tasks

### Task 1 — W-01: Content-Length pre-check on CSV import

**Commit:** `e4f1cf5`
**Files:** `app/routers/brew.py`, `tests/routers/test_brew_list_csv.py`

**What changed:**

Added a pre-check at the very top of `import_sessions` (before `await request.form()`) that reads the `Content-Length` request header. If it is present, all-digit, and exceeds `csv_io_service.MAX_CSV_BYTES` (5 MiB), the handler returns the "That file is too large to import." error fragment immediately — the multipart body is never buffered.

- Non-digit or absent `Content-Length` values fall through (chunked transfer-encoding has no Content-Length; adversarial clients may omit or lie).
- The existing post-read `len(raw_bytes) > MAX_CSV_BYTES` check is retained as defense-in-depth for those cases.
- Docstring updated to describe the two-layer design accurately.

New test `test_import_oversized_content_length_rejected` in `tests/routers/test_brew_list_csv.py`:
- Sends a small body with `Content-Length` overridden to `MAX_CSV_BYTES + 1`.
- Asserts HTTP 200 (fragment), "too large" error text in response, and zero rows inserted.
- Uses the module's established skip gates, `_authed_client`, and fixture patterns.
- Documents the httpx header-override limitation in the docstring.

**Verification:** `ruff format` + `ruff check` clean. Full pytest for this module requires a live Postgres container with the p5 migration applied; not available in the local dev environment (the conftest test-isolation fix is a prerequisite). The logic is structurally sound: the pre-check runs before any body read, the isdigit() guard is correct, and the test correctly overrides the header.

### Task 2 — W-02: Widen Jinja safety grep test to all templates

**Commit:** `ccf98f3`
**Files:** `tests/ci/test_no_unsafe_jinja.py`

**What changed:**

Renamed `PAGES_DIR = Path("app/templates/pages")` to `TEMPLATES_DIR = Path("app/templates")` so the `rglob("*.html")` now covers `pages/`, `fragments/`, `base.html`, and any future subdirs. Updated all references: `parametrize` call, test function docstring, module docstring, and inline comments. `FORBIDDEN_PATTERNS`, `_strip_comments`, and all four regex patterns are unchanged.

**Verification:** Full pytest run locally (no DB needed — test reads files only):
- Previously: ~12 templates collected (pages/ only)
- After widening: **43 templates collected, 43 passed** in 47.56s
- `ruff format` + `ruff check` clean

## Deviations from Plan

None. Both tasks executed exactly as specified.

## Verification Summary

| Check | W-01 | W-02 |
|-------|------|------|
| ruff format --check | PASS | PASS |
| ruff check | PASS | PASS |
| pytest (local, no DB) | Not run (DB required for brew router tests) | 43/43 PASS |
| Logic review | Pre-check is correct; test correctly overrides header | Scope widened, no false positives |

**W-01 pytest limitation:** `tests/routers/test_brew_list_csv.py` requires a live Postgres instance with the p5 migration applied. The local environment does not have Docker running during this execution. The conftest test-isolation fix (see STATE.md blockers) is also a prerequisite before running brew router tests in-container safely.

## Known Stubs

None.

## Threat Flags

None. Both changes add guards; no existing CSRF, security-header, or encryption guard is removed or weakened.

## Self-Check

- [x] `app/routers/brew.py` — modified, committed in e4f1cf5
- [x] `tests/routers/test_brew_list_csv.py` — modified, committed in e4f1cf5
- [x] `tests/ci/test_no_unsafe_jinja.py` — modified, committed in ccf98f3
- [x] Both commits exist in git log
- [x] No planning docs committed (constraint honored)

## Self-Check: PASSED
