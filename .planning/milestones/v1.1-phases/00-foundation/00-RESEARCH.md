# Phase 0: Foundation - Research

**Researched:** 2026-05-17
**Domain:** Two-container greenfield bootstrap (FastAPI + Postgres 16) with Alembic, Tailwind standalone CLI, structlog JSON, single-worker uvicorn behind NGINX proxy-headers trust list.
**Confidence:** HIGH overall — every load-bearing decision is already locked in CONTEXT.md / STACK.md / ARCHITECTURE.md / PITFALLS.md; this research verifies the upstream details (Tailwind CLI binary URL pattern, structlog ProcessorFormatter wiring, Alembic env.py shape for SQLAlchemy 2.0 + psycopg 3, postgres:16-alpine HEALTHCHECK) and pins specific implementation steps the planner needs.

## Summary

This is a greenfield bootstrap phase with **zero application code on disk** today (only `CLAUDE.md`, `snobbery-gsd-prompt.md`, and the `.planning/` tree exist). The architectural work — what tables to ship, what pool knobs to set, single-worker rule, MultiFernet from day one, Tailwind CLI vs CDN, etc. — was already done during init and Phase 0 discuss. **Research here is verification, not exploration.** Every load-bearing technical decision came in from CONTEXT.md, STACK.md, or PITFALLS.md and is `[VERIFIED]` or `[CITED]` against upstream docs unless explicitly flagged.

The phase has exactly five deliverables that move together: (1) `docker-compose.yml` with two services + three named volumes + `pg_isready` healthcheck + `depends_on: condition: service_healthy`; (2) multi-stage `Dockerfile` (tailwind-builder → `python:3.12-slim` runtime, `postgresql-client-16` from PGDG apt, non-root UID 1000); (3) `entrypoint.sh` (alembic upgrade head + uvicorn `--workers 1 --proxy-headers --forwarded-allow-ips=$TRUSTED_PROXY_IPS`); (4) one mega-migration `0001_initial.py` that installs the three Postgres extensions, creates **five** tables (`users`, `bags`, `wishlist_entries`, `ai_recommendations`, `app_settings` — `wishlist_entries` is locked in CONTEXT D-01 and PROJECT.md row 12, do not omit it), and seeds 18 `app_settings` rows; (5) app skeleton (`config.py` as the sole `os.environ` reader, `db.py` engine with pool knobs `pool_size=10, max_overflow=5, pool_timeout=5, pool_pre_ping=True, pool_recycle=300`, `logging.py` structlog ProcessorFormatter JSON-by-default, `main.py` lifespan + StaticFiles + Jinja autoescape ON, two routes `/healthz` and `/`).

