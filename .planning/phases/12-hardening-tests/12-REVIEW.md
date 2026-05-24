---
phase: 12-hardening-tests
reviewed: 2026-05-23T00:00:00Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - .github/workflows/ci.yml
  - Dockerfile
  - README.md
  - docker-compose.yml
  - pyproject.toml
  - requirements-dev.txt
  - tests/ci/test_csp_nonce.py
  - tests/ci/test_no_credential_dump.py
  - tests/conftest.py
  - tests/e2e/__init__.py
  - tests/e2e/conftest.py
  - tests/e2e/test_responsive_smoke.py
  - tests/middleware/test_csrf.py
  - tests/test_happy_path_smoke.py
findings:
  critical: 0
  warning: 5
  info: 3
  total: 8
status: issues_found
---

# Phase 12: Code Review Report

**Reviewed:** 2026-05-23
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

## Summary

Phase 12 ships the test/CI hardening layer: SNOB_CI skip-enforcement gate, permanent security grep tests, happy-path smoke, CSRF unit tests, a dev/test multi-stage Dockerfile target with a compose test profile, a Playwright e2e responsive smoke suite, and a GitHub Actions CI workflow. The core isolation logic in `conftest.py` is sound — the test-DB isolation guard, `fresh_db` autouse, `_reset_catalog_tables`, and the `seeded_*` fixture chain all hold up under scrutiny. No critical bugs or security vulnerabilities were found.

Five warnings are present. The most consequential is a documentation/code mismatch in the `app` fixture where the CI workflow comment claims `SNOB_CI=1` prevents hollow-green skips due to a missing Tailwind file, but the code does not enforce this — actual protection comes from workflow step ordering. A second significant gap is dead code: `_require_postgres_hard` is defined with documentation instructing callers to use it, but is never called. Three additional warnings cover an unpinned `pytest-asyncio` that has caused breaking changes in the past, CWD-relative paths in both CI security tests that silently collect zero cases if run outside the repo root, and a wrong line-number calculation in `test_no_credential_dump.py`'s failure message.

---

## Warnings

### WR-01: README documents Tailwind CLI v4 but the build uses v3.4.17

**File:** `README.md:14`, `README.md:23`
**Issue:** The README stack list says "Tailwind CSS (standalone CLI v4)" and the Prerequisites section says "the Tailwind v4 standalone CLI binary." Both the Dockerfile (`ARG TAILWIND_VERSION=v3.4.17`) and the CI workflow download the v3.4.17 binary. The Dockerfile comment at line 21 explicitly explains why v3 is required: the `tailwind.src.css` uses v3 directives (`@tailwind base/components/utilities`) and a v3-style `tailwind.config.js`. The v4 CLI is CSS-first and would produce a near-empty stylesheet. The docs are incorrect.
**Fix:**
```markdown
- Jinja2 + HTMX 2.x + Tailwind CSS (standalone CLI v3) + Alpine.js (CDN, added in Phase 1)
```
and
```markdown
- No Python or Node required on the host — the image bakes Python 3.12, the Tailwind v3 standalone CLI binary, and `postgresql-client-16` from PGDG.
```

---

### WR-02: `app` fixture skips on missing Tailwind even under SNOB_CI=1; CI workflow comment overclaims

**File:** `tests/conftest.py:111-116`, `.github/workflows/ci.yml:38-39`
**Issue:** The `app` fixture catches `RuntimeError` (raised by `app.main` when `tailwind.<hash>.css` is absent) and calls `pytest.skip()` unconditionally — it does not check `_CI_MODE`. The CI workflow comment at lines 38-39 says SNOB_CI=1 "is designed to prevent" the hollow-green result from this skip path. That claim is false: the actual protection is that the "Build Tailwind CSS" step runs before `pytest` and fails the job via `set -euo pipefail` if the binary download or compilation fails. If the Tailwind build step is ever reordered, removed, or conditionally skipped, `test_happy_path_full_chain` (and any test using `client`) will silently skip under `SNOB_CI=1` — producing hollow green without the gate catching it.
**Fix:** Add a `_CI_MODE` check inside the `app` fixture, consistent with `_require_postgres`:
```python
@pytest.fixture
def app() -> Any:
    try:
        from app.main import app as _app
    except RuntimeError as exc:
        if _CI_MODE:
            pytest.fail(f"SNOB_CI=1 but app.main import failed (Tailwind CSS missing?): {exc}")
        pytest.skip(f"app.main import failed (likely Tailwind CSS missing): {exc}")
    except ImportError as exc:
        pytest.skip(f"app.main not importable (Wave 1 dependency missing): {exc}")
    return _app
```
And update the CI comment to say "the Tailwind build step above ensures this file exists; SNOB_CI=1 is a belt-and-braces enforcement in the fixture itself."

---

### WR-03: `_require_postgres_hard` is dead code — defined but never called

