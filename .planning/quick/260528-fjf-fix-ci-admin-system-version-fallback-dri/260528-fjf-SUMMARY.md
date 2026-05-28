---
quick_id: 260528-fjf
plan: 01
status: complete
type: execute
requirements:
  - CI-FIX-VERSION-FALLBACK
files_modified:
  - tests/phase_09/test_admin_system.py
commit: 4b4a73d
completed: 2026-05-28
---

# Quick Task 260528-fjf: Fix CI admin_system version fallback (drift `0.1.0` → pyproject)

## One-liner

Replaced stale hardcoded `app_version = "0.1.0"` fallback in `TestSystemInfo.test_system_info` with a `tomllib`-based read of `pyproject.toml`, mirroring the production fallback in `app/routers/admin/system.py`. Unblocks CI without touching production code.

## Root cause (confirmed)

Project memory `ci-source-tree-vs-baked-image-divergence`: CI runs the source tree without pip-installing the app, so `importlib.metadata.version("coffee-snobbery")` raises `PackageNotFoundError` on CI and the test fell back to the hardcoded `"0.1.0"`. That literal drifted when `pyproject.toml` was bumped to `1.2.0` (Phase 18-02, commit `d07cc6b`). The baked container image installs the package, so the baked-image test gate stayed green — only CI broke.

Production was intentionally not touched: `app/routers/admin/system.py:137-147` already implements the correct `pyproject.toml` fallback. This patch makes the test mirror production.

## Diff applied

`tests/phase_09/test_admin_system.py`, single hunk inside `TestSystemInfo.test_system_info`:

```diff
         # App version — either from importlib.metadata or pyproject.toml fallback.
         try:
             from importlib.metadata import version as pkg_version

             app_version = pkg_version("coffee-snobbery")
         except Exception:
-            app_version = "0.1.0"  # pyproject.toml fallback value
+            import tomllib
+            from pathlib import Path
+
+            _pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
+            with _pyproject.open("rb") as _f:
+                app_version = tomllib.load(_f)["project"]["version"]
         assert app_version in body, f"App version '{app_version}' not found in /admin body"
```

Path math: `tests/phase_09/test_admin_system.py` → `parents[2]` = repo root (where `pyproject.toml` lives). Verified before commit.

## Verify commands

| Command | Result | Exit |
|---|---|---|
| `python -m ruff format --check tests/phase_09/test_admin_system.py` | `1 file already formatted` | 0 |
| `python -m ruff check tests/phase_09/test_admin_system.py` | `All checks passed!` | 0 |
| `python -m pytest tests/phase_09/test_admin_system.py::TestSystemInfo::test_system_info -v` | **Local skip** — `ModuleNotFoundError: No module named 'respx'` on host Python 3.14. Pytest+respx are not installed on the Windows host (per CLAUDE.md, the dev test loop runs inside the `coffee-snobbery` container or in CI). | n/a |

Local pytest gating skipped per the constraint's escape hatch: "If pytest fails with a DB-fixture error locally … capture the failure mode and do not block the commit." The failure is a host-environment gap (respx missing on host), not a code defect. The CI run is the authoritative gate.

## Post-commit sanity (plan `verification` block)

| Check | Result |
|---|---|
| `git diff --stat HEAD~1 HEAD` shows single file | ✔ `tests/phase_09/test_admin_system.py \| 7 ++++++-` |
| grep `"0.1.0"` in file | ✔ no matches (stale literal gone) |
| grep `tomllib.load` in file | ✔ 1 match at line 234 |
| Neighbor tests touched | ✘ no — surgical Edit, no formatting drift |

## Commit

- **Hash:** `4b4a73d`
- **Message:** `fix(tests-09): make admin_system version fallback read pyproject.toml`
- **Branch:** `main`
- **Author signed:** John Heikkila

## Out-of-scope items observed (not touched)

Untracked / dirty in working tree at start of task — left alone per scope:

- `M .claude/settings.local.json` (Claude Code local config)
- `?? .planning/debug/edit-coffee-buttons-dead.md` (separate debug doc)
- `?? .planning/quick/260528-fjf-fix-ci-admin-system-version-fallback-dri/` (this task's planning artifacts — orchestrator handles docs commit separately because `commit_docs: false` for this project)

## Self-Check: PASSED

- File modified exists with expected new contents (verified via Grep for `tomllib.load`).
- Stale literal absent (verified via Grep for `"0.1.0"`).
- Commit `4b4a73d` present on `main` (verified via `git rev-parse --short HEAD`).
- Both ruff gates exited 0.
- Pytest local run blocked by host-env (respx not installed); CI is the gate. Documented above.
