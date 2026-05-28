---
phase: 260528-fjf
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tests/phase_09/test_admin_system.py
autonomous: true
requirements:
  - CI-FIX-VERSION-FALLBACK
must_haves:
  truths:
    - "test_admin_system.py::TestSystemInfo::test_system_info passes on CI (source tree, package not pip-installed)"
    - "test_admin_system.py::TestSystemInfo::test_system_info still passes inside the baked container image (package installed)"
    - "Test version-resolution chain mirrors production fallback in app/routers/admin/system.py:137-147 (pyproject.toml read), so future version bumps do not re-break this test"
    - "Ruff format check + ruff lint check both pass on the edited test file"
  artifacts:
    - path: "tests/phase_09/test_admin_system.py"
      provides: "TestSystemInfo.test_system_info with pyproject.toml fallback instead of hardcoded '0.1.0'"
      contains: "tomllib.load"
  key_links:
    - from: "tests/phase_09/test_admin_system.py::TestSystemInfo.test_system_info"
      to: "pyproject.toml (project.version)"
      via: "tomllib read via Path(__file__).resolve().parents[2] / 'pyproject.toml'"
      pattern: "tomllib\\.load"
---

<objective>
Fix the CI test failure `tests/phase_09/test_admin_system.py::TestSystemInfo::test_system_info` caused by a stale hardcoded `"0.1.0"` fallback in the test. Production code (admin/system.py) already falls back to reading `pyproject.toml` when `importlib.metadata.version("coffee-snobbery")` raises (the CI source-tree case, where the package isn't pip-installed). The test must mirror that same fallback so it resolves to the real current version (`1.2.0`) and stays resilient to future version bumps.

Purpose: Unstick CI without touching production code, schema, or `pyproject.toml`. This is a test-only fix per the well-known `ci-source-tree-vs-baked-image-divergence` pattern.

Output: One-method edit in `tests/phase_09/test_admin_system.py`, ruff-clean.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@tests/phase_09/test_admin_system.py
@app/routers/admin/system.py
@pyproject.toml

<interfaces>
<!-- Production version-resolution chain that the test must mirror. -->
<!-- Source: app/routers/admin/system.py lines ~137-147. Do NOT modify this file. -->

Production fallback chain in app/routers/admin/system.py (when resolving app_version):
  1. get_app_version()  # env var, unset in CI
  2. importlib.metadata.version("coffee-snobbery")  # raises in CI (no install)
  3. Read pyproject.toml at parents[3] of system.py and parse project.version

Test file path math:
  - tests/phase_09/test_admin_system.py
  - Path(__file__).resolve().parents[0] == tests/phase_09/
  - Path(__file__).resolve().parents[1] == tests/
  - Path(__file__).resolve().parents[2] == repo root  (where pyproject.toml lives)

Current test code at lines 222-230 (the bug):
  try:
      from importlib.metadata import version as pkg_version
      app_version = pkg_version("coffee-snobbery")
  except Exception:
      app_version = "0.1.0"  # STALE — pyproject.toml is now 1.2.0
  assert app_version in body, ...

Required replacement (mirrors production):
  try:
      from importlib.metadata import version as pkg_version
      app_version = pkg_version("coffee-snobbery")
  except Exception:
      import tomllib
      from pathlib import Path
      _pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
      with _pyproject.open("rb") as _f:
          app_version = tomllib.load(_f)["project"]["version"]
  assert app_version in body, f"App version '{app_version}' not found in /admin body"
</interfaces>

<memory>
Relevant prior memory:
- `ci-source-tree-vs-baked-image-divergence`: CI runs the source tree without pip-installing the app, so `importlib.metadata.version("coffee-snobbery")` raises `PackageNotFoundError` only on CI. The baked container image installs the package and the call succeeds there.
- `executors-skip-ruff-ci-gates-both`: GSD executors routinely commit without running ruff; CI gates on BOTH `ruff format --check` AND `ruff check`. The `verify` block below makes both explicit.
- `windows-crlf-pathlib-write-text`: This edit is via the Edit tool, not `Path.write_text`, so CRLF normalization is not a risk. Do not rewrite the file wholesale.
</memory>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Replace stale hardcoded version fallback with pyproject.toml read in TestSystemInfo.test_system_info</name>
  <files>tests/phase_09/test_admin_system.py</files>
  <action>
Open `tests/phase_09/test_admin_system.py` and locate `TestSystemInfo.test_system_info` (around lines 207-230). The current fallback block hardcodes `app_version = "0.1.0"` when `importlib.metadata.version("coffee-snobbery")` raises. That value drifted when `pyproject.toml` was bumped to `1.2.0` in commit d07cc6b (Plan 18-02), and CI source-tree runs hit the except branch because the package isn't pip-installed.

Replace ONLY the `try/except`/assert block (current lines ~223-230) with a fallback that reads `pyproject.toml` directly, mirroring the production fallback in `app/routers/admin/system.py:137-147`. From this test file, the repo root is `Path(__file__).resolve().parents[2]` (because the file lives at `tests/phase_09/test_admin_system.py`).

Use the Edit tool to perform this surgical change. New block:

  try:
      from importlib.metadata import version as pkg_version

      app_version = pkg_version("coffee-snobbery")
  except Exception:
      import tomllib
      from pathlib import Path

      _pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
      with _pyproject.open("rb") as _f:
          app_version = tomllib.load(_f)["project"]["version"]
  assert app_version in body, f"App version '{app_version}' not found in /admin body"

Constraints (per scope and project CLAUDE.md):
- Do NOT modify `app/routers/admin/system.py`, `pyproject.toml`, or anything under `app/`.
- Do NOT add new tests or refactor other tests in this file.
- Preserve the existing `from __future__ import annotations` at the top of the file.
- Imports inside the `except` branch are intentional — they keep the happy path import-light and mirror the production lazy-import pattern. Ruff is fine with function-local imports; do not hoist to module top.
- Leave the existing comment style consistent with surrounding code. Drop the stale "pyproject.toml fallback value" comment since the new code IS the pyproject.toml read.
- After editing, run `python -m ruff format tests/phase_09/test_admin_system.py` (NOT `--check`) once locally to normalize formatting, then commit. The `verify` step uses `--check` to gate.
- Commit with: `fix(tests-09): make admin_system version fallback read pyproject.toml` (conventional commits, `fix:` because the test was buggy on CI).
  </action>
  <verify>
    <automated>python -m pytest tests/phase_09/test_admin_system.py::TestSystemInfo::test_system_info -v &amp;&amp; python -m ruff format --check tests/phase_09/test_admin_system.py &amp;&amp; python -m ruff check tests/phase_09/test_admin_system.py</automated>
  </verify>
  <done>
- `test_admin_system.py::TestSystemInfo::test_system_info` passes (1 passed) under `python -m pytest` against the local CI-equivalent environment (package not pip-installed on the host, so the except branch is exercised).
- `python -m ruff format --check tests/phase_09/test_admin_system.py` exits 0.
- `python -m ruff check tests/phase_09/test_admin_system.py` exits 0.
- No diff outside `tests/phase_09/test_admin_system.py`. Specifically: `git diff --name-only` lists exactly that one path.
- The committed change uses the prescribed commit message.
  </done>
</task>

</tasks>

<verification>
After the task completes, additionally confirm:

1. `git diff --stat HEAD~1 HEAD` shows a single file changed: `tests/phase_09/test_admin_system.py`.
2. Grep the file for the stale literal — it must be gone:
   `grep -n '"0.1.0"' tests/phase_09/test_admin_system.py` returns no matches.
3. Grep the file for the new fallback wiring:
   `grep -n 'tomllib.load' tests/phase_09/test_admin_system.py` returns at least 1 match in the `TestSystemInfo.test_system_info` body.
4. Optional sanity (do NOT block on this if CI environment is unavailable locally): run the full `tests/phase_09/test_admin_system.py` module to confirm no neighboring test regressed:
   `python -m pytest tests/phase_09/test_admin_system.py -v`
</verification>

<success_criteria>
- The three `verify` commands all exit 0.
- CI's previously-failing assertion (`App version '0.1.0' not found in /admin body`) is gone; the test now compares against whatever `pyproject.toml` currently declares (today: `1.2.0`).
- Production code and `pyproject.toml` are unchanged.
- File remains ruff-format-clean and ruff-lint-clean.
</success_criteria>

<output>
After completion, create `.planning/quick/260528-fjf-fix-ci-admin-system-version-fallback-dri/260528-fjf-01-SUMMARY.md` capturing:
- The exact diff applied (or a short before/after snippet).
- Which `verify` commands ran and their exit codes.
- The commit SHA + message.
- A one-line note confirming the `ci-source-tree-vs-baked-image-divergence` pattern was the root cause and that production was intentionally not touched.
</output>
