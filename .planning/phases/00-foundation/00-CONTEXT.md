# Phase 0: Foundation - Context

**Gathered:** 2026-05-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Greenfield bootstrap. A clean `git clone` + `docker compose up -d` brings up a two-container stack (`coffee-snobbery` web + `coffee-snobbery-db`) on `coffee-snobbery-net`, the first migration installs Postgres extensions and the five v1 foundation tables, Tailwind is compiled into the image, structlog emits JSON, and uvicorn runs as a single worker behind a trusted-proxy header list. No user-facing UI beyond a `GET /` placeholder and a DB-touching `GET /healthz`.

In scope (Phase 0 owns):
- `docker-compose.yml` with two services, three named volumes, `coffee-snobbery-net` bridge, Postgres HEALTHCHECK + `depends_on: condition: service_healthy`
- Multi-stage Dockerfile: tailwind-builder stage → `python:3.12-slim` runtime; non-root `app` user (UID 1000); `postgresql-client-16` apt-installed for backup parity (PITFALL SH-5)
- `entrypoint.sh` running `alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips=$TRUSTED_PROXY_IPS`
- Alembic configuration (`alembic.ini`, `app/migrations/env.py` for SQLAlchemy 2.0 + psycopg 3 native sync) and **one** initial migration `0001_initial.py` (extensions + 5 tables + seed inserts)
- Five tables: `users`, `bags`, `ai_recommendations` (including all 9 cost-observability columns), `app_settings`, `wishlist_entries`
- `app/config.py` (pydantic-settings) — only module that reads `os.environ`
- `app/db.py` — SQLAlchemy 2.0 sync engine + sessionmaker with locked pool knobs (PITFALL SH-2)
- `app/logging.py` — structlog JSON output by default, ConsoleRenderer when `LOG_FORMAT=console`
- `app/main.py` — FastAPI app factory, lifespan (open/close engine), StaticFiles mount, Jinja2 environment with autoescape ON, two routes (`/healthz`, `/`)
- `app/templates/base.html` + `app/templates/pages/index.html` (placeholder)
- `app/static/css/tailwind.<hash>.css` (built at image build time) + `app/static/css/tailwind.src.css` (source)
- `tailwind.config.js` with the warm-cream / espresso palette baked in + `darkMode: 'media'`
- `.env.example` with one-liner generation hints for every env var
- `Makefile` wrapping the common compose flows
- `README.md` Phase-0 section: how to bring it up, the loud single-worker note (one of three places — also in `entrypoint.sh` and a comment in the future scheduler module)
- `pyproject.toml` with ruff + mypy tool configs (no GitHub Actions YAML yet — Phase 12 owns CI)
- Placeholder `tests/` directory (no tests yet; conftest scaffold + a smoke test of `/healthz` is fine)

Out of scope (belongs to later phases):
- CSP / security headers / CSRF / session middleware — Phase 1
- Real `/setup` route body, argon2id verify, session-ID regeneration — Phase 2
- Encryption service (`MultiFernet`) + `api_credentials` table — Phase 3 (the env var `APP_ENCRYPTION_KEY` is defined here; the wiring is Phase 3)
- Catalog (`coffees`, `equipment`, `recipes`, `roasters`, `flavor_notes`) — Phase 4
- Brew sessions — Phase 5
- Analytics / home page — Phase 6
- AI service — Phase 7
- APScheduler + nightly backups — Phase 8
- GitHub Actions / CI YAML — Phase 12

14 requirements mapped: FOUND-01 through FOUND-12 + CAT-04 (bags table) + AI-02 (ai_recommendations table).

</domain>

<decisions>
## Implementation Decisions

### First-migration scope and split

- **D-01: `wishlist_entries` lands in the Phase 0 first-migration set.** Matches PROJECT.md Key Decisions row 11. The "add to wishlist" target landing exists from day one; Phase 7's AI rec card doesn't have to coordinate a schema add. CRUD UI for wishlist lands whenever it's needed (likely Phase 4 or Phase 7); the table is here.
- **D-02: One mega-migration `0001_initial.py`.** Single file does the three extensions, the five tables, and all seed inserts. Clean blame for "the foundation"; `alembic upgrade head` is one step on cold start. Expected to be 200–300 LOC.
- **D-03: Migration uses `op.execute("CREATE EXTENSION IF NOT EXISTS citext")`** (and the same for `pg_trgm`, `unaccent`) — extensions installed by superuser at db-container init, so this is idempotent even if the Postgres image already created them. Planner verifies the docker image entrypoint behavior for `postgres:16-alpine`.

