# Phase 12: Hardening + Tests - Pattern Map

**Mapped:** 2026-05-23
**Files analyzed:** 10 new/modified files
**Analogs found:** 8 / 10 (2 net-new with no in-repo analog)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `tests/test_happy_path_smoke.py` | test (smoke/integration) | request-response | `tests/test_phase02_smoke.py` | exact |
| `tests/conftest.py` (modified) | test-infra | CRUD | `tests/conftest.py` (existing) | self-extension |
| `tests/ci/test_csp_nonce.py` | test (static grep) | transform | `tests/ci/test_no_unsafe_jinja.py` | exact |
| `tests/ci/test_no_credential_dump.py` | test (static grep) | transform | `tests/ci/test_no_unsafe_jinja.py` | exact |
| `tests/e2e/conftest.py` | test-infra (Playwright) | request-response | `tests/conftest.py` fixture pattern | partial |
| `tests/e2e/test_responsive_smoke.py` | test (e2e browser) | request-response | none — net-new | none |
| `Dockerfile` (modified) | config (container build) | batch | `Dockerfile` existing stages | self-extension |
| `docker-compose.yml` (modified) | config (orchestration) | event-driven | `docker-compose.yml` existing services | self-extension |
| `.github/workflows/ci.yml` | config (CI pipeline) | event-driven | none — net-new | none |
| `requirements-dev.txt` (modified) | config (dependencies) | — | `requirements-dev.txt` existing | self-extension |

---

## Pattern Assignments

### `tests/test_happy_path_smoke.py` (test, request-response)

**Analog:** `tests/test_phase02_smoke.py`

**Imports pattern** (lines 1-10):
```python
from __future__ import annotations

import re

import pytest
```

**Guard pattern** (lines 32-39 of analog — hard-require wiring):
```python
def _require_phase02_wired() -> None:
    """Skip cleanly if any Wave 4 / Wave 5 dependency is missing."""
    try:
        from app.csrf import CSRFFormFieldShim  # noqa: F401
        from app.routers.admin import router as admin_router  # noqa: F401
        from app.routers.auth import router as auth_router  # noqa: F401
    except ImportError as exc:
        pytest.skip(f"Wave 4/5 deps not yet present: {exc}")
```

For TEST-01 the guard becomes a hard-fail in CI (`SNOB_CI=1`), not a skip. The equivalent for Phase 12 reads:
```python
import os
_CI_MODE = os.environ.get("SNOB_CI") == "1"

def _require_wired(label: str) -> None:
    try:
        from app.routers.brew import router  # noqa: F401
        from app.routers.catalog import router  # noqa: F401
    except ImportError as exc:
        if _CI_MODE:
            pytest.fail(f"SNOB_CI=1 but dependency missing: {exc}")
        pytest.skip(str(exc))
```

**CSRF + session bootstrap pattern** (lines 57-96 of analog):
```python
# Step 1: GET the setup form, capture csrftoken cookie
r_setup_get = client.get("/setup")
assert r_setup_get.status_code == 200
token = r_setup_get.cookies.get("csrftoken")
assert token, "starlette-csrf must set csrftoken cookie"

# Step 2: POST with form field + header + cookie (the triple-send idiom)
r_setup = client.post(
    "/setup",
    data={
        "X-CSRF-Token": token,
        "username": "smoketest",
        "email": "smoke@example.com",
        "password": "twelve-chars-min-password",
    },
    headers={"X-CSRF-Token": token},
    cookies={"csrftoken": token},
    follow_redirects=False,
)
assert r_setup.status_code == 303

# Step 3: extract session cookie for subsequent requests
m = re.search(r"session_id=([^;]+)", r_setup.headers.get("set-cookie", ""))
assert m
session_signed = m.group(1)

# Step 4: authenticated GET — carry both cookies
r_home = client.get(
    "/",
    cookies={"session_id": session_signed, "csrftoken": token},
)
assert r_home.status_code == 200
```

**Refresh CSRF token pattern** (lines 116-117 of analog — rotation-safe):
```python
# Refresh CSRF token from the latest response in case rotation kicked in.
token2 = r_home.cookies.get("csrftoken", token)
```

