# Phase 12: Hardening + Tests — Research

**Researched:** 2026-05-23
**Domain:** Test infrastructure, CI/CD plumbing, Playwright responsive smoke, security grep audits
**Confidence:** HIGH (all key findings come from the codebase itself + established docs)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Fix root-conftest isolation so full `pytest tests/` runs green as one batch. Root cause: `fresh_db` only truncates `users`/`sessions`; phase_04 `DELETE FROM coffees` trips the RESTRICT FK on second run; `test_setup_concurrent_race` fails due to in-memory `app_settings` cache not invalidated between modules. Fix = root-conftest session/module teardown that TRUNCATEs catalog + per-user tables and clears the `app_settings` cache. Preserve the "test" in db name safety interlock verbatim.
- **D-02:** Ship gate fails on UNEXPECTED skips. Gate runs with `-rs`. Critical-path tests (TEST-01 smoke, load-bearing service tests, CSRF) must hard-require Postgres so a skip becomes a FAILURE. Planner picks exact mechanism (skip-budget assertion / env flag / allowlist); outcome is locked.
- **D-03:** Add Dockerfile dev/test multi-stage target + compose `test` profile. `docker compose run --rm test` runs the gate. Bakes `requirements-dev.txt` (add `playwright>=1.59,<2` to it). Prod image stays pytest-free.
- **D-04:** GitHub Actions full gate on push/PR: ruff + grep tests + full `pytest -rs` against a Postgres 16 service container. CI sets `DATABASE_URL`/`POSTGRES_*` so conftest `<db>_test` forcing resolves to the service container. No deploy pipeline.
- **D-05:** Playwright (Python) `>=1.59,<2` chromium headless against the running compose app. Viewports: 375x667 and 390x844. Assert: bottom nav present + functional, brew form no horizontal scroll, photo upload control present, home cards stack vertically, computed `font-size >= 16px` on every `input`/`select`/`textarea` (MX-1 iOS zoom).
- **D-06:** Playwright LOCAL / pre-deploy only — NOT in GitHub Actions.
- **D-07:** CSP + `model_dump` audits as permanent `tests/ci/` grep tests. (a) CSP grep: scan `app/templates/` for `<script>`/`<style>` lacking nonce and for `'unsafe-eval'`/`'unsafe-inline'` outside `docs/decisions/`. (b) SEC-6 grep: forbid `model_dump()` on `ApiCredential`. Follow `tests/ci/test_no_unsafe_jinja.py` idiom.
- **D-08:** Targeted README gap-fill only: restore runbook, single-worker restatement, iOS Wake-Lock caveat, `/sw.js` `Cache-Control: no-cache` note. Do not break `tests/docs/test_readme_nginx.py` or `tests/test_env_example.py`.

### Claude's Discretion

- TEST-01 smoke construction — end-to-end: setup → create coffee → create equipment → create recipe → log session → GET / renders all sections. Hard test (require Postgres per D-02).
- D-01 teardown mechanism — TRUNCATE list + ordering (respect RESTRICT FK on `coffees`/`brew_sessions`).
- D-02 skip-enforcement mechanism — skip-budget assertion vs CI env flag vs allowlist.
- Playwright auth + seeding — programmatic `/setup` + form POSTs or seed step in compose `test` profile.
- CSP grep strictness — exact regex for nonce-on-script/style and unsafe-* allowlist.
- GitHub Actions matrix/caching detail — single job, Python 3.12, pip cache.

### Deferred Ideas (OUT OF SCOPE)

- G-01 VPS-volume `chown` deploy fix — deploy-time ops, not test/hardening scope (note in README only).
- Full per-router test coverage.
- `filterwarnings = ["error"]` in pytest — optional if suite is clean; not a phase requirement.
- Playwright in GitHub Actions.
- Phase 11 manual UAT gate.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TEST-01 | Pytest smoke: create user → create coffee → create equipment → create recipe → log session → view home page renders | Extend `tests/test_phase02_smoke.py` setup+CSRF+session idiom; reuse `seeded_admin_user` fixture; requires D-01 isolation fix first |
| TEST-02 | Unit tests for `services/ai_service.py` signature computation + provider fallback logic | Already exists in `tests/services/test_ai_service.py` — VERIFY coverage, fill named gaps only |
| TEST-03 | Unit tests for `services/encryption.py` round-trip + MultiFernet key rotation | Already exists in `tests/services/test_encryption.py` — VERIFY coverage only |
| TEST-04 | Unit tests for `services/analytics.py` queries against seeded test DB | Already exists in `tests/services/test_analytics.py` + `test_analytics_perf.py` — VERIFY coverage only |
| TEST-05 | Unit tests for CSRF middleware (positive + negative) | Already exists in `tests/middleware/test_csrf.py` + `test_csrf_form_shim.py` — VERIFY coverage only |
| TEST-06 | Playwright responsive smoke at 375x667 and 390x844 viewports | Zero playwright in repo — fully net-new; `playwright>=1.59,<2` in `requirements-dev.txt` |

</phase_requirements>

---

## Summary

