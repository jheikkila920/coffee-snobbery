---
phase: 00-foundation
verified: 2026-05-17T15:30:00Z
status: passed
score: 5/5 success criteria verified (static gates); 5 live-docker gates deferred to `make smoke`
requirements_score: 14/14 requirements addressed in code
overrides_applied: 0
static_gates_passed: 13
runtime_gates_deferred: 5
---

# Phase 0: Foundation Verification Report

**Phase Goal (verbatim from ROADMAP.md §Phase 0):**

> A clean `git clone` + `docker compose up -d` brings up a two-container stack with Postgres extensions installed, the first migration applied (including the `bags` and `ai_recommendations` tables so later phases never need a painful retrofit), Tailwind compiled into the image, and uvicorn running as a single worker behind the proxy-headers trust list.

**Verified:** 2026-05-17
**Status:** READY (with deferred live-docker smoke)
**Re-verification:** No — initial verification

---

## Per-Criterion Verdict

### Success Criterion #1 — Clean checkout `docker compose up -d` brings up the two-container stack

**Verdict: PASS (static); live-docker leg deferred to `make smoke`.**

| Sub-claim | Evidence | Status |
|---|---|---|
| Web service `coffee-snobbery` declared | `docker-compose.yml:43-67` (container_name + image + build) | PASS |
| DB service `coffee-snobbery-db` declared | `docker-compose.yml:22-41` (container_name=coffee-snobbery-db) | PASS |
| Bridge `coffee-snobbery-net` declared | `docker-compose.yml:69-72` (`driver: bridge`, `name: coffee-snobbery-net`) | PASS |
| Three named volumes: `coffee_snobbery_postgres_data`, `coffee_snobbery_photos`, `coffee_snobbery_backups` | `docker-compose.yml:74-80` (each `name:` matches volume key) | PASS |
| Host port bind `127.0.0.1:8080:8000` (never `0.0.0.0`) | `docker-compose.yml:66-67` (`"127.0.0.1:8080:8000"`) | PASS |
| `pg_dump` matches Postgres 16 server version | `Dockerfile:62-76` — installs `postgresql-client-16` from PGDG apt repo | PASS (static) |
| Live: `docker compose up` produces healthy stack + `pg_dump --version` reports 16.x | No docker daemon on this host | DEFERRED to `make smoke` |

---

### Success Criterion #2 — Container start runs `alembic upgrade head`; migration installs extensions + tables + seeds

**Verdict: PASS.**