**Extended smoke pattern for catalog + brew entities:**
The TEST-01 smoke adds entity-creation steps after login. Each catalog POST follows the same triple-send idiom (data `X-CSRF-Token` + `headers` + `cookies`), then carries the session/CSRF cookies into the next step. The full chain: setup → login → POST /catalog/roasters → POST /catalog/coffees → POST /catalog/equipment → POST /catalog/recipes → POST /brew → GET / (assert all home sections render).

---

### `tests/conftest.py` (modified — D-01 teardown + D-02 skip enforcement)

**Analog:** `tests/conftest.py` (self-extension — the existing file is the pattern source)

**Safety interlock pattern** (lines 322-332 — MUST be replicated in the new teardown):
```python
# Safety interlock: NEVER issue destructive reset against a non-test database.
try:
    from app.config import settings as _settings
    _active_db = urlparse(
        _settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
    ).path.lstrip("/")
except Exception:
    _active_db = ""
if "test" not in _active_db.lower():
    yield
    return
```

**Existing `fresh_db` TRUNCATE pattern** (lines 335-354 — catalog teardown extends this):
```python
# NOTE (lines 337-341): TRUNCATE ... CASCADE in Postgres truncates every
# referencing table regardless of FK delete_rule. app_settings.updated_by_user_id
# FKs to users.id (ON DELETE SET NULL), so TRUNCATE users CASCADE would wipe
# the 19 seeded app_settings rows. Use explicit DELETE so ON DELETE SET NULL
# is honored.
with engine.begin() as conn:
    conn.execute(text("DELETE FROM sessions"))
    conn.execute(text("DELETE FROM users"))
    conn.execute(text("ALTER SEQUENCE users_id_seq RESTART WITH 1"))
    conn.execute(
        text("UPDATE app_settings SET value='false' WHERE key='setup_completed'")
    )
```

**New catalog teardown pattern to add (module-scoped, after each test module):**
```python
@pytest.fixture(scope="module", autouse=True)
def _reset_catalog_tables() -> Iterator[None]:
    yield
    if not _postgres_reachable():
        return
    try:
        from app.config import settings as _s
        _active_db = urlparse(
            _s.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
        ).path.lstrip("/")
    except Exception:
        return
    if "test" not in _active_db.lower():
        return
    try:
        from app.db import engine
        from sqlalchemy import text
        with engine.begin() as conn:
            # FK-safe TRUNCATE order (RESTRICT on brew_sessions → coffees/bags):
            conn.execute(text("TRUNCATE brew_sessions RESTART IDENTITY CASCADE"))
            conn.execute(text("TRUNCATE bags RESTART IDENTITY CASCADE"))
            conn.execute(text("TRUNCATE coffees RESTART IDENTITY CASCADE"))
            conn.execute(text("TRUNCATE equipment RESTART IDENTITY CASCADE"))
            conn.execute(text("TRUNCATE recipes RESTART IDENTITY CASCADE"))
            conn.execute(text("TRUNCATE roasters RESTART IDENTITY CASCADE"))
            conn.execute(text("TRUNCATE flavor_notes RESTART IDENTITY CASCADE"))
    except Exception:
        pass
    # Clear in-memory app_settings cache (resolves test_setup_concurrent_race)
    # app/services/settings.py exports `invalidate` (test-only hook, line 275-281)
    # and `_cache` (module-level dict, line 78). Clear all keys:
    try:
        import app.services.settings as _svc
        _svc._cache.clear()  # type: ignore[attr-defined]
    except Exception:
        pass
```

**Key finding on cache invalidation:** `app/services/settings.py` line 78 defines `_cache: dict[str, _CachedSetting] = {}` as a plain module-level dict. Line 275-281 exports `invalidate(key)` which calls `_cache.pop(key, None)`. For full reset, call `_svc._cache.clear()` — faster than calling `invalidate` per key since the key set is not known statically.

**D-02 skip enforcement pattern (add at conftest module top):**
```python
import os
_CI_MODE = os.environ.get("SNOB_CI") == "1"

def _require_postgres(reason: str) -> None:
    """In CI mode (SNOB_CI=1), fail instead of skip on missing Postgres."""
    if _CI_MODE:
        pytest.fail(f"SNOB_CI=1 but Postgres unreachable: {reason}")
    else:
        pytest.skip(reason)
```