Phase 12 is a ship-readiness gate, not a test-building phase. Phases 0-11 already shipped ~70 test files covering the bulk of TEST-02..05. The work is: (1) fix the one known full-suite isolation gap (T-INFRA-1 / D-01) so `pytest tests/` runs green as a single batch, (2) add a skip-enforcement gate so green can't be hollow, (3) build the TEST-01 happy-path smoke and the TEST-06 Playwright responsive smoke (both are net-new), (4) add two SEC/CSP grep tests under `tests/ci/` (net-new), (5) stand up the Dockerfile dev stage + compose `test` profile + GitHub Actions workflow, and (6) fill four named README gaps.

The critical dependency ordering is: D-01 (isolation fix) must land before TEST-01 smoke is meaningful, because the smoke's catalog entities will collide with phase_04 fixtures if cross-module pollution isn't resolved first. D-03 (dev image) must land before D-04 (CI) so Actions uses the same image.

The two most technically novel items for the planner are the D-01 TRUNCATE ordering (catalog FK graph must be respected) and the D-05 Playwright computed-style assertion pattern (requires `page.evaluate()` to read `getComputedStyle`, not just DOM presence checks).

**Primary recommendation:** Wave the work in this order — D-01 isolation fix → D-02 skip enforcement → TEST-01 smoke → D-07 grep tests → D-03 dev image → D-04 CI → D-05/D-06 Playwright → D-08 README.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Full-suite isolation (D-01) | Test infrastructure | — | Root conftest teardown; no app-tier change |
| Skip gate enforcement (D-02) | Test infrastructure | CI | conftest fixture + pyproject.toml addopts or env flag |
| Dev/test Docker stage (D-03) | Container build | compose profiles | New Dockerfile stage; prod stage untouched |
| GitHub Actions CI (D-04) | CI pipeline | Container build | Shares dev image; no deploy path |
| Playwright responsive smoke (D-05) | E2E / browser | compose test profile | Against running app stack; local only |
| CSP + model_dump grep tests (D-07) | Test infrastructure (static analysis) | — | `tests/ci/` idiom; runs in CI |
| README gap-fill (D-08) | Documentation | — | Surgical edits; existing doc tests guard regressions |

---

## Standard Stack

### Core (already in requirements-dev.txt — verify/confirm only)

| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| pytest | `>=9.0,<10` | Test runner | Already in requirements-dev.txt |
| pytest-asyncio | unpinned | Async test support | Already in requirements-dev.txt |
| respx | unpinned | HTTP mock for httpx (AI service tests) | Already in requirements-dev.txt |
| pytest-cov | unpinned | Coverage reporting | Already in requirements-dev.txt |
| httpx | `>=0.28,<0.29` | ASGI test client (in requirements.txt) | Already present |

### Net-New (must be added)

| Library | Version | Purpose | Where |
|---------|---------|---------|-------|
| playwright (Python) | `>=1.59,<2` | Headless browser for D-05 | Add to requirements-dev.txt |

**playwright install note:** [ASSUMED] After `pip install playwright`, the browser binary is installed separately via `playwright install chromium`. In the Dockerfile dev stage, this means a `RUN playwright install chromium --with-deps` step after `pip install -r requirements-dev.txt`. The `--with-deps` flag installs OS-level dependencies (libglib, libfontconfig, etc.) needed in the debian:bookworm-slim base. Without it, chromium silently fails to launch inside the container.

### Version verification

```bash
# Run in the web container or dev environment
pip show playwright pytest pytest-asyncio respx
```

[VERIFIED: requirements-dev.txt] Current dev deps: pytest `>=9.0,<10`, pytest-asyncio (unpinned), respx (unpinned), pytest-cov (unpinned). playwright not yet present.

---

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  LOCAL / pre-deploy                                             │
│                                                                 │
│  docker compose run --rm test                                   │
│    └─ dev image (requirements-dev.txt baked)                    │
│         ├─ ruff check / format (lint gate)                      │
│         ├─ pytest tests/ -rs (full suite, no -x)                │
│         │    ├─ tests/ci/   (grep audits — no Postgres needed)  │
│         │    ├─ tests/      (unit + integration — Postgres)     │
│         │    └─ tests/e2e/  (excluded from default run — D-06)  │
│         └─ pytest tests/e2e/ (Playwright, separate invocation)  │
│              └─ targets http://coffee-snobbery:8000             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  GITHUB ACTIONS (push/PR)                                       │
│                                                                 │
│  services: postgres:16-alpine                                   │
│    └─ DATABASE_URL=postgresql+psycopg://test:test@localhost/    │
│         snobbery_test                                           │
│  steps:                                                         │
│    1. ruff format --check + ruff check                          │
│    2. pytest tests/ -rs  (excludes tests/e2e/)                  │
│       └─ conftest forces snobbery_test DB on service container  │
└─────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure (new files only)

```
.github/
└── workflows/
    └── ci.yml                  # D-04: Actions full gate

tests/
├── ci/
│   ├── test_no_unsafe_jinja.py  # EXISTS — |safe + hx-on: grep
│   ├── test_csp_nonce.py        # NET-NEW D-07a: <script>/<style> nonce grep
│   └── test_no_credential_dump.py # NET-NEW D-07b: model_dump on ApiCredential
├── e2e/
│   ├── conftest.py              # NET-NEW: Playwright fixtures (page, viewport)
│   └── test_responsive_smoke.py # NET-NEW D-05/TEST-06
└── test_happy_path_smoke.py     # NET-NEW TEST-01

Dockerfile                       # D-03: add dev/test stage
docker-compose.yml               # D-03: add test profile
requirements-dev.txt             # add playwright>=1.59,<2
```