### Docker / runtime architecture

- **D-04: Multi-stage Dockerfile.** Stage 1 (`tailwind-builder`): downloads the Tailwind standalone CLI binary, runs `tailwindcss -i ./app/static/css/tailwind.src.css -o ./app/static/css/tailwind.<hash>.css --minify`, exits. Stage 2 (`python:3.12-slim`) `COPY --from=tailwind-builder` of the compiled CSS only. Final image has zero Tailwind tooling — smaller, cleaner, and `pip install` layer caches independently of CSS changes.
- **D-05: Non-root `app` user, UID 1000.** Dockerfile: `RUN useradd -u 1000 -m app`, `USER app` before `CMD`. UID 1000 matches typical host deploy user, simplifying any future bind-mount work (we use named volumes today, so SH-4 isn't a blocker — this is forward-defense).
- **D-06: `postgresql-client-16` installed in the web image** from PostgreSQL's apt repo, NOT the slim repo (which would give Postgres 15 client and silently break nightly `pg_dump` per PITFALL SH-5). Planner pins the apt source-list pattern.
- **D-07: DB readiness via compose, not bash.** docker-compose.yml gives the `coffee-snobbery-db` service a `HEALTHCHECK: pg_isready -U $POSTGRES_USER -d $POSTGRES_DB`. The `coffee-snobbery` service declares `depends_on: coffee-snobbery-db: condition: service_healthy`. `entrypoint.sh` therefore does NOT include a bash wait-loop — just `alembic upgrade head && exec uvicorn ...`.
- **D-08: `GET /healthz` does a DB-touching 1-row SELECT.** Uses a SQLAlchemy session against a 2-second pool_timeout to prevent a healthcheck from hanging on pool exhaustion. Returns `{"status":"ok"}` on success, 503 with a structured-log entry on failure. Docker `HEALTHCHECK` on the web service calls this endpoint.
- **D-09: docker-compose.yml publishes the web service on `127.0.0.1:8080:8000` only** — never `0.0.0.0:8080:8000`. NGINX (host-side) terminates TLS and proxies to localhost; binding to the host's public interface would expose the dev port externally.
- **D-10: SQLAlchemy engine pool knobs (locked).** `pool_size=10, max_overflow=5, pool_timeout=5, pool_pre_ping=True, pool_recycle=300` — per PITFALL SH-2 and CLAUDE.md. These are not defaults; they are explicit choices for the single-worker household-scale shape.

### App skeleton + routes

- **D-11: Scaffold ALL `app/` subpackages in Phase 0.** Even the ones Phase 0 doesn't put code in: `app/middleware/__init__.py` (owned by Phase 1), `app/routers/__init__.py` (owned by Phase 2+), `app/services/__init__.py` (owned by Phase 3+). Each empty `__init__.py` has a one-line module docstring naming its owning phase. Reason: directory contract is established once; later phases never have to decide "where should this go."
- **D-12: Phase 0 ships exactly two HTTP routes.** `GET /healthz` (per D-08) and `GET /` (renders `base.html` + `pages/index.html` with the literal text "Snobbery — setup pending. POST /setup once auth lands."). Phase 2's `/setup` and Phase 6's real home replace `GET /` later.
- **D-13: `app/templates/base.html` is a real shell, not a stub.** Includes: `<!doctype html>`, `<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">`, dual `theme-color` meta (light cream + dark espresso per PITFALL PWA-5), `<link rel="stylesheet" href="{{ tailwind_css_path }}">`, `<body class="bg-cream-50 text-espresso-900 dark:bg-espresso-950 dark:text-cream-100">`, `{% block content %}{% endblock %}`. **No** HTMX or Alpine yet — Phase 1 adds those alongside CSP nonce wiring. **No** `|safe` anywhere.
- **D-14: `tailwind.config.js` ships the palette baseline in Phase 0.** `theme.extend.colors.cream` (50-950 scale anchored around #FAF7F2) and `theme.extend.colors.espresso` (50-950 scale anchored around #3D2817). `darkMode: 'media'` (system preference, no manual toggle — matches PROJECT.md row 6). Exact hex values are tunable during the first `/gsd-ui-phase` pass; the *structure* (named colors, dark-mode strategy) lands now so Phase 1/2/3 minor UI bits (login form, setup form, admin shell) have a coherent starting point.
- **D-15: Static asset path is content-hashed at build time.** Dockerfile build stage emits `tailwind.<sha8>.css` where the hash is computed from the source file content. The Jinja2 environment exposes a `tailwind_css_path` global computed at app startup by globbing `app/static/css/tailwind.*.css` — no per-request filesystem work. Phase 11 (PWA) will replace this with a fuller asset-manifest if needed.

### Logging

- **D-16: structlog format is env-var-controlled.** `LOG_FORMAT=json` (default) → `structlog.processors.JSONRenderer`. `LOG_FORMAT=console` → `structlog.dev.ConsoleRenderer` (color-on-TTY). Documented in `.env.example` and the README. Base context every log line carries: `event`, `timestamp_iso`, `level`. Per-request `request_id` binding is Phase 1's middleware; per-user `user_id` binding is Phase 2's middleware.

### app_settings seed rows (in `0001_initial.py`)

- **D-17: Seed liberally — Phase 0 owns the foundational `app_settings` row set.** Locked rows:
  - `recommendation_region = "US"` (spec-mandated)
  - `min_sessions_for_ai = "3"` (PITFALL AI-7)
  - `min_flavor_notes_for_ai = "5"` (PITFALL AI-7)
  - `ai_primary_max_searches = "5"` (PITFALL COST-5)
  - `ai_broadened_max_searches = "3"` (PITFALL COST-5)
  - `ai_tool_version_anthropic = "web_search_20250305"` (PITFALL AI-5)
  - `ai_tool_version_openai = "web_search"` (PITFALL AI-5; the non-preview variant)
  - `ai_provider_default = "anthropic"` (PROJECT.md aesthetic / cost ordering)
  - `last_ai_run_status = "never_run"` (PITFALL COST-3)
  - `last_backup_status = "never_run"` (Phase 8 health panel)
  - `last_backup_at = NULL` (Phase 8 health panel)
  - `setup_completed = "false"` (PITFALL SEC-5 — read by Phase 2 `/setup` under `SELECT ... FOR UPDATE`)
  - `photo_max_bytes = "5242880"` (Phase 4 — 5 MiB per spec)
  - `csv_import_max_rows = "5000"` (Phase 5 CSV import)
  - `home_recent_brews_limit = "10"` (Phase 6 — per spec)
  - `home_top_coffees_limit = "5"` (Phase 6 — per spec, "top 5")
  - `home_top_coffees_min_sessions = "2"` (Phase 6 — per spec, "min 2 sessions")
  - `home_top_flavors_min_rating = "4.0"` (Phase 6 — per spec, "4.0+ rated sessions")
  - `home_sweetspot_min_sessions = "3"` (Phase 6 — per spec, "min 3 sessions")
- `app_settings` schema follows the spec's `(key, value, value_type, updated_at)` shape so the Phase 9 admin editor can render the right input control. Planner picks `value_type` enum values (`string`, `int`, `float`, `bool`, `null`) and any indexes (`UNIQUE(key)`).

### Tooling / dev ergonomics

- **D-18: `Makefile` ships in Phase 0** wrapping the common docker compose flows. Targets: `up`, `down`, `logs`, `psql`, `migrate`, `revision`, `test`, `shell`, `build`. Mirrors CLAUDE.md's "Working with the code" block — convenience over correctness; raw `docker compose` commands still work.
- **D-19: `pyproject.toml` lands the ruff + mypy tool configs.** No GitHub Actions YAML yet (Phase 12 owns CI). `tests/` is a placeholder directory with a `conftest.py` skeleton and one smoke test asserting `GET /healthz` returns 200 inside a TestClient. pytest + ruff + mypy listed in `requirements-dev.txt` (or a `pyproject.toml` optional-dependencies group — planner's choice).

### Claude's Discretion

- **Cookie-name conventions, signed-cookie serializer choice** — not Phase 0's concern; Phase 1 owns this.
- **Concrete column types beyond what spec enumerates** — e.g., `users.username` as `citext` unique, `users.password_hash` as `text NOT NULL`, `users.is_admin` as `boolean NOT NULL DEFAULT false`, `users.is_active` as `boolean NOT NULL DEFAULT true`, `users.created_at`/`updated_at` as `timestamptz NOT NULL DEFAULT now()`, `users.last_login_at` as `timestamptz NULL`. Planner uses spec + Phase 2 implications.
- **`bags` schema:** spec (CAT-04) enumerates `id`, `coffee_id`, `roast_date`, `weight_grams`, `opened_at`, `finished_at`, `notes`, `created_at`, `updated_at`. `coffee_id` is FK to `coffees(id)` — but `coffees` doesn't exist until Phase 4. Planner decides: ship `coffee_id` as a NOT NULL `bigint` with a deferred FK constraint added in Phase 4's migration, OR ship it as NULLABLE `bigint` now and tighten to NOT NULL in Phase 4. Prefer the first (forward-defensible).
- **`ai_recommendations` schema:** spec (AI-02) enumerates 16+ columns. `user_id` is FK to `users(id)`. `input_signature` gets a btree index for the nightly signature-comparison query. Planner picks index choices for `(user_id, recommendation_type, generated_at DESC)` and any other access patterns visible from the AI-flow requirements.
- **Tailwind palette exact hex values, `cream-50` through `cream-950` and `espresso-50` through `espresso-950` ramps** — planner picks defensible values; tuned during `/gsd-ui-phase` later.
- **Whether Jinja2's `tailwind_css_path` global is computed once at startup or memoized per-request** — planner's call; startup is fine and avoids per-request glob.
- **Exact `pyproject.toml` ruff rule set + mypy `strict` knobs** — pick reasonable defaults that match CLAUDE.md conventions (ruff format ON, `extend-select = ["E", "F", "I", "B", "UP", "S"]`, mypy `strict_optional`, etc.). Phase 12 hardening can tighten later.
- **Dockerfile base image patch level** — `python:3.12-slim` is fine; planner pins to a specific digest if reproducibility matters.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level
- `.planning/PROJECT.md` §"Key Decisions" — single uvicorn worker (row 16), HTMX 2.x (row 9), Tailwind standalone CLI (row 10), bags table in Foundation (row 11), wishlist_entries in Foundation (row 12), MultiFernet from day one (row 18 — env var defined here, wiring is Phase 3).
- `.planning/REQUIREMENTS.md` §"Foundation" (FOUND-01 through FOUND-12), §"Shared Catalog" (CAT-04 for `bags`), §"AI Integration" (AI-02 for `ai_recommendations`). Verbatim requirements.
- `.planning/ROADMAP.md` §"Phase 0: Foundation" — goal, 5 success criteria, dependencies (none — first phase), Notes carrying SH-2 / SH-5 / SH-6 / AI-6 / COST-1.
- `.planning/STATE.md` — current decision accumulator + the four plan-phase research flags carried forward (none for Phase 0).
- `.planning/phases/01-middleware/01-CONTEXT.md` — Phase 1 has already locked decisions that depend on Phase 0 plumbing being present (uvicorn proxy-header flag, single-worker, structlog setup). Read so Phase 0 doesn't accidentally contradict the Phase 1 middleware order (D-15 in 01-CONTEXT.md: "ProxyHeaders (uvicorn flag) → SessionMiddleware → ...").

### Research output
- `.planning/research/STACK.md` §1 (pinned versions: FastAPI 0.136, SQLAlchemy 2.0.49, Alembic 1.18, psycopg 3.3, structlog 25.5, pydantic-settings 2.14, python-multipart 0.0.28, Pillow 12.2 — Pillow not needed yet but pin lands here so requirements.txt is complete from day one), §2 (gap library notes: pyproject + ruff 0.15, pytest 9.0 placeholder), §3.1 (Tailwind CDN vs CLI tradeoff and CSP impact), §3.3 (SQLAlchemy 2.0 + psycopg 3 + asyncio interaction), §3.4 (FastAPI lifespan vs startup/shutdown — use lifespan).
- `.planning/research/PITFALLS.md` §4 (SH-2 pool exhaustion + explicit knobs, SH-3 volume restore docs, SH-5 pg_dump version match, SH-6 X-Forwarded-Proto), §1 (AI-5 tool versioning seeded in app_settings, AI-7 cold-start thresholds), §7 (COST-3 health row, COST-5 max_uses ceilings). These are the load-bearing ones for Phase 0.
- `.planning/research/ARCHITECTURE.md`, `.planning/research/FEATURES.md`, `.planning/research/SUMMARY.md` — context only; nothing Phase-0-specific that isn't in the other refs.

### Operational + spec
- `CLAUDE.md` §"Stack invariants" (locked versions / no-change without ask list), §"Code conventions" (ruff format, mypy, SQLAlchemy 2.0 style, conventional commits), §"Files worth knowing" (target file layout), §"Adding a new env var" (the 4-step procedure that Phase 0 establishes by example), §"Things to never do silently" (the don't-bypass-encryption / don't-disable-CSRF list — Phase 0 lays the floor for the rest).
- `snobbery-gsd-prompt.md` — original product brief. Historical reference where the .planning/ docs diverge, those win.

### External library docs (planner verifies via Context7 in plan-phase)
- `python:3.12-slim` Dockerfile base image — apt source list pattern for adding PostgreSQL's official repo (so we can install `postgresql-client-16`, not the slim default 15).
- Tailwind CSS standalone CLI binary — official install URL pattern, current version (v4.x line), invocation syntax for `--minify` + content scanning.
- Alembic env.py pattern for SQLAlchemy 2.0 (`Mapped[...]` autogenerate) + psycopg 3 (URL prefix `postgresql+psycopg://`).
- structlog `ProcessorFormatter` integration with stdlib `logging` (so uvicorn/FastAPI/SQLAlchemy logs merge into the same JSON stream).
- FastAPI `lifespan` async context manager pattern (engine open at startup, dispose at shutdown).
- Docker Compose `depends_on: condition: service_healthy` syntax and the `pg_isready` HEALTHCHECK pattern for `postgres:16-alpine`.

</canonical_refs>

<code_context>
## Existing Code Insights

**Greenfield phase — no existing application code yet.** This is the phase that *creates* the patterns later phases inherit. Nothing to extend or refactor.

### Reusable Assets
- None on disk. `snobbery-gsd-prompt.md` is the historical spec; `CLAUDE.md` is the aspirational guidance that becomes operational truth once Phase 0 ships.

### Established Patterns (set by this phase, inherited by every later phase)
- **"All env reads go through `app/config.py`"** — Pydantic-settings singleton. Other modules import `from app.config import settings` and read attributes. CI grep test forbidding `os.environ` outside `app/config.py` lands in Phase 1 (per Phase 1 CONTEXT.md `<specifics>`); Phase 0 establishes the rule.
- **"Sync FastAPI handlers + sync SQLAlchemy sessions are the default; async is reserved for AI calls"** — set by `app/db.py` shipping only a sync engine + sessionmaker in Phase 0. Phase 7 adds the async path for `ai_service.py`.
- **"Cross-cutting concern → `app/middleware/`"** — established by scaffolding the empty package; Phase 1 fills it.
- **"Feature surface → `app/routers/`"** — established by scaffolding the empty package; Phase 2+ fills it.
- **"Stateful logic → `app/services/`"** — established by scaffolding the empty package; Phase 3+ fills it.
- **"Migrations are autogenerated from `Mapped[...]` models in `app/models/` via alembic env.py; one migration per logical change; never edit a committed migration"** — Phase 0 lays the first one, future phases extend.
- **"Templates live in `app/templates/`; autoescape ON globally; never `|safe`; never `hx-on:*`"** — Phase 0 ships `base.html` + `pages/index.html` setting the convention. Phase 1 adds the CI grep tests enforcing it.
- **"Static assets live under `app/static/`; CSS is content-hash-suffixed at image build time"** — Phase 0 ships `tailwind.<hash>.css`.

### Integration Points
- **NGINX (host-side, outside the repo)** — Phase 0 documents the server-block snippet in README and trusts `TRUSTED_PROXY_IPS` env var. Phase 1's README section adds the full HSTS + `proxy_set_header X-Forwarded-Proto $scheme` + `proxy_buffering off` (forward-looking for Phase 7 SSE, even though Phase 7 chose polling).
- **Docker host volumes** — `coffee_snobbery_postgres_data` (db data), `coffee_snobbery_photos` (Phase 4 photo uploads land here), `coffee_snobbery_backups` (Phase 8 backups land here). All three are *named* volumes (not bind mounts) per PITFALL SH-4.

</code_context>

<specifics>
## Specific Ideas

- **Three places loudly say "single worker":** (1) `README.md` deployment section, (2) `entrypoint.sh` comment block above the uvicorn invocation, (3) a top-of-file comment in `app/services/scheduler.py` (placeholder file created by Phase 0 with just the comment + a `# Phase 8 owns this module` docstring — so the comment is in place before the scheduler exists). Anyone trying to add `--workers 4` trips over the note three times before they succeed.
- **`.env.example` env var generation hints** (one-liner per var):
  - `APP_SECRET_KEY` → `python -c "import secrets; print(secrets.token_urlsafe(64))"`
  - `APP_ENCRYPTION_KEY` → `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
  - `TRUSTED_PROXY_IPS` → comma-separated list, e.g. `127.0.0.1` for local NGINX
  - `APP_TIMEZONE` → IANA name, e.g. `America/Los_Angeles`
  - `BACKUP_RETENTION_DAYS` → integer, default `14`
  - `LOG_LEVEL` → one of `DEBUG INFO WARNING ERROR`, default `INFO`
  - `LOG_FORMAT` → `json` (default) or `console`
  - `DATABASE_URL` → `postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@coffee-snobbery-db:5432/${POSTGRES_DB}`
  - `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` → user-chosen
- **README.md NGINX server-block snippet** lives in Phase 0 in skeletal form (`proxy_pass http://127.0.0.1:8080;` + `proxy_set_header Host $host;` + `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;` + `proxy_set_header X-Forwarded-Proto $scheme;`) so the `TRUSTED_PROXY_IPS=127.0.0.1` recommendation in `.env.example` lines up with reality. Phase 1 extends it with HSTS / `proxy_buffering off` / SSL cipher list.
- **`MultiFernet` env var shape is established here, used in Phase 3.** `APP_ENCRYPTION_KEY` is documented as "comma-separated list of Fernet keys; first = primary for encryption, all attempted for decryption." Phase 0's `app/config.py` parses it as `List[str]`; Phase 3 builds the `MultiFernet([Fernet(k) for k in keys])` instance in `app/services/encryption.py`.

</specifics>

<deferred>
## Deferred Ideas

- **CI YAML (GitHub Actions).** Phase 0 lands tool configs in `pyproject.toml` but no `.github/workflows/`. Phase 12 (Hardening + Tests) owns the actual CI pipeline.
- **Per-fragment cache headers + `FragmentCacheHeadersMiddleware`** — Phase 1 (per 01-CONTEXT.md D-11).
- **Per-request `request_id` correlation in logs** — structlog config in Phase 0 supports binding it, but the actual middleware that mints and binds the ID is Phase 1.
- **`/debug/proxy` endpoint** — Phase 1 (already decided in 01-CONTEXT.md D-16).
- **`/setup` route body + `setup_completed` flip + first admin creation** — Phase 2. Phase 0 only seeds the `setup_completed = false` row; no route handler.
- **`MultiFernet` instance construction + `api_credentials` table** — Phase 3. Phase 0 only defines and documents `APP_ENCRYPTION_KEY`.
- **Catalog tables (`coffees`, `equipment`, `recipes`, `roasters`, `flavor_notes`)** — Phase 4. Phase 0 ships `bags` with a `coffee_id` column whose FK constraint will be added in Phase 4's migration (or, if the planner picks the simpler path, the FK is added in Phase 4 once `coffees` exists; Phase 0 ships the column as a typed `bigint`).
- **APScheduler + nightly `pg_dump` + photos tarball + `SQLAlchemyJobStore`** — Phase 8. Phase 0 ships the comment in a placeholder `app/services/scheduler.py` mentioning the single-worker requirement.
- **PWA manifest + service worker + maskable icons** — Phase 11. Phase 0's `base.html` already has the dual `theme-color` meta tags per PITFALL PWA-5, so adding the manifest is additive later.
- **`tests/` real coverage beyond a `/healthz` smoke test** — Phase 12.
- **Pinning Dockerfile base image to a specific digest for reproducibility** — defer to Phase 12 hardening; `python:3.12-slim` tag is fine for v1 launch.
- **Whether to add the second `*_actual` and TDS columns to a future `brew_sessions` migration** — PROJECT.md row 13 locks the decision (yes, in v1). Phase 5 owns the `brew_sessions` migration. Phase 0 does not touch it.
- **Tailwind palette exact hex tuning** — first `/gsd-ui-phase` pass (likely before Phase 4) refines the cream/espresso ramp. Phase 0 ships defensible defaults.

</deferred>

---

*Phase: 0-Foundation*
*Context gathered: 2026-05-16*
