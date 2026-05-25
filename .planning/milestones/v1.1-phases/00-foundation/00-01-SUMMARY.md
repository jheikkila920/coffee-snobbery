---
phase: 0
plan: 01
subsystem: foundation
tags:
  - skeleton
  - dependencies
  - config
  - settings
  - testing
  - wave-0
requirements: [FOUND-09, FOUND-10]
dependency_graph:
  requires: []
  provides:
    - "from app.config import settings"
    - "Settings field contract: 11 typed env-derived attributes"
    - "tests/conftest.py env-stub pattern (extended by Plan 03)"
    - ".gitignore + .dockerignore baseline"
    - "app/ subpackage directory contract (CONTEXT D-11)"
    - "app/services/scheduler.py single-worker rule callsite #2 of 3"
  affects:
    - "Plan 00-02: app/main.py + lifespan reads settings.LOG_FORMAT/LOG_LEVEL"
    - "Plan 00-03: app/db.py reads settings.DATABASE_URL + app/migrations/ inherits the no-direct-env rule"
    - "Plan 00-04: Dockerfile installs from requirements.txt, COPY picks up app/ tree"
    - "Plan 00-05: Makefile test target runs the Wave 0 tests authored here"
tech_stack:
  added:
    - "FastAPI 0.136 (pin only — not yet wired)"
    - "SQLAlchemy 2.0.49 (pin only)"
    - "Alembic 1.18 (pin only)"
    - "psycopg[binary] 3.3 (pin only)"
    - "pydantic 2.13 + pydantic-settings 2.14 (wired in app/config.py)"
    - "structlog 25.5 (pin only)"
    - "Pillow 12.2, APScheduler 3.11, anthropic 0.102, openai 2.37, argon2-cffi 25.1, cryptography 48, itsdangerous 2.2 (all pin-only — wired in later phases)"
    - "ruff 0.15.13 + mypy 1.13 + pytest 9.0 (tool configs in pyproject.toml)"
  patterns:
    - "pydantic-settings BaseSettings subclass as SOLE os.environ reader (FOUND-10)"
    - "SettingsConfigDict(extra='forbid') at the trust edge (T-00-01-04)"
    - "Env-stub via os.environ.setdefault at conftest.py module import time (predates first Settings() construction)"
    - "Grep/regex enforcement tests run before any production code lands (Wave 0 invariant)"
key_files:
  created:
    - path: "pyproject.toml"
      purpose: "ruff + mypy + pytest tool configs (no GitHub Actions YAML yet — Phase 12)"
    - path: "requirements.txt"
      purpose: "Pinned runtime deps, complete from day one (STACK.md §1)"
    - path: "requirements-dev.txt"
      purpose: "Pinned dev deps (ruff, mypy, pytest, pytest-asyncio, pytest-cov, respx); -r requirements.txt for inheritance"
    - path: ".env.example"
      purpose: "Documented env-var inventory with one-line generation hints (FOUND-09); gitignored at the .env target"
    - path: ".gitignore"
      purpose: ".env, build caches, hashed Tailwind output; tailwind.src.css whitelisted"
    - path: ".dockerignore"
      purpose: "Trim build context (.git, .planning, .claude, docs); tests/ intentionally NOT excluded so make test runs inside the image"
    - path: "app/__init__.py + app/{middleware,routers,services,schemas,models}/__init__.py"
      purpose: "Package skeleton with one-line owner docstrings (CONTEXT D-11)"
    - path: "app/services/scheduler.py"
      purpose: "Phase 8 placeholder; single-worker rule call-out location #2 of three (FOUND-04)"
    - path: "app/config.py"
      purpose: "pydantic-settings Settings class — sole os.environ reader; singleton exported as settings"
    - path: "app/templates/.gitkeep + app/static/.gitkeep"
      purpose: "Directory placeholders; filled by Plan 00-04 (templates) and 00-04 builder stage (static/css)"
    - path: "tests/__init__.py"
      purpose: "Marks tests/ as a package for pytest discovery"
    - path: "tests/conftest.py"
      purpose: "Wave 0 env-stub fixture — os.environ.setdefault at import time so Settings() constructs in test runs"
    - path: "tests/test_no_direct_env.py"
      purpose: "FOUND-10 enforcement — fails the build if os.environ leaks outside app/config.py"
    - path: "tests/test_env_example.py"
      purpose: "FOUND-09 enforcement — fails the build if .env.example and Settings drift"
  modified: []