| Sub-claim | Evidence | Status |
|---|---|---|
| `entrypoint.sh` runs `alembic upgrade head` before uvicorn | `entrypoint.sh:24` (`alembic upgrade head`) then `entrypoint.sh:30` (`exec uvicorn ...`) | PASS |
| `CREATE EXTENSION IF NOT EXISTS citext` | `app/migrations/versions/0001_initial.py:59` | PASS |
| `CREATE EXTENSION IF NOT EXISTS pg_trgm` | `app/migrations/versions/0001_initial.py:60` | PASS |
| `CREATE EXTENSION IF NOT EXISTS unaccent` | `app/migrations/versions/0001_initial.py:61` | PASS |
| `users` table created | `app/migrations/versions/0001_initial.py:64-93` (9 columns, CITEXT username/email, partial unique index) | PASS |
| `bags` table created (CAT-04) | `app/migrations/versions/0001_initial.py:99-121` (9 columns; `coffee_id` BigInteger NOT NULL, no FK by design) | PASS |
| `wishlist_entries` table created | `app/migrations/versions/0001_initial.py:124-147` | PASS |
| `ai_recommendations` table created (AI-02) | `app/migrations/versions/0001_initial.py:153-194` | PASS |
| All 11 cost-observability columns present (web_search_count, tokens_input_search, provider_used, model_used, tool_version, input_signature, url_verified, duration_ms, generated_by, tokens_input, tokens_output, error_status) | `app/migrations/versions/0001_initial.py:155-187` (11 columns; one is `input_signature` which lives on the table as a separate column) | PASS |
| `app_settings` table created | `app/migrations/versions/0001_initial.py:197-216` | PASS |
| 19 documented `app_settings` rows seeded | `app/migrations/versions/0001_initial.py:230-358` (19 dicts in `op.bulk_insert(...)` call — exact count verified) | PASS (ROADMAP SC#2 wording says "the documented `app_settings` rows" without count; CONTEXT D-17 specifies 19; migration delivers 19) |
| Live: migration applies cleanly on container start | No docker daemon on this host | DEFERRED to `make smoke` |

**Note:** The verification prompt mentioned "18-19 seed rows" but CONTEXT D-17, the migration, the model docstring, and `test_app_settings_seeded_with_19_rows` consistently state 19. Counted directly from the migration body: 19 dicts in the `op.bulk_insert` array.

---

### Success Criterion #3 — `app/config.py` is the only `os.environ` reader; `.env.example` documents every var

**Verdict: PASS.**

| Sub-claim | Evidence | Status |
|---|---|---|
| `app/config.py` is the only `os.environ` reader | Grep `os.environ` in `app/`: matches `app/config.py` (docstring only — the actual env read is via pydantic-settings `BaseSettings`) and `app/migrations/env.py` (docstring mentions "we never read os.environ here" — no live reads). FOUND-10 test `tests/test_no_direct_env.py` excludes `migrations/` and `config.py`; runs green. | PASS |
| Pydantic-settings `Settings` class is sole env consumer | `app/config.py:26-66` (`class Settings(BaseSettings)`) with `extra="forbid"` and 11 typed fields | PASS |
| `APP_SECRET_KEY` in `.env.example` + Settings | `.env.example:20`, `app/config.py:44` | PASS |
| `APP_ENCRYPTION_KEY` in `.env.example` + Settings | `.env.example:24`, `app/config.py:48` | PASS |
| `TRUSTED_PROXY_IPS` in `.env.example` + Settings | `.env.example:28`, `app/config.py:51` | PASS |
| `APP_TIMEZONE` in `.env.example` + Settings | `.env.example:30`, `app/config.py:52` | PASS |
| `BACKUP_RETENTION_DAYS` in `.env.example` + Settings | `.env.example:32`, `app/config.py:53` | PASS |
| `LOG_LEVEL` in `.env.example` + Settings | `.env.example:36`, `app/config.py:56` | PASS |
| `DATABASE_URL` in `.env.example` + Settings | `.env.example:16`, `app/config.py:39` | PASS |
| `POSTGRES_USER/PASSWORD/DB` triple in `.env.example` + Settings | `.env.example:11-14`, `app/config.py:36-38` | PASS |
| One-liner generation hints documented in `.env.example` | `.env.example:19` (`secrets.token_urlsafe(64)`), `:22` (`Fernet.generate_key()`), `:12` (`openssl rand -hex 32`) | PASS |
| `tests/test_env_example.py` enforces parity | `tests/test_env_example.py:38-52` (asserts strict equality between `Settings.model_fields` and `.env.example` keys); runs green (`1 passed`) | PASS |
| `tests/test_no_direct_env.py` enforces FOUND-10 | `tests/test_no_direct_env.py:35-53` — runs green (`1 passed`) | PASS |

**Bonus note:** `LOG_FORMAT` is also documented in both files (`.env.example:38`, `app/config.py:57`). The ROADMAP enumerates 8 vars; the implementation ships 11 (the spec's 8 + `LOG_FORMAT` + the three POSTGRES_* split out from the conceptual "Postgres triple"). All within the contract.

---

### Success Criterion #4 — uvicorn `--workers 1 --proxy-headers --forwarded-allow-ips=$TRUSTED_PROXY_IPS`; single-worker rule in 3 files

**Verdict: PASS.**

| Sub-claim | Evidence | Status |
|---|---|---|
| `--workers 1` flag | `entrypoint.sh:33` (`--workers 1 \`) | PASS |
| `--proxy-headers` flag | `entrypoint.sh:34` | PASS |
| `--forwarded-allow-ips "${TRUSTED_PROXY_IPS:-127.0.0.1}"` flag | `entrypoint.sh:35` | PASS |
| Single-worker rule in `entrypoint.sh` | `entrypoint.sh:4-16` (comment block + literal `--workers 1`) — "location #1 of three" | PASS |
| Single-worker rule in `app/services/scheduler.py` | `app/services/scheduler.py:3-16` (top-of-file comment block) — "location #2 of three" | PASS |
| Single-worker rule in `README.md` | `README.md:63-84` ("DO NOT change" + 4x AI cost rationale + cross-refs) — "location #3 of three" | PASS |
| Audit grep `--workers 1\|single worker` returns ≥3 hits across all 3 files | Grep returned 7 hits across all 3 files (`README.md:65`, `README.md:72`, `README.md:81`, `entrypoint.sh:9`, `entrypoint.sh:33`, `app/services/scheduler.py:4`, `app/services/scheduler.py:9`) | PASS (exceeds gate) |

---

### Success Criterion #5 — Tailwind built by standalone CLI (no Node); structlog emits JSON with `request_id` correlation seat

**Verdict: PASS.**

| Sub-claim | Evidence | Status |
|---|---|---|
| Multi-stage Dockerfile with `tailwind-builder` stage | `Dockerfile:19-52` (Stage 1 `debian:bookworm-slim AS tailwind-builder`) | PASS |
| Tailwind v4 standalone CLI binary downloaded (no Node, no npm) | `Dockerfile:31-38` (curl from GitHub releases; `chmod +x /usr/local/bin/tailwindcss`) | PASS |
| `tailwindcss --minify` invoked against source CSS | `Dockerfile:46-52` (`tailwindcss -i app/static/css/tailwind.src.css -o ...`) | PASS |
| Output is content-hashed `tailwind.<sha8>.css` | `Dockerfile:47` (`HASH="$(sha256sum app/static/css/tailwind.src.css \| cut -c1-8)"`) | PASS |
| CSS served at `/static/css/tailwind.<hash>.css` | `app/main.py:61-89` (`compute_tailwind_css_path()` globs the hashed file and returns `/static/css/{name}`) + `app/main.py:123` (`app.mount("/static", StaticFiles(directory="app/static"), name="static")`) | PASS |
| structlog `JSONRenderer` by default | `app/logging.py:122-126` (`if format == "console": ... else: JSONRenderer()`) — default `format="json"` per `app/logging.py:87` | PASS |
| `request_id` correlation seat wired | `app/logging.py:115-121` — `pre_chain[0]` is `structlog.contextvars.merge_contextvars`. Phase 1's middleware will call `bind_contextvars(request_id=...)`. Verified by `tests/test_logging.py::test_contextvars_processor_present_in_chain` (green) | PASS |
| `timestamp_iso` key per FOUND-11 contract | `app/logging.py:114` (`TimeStamper(fmt="iso", key="timestamp_iso")`) — pinned by `tests/test_logging.py::test_json_renderer_shape` (green) | PASS |
| Live: hashed Tailwind CSS lands in built image at `/app/static/css/` | No docker daemon on this host | DEFERRED to `make smoke` |

---

## Requirement Coverage Map (14/14)

| Req ID | Phase 0 description | Source | Status | Evidence |
|---|---|---|---|---|
| FOUND-01 | `docker compose up -d` from clean checkout → working app on host port 8080 | 00-05-PLAN | SATISFIED (static) | `docker-compose.yml`, `Dockerfile`, `entrypoint.sh` — full stack declared; live boot is `make smoke` |
| FOUND-02 | Two container services on `coffee-snobbery-net` with fixed names | 00-05-PLAN | SATISFIED | `docker-compose.yml:22-72` |
| FOUND-03 | Three named volumes (`coffee_snobbery_postgres_data`, `_photos`, `_backups`) | 00-05-PLAN | SATISFIED | `docker-compose.yml:74-80` with explicit `name:` keys |
| FOUND-04 | Single uvicorn worker; documented loudly in README + entrypoint | 00-04-PLAN | SATISFIED | `entrypoint.sh:33`, single-worker rule in 3 files |
| FOUND-05 | Alembic migrations auto-run on container start; first creates schema + seeds | 00-03-PLAN | SATISFIED | `entrypoint.sh:24` + `0001_initial.py` |
| FOUND-06 | `citext`, `pg_trgm`, `unaccent` installed in first migration | 00-03-PLAN | SATISFIED | `0001_initial.py:59-61` |
| FOUND-07 | `postgresql-client-16` installed in web image (pg_dump version parity) | 00-04-PLAN | SATISFIED | `Dockerfile:62-76` (PGDG apt repo + `postgresql-client-16`) |
| FOUND-08 | App honors `X-Forwarded-Proto`/`X-Forwarded-For` from `TRUSTED_PROXY_IPS` | 00-04-PLAN | SATISFIED | `entrypoint.sh:34-35` (`--proxy-headers --forwarded-allow-ips`) + `app/config.py:51` |
| FOUND-09 | `.env.example` documents all env vars with one-liner hints | 00-01-PLAN | SATISFIED | `.env.example` + `tests/test_env_example.py` (green) |
| FOUND-10 | Pydantic-settings in `app/config.py` is sole `os.environ` reader | 00-01-PLAN | SATISFIED | `app/config.py:26-66` (`Settings(BaseSettings)`) + `tests/test_no_direct_env.py` (green) |
| FOUND-11 | structlog JSON output with request_id correlation seat | 00-02-PLAN | SATISFIED | `app/logging.py` + `tests/test_logging.py` 5 tests all green |
| FOUND-12 | Tailwind compiled by standalone CLI (no Node), content-hashed filename | 00-04-PLAN | SATISFIED | `Dockerfile` stage 1 + `app/main.py:compute_tailwind_css_path()` |
| CAT-04 | `bags` table with 9 spec columns | 00-03-PLAN | SATISFIED | `0001_initial.py:99-121` + `app/models/bag.py` (`Mapped[...]`) |
| AI-02 | `ai_recommendations` persists every call with full column set | 00-03-PLAN | SATISFIED | `0001_initial.py:153-194` (18 cols incl. all 11 cost-obs) + `app/models/ai_recommendation.py` |

**Orphaned requirements:** None. All 14 are claimed by Phase 0 plans (FOUND-01..03 by Plan 05; FOUND-04, FOUND-07, FOUND-08, FOUND-12 by Plan 04; FOUND-05, FOUND-06, CAT-04, AI-02 by Plan 03; FOUND-11 by Plan 02; FOUND-09, FOUND-10 by Plan 01).

---

## Architecture & Pattern Verification (additional dimensions)

### Bag-as-instance schema (CAT-04)

| Check | Evidence | Status |
|---|---|---|
| 9 spec columns present | `0001_initial.py:99-121` — `id`, `coffee_id`, `roast_date`, `weight_grams`, `opened_at`, `finished_at`, `notes`, `created_at`, `updated_at` | PASS |
| `coffee_id` is `BigInteger NOT NULL` with NO FK (forward-defensible per CONTEXT) | `0001_initial.py:102` (`sa.BigInteger, nullable=False` — no `sa.ForeignKey`) | PASS |
| Phase-0 assertion guards against premature FK addition | `tests/test_migrations.py:128-142` (`test_bags_coffee_id_has_no_foreign_key`) | PASS |
| Model uses `Mapped[int]` not legacy Column syntax | `app/models/bag.py:33` (`coffee_id: Mapped[int] = mapped_column(...)`) | PASS |
| `ix_bags_coffee_id` btree index for reverse-lookup | `0001_initial.py:121` | PASS |

### AI cost-observability columns (AI-02 / COST-1)

| Column | In Migration | In Model | Status |
|---|---|---|---|
| `tokens_input` | `0001_initial.py:172` | `ai_recommendation.py:62` | PASS |
| `tokens_output` | `0001_initial.py:173` | `ai_recommendation.py:63` | PASS |
| `tokens_input_search` | `0001_initial.py:174` | `ai_recommendation.py:66-68` | PASS |
| `web_search_count` | `0001_initial.py:175` | `ai_recommendation.py:69` | PASS |
| `provider_used` | `0001_initial.py:167` | `ai_recommendation.py:56` | PASS |
| `model_used` | `0001_initial.py:168` | `ai_recommendation.py:57` | PASS |
| `tool_version` | `0001_initial.py:170` | `ai_recommendation.py:59` | PASS |
| `url_verified` | `0001_initial.py:177` | `ai_recommendation.py:72` | PASS |
| `duration_ms` | `0001_initial.py:178` | `ai_recommendation.py:73` | PASS |
| `generated_by` | `0001_initial.py:186` | `ai_recommendation.py:78` | PASS |
| `error_status` | `0001_initial.py:187` | `ai_recommendation.py:80` | PASS |
| `input_signature` (indexed) | `0001_initial.py:164,189` | `ai_recommendation.py:53` | PASS |

All 11 cost-observability columns plus `input_signature` (the indexed signature column called out in ROADMAP SC #2) are present from day one. Retrofit risk eliminated.

### SQLAlchemy 2.0 `Mapped[...]` typed columns

All 5 models verified to use `Mapped[...] = mapped_column(...)` (SQLAlchemy 2.0 style, not legacy `Column`):
- `app/models/user.py` (lines 38-52)
- `app/models/bag.py` (lines 29-44)
- `app/models/wishlist_entry.py` (lines 25-41)
- `app/models/ai_recommendation.py` (lines 42-80)
- `app/models/app_setting.py` (lines 31-44)

### Dockerfile multi-stage with standalone Tailwind CLI

- Stage 1 (lines 19-52): `debian:bookworm-slim` builder downloads Tailwind v4.3.0 standalone CLI binary from GitHub releases (no Node, no npm)
- Stage 2 (lines 55-109): `python:3.12-slim` runtime — `COPY --from=tailwind-builder` brings only the compiled CSS into the runtime image. Pip layer cached separately. Non-root `app` user UID 1000. HEALTHCHECK against `/healthz`.

### `app_settings` seed row count

19 rows verified by counting dict entries in `0001_initial.py:230-358`. The `tests/test_migrations.py::test_app_settings_seeded_with_19_rows` asserts `>= 19` (forward-compatible); `test_app_settings_critical_keys_present` enumerates all 19 keys by name.

---

## Static Gates Passed (13)

1. `tests/test_no_direct_env.py` — FOUND-10 grep gate (green, 1 passed)
2. `tests/test_env_example.py` — FOUND-09 parity gate (green, 1 passed)
3. `tests/test_logging.py` — 5 structlog tests including FOUND-11 JSON shape (green, 5 passed)
4. `tests/test_healthz.py` — skips cleanly when DB/CSS missing (green via skip, expected pre-build)
5. `tests/test_migrations.py` — 9 schema/seed introspection tests; skips cleanly when DB unreachable (deferred to live env)
6. `os.environ` grep across `app/`: 0 actual reads outside `app/config.py` (matches in docstrings only)
7. Single-worker rule grep across the 3 files: 7 hits ≥3 required
8. `docker-compose.yml` YAML shape: 2 services, 3 named volumes, healthcheck, `127.0.0.1:8080:8000` bind
9. Multi-stage Dockerfile parses: 2 `FROM` statements, no `RUN npm`, no `RUN node`, content-hashed output
10. All 5 SQLAlchemy models use `Mapped[...]` typed columns
11. All 11 AI cost-observability columns present in both migration and model
12. `app/services/scheduler.py` is a comment-only placeholder (no scheduler wiring — Phase 8's job)
13. Wave 0 + Wave 2 unit suite: 7/7 passed in 0.24s

---

## Runtime Gates Deferred (5)

These cannot be verified without a Docker daemon. They are explicitly the responsibility of `make smoke` per Plan 05's plan, summary, and verification block.

| Gate | How to run | Owner |
|---|---|---|
| Cold-start: `docker compose down -v && up -d --build && curl /healthz` returns `{"status":"ok"}` | `make smoke` on a host with Docker | Plan 05 closure |
| `pg_dump --version` inside web container reports 16.x | `docker compose exec coffee-snobbery pg_dump --version` | smoke env |
| Hashed Tailwind CSS exists in built image (`tailwind.<sha8>.css`) | `docker compose exec coffee-snobbery ls app/static/css/` | smoke env |
| Three Postgres extensions queryable in live DB | `docker compose exec coffee-snobbery-db psql ... -c "SELECT extname FROM pg_extension WHERE extname IN ('citext','pg_trgm','unaccent')"` | smoke env (covered by `tests/test_migrations.py` once DB up) |
| 19 `app_settings` seed rows physically present in DB | `tests/test_migrations.py::test_app_settings_seeded_with_19_rows` runs against live DB | smoke env |

---

## Anti-Patterns Scan

| File | Pattern searched | Result |
|---|---|---|
| All Phase 0 source files | `TBD`, `FIXME`, `XXX` (blocker markers) | None found |
| All Phase 0 source files | `TODO`, `HACK`, `PLACEHOLDER` (warning markers) | None of substance. The placeholder-related strings present are: `app/services/scheduler.py` documents itself as a Phase 8 placeholder (intentional — single-worker callsite #2 of 3); `app/templates/pages/index.html` is the CONTEXT D-12 placeholder home page (intentional). Neither is a debt marker. |
| `app/main.py` | Stub returns (`return null`, `return {}`) | Real returns: `{"status":"ok"}` or 503 with logged error class. Not a stub. |
| `app/templates/pages/index.html` | "Coming soon", "placeholder" | Contains "setup pending" — this is the CONTEXT D-12 intentional Phase 0 placeholder per the goal (`/` is replaced by Phase 2's `/setup` flow). Not a stub leak. |
| `app/services/scheduler.py` | Empty implementation | Is a documented Phase 8 placeholder + the single-worker rule callsite #2. Not a Phase 0 stub — it's intentional documented scaffolding. |

No blockers. No unresolved debt markers.

---

## Deviations Noted (recorded in summaries, accepted as deferred-by-design)

1. **`app/templates/pages/index.html` is the Phase 0 placeholder** — CONTEXT D-12 specifies this. `/` gets replaced in Phase 2 (`/setup` flow) and Phase 6 (real home page). Accepted.
2. **`bags.coffee_id` has no FK constraint in Phase 0** — CAT-04 + CONTEXT decision to defer the FK to Phase 4 when `coffees` exists. `tests/test_migrations.py::test_bags_coffee_id_has_no_foreign_key` actively guards against accidental addition. Accepted.
3. **`app/services/scheduler.py` is a comment-only placeholder** — Phase 8 owns the actual scheduler wiring. Phase 0 ships only the single-worker callsite #2 + the docstring claiming Phase 8 ownership. Accepted.
4. **Live-docker probes deferred to `make smoke`** — the worktree where execution happened had no Docker daemon. Plans 04 and 05 both explicitly document this; `make smoke` is the canonical environment for live verification. Accepted.
5. **`alembic.ini` has no `[loggers]` / `[handlers]` / `[formatters]` sections** — intentional; structlog (`app/logging.py`) owns the project's logging story. `app/migrations/env.py:32-38` handles the missing-section case defensively. Accepted.

---

## Anti-Pattern: Plan 00-03 `Self-Check: PARTIAL` claim — investigated

The 00-03-SUMMARY.md ends with `Self-Check: PARTIAL` claiming the Bash sandbox prevented commits of Task 2 and Task 3. **Verified resolved.** `git log` shows commits `5c94352` (Task 2 — Alembic + migration) and `8b52b80` (Task 3 — tests) both present after the sandbox-blocked summary was written; the next-agent merge picked them up. All three planned commits land in `git log`. Not a real gap.

---

## Overall Phase Verdict: READY

All 5 ROADMAP Phase 0 Success Criteria are satisfied at the code-substrate level. All 14 mapped requirements are addressed in committed code. All 3 structural invariants (single-worker rule in 3 files, `os.environ` only in `app/config.py`, `Mapped[...]` typed models) verified by both static inspection and runnable grep / unit tests.

The five live-docker gates (cold-start, `pg_dump` version, hashed CSS in image, extensions in DB, 19 seed rows in DB) cannot be verified on this Windows worktree (no Docker daemon). They are run by `make smoke` on a Docker-equipped host. This is consistent with the Plan 04 and Plan 05 summaries — both explicitly defer these to `make smoke` and call out the deferred gates by name.

**Phase 0 is shippable as-is.** Proceed to:

1. **(Strongly recommended)** Run `make smoke` on the production VPS (or any Docker-equipped host) once before declaring Phase 1 plan-phase open. This is the canonical phase-gate per Plan 05's plan body — five minutes of physical work, eliminates the residual uncertainty about the live stack. The Makefile target is wired and idempotent (`docker compose down -v` before bringing up clean).
2. **Then** open Phase 1 plan-phase. Phase 1's 10 plans are already drafted (per ROADMAP). The Phase 1 CONTEXT references Phase 0 plumbing (structlog contextvars seat, single-worker rule, `--proxy-headers` flag, `/healthz` route, pydantic-settings singleton) — all present and verified above.

## Recommended Next Step

**Run `make smoke` on a Docker host before opening Phase 1.** Five minutes; canonical phase gate; zero outstanding code gaps.

If `make smoke` is not immediately runnable (no Docker host available), Phase 1 can still open — the static gates above prove the substrate is wired correctly. The smoke run can be deferred to first VPS deployment without blocking Phase 1 planning. Mark this decision in STATE.md.

---

_Verified: 2026-05-17_
_Verifier: Claude (gsd-verifier, goal-backward methodology)_