Replace the existing `pytest.skip(...)` calls in Postgres-dependent fixtures with `_require_postgres(...)` for the critical-path fixtures: `fresh_db`, `sync_db`, `seeded_admin_user`, `seeded_regular_user`.

**`_provision_test_db` fixture pattern** (lines 225-273 — the existing session-scoped autouse DB provisioner; the CI workflow depends on this pattern correctly rewriting the DB name):
```python
@pytest.fixture(scope="session", autouse=True)
def _provision_test_db() -> Iterator[None]:
    if not _postgres_reachable():
        yield
        return
    # ... creates snobbery_test if missing, runs alembic upgrade head
    _parsed = urlparse(_settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://"))
    _test_db = _parsed.path.lstrip("/")
    if "test" not in _test_db.lower():
        yield
        return
    # alembic.ini Config("alembic.ini") — env var DATABASE_URL already forced above
    command.upgrade(Config("alembic.ini"), "head")
    yield
```

---

### `tests/ci/test_csp_nonce.py` (test, static grep)

**Analog:** `tests/ci/test_no_unsafe_jinja.py` — clone this structure exactly.

**Full analog** (lines 1-89 of analog, condensed to the structural template):

**Module docstring pattern** (lines 1-32 of analog):
```python
"""D-07a: Every <script> and <style> tag in app/templates/ must carry a nonce attribute.
   No 'unsafe-eval' or 'unsafe-inline' in template-level CSP directives outside
   documented trade-offs in docs/decisions/0001*.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
```

**Directory + pattern list pattern** (lines 41-60 of analog):
```python
TEMPLATES_DIR = Path("app/templates")

FORBIDDEN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\|\s*safe"),
        "Pipe `|safe` is forbidden (SEC-05).",
    ),
    # ... more patterns
]

_JINJA_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

def _strip_comments(source: str) -> str:
    source = _JINJA_COMMENT.sub("", source)
    source = _HTML_COMMENT.sub("", source)
    return source
```

**Parametrize + test body pattern** (lines 73-89 of analog):
```python
@pytest.mark.parametrize(
    "template_path",
    list(TEMPLATES_DIR.rglob("*.html")) if TEMPLATES_DIR.exists() else [],
)
def test_template_safety(template_path: Path) -> None:
    raw = template_path.read_text(encoding="utf-8")
    scannable = _strip_comments(raw)
    for pattern, message in FORBIDDEN_PATTERNS:
        match = pattern.search(scannable)
        assert not match, f"{template_path}: {message} (matched: {match.group(0)!r})"
```

**CSP-specific patterns to detect (D-07a):**
```python
# Pattern: <script> or <style> tag without a nonce attribute
# Negative lookahead: (?![^>]*\bnonce\s*=) — tag has no nonce before >
SCRIPT_WITHOUT_NONCE = re.compile(
    r'<(script|style)(?![^>]*\bnonce\s*=)[^>]*>',
    re.IGNORECASE,
)

# Pattern: unsafe directives that should never appear in template-level CSP
UNSAFE_DIRECTIVES = re.compile(r"'unsafe-eval'|'unsafe-inline'")
```

For the CSP grep, the `FORBIDDEN_PATTERNS` list style from the analog is replaced by separate parametrized tests or a single test that checks for the `SCRIPT_WITHOUT_NONCE` regex after comment-stripping. The `_strip_comments` helper is copied verbatim.

---

### `tests/ci/test_no_credential_dump.py` (test, static grep)

**Analog:** `tests/ci/test_no_unsafe_jinja.py` — same structure, different scan target (Python source files, not templates).