decisions:
  - "APP_ENCRYPTION_KEY parsed as raw string in Phase 0; Phase 3 splits and builds MultiFernet (PROJECT.md row 18 — locked)"
  - "APP_SECRET_KEY uses Field(..., min_length=32) to reject empty / weak values at startup while leaving fixtures loose (T-00-01-03)"
  - "extra='forbid' in SettingsConfigDict rejects unknown env keys (T-00-01-04 defense in depth)"
  - "Tests/ directory excluded from .dockerignore so `docker compose exec coffee-snobbery pytest` works inside the container (Plan 00-05 dependency)"
  - "Excluded migrations/ from FOUND-10 grep preemptively so Plan 00-03's alembic env.py doesn't break this test"
metrics:
  duration_seconds: 385
  duration_human: "~6m 25s"
  tasks_completed: 3
  files_created: 19
  commits: 3
  completed: "2026-05-17T14:50:49Z"
---

# Phase 0 Plan 01: Project Skeleton + Settings + Wave 0 Tests — Summary

**One-liner:** Pinned runtime + dev dependency manifests, pydantic-settings `Settings` class as sole `os.environ` reader, fully documented `.env.example`, app/ package skeleton with phase-owner docstrings, and the two Wave 0 grep/regex tests (FOUND-09 + FOUND-10) all in place — green from this commit forward.

## What Was Built

Plan 00-01 lays the substrate every later phase inherits. There is no runtime app yet (the FastAPI `app/main.py`, the engine, the migrations, the Dockerfile, the entrypoint — all land in Plans 00-02 through 00-05). What this plan ships is the *contract*:

1. **Dependency manifests** (`requirements.txt`, `requirements-dev.txt`) pinned verbatim from `00-RESEARCH.md §Standard Stack`. Every library the project will use in any phase is pinned now so the image is complete from day one.
2. **Tool configs** (`pyproject.toml`): ruff (line-length 100, target-version py312, extend-select `E,F,I,B,UP,S`); mypy (strict_optional, disallow_untyped_defs, warn_unused_ignores); pytest (testpaths=tests, asyncio_mode=auto, addopts=`-x --tb=short`). No CI YAML — Phase 12 owns that.
3. **`Settings` class** (`app/config.py`) — the SOLE `os.environ` reader (FOUND-10). 11 typed fields covering Postgres connection, app secrets, proxy/runtime, and logging. `extra="forbid"` at the trust edge.
4. **`.env.example`** documenting every Settings field with a one-line generation hint (FOUND-09). Committed to git; `.env` is gitignored.
5. **`app/` package skeleton** with one-line owner docstrings (CONTEXT D-11): middleware (Phase 1), routers (Phase 2+), services (Phase 3+), schemas (Phase 1+), models (Plan 03).
6. **`app/services/scheduler.py`** placeholder containing the single-worker rule call-out — location #2 of three (FOUND-04; CONTEXT `<specifics>`).
7. **Wave 0 test infrastructure** (`tests/conftest.py`, `tests/test_no_direct_env.py`, `tests/test_env_example.py`) — both grep/regex enforcement tests run green right now (before any production code lands), and both fail with informative messages when the rule is violated.

## Final Pinned Versions (`requirements.txt`)

> Plan 00-02 / 00-03 / 00-04 / 00-05 consume these. Do not re-derive — copy.