**File:** `tests/test_happy_path_smoke.py:51-65`
**Issue:** `_require_postgres_hard` is defined with documentation saying "Call this guard at the top of any HARD test so SNOB_CI=1 turns that skip into a failure." But `test_happy_path_full_chain` — the only test in the file — never calls it. The docstring's promise that a Postgres-unreachable CI run will fail hard is therefore not honored by the code. If the conftest `client` fixture behavior ever changes (e.g., stops skipping silently on DB errors), this gap could allow a Postgres-less CI run to silently pass.
**Fix:** Call it at the top of `test_happy_path_full_chain`, immediately after `_require_wired`:
```python
def test_happy_path_full_chain(client) -> None:
    _require_wired("brew + catalog")
    _require_postgres_hard(client)
    # ... rest of test
```

---

### WR-04: `pytest-asyncio` is unpinned in `requirements-dev.txt`

**File:** `requirements-dev.txt:9`
**Issue:** `pytest-asyncio` has no version constraint. `pyproject.toml` (line 60) refers to "pytest-asyncio / httpx pins" in `requirements-dev.txt`, but the file only pins `pytest>=9.0,<10`. `pytest-asyncio` has a history of breaking changes: version 0.21 introduced `asyncio_mode="auto"` as a required opt-in; 0.23 changed fixture handling again. An unpinned install picks up the latest release on a fresh CI runner, and a new major or minor version could break the suite silently (collection errors or behavior changes with `asyncio_mode="auto"`).
**Fix:**
```
pytest-asyncio>=0.23,<1
```
Pin to the current stable line. Check `pypi.org/project/pytest-asyncio` for the current release and tighten the upper bound accordingly.

---

### WR-05: CWD-relative `Path()` in CI security tests silently yields zero test cases outside repo root

**File:** `tests/ci/test_csp_nonce.py:37,63-64,84`, `tests/ci/test_no_credential_dump.py:44,72`
**Issue:** Both CI security tests define their scan targets at module level using relative `Path` objects (`TEMPLATES_DIR = Path("app/templates")`, `APP_DIR = Path("app")`), evaluated at collection time relative to the process CWD. If `pytest` is run from any directory other than the repo root — including from inside the `tests/` or `tests/ci/` directories — both directories fail `.exists()` and `rglob()` returns zero items. `@pytest.mark.parametrize` with zero cases produces 0 collected tests, which pytest reports as "no tests ran" (not as a failure). Under `SNOB_CI=1` this is indistinguishable from a genuinely clean run. The CI workflow runs `python -m pytest tests/` from the repo root (GitHub Actions default CWD), so this does not affect CI today, but it will silently yield no-op results for any developer who runs `pytest` from a non-root directory.
**Fix:** Anchor the paths to the file's location using `Path(__file__)`:
```python
# test_csp_nonce.py
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "app" / "templates"

# test_no_credential_dump.py
APP_DIR = Path(__file__).parent.parent.parent / "app"
```

---

## Info

### IN-01: Tailwind binary download lacks SHA-256 integrity verification

**File:** `Dockerfile:41`, `.github/workflows/ci.yml:45-46`
**Issue:** Both the Dockerfile and CI workflow download the Tailwind standalone CLI binary via `curl -fsSL` without verifying the downloaded binary's SHA-256 digest against a known-good value. HTTPS from GitHub provides transport security but does not pin the binary to a specific expected hash. A compromised CDN or a GitHub release replacement attack would go undetected. The Tailwind project publishes checksums alongside its releases on GitHub.
**Fix:** Capture and verify the expected hash during the build. For Dockerfile:
```dockerfile
ARG TAILWIND_SHA256=<sha256 of tailwindcss-linux-x64 for v3.4.17>
RUN curl -fsSL "..." -o /usr/local/bin/tailwindcss \
    && echo "${TAILWIND_SHA256}  /usr/local/bin/tailwindcss" | sha256sum -c -
```
Repeat the pattern in `ci.yml` for the CI download step.

---

### IN-02: CI workflow has no `workflow_dispatch` trigger

**File:** `.github/workflows/ci.yml:3`
**Issue:** The workflow triggers only on `push` and `pull_request`. There is no `workflow_dispatch` entry, so CI cannot be manually triggered from the GitHub Actions UI without a commit or PR. This matters for ad-hoc re-runs (e.g., after a flaky external service recovers) and for testing the CI workflow itself.
**Fix:**
```yaml
on:
  push:
  pull_request:
  workflow_dispatch:
```

---

### IN-03: `page_at_viewport` fixture return type annotation is incorrect

**File:** `tests/e2e/conftest.py:256`
**Issue:** `page_at_viewport` is a `yield` fixture but its return annotation is `-> Page`. Yield fixtures should be annotated as `-> Iterator[Page]` (or `Generator[Page, None, None]`). With `from __future__ import annotations` at the top of the file, this is a latent mypy/pyright error rather than a runtime failure, but it produces misleading type information for callers.
**Fix:**
```python
from collections.abc import Iterator

@pytest.fixture(params=[(375, 667), (390, 844)], ids=["375x667", "390x844"])
def page_at_viewport(
    request: pytest.FixtureRequest,
    browser: Browser,
    base_url: str,
    _auth_cookies: dict[str, str],
) -> Iterator[Page]:
```

---

_Reviewed: 2026-05-23_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