**Primary recommendation:** Build in seven thin slices in the order listed in §1 (Implementation Strategy). Two of the bigger landmines are non-obvious: the `bags.coffee_id` FK can't be hard-pointed at `coffees(id)` yet because Phase 4 hasn't built the catalog (recommendation: ship the column as `bigint NOT NULL` with no FK constraint, add the FK in Phase 4's first migration — forward-defensible); and the Tailwind CLI download URL pattern uses `releases/latest/download/...` not a pinned version, so plan-phase needs to decide whether to pin (recommended) for reproducibility.

## User Constraints (from CONTEXT.md)

### Locked Decisions

**First-migration scope and split:**
- **D-01**: `wishlist_entries` lands in the Phase 0 first-migration set. Matches PROJECT.md Key Decisions row 11. CRUD UI for wishlist lands later (Phase 4 or Phase 7); the table is here.
- **D-02**: One mega-migration `0001_initial.py`. Single file does three extensions, five tables, all seed inserts. Expected 200–300 LOC.
- **D-03**: Migration uses `op.execute("CREATE EXTENSION IF NOT EXISTS citext")` (and same for `pg_trgm`, `unaccent`) — idempotent.

**Docker / runtime architecture:**
- **D-04**: Multi-stage Dockerfile. Stage 1 (`tailwind-builder`): downloads Tailwind standalone CLI binary, runs `tailwindcss -i ./app/static/css/tailwind.src.css -o ./app/static/css/tailwind.<hash>.css --minify`. Stage 2 (`python:3.12-slim`) `COPY --from=tailwind-builder` of compiled CSS only.
- **D-05**: Non-root `app` user, UID 1000. Dockerfile: `RUN useradd -u 1000 -m app`, `USER app` before `CMD`.
- **D-06**: `postgresql-client-16` installed in the web image from PostgreSQL's apt repo (NOT slim default — would give Postgres 15 client and silently break nightly `pg_dump` per PITFALL SH-5).
- **D-07**: DB readiness via compose, not bash. DB service gets `HEALTHCHECK: pg_isready -U $POSTGRES_USER -d $POSTGRES_DB`; web service declares `depends_on: coffee-snobbery-db: condition: service_healthy`. `entrypoint.sh` therefore has NO wait-loop.
- **D-08**: `GET /healthz` does a DB-touching 1-row SELECT against a 2-second pool_timeout. Returns 200 / 503. Docker `HEALTHCHECK` on the web service calls this endpoint.
- **D-09**: docker-compose.yml publishes the web service on `127.0.0.1:8080:8000` only — never `0.0.0.0`.
- **D-10**: SQLAlchemy engine pool knobs (locked): `pool_size=10, max_overflow=5, pool_timeout=5, pool_pre_ping=True, pool_recycle=300`.

**App skeleton + routes:**
- **D-11**: Scaffold ALL `app/` subpackages in Phase 0 — `middleware/`, `routers/`, `services/` with empty `__init__.py` + one-line "owned by Phase N" docstring.
- **D-12**: Phase 0 ships exactly two HTTP routes: `GET /healthz` and `GET /` (renders `base.html` + `pages/index.html` with placeholder text).
- **D-13**: `base.html` is a real shell — doctype, viewport meta with `viewport-fit=cover`, dual `theme-color` meta (light cream + dark espresso per PITFALL PWA-5), Tailwind link, body palette classes, `{% block content %}`. NO HTMX/Alpine yet (Phase 1). NO `|safe` anywhere.
- **D-14**: `tailwind.config.js` ships palette baseline — `theme.extend.colors.cream` (50-950) and `theme.extend.colors.espresso` (50-950), `darkMode: 'media'`. Hex values tunable.
- **D-15**: Static asset path is content-hashed at build time. Dockerfile build stage emits `tailwind.<sha8>.css`. Jinja2 environment exposes `tailwind_css_path` global computed at startup by globbing `app/static/css/tailwind.*.css`.

**Logging:**
- **D-16**: structlog format is env-var-controlled. `LOG_FORMAT=json` (default) → `structlog.processors.JSONRenderer`. `LOG_FORMAT=console` → `structlog.dev.ConsoleRenderer`. Base context: `event`, `timestamp_iso`, `level`. Per-request `request_id` binding is Phase 1.

**app_settings seed rows (in `0001_initial.py`):**
- **D-17**: Seed liberally — Phase 0 owns the foundational `app_settings` row set. 18 rows locked (full list in §3 below).

**Tooling / dev ergonomics:**
- **D-18**: `Makefile` ships in Phase 0 wrapping common compose flows. Targets: `up`, `down`, `logs`, `psql`, `migrate`, `revision`, `test`, `shell`, `build`.
- **D-19**: `pyproject.toml` lands ruff + mypy tool configs. No GitHub Actions YAML yet (Phase 12). `tests/` directory + `conftest.py` skeleton + one smoke test asserting `GET /healthz` returns 200.

### Claude's Discretion

- Cookie names / signed-cookie serializer choice — Phase 1's concern, not Phase 0.
- Concrete column types beyond what spec enumerates (e.g. `users.username` as `citext UNIQUE NOT NULL`, `users.password_hash` as `text NOT NULL`, `users.is_admin` as `boolean NOT NULL DEFAULT false`, `users.created_at/updated_at` as `timestamptz NOT NULL DEFAULT now()`).
- **`bags.coffee_id` shape**: ship as `bigint NOT NULL` with NO FK constraint now (Phase 4 adds the FK in its own migration when `coffees` exists) — researcher recommendation; planner's final call.
- **`ai_recommendations` index choices**: `input_signature` btree (required by signature-comparison query), `(user_id, recommendation_type, generated_at DESC)` btree (required by "show me this user's latest coffee rec").
- Tailwind palette exact hex values across the 50-950 ramps — tunable in `/gsd-ui-phase` later.
- Whether Jinja2's `tailwind_css_path` is computed once at startup (recommended) or memoized per-request.
- Exact `pyproject.toml` ruff rule set + mypy strict knobs (researcher recommends `extend-select = ["E", "F", "I", "B", "UP", "S"]`, ruff format ON, mypy `strict_optional` + `disallow_untyped_defs`).
- `python:3.12-slim` digest pin — leave as tag for v1; Phase 12 hardening can tighten.

### Deferred Ideas (OUT OF SCOPE)

- CI YAML (GitHub Actions) — Phase 12.
- `FragmentCacheHeadersMiddleware`, `/debug/proxy`, structured-logger middleware that mints `request_id` — Phase 1.
- `/setup` route body + first-admin flow + flipping `setup_completed` — Phase 2.
- `MultiFernet` instance construction + `api_credentials` table — Phase 3 (env var `APP_ENCRYPTION_KEY` shape is established here; the wiring is Phase 3).
- Catalog tables (`coffees`, `equipment`, `recipes`, `roasters`, `flavor_notes`) — Phase 4.
- APScheduler + nightly `pg_dump` + photos tarball — Phase 8.
- PWA manifest + service worker + maskable icons — Phase 11 (the dual `theme-color` meta lands now to avoid PWA-5 flicker later).
- Real test coverage beyond `/healthz` smoke — Phase 12.
- Tailwind palette hex tuning — first `/gsd-ui-phase` pass.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **FOUND-01** | `docker compose up -d` from clean checkout brings up working app on host port 8080 with DB initialized | §1 step 1+2 (compose + Dockerfile), §5 (compose shape with `depends_on` healthcheck), §6 (smoke test) |
| **FOUND-02** | Two container services: `coffee-snobbery` (web) + `coffee-snobbery-db` (db) on `coffee-snobbery-net` | §5 (compose shape — service names + network) |
| **FOUND-03** | Named volumes: `coffee_snobbery_postgres_data`, `coffee_snobbery_photos`, `coffee_snobbery_backups` | §5 (compose shape — volumes section) |
| **FOUND-04** | Single uvicorn worker; documented loudly in README + entrypoint | §1 step 3 (entrypoint.sh), §4 (Dockerfile CMD), §7 risk-table for the three-place rule |
| **FOUND-05** | Alembic migrations auto-run on container start via `entrypoint.sh`; first run creates schema + seeds `app_settings` | §1 step 3+4 (entrypoint + Alembic env.py), §3 (migration content) |
| **FOUND-06** | Postgres extensions `citext`, `pg_trgm`, `unaccent` in first migration | §3 (CREATE EXTENSION as first ops in `0001_initial.py`) |
| **FOUND-07** | `postgresql-client-16` installed in web image (version-matched `pg_dump`) | §4 (Dockerfile — PGDG apt repo install of `postgresql-client-16`) |
| **FOUND-08** | App honors `X-Forwarded-Proto`/`X-Forwarded-For` from `TRUSTED_PROXY_IPS` trust list | §1 step 3 (uvicorn flags), §2 (Key Decisions — uvicorn 0.47 flags), §7 risk-table SH-6 |
| **FOUND-09** | `.env.example` documents all env vars with generation hints | §2 (env var inventory with one-liners), §6 (test: every var documented) |
| **FOUND-10** | pydantic-settings in `app/config.py`; no `os.environ` elsewhere | §1 step 5 (config module), §7 (planner concern — Phase 1 adds CI grep test) |
| **FOUND-11** | Structured logging via structlog with JSON output + request correlation IDs; auth events audit-tagged | §1 step 6 (logging module), §2 (structlog pattern verified), §7 risk-table (request_id middleware = Phase 1, but binding pattern + base context = Phase 0) |
| **FOUND-12** | Tailwind compiled by standalone CLI binary baked into Docker image (no Node, no npm); output served as content-hashed filename | §1 step 2 (Dockerfile multi-stage), §4 (tailwind-builder stage detail), §2 (CLI binary download URL) |
| **CAT-04** | `bags` table: `id`, `coffee_id`, `roast_date`, `weight_grams`, `opened_at`, `finished_at`, `notes`, `created_at`, `updated_at` (CRUD UI is Phase 4) | §3 (bags schema with all 9 spec columns + FK strategy) |
| **AI-02** | `ai_recommendations` table with full cost-observability column set | §3 (`ai_recommendations` schema with all 16+ columns including the 9 cost-observability columns mandated by COST-1) |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| HTTP request handling | API/Backend (FastAPI) | — | Server-rendered Jinja, no separate frontend tier. |
| Database persistence | Database (Postgres 16) | — | Single tenant, single DB. |
| Static asset serving | API/Backend (FastAPI `StaticFiles`) | — | No CDN tier in this deployment. Phase 4's photos use a custom router for ACL, but plain Tailwind CSS goes through `StaticFiles`. |
| CSS compilation | Build-time (Dockerfile `tailwind-builder` stage) | — | Compiled into the image; not a runtime concern. |
| Migrations | API/Backend container (alembic upgrade head on entrypoint) | — | Single-worker means no leader-election concern. |
| Configuration loading | API/Backend (pydantic-settings, single module `app/config.py`) | — | Sole `os.environ` reader by contract. |
| Logging output | API/Backend (structlog → stdout JSON) | Host (Docker log driver) | Container stdout/stderr captured by Docker; no log-shipping in v1. |
| TLS / HSTS | Host (NGINX reverse proxy) | — | App receives `X-Forwarded-Proto: https` only; never terminates TLS itself. |
| Health checking | API/Backend (`GET /healthz`) | Compose (`HEALTHCHECK` on web + db services) | Two layers — compose-level proves both up; app-level proves DB reachable from web. |

## Standard Stack

### Core (Phase 0 directly installs / configures)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12 | Runtime | `[VERIFIED: STACK.md §1]` Phase 0 of CLAUDE.md stack invariants — locked. |
| FastAPI | `>=0.136,<0.137` | Web framework | `[VERIFIED: PyPI structlog page + STACK.md]` Lifespan async-context-manager is the only supported startup/shutdown path (deprecated `@app.on_event`). |
| Starlette | `>=1.0,<2.0` | ASGI substrate | `[VERIFIED: STACK.md §1]` Pulled in transitively by FastAPI 0.136. 1.0 stable as of Mar 22 2026. |
| Uvicorn | `>=0.47,<0.48` | ASGI server | `[VERIFIED]` Need `--proxy-headers` and `--forwarded-allow-ips` flags. |
| SQLAlchemy | `>=2.0.49,<2.1` | ORM + engine | `[VERIFIED: PyPI sqlalchemy page, May 2026]` Use 2.0.x stable; 2.1 still beta. Typed `Mapped[...]` columns; `select()` constructs; no legacy `Query` API. |
| Alembic | `>=1.18,<2.0` | Migrations | `[VERIFIED: STACK.md §1]` Autogenerate handles `Mapped[...]` correctly. |
| psycopg | `psycopg[binary]>=3.3,<3.4` | Postgres driver | `[VERIFIED: WebSearch 2026-05-17]` URL form is `postgresql+psycopg://...`. Use psycopg 3, NOT psycopg2. `[binary]` extra installs prebuilt wheel. |
| Pydantic | `>=2.13,<3.0` | Validation + settings | `[VERIFIED: STACK.md §1]` v2 only. |
| pydantic-settings | `>=2.14,<3.0` | Env var reader | `[VERIFIED: STACK.md §1]` Single source for all env reads (FOUND-10). |
| Jinja2 | `>=3.1.6,<4` | Templating | `[VERIFIED: STACK.md §1]` Autoescape ON globally; never `\|safe`. |
| structlog | `>=25.5,<26` | Structured logging | `[VERIFIED: PyPI structlog page, latest 25.5.0 released Oct 27 2025]` ProcessorFormatter merges uvicorn/SQLAlchemy stdlib logs into the same JSON stream. |
| Postgres server image | `postgres:16-alpine` | Database | `[VERIFIED: STACK.md §1]` Postgres 16 locked by spec; `citext`, `pg_trgm`, `unaccent` are in postgres-contrib which is bundled. |

### Supporting (installed in Phase 0 because requirements.txt is complete from day one, not used until later phases)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| argon2-cffi | `>=25.1,<26` | Password hashing | Phase 2 (auth). |
| cryptography | `>=48,<49` | `Fernet` / `MultiFernet` | Phase 3 (encryption service). Env var `APP_ENCRYPTION_KEY` shape established now. |
| itsdangerous | `>=2.2,<3.0` | Signed cookies | Phase 1 (sessions middleware). |
| httpx | `>=0.28,<0.29` | HTTP client | Phase 7 (AI URL verification). |
| Pillow | `>=12.2,<13` | Image processing | Phase 4 (bag photo upload). |
| APScheduler | `>=3.11,<4` | In-process job scheduling | Phase 8. |
| anthropic | `>=0.102,<1.0` | Claude SDK | Phase 7. |
| openai | `>=2.37,<3.0` | OpenAI SDK | Phase 7. |
| python-multipart | `>=0.0.28,<0.1` | Form parsing | Phase 1+ (every POST). Required by FastAPI. |

### Development / tooling

| Library | Version | Purpose |
|---------|---------|---------|
| ruff | `>=0.15.13,<0.16` | Lint + format |
| mypy | `>=1.13,<2` | Type check |
| pytest | `>=9.0,<10` | Test runner |
| pytest-asyncio | latest | Async test support |
| pytest-cov | latest | Coverage on critical-path units |

### Alternatives Considered (rejected during research/discuss)

| Instead of | Could Use | Why rejected |
|------------|-----------|----------|
| psycopg[binary] 3.3 | psycopg2-binary | psycopg 3 has native async, modern packaging, actively developed. Spec doesn't pin a driver. |
| Tailwind standalone CLI | Tailwind Play CDN v4 | Play CDN v4 requires `'unsafe-inline'` for styles — breaks the strict CSP plan in Phase 1. CLI is a single static binary, honors spec's "no build pipeline" intent. (Locked decision per PROJECT.md.) |
| starlette `SessionMiddleware` | — | Cookie-only; spec requires table-backed sessions. Custom middleware ships in Phase 1. |
| stdlib `logging` alone | — | Would re-implement structlog's redactor chain. |
| MultiFernet from day 1 | Single Fernet | Rotation-ready encryption from first encrypted row. Adding key rotation later orphans previously-encrypted rows. (Locked.) |
| Single mega-migration | Three split migrations (extensions, tables, seeds) | Cleaner blame per concern, but adds alembic dep noise; user picked single file in CONTEXT D-02. |
| FK constraint on `bags.coffee_id` in Phase 0 | NULLABLE coffee_id, tighten in Phase 4 | Spec demands NOT NULL; forward-defensible is to ship `bigint NOT NULL` with no FK and have Phase 4 add the FK once `coffees` exists. |

**Installation (Phase 0 requirements.txt):**
```
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

**Dev requirements (`requirements-dev.txt` or `[project.optional-dependencies].dev` group):**
```
ruff>=0.15.13,<0.16
mypy>=1.13,<2
pytest>=9.0,<10
pytest-asyncio
pytest-cov
```

**Version verification:** Verify each pin before image build:
```bash
# In an interactive container or local venv:
pip install --dry-run -r requirements.txt
# Or: python -m pip index versions <package>
```
PyPI search confirmed during research: structlog 25.5.0 published 2025-10-27; SQLAlchemy 2.0.49 published 2026-04-03; latest libraries match STACK.md §1 versions.

## Architecture Patterns

### System Architecture Diagram

```
                       Host (VPS)
  ┌────────────────────────────────────────────────────────────────┐
  │  NGINX (HTTPS termination; sets X-Forwarded-Proto/For/Host)    │
  │       │                                                         │
  │       ▼   proxy_pass http://127.0.0.1:8080                      │
  │  ┌─────────────────────────── docker compose stack ──────────┐  │
  │  │  Network: coffee-snobbery-net (bridge)                    │  │
  │  │                                                            │  │
  │  │  coffee-snobbery (web)   coffee-snobbery-db (db)           │  │
  │  │  ┌─────────────────┐     ┌──────────────────────────────┐  │  │
  │  │  │ entrypoint.sh   │     │ postgres:16-alpine           │  │  │
  │  │  │  1. alembic     │     │ HEALTHCHECK: pg_isready      │  │  │
  │  │  │     upgrade hd  │ ──► │ env: POSTGRES_USER/PWD/DB    │  │  │
  │  │  │  2. exec uvicorn│     │ extensions: citext, pg_trgm, │  │  │
  │  │  │     --workers 1 │     │             unaccent         │  │  │
  │  │  │     --proxy-    │     │   (CREATE EXTENSION in       │  │  │
  │  │  │      headers    │     │    0001_initial.py)          │  │  │
  │  │  │     --forwarded │     └───────┬──────────────────────┘  │  │
  │  │  │     -allow-ips  │             │ volume:                 │  │
  │  │  │      $TRUST_IPS │             │ coffee_snobbery_        │  │
  │  │  └────────┬────────┘             │     postgres_data       │  │
  │  │           │                                                 │  │
  │  │  ┌────────▼────────────────────────────────┐               │  │
  │  │  │ uvicorn (1 worker)                      │               │  │
  │  │  │  └─ FastAPI app (app.main:app)          │               │  │
  │  │  │       ├ lifespan: open SQLAlchemy engine│               │  │
  │  │  │       ├ StaticFiles mount /static       │               │  │
  │  │  │       ├ Jinja2 env (autoescape ON)      │               │  │
  │  │  │       ├ route: GET /healthz (DB ping)   │               │  │
  │  │  │       └ route: GET / (Tailwind smoke)   │               │  │
  │  │  │ HEALTHCHECK: curl localhost:8000/healthz│               │  │
  │  │  └────┬────────┬───────────────────────────┘               │  │
  │  │       │        │                                            │  │
  │  │       │        │ Volumes (named):                           │  │
  │  │       │        ├─ coffee_snobbery_photos   → /app/data/    │  │
  │  │       │        │    photos (used Phase 4)                  │  │
  │  │       │        └─ coffee_snobbery_backups  → /app/data/    │  │
  │  │       │             backups (used Phase 8)                 │  │
  │  │       │                                                     │  │
  │  │       ▼ stdout → structlog JSON → docker log driver        │  │
  │  └────────────────────────────────────────────────────────────┘  │
  └────────────────────────────────────────────────────────────────┘

Build-time (Dockerfile, multi-stage):
  Stage 1 (tailwind-builder, debian-slim):
    curl tailwindcss-linux-x64 → /usr/local/bin/tailwindcss
    tailwindcss -i app/static/css/tailwind.src.css
                -o app/static/css/tailwind.<sha8>.css
                --minify
  Stage 2 (python:3.12-slim):
    apt-get install postgresql-client-16 (from PGDG repo)
    pip install -r requirements.txt
    COPY --from=tailwind-builder /app/static/css/tailwind.*.css
                                  → /app/app/static/css/
    useradd -u 1000 -m app; USER app
    ENTRYPOINT ["./entrypoint.sh"]
```

### Recommended Project Structure

```
coffee-snobbery/                       # repo root (NB: container name uses hyphen)
├── docker-compose.yml
├── Dockerfile
├── entrypoint.sh
├── .env.example
├── .gitignore                          # at minimum: .env, __pycache__/, *.egg-info, .ruff_cache, .mypy_cache
├── README.md
├── Makefile
├── pyproject.toml                      # ruff + mypy + pytest configs
├── requirements.txt
├── requirements-dev.txt                # or [project.optional-dependencies].dev
├── alembic.ini
├── tailwind.config.js
└── app/
    ├── __init__.py
    ├── main.py                         # FastAPI factory + lifespan + StaticFiles + routes
    ├── config.py                       # pydantic-settings — SOLE os.environ reader
    ├── db.py                           # SQLAlchemy 2.0 engine + sessionmaker (sync only in P0)
    ├── logging.py                      # structlog ProcessorFormatter + JSON/console renderer
    ├── models/
    │   ├── __init__.py                 # imports all models so Alembic metadata sees them
    │   ├── base.py                     # DeclarativeBase
    │   ├── user.py                     # users
    │   ├── bag.py                      # bags
    │   ├── wishlist_entry.py           # wishlist_entries
    │   ├── ai_recommendation.py        # ai_recommendations
    │   └── app_setting.py              # app_settings
    ├── middleware/
    │   └── __init__.py                 # docstring: "Cross-cutting middleware; owned by Phase 1"
    ├── routers/
    │   └── __init__.py                 # docstring: "HTTP routers; owned by Phase 2+"
    ├── services/
    │   ├── __init__.py                 # docstring: "Stateful logic; owned by Phase 3+"
    │   └── scheduler.py                # PLACEHOLDER — comment about single-worker rule + Phase 8 ownership
    ├── schemas/
    │   └── __init__.py                 # docstring: "Pydantic v2 form/AI schemas; owned by Phase 1+"
    ├── templates/
    │   ├── base.html                   # real shell — doctype, dual theme-color, Tailwind link
    │   └── pages/
    │       └── index.html              # placeholder content
    ├── static/
    │   └── css/
    │       ├── tailwind.src.css        # @tailwind base/components/utilities + custom layer
    │       └── tailwind.<sha8>.css     # built by Stage 1 of Dockerfile
    └── migrations/
        ├── env.py                      # SQLAlchemy 2.0 + psycopg 3 form
        ├── script.py.mako              # Alembic default
        └── versions/
            └── 0001_initial.py         # extensions + 5 tables + 18 app_settings seed rows

tests/
├── conftest.py                         # pytest fixtures (engine, TestClient)
└── test_healthz.py                     # single smoke test asserting GET /healthz → 200
```

### Pattern 1: FastAPI Lifespan for engine open/close

**What:** Open the SQLAlchemy engine at app startup (inside lifespan, AFTER alembic has run) and dispose at shutdown. NEVER use `@app.on_event("startup")` — deprecated in Starlette upstream.

**When to use:** Every Phase 0+ app factory. Phase 8 extends this with `scheduler.start() / scheduler.shutdown(wait=True)`.

**Example:**
```python
# app/main.py
# Source: https://fastapi.tiangolo.com/advanced/events/ (verified 2026-05-17)
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.db import engine, dispose_engine
from app.logging import configure_logging

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    configure_logging(format=settings.LOG_FORMAT, level=settings.LOG_LEVEL)
    # engine is module-level; just confirm it can connect
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    yield
    # Shutdown
    dispose_engine()

def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan, title="Snobbery")
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    # ... include routers
    return app

