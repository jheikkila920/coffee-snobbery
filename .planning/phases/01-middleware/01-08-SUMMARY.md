---
phase: 01-middleware
plan: 08
status: complete
type: execute
wave: 2
completed: 2026-05-17
files_created:
  - app/templates_setup.py
  - app/templates/pages/.gitkeep
  - app/templates/fragments/.gitkeep
  - app/routers/debug.py
  - app/schemas/__init__.py
  - app/schemas/debug.py
files_modified:
  - app/templates/base.html
  - README.md
commits:
  - 52bde31 feat(01-08): Jinja2 engine + autoescape + csp_nonce global + base.html
  - 7a987dd feat(01-08): /debug/proxy endpoint + DebugProxyResponse schema
  - a2832cd docs(01-08): README NGINX server block + HSTS + smoke check
executor: orchestrator-mediated (subagent git commits blocked by sandbox)
---

## Plan 01-08 — Jinja engine + base.html + /debug/proxy + README NGINX

Lands the last set of pieces Plan 09 needs before assembling `app/main.py`:
the canonical Jinja2 templates instance, the CSP-nonce-aware base layout,
the operational /debug/proxy smoke endpoint, and the README NGINX block.

## Task outcomes

### Task 1 — Jinja engine + base.html
- `app/templates_setup.py` ships `templates = Jinja2Templates(directory="app/templates")` with `select_autoescape(["html", "jinja", "jinja2"])` and `csp_nonce(request)` registered as a Jinja global.
- `csp_nonce` falls back to empty string when `request.state.csp_nonce` is absent (no-middleware unit-test path) — fails safe: `script-src 'self' 'nonce-'` matches nothing.
- `app/templates/base.html` extends the Phase 0 shell (preserves `tailwind_css_path`, theme-color metas, viewport).
- Three `<script defer>` tags carry `nonce="{{ csp_nonce(request) }}"`:
  - `@alpinejs/csp@3.14.9` (jsdelivr CDN) — pinned exact per RESEARCH §16 Open Question 2 resolution.
  - HTMX 2.0.10 (unpkg)
  - `/static/js/htmx-listeners.js` loaded AFTER htmx core so `htmx.config.allowEval = false` runs after the htmx symbol is defined.
- `<meta name="csrf-token" content="{{ request.cookies.get('csrftoken', '') }}">` for htmx-listeners.js to read.
- No `|safe`, no `hx-on:`, no `hx-vals='js:`, no `hx-headers='js:` — passes `tests/ci/test_no_unsafe_jinja.py` grep gate.
- `pages/.gitkeep` + `fragments/.gitkeep` anchor the canonical layout so the grep test's `rglob` has a directory to walk.

**Block additions beyond Phase 0:** `base.html` exposes only `{% block page_title %}{% endblock %}{% block title %}{% endblock %}` (Phase 0 already had these) and `{% block content %}{% endblock %}` for the body. No additional `{% block %}` placeholders were added — Phase 4+ ergonomics not yet known; future plans can extend.

### Task 2 — /debug/proxy + DebugProxyResponse
- `app/schemas/debug.py` ships Pydantic v2 `DebugProxyResponse` with exactly four fields: `scheme: str`, `client_host: str`, `trusted_proxy_ips: str`, `headers_honored: bool`.
- `app/routers/debug.py` ships `router = APIRouter()` + one route `GET /debug/proxy` returning the four-field model.
- `headers_honored = scheme == "https" and client_host not in trusted_list` per D-16 / plan acceptance.
- Reads `request.url.scheme` and `request.client.host` directly (uvicorn `--proxy-headers` has already rewritten them when the trust list matched). Does not read raw `X-Forwarded-*` headers — that's the whole point of the smoke check.
- `app/config.py` already shipped from Phase 0 with `TRUSTED_PROXY_IPS: str = "127.0.0.1"` — no stub needed.
- `tests/routers/test_debug_proxy.py` — 2 tests collect cleanly. Skip on host because `app` fixture cannot bootstrap without the Docker-built Tailwind hash; flip to pass once Plan 09 mounts the router on `app.main`.

### Task 3 — README NGINX block + HSTS + smoke check
- Extended the existing Phase 0 NGINX snippet (was minimal — four `proxy_set_header` lines) into the canonical RESEARCH §10 server block.
- New literal substrings (all required by `tests/docs/test_readme_nginx.py`):
  - `Strict-Transport-Security "max-age=63072000; includeSubDomains"` (HSTS, two years)
  - Optional HTTP→HTTPS redirect server block so HSTS gets installed on first visit
  - `proxy_buffering off` (Phase 7 SSE forward-look)
  - `/sw.js` location with `Service-Worker-Allowed: /` (Phase 11 PWA forward-look)
- New "Operational smoke check" section: `curl -i https://snobbery.example.com/debug/proxy` + remediation steps if `headers_honored` is false.
- Extended TRUSTED_PROXY_IPS section with value-selection rules (127.0.0.1 vs Docker bridge gateway IP + `docker network inspect` command).
- Single-uvicorn-worker section already existed at the 3-location threshold from Phase 0 — unchanged.
- All 3 grep tests in `tests/docs/test_readme_nginx.py` pass.

## Wave 0 test status (after this plan)

- `tests/ci/test_no_unsafe_jinja.py` — PASS
- `tests/templates/test_autoescape.py` — collects + passes (autoescape verified via `<script>` → `&lt;script&gt;` render check, which doesn't need the full app)
- `tests/routers/test_debug_proxy.py` — collects; 2 tests skip on host (app-fixture bootstrap fails without Docker Tailwind); will flip to PASS after Plan 09
- `tests/docs/test_readme_nginx.py` — 3 PASS

## Deviations from the plan

1. **Executor mode** — plan assumed worktree-isolated executor agents. Two subagent attempts hit Claude Code worktree-base bugs (worktree HEAD created at orphan initial commit `5c6f07e` instead of plan base `603df82`); the third hit a Bash-tool denial on every variant of `git commit`. The orchestrator finished Tasks 1, 2, 3 inline and committed each atomically. Per-task atomicity preserved.
2. **Alpine CSP build version** — pinned `@alpinejs/csp@3.14.9` (the latest 3.14.x at plan time per the agent's earlier resolution). Plan 10 ADR `0001-csp-strict-no-unsafe-eval.md` documents the why.
3. **Subagent permission issue** — surfaced to user during execution; user chose orchestrator-mediated commits.

## Plan 09 hooks (the next plan picks up)

- `from app.templates_setup import templates` — single Jinja instance.
- `from app.routers.debug import router as debug_router` — mount under no prefix.
- `from app.schemas.debug import DebugProxyResponse` — already used by the router; no additional import in main.

## Verification commands

```bash
python -c "from app.templates_setup import templates, csp_nonce; assert templates.env.autoescape is not None; assert 'csp_nonce' in templates.env.globals"
python -c "from app.routers.debug import router; assert '/debug/proxy' in [r.path for r in router.routes]"
python -c "from app.schemas.debug import DebugProxyResponse; assert set(DebugProxyResponse.model_fields) == {'scheme', 'client_host', 'trusted_proxy_ips', 'headers_honored'}"
python -m pytest tests/docs/test_readme_nginx.py tests/ci/test_no_unsafe_jinja.py -x
ruff check app/templates_setup.py app/routers/debug.py app/schemas/
```

All pass.