### Pattern 1: Full-Suite Isolation Teardown (D-01)

**What:** Session-scoped teardown in root `conftest.py` that runs after each test module and TRUNCATEs catalog + brew tables in FK-safe order, then clears the `app_settings` in-memory cache.

**The FK graph to respect (RESTRICT constraints):**
- `brew_sessions.coffee_id → coffees.id` (RESTRICT) — must delete brew_sessions before coffees
- `brew_sessions.bag_id → bags.id` — must delete brew_sessions before bags
- `bags.coffee_id → coffees.id` — must delete bags before coffees
- `brew_sessions.user_id → users.id` — handled by existing fresh_db users DELETE (cascade)

**Safe TRUNCATE order:**
```sql
-- In a single transaction, within a module-scoped teardown:
TRUNCATE brew_sessions RESTART IDENTITY CASCADE;
TRUNCATE bags RESTART IDENTITY CASCADE;
TRUNCATE coffees RESTART IDENTITY CASCADE;
TRUNCATE equipment RESTART IDENTITY CASCADE;
TRUNCATE recipes RESTART IDENTITY CASCADE;
TRUNCATE roasters RESTART IDENTITY CASCADE;
TRUNCATE flavor_notes RESTART IDENTITY CASCADE;
-- DO NOT cascade on users — that wipes app_settings.updated_by FK (SET NULL)
-- and resets the 19-row seeded app_settings (existing fresh_db handles users)
```

**app_settings cache fix:** [ASSUMED] The `app_settings` `setup_completed` row is updated to `'false'` by `fresh_db` already. The `test_setup_concurrent_race` failure is an in-memory cache (`app_settings` service-level cache, not DB). The fix is to call the cache-invalidation path (likely `settings_service.invalidate()` or equivalent) in the teardown, OR to use `monkeypatch` to reset the cached flag between modules. The exact symbol name must be verified in `app/services/settings.py`.

**Pattern:**
```python
# root conftest.py — module-scoped autouse fixture (or session-scoped with
# pytest_runtest_teardown hook if module scope isn't granular enough)
@pytest.fixture(scope="module", autouse=True)
def _reset_catalog_tables() -> Iterator[None]:
    yield
    # teardown after each module
    if not _postgres_reachable():
        return
    try:
        from app.config import settings as _s
        active_db = urlparse(_s.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")).path.lstrip("/")
    except Exception:
        return
    if "test" not in active_db.lower():
        return
    from app.db import engine
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE brew_sessions RESTART IDENTITY CASCADE"))
        conn.execute(text("TRUNCATE bags RESTART IDENTITY CASCADE"))
        conn.execute(text("TRUNCATE coffees RESTART IDENTITY CASCADE"))
        conn.execute(text("TRUNCATE equipment RESTART IDENTITY CASCADE"))
        conn.execute(text("TRUNCATE recipes RESTART IDENTITY CASCADE"))
        conn.execute(text("TRUNCATE roasters RESTART IDENTITY CASCADE"))
        conn.execute(text("TRUNCATE flavor_notes RESTART IDENTITY CASCADE"))
    # Clear in-memory app_settings cache if it exists
    try:
        import app.services.settings as _svc
        if hasattr(_svc, "invalidate_settings_cache"):
            _svc.invalidate_settings_cache()
    except Exception:
        pass
```

[ASSUMED — exact cache invalidation symbol] The function name must be verified against `app/services/settings.py` before implementation.

### Pattern 2: Skip Enforcement Gate (D-02)

**Three viable mechanisms** — planner picks one:

**Option A: `SNOB_CI=1` env flag** (recommended for simplicity)

```python
# In conftest.py, at the top of any hard-require check:
import os
_CI_MODE = os.environ.get("SNOB_CI") == "1"

def _require_postgres(reason: str) -> None:
    """In CI mode, fail immediately instead of skipping."""
    if _CI_MODE:
        pytest.fail(f"SNOB_CI=1 but Postgres unreachable: {reason}")
    else:
        pytest.skip(reason)
```

The compose `test` service and the Actions workflow both set `SNOB_CI=1`. Host-only unit runs (no `SNOB_CI`) still skip cleanly.

**Option B: Skip-budget assertion** — a session-scoped fixture that counts skips and fails if count > N (too brittle — N changes as tests are added).

**Option C: Allowlist** — a known-skip registry (more complex than Option A, equivalent result).

**Recommendation:** Option A (env flag). It's the same pattern used by several projects in the Python ecosystem for distinguishing local dev from CI runs. [ASSUMED]

### Pattern 3: Dockerfile Dev/Test Stage (D-03)

```dockerfile
# Stage 3: Dev/test — extends runtime with test tooling
FROM runtime AS dev

USER root
# Install playwright system deps (chromium needs libglib, etc.)
RUN pip install playwright>=1.59,<2 && playwright install chromium --with-deps

# Install the rest of dev deps (pytest, ruff, respx, etc.)
COPY requirements-dev.txt ./
RUN pip install -r requirements-dev.txt

USER app
# Override entrypoint for test runs
ENTRYPOINT ["python", "-m", "pytest"]
CMD ["tests/", "-rs", "--tb=short"]
```