app = create_app()
```

### Pattern 2: structlog ProcessorFormatter wiring stdlib loggers

**What:** Configure structlog as the structured-logging frontend, route stdlib logging (uvicorn, FastAPI, SQLAlchemy) through `ProcessorFormatter` so every log line emits the same JSON shape.

**When to use:** Phase 0 `app/logging.py`. Phase 1 adds the `request_id` contextvar middleware that binds onto the call chain.

**Example:**
```python
# app/logging.py
# Source: https://www.structlog.org/en/stable/standard-library.html (verified 2026-05-17)
import logging
import logging.config
import structlog

def configure_logging(format: str = "json", level: str = "INFO") -> None:
    timestamper = structlog.processors.TimeStamper(fmt="iso", key="timestamp_iso")
    pre_chain = [
        structlog.contextvars.merge_contextvars,   # picks up request_id once Phase 1 binds it
        structlog.stdlib.add_log_level,
        structlog.stdlib.ExtraAdder(),
        timestamper,
    ]
    if format == "console":
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=pre_chain + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "structured": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processors": [
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    renderer,
                ],
                "foreign_pre_chain": pre_chain,
            },
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "formatter": "structured",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "": {"handlers": ["stdout"], "level": level, "propagate": True},
            "uvicorn.error": {"handlers": ["stdout"], "level": level, "propagate": False},
            "uvicorn.access": {"handlers": ["stdout"], "level": level, "propagate": False},
        },
    })
```

### Pattern 3: SQLAlchemy 2.0 sync engine with locked pool knobs

**What:** Module-level engine + sessionmaker; explicit pool knobs per PITFALL SH-2 and CONTEXT D-10.

**When to use:** Every sync DB call from Phase 0 onward. Phase 7 adds an async path for AI calls only; Phase 0 doesn't need it.

**Example:**
```python
# app/db.py
# Source: https://docs.sqlalchemy.org/en/20/core/engines.html (verified 2026-05-17)
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,                  # postgresql+psycopg://...
    pool_size=10,                            # CONTEXT D-10, PITFALL SH-2
    max_overflow=5,
    pool_timeout=5,
    pool_pre_ping=True,
    pool_recycle=300,
    echo=False,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass

def dispose_engine() -> None:
    engine.dispose()
```

### Pattern 4: Alembic env.py for SQLAlchemy 2.0 + psycopg 3

**What:** Override `sqlalchemy.url` from `settings.DATABASE_URL` at runtime (so the value in `alembic.ini` is a placeholder); set `target_metadata` from `Base.metadata`; ensure all models are imported so the metadata is populated.

**Example:**
```python
# app/migrations/env.py
# Source: Alembic generic template (verified 2026-05-17) + STACK.md §3.3
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.db import Base
import app.models   # noqa: F401 — registers every model with Base.metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override the sqlalchemy.url in alembic.ini with the runtime DATABASE_URL.
# alembic.ini ships with `sqlalchemy.url = ` (empty) — the value lives in pydantic-settings.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

target_metadata = Base.metadata

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,                  # fresh connection per migration run
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

### Anti-Patterns to Avoid

- **`async def` handler calling sync `Session.execute(...)`.** Blocks the event loop. Phase 0 ships ONLY sync handlers (`def healthz(...)`, `def home(...)`). Phase 7 introduces async handlers — they must use `await asyncio.to_thread(...)` for DB calls or a separate async engine.
- **`@app.on_event("startup")` / `@app.on_event("shutdown")`.** Deprecated in Starlette 1.0; will be removed. Use `lifespan` exclusively.
- **`os.environ["FOO"]` outside `app/config.py`.** Violates FOUND-10. Phase 1 lands the CI grep test enforcing this; Phase 0 must not seed any violations.
- **Reading `os.environ` inside the migration's `env.py` for `DATABASE_URL`.** The pattern above reads it via `settings.DATABASE_URL` (which `app/config.py` resolved from `os.environ` exactly once).
- **`{% autoescape false %}` or `{{ x|safe }}` in any template.** No exceptions in Phase 0.
- **Mounting `app/static/photos` via `StaticFiles`.** Phase 4 owns photos via a custom router. `StaticFiles` in Phase 0 mounts only the static CSS/JS directory, NOT the photos volume.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Wait for Postgres to be ready | Bash `until pg_isready` loop in entrypoint.sh | docker-compose `depends_on: condition: service_healthy` + Postgres `HEALTHCHECK` | Compose-native; one less moving part; survives partial restarts. (CONTEXT D-07.) |
| Env var loading | `os.environ["FOO"]` scattered across modules | `pydantic-settings.BaseSettings` subclass in `app/config.py` | Typed reads, `.env` loading, single source of truth. (FOUND-10.) |
| Structured logging | Custom JSON formatter on stdlib `logging.Formatter` | `structlog` + `ProcessorFormatter` | Battle-tested processor chain; redaction is testable; uvicorn/SQLAlchemy logs merge into one stream. (FOUND-11.) |
| Tailwind compilation | Pre-build CSS by hand + commit | Tailwind standalone CLI binary in builder stage | Single static executable, no Node, no npm; CSP-friendly output served from `app/static`. (FOUND-12.) |
| Migration ordering / DDL | Hand-rolled SQL files run by entrypoint | Alembic `upgrade head` | Reversible, version-tracked, autogeneration support, idempotent. (FOUND-05.) |
| Image hashing for static assets | Hand-implement digest + filename swap | Build-time `--minify` output named `tailwind.<sha8>.css`; Jinja2 global computed at startup by glob | One-line filesystem glob at import; no per-request hashing. (CONTEXT D-15.) |
| Health check polling | Custom `/healthz` that returns 200 without touching DB | DB-touching `/healthz` with explicit 2s pool_timeout | Proves both web AND db reachable. (CONTEXT D-08.) |
| HTTP-server proxy header trust | Read `X-Forwarded-Proto` in a custom middleware | uvicorn `--proxy-headers --forwarded-allow-ips=…` flags | Honored by uvicorn before the ASGI stack ever runs; works correctly with `Secure` cookies set in Phase 1. (FOUND-08, PITFALL SH-6.) |

**Key insight:** This is a phase where "boring is correct." Every problem above has a well-trodden one-line solution. The temptation when bootstrapping is to reach for shell wait-loops, ad-hoc logging, hand-rolled migrations — all of which work in development and silently fail in production (NGINX behind TLS, container restart timing, version skew on `pg_dump`). Use the standard answer everywhere.

## Runtime State Inventory

*(Not applicable — this is a greenfield bootstrap, not a rename/refactor/migration phase. No existing runtime state exists.)*

## Common Pitfalls

The full landmine catalog lives in `.planning/research/PITFALLS.md`. Phase 0 specifically carries these:

### Pitfall SH-1: APScheduler default `MemoryJobStore` loses jobs on restart
**What goes wrong:** A future Phase 8 scheduler module that uses APScheduler defaults silently drops every scheduled job on container restart; nightly AI runs and backups go missing for days.
**Why it happens:** Defaults are `MemoryJobStore` + `misfire_grace_time=1s`. Restart at 23:59 → 00:00 trigger missed → no recovery.
**How to avoid:** Phase 0 ships a placeholder `app/services/scheduler.py` with a top-of-file comment block warning future implementers about `SQLAlchemyJobStore` + `misfire_grace_time=3600` + `coalesce=True`. The fix lands in Phase 8.
**Warning signs:** Will only be observable in Phase 8 testing; Phase 0 cannot trigger this directly. The defensive comment is the Phase 0 deliverable.