**Key structural differences from the template analog:**
- `SCAN_DIR = Path("app")` instead of `TEMPLATES_DIR = Path("app/templates")`
- `rglob("*.py")` instead of `rglob("*.html")`
- No `_strip_comments` needed (Python comments don't embed the forbidden pattern)
- Early-return guard: if `ApiCredential` not in source, skip (avoids false positives on unrelated files)

**Pattern:**
```python
"""SEC-6: model_dump() must never be called in files that reference ApiCredential.
   The decrypted key must never enter a serializable model dict.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

APP_DIR = Path("app")
MODEL_DUMP_PATTERN = re.compile(r"\bmodel_dump\s*\(")

@pytest.mark.parametrize(
    "source_path",
    [p for p in APP_DIR.rglob("*.py") if p.exists()] if APP_DIR.exists() else [],
)
def test_no_api_credential_model_dump(source_path: Path) -> None:
    src = source_path.read_text(encoding="utf-8")
    if "ApiCredential" not in src and "api_credential" not in src.lower():
        return  # file doesn't reference credentials — not in scope
    match = MODEL_DUMP_PATTERN.search(src)
    assert not match, (
        f"{source_path}: model_dump() in a file that references ApiCredential "
        f"(SEC-6). Line: {src[:match.start()].count(chr(10)) + 1}"
    )
```

**Context from `app/models/api_credential.py` line 16:** The `last_four` column is explicitly denormalized "so the Phase 9 admin list view can mask the key without invoking the encryption service. This keeps audit log lines and error messages safely tail-masked (SEC-6: never put the decrypted key in a Pydantic schema that could leak via `model_dump()`)." The grep test enforces this invariant permanently.

---

### `tests/e2e/conftest.py` (test-infra, Playwright session fixtures)

**Analog:** `tests/conftest.py` fixture patterns — no Playwright analog exists. Map to the closest structural patterns.

**Session-scoped browser fixture pattern** (mirrors `_provision_test_db` session scope in root conftest):
```python
from __future__ import annotations

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright


@pytest.fixture(scope="session")
def browser():
    """Session-scoped headless Chromium browser."""
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture(params=[(375, 667), (390, 844)], ids=["375x667", "390x844"])
def page_at_viewport(browser: Browser):
    """Function-scoped Page at each required mobile viewport."""
    width, height = request.param
    ctx: BrowserContext = browser.new_context(
        viewport={"width": width, "height": height}
    )
    page: Page = ctx.new_page()
    yield page
    ctx.close()
```

**Auth-seeding pattern** (mirrors the CSRF + session bootstrap from `test_phase02_smoke.py` lines 57-96, but via httpx for the setup step then Playwright for navigation):
The Playwright smoke must authenticate before asserting layout. The simplest approach mirrors the `test_phase02_smoke.py` setup flow but via direct HTTP requests (httpx or `page.request`) to `/setup` → `/login`, storing the resulting `session_id` cookie into the Playwright context.

---

### `tests/e2e/test_responsive_smoke.py` (test, e2e browser)

**Analog:** None in-repo. Patterns from RESEARCH.md Pattern 5 apply.

**Core computed-style assertion pattern** (from RESEARCH.md):
```python
def test_input_font_size_no_ios_zoom(page_at_viewport: Page, base_url: str) -> None:
    """MX-1: every input/select/textarea must have computed font-size >= 16px."""
    page_at_viewport.wait_for_selector("input, select, textarea")
    violations = page_at_viewport.evaluate("""() => {
        const els = document.querySelectorAll('input, select, textarea');
        const out = [];
        for (const el of els) {
            const fs = parseFloat(getComputedStyle(el).fontSize);
            if (fs < 16) out.push({tag: el.tagName, id: el.id, name: el.name, fontSize: fs});
        }
        return out;
    }""")
    assert violations == [], f"iOS-zoom violations (font-size < 16px): {violations}"
```

**No-horizontal-scroll assertion pattern:**
```python
def test_no_horizontal_scroll(page_at_viewport: Page, base_url: str) -> None:
    scroll_width = page_at_viewport.evaluate("document.documentElement.scrollWidth")
    client_width = page_at_viewport.evaluate("document.documentElement.clientWidth")
    assert scroll_width <= client_width, (
        f"Horizontal scroll at {page_at_viewport.viewport_size}: "
        f"scrollWidth={scroll_width} > clientWidth={client_width}"
    )
```

**Note on selector for bottom nav:** The exact CSS class or `data-testid` on the bottom nav element must be verified in `app/templates/base.html` before writing the assertion. Phase 11 shipped the bottom nav; read the template before hardcoding the selector.

---

### `Dockerfile` (modified — D-03 dev/test multi-stage target)

**Analog:** Existing `Dockerfile` stages (self-extension).

**Existing stage declaration pattern** (lines 19 and 63):
```dockerfile
FROM debian:bookworm-slim AS tailwind-builder
# ...
FROM python:3.12-slim AS runtime
```

**New dev stage pattern to add after `runtime` stage:**
```dockerfile
# --- Stage 3: Dev/test — extends runtime with pytest + playwright ----------
FROM runtime AS dev

USER root

# Install requirements-dev.txt (pytest, ruff, mypy, respx, playwright, etc.)
COPY requirements-dev.txt ./
RUN pip install -r requirements-dev.txt

# Install Playwright's Chromium browser binary + OS-level deps.
# --with-deps handles libglib2.0-0, libfontconfig, etc. for bookworm-slim.
RUN playwright install chromium --with-deps

USER app

# Override entrypoint for test invocations. The full-suite gate command is:
#   docker compose run --rm coffee-snobbery-test
# which maps to:
#   python -m pytest tests/ -rs --tb=short --ignore=tests/e2e
ENTRYPOINT ["python", "-m", "pytest"]
CMD ["tests/", "-rs", "--tb=short", "--ignore=tests/e2e"]
```

**Critical constraint (from RESEARCH.md Pitfall 2):** The dev stage must inherit from `runtime` (not `tailwind-builder`), which already contains the compiled Tailwind CSS via `COPY --from=tailwind-builder`. This ensures the `app` fixture in conftest doesn't skip with "Tailwind CSS missing."

**Existing `COPY --from=tailwind-builder` pattern** (Dockerfile line 104):
```dockerfile
COPY --from=tailwind-builder --chown=app:app /build/app/static/css/tailwind.*.css ./app/static/css/
```
This is already present in `runtime`; the `dev` stage inherits it by building FROM runtime.

---

### `docker-compose.yml` (modified — D-03 test profile)

**Analog:** Existing `docker-compose.yml` service blocks (self-extension).

**Existing service pattern** (lines 43-67):
```yaml
  coffee-snobbery:
    image: coffee-snobbery:latest
    build:
      context: .
      dockerfile: Dockerfile
    container_name: coffee-snobbery
    restart: unless-stopped
    depends_on:
      coffee-snobbery-db:
        condition: service_healthy
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@coffee-snobbery-db:5432/${POSTGRES_DB}
    volumes:
      - coffee_snobbery_photos:/app/data/photos
      - coffee_snobbery_backups:/app/data/backups
    networks:
      - coffee-snobbery-net
    ports:
      - "127.0.0.1:8080:8000"
```

**New test service to add (under `services:`):**
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
      - .:/app
```

**Key differences from prod service:** no `container_name` (allows multiple run invocations), no `restart`, no `ports`, no photo/backup volumes, adds source bind-mount `- .:/app` (for test runs), adds `SNOB_CI: "1"`, adds `profiles: [test]` (keeps `docker compose up -d` from starting the test container).

---

### `.github/workflows/ci.yml` (net-new — no in-repo analog)

**Analog:** None. Pattern from RESEARCH.md Pattern 4.

**Full structure** (from RESEARCH.md lines 311-362):
```yaml
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

**Critical integration note:** The conftest DB-name forcing logic (lines 51-64 of `tests/conftest.py`) rewrites `snobbery` → `snobbery_test` automatically when `DATABASE_URL` points to a DB without "test" in the name. Setting `DATABASE_URL=.../snobbery` in CI is correct — conftest handles the rename. No explicit migration step is needed because `_provision_test_db` runs `alembic upgrade head` against `snobbery_test`.

**pyproject.toml addopts conflict:** Current `addopts = "-x --tb=short"` (line 39 of `pyproject.toml`). The gate command passes explicit `-rs --tb=short` — pytest CLI flags are additive with addopts for most flags, but `-x` will persist unless overridden. Safest resolution: change `addopts` to just `"--tb=short"` in `pyproject.toml` and pass `-x` explicitly on dev one-shots. The CI command above uses `--tb=short` without `-x`, which should override for the gate run.

---

### `requirements-dev.txt` (modified)

**Analog:** `requirements-dev.txt` (self-extension).

**Current content** (lines 1-12):
```
-r requirements.txt

ruff>=0.15.13,<0.16
mypy>=1.13,<2
pytest>=9.0,<10
pytest-asyncio
pytest-cov
respx
# httpx is already in requirements.txt; FastAPI TestClient depends on it.
```

**Addition:**
```
playwright>=1.59,<2
```

---

## Shared Patterns

### CSRF Triple-Send Idiom
**Source:** `tests/test_phase02_smoke.py` lines 67-78
**Apply to:** `tests/test_happy_path_smoke.py` (every state-changing POST in the smoke)
```python
client.post(
    "/some-endpoint",
    data={"X-CSRF-Token": token, ...form_fields...},
    headers={"X-CSRF-Token": token},
    cookies={"csrftoken": token, "session_id": session_signed},
    follow_redirects=False,
)
```
Always send the CSRF token in all three places: form body, request header, and cookie. The `CSRFFormFieldShim` hoists the form field into the header; the header is also sent directly for idempotency.

### Test Safety Interlock (preserve verbatim)
**Source:** `tests/conftest.py` lines 322-332
**Apply to:** Every new fixture in `tests/conftest.py` that issues destructive SQL
```python
if "test" not in _active_db.lower():
    yield  # refuse to mutate non-test database
    return
```
This guard must appear in the new `_reset_catalog_tables` module-scoped fixture, identical to the existing `fresh_db` implementation.

### Skip → Fail Gate (D-02 skip enforcement)
**Source:** `tests/conftest.py` (new, extending existing `_postgres_reachable()` pattern)
**Apply to:** `fresh_db`, `sync_db`, `seeded_admin_user`, `seeded_regular_user`, and the TEST-01 smoke guard
```python
_CI_MODE = os.environ.get("SNOB_CI") == "1"

def _require_postgres(reason: str) -> None:
    if _CI_MODE:
        pytest.fail(f"SNOB_CI=1 but Postgres unreachable: {reason}")
    else:
        pytest.skip(reason)
```

### Grep Test Structure (CI static analysis)
**Source:** `tests/ci/test_no_unsafe_jinja.py` (entire file — 89 lines)
**Apply to:** `tests/ci/test_csp_nonce.py` and `tests/ci/test_no_credential_dump.py`
Key elements to copy verbatim: `_JINJA_COMMENT` + `_HTML_COMMENT` regexes, `_strip_comments()`, `TEMPLATES_DIR.rglob("*.html") if TEMPLATES_DIR.exists() else []` parametrize guard, assertion message format `f"{template_path}: {message} (matched: {match.group(0)!r})"`.

### `_postgres_reachable()` Pattern
**Source:** `tests/conftest.py` lines 358-386
**Apply to:** The new `_reset_catalog_tables` fixture teardown body (copy the reachability probe rather than duplicating the socket logic)
```python
if not _postgres_reachable():
    return
```
Call the existing helper; do not re-implement the socket probe.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `.github/workflows/ci.yml` | config (CI) | event-driven | No GitHub Actions workflows exist in the repo |
| `tests/e2e/test_responsive_smoke.py` | test (e2e browser) | request-response | No Playwright tests exist in the repo |

Both rely on patterns documented in RESEARCH.md (Pattern 4 and Pattern 5 respectively).

---

## Metadata

**Analog search scope:** `tests/`, `tests/ci/`, `tests/docs/`, `app/services/`, `Dockerfile`, `docker-compose.yml`, `requirements-dev.txt`, `pyproject.toml`
**Files scanned:** 10 existing files read in full
**Pattern extraction date:** 2026-05-23

**Key resolved assumptions from RESEARCH.md:**
- A5 (cache invalidation symbol): RESOLVED — `app/services/settings.py` line 78 confirms `_cache` is a plain module-level dict; line 275 exports `invalidate(key)` for single-key eviction. Full reset: `_svc._cache.clear()`.
- A6 (concurrent race root cause): CONFIRMED — `test_setup_concurrent_race` fails because `_cache` retains `setup_completed=true` from a prior test module; `_cache.clear()` in the module teardown resolves it.
- alembic.ini DATABASE_URL: conftest line 268 uses `Config("alembic.ini")` with env var already forced — alembic.ini reads from env, no hardcoded URL concern.