[ASSUMED] The `--with-deps` flag on `playwright install` handles OS-level browser deps in the container. The exact apt packages it installs (libglib2.0-0, etc.) are managed by the playwright installer. Confirmed this is the documented pattern for CI/Docker use. [ASSUMED: exact playwright Dockerfile invocation — verify against https://playwright.dev/python/docs/docker]

**Compose `test` profile:**
```yaml
  coffee-snobbery-test:
    build:
      context: .
      dockerfile: Dockerfile
      target: dev
    profiles: [test]
    depends_on:
      coffee-snobbery-db:
        condition: service_healthy
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@coffee-snobbery-db:5432/${POSTGRES_DB}
      SNOB_CI: "1"
    networks:
      - coffee-snobbery-net
    volumes:
      - .:/app  # source bind-mount for test runs (not needed in prod)
```

[ASSUMED] The `profiles: [test]` key ensures `docker compose up -d` (no profile) never starts the test container. `docker compose run --rm test coffee-snobbery-test` (or via the profile) runs the gate.

### Pattern 4: GitHub Actions Postgres 16 Service Container (D-04)

[ASSUMED: GitHub Actions service container wiring — standard, stable pattern]

```yaml
# .github/workflows/ci.yml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: snobbery
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-timeout 3s
          --health-retries 10
        ports:
          - 5432:5432

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install deps
        run: pip install -r requirements-dev.txt

      - name: Ruff format check
        run: ruff format --check .

      - name: Ruff lint
        run: ruff check .

      - name: Pytest full suite
        env:
          DATABASE_URL: postgresql+psycopg://test:test@localhost:5432/snobbery
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: snobbery
          APP_SECRET_KEY: ${{ secrets.APP_SECRET_KEY || 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' }}
          APP_ENCRYPTION_KEY: ${{ secrets.APP_ENCRYPTION_KEY || '0123456789abcdef0123456789abcdef0123456789a=' }}
          SNOB_CI: "1"
        run: python -m pytest tests/ -rs --tb=short --ignore=tests/e2e
```

**Critical conftest integration:** The conftest `DATABASE_URL` forcing logic already handles this correctly. When `DATABASE_URL=.../snobbery` is set in CI, the conftest detects `"test"` is NOT in `"snobbery"` and rewrites it to `snobbery_test`. The conftest then calls `_provision_test_db()` which runs `alembic upgrade head` against `snobbery_test`. This means the Actions job needs no migration step — conftest handles it. [VERIFIED: conftest.py lines 51-64]

**Why `--ignore=tests/e2e`:** Playwright tests need the running app stack (D-06 — local only). Excluding the dir keeps CI fast without needing markers.

### Pattern 5: Playwright Responsive Smoke (D-05)

[ASSUMED: Playwright Python API — stable since 1.20+, verified against training knowledge of 1.59]

```python
# tests/e2e/conftest.py
import pytest
from playwright.sync_api import sync_playwright, Browser, Page

@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        yield browser
        browser.close()

@pytest.fixture(params=[(375, 667), (390, 844)], ids=["375x667", "390x844"])
def page_at_viewport(browser: Browser, request):
    """Yield a Page at the parametrized viewport size."""
    width, height = request.param
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    yield page
    context.close()
```

**Computed font-size assertion (MX-1 — iOS zoom prevention):**
```python
def test_input_font_size_no_ios_zoom(page_at_viewport: Page):
    """Every input/select/textarea must have computed font-size >= 16px."""
    # Navigate to brew form (requires auth — see auth setup below)
    page_at_viewport.goto("http://localhost:8080/brew/new")
    
    violations = page_at_viewport.evaluate("""() => {
        const els = document.querySelectorAll('input, select, textarea');
        const violations = [];
        for (const el of els) {
            const fs = parseFloat(getComputedStyle(el).fontSize);
            if (fs < 16) {
                violations.push({
                    tag: el.tagName,
                    id: el.id,
                    name: el.name,
                    fontSize: fs
                });
            }
        }
        return violations;
    }""")
    assert violations == [], f"iOS-zoom violations (font-size < 16px): {violations}"
```

**No-horizontal-scroll assertion:**
```python
def test_brew_form_no_horizontal_scroll(page_at_viewport: Page):
    page_at_viewport.goto("http://localhost:8080/brew/new")
    scroll_width = page_at_viewport.evaluate("document.documentElement.scrollWidth")
    client_width = page_at_viewport.evaluate("document.documentElement.clientWidth")
    assert scroll_width <= client_width, (
        f"Horizontal scroll at {page_at_viewport.viewport_size}: "
        f"scrollWidth={scroll_width} > clientWidth={client_width}"
    )
```

**Bottom nav assertion:**
```python
def test_bottom_nav_present(page_at_viewport: Page):
    page_at_viewport.goto("http://localhost:8080/")
    nav = page_at_viewport.locator("nav[data-testid='bottom-nav'], nav.bottom-nav, [class*='bottom'][class*='nav']").first
    # Fallback: look for the nav that's only visible at mobile widths
    assert nav.is_visible(), "Bottom nav not visible at mobile viewport"
    bbox = nav.bounding_box()
    assert bbox is not None
    # Must be near the bottom of the viewport
    assert bbox["y"] > page_at_viewport.viewport_size["height"] * 0.7, (
        "Bottom nav not in lower 30% of viewport"
    )
```

**Auth seeding for Playwright:** The smoke needs an authenticated session. Simplest pattern: use the app's `/setup` endpoint at the start of the test session to create a user, then POST to `/login`, store the session cookie, and use it across all page navigations. This mirrors `test_phase02_smoke.py`. The Playwright `browser_context` stores cookies automatically between requests.

### Pattern 6: CI Grep Tests (D-07)

**CSP nonce grep (clone of `test_no_unsafe_jinja.py`):**

```python
# tests/ci/test_csp_nonce.py
"""D-07a: Every <script> and <style> tag in app/templates/ must carry a nonce attribute.
   No 'unsafe-eval' or 'unsafe-inline' outside documented trade-offs in docs/decisions/.
"""
import re
from pathlib import Path

import pytest

TEMPLATES_DIR = Path("app/templates")
DECISIONS_DIR = Path("docs/decisions")

# Patterns that MUST be absent (outside documented exceptions)
UNSAFE_DIRECTIVES = re.compile(r"'unsafe-eval'|'unsafe-inline'")

# <script> or <style> tag that lacks nonce="{{ ... }}"
SCRIPT_WITHOUT_NONCE = re.compile(
    r'<(script|style)(?![^>]*\bnonce\s*=)[^>]*>',
    re.IGNORECASE,
)

_JINJA_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

def _strip_comments(src: str) -> str:
    src = _JINJA_COMMENT.sub("", src)
    src = _HTML_COMMENT.sub("", src)
    return src

@pytest.mark.parametrize(
    "template_path",
    list(TEMPLATES_DIR.rglob("*.html")) if TEMPLATES_DIR.exists() else [],
)
def test_script_style_has_nonce(template_path: Path) -> None:
    raw = template_path.read_text(encoding="utf-8")
    scannable = _strip_comments(raw)
    match = SCRIPT_WITHOUT_NONCE.search(scannable)
    assert not match, (
        f"{template_path}: <{match.group(1)}> tag lacks nonce attribute (SEC-02). "
        f"Matched: {match.group(0)!r}"
    )
```

**model_dump grep (SEC-6):**

```python
# tests/ci/test_no_credential_dump.py
"""SEC-6: model_dump() must never be called on ApiCredential.
   The decrypted key must never enter a serializable model dict.
"""
import re
from pathlib import Path
import pytest

APP_DIR = Path("app")

# Look for model_dump() calls in files that import or reference ApiCredential
MODEL_DUMP_PATTERN = re.compile(r"\bmodel_dump\s*\(")

@pytest.mark.parametrize(
    "source_path",
    [p for p in APP_DIR.rglob("*.py") if p.exists()] if APP_DIR.exists() else [],
)
def test_no_api_credential_model_dump(source_path: Path) -> None:
    src = source_path.read_text(encoding="utf-8")
    if "ApiCredential" not in src and "api_credential" not in src.lower():
        return  # file doesn't touch credentials — skip
    match = MODEL_DUMP_PATTERN.search(src)
    assert not match, (
        f"{source_path}: model_dump() called in a file that references ApiCredential. "
        f"Decrypted keys must never enter a serializable dict (SEC-6). "
        f"Line: {src[:match.start()].count(chr(10)) + 1}"
    )
```

[ASSUMED] The exact strictness of the CSP nonce regex depends on the actual base template. If `base.html` uses Jinja expressions like `nonce="{{ csp_nonce }}"`, the regex `nonce\s*=` will match correctly. If the app uses a different pattern, the regex needs adjustment. Verify against `app/templates/base.html`.

### Anti-Patterns to Avoid

- **Re-implementing existing tests:** Do NOT rewrite `test_ai_service.py`, `test_encryption.py`, `test_analytics.py`, or `test_csrf.py` from scratch. Verify coverage; add gaps only.
- **Cascade-TRUNCATEing users:** The current `fresh_db` correctly avoids `TRUNCATE users CASCADE` because that wipes `app_settings.updated_by_user_id` (SET NULL FK) and resets the 19-row app_settings seed. The new catalog teardown must mirror this discipline. [VERIFIED: conftest.py comment lines 335-342]
- **`-x` in the ship gate:** The current `pyproject.toml` `addopts = "-x --tb=short"` stops at first failure. The gate run wants `-rs --tb=short` (no `-x`) so all failures surface at once. Override via CLI or create a separate `pytest.ini`/`override addopts` for the gate command.
- **Playwright in CI:** D-06 is explicit — no Playwright in Actions. The `tests/e2e/` directory must be excluded from the Actions `pytest` invocation.
- **`unsafe-inline` allowlist assumption:** Do not assume the CSP grep will pass clean. If there are `<script>` tags without nonces in templates, those are real findings to fix. Do not soften the test.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Headless browser assertions | Custom screenshot diffing or HTML string parsing | `playwright.sync_api` `evaluate()`, `bounding_box()`, `is_visible()` | Playwright gives computed layout truth; string parsing can't |
| HTTP mocking for AI service tests | Custom `monkeypatch` httpx transport | `respx` (already in requirements-dev.txt) | Already the project pattern; consistent |
| Postgres service in CI | docker-in-docker or separate compose | GitHub Actions `services:` block | Native support; no extra complexity |
| Browser dependency management in Docker | Manual apt package list | `playwright install chromium --with-deps` | Playwright manages its own OS deps |

---

## Common Pitfalls

### Pitfall 1: TRUNCATE CASCADE on app_settings FK
**What goes wrong:** `TRUNCATE users CASCADE` wipes `app_settings` rows because `updated_by_user_id` is a FK. `test_migrations.py::test_app_settings_seeded_with_19_rows` fails.
**Why it happens:** Postgres `CASCADE` truncates all referencing tables, not just the declared cascade-delete chain. The FK is `ON DELETE SET NULL`, not `CASCADE`, but `TRUNCATE CASCADE` ignores that.
**How to avoid:** Use `DELETE FROM users` (not TRUNCATE) for the users table, preserving existing `fresh_db` behavior. Only use TRUNCATE for the catalog tables that have no `app_settings` FKs.
**Warning signs:** `test_app_settings_seeded_with_19_rows` fails after the isolation fix lands.
[VERIFIED: conftest.py comment lines 335-342 documents this exact issue]

### Pitfall 2: app.main import skip masking the gate
**What goes wrong:** The `app` fixture in conftest catches `RuntimeError` (Tailwind CSS missing) and issues `pytest.skip()`. In CI with the baked dev image, the Tailwind CSS IS present — but if the dev stage copies source before running the Tailwind build, the hash file won't exist, and the whole test suite skips silently.
**Why it happens:** The dev stage must either copy the compiled Tailwind CSS from the `tailwind-builder` stage or run the Tailwind build as part of the dev stage build step.
**How to avoid:** In the Dockerfile dev stage, `COPY --from=tailwind-builder` the compiled CSS, same as the runtime stage does.
**Warning signs:** In CI, pytest reports 0 tests collected or all tests skipped.

### Pitfall 3: conftest DATABASE_URL rewriting in CI
**What goes wrong:** CI sets `DATABASE_URL=postgresql+psycopg://test:test@localhost:5432/snobbery`. The conftest rewrites this to `snobbery_test`. The `_provision_test_db` fixture then tries to `CREATE DATABASE snobbery_test` on the service container, which works — but if `alembic.ini` points to the wrong URL or uses a relative path, migrations fail silently and tests skip.
**How to avoid:** Confirm `alembic.ini` uses `%(DATABASE_URL)s` interpolation (or equivalent) and not a hardcoded URL. The conftest already passes `Config("alembic.ini")` — so the env var must be set before alembic runs.
**Warning signs:** `_provision_test_db` silently passes but schema tables are absent; all DB-dependent tests skip.

### Pitfall 4: Playwright chromium headless mode + compute style
**What goes wrong:** `page.evaluate("getComputedStyle(el).fontSize")` returns an empty string for elements that aren't rendered (e.g., hidden behind auth gate, not yet in DOM).
**How to avoid:** Ensure the Playwright smoke authenticates first, navigates to the actual page, and waits for the specific elements before querying computed style. Use `page.wait_for_selector("input")` before the `evaluate()` call.
**Warning signs:** Font-size assertions return `""` or `"0px"` for all elements.

### Pitfall 5: `-x` flag conflict with gate semantics
**What goes wrong:** The current `pyproject.toml` `addopts = "-x --tb=short"` stops at first failure. The gate command needs `-rs` and no `-x` to surface all failures at once. But if the gate command doesn't override addopts, the `-x` persists.
**How to avoid:** The `docker compose run --rm test` command (or the Actions step) passes explicit flags: `python -m pytest tests/ -rs --tb=short --ignore=tests/e2e`. pytest CLI flags override `addopts`. Alternatively, update `addopts` in `pyproject.toml` to just `--tb=short` and pass `-x` explicitly when desired.
[ASSUMED: pytest CLI flags override addopts — standard pytest behavior]

### Pitfall 6: skip-as-green masking in test_nav.py
**What goes wrong:** `tests/test_nav.py` wraps all 5 tests in `_require_nav_wired()` which issues `pytest.skip` on config_hub import error. In CI with `SNOB_CI=1`, the skip-enforcement gate will convert this to a FAILURE — which is correct, but it may surface a real import issue that was previously hidden.
**How to avoid:** After D-02 is implemented, run the full suite with `SNOB_CI=1` in the dev container first. Any skip that becomes a failure reveals a real gap to fix before enabling CI.
[VERIFIED: memory `test-nav-require-wired-skip-guard`]

---

## Code Examples

### Existing grep test idiom (D-07 template)
```python
# Source: tests/ci/test_no_unsafe_jinja.py (VERIFIED)
# Key structure: TEMPLATES_DIR.rglob("*.html") parametrized, _strip_comments(), pattern.search()
# Clone this exact structure for CSP nonce and model_dump tests
TEMPLATES_DIR = Path("app/templates")

@pytest.mark.parametrize(
    "template_path",
    list(TEMPLATES_DIR.rglob("*.html")) if TEMPLATES_DIR.exists() else [],
)
def test_template_safety(template_path: Path) -> None:
    raw = template_path.read_text(encoding="utf-8")
    scannable = _strip_comments(raw)
    for pattern, message in FORBIDDEN_PATTERNS:
        match = pattern.search(scannable)
        assert not match, f"{template_path}: {message}"
```

### conftest safety interlock (preserve verbatim in D-01 teardown)
```python
# Source: tests/conftest.py lines 324-331 (VERIFIED)
# MUST replicate this guard in the new catalog teardown:
if "test" not in _active_db.lower():
    yield  # refuse to mutate non-test database
    return
```

### pyproject.toml addopts override strategy
```toml
# Current (pyproject.toml line 39 — VERIFIED):
addopts = "-x --tb=short"

# Gate command overrides -x by passing explicit flags.
# pytest CLI: later flags win over addopts for most options,
# but for addopts the behavior is additive for some flags.
# Safest: change to just "--tb=short" and pass -x/-rs explicitly.
```

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Per-phase isolated test runs only | Full-suite green (D-01) | Honest baseline; cross-module pollution caught |
| Manual `pip install pytest` in container | Baked dev image (D-03) | Reproducible; eliminates `docker cp` footgun |
| No CI | GitHub Actions gate (D-04) | Regression net on every push |
| Skip-as-green | Skip-fails-gate with `SNOB_CI=1` (D-02) | Eliminates hollow green |
| No Playwright | Playwright responsive smoke (D-05/TEST-06) | Real layout + computed style truth |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `playwright install chromium --with-deps` handles all OS-level browser deps in debian:bookworm-slim | Pattern 3, Common Pitfalls | Dev image build fails; need manual apt installs |
| A2 | `SNOB_CI=1` env flag approach for skip enforcement (recommended) | Pattern 2 | Planner may prefer allowlist or budget; outcome is locked regardless |
| A3 | pytest CLI flags `-rs` override `addopts = "-x"` behavior (additive not replacing for some flags) | Pitfall 5 / Pattern 3 | Gate may still stop at first failure; safest fix is to remove `-x` from addopts |
| A4 | `page.evaluate("getComputedStyle(el).fontSize")` works for DOM-rendered elements in Playwright Python sync API | Pattern 5 | Need to use `locator.evaluate()` instead; API may differ slightly |
| A5 | The `app_settings` cache is invalidatable via a function in `app/services/settings.py` | Pattern 1 | May need different reset strategy; verify exact symbol before implementing |
| A6 | The `test_setup_concurrent_race` failure is caused by in-memory `app_settings.setup_completed` cache not invalidated between test modules | D-01 description | Root cause may be different; requires verification in `app/services/setup.py` |
| A7 | `alembic.ini` uses env-var interpolation for DATABASE_URL (not hardcoded) | Pitfall 3 | CI migrations fail silently; alembic.ini must be checked |

---

## Open Questions

1. **Exact `app_settings` cache invalidation symbol**
   - What we know: the `test_setup_concurrent_race` failure is documented as an in-memory cache issue (T-INFRA-1); `fresh_db` already resets the DB row
   - What's unclear: the exact function/attribute to call in `app/services/settings.py` to flush the in-memory cache
   - Recommendation: planner must read `app/services/settings.py` before writing the teardown; look for a module-level dict or a `@functools.lru_cache` that caches `setup_completed`

2. **`alembic.ini` DATABASE_URL source**
   - What we know: conftest calls `Config("alembic.ini")` and the env var is already set
   - What's unclear: whether `alembic.ini` uses `%(here)s` or a literal URL vs env interpolation
   - Recommendation: planner reads `alembic.ini` before writing the CI workflow; if it's hardcoded, the CI workflow needs an extra `alembic.ini` patch step

3. **Bottom nav selector for Playwright**
   - What we know: Phase 11 added the bottom nav (`MOB-01`); it's template-level HTML
   - What's unclear: the exact CSS class or `data-testid` attribute on the bottom nav element
   - Recommendation: planner reads `app/templates/base.html` or the nav fragment to confirm the selector before writing the Playwright test

4. **`tests/e2e/` exclusion from default pytest run**
   - What we know: D-06 says exclude from Actions; `--ignore=tests/e2e` is the pytest mechanism
   - What's unclear: whether a pytest `conftest.py` marker approach or a separate `testpaths` override is cleaner
   - Recommendation: `--ignore=tests/e2e` in the CI command + README runbook is sufficient; no need for markers

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL 16 | D-01/D-02/TEST-01..05 | In compose stack | 16-alpine | — (required) |
| Docker Compose | D-03 gate | Standard dev requirement | v2 | — |
| GitHub Actions | D-04 | Remote repo exists | — | — |
| playwright Python | TEST-06 / D-05 | NOT in requirements-dev.txt | — | Must add |
| ruff | D-04 lint gate | In requirements-dev.txt | `>=0.15.13,<0.16` | — |

**Missing dependencies:**
- `playwright>=1.59,<2` — must be added to `requirements-dev.txt` before D-03/D-05 work

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.x (`>=9.0,<10`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `python -m pytest tests/ci/ tests/middleware/test_csrf.py -rs --tb=short` |
| Full suite command | `python -m pytest tests/ -rs --tb=short --ignore=tests/e2e` |
| Playwright command | `python -m pytest tests/e2e/ -rs --tb=short` (local only) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TEST-01 | Happy-path: setup → coffee → equipment → recipe → session → home | smoke/integration | `pytest tests/test_happy_path_smoke.py -rs -x` | ❌ Wave 0 |
| TEST-02 | ai_service signature + provider fallback | unit | `pytest tests/services/test_ai_service.py -rs` | ✅ verify coverage |
| TEST-03 | encryption round-trip + MultiFernet rotation | unit | `pytest tests/services/test_encryption.py -rs` | ✅ verify coverage |
| TEST-04 | analytics queries (top coffees, sweet spots, freshness) | unit/integration | `pytest tests/services/test_analytics.py tests/services/test_analytics_perf.py -rs` | ✅ verify coverage |
| TEST-05 | CSRF middleware positive + negative | unit | `pytest tests/middleware/test_csrf.py tests/middleware/test_csrf_form_shim.py -rs` | ✅ verify coverage |
| TEST-06 | Playwright 375x667 + 390x844: nav, no-scroll, font-size | e2e | `pytest tests/e2e/ -rs` (local only) | ❌ Wave 0 |
| D-01 | Full suite isolation (cross-module catalog teardown) | infrastructure | `pytest tests/ -rs --ignore=tests/e2e` (all green) | ❌ Wave 0 (root conftest change) |
| D-02 | Skip gate: SNOB_CI=1 turns skips to failures | infrastructure | `SNOB_CI=1 pytest tests/ -rs --ignore=tests/e2e` | ❌ Wave 0 (conftest change) |
| D-07a | CSP: every `<script>`/`<style>` has nonce | static grep | `pytest tests/ci/test_csp_nonce.py -rs` | ❌ Wave 0 |
| D-07b | SEC-6: no `model_dump()` on ApiCredential | static grep | `pytest tests/ci/test_no_credential_dump.py -rs` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/ci/ -rs --tb=short` (grep tests; no Postgres needed; fast)
- **Per wave merge:** `pytest tests/ -rs --tb=short --ignore=tests/e2e` (full suite)
- **Phase gate:** Full suite green with `SNOB_CI=1` + Playwright smoke local before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_happy_path_smoke.py` — covers TEST-01
- [ ] Root `tests/conftest.py` module-scoped catalog teardown — covers D-01
- [ ] `SNOB_CI` skip-enforcement in root conftest — covers D-02
- [ ] `tests/ci/test_csp_nonce.py` — covers D-07a
- [ ] `tests/ci/test_no_credential_dump.py` — covers D-07b
- [ ] `tests/e2e/__init__.py` + `tests/e2e/conftest.py` + `tests/e2e/test_responsive_smoke.py` — covers TEST-06
- [ ] `playwright>=1.59,<2` in `requirements-dev.txt`
- [ ] Dockerfile `dev` stage — covers D-03
- [ ] `docker-compose.yml` `test` profile — covers D-03
- [ ] `.github/workflows/ci.yml` — covers D-04

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | yes | Existing Pydantic schemas; test_schemas_form_validation.py already covers |
| V6 Cryptography | yes | test_encryption.py covers MultiFernet; D-07b grep prevents key leakage |
| V1 Architecture | yes | CSP nonce grep (D-07a) validates architectural constraint on every CI run |

### Phase-Specific Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| `model_dump()` leaks decrypted API key into logs/JSON | Information Disclosure | D-07b grep test; permanent CI gate |
| `<script>` without nonce bypasses CSP | Tampering / XSS | D-07a grep test; permanent CI gate |
| Skip-as-green masks security test failures | Repudiation | D-02 `SNOB_CI=1` flag; skips become failures in the gate |

---

## Sources

### Primary (HIGH confidence)
- `tests/conftest.py` (VERIFIED in this session) — safety interlock, fresh_db, seeded fixtures, TRUNCATE comment
- `tests/ci/test_no_unsafe_jinja.py` (VERIFIED) — grep test idiom
- `pyproject.toml` (VERIFIED) — addopts `-x --tb=short`, asyncio_mode
- `Dockerfile` (VERIFIED) — multi-stage structure, tailwind-builder, runtime stage
- `docker-compose.yml` (VERIFIED) — services, volumes, network names
- `requirements-dev.txt` (VERIFIED) — current dev deps (no playwright)
- `.planning/phases/12-hardening-tests/12-CONTEXT.md` (VERIFIED) — all locked decisions
- `.planning/REQUIREMENTS.md` (VERIFIED) — TEST-01..06 verbatim

### Secondary (MEDIUM confidence)
- Project memory entries (VERIFIED in context) — `full-suite-test-isolation-gaps`, `tests-pass-by-skip-mask-green`, `test-nav-require-wired-skip-guard`, `docker-cp-into-container-nesting`, `sw-stale-cache-confounds-ui-verify`

### Tertiary (LOW / ASSUMED — training knowledge)
- Playwright Python Docker install pattern (`playwright install chromium --with-deps`) — [ASSUMED; A1]
- GitHub Actions `services:` Postgres 16 wiring — [ASSUMED; A3; well-established pattern]
- pytest `-rs` flag semantics and addopts override behavior — [ASSUMED; A3]

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all deps verified from requirements files
- Architecture: HIGH — codebase read directly; patterns derived from existing code
- Pitfalls: HIGH for Pitfalls 1-2 (documented in conftest comments + memory); MEDIUM for 3-6 (training knowledge + evidence from memories)
- GitHub Actions CI wiring: MEDIUM — standard stable pattern, not verified in this session

**Research date:** 2026-05-23
**Valid until:** 2026-06-23 (stable tech stack; test infra patterns don't change rapidly)