### Pitfall SH-2: Postgres connection pool exhaustion under HTMX traffic + AI calls
**What goes wrong:** SQLAlchemy defaults (`pool_size=5, max_overflow=10`) can be exhausted by a single home page render (6 lazy-loaded sections × in-flight AI call).
**Why it happens:** Each FastAPI sync handler holds a DB session for the duration. Two users + AI in flight = pool empty + 30s `pool_timeout` → 500s.
**How to avoid:** Phase 0 sets explicit knobs (`pool_size=10, max_overflow=5, pool_timeout=5, pool_pre_ping=True, pool_recycle=300`) per CONTEXT D-10. `pool_timeout=5` (NOT 30) is deliberate — fail fast rather than block. `pool_pre_ping=True` defends against stale connections after long idle.
**Warning signs:** `TimeoutError: QueuePool limit reached` in logs (won't appear in Phase 0 because there's no real traffic, but the knobs are set now).

### Pitfall SH-5: `pg_dump` version mismatch
**What goes wrong:** Default `postgresql-client` package in `python:3.12-slim` apt is Postgres 15; DB server is 16. Phase 8 nightly `pg_dump` fails with `server version: 16.x; pg_dump version: 15.x`. Backups silently empty.
**Why it happens:** Debian/Ubuntu slim ships an older client by default.
**How to avoid:** Install `postgresql-client-16` from PostgreSQL's official APT repository (PGDG) in the Dockerfile. Verified install method in §4.
**Warning signs:** Smoke test asserts `pg_dump --version` inside the web container shows 16.x, matching the DB container's `SELECT version();`.

### Pitfall SH-6: `X-Forwarded-Proto` not honored → `Secure` cookies dropped
**What goes wrong:** Without uvicorn's `--proxy-headers` flag, FastAPI sees `scheme=http` even when NGINX terminates HTTPS. Cookies set with `Secure` flag are then refused by the browser on next HTTPS request → invisible auth failures, redirect loops.
**Why it happens:** uvicorn defaults to "don't trust any proxy header" because trusting them unconditionally is a security hole.
**How to avoid:** Phase 0 entrypoint.sh launches uvicorn with `--proxy-headers --forwarded-allow-ips="$TRUSTED_PROXY_IPS"`. The trust list is `127.0.0.1` because compose binds the web service to `127.0.0.1:8080:8000` (CONTEXT D-09) — NGINX runs on the host and connects from localhost.
**Warning signs:** Phase 1 ships `/debug/proxy` to confirm `request.url.scheme == "https"` end-to-end. Phase 0 just sets the flags correctly.

### Pitfall COST-1: Cost-observability columns missing from `ai_recommendations`
**What goes wrong:** Phase 7 ships AI service without per-call cost telemetry; the first surprise Anthropic bill arrives without any way to attribute spend per recommendation type / provider / user. Retrofitting columns on a populated table is painful.
**Why it happens:** "We'll add it later" — but later never comes until the bill does.
**How to avoid:** All 9 cost-observability columns land in `ai_recommendations` in `0001_initial.py` even though they aren't written until Phase 7. The full column list is in §3 below.
**Warning signs:** Smoke test against the migration asserts every cost-observability column exists with the right type and nullability.

### Pitfall PWA-5: Dual `theme-color` meta missing → status bar flickers on dark-mode launch
**What goes wrong:** Phase 11 ships PWA but `base.html` has only a single `theme_color` from the manifest. iOS uses the manifest value at launch then redraws to dark — a visible flicker.
**How to avoid:** Phase 0 ships dual `theme-color` meta tags in `base.html` even before the manifest exists:
```html
<meta name="theme-color" content="#FAF7F2" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#1A1110" media="(prefers-color-scheme: dark)">
```
Phase 11's manifest doesn't fight the meta tags; the meta tags win at first paint.

## Schema Design for First Migration

