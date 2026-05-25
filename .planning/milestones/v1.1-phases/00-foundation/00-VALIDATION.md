---
phase: 0
slug: foundation
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-17
---

# Phase 0 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest `>=9.0,<10` |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` — Wave 0 installs |
| **Quick run command** | `make test` (delegates to `docker compose exec coffee-snobbery pytest -x`) |
| **Full suite command** | `make test` (same — only one runtime test in Phase 0) |
| **Smoke command** | `make smoke` (`docker compose up -d --build && curl -fsS http://127.0.0.1:8080/healthz`) |
| **Estimated runtime** | ~30s smoke; <5s unit suite |

---

## Sampling Rate

- **After every task commit:** Run `make test`
- **After every plan wave:** Run `make test` + `make smoke`
- **Before `/gsd-verify-work`:** Full smoke + all introspection checks green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

> Populated by the planner — one row per task. Each row binds a task to a requirement, a test type, and an automated command. Rows referencing Wave 0 files are marked `❌ W0` until the file lands.

| Task ID  | Plan       | Wave | Requirement | Threat Ref  | Secure Behavior                                                          | Test Type   | Automated Command                                                                                                                                                              | File Exists | Status     |
|----------|------------|------|-------------|-------------|--------------------------------------------------------------------------|-------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------|------------|
| 00-01-01 | 00-01-PLAN | 1    | FOUND-09    | T-00-01-01  | `.env` excluded from git + docker build context                          | unit        | `python -c "import tomllib, pathlib; data = tomllib.loads(pathlib.Path('pyproject.toml').read_text()); assert data['tool']['pytest']['ini_options']['testpaths'] == ['tests']"` | ❌ W0       | ⬜ pending |
| 00-01-02 | 00-01-PLAN | 1    | FOUND-09    | T-00-01-03  | Required secrets have no default → fail-loud on missing env              | unit        | `python -c "from app.config import settings; assert settings.LOG_FORMAT == 'json'; assert settings.TRUSTED_PROXY_IPS == '127.0.0.1'"`                                          | ❌ W0       | ⬜ pending |
| 00-01-03 | 00-01-PLAN | 1    | FOUND-10    | T-00-01-02  | `os.environ` reads confined to `app/config.py` (CI grep)                 | unit        | `pytest tests/test_no_direct_env.py tests/test_env_example.py -x --tb=short`                                                                                                   | ❌ W0       | ⬜ pending |
| 00-02-01 | 00-02-PLAN | 2    | FOUND-11    | T-00-02-01  | Redactor scrubs deny-list keys in JSON + console output                  | unit        | `python -c "from app.logging import configure_logging; configure_logging('json','INFO'); import structlog; structlog.get_logger('t').info('hi')"`                              | ❌ W0       | ⬜ pending |
| 00-02-02 | 00-02-PLAN | 2    | FOUND-11    | T-00-02-01  | JSON shape, redactor, console flip, idempotency, contextvars seat        | unit        | `pytest tests/test_logging.py -x --tb=short`                                                                                                                                   | ❌ W0       | ⬜ pending |
| 00-03-01 | 00-03-PLAN | 2    | CAT-04, AI-02 | T-00-03-02 | Pool knobs locked (pool_size=10/overflow=5/timeout=5/pre_ping=True)      | unit        | `python -c "from app.models import Base; assert set(Base.metadata.tables.keys()) == {'users','bags','wishlist_entries','ai_recommendations','app_settings'}"`                  | ❌ W0       | ⬜ pending |
| 00-03-02 | 00-03-PLAN | 2    | FOUND-05, FOUND-06 | T-00-03-04 | Extensions installed, 19 seed rows, cost-obs columns present       | unit        | `python -c "import pathlib; src = pathlib.Path('app/migrations/versions/0001_initial.py').read_text(); assert 'CREATE EXTENSION IF NOT EXISTS citext' in src"`                 | ❌ W0       | ⬜ pending |
| 00-03-03 | 00-03-PLAN | 2    | FOUND-05, FOUND-06, CAT-04, AI-02 | T-00-03-07 | citext + tables + seed rows verified via pg_extension / information_schema | integration | `pytest tests/test_migrations.py -x --tb=short --co -q` (collection); full run inside `make smoke`                                                                             | ❌ W0       | ⬜ pending |
| 00-04-01 | 00-04-PLAN | 3    | FOUND-12    | T-00-04-09  | Jinja autoescape ON; dual theme-color meta; no `\|safe` in base.html     | unit        | `python -c "import pathlib; base = pathlib.Path('app/templates/base.html').read_text(); assert '#FAF7F2' in base and '#1A1110' in base; assert '\|safe' not in base"`           | ❌ W0       | ⬜ pending |
| 00-04-02 | 00-04-PLAN | 3    | FOUND-12    | T-00-04-05  | `/healthz` enforces 2s statement_timeout (`SET LOCAL`) per CONTEXT D-08  | smoke       | `python -c "from app.main import app; routes = {r.path for r in app.routes if hasattr(r,'path')}; assert '/healthz' in routes and '/' in routes"` + grep `SET LOCAL statement_timeout` | ❌ W0       | ⬜ pending |
| 00-04-03 | 00-04-PLAN | 3    | FOUND-04, FOUND-07, FOUND-08 | T-00-04-01, T-00-04-02, T-00-04-03 | --workers 1, --proxy-headers, --forwarded-allow-ips; non-root UID 1000; pg_dump v16 | smoke | `python -c "import pathlib; df = pathlib.Path('Dockerfile').read_text(); assert 'postgresql-client-16' in df and 'useradd -u 1000' in df; ep = pathlib.Path('entrypoint.sh').read_text(); assert '--workers 1' in ep and '--proxy-headers' in ep"` | ❌ W0       | ⬜ pending |
| 00-05-01 | 00-05-PLAN | 4    | FOUND-01, FOUND-02, FOUND-03 | T-00-05-02, T-00-05-03, T-00-05-04 | 127.0.0.1:8080 bind only; no DB ports; pg_isready healthcheck; service_healthy gate | unit | `python -c "import yaml, pathlib; d = yaml.safe_load(pathlib.Path('docker-compose.yml').read_text()); svcs = d['services']; assert svcs['coffee-snobbery']['ports'] == ['127.0.0.1:8080:8000']; assert 'ports' not in svcs['coffee-snobbery-db']"` | ❌ W0       | ⬜ pending |
| 00-05-02 | 00-05-PLAN | 4    | FOUND-01    | —           | N/A (developer ergonomics target list)                                   | unit        | `python -c "import pathlib, re; m = pathlib.Path('Makefile').read_text(); [m.index(t + ':') for t in ['up','down','logs','psql','migrate','revision','test','smoke','shell','build','fmt','lint']]"` | ❌ W0       | ⬜ pending |
| 00-05-03 | 00-05-PLAN | 4    | FOUND-01, FOUND-02, FOUND-03 | T-00-05-01, T-00-05-06 | Single-worker rule loud in 3rd location; NGINX snippet w/ X-Forwarded-Proto; PITFALL refs | manual + grep | `grep -RIn -E '\-\-workers 1\|single worker' README.md entrypoint.sh app/services/scheduler.py \| wc -l` returns ≥3                                                            | ❌ W0       | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Wave 0 lands the test infrastructure before any production code so every subsequent task has a verification target. Source: 00-RESEARCH.md §Validation Architecture → Wave 0 Gaps.

