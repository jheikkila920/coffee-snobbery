# Phase 0: Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-16
**Phase:** 0-Foundation
**Areas discussed:** First-migration scope & split, Dockerfile + entrypoint architecture, app/ skeleton, app_settings seed rows, wrap-up adds

---

## First-migration scope & split

### Q1 — Where does `wishlist_entries` land?

| Option | Description | Selected |
|--------|-------------|----------|
| Land in Phase 0 first-migration set | Matches PROJECT.md decision row 11. Cheap now, expensive to retrofit later (same logic as `bags` and `ai_recommendations` cost columns). | ✓ |
| Defer to Phase 4 (shared catalog) | Treats wishlist as a catalog entity. Risk: Phase 7 AI rec card lands first and has nowhere to write "Add to wishlist" results. | |
| Defer to Phase 7 (AI services) | Lands with the consumer. Tightest scope. Risk: Phase 7 owns migration + AI plumbing — wider scope. | |

**User's choice:** Phase 0.
**Notes:** Matches the established "ship schema early, retrofit is painful" pattern.

### Q2 — Migration file split

| Option | Description | Selected |
|--------|-------------|----------|
| One mega-migration: `0001_initial.py` | Single file: extensions + 5 tables + seed inserts. Clean blame; one `upgrade head`. | ✓ |
| Split by concern: `0001_extensions` / `0002_core_tables` / `0003_seed_app_settings` | Cleaner per-concern blame; re-seed without re-schema. Cost: 3 files, alembic dep noise. | |
| Split by lifecycle: `0001_extensions_and_users` / `0002_bags_ai_wishlist_settings` | Auth-adjacent vs feature tables. Arbitrary line. | |

**User's choice:** Single `0001_initial.py`.

---

## Dockerfile + entrypoint architecture

### Q1 — Dockerfile structure

| Option | Description | Selected |
|--------|-------------|----------|
| Multi-stage: tailwind-builder → final runtime | Stage 1 downloads CLI + compiles. Stage 2 (`python:3.12-slim`) copies CSS only. Smaller final image, better layer caching. | ✓ |
| Single-stage: download + compile during build | One Dockerfile. CLI download bloats cache. | |
| Single-stage with CLI retained | Largest image; easiest dev loop. | |

**User's choice:** Multi-stage.

### Q2 — Container runtime user

| Option | Description | Selected |
|--------|-------------|----------|
| Non-root `app` user, UID 1000 | Standard hardening; named volumes handle ownership. | ✓ |
| Run as root | Simpler; container behind NGINX. CIS Docker flags it. | |

**User's choice:** Non-root.

### Q3 — DB readiness

| Option | Description | Selected |
|--------|-------------|----------|
| Compose `depends_on: condition: service_healthy` + Postgres HEALTHCHECK | Compose orchestrates; entrypoint.sh stays clean. | ✓ |
| Bash wait-for-db loop in entrypoint.sh | Works without compose. ~20 LOC of bash to maintain. | |
| SQLAlchemy `pool_pre_ping` only | Trust the pool. Noisy logs on cold start. | |

**User's choice:** Compose `depends_on: condition: service_healthy`.

### Q4 — Healthcheck

| Option | Description | Selected |
|--------|-------------|----------|
| `GET /healthz` with 1-row SELECT | Proves both web up AND db reachable. 2s pool_timeout guard. | ✓ |
| `GET /healthz` returns 200 without DB | True liveness check; never flaps on DB hiccups. | |
| No app-level — TCP port check | Cheapest. Doesn't catch stuck Python. | |

**User's choice:** DB-touching `/healthz`.

---

## app/ skeleton — modules + routes

### Q1 — Subpackage scaffolding

| Option | Description | Selected |
|--------|-------------|----------|
| Scaffold all | Phase 0 creates middleware/, routers/, services/ with one-line "owned by Phase X" docstrings. Directory contract established once. | ✓ |
| Scaffold only what Phase 0 needs | Each later phase creates its own packages. Zero speculative files. | |

**User's choice:** Scaffold all.

### Q2 — Routes in Phase 0