```
# Core
fastapi>=0.136,<0.137
uvicorn[standard]>=0.47,<0.48
sqlalchemy>=2.0.49,<2.1
alembic>=1.18,<2.0
psycopg[binary]>=3.3,<3.4
pydantic>=2.13,<3.0
pydantic-settings>=2.14,<3.0
jinja2>=3.1.6,<4
structlog>=25.5,<26
python-multipart>=0.0.28,<0.1

# Pinned for later phases — installed now so the image is complete from day one:
argon2-cffi>=25.1,<26
cryptography>=48,<49
itsdangerous>=2.2,<3.0
httpx>=0.28,<0.29
Pillow>=12.2,<13
APScheduler>=3.11,<4
anthropic>=0.102,<1.0
openai>=2.37,<3.0
```

Dev (`requirements-dev.txt`, in addition to `-r requirements.txt`):

```
ruff>=0.15.13,<0.16
mypy>=1.13,<2
pytest>=9.0,<10
pytest-asyncio
pytest-cov
respx
```

## `Settings` Field Contract

> Downstream phases consume via `from app.config import settings`. This is the canonical list.

| Field | Type | Default | Notes |
|---|---|---|---|
| `POSTGRES_USER` | `str` | (required) | |
| `POSTGRES_PASSWORD` | `str` | (required) | |
| `POSTGRES_DB` | `str` | (required) | |
| `DATABASE_URL` | `str` | (required) | Expected shape `postgresql+psycopg://...` |
| `APP_SECRET_KEY` | `str` (min_length=32) | (required) | `secrets.token_urlsafe(64)` |
| `APP_ENCRYPTION_KEY` | `str` | (required) | Comma-separated Fernet keys; Phase 3 parses and builds `MultiFernet` |
| `TRUSTED_PROXY_IPS` | `str` | `"127.0.0.1"` | Comma-separated; uvicorn `--forwarded-allow-ips` |
| `APP_TIMEZONE` | `str` | `"America/Chicago"` | IANA; APScheduler (Phase 8) |
| `BACKUP_RETENTION_DAYS` | `int` | `14` | Phase 8 backup job |
| `LOG_LEVEL` | `Literal["DEBUG","INFO","WARNING","ERROR"]` | `"INFO"` | |
| `LOG_FORMAT` | `Literal["json","console"]` | `"json"` | CONTEXT D-16; Phase 0 Plan 02 wires structlog renderer |

`SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="forbid")`. The `extra="forbid"` setting rejects unknown env keys at startup — defense in depth against T-00-01-04 (Tampering).

## Test Commands Confirmed Green

> Run from repo root inside the project Python env (Plan 00-04 lands the Dockerfile that makes this `docker compose exec coffee-snobbery pytest ...`).

```bash
# Wave 0 tests — both pass:
pytest tests/test_no_direct_env.py tests/test_env_example.py -x --tb=short
# 2 passed in 0.21s

# pyproject.toml parses + has the expected configs:
python -c "import tomllib, pathlib; data = tomllib.loads(pathlib.Path('pyproject.toml').read_text()); \
  assert data['tool']['pytest']['ini_options']['testpaths'] == ['tests']; \
  assert data['tool']['ruff']['target-version'] == 'py312'; print('pyproject OK')"
# pyproject OK

# Settings round-trip (with stub env vars):
POSTGRES_USER=x POSTGRES_PASSWORD=x POSTGRES_DB=x \
DATABASE_URL=postgresql+psycopg://x:x@h/x \
APP_SECRET_KEY=$(printf 'x%.0s' {1..64}) \
APP_ENCRYPTION_KEY=$(printf 'x%.0s' {1..44}) \
python -c "from app.config import settings; print(settings.LOG_FORMAT)"
# json
```

Negative cases verified by hand:

- Adding `os.environ` to `app/middleware/__init__.py` → `test_no_direct_env.py` fails listing `app\middleware\__init__.py` as offender.
- Removing `LOG_FORMAT=` line from `.env.example` → `test_env_example.py` fails with `Missing from .env.example: ['LOG_FORMAT']`.

## Commits