- [ ] `tests/conftest.py` — TestClient fixture, DB session with rollback, env var setup
- [ ] `tests/test_healthz.py` — smoke test of `GET /healthz`
- [ ] `tests/test_env_example.py` — regex check that `.env.example` documents every `Settings().model_fields` key
- [ ] `tests/test_logging.py` — capture structlog output; assert JSON shape with `event`, `timestamp_iso`, `level`; redactor scrubs deny-list keys
- [ ] `tests/test_migrations.py` — introspect `pg_extension` + `information_schema.columns` for each table
- [ ] `tests/test_no_direct_env.py` — grep-style assertion that `os.environ` is only referenced in `app/config.py`
- [ ] `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths`, `asyncio_mode`
- [ ] `requirements-dev.txt` — pytest, pytest-asyncio, httpx, respx, ruff, mypy
- [ ] `Makefile` — `test`, `smoke`, `fmt`, `lint` targets

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `pg_dump --version` matches `coffee-snobbery-db` server version | FOUND-07 | Cross-container shell compare; trivial in CI but explicit visual confirmation is faster on first build | `docker compose exec coffee-snobbery pg_dump --version` and `docker compose exec coffee-snobbery-db postgres --version` — both must read `16.x` |
| Stack reachable from host on `127.0.0.1:8080` and NOT on `0.0.0.0` | FOUND-01, security | The bind-address check requires an external scan from the host | `ss -tlnp \| grep 8080` on the host — listener must be `127.0.0.1`, not `0.0.0.0` |
| Single-worker rule documented in three places | FOUND-04 | Document grep — easy to inspect but the count gates merge | `grep -RIn "workers 1\|--workers 1\|single worker" README.md entrypoint.sh app/services/scheduler.py` must return ≥3 hits |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