| Option | Description | Selected |
|--------|-------------|----------|
| `/healthz` + bare `GET /` placeholder | Visually confirms Tailwind compiled; ~30 LOC + 2 templates. | ✓ |
| `/healthz` only — root 404s | Strictly minimal. Trust the build, no visual confirmation. | |
| `/healthz` + `/` + a `/static/css/tailwind.<hash>.css` smoke endpoint | Overkill — StaticFiles already serves /static/* directly. | |

**User's choice:** `/healthz` + `GET /`.

### Q3 — `base.html`

| Option | Description | Selected |
|--------|-------------|----------|
| Real shell, layout-only | Doctype, viewport, dual theme-color, Tailwind link, body palette classes, block content. No HTMX/Alpine yet. | ✓ |
| Stub `base.html` | Empty html/body/block. Phase 4 redoes theme-color etc. | |
| No base.html, `GET /` returns plain text | Smallest surface. Loses Tailwind visual confirmation. | |

**User's choice:** Real shell.

### Q4 — Tailwind palette baseline

| Option | Description | Selected |
|--------|-------------|----------|
| Ship palette in Phase 0's tailwind.config.js | `theme.extend.colors.{cream, espresso}` + `darkMode: 'media'`. Exact hexes tunable. | ✓ |
| Ship vanilla Tailwind; defer to `/gsd-ui-phase 4` | Minimal config. Phase 1-3 minor UI bits ship without an established palette. | |

**User's choice:** Ship palette baseline.

---

## app_settings seed rows in migration 1

### Q1 — Core AI-flow keys

| Option | Description | Selected |
|--------|-------------|----------|
| `recommendation_region = US` | Spec-mandated Phase 0 seed. | ✓ |
| `min_sessions_for_ai = 3` + `min_flavor_notes_for_ai = 5` | PITFALL AI-7 cold-start gates. | ✓ |
| `ai_primary_max_searches = 5` + `ai_broadened_max_searches = 3` | PITFALL COST-5 cost ceilings. | ✓ |
| `ai_tool_version_anthropic = web_search_20250305` + `ai_tool_version_openai = web_search` | PITFALL AI-5 model/tool versioning, swap from admin without redeploy. | ✓ |

**User's choice:** All four.

### Q2 — Operational/health keys

| Option | Description | Selected |
|--------|-------------|----------|
| `last_ai_run_status` (PITFALL COST-3) | Phase 8 writes, Phase 9 reads. Seed `never_run` now. | ✓ |
| `last_backup_status` + `last_backup_at` | Phase 8 backups health panel. | ✓ |
| `setup_completed = false` (PITFALL SEC-5) | Read by Phase 2 `/setup` under `SELECT ... FOR UPDATE`. | ✓ |

**User's choice:** All three.

### Q3 — Phase-specific keys

| Option | Description | Selected |
|--------|-------------|----------|
| Seed all phase-specific keys in Phase 0 too | "If a key shows up in app_settings, it was seeded by the foundation." Bigger 0001_initial.py but consistent. | ✓ |
| Only seed Phase-0-or-cross-phase keys | Tighter Phase 0; later phases add their own keys in their own migrations. | |

**User's choice:** Seed all.

---

## Wrap-up adds

| Option | Description | Selected |
|--------|-------------|----------|
| No, write CONTEXT.md | All gray areas covered. | ✓ |
| structlog format = LOG_FORMAT env var (json\|console), default json | ConsoleRenderer for dev legibility. ~10 LOC. | ✓ |
| docker-compose.yml publishes web service on `127.0.0.1:8080` only | Don't expose dev port externally. | ✓ |
| Makefile wrapping the docker compose commands | up/logs/psql/migrate/test convenience. | ✓ |

**User's choice:** All four (proceeded with CONTEXT write AND included all three adds).

---

## Claude's Discretion

- Cookie names + signed-cookie serializer choice (Phase 1 owns).
- Concrete column types beyond what REQUIREMENTS.md/spec enumerate (planner picks defensible defaults; e.g., `users.username` as `citext`, password_hash as `text NOT NULL`).
- Whether `bags.coffee_id` ships NULLABLE in Phase 0 or NOT NULL with the FK deferred until Phase 4 creates `coffees` (planner's call — forward-defensible is preferred).
- Exact Tailwind palette hex values across the 50-950 ramp (tuned during first `/gsd-ui-phase` pass).
- Whether the Jinja2 `tailwind_css_path` global is computed once at startup or memoized per-request.
- `pyproject.toml` ruff rule set + mypy strictness knobs.
- `python:3.12-slim` digest pin (left as tag for v1; Phase 12 can tighten).

---

## Deferred Ideas

- CI YAML (GitHub Actions) — Phase 12.
- `FragmentCacheHeadersMiddleware`, `/debug/proxy`, structured-logger middleware that mints `request_id` — Phase 1.
- `/setup` route body + first-admin flow + flipping `setup_completed` — Phase 2.
- `MultiFernet` instance construction + `api_credentials` table — Phase 3 (env var `APP_ENCRYPTION_KEY` shape established here).
- Catalog tables (`coffees`, `equipment`, `recipes`, `roasters`, `flavor_notes`) — Phase 4.
- APScheduler + nightly `pg_dump` + photos tarball — Phase 8.
- PWA manifest + service worker + maskable icons — Phase 11 (dual `theme-color` meta lands now to avoid PITFALL PWA-5 flicker later).
- Real test coverage beyond `/healthz` smoke — Phase 12.
- Tailwind palette hex tuning — first `/gsd-ui-phase` pass (likely pre-Phase-4).
