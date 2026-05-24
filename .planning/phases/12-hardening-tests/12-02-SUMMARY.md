---
phase: 12-hardening-tests
plan: "02"
subsystem: tests/ci
tags: [security, csp, grep-tests, ci-gate, credential-safety]
dependency_graph:
  requires: []
  provides: [D-07a, D-07b, TEST-03]
  affects: [tests/ci/]
tech_stack:
  added: []
  patterns: [static-grep-test, parametrize-rglob, comment-strip-before-scan]
key_files:
  created:
    - tests/ci/test_csp_nonce.py
    - tests/ci/test_no_credential_dump.py
  modified: []
decisions:
  - "Strip Python triple-quoted docstrings before model_dump scan to avoid false positive in app/models/api_credential.py module docstring (line 16 documents the exact invariant being enforced)."
metrics:
  duration: "~15 minutes"
  completed: "2026-05-24"
  tasks_completed: 2
  tasks_total: 2
  files_created: 2
  files_modified: 0
---

# Phase 12 Plan 02: Security Grep Tests (D-07a + D-07b) Summary

Two permanent security grep tests added to `tests/ci/`, both static file scans with zero Postgres dependency. They gate on every pytest invocation and will run in CI (Plan 07).

## Tasks

### Task 1: CSP nonce + unsafe-directive template grep (D-07a) -- COMPLETE

**Commit:** `6f86c56`
**Files:** `tests/ci/test_csp_nonce.py`

Two parametrized tests over `app/templates/**/*.html` (81 files at commit time):

1. `test_script_style_tags_have_nonce` -- fails on any `<script>`/`<style>` open tag missing a `nonce=` attribute. Uses negative lookahead `(?![^>]*\bnonce\s*=)` after stripping Jinja + HTML comments.
2. `test_no_unsafe_directives` -- fails on `'unsafe-eval'` or `'unsafe-inline'` in any template source.

Result: **162 passed** (81 templates x 2 checks).

### Task 2: model_dump-on-ApiCredential grep (D-07b / SEC-6) -- COMPLETE

**Commit:** `9ae5b3d`
**Files:** `tests/ci/test_no_credential_dump.py`

One parametrized test over `app/**/*.py` (106 files at commit time):

- Early-returns files that don't reference `ApiCredential` or `api_credential` (keeps scan narrow, avoids false positives on unrelated models).
- Strips triple-quoted docstrings and `#` comments before scanning. This was necessary because `app/models/api_credential.py` line 16 contains `model_dump()` inside the module docstring -- it documents the invariant being enforced, not a real call. Without stripping, the test would false-positive on the file that defines the model.
- Fails with file + 1-based line number on any real `model_dump(` in a credential-referencing file.

Result: **106 passed**.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Added Python docstring/comment stripping to credential dump test**

- **Found during:** Task 2 pre-flight scan
- **Issue:** `app/models/api_credential.py` line 16 contains `model_dump()` inside the module docstring -- it explains the SEC-6 invariant. The plan's PATTERNS.md block did not include comment stripping, so the naive scan would false-positive immediately.
- **Fix:** Added `_strip_python_non_code()` helper (triple-quoted string strip + `#` comment strip) mirroring the template test's `_strip_comments()` philosophy. Verified: stripped scan finds no false positive; a synthetic real call in code is still caught.
- **Files modified:** `tests/ci/test_no_credential_dump.py`
- **No source fix needed:** The docstring is correct; the test just needed comment-aware scanning.

## Overall Verification

`pytest tests/ci/ -q` (all three grep tests: `test_no_unsafe_jinja.py`, `test_csp_nonce.py`, `test_no_credential_dump.py`): **349 passed**.

Both new tests collect at least one parametrized case (templates and app/*.py both exist).

## Known Stubs

None.

## Threat Flags

None -- these are tests, not new application surface.

## Self-Check: PASSED

- `tests/ci/test_csp_nonce.py` exists: FOUND
- `tests/ci/test_no_credential_dump.py` exists: FOUND
- Commit `6f86c56` exists: FOUND
- Commit `9ae5b3d` exists: FOUND
- `pytest tests/ci/` green (349 passed): CONFIRMED