The migration `0001_initial.py` is a single file that runs as one transaction (`op.execute` doesn't auto-COMMIT, but Alembic wraps the whole upgrade in one transaction by default — confirm by checking that `transaction_per_migration` is not set in `alembic.ini`).

### Operation order (load-bearing — extensions must run before column types that depend on them)

```python
def upgrade() -> None:
    # 1) Postgres extensions (FOUND-06; CONTEXT D-03; idempotent via IF NOT EXISTS)
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    # 2) users  — referenced by ai_recommendations.user_id and wishlist_entries.user_id
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("username", postgresql.CITEXT, nullable=False, unique=True),
        sa.Column("email", postgresql.CITEXT, nullable=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("is_admin", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True, postgresql_where=sa.text("email IS NOT NULL"))

    # 3) bags  — coffee_id FK deferred to Phase 4 when coffees table exists
    op.create_table(
        "bags",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("coffee_id", sa.BigInteger, nullable=False),           # FK added in Phase 4 migration
        sa.Column("roast_date", sa.Date, nullable=True),
        sa.Column("weight_grams", sa.Integer, nullable=True),
        sa.Column("opened_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_bags_coffee_id", "bags", ["coffee_id"])           # supports "bags of this coffee" lookup

    # 4) wishlist_entries  — present from day one per CONTEXT D-01 / PROJECT row 12
    op.create_table(
        "wishlist_entries",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("coffee_name", sa.Text, nullable=False),
        sa.Column("roaster_name", sa.Text, nullable=True),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("source", sa.Text, nullable=True),                      # e.g., "ai_recommendation", "manual"
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.Column("added_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("purchased_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_wishlist_entries_user_id", "wishlist_entries", ["user_id"])

    # 5) ai_recommendations  — full AI-02 column set INCLUDING cost-observability (COST-1)
    op.create_table(
        "ai_recommendations",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recommendation_type", sa.Text, nullable=False),       # enum-as-text: 'coffee'|'equipment'|'paste_rank'|'sweet_spots'
        sa.Column("input_signature", sa.Text, nullable=False),
        sa.Column("response_json", postgresql.JSONB, nullable=False),
        sa.Column("provider_used", sa.Text, nullable=False),             # 'anthropic'|'openai'
        sa.Column("model_used", sa.Text, nullable=False),                # e.g. 'claude-opus-4-7'
        sa.Column("tool_version", sa.Text, nullable=True),               # e.g. 'web_search_20250305'
        sa.Column("tokens_input", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_output", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_input_search", sa.Integer, nullable=False, server_default="0"),     # COST-1
        sa.Column("web_search_count", sa.Integer, nullable=False, server_default="0"),         # COST-1
        sa.Column("url_verified", sa.Boolean, nullable=True),             # null until verification background task runs
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("generated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("generated_by", sa.Text, nullable=False),               # 'scheduler'|'manual_refresh'
        sa.Column("error_status", sa.Text, nullable=True),                # nullable; populated only on failure
    )
    op.create_index("ix_ai_recs_input_signature", "ai_recommendations", ["input_signature"])
    op.create_index(
        "ix_ai_recs_user_type_generated",
        "ai_recommendations",
        ["user_id", "recommendation_type", sa.text("generated_at DESC")],
    )

    # 6) app_settings  — key-value runtime config
    op.create_table(
        "app_settings",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("value", sa.Text, nullable=True),                       # JSON-encoded string or NULL
        sa.Column("value_type", sa.Text, nullable=False),                 # 'string'|'int'|'float'|'bool'|'json'|'null'
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_by_user_id", sa.BigInteger, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )

    # 7) Seed app_settings rows (CONTEXT D-17 — 18 rows)
    op.bulk_insert(app_settings_table, [
        {"key": "recommendation_region", "value": "US", "value_type": "string", "description": "Geographic scope for live coffee search; comma-separated region codes or 'any'."},
        {"key": "min_sessions_for_ai", "value": "3", "value_type": "int", "description": "AI-7 cold-start gate: minimum brew_sessions count per user."},
        {"key": "min_flavor_notes_for_ai", "value": "5", "value_type": "int", "description": "AI-7 cold-start gate: minimum distinct flavor_notes observed per user."},
        {"key": "ai_primary_max_searches", "value": "5", "value_type": "int", "description": "COST-5: max_uses cap for primary web-search."},
        {"key": "ai_broadened_max_searches", "value": "3", "value_type": "int", "description": "COST-5: max_uses cap for broadened fallback."},
        {"key": "ai_tool_version_anthropic", "value": "web_search_20250305", "value_type": "string", "description": "AI-5: Anthropic web-search tool version; editable from admin."},
        {"key": "ai_tool_version_openai", "value": "web_search", "value_type": "string", "description": "AI-5: OpenAI web-search tool version (non-preview)."},
        {"key": "ai_provider_default", "value": "anthropic", "value_type": "string", "description": "Default AI provider when both keys are enabled."},
        {"key": "last_ai_run_status", "value": "never_run", "value_type": "string", "description": "COST-3: last AI scheduler run status; surfaced in admin health panel."},
        {"key": "last_backup_status", "value": "never_run", "value_type": "string", "description": "Phase 8 health panel."},
        {"key": "last_backup_at", "value": None, "value_type": "null", "description": "Phase 8 health panel."},
        {"key": "setup_completed", "value": "false", "value_type": "bool", "description": "SEC-5: read under SELECT...FOR UPDATE by /setup."},
        {"key": "photo_max_bytes", "value": "5242880", "value_type": "int", "description": "Phase 4: max bag photo upload size (bytes); 5 MiB."},
        {"key": "csv_import_max_rows", "value": "5000", "value_type": "int", "description": "Phase 5: max rows accepted per brew session CSV import."},
        {"key": "home_recent_brews_limit", "value": "10", "value_type": "int", "description": "Phase 6: how many recent brews on home page."},
        {"key": "home_top_coffees_limit", "value": "5", "value_type": "int", "description": "Phase 6: top-N coffees by avg rating."},
        {"key": "home_top_coffees_min_sessions", "value": "2", "value_type": "int", "description": "Phase 6: minimum sessions for a coffee to qualify."},
        {"key": "home_top_flavors_min_rating", "value": "4.0", "value_type": "float", "description": "Phase 6: rating floor for top-flavor-descriptors query."},
        {"key": "home_sweetspot_min_sessions", "value": "3", "value_type": "int", "description": "Phase 6: minimum sessions for a sweet-spot cell."},
    ])

def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_table("ai_recommendations")
    op.drop_table("wishlist_entries")
    op.drop_table("bags")
    op.drop_table("users")
    # Extensions left in place — dropping them would break other databases on the same cluster.
```

### Notes on schema choices (planner decides finals)

- **`id` as `BigInteger` not `UUID`.** The spec mentions UUID for some tables and integer for others; the locked-in pattern across PROJECT.md / CLAUDE.md is consistent integer surrogate keys. Researcher recommends `BigInteger` PK with `IDENTITY` (Postgres-native sequence) across all tables — simpler joins, smaller index size, no UUID-generation extension needed. Planner's call.
- **`citext` extension is used by `users.username` and `users.email`.** Therefore the `CREATE EXTENSION citext` MUST run before `CREATE TABLE users`. Order matters.
- **`bags.coffee_id` has NO FK constraint in Phase 0.** Phase 4 adds the FK in its own migration (after `coffees` exists). Researcher recommendation: ship `bigint NOT NULL`; planner can choose NULLABLE-then-tighten if preferred.
- **`ai_recommendations.recommendation_type` and `app_settings.value_type` are `text` not enums.** Postgres enum types lock the value list at migration time and require an ALTER for additions; text + CHECK constraint or text + application-side validation is more flexible. Planner picks.
- **Indexes:** Phase 0 ships these. More can be added in later migrations.
  - `users.username` UNIQUE (implicit via the column constraint)
  - `users.email` UNIQUE WHERE NOT NULL (partial index)
  - `bags.coffee_id` btree
  - `wishlist_entries.user_id` btree
  - `ai_recommendations.input_signature` btree
  - `ai_recommendations(user_id, recommendation_type, generated_at DESC)` btree

## Dockerfile Strategy

Multi-stage build per CONTEXT D-04 / D-05 / D-06. Stage 1 isolates Tailwind tooling; Stage 2 is the lean runtime.

```dockerfile
# syntax=docker/dockerfile:1.7
# --- Stage 1: Tailwind builder -----------------------------------------------
FROM debian:bookworm-slim AS tailwind-builder

ARG TAILWIND_VERSION=v4.3.0
ARG TARGETARCH

# Install curl (the only thing this stage needs)
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Download the standalone CLI binary. Filename pattern: tailwindcss-{platform}-{arch}
# Source: https://tailwindcss.com/blog/standalone-cli + GitHub releases (verified 2026-05-17)
RUN set -eux; \
    case "${TARGETARCH:-amd64}" in \
      amd64) bin=tailwindcss-linux-x64 ;; \
      arm64) bin=tailwindcss-linux-arm64 ;; \
      *) echo "unsupported arch: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/tailwindlabs/tailwindcss/releases/download/${TAILWIND_VERSION}/${bin}" -o /usr/local/bin/tailwindcss; \
    chmod +x /usr/local/bin/tailwindcss

WORKDIR /build
COPY tailwind.config.js ./
COPY app/static/css/tailwind.src.css ./app/static/css/tailwind.src.css
COPY app/templates ./app/templates                  # content scan for tree-shaking

# Compute SHA8 of source, emit content-hashed output filename.
RUN set -eux; \
    HASH="$(sha256sum app/static/css/tailwind.src.css | cut -c1-8)"; \
    tailwindcss \
      -i app/static/css/tailwind.src.css \
      -o app/static/css/tailwind.${HASH}.css \
      --minify; \
    echo "Built: app/static/css/tailwind.${HASH}.css"

# --- Stage 2: Python runtime -------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# Install postgresql-client-16 from PostgreSQL's official APT repo (PITFALL SH-5).
# Source: https://wiki.postgresql.org/wiki/Apt
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl gnupg lsb-release; \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /etc/apt/keyrings/postgresql.gpg; \
    echo "deb [signed-by=/etc/apt/keyrings/postgresql.gpg] https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends postgresql-client-16; \
    apt-get purge -y --auto-remove curl gnupg lsb-release; \
    rm -rf /var/lib/apt/lists/*

# Non-root app user (CONTEXT D-05; PITFALL SH-4 forward-defense)
RUN useradd -u 1000 -m -s /bin/bash app

WORKDIR /app

# Install Python deps before COPYing the rest so layer caches survive code edits.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Copy application code
COPY --chown=app:app . .

# Copy Tailwind-compiled CSS from the builder stage (overwrites the placeholder src file's directory)
COPY --from=tailwind-builder --chown=app:app /build/app/static/css/tailwind.*.css ./app/static/css/

# Make entrypoint executable
RUN chmod +x entrypoint.sh

USER app
EXPOSE 8000

# Healthcheck calls our /healthz endpoint (CONTEXT D-08).
# curl is installed above; --fail returns non-zero on 4xx/5xx so Docker marks unhealthy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

ENTRYPOINT ["./entrypoint.sh"]
```

**Why each stage exists:**
- **Stage 1 (tailwind-builder):** Isolates the Tailwind binary, source CSS, and templates needed for tree-shaking. The runtime image carries zero Tailwind tooling — just the compiled output. Saves ~50MB and removes a build dependency from the production image. `--mount=type=cache` is intentionally NOT used (simpler, and Tailwind compiles fast).
- **Stage 2 (runtime):** `python:3.12-slim` base. Installs `postgresql-client-16` from PGDG (NOT slim's default which is Postgres 15 → PITFALL SH-5). Pip install layer is cached separately from code COPY so dependency churn doesn't invalidate the whole build. Non-root user UID 1000 matches typical host deploy user. `curl` is installed in Stage 2 only for the HEALTHCHECK; the apt cleanup retains it via `--no-install-recommends`.

**Note on curl in Stage 2:** the `apt-get purge -y --auto-remove curl gnupg lsb-release` line removes curl after the PGDG install. The HEALTHCHECK then can't use curl. **Fix:** keep curl installed, OR replace the HEALTHCHECK CMD with a Python one-liner: `python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=2).status==200 else 1)"`. Researcher recommendation: keep curl (cheaper), revise the apt cleanup to not purge it. Planner picks.

**Dockerfile open question — flagged for plan-phase:**
- Tailwind version pin: ARG `TAILWIND_VERSION=v4.3.0` is a fixed pin; CONTEXT.md doesn't specify a version. Planner decides whether to pin v4.3.0, pin a later v4.x, or use `releases/latest/download/...` (NOT recommended — non-reproducible).

## docker-compose.yml Shape

Per CONTEXT D-07 / D-09 and FOUND-02 / FOUND-03.

```yaml
# docker-compose.yml
name: coffee-snobbery

services:
  coffee-snobbery-db:
    image: postgres:16-alpine
    container_name: coffee-snobbery-db
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - coffee_snobbery_postgres_data:/var/lib/postgresql/data
    networks:
      - coffee-snobbery-net
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 10s
    # NB: no `ports:` — DB is not exposed to host (FOUND-02 internal only)

  coffee-snobbery:
    image: coffee-snobbery:latest
    build:
      context: .
      dockerfile: Dockerfile
    container_name: coffee-snobbery
    restart: unless-stopped
    depends_on:
      coffee-snobbery-db:
        condition: service_healthy            # CONTEXT D-07
    env_file:
      - .env
    environment:
      # All other env vars come from .env; these are computed here for clarity.
      DATABASE_URL: postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@coffee-snobbery-db:5432/${POSTGRES_DB}
    volumes:
      - coffee_snobbery_photos:/app/data/photos        # Phase 4 writes here
      - coffee_snobbery_backups:/app/data/backups      # Phase 8 writes here
    networks:
      - coffee-snobbery-net
    ports:
      - "127.0.0.1:8080:8000"                          # CONTEXT D-09 — never 0.0.0.0

networks:
  coffee-snobbery-net:
    driver: bridge
    name: coffee-snobbery-net

volumes:
  coffee_snobbery_postgres_data:
    name: coffee_snobbery_postgres_data
  coffee_snobbery_photos:
    name: coffee_snobbery_photos
  coffee_snobbery_backups:
    name: coffee_snobbery_backups
```

**entrypoint.sh:**

```bash
#!/usr/bin/env bash
# Snobbery container entrypoint.
#
# IMPORTANT: This service MUST run with exactly one uvicorn worker. APScheduler
# (Phase 8) is in-process and module-level AI locks (Phase 7) require single-process.
# A future `--workers 4` would fire every nightly job 4x and bill 4x the AI cost.
# This is reinforced in README.md and app/services/scheduler.py.
set -euo pipefail

# 1) Run migrations — DB is already healthy by the time this runs (compose depends_on)
alembic upgrade head

# 2) Launch uvicorn behind the proxy-headers trust list (FOUND-08, PITFALL SH-6)
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips "${TRUSTED_PROXY_IPS:-127.0.0.1}"
```

## Implementation Strategy

Recommended step order (seven thin slices). Each slice is verifiable on its own before moving to the next.

### Step 1: Compose + Dockerfile skeleton (FOUND-01, FOUND-02, FOUND-03, FOUND-07)
- Author `docker-compose.yml` per §5 shape.
- Author `Dockerfile` (Stage 2 only initially — Stage 1 added in Step 2).
- Author `.env.example` per §2 inventory.
- Author bare `entrypoint.sh` that just `exec uvicorn ... --workers 1 --proxy-headers ...` (no alembic call yet).
- Author trivial `app/main.py` with a single `GET /` that returns `{"status":"bootstrap"}`.
- Author trivial `requirements.txt` with just `fastapi`, `uvicorn[standard]`.
- **Verify:** `docker compose up -d --build`, then `curl http://127.0.0.1:8080/` returns 200. `docker compose ps` shows both services up; web is healthy after start_period.

### Step 2: Tailwind builder stage (FOUND-12, CONTEXT D-04, D-13, D-14, D-15)
- Author `tailwind.config.js` per CONTEXT D-14 (palette baseline + `darkMode: 'media'`).
- Author `app/static/css/tailwind.src.css` with `@tailwind base; @tailwind components; @tailwind utilities;` plus the custom layer for the 16px input rule (Phase 5 needs it; landing it now is cheap).
- Author `app/templates/base.html` per CONTEXT D-13 (real shell, dual `theme-color`, Tailwind link via `tailwind_css_path` global, no HTMX/Alpine yet).
- Author `app/templates/pages/index.html` with the placeholder copy.
- Add Stage 1 (`tailwind-builder`) to `Dockerfile` per §4.
- Mount `StaticFiles` at `/static` in `app/main.py`; configure Jinja2 templates with autoescape ON.
- Compute `tailwind_css_path` global at app startup by globbing `app/static/css/tailwind.*.css` (single result).
- **Verify:** `docker compose build` produces an image with `app/static/css/tailwind.<sha8>.css`; `curl http://127.0.0.1:8080/` returns HTML referencing the hashed file; `curl http://127.0.0.1:8080/static/css/tailwind.<sha8>.css` returns CSS with a sensible byte count (>5KB, <100KB after minify).

### Step 3: Config + logging plumbing (FOUND-09, FOUND-10, FOUND-11, CONTEXT D-16)
- Author `app/config.py` (pydantic-settings `BaseSettings` subclass with every env var from §2). This is the SOLE `os.environ` reader.
- Author `app/logging.py` per §Pattern 2 (structlog ProcessorFormatter, JSON default, console when `LOG_FORMAT=console`).
- Wire `configure_logging(...)` into the `lifespan` startup branch in `app/main.py`.
- Add `LOG_FORMAT`, `LOG_LEVEL`, `TRUSTED_PROXY_IPS`, `APP_TIMEZONE`, `APP_SECRET_KEY`, `APP_ENCRYPTION_KEY`, `BACKUP_RETENTION_DAYS`, `DATABASE_URL`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` to `.env.example` with the generation hints below.
- **Verify:** `docker compose logs coffee-snobbery` shows one-per-line JSON like `{"event":"app.startup","timestamp_iso":"2026-05-17T...","level":"info"}`. `LOG_FORMAT=console docker compose up` shows colored output instead.

**`.env.example` content (FOUND-09):**
```bash
# Postgres
POSTGRES_USER=snobbery
POSTGRES_PASSWORD=                  # generate: openssl rand -hex 32
POSTGRES_DB=snobbery
# Wired into the web service from POSTGRES_* above:
DATABASE_URL=postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@coffee-snobbery-db:5432/${POSTGRES_DB}

# App secrets
# generate: python -c "import secrets; print(secrets.token_urlsafe(64))"
APP_SECRET_KEY=

# generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Comma-separated list (first = primary for encryption, all attempted for decryption).
# Phase 3 wires the MultiFernet construction; Phase 0 only requires the env var to be set.
APP_ENCRYPTION_KEY=

# Proxy / runtime
TRUSTED_PROXY_IPS=127.0.0.1         # comma-separated list of upstream IPs uvicorn will trust for X-Forwarded-* headers
APP_TIMEZONE=America/Chicago        # IANA name; consumed by APScheduler (Phase 8)
BACKUP_RETENTION_DAYS=14            # consumed by Phase 8 backup job
LOG_LEVEL=INFO                      # DEBUG | INFO | WARNING | ERROR
LOG_FORMAT=json                     # json (default) | console
```

### Step 4: SQLAlchemy + Alembic + initial migration (FOUND-05, FOUND-06, CAT-04, AI-02)
- Author `app/db.py` per §Pattern 3 (engine + sessionmaker, locked pool knobs).
- Author `app/models/base.py` (DeclarativeBase) and per-entity model files in `app/models/{user,bag,wishlist_entry,ai_recommendation,app_setting}.py`. `app/models/__init__.py` re-imports all so Alembic metadata is populated.
- Run `alembic init app/migrations` once locally; replace the generated `env.py` with §Pattern 4. Edit `alembic.ini` to remove `sqlalchemy.url` (override comes from `env.py`).
- Hand-author `0001_initial.py` per §3. **Do NOT use autogenerate** for the first migration — autogenerate doesn't emit `CREATE EXTENSION` and gets the column ordering wrong for cross-table FKs.
- Update `entrypoint.sh` to run `alembic upgrade head` before `exec uvicorn`.
- **Verify:** `docker compose down -v && docker compose up -d --build`. `docker compose exec coffee-snobbery-db psql -U $POSTGRES_USER -d $POSTGRES_DB -c "\dx"` shows all three extensions. `\dt` shows all five tables. `SELECT count(*) FROM app_settings;` returns 18.

### Step 5: Healthcheck route (FOUND-01, CONTEXT D-08)
- Author `app/routers/__init__.py` (just the empty docstring per CONTEXT D-11) — DO NOT create a `routers/healthz.py`; the route is small enough to live in `app/main.py` for now (or inline in a `routers/system.py` if the planner prefers structure).
- Implement `GET /healthz`: open a session, `session.execute(text("SELECT 1"))` with 2s timeout, return 200 / 503.
- Wire the Docker HEALTHCHECK in the Dockerfile per §4.
- **Verify:** `docker compose exec coffee-snobbery curl -fsS http://127.0.0.1:8000/healthz` returns `{"status":"ok"}`. Stop the DB: `docker compose stop coffee-snobbery-db` → web container's HEALTHCHECK should flip to unhealthy within 30s, and `curl /healthz` returns 503.

### Step 6: Tooling polish (CONTEXT D-18, D-19)
- Author `Makefile` with targets: `up`, `down`, `logs`, `psql`, `migrate`, `revision`, `test`, `shell`, `build`.
- Author `pyproject.toml` with `[tool.ruff]` (format ON, `extend-select = ["E","F","I","B","UP","S"]`), `[tool.mypy]` (`strict_optional`, `disallow_untyped_defs`), `[tool.pytest.ini_options]` (`testpaths = ["tests"]`).
- Author `tests/conftest.py` (TestClient fixture for FastAPI) and `tests/test_healthz.py` (single smoke test).
- Author `requirements-dev.txt` with ruff/mypy/pytest pins.
- **Verify:** `make test` runs `pytest` inside the container and the single `/healthz` smoke test passes. `make psql` opens a shell on the DB.

### Step 7: README + verification artifacts (FOUND-04, FOUND-08, PITFALL SH-6)
- Author `README.md` Phase 0 section with: stack overview, prerequisites, setup (copy `.env.example`, generate keys, `make up`), NGINX server-block snippet for reverse proxy (skeletal — Phase 1 extends it with HSTS + buffering off), backup restore stub (full procedure in Phase 8), troubleshooting (loud single-worker note).
- Author top-of-file comment block in `app/services/scheduler.py` referencing the single-worker rule (this is location #2 of three for the rule; locations #1 is entrypoint.sh, #3 is README.md).
- **Verify:** A fresh checkout + `cp .env.example .env` + fill in secrets + `docker compose up -d --build` brings up the stack. `curl http://127.0.0.1:8080/healthz` returns 200. `curl http://127.0.0.1:8080/` returns HTML with the placeholder text.

## Key Technical Decisions

| Decision | Value | Source / Verification |
|----------|-------|------------------------|
| Python pin | `python:3.12-slim` | `[VERIFIED: STACK.md §1]` CLAUDE.md stack invariant. |
| FastAPI pin | `>=0.136,<0.137` | `[VERIFIED: STACK.md §1]` Lifespan-only; `@app.on_event` deprecated. |
| SQLAlchemy pin | `>=2.0.49,<2.1` | `[VERIFIED: PyPI 2026-05-17]` 2.1.0b2 is beta — stay on 2.0.x. |
| psycopg pin | `psycopg[binary]>=3.3,<3.4` | `[VERIFIED: PyPI + WebSearch 2026-05-17]` URL form `postgresql+psycopg://...`. |
| Alembic pin | `>=1.18,<2.0` | `[VERIFIED: STACK.md §1]` Handles `Mapped[...]` autogenerate. |
| Postgres image | `postgres:16-alpine` | `[VERIFIED: STACK.md §1]` Spec lock. |
| structlog pin | `>=25.5,<26` | `[VERIFIED: PyPI structlog page]` 25.5.0 released 2025-10-27. |
| Tailwind CLI binary download URL | `https://github.com/tailwindlabs/tailwindcss/releases/download/${TAILWIND_VERSION}/tailwindcss-linux-x64` | `[VERIFIED: tailwindcss.com/blog/standalone-cli, GitHub releases]` ARG-pinnable for reproducibility. |
| Tailwind version (recommended pin) | `v4.3.0` | `[CITED: GitHub releases]` Current stable v4 line; planner may pin a more recent v4.x at plan time. |
| Postgres-client install source | PGDG APT repo (`https://apt.postgresql.org/pub/repos/apt`) | `[VERIFIED: wiki.postgresql.org/wiki/Apt]` Exact-version-matched `postgresql-client-16` per PITFALL SH-5. |
| postgres-contrib extensions (citext, pg_trgm, unaccent) bundled in alpine image | Yes, via the postgres-contrib package | `[ASSUMED — needs smoke verification in migration]` Documented on Postgres image hub as "extensions in postgres-contrib are included"; smoke test asserts `SELECT * FROM pg_extension` shows all three. |
| uvicorn flags | `--host 0.0.0.0 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips=$TRUSTED_PROXY_IPS` | `[VERIFIED: uvicorn.dev/settings]` Required by FOUND-04 + FOUND-08. |
| Compose port binding | `127.0.0.1:8080:8000` | `[VERIFIED: CONTEXT D-09]` Never `0.0.0.0`. |
| SQLAlchemy pool knobs | `pool_size=10, max_overflow=5, pool_timeout=5, pool_pre_ping=True, pool_recycle=300` | `[VERIFIED: PITFALL SH-2, CONTEXT D-10]` Locked. |
| FastAPI lifespan pattern | `@asynccontextmanager async def lifespan(app)` | `[VERIFIED: fastapi.tiangolo.com/advanced/events]` Only supported path. |
| structlog config | ProcessorFormatter + dictConfig | `[VERIFIED: structlog.org/en/stable/standard-library.html]` Canonical stdlib-merge pattern. |
| Single-worker note locations | (1) `entrypoint.sh` comment block, (2) `README.md` deployment section, (3) `app/services/scheduler.py` placeholder file | `[VERIFIED: CONTEXT <specifics>]` Three locations per spec. |

## Environment Availability

The phase depends on tools that are installed inside the Docker image at build time, not on the developer's host machine. Host-side, only Docker is required.

| Dependency | Required By | Available on host? | Version | Fallback |
|------------|------------|---------------------|---------|----------|
| Docker | Whole phase | (assumed yes — VPS deployment) | n/a | None — blocking |
| Docker Compose v2 | `docker compose ...` commands | (assumed yes) | n/a | None — blocking |
| Internet access at build time | `apt-get`, `pip install`, `curl github.com tailwindcss` | (assumed yes) | n/a | Cache image base for offline rebuild, or vendor a Tailwind binary into the repo (not recommended) |
| Python 3.12 on host | Local dev only (NOT required if all work happens inside the container) | (optional) | n/a | All dev can happen via `make shell` → container Python |
| Postgres 16 on host | NO — postgres runs in a container | n/a | n/a | n/a |

**Missing dependencies that would block execution:** Docker / Docker Compose v2. If absent on the target VPS, this phase cannot complete. Researcher assumes both are present per CLAUDE.md's deployment runbook.

**Missing dependencies with fallback:** None applicable in this phase.

## Validation Architecture

Per `.planning/config.json` (`workflow.nyquist_validation: true`), this section is required.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest `>=9.0,<10` |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`); ships in Phase 0 Step 6 |
| Quick run command | `make test` (delegates to `docker compose exec coffee-snobbery pytest -x`) |
| Full suite command | `make test` (same — only one test in Phase 0) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| FOUND-01 | `docker compose up -d` brings the stack up and `127.0.0.1:8080` answers | smoke | `docker compose up -d --build && sleep 30 && curl -fsS http://127.0.0.1:8080/healthz` | ❌ Wave 0 — landed as a Makefile target `make smoke` |
| FOUND-02 | Two services named `coffee-snobbery` + `coffee-snobbery-db` on `coffee-snobbery-net` | integration | `docker network inspect coffee-snobbery-net \| jq -e '.[].Containers \| keys \| length == 2'` | ❌ Wave 0 |
| FOUND-03 | Three named volumes exist | integration | `docker volume ls \| grep -E 'coffee_snobbery_(postgres_data\|photos\|backups)' \| wc -l` returns 3 | ❌ Wave 0 |
| FOUND-04 | Single uvicorn worker | integration | `docker compose exec coffee-snobbery ps -ef \| grep uvicorn \| grep -- '--workers 1'` | ❌ Wave 0 |
| FOUND-05 | Migrations run on container start | integration | `docker compose logs coffee-snobbery \| grep "Running upgrade .* -> 0001"` | ❌ Wave 0 |
| FOUND-06 | Three extensions installed | integration | `docker compose exec -T coffee-snobbery-db psql -U $POSTGRES_USER -d $POSTGRES_DB -tAc "SELECT extname FROM pg_extension WHERE extname IN ('citext','pg_trgm','unaccent')" \| wc -l` returns 3 | ❌ Wave 0 |
| FOUND-07 | `pg_dump --version` is 16.x in the web container | integration | `docker compose exec coffee-snobbery pg_dump --version \| grep -E "16\."` | ❌ Wave 0 |
| FOUND-08 | uvicorn launched with `--proxy-headers --forwarded-allow-ips=…` | integration | `docker compose exec coffee-snobbery ps -ef \| grep -- '--proxy-headers'` and `grep -- '--forwarded-allow-ips'` | ❌ Wave 0 |
| FOUND-09 | `.env.example` documents every required env var with hints | unit (regex over file content) | `pytest tests/test_env_example.py::test_env_example_documents_all_vars` | ❌ Wave 0 |
| FOUND-10 | `app/config.py` is the only module that reads `os.environ` | unit (grep) | `! grep -RIn --include='*.py' --exclude-dir=migrations 'os\.environ' app/ \| grep -v 'app/config\.py:'` | ❌ Wave 0 |
| FOUND-11 | structlog emits JSON with `event`, `timestamp_iso`, `level` | unit | `pytest tests/test_logging.py::test_json_renderer_shape` | ❌ Wave 0 |
| FOUND-12 | Tailwind CSS is present in image, content-hashed | integration | `docker compose exec coffee-snobbery ls app/static/css/ \| grep -E 'tailwind\.[0-9a-f]{8}\.css'` | ❌ Wave 0 |
| CAT-04 | `bags` table exists with the 9 spec columns | unit | `pytest tests/test_migrations.py::test_bags_columns` | ❌ Wave 0 |
| AI-02 | `ai_recommendations` exists with the 16+ columns including 9 cost-obs cols | unit | `pytest tests/test_migrations.py::test_ai_recommendations_columns` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `make test` (quick — just the unit tests). Migration introspection tests run against an ephemeral SQLite-equivalent OR against the running compose stack — researcher recommends against the running stack for unit tests (slow); use a transactional pytest fixture that points at the compose DB but rolls back after each test.
- **Per wave merge:** `make smoke` — `docker compose down -v && docker compose up -d --build && curl http://127.0.0.1:8080/healthz` + all the integration probes above.
- **Phase gate:** Full smoke green; every FOUND/CAT-04/AI-02 requirement has a passing check.

### Wave 0 Gaps

- [ ] `tests/conftest.py` — TestClient fixture, DB session fixture with rollback, env var setup
- [ ] `tests/test_healthz.py` — smoke test of `GET /healthz`
- [ ] `tests/test_env_example.py` — regex check that `.env.example` documents all keys returned by `Settings().model_fields.keys()`
- [ ] `tests/test_logging.py` — capture structlog output, assert JSON shape with `event`, `timestamp_iso`, `level` keys
- [ ] `tests/test_migrations.py` — connect to the compose DB, introspect `pg_extension`, `information_schema.columns` for each table, assert every required column exists with the right type and nullability
- [ ] `tests/test_no_direct_env.py` — grep-style test asserting `os.environ` is only referenced in `app/config.py`
- [ ] `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths`, `asyncio_mode`
- [ ] Framework install: `pip install -r requirements-dev.txt` — included in image OR runnable via `make test`

## Security Domain

`security_enforcement` not explicitly set to `false` in config — treat as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | partial — Phase 0 prepares `users` table; auth lands in Phase 2 | argon2-cffi (installed in Phase 0, used in Phase 2) |
| V3 Session Management | no (Phase 1) | Custom SessionMiddleware (Phase 1) |
| V4 Access Control | no (Phase 2+) | `is_admin` gate (Phase 2) |
| V5 Input Validation | no (Phase 1+) | Pydantic v2 schemas (Phase 1+) |
| V6 Cryptography | partial — `APP_ENCRYPTION_KEY` env var documented + `MultiFernet` env shape locked | `cryptography.MultiFernet` (Phase 3) |
| V7 Error Handling and Logging | yes — structlog emits structured logs from day one | structlog 25.5 (no PII / no request bodies — see Phase 1 redactors) |
| V11 Business Logic | n/a in Phase 0 | n/a |
| V12 File and Resource | n/a — no uploads yet | n/a |
| V14 Configuration | yes | pydantic-settings (single env reader), `.env.example` with generation hints, no secrets in repo |

### Known Threat Patterns for {Python 3.12 / FastAPI / Postgres 16 / Docker stack}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Reading `os.environ` in scattered modules; hard-coded fallbacks leak secrets | Information Disclosure | Single pydantic-settings reader in `app/config.py` (FOUND-10) |
| Secrets committed to git via `.env` | Information Disclosure | `.gitignore` includes `.env`; only `.env.example` (sanitized) tracked |
| API key encryption with single Fernet → rotation orphans data | Repudiation / Information Disclosure | MultiFernet env shape locked in Phase 0; wiring in Phase 3 |
| `pg_dump` version mismatch → silent backup failure | Denial of Service (no recoverable backup) | `postgresql-client-16` from PGDG APT repo (PITFALL SH-5) |
| Container runs as root → file ownership issues + larger blast radius | Elevation of Privilege | Non-root `app` user UID 1000 (CONTEXT D-05) |
| Web service exposed publicly on `0.0.0.0` | Tampering / Information Disclosure | `127.0.0.1:8080:8000` binding only (CONTEXT D-09) |
| Browser drops `Secure` session cookie because uvicorn sees `scheme=http` | Spoofing (session hijack via cookie failure) | `--proxy-headers --forwarded-allow-ips=$TRUSTED_PROXY_IPS` (FOUND-08, PITFALL SH-6) |
| Migration accidentally drops a column with data | Tampering / Denial of Service | Migration code-reviewed before merge; CLAUDE.md "ask first" rule for lossy migrations |

## Project Constraints (from CLAUDE.md)

These are directives the planner MUST honor. Each is sourced from `./CLAUDE.md`.

### Stack invariants — DO NOT change without confirming with John:
- Python 3.12 + FastAPI
- PostgreSQL 16
- SQLAlchemy 2.0 + Alembic
- Jinja2 + HTMX + Tailwind (CDN) + Alpine.js — **NO npm build pipeline** (this phase resolves the spec/CLAUDE-md/CONTEXT.md three-way tension by using the Tailwind standalone CLI binary, NOT the CDN, NOT npm)
- argon2-cffi for passwords, Fernet for API key encryption
- APScheduler in-process for nightly jobs (placeholder + comment only in Phase 0)
- Docker Compose, two containers: `coffee-snobbery` (web) + `coffee-snobbery-db`

### Code conventions:
- `ruff format` before committing
- `ruff check`; treat warnings as errors
- Type hints required on function signatures; use `from __future__ import annotations`
- Pydantic v2 for request/response/form schemas
- SQLAlchemy 2.0 style: typed `Mapped[...]` columns, `select()` constructs, NO legacy Query API
- Templates: 2-space indent for HTML/Jinja, snake_case for variables
- CSS: Tailwind utility classes; custom CSS only when utilities don't cover it (lives in `app/static/css/custom.css`)
- JS: Alpine.js inline, vanilla JS in `app/static/js/` for anything heavier; NO npm
- Commits: conventional commits (`feat:`, `fix:`, `chore:`, `refactor:`, `docs:`); short, imperative, present tense
- Branches: `main` direct for small changes; feature branch + merge for schema/auth/AI

### Architectural invariants — Phase 0 SETS these for the rest of the project:
- Coffees, equipment, recipes, roasters, flavor notes are shared across users. Brew sessions and AI recommendations are per-user. *(Phase 0 ships `users`, `bags`, `wishlist_entries`, `ai_recommendations`, `app_settings`. `users` and `wishlist_entries` are per-user; the rest of the per-user/shared partition lands in later phases.)*
- No public registration. Admin creates users via `/admin`. The `/setup` route only works when zero users exist. *(Phase 0 seeds `setup_completed = false`; Phase 2 implements `/setup`.)*
- AI keys live encrypted in the DB, not env vars. Never bypass `services/encryption.py`. *(Phase 0 documents `APP_ENCRYPTION_KEY` env var; Phase 3 builds the service.)*
- Signature-based AI regeneration. *(Phase 0 ships `ai_recommendations.input_signature` column + index; Phase 7 implements signature logic.)*
- Mobile-first; any UI tested at 375px. *(Phase 0's placeholder `/` page must render readably at 375px — but this is a placeholder, not a real UI.)*
- Reverse-proxy aware. *(Phase 0 wires `--proxy-headers` flag.)*
- CSRF on all state-changing forms. *(Phase 0 has no state-changing forms; Phase 1 adds the middleware.)*

### "Never do silently" directives that apply to Phase 0:
- Don't drop or rename a column in a migration without explicit data-preservation plan *(N/A — only ADD operations in `0001_initial.py`)*
- Don't disable CSRF, CSP, or security headers *(Phase 1's concern)*
- Don't log API keys, passwords, or session tokens *(structlog config — Phase 0 does NOT log any of these)*
- Don't commit `.env` or any file with real secrets *(`.gitignore` must include `.env`)*
- Don't push directly to the VPS without going through git *(operational, not a Phase 0 file change)*
- Don't bypass the encryption layer for stored API keys *(no API keys stored yet in Phase 0)*
- Don't modify `docs/snobbery-gsd-prompt.md` *(read-only historical reference)*

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@app.on_event("startup")` / `@app.on_event("shutdown")` | `@asynccontextmanager async def lifespan(...)` | Starlette 0.x → 1.0 (March 2026) | FastAPI 0.136 ships against Starlette 1.0; old API will be removed. Phase 0 uses `lifespan` only. |
| `psycopg2-binary` | `psycopg[binary]` (v3) | psycopg 3.0 GA, 3.3 current (May 2026) | Native async support; modern packaging; URL prefix is `postgresql+psycopg://...`. |
| `cookie-based SessionMiddleware` (Starlette default) | Custom table-backed middleware (`sessions` table) | Spec-mandated — Phase 1 builds it | Phase 0 doesn't ship the middleware, but the architectural shape is locked. |
| `bleach` for HTML sanitization | Avoid HTML sanitization entirely (autoescape ON, no `\|safe`) | Mozilla deprecated bleach 2023 | Phase 0 templates have NO `\|safe`. |
| Single `Fernet` key | `MultiFernet([Fernet(primary), Fernet(secondary), ...])` | spec — locked in PROJECT.md | Phase 0 documents `APP_ENCRYPTION_KEY` as comma-separated; Phase 3 constructs the MultiFernet. |
| Tailwind v3 Play CDN | Tailwind v4 standalone CLI binary | Tailwind v4 (GA late 2024); v4 Play CDN now warns "not for production" | Phase 0 ships the CLI binary in the Dockerfile, not the CDN. |
| HTMX 1.9 (per spec wording) | HTMX 2.x (2.0.10 current) | spec predates HTMX 2.x stable | Phase 0 doesn't ship HTMX yet (Phase 1 does), but the version is decided. |

**Deprecated / outdated patterns Phase 0 must NOT use:**
- `@app.on_event(...)` — use `lifespan` only.
- `psycopg2` — use `psycopg` (v3).
- `os.environ[...]` outside `app/config.py` — use `settings` import.
- `MemoryJobStore` / default APScheduler config (Phase 8 concern but the placeholder file's docstring flags it).
- Tailwind Play CDN (v3 or v4) — incompatible with the strict CSP plan in Phase 1.
- `requirements.txt` without upper bounds — every pin is bounded (per CLAUDE.md).
- Plain stdlib `logging.basicConfig()` for production logs — use structlog ProcessorFormatter wiring (Pattern 2).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `citext`, `pg_trgm`, `unaccent` are bundled with `postgres:16-alpine` (postgres-contrib included) | §3 (schema design — extensions run via `CREATE EXTENSION`) | If extensions are absent, `CREATE EXTENSION` fails. Verifiable in Step 4 smoke. **Mitigation:** if absent, planner adds an apt-install step in a custom DB image — but this is well-documented as bundled in alpine postgres-contrib. |
| A2 | Tailwind v4.3.0 is current stable and the recommended pin | Key Technical Decisions | If a newer v4.x is current, the binary URL pattern still works — the ARG is the only thing to change. Low risk. |
| A3 | `releases/download/${VERSION}/tailwindcss-linux-x64` filename pattern is stable across the v4 line | §4 Dockerfile | If Tailwind changes asset naming (e.g., adds an ABI tag), the curl command fails fast at build time — visible immediately. |
| A4 | `psycopg[binary]` 3.3.x prebuilt wheel is available for Python 3.12 on linux/amd64 | requirements.txt | Heavily verified — psycopg[binary] is the recommended install across the SQLAlchemy ecosystem. |
| A5 | The compose `depends_on: condition: service_healthy` syntax works in Docker Compose v2 | §5 compose shape | Documented in Compose v2 spec; standard. |
| A6 | `pg_isready` is on the path in `postgres:16-alpine` | §5 compose HEALTHCHECK | `pg_isready` is part of the postgres server install; bundled. |
| A7 | Server-default `now()` works for `timestamptz` columns in SQLAlchemy 2.0 + psycopg 3 + Alembic | §3 migration code | Standard SQLAlchemy pattern; well-tested. |
| A8 | The `bigint` PK + ForeignKey deferred shape (Phase 0 ships `bags.coffee_id` with no FK; Phase 4 adds the FK) works without data-validity issues | §3 (bags table) | Researcher's recommendation; if planner prefers NULLABLE-then-tighten, the only impact is migration shape. Either approach is defensible. |

**Confidence assessment:** All claims tagged `[VERIFIED]` or `[CITED]` are unaffected. Only A1, A2, A8 are `[ASSUMED]` — and A1 is the only one with non-trivial downside if wrong (it would surface at the very first `docker compose up -d` smoke run).

## Open Questions (RESOLVED)

These gaps were resolved during plan-phase. Each question retains its original Recommendation line plus a RESOLVED marker citing the implementing plan + task.

1. **Tailwind binary version pin.**
   - What we know: Tailwind v4 standalone CLI exists at `https://github.com/tailwindlabs/tailwindcss/releases/`; v4.3.0 is the latest version visible.
   - What's unclear: Whether John wants a fixed pin (recommended — reproducible builds) or to track `latest` (faster security updates, less reproducible).
   - Recommendation: Pin `TAILWIND_VERSION=v4.3.0` (or whatever is current at plan time) and surface it as a Dockerfile ARG; revisit during Phase 12 hardening.
   - **RESOLVED:** Dockerfile ships `ARG TAILWIND_VERSION=v4.3.0` in stage 1 (tailwind-builder); the pin is surfaced as a build-arg so Phase 12 can bump or pin to a sha256 without editing the Dockerfile body. See PLAN 00-04 task 3.

2. **`bags.coffee_id` FK timing.**
   - What we know: spec says NOT NULL; `coffees` doesn't exist until Phase 4.
   - What's unclear: Whether to ship NOT NULL `bigint` with no FK (researcher's recommendation — forward-defensible) OR NULLABLE `bigint` and tighten in Phase 4.
   - Recommendation: NOT NULL `bigint` with no FK; Phase 4's first migration adds the FK constraint. Both approaches are defensible; researcher prefers forward-defensible.
   - **RESOLVED:** `bags.coffee_id` ships as `BigInteger NOT NULL` with NO `ForeignKey(...)` constraint in Plan 03; `tests/test_migrations.py::test_bags_coffee_id_has_no_foreign_key` asserts the constraint count is 0. See PLAN 00-03 tasks 1 and 2. Phase 4 first migration adds the FK once the `coffees` table exists.

3. **`pg_dump` path in the web container.**
   - What we know: Phase 8 needs `pg_dump`; spec says version-match. Phase 0 installs `postgresql-client-16`.
   - What's unclear: Whether Phase 8's backup script runs `pg_dump` directly (`pg_dump $DATABASE_URL`) or via subprocess from APScheduler.
   - Recommendation: Defer entirely to Phase 8 plan — Phase 0's only responsibility is making sure `pg_dump` v16 is on the path.
   - **RESOLVED (deferred):** Phase 0 only ensures `pg_dump` v16 is on the runtime image path (Plan 04 task 3 installs `postgresql-client-16` from PGDG); `make smoke` (PLAN 00-05 task 2) verifies `docker compose exec coffee-snobbery pg_dump --version` reports `16.x`. The invocation pattern (direct vs subprocess vs APScheduler-wrapped) is tracked for Phase 8.

4. **structlog renderer wrap for production.**
   - What we know: `LOG_FORMAT=json` uses `JSONRenderer`; `LOG_FORMAT=console` uses `ConsoleRenderer`.
   - What's unclear: Whether to emit the `event` key as `event` (structlog default) or rename to `message` to align with common log aggregator expectations (e.g., Datadog, Loki).
   - Recommendation: Keep structlog default (`event`) for v1; if log aggregation lands later it's a one-line `EventRenamer` processor in Phase 8 or 12.
   - **RESOLVED:** `event` key retained (structlog default); Plan 02's `test_json_renderer_shape` asserts `record["event"] == "hello world"`. Switching to `message` would be a one-line `EventRenamer` processor add in a later phase. See PLAN 00-02 task 1.

5. **Dockerfile `curl` in runtime stage.**
   - What we know: HEALTHCHECK uses `curl`; the example Dockerfile in §4 purges curl after PGDG setup.
   - What's unclear: Whether to keep curl in the runtime image (smaller blast radius if it's not there, but breaks the HEALTHCHECK) or use a Python one-liner.
   - Recommendation: Keep `curl` installed; the convenience for HEALTHCHECK and ad-hoc operational debugging outweighs the marginal attack-surface cost. Researcher edits §4 to NOT purge curl.
   - **RESOLVED:** `curl` is retained in the runtime image; the Dockerfile purges only `gnupg lsb-release` after PGDG repo setup. Docker HEALTHCHECK invokes `curl -fsS http://127.0.0.1:8000/healthz`. See PLAN 00-04 task 3.

6. **`tailwind.src.css` content scan paths in `tailwind.config.js`.**
   - What we know: Tailwind v4 needs `content: ["./app/templates/**/*.html", "./app/static/js/**/*.js"]` or equivalent to tree-shake unused utilities.
   - What's unclear: Whether `app/static/js/` should be in the scan paths even though Phase 0 has no JS files there yet.
   - Recommendation: Include it. Adds zero bytes if empty; saves a Tailwind config edit in Phase 1 when HTMX/Alpine snippets land.
   - **RESOLVED:** `tailwind.config.js` ships `content: ["./app/templates/**/*.html", "./app/static/js/**/*.js"]` — both paths scanned from day one, so Phase 1's HTMX/Alpine JS snippets need no Tailwind config edit. See PLAN 00-04 task 1.

## Sources

### Primary (HIGH confidence — verified via official docs)

- [FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/events/) — verified 2026-05-17. Canonical `@asynccontextmanager async def lifespan(...)` pattern; deprecation of `@app.on_event`.
- [structlog stdlib integration](https://www.structlog.org/en/stable/standard-library.html) — verified 2026-05-17. ProcessorFormatter + dictConfig wiring exactly as shown in §Pattern 2.
- [structlog on PyPI](https://pypi.org/project/structlog/) — verified 2026-05-17. Current version 25.5.0 (released 2025-10-27).
- [SQLAlchemy on PyPI](https://pypi.org/project/SQLAlchemy/) — verified 2026-05-17. Current 2.0.x is 2.0.49 (released 2026-04-03); 2.1 still beta.
- [SQLAlchemy 2.0 Engine Configuration](https://docs.sqlalchemy.org/en/20/core/engines.html) — verified via WebSearch result reference. `create_engine` pool knobs.
- [psycopg 3 connection pool / SQLAlchemy integration](https://www.psycopg.org/psycopg3/docs/api/pool.html) — verified 2026-05-17 via WebSearch. URL prefix `postgresql+psycopg://...`.
- [Tailwind CSS standalone CLI blog post](https://tailwindcss.com/blog/standalone-cli) — verified 2026-05-17. Binary download URL pattern `https://github.com/tailwindlabs/tailwindcss/releases/.../tailwindcss-linux-x64`.
- [Tailwind GitHub releases](https://github.com/tailwindlabs/tailwindcss/releases) — verified 2026-05-17. v4.3.0 visible as the current line.
- [Alembic generic env.py template](https://github.com/sqlalchemy/alembic/blob/main/alembic/templates/generic/env.py) — verified 2026-05-17. Confirmed `target_metadata = Base.metadata` pattern and the `run_migrations_online` / `run_migrations_offline` structure.
- `.planning/research/STACK.md` (in-repo) — verified inline. Pinned versions for every library.
- `.planning/research/ARCHITECTURE.md` (in-repo) — verified inline. Component map; request paths; FastAPI lifespan canonical pattern; uvicorn `--proxy-headers` invocation.
- `.planning/research/PITFALLS.md` (in-repo) — verified inline. SH-1, SH-2, SH-5, SH-6 (and COST-1, PWA-5) are the load-bearing Phase 0 pitfalls.
- `.planning/phases/00-foundation/00-CONTEXT.md` (in-repo) — verified inline. All locked decisions D-01 through D-19.
- `.planning/ROADMAP.md` (in-repo) — verified inline. Phase 0 goal + 5 success criteria.
- `.planning/REQUIREMENTS.md` (in-repo) — verified inline. FOUND-01..12, CAT-04, AI-02 with exact text.
- `CLAUDE.md` (in-repo) — verified inline. Stack invariants, code conventions, architectural invariants, "never do silently" list.

### Secondary (MEDIUM confidence)

- [PostgreSQL official APT repo wiki](https://www.postgresql.org/download/linux/debian/) — referenced for the PGDG repo install procedure. Standard, well-documented. Used by §4 Dockerfile.
- [Docker Hub: postgres image](https://hub.docker.com/_/postgres) — verified 2026-05-17. `POSTGRES_PASSWORD` required env var; postgres-contrib bundled. The page does NOT explicitly enumerate the contrib extensions, hence A1 in the assumption log.
- [Uvicorn settings](https://uvicorn.dev/settings/) — referenced via ARCHITECTURE.md; `--proxy-headers`, `--forwarded-allow-ips` semantics.
- [Tailwind v4 production warning](https://tailwindcss.com/docs/installation/play-cdn) — referenced via STACK.md §3.1.

### Tertiary (LOW confidence — used only as cross-check)

- WebFetch results were partial in a few cases (Tailwind GitHub releases page returned without asset details; PostgreSQL Docker page returned without HEALTHCHECK example). Information used was cross-verified against the in-repo STACK.md / ARCHITECTURE.md / PITFALLS.md which were thoroughly researched 2026-05-16.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every pin sourced from STACK.md and verified against PyPI within the last 24 hours where relevant.
- Architecture (compose/Dockerfile shape, multi-stage strategy, entrypoint, uvicorn flags): HIGH — sourced from CONTEXT.md locked decisions and verified upstream.
- Schema design: HIGH for column existence (mandated by AI-02, CAT-04, COST-1, CONTEXT D-17); MEDIUM for column type details (planner picks `bigint` vs `uuid`, `text` vs `enum`).
- Pitfalls: HIGH — all referenced pitfalls (SH-1, SH-2, SH-5, SH-6, COST-1, PWA-5) have detailed prevention sections in PITFALLS.md.
- Validation architecture: HIGH — straightforward pytest patterns; only one smoke test ships in Phase 0 itself.

**Research date:** 2026-05-17
**Valid until:** 2026-06-17 (30 days — stack is stable, but the Anthropic + OpenAI SDKs in particular move fast and would invalidate any reference here if AI-02 / AI-05 columns needed reshaping).