| Task | Type | Hash | Summary |
|---|---|---|---|
| 1 | chore | `19c7066` | Scaffold dependency manifests + app/ package skeleton |
| 2 | feat | `a35827b` | pydantic-settings `Settings` + `.env.example` inventory |
| 3 | test | `d948696` | Wave 0 test infrastructure (FOUND-09 + FOUND-10 grep gates) |

## Deviations from Plan

None. Plan executed exactly as written.

The plan's verification probe #6 (`python -m pip install --dry-run -r requirements.txt`) is explicitly marked "network-dependent — skip in CI sandbox if unavailable" and was skipped per the plan's own instruction. All seven other cross-task probes ran green. Plans 00-02 through 00-05 will exercise the install via the Dockerfile build inside the container, which is the canonical verification environment per CLAUDE.md.

## Threat Flags

No new surface introduced beyond what the threat register already covers (T-00-01-01 through T-00-01-05 — all `mitigate` or `accept`-with-Phase-3-followup dispositions verified). The mitigations are in place:

- `.env` in `.gitignore` (T-00-01-01)
- `app/config.py` is the sole `os.environ` reader and `test_no_direct_env.py` enforces it (T-00-01-02)
- `APP_SECRET_KEY` / `APP_ENCRYPTION_KEY` have no defaults; `min_length=32` on the secret key (T-00-01-03)
- `extra="forbid"` rejects unknown env keys (T-00-01-04)
- `APP_ENCRYPTION_KEY` documented as comma-separated for future `MultiFernet` (T-00-01-05; rotation wiring is Phase 3 per disposition)

## Notes for Downstream Plans

- **Plan 00-02** (logging + app factory): import as `from app.config import settings`; consume `settings.LOG_FORMAT` and `settings.LOG_LEVEL` in `app/logging.py:configure_logging`. The `Settings` import side-effect-evaluates `Settings()` at module import — that's intentional; lifespan startup happens after this in `app/main.py`.
- **Plan 00-03** (db + migrations): `app/models/__init__.py` is currently empty; this plan fills it with imports of every model module so Alembic metadata is complete. `app/migrations/` doesn't exist yet — `tests/test_no_direct_env.py` already excludes that directory name, so alembic env.py's `os.environ` reads (if any) will not break this test.
- **Plan 00-04** (Dockerfile + entrypoint): the package skeleton is laid; the Dockerfile's `COPY ./app /app/app` step picks up the entire tree. `requirements.txt` is the only file `pip install -r` reads; `requirements-dev.txt` is for local-dev installs only (not baked into the production image). The single-worker comment in `app/services/scheduler.py` is location #2 of three — locations #1 (entrypoint.sh) and #3 (README.md) are this plan's siblings' responsibility.
- **Plan 00-05** (Makefile + tests + README): the `make test` target runs `docker compose exec coffee-snobbery pytest -x` — the two Wave 0 tests authored here will be the seed test suite. Plan 05 will add `tests/test_healthz.py` once the route exists.

## Self-Check: PASSED

- `pyproject.toml`: FOUND
- `requirements.txt`: FOUND
- `requirements-dev.txt`: FOUND
- `.env.example`: FOUND
- `.gitignore`: FOUND
- `.dockerignore`: FOUND
- `app/__init__.py`: FOUND
- `app/middleware/__init__.py`: FOUND
- `app/routers/__init__.py`: FOUND
- `app/services/__init__.py`: FOUND
- `app/services/scheduler.py`: FOUND
- `app/schemas/__init__.py`: FOUND
- `app/models/__init__.py`: FOUND
- `app/templates/.gitkeep`: FOUND
- `app/static/.gitkeep`: FOUND
- `app/config.py`: FOUND
- `tests/__init__.py`: FOUND
- `tests/conftest.py`: FOUND
- `tests/test_no_direct_env.py`: FOUND
- `tests/test_env_example.py`: FOUND
- Commit `19c7066` (Task 1): FOUND in git log
- Commit `a35827b` (Task 2): FOUND in git log
- Commit `d948696` (Task 3): FOUND in git log
- Cross-task verification probes 1–7 (excluding network-dependent probe 6 step 2): all green
