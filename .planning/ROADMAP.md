# Snobbery — Roadmap

**Project:** Snobbery (self-hosted household coffee log)
**Phases:** 13
**Generated:** 2026-05-16
**Mode:** Horizontal Layers

## Overview

Snobbery ships as 13 sequenced horizontal layers, each one a load-bearing slice of the stack the next layer relies on. The build order is rigid for Phases 0–8 because middleware gates routers, auth gates features, encryption gates AI keys, catalog gates sessions, sessions gate analytics, and analytics gates AI. Phases 9–12 (admin, search, PWA, polish) attach to the trunk with fewer dependencies. Two foundational schema bets — the `bags` instance table (CAT-04) and the AI cost-observability columns on `ai_recommendations` (AI-02) — land in the very first migration set even though they're not exercised until much later, because retrofitting them after 500+ rows of brew sessions or after the first surprise AI bill is the painful path. Single uvicorn worker is non-negotiable and documented at the bottom of Phase 0 (FOUND-04), invoked by Phase 7's in-memory lock, and depended on by Phase 8's APScheduler — three references to one decision.

## Phase Index

| # | Phase | Requirements | Dependencies |
|---|-------|--------------|--------------|
| 0 | Foundation | 14 | — |
| 1 | Middleware | 8 | 0 |
| 2 | Auth | 7 | 1 |
| 3 | Encryption + Settings | 2 | 2 |
| 4 | Shared Catalog | 9 | 2 |
| 5 | Brew Sessions | 13 | 4 |
| 6 | Analytics (Home Page) | 8 | 5 |
| 7 | AI Services | 18 | 3, 6 |
| 8 | Scheduler + Backups | 4 | 7 |
| 9 | Admin | 6 | 3, 8 |
| 10 | Global Search | 4 | 4, 5 |
| 11 | PWA + Mobile Polish | 17 | 6, 9 |
| 12 | Hardening + Tests | 6 | 11 |

**Total mapped requirements:** 116/116

## Phases

- [ ] **Phase 0: Foundation** — Two-container Docker stack, Postgres + extensions, Alembic + first migration set including `bags` and `ai_recommendations` schema, Tailwind CLI in Dockerfile, config + logging plumbing
- [ ] **Phase 1: Middleware** — Cross-cutting layers (proxy-headers trust list, CSP nonce, security headers, structured logging, `sessions` table + custom SessionMiddleware, CSRF double-submit-cookie, slowapi limiter, Jinja autoescape)
- [ ] **Phase 2: Auth** — Setup race-protected first-admin creation, argon2id login, session regeneration on privilege change, admin gate
- [ ] **Phase 3: Encryption + Settings** — `MultiFernet` encryption service, `app_settings` table + typed reader, `api_credentials` table — infrastructure that AI and Admin depend on
- [ ] **Phase 4: Shared Catalog** — Coffees / equipment / recipes / roasters / flavor notes CRUD with autocomplete-on-create, recipe step builder, bag photo upload with magic-byte + Pillow re-encode pipeline
- [ ] **Phase 5: Brew Sessions** — `brew_sessions` table + prefill form + tap-on-stars rating + tag input + LocalStorage + server-side draft autosave + CSV import/export; 16px form-input baseline
- [ ] **Phase 6: Analytics (Home Page)** — Pure-SQL preference derivations (top coffees, profile, sweet spots, freshness buckets), HTMX-staggered lazy load, stale-data signature plumbing
- [ ] **Phase 7: AI Services** — Provider abstraction (Anthropic default / OpenAI fallback), three-tier web-search fallback, ranged-GET URL verification, advisory-lock-backed regeneration, cold-start gate, all per-flow Pydantic schemas + citation stripping
- [ ] **Phase 8: Scheduler + Backups** — APScheduler `AsyncIOScheduler` + `SQLAlchemyJobStore` in lifespan, nightly AI refresh @ 00:00, nightly `pg_dump` + photos tarball @ 02:00 with 14-day retention
- [ ] **Phase 9: Admin** — User CRUD, API credential vault with last-4 display, app_settings value_type-driven editor, backups list + manual run, system info + API health panels
- [ ] **Phase 10: Global Search** — FTS-vs-trigram decision at plan time, Postgres-based cross-entity search with per-user session-note scoping, debounced HTMX live results
- [ ] **Phase 11: PWA + Mobile Polish** — Manifest from `/manifest.json`, `/sw.js` at root with `Service-Worker-Allowed: /`, dual theme-color metas, maskable icons, iOS install banner, bottom/top nav, card-list collapse, Guided Brew Mode with wake-lock fallback, aesthetic + dark mode + branding
- [ ] **Phase 12: Hardening + Tests** — Pytest smoke (happy path), `respx`-backed AI service tests, encryption round-trip + rotation test, analytics-query tests, CSRF tests, Playwright responsive smoke at 375×667 and 390×844, CSP audit, `|safe` grep test

## Phase Details

### Phase 0: Foundation
**Goal:** A clean `git clone` + `docker compose up -d` brings up a two-container stack with Postgres extensions installed, the first migration applied (including the `bags` and `ai_recommendations` tables so later phases never need a painful retrofit), Tailwind compiled into the image, and uvicorn running as a single worker behind the proxy-headers trust list.
**Depends on:** Nothing (first phase)
**Requirements:** FOUND-01, FOUND-02, FOUND-03, FOUND-04, FOUND-05, FOUND-06, FOUND-07, FOUND-08, FOUND-09, FOUND-10, FOUND-11, FOUND-12, CAT-04, AI-02
**Success Criteria** (what must be TRUE):
  1. From a clean checkout, `docker compose up -d` brings up `coffee-snobbery` (web) and `coffee-snobbery-db` (db) on `coffee-snobbery-net` with all three named volumes, the app reachable on `127.0.0.1:8080`, and `pg_dump --version` inside the web container matching the Postgres 16 server version.
  2. Container start runs `alembic upgrade head` automatically; the first migration installs `citext`, `pg_trgm`, and `unaccent`, creates the `users`, `bags`, and `ai_recommendations` tables (including the cost-observability columns: `web_search_count`, `tokens_input_search`, `provider_used`, `model_used`, `tool_version`, `input_signature`, `url_verified`, `duration_ms`, `generated_by`), and seeds the documented `app_settings` rows.
  3. `app/config.py` (pydantic-settings) is the only module that reads `os.environ`; `.env.example` documents every var with a one-liner generation hint (`APP_SECRET_KEY`, `APP_ENCRYPTION_KEY`, `TRUSTED_PROXY_IPS`, `APP_TIMEZONE`, `BACKUP_RETENTION_DAYS`, `LOG_LEVEL`, `DATABASE_URL`, Postgres triple).
  4. uvicorn is launched with `--workers 1 --proxy-headers --forwarded-allow-ips=$TRUSTED_PROXY_IPS`; the single-worker requirement is called out in the README, `entrypoint.sh`, and as a comment in the future scheduler module — anyone trying to add `--workers 4` trips over the note three times.
  5. Tailwind CSS is built by the standalone CLI binary baked into the Dockerfile (no Node, no npm), output served as `/static/css/tailwind.<hash>.css`; structlog emits JSON with a `request_id` correlation field.
**Plans:** 5 plans
Plans:
- [x] 00-01-PLAN.md — Project skeleton, dependency manifest, pydantic-settings config, Wave-0 test infrastructure (FOUND-09, FOUND-10)
- [x] 00-02-PLAN.md — structlog ProcessorFormatter logging with JSON/console renderer + contextvars seat for Phase 1 request_id (FOUND-11)
- [x] 00-03-PLAN.md — SQLAlchemy engine + 5 models + Alembic + first migration (extensions + 5 tables + 18 app_settings seed rows) (FOUND-05, FOUND-06, CAT-04, AI-02)
- [x] 00-04-PLAN.md — Multi-stage Dockerfile + entrypoint.sh + Tailwind builder + app/main.py (lifespan + /healthz + /) (FOUND-04, FOUND-07, FOUND-08, FOUND-12)
- [x] 00-05-PLAN.md — docker-compose.yml + Makefile + publishable README.md (single-worker rule location #3) (FOUND-01, FOUND-02, FOUND-03)
**Notes:** Carries SH-5 (`postgresql-client-16` in web image — exact version match), SH-2 (set `pool_size=10, max_overflow=5, pool_timeout=5, pool_pre_ping=True` explicitly), SH-6 (proxy-headers flag — confirm via `/debug/proxy` smoke later in Phase 9), AI-6 / SH-1 (single-worker rule), COST-1 (cost-observability columns must be present from migration 1). Cross-cuts into Phase 1 (`--proxy-headers` only works if the trust list is right) and Phase 8 (scheduler depends on single worker). The bag-as-instance call (CAT-04) deviates from a naive single-row coffee model — table ships now, CRUD UI is built in Phase 4 as a derived task during catalog work.

### Phase 1: Middleware
**Goal:** Every cross-cutting concern that every later router will rely on is in place — proxy headers honored end-to-end, CSP nonce minted per request, structured logging with request IDs, table-backed sessions resolving `request.state.user`, double-submit-cookie CSRF working with HTMX swaps, slowapi limiter wired but used only by `/login` and `/setup`, and Jinja autoescape on with `|safe` already a banned pattern in `templates/pages/`.
**Depends on:** Phase 0
**Requirements:** AUTH-05, AUTH-08, AUTH-10, SEC-01, SEC-02, SEC-03, SEC-04, SEC-05
**Success Criteria** (what must be TRUE):
  1. A `curl -H "X-Forwarded-Proto: https"` to a `/debug/proxy` endpoint shows `scheme=https` and the client IP from `X-Forwarded-For`; a request without the header (or from an untrusted source IP) does not. Secure cookies set during Phase 2 will therefore not be dropped by the browser.
  2. Every response carries `Content-Security-Policy` (nonce-based, `script-src 'self' 'nonce-…'`, no `unsafe-inline` for styles), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, and `Permissions-Policy: camera=(self), microphone=(), geolocation=()`. The CSP-build Alpine bundle is in place so no future template needs `'unsafe-eval'`.
  3. A POST to any state-changing endpoint without a valid double-submit-cookie CSRF token returns 403; an HTMX POST that follows a fragment swap still succeeds on the second click (the cookie is the token — no rotation required).
  4. Hitting `/login` (a stub returning 200) six times within 15 minutes from the same IP returns 429 on the sixth; structured logs show one JSON line per auth event with `event=auth.login_attempt`, `user_id`, `ip`, `request_id`, and no request body.
  5. README documents the NGINX `Strict-Transport-Security` line for HSTS at the proxy layer and includes a server-block example with `proxy_set_header X-Forwarded-Proto $scheme` and `proxy_buffering off` ready for future SSE.
**Plans:** 10 plans
Plans:
- [x] 01-01-PLAN.md — Wave 0 test scaffolding + CI grep tests + pyproject pytest config
- [x] 01-02-PLAN.md — RequestContextMiddleware + structlog ProcessorFormatter + event taxonomy module
- [x] 01-03-PLAN.md — SecurityHeadersMiddleware (CSP nonce + standard headers) + /csp-report endpoint
- [x] 01-04-PLAN.md — sessions table migration + table-backed SessionMiddleware + regenerate helper
- [x] 01-05-PLAN.md — starlette-csrf wiring + htmx-listeners.js (allowEval=false + X-CSRF-Token)
- [x] 01-06-PLAN.md — FragmentCacheHeadersMiddleware (HX-Request fail-safe cache policy)
- [x] 01-07-PLAN.md — slowapi limiter finalization + stub /login + /setup with rate limit
- [x] 01-08-PLAN.md — Jinja autoescape + base.html + /debug/proxy + README NGINX block
- [x] 01-09-PLAN.md — app/main.py: lifespan + middleware stack assembly + router includes
- [x] 01-10-PLAN.md — ADRs (CSP, pure ASGI, D-14 amendment) + Alpine components scaffold

**Notes:** Carries the top-5 pitfalls SH-6 (proxy headers → Secure cookie), SEC-1 (CSP / Alpine / Tailwind trade-off — documented in `docs/decisions/`), HX-1 (double-submit-cookie chosen over rotated tokens). HX-2 fragment-cache concerns codified here: add `Cache-Control: no-store` + `Vary: HX-Request` helper used by every fragment route from Phase 4 onward. **Plan-phase research flag:** prototype intended Alpine directives against the CSP build to confirm `'unsafe-eval'` can be avoided entirely; document any residual requirement under `docs/decisions/`.

### Phase 2: Auth
**Goal:** A fresh deployment lands on `/setup`, creates the first admin under a `SELECT FOR UPDATE` lock so two concurrent setup hits can't both succeed, and afterwards every visit to `/setup` redirects to `/login`; users log in with argon2id-verified passwords, sessions regenerate their ID on every login and admin-toggle, and `/admin` returns 403 to anyone without `is_admin`.
**Depends on:** Phase 1
**Requirements:** AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-06, AUTH-07, AUTH-09
**Success Criteria** (what must be TRUE):
  1. With zero users, `/setup` accepts a username + password and creates an admin user; concurrent `/setup` POSTs to a brand-new instance produce exactly one user row because the route holds a `SELECT … FOR UPDATE` on an `app_settings.setup_completed` row; once true, the route responds `302 → /login` (per CONTEXT D-01: friendlier than 404, zero info-leak since the route is read-only post-setup).
  2. `/login` accepts the new credentials, sets a `session_id` cookie with `HttpOnly`, `Secure`, `SameSite=Lax`, signed by `APP_SECRET_KEY`, and 30-day max-age; refresh on activity bumps `sessions.last_seen`.
  3. Successful login deletes the previous `sessions` row and mints a fresh `session_id` — a pre-set cookie cannot be reused to inherit the new authenticated session (session-fixation defense).
  4. Hitting `/admin` as a non-admin returns 403; as an admin returns 200 (stub at this phase). Logout deletes the session row and unsets the cookie.
  5. Smoke pass: cold container → `/setup` → auto-login → see a stub `/` page that prints "Signed in as <username>" in the footer (per CONTEXT D-03: setup's happy path auto-logs in via session-ID regen + 303 → /, skipping a separate /login step).
**Plans:** 11 plans
Plans:
- [x] 02-01-PLAN.md — Wave 0 conftest fixtures (async_client, fresh_db, seeded_admin/regular_user) + tests/dependencies package marker
- [x] 02-02-PLAN.md — app/services/auth.py: PasswordHasher singleton + hash_password + verify_password + dummy_verify (AUTH-04 + AUTH-03 user-not-found timing defense)
- [x] 02-03-PLAN.md — app/dependencies package: get_async_session + require_user + require_admin (AUTH-09 module location)
- [x] 02-04-PLAN.md — app/csrf.py: CSRFFormFieldShim ASGI middleware (D-15) + 5 test cases
- [x] 02-05-PLAN.md — app/services/setup.py: create_first_admin FOR UPDATE transaction (AUTH-02)
- [x] 02-06-PLAN.md — app/middleware/session.py: D-09 User-row load + D-10 fail-closed
- [x] 02-07-PLAN.md — app/routers/auth.py real /setup + /login + /logout + templates + schemas + replaces test_auth_stub.py (AUTH-01, AUTH-03, AUTH-06, AUTH-07)
- [x] 02-08-PLAN.md — app/routers/admin.py + /admin template (D-13, AUTH-09)
- [x] 02-09-PLAN.md — /debug/proxy admin-gate wrap + test_debug_proxy extension (D-14, AUTH-09)
- [x] 02-10-PLAN.md — app/main.py wire CSRFFormFieldShim + admin router; pages/index.html footer; tests/test_phase02_smoke.py; D-15 logging assertions on real /login handler
- [x] 02-11-PLAN.md — ROADMAP doc amendments per D-01 / D-03 + populate Plans list (this plan)
**Notes:** Carries SEC-3 (session-ID regeneration) and SEC-5 (setup race via `FOR UPDATE` on `app_settings`). Argon2id parameters per spec: `memory_cost=64MB, time_cost=3, parallelism=4`. Argon2 verify runs even when the user is not found, to defend against user enumeration.

### Phase 3: Encryption + Settings
**Goal:** `services/encryption.py` exposes `MultiFernet` round-trip from day one (so a future key rotation doesn't orphan stored API keys), `app_settings` is queryable via a typed reader with in-memory cache + write-through invalidation, and `api_credentials` rows persist encrypted at rest. Nothing user-facing yet — this is the substrate for Phase 7 (AI service reads keys + tool versions + region from here) and Phase 9 (admin edits the same rows).
**Depends on:** Phase 2
**Requirements:** SEC-08, SEC-09
**Success Criteria** (what must be TRUE):
  1. `services/encryption.py` constructs a `MultiFernet([Fernet(primary), Fernet(secondary)])` from `APP_ENCRYPTION_KEY` (comma-separated, first key is the encryption key, all keys are decryption candidates); a round-trip test encrypts under the primary, rotates the env var so the old primary is now secondary, and still decrypts correctly.
  2. A missing or malformed `APP_ENCRYPTION_KEY` causes startup to fail loudly with a clear error message — the app does not boot into a state where encrypted writes would silently fail.
  3. `app_settings` table is queryable via `services/settings.py` with `value_type`-aware coercion (`string`, `integer`, `boolean`, `json`); reads are cached in-memory and invalidated on write.
  4. `api_credentials` rows persist key material only as ciphertext; reading a row through the service returns a transient dataclass holding the decrypted key — no Pydantic model includes the decrypted field, so `model_dump()` cannot leak it.
**Plans:** 6 plans
Plans:
- [x] 03-01-PLAN.md — `api_credentials` table + ApiCredential model + migration with 2-row seed and `encryption_key_primary_fingerprint` app_settings row (SEC-08)
- [x] 03-02-PLAN.md — `app/services/encryption.py` MultiFernet primitives + `startup_check` + `primary_key_fingerprint`; 5 new event constants in `app/events.py` (SEC-08, SEC-09)
- [x] 03-03-PLAN.md — `app/services/settings.py` typed reader + module-level cache + write-through invalidation + audit emit (SEC-08)
- [x] 03-04-PLAN.md — `app/services/credentials.py` CRUD + ProviderCredential frozen+slots dataclass + `rewrap_if_needed` (SEC-08, SEC-09)
- [x] 03-05-PLAN.md — `app/main.py` lifespan wires the three Phase 3 hooks in D-16 order (SEC-08, SEC-09)
- [x] 03-06-PLAN.md — Test files for encryption / settings / credentials / migrations / lifespan; flip `nyquist_compliant: true` (SEC-08, SEC-09)
**Notes:** Carries SEC-2 (MultiFernet from day 1 — the cheapest moment to install rotation) and SEC-6 (no Pydantic model carries decrypted `api_key`; CI grep test for `model_dump\(\)` on `ApiCredential` lands in Phase 12). The `app_settings` seed rows (`recommendation_region`, `min_sessions_for_ai`, `min_flavor_notes_for_ai`, `ai_primary_max_searches`, `ai_broadened_max_searches`, `anthropic_web_search_tool_version`, `openai_web_search_tool_version`, `setup_completed`) ship in the Phase 0 migration; this phase wires the reader.

### Phase 4: Shared Catalog
**Goal:** Coffees, roasters, flavor notes, equipment, and recipes are fully CRUD'd via the shared catalog UI; autocomplete-on-create-on-save smooths roaster + flavor-note entry; recipes have a step builder with cumulative water + time offsets and a duplicate action; bag photos upload through a hardened pipeline (magic-byte → Pillow re-encode → EXIF strip → resize → 400px thumbnail). Pydantic v2 form validation with numeric ranges is now the universal pattern for any state-changing endpoint.
**Depends on:** Phase 2
**Requirements:** CAT-01, CAT-02, CAT-03, CAT-05, CAT-06, CAT-07, CAT-08, SEC-06, SEC-07
**Success Criteria** (what must be TRUE):
  1. A logged-in user can create a roaster, a flavor note, a coffee, an equipment item (brewer/grinder/kettle/scale/water_filter/other), and a recipe with a multi-step pour timeline — all five entities visible immediately to every household user (shared catalog). Autocomplete-on-create works for roasters and flavor notes from inside the coffee form.
  2. The coffees list renders as a table on desktop (≥768px) and collapses to a card list at <768px (smoke checked at 375px); filters by roaster, country, process, and archived state work; archive (not delete) is the default for any entity referenced by other rows.
  3. The recipe step builder lets a user add, remove, and reorder pours; cumulative water (grams) and time offset (seconds) are computed live; "Duplicate recipe" creates an editable copy; the pour-timeline preview renders as a vertical bar with proportional segments.
  4. Bag photo upload accepts JPEG/PNG/WebP up to 5MB, rejects anything that fails magic-byte check, re-encodes via Pillow (which strips trailing/polyglot bytes), strips EXIF, resizes to ≤1600px wide and generates a 400px thumbnail; photos are served via `routers/photos.py` (not a `StaticFiles` mount) with `Content-Type` set and `Cache-Control: private, max-age=31536000, immutable`.
  5. Every form (coffee, equipment, recipe, roaster, flavor note, bag) round-trips through a Pydantic v2 schema with explicit numeric ranges — temp 0–100°C, dose/water in sensible ranges, rating constraints not yet active here but the validator pattern is in place for Phase 5.
**Plans:** 11 plans
Plans:
- [ ] 04-01-PLAN.md — Phase 4 test scaffolding + app/services/photos.py (Pillow pipeline + sweep_orphans) + events.catalog.* taxonomy (SEC-07)
- [ ] 04-02-PLAN.md — Six Pydantic v2 form schemas + form_validation.errors_by_field helper + sync get_session dep (SEC-06)
- [ ] 04-03-PLAN.md — Five new Mapped[...] models + bag FK/photo_filename + single alembic migration with GIN index (CAT-01..03, 05, 06, 08)
- [ ] 04-04-PLAN.md — Roasters CRUD + autocomplete + HX-Trigger mini-modal substrate; establishes catalog CRUD template (CAT-01)
- [ ] 04-05-PLAN.md — Flavor notes CRUD + autocomplete; reuses shared autocomplete_list.html fragment (CAT-02)
- [ ] 04-06-PLAN.md — Equipment CRUD with type-grouped list (CAT-05)
- [ ] 04-07-PLAN.md — Coffees CRUD with 4-dim hx-push-url filter bar + desktop/card responsive layout + coffee detail page + bag-form-mount (CAT-03, CAT-07)
- [ ] 04-08-PLAN.md — Recipes CRUD + Alpine recipe-step-builder + pour-timeline preview + HX-Redirect duplicate (CAT-06)
- [ ] 04-09-PLAN.md — Bags nested CRUD under coffee detail + photo upload pipeline (magic-byte/Pillow/EXIF/atomic replace) + photo-upload.js Canvas downscale (CAT-08)
- [ ] 04-10-PLAN.md — app/routers/photos.py auth-gated serve route with D-06 header contract (SEC-07)
- [ ] 04-11-PLAN.md — Wire D-13..D-16: mini-modal + autocomplete Alpine components + parent-form pre-select on HX-Trigger (CAT-01, CAT-02)
**Notes:** Carries SEC-4 (polyglot upload — `img.save(new_path, format=img.format)` after decode strips trailing data; serve with `nosniff` + `Content-Disposition: inline`). CAT-04 (bags) table is already in place from Phase 0; the bag CRUD UI ("open new bag of this coffee" action from coffee detail) lands as a derived task in this phase even though the REQ-ID is owned by Phase 0. HX-3 (`hx-swap-oob` duplicate-ID footgun on the flavor-notes datalist) — prefer `hx-get` on focus over OOB swap.

### Phase 5: Brew Sessions
**Goal:** The daily-use surface ships — a single scrollable add-session form with aggressive prefill from last session + selected recipe, tap-on-stars rating (not native range — the 44×44px requirement makes native range unusable at 375px), tag input for observed flavor notes, live brew-ratio readout in the form, LocalStorage draft persistence namespaced by `user_id`, server-side draft autosave-on-blur as an iOS ITP backstop, sessions list with filters and CSV export, CSV import limited to "refuse rows where coffee or bag not in catalog", and the 16px form-input baseline that prevents iOS Safari focus-zoom on every input the user touches.
**Depends on:** Phase 4
**Requirements:** BREW-01, BREW-02, BREW-03, BREW-04, BREW-05, BREW-06, BREW-07, BREW-08, BREW-09, BREW-10, BREW-11, MOB-05, MOB-06
**Success Criteria** (what must be TRUE):
  1. A returning user with one prior session can log session N+1 in under 30 seconds: opening the add form prefills coffee, recipe, brewer, grinder, kettle, water type, dose, water, temp, and grind setting from the last session (with visible ghost-text / pill indicators), leaving only rating, observed flavor notes, and notes to fill in.
  2. The rating control is a 5-star tap component with 56×56px stars; each star supports quarter / half / three-quarter / full via tap-zone or repeated-tap; the value persists as a `Decimal` to the `brew_sessions.rating` column (`ge=0, le=5, multiple_of=0.25`). The form's `1:N.NN` ratio readout updates live as the user changes dose or water.
  3. LocalStorage drafts survive reload + tab navigation and are namespaced as `snobbery:draft:brew:<user_id>` so a shared phone never leaks one user's draft to another; on every field blur, the form POSTs to `/brew/draft` so an iOS Safari ITP eviction at day 7 doesn't lose the draft. Drafts clear on successful submit and on logout.
  4. The sessions list renders the current user's sessions only, filterable by coffee / brewer / rating range / date range; "Brew again" on any row opens a new session form prefilled with that session's coffee, bag (if open), recipe, brewer, grinder, kettle, water, dose, temp, grind — and explicitly blank rating, flavor notes, and notes. CSV export downloads the filtered view.
  5. CSV import accepts a Beanconqueror-style file, refuses rows where the named coffee or bag is not yet in the catalog (with a per-row error list), and inserts the rest in one transaction. Every form input on this surface computes to ≥16px font-size — Playwright assertion at 375px confirms no zoom-in on focus for any input.
**Plans:** TBD
**Notes:** Carries MX-1 (16px font rule — global CSS in `app/static/css/custom.css`), MX-5 (LocalStorage draft namespacing + clear-on-logout), MX-6 (tap-on-stars not native range), HX-3 (flavor-note tag input — `hx-get` on focus, no OOB swap). Guided Brew Mode (BREW-12, BREW-13) is deferred to Phase 11 alongside the wake-lock fallback and full-screen mobile chrome.

### Phase 6: Analytics (Home Page)
**Goal:** The home page renders for a user with ≥3 sessions: recent brews eager-loaded, every analytics card lazy-loaded via HTMX with staggered triggers (`load delay:100ms` per section, the expensive AI section using `hx-trigger="revealed"`), every query pure SQL with explicit indexes, and the stale-data signature plumbing in place so the AI card knows (later, in Phase 7) whether to show an "Outdated" badge.
**Depends on:** Phase 5
**Requirements:** HOME-01, HOME-02, HOME-03, HOME-04, HOME-05, HOME-07, HOME-08, HOME-09
**Success Criteria** (what must be TRUE):
  1. A user with ≥3 sessions sees: top 5 coffees by avg rating (min 2 sessions), preference-profile cards (avg rating by origin / process / roaster / roast level), top-10 flavor descriptors in 4.0+ sessions, roast-freshness buckets using `bags.roast_date` (never `coffees.roast_date`), top 3 sweet spots `(origin × process × brewer × recipe)` with min 3 sessions, recent 10 brews with edit links, and unrated coffees from the catalog.
  2. Each section lazy-loads via HTMX with `hx-trigger="load delay:Nms"` staggered 100ms apart; p95 of every analytics query is <50ms against a 1000-session seeded dataset; the home page's Time-To-Interactive at 375px on a throttled 3G profile is under 2 seconds.
  3. `services/analytics.py` exposes a `compute_input_signature(user_id) -> str` helper that returns a content-hash of *this user's own* sessions (not shared catalog counts) so adding a coffee to the household doesn't thrash everyone's signature.
  4. Cold-start path: a user with `<3 sessions OR <5 distinct observed flavor notes` sees a friendly empty state with a progress meter ("Log 2 more brews and add 3 more flavor notes to unlock recommendations") instead of a degraded analytics view.
**Plans:** TBD
**Notes:** Carries HX-5 (staggered lazy-load to avoid thundering-herd on the connection pool), SH-2 (connection-pool sizing — `pool_size=10, max_overflow=5`), COST-4 (signature must NOT include shared `equipment_count` / `recipe_count`), AI-7 (cold-start gate at `min_sessions=3 AND min_flavor_notes=5`). HOME-06 (AI prose under sweet spots) is owned by Phase 7 because it requires the AI service. Sweet-spots SQL is a UNION of GROUP BYs with HAVING (no Python loops).

### Phase 7: AI Services
**Goal:** Snobbery's differentiator goes live. `services/ai_service.py` exposes a provider-agnostic API; the live coffee recommendation runs a three-tier web-search fallback (primary → broadened → characteristics-only); structured outputs land via tool_use blocks and pass per-flow Pydantic validation after citation projection; URL verification uses a ranged GET with a realistic User-Agent and a body-contains-name check; an asyncio lock + Postgres advisory lock prevents the scheduler and a manual refresh from racing; the home page shows the new card with a stale-indicator badge when the stored signature drifts; equipment recommendation, alternative-brewer callout, paste-and-rank, and sweet-spots prose all land alongside.
**Depends on:** Phase 3 (encryption + settings), Phase 6 (analytics + signature)
**Requirements:** AI-01, AI-03, AI-04, AI-05, AI-06, AI-07, AI-08, AI-09, AI-10, AI-11, AI-12, AI-13, AI-14, AI-15, AI-16, AI-17, AI-18, HOME-06
**Success Criteria** (what must be TRUE):
  1. A user with ≥3 sessions and ≥5 distinct flavor notes hits "Refresh recommendations" and sees a coffee suggestion within ~30s with a verified buy URL (or a plain-text URL with a "couldn't verify" note); the AI prose under sweet spots renders alongside, generated in the same call. Every `ai_recommendations` row persists provider, model, tool version, input/output/search tokens, web search count, URL verification status, and `generated_by=manual_refresh` or `scheduler`.
  2. Provider fallback only triggers on non-retryable errors (`AuthenticationError`, `BadRequestError`, `PermissionDeniedError`, persistent `OverloadedError` after one retry). The SDK clients are constructed with `max_retries=1` to disable hidden retry loops. Web search `max_uses` is read from `app_settings` (default 5 primary / 3 broadened).
  3. A manual refresh while another run is in flight returns 429 with an HX-Retarget to a "please wait" message (5-minute per-user throttle); a manual refresh that completes a search returns a fresh recommendation card via the HTMX polling pattern (no SSE in v1; deferred to v1.1).
  4. Recipe suggestion picks from the user's existing `recipes` (never invents) ranked by historical avg rating for matching origin + process + roast level; if no recipe matches, the suggestion text says so and links to the recipe builder. Alternative-brewer callout fires only when historical data shows ≥0.5 rating delta on a different brewer for the recommended style.
  5. With no provider enabled in admin, the home page AI section renders a graceful "AI not configured" state. With at least one provider enabled but a Pydantic validation failure on the response, the user sees a "Try again" UI — not garbled JSON. Paste-and-rank is a separate on-demand route that never caches and never schedules.
**Plans:** TBD
**Notes:** Carries the top-1 pitfall AI-1 (token cost from web search), AI-2 (URL verification via ranged GET + body-contains-name + 5s timeout + no cross-host redirects), AI-3 (citation-block projector before Pydantic), AI-4 (fallback only on non-retryable), AI-5 (tool version in `app_settings`, not hardcoded), AI-6 (Postgres advisory lock backstop alongside in-memory lock), COST-2 (5-minute throttle on manual refresh), COST-4 (signature uses content hash of *user's own* sessions only), COST-5 (`max_uses=5/3`). **Plan-phase research flags:** confirm Anthropic structured-output via tool_use returns citations as a separate content block (verify projector strips them correctly); decide polling-vs-SSE for response delivery (SUMMARY recommends polling for v1).

### Phase 8: Scheduler + Backups
**Goal:** APScheduler `AsyncIOScheduler` starts in FastAPI's `lifespan` with `SQLAlchemyJobStore` (jobs survive container restart), `misfire_grace_time=3600`, `coalesce=True`, `max_instances=1`. The nightly AI refresh runs at 00:00 `APP_TIMEZONE`, computes each active user's current signature, and only regenerates when changed (logging users processed, regenerations, skips, total tokens split by web-search vs not). The nightly backup runs at 02:00, produces a `pg_dump` SQL + photos tarball into `/app/data/backups`, and prunes older than `BACKUP_RETENTION_DAYS` (default 14).
**Depends on:** Phase 7
**Requirements:** SCHED-01, SCHED-02, SCHED-03, SCHED-04
**Success Criteria** (what must be TRUE):
  1. The scheduler starts in `lifespan` with `SQLAlchemyJobStore(url=DATABASE_URL)` so missed jobs are detected on restart; `misfire_grace_time=3600` means a container restart that lands within 1h of the scheduled fire still runs the job; `coalesce=True` collapses multiple missed firings into one; `max_instances=1` prevents overlap.
  2. The nightly AI refresh at 00:00 iterates every active user with ≥3 brew sessions, computes the input signature, and triggers `ai_service.regenerate(user_id, generated_by="scheduler")` only when the signature differs from the stored one. The same in-memory lock + advisory lock from Phase 7 keeps it from racing a manual refresh.
  3. After the nightly run, structured logs show a single summary line per run with `users_processed`, `regenerations`, `skips`, `tokens_input_total`, `tokens_output_total`, `tokens_input_search_total`, `errors`. A separate `app_settings.last_ai_run_status` row (success/error + message) updates so the admin "API health" panel (Phase 9) can show it.
  4. The nightly backup at 02:00 runs `pg_dump` from inside the web container (matching `postgresql-client-16` version), writes `db_YYYY-MM-DD.sql` + `photos_YYYY-MM-DD.tar.gz` into the named `coffee_snobbery_backups` volume, and deletes files older than `BACKUP_RETENTION_DAYS`. After a simulated container restart at 23:55, the 00:00 AI job and 02:00 backup both still fire.
**Plans:** TBD
**Notes:** Carries the top-2 pitfall SH-1 (default `MemoryJobStore` would lose jobs; default `misfire_grace_time=1s` would silently skip restarts), SH-5 (version-matched `pg_dump` — already installed in Phase 0), COST-3 (`last_ai_run_status` for admin health panel). Re-references the Phase 0 single-worker rule — if a future operator sets `--workers 4`, every nightly job fires four times.

### Phase 9: Admin
**Goal:** A `/admin` area gated by `is_admin` lets John manage users, set/update encrypted API credentials per provider (Anthropic, OpenAI) with last-4 display, edit any row in `app_settings` via a `value_type`-driven input, view + download retained backups + trigger a manual backup, see system info (versions, storage, sessions, last backup), and read an API health panel that surfaces silent failures (deprecated model, revoked key, quota hit) from the cost-telemetry rows the scheduler writes.
**Depends on:** Phase 3 (encryption + settings), Phase 8 (backup job populates the list the UI reads)
**Requirements:** ADMIN-01, ADMIN-02, ADMIN-03, ADMIN-04, ADMIN-05, ADMIN-06
**Success Criteria** (what must be TRUE):
  1. An admin can list / create / edit (reset password, toggle `is_admin`, deactivate) / delete users; toggling `is_admin` also regenerates the target user's session ID. Non-admins hitting `/admin` get 403.
  2. The API-credentials page lets the admin set or update Anthropic and OpenAI keys (each encrypted at rest via the `services/encryption.py` MultiFernet), enable/disable each provider, and pick a model per provider. After save the form shows only the last 4 characters; the decrypted key never lives in a Pydantic model.
  3. The `app_settings` editor renders one input per row driven by `value_type`: `string` → text, `integer` → number, `boolean` → checkbox, `json` → textarea; the description is shown as helper text; saving persists immediately and invalidates the in-memory cache.
  4. The backups page lists every retained file (size + timestamp), offers a per-file download, and a "Run backup now" button that synchronously invokes the same `services/backup.py` entry point the scheduler uses.
  5. The system info panel shows app version, DB server version, photo storage usage, backup storage usage, active session count, and last backup status with timestamp. The API health panel shows last AI run timestamp + status per recommendation type, last success/error per provider, and the last 5 error messages per provider — surfaces silent failures from model deprecation, quota, or key revocation.
**Plans:** TBD
**Notes:** Carries COST-3 (model deprecation surfaced through the health panel by reading `app_settings.last_ai_run_status` + the latest `ai_recommendations.error_status` rows), AI-5 (the tool-version `app_settings` rows are editable here so a deprecated `web_search_20250305` can be swapped without redeploy). The `/debug/proxy` smoke endpoint promised in Phase 1 can be hardened or removed here once the deployment is verified end-to-end.

### Phase 10: Global Search
**Goal:** A persistent search input in the top nav (collapsed to an icon at <768px that expands to a full-screen sheet) drives a Postgres-based search across coffee names, roaster names, flavor note names, brew-session notes (only the searcher's own), recipe names/descriptions, and equipment names; HTMX live results are debounced to 250ms with a 2-character minimum and `hx-sync="this:replace"` to cancel in-flight requests; results are grouped by entity type; the searcher only sees their own session notes; the shared catalog is visible to all authenticated users.
**Depends on:** Phase 4 (catalog), Phase 5 (sessions)
**Requirements:** SEARCH-01, SEARCH-02, SEARCH-03, SEARCH-04
**Success Criteria** (what must be TRUE):
  1. Typing in the search input fires an HTMX request 250ms after the last keystroke (only when the input has ≥2 chars), returns within 100ms p95 against a seeded dataset, and renders results grouped under entity-type headers (Coffees, Roasters, Recipes, Equipment, Flavor Notes, Your Brew Notes); each result links to the entity's edit page.
  2. User A's search for a phrase that appears only in User B's brew-session notes does not surface User B's row; the shared catalog (coffees, roasters, recipes, equipment, flavor notes) appears in everyone's results regardless of who created the row.
  3. In-flight HTMX requests are cancelled by `hx-sync="this:replace"` when the user keeps typing; rapid typing of "ethiopia" results in at most 1–2 queries hitting Postgres rather than 8.
  4. The search input collapses to an icon at <768px and expands to a full-screen sheet on tap; at ≥768px it is inline in the top nav.
**Plans:** TBD
**Notes:** Carries HX-4 (debounce 250ms + min-length + `hx-sync` to avoid hammering the DB at every keystroke). **Plan-phase research flag:** prototype both Postgres FTS (tsvector + `to_tsquery`) and `pg_trgm` ILIKE/similarity against the seeded dataset and pick one; both are pure-Postgres with no architecture impact. Indexes are migration work — defer index creation to this phase rather than landing dead indexes in Phase 0.

### Phase 11: PWA + Mobile Polish
**Goal:** Snobbery becomes installable on iOS Safari and Android Chrome, behaves correctly at 375×667 and 390×844, ships the bottom-tab nav on mobile + top nav on desktop, collapses all tables to card lists at mobile widths, replaces native pickers with full-screen sheets where appropriate, lands the warm-minimalist palette with system-preference dark mode, and finally ships Guided Brew Mode — full-screen timer, audio + haptic step-transition cues, wake lock with iOS fallback (silent audio loop / NoSleep.js), re-acquisition on `visibilitychange`, and a visible "Screen will stay on" indicator.
**Depends on:** Phase 6 (home page settled), Phase 9 (admin nav target exists for MOB-02)
**Requirements:** BREW-12, BREW-13, MOB-01, MOB-02, MOB-03, MOB-04, MOB-07, MOB-08, MOB-09, MOB-10, MOB-11, MOB-12, MOB-13, UX-01, UX-02, UX-03, UX-04
**Success Criteria** (what must be TRUE):
  1. Installable on both iOS Safari and Android Chrome: `/manifest.json` returns 200 with `name="Snobbery — Coffee Log"`, `short_name="Snobbery"`, dual light/dark `theme_color`, `display: standalone`, `start_url: "/?source=pwa"` (which itself returns 200, never a redirect), and icons including a `purpose: "maskable"` variant at 192px and 512px so Android doesn't show a white square. iOS users see a one-time educational banner ("Tap [share] → Add to Home Screen") because iOS never prompts.
  2. `/sw.js` is served from the root with `Service-Worker-Allowed: /` so its scope is the entire app; the service worker stale-while-revalidates the app shell (base.html + tailwind.css + JS modules + manifest + icons), bypasses non-GET, network-firsts every other GET; the cache name embeds the build hash so each deploy purges old shells.
  3. Mobile chrome works: bottom tab nav (Home / Log / Config / Admin) at <768px with `env(safe-area-inset-bottom)` padding, top horizontal nav at ≥768px, Admin tab hidden for non-admins; every table on mobile collapses to a card list with no horizontal scroll; every tap target measures ≥44×44px; modals are full-screen sheets <768px and dialogs ≥768px; native `<select>` for short lists, HTMX searchable dropdown only for the long coffees list.
  4. Guided Brew Mode launches full-screen with a large countdown timer, the current step highlighted with cumulative water target and elapsed time, audio chime + vibration at each step transition (each configurable), pause/resume, cancel-without-logging, and "Done brewing" returns to the session form with timer data + recipe + selected coffee prefilled. Wake lock is requested on start, re-acquired on `visibilitychange` to `visible`, and a visible indicator shows when it's held; on iOS a silent-audio-loop / NoSleep.js fallback engages because the Wake Lock API has incomplete iOS support.
  5. Aesthetic: warm off-white/cream surfaces with espresso accents, system-preference dark mode (no manual toggle in v1), dual `<meta name="theme-color">` tags so the iOS status bar matches the active scheme on launch, "Snobbery — {Page Name}" tab title format, wordmark on desktop / icon-only on mobile, empty-state copy that leans into the snobbery tone without being gimmicky ("No brews logged yet. The snobbery awaits.").
**Plans:** TBD
**Notes:** Carries PWA-1 (iOS install banner), PWA-2 (`start_url` must return 200), PWA-3 (top-5 pitfall: serve `/sw.js` from root with `Service-Worker-Allowed: /`), PWA-4 (keep cached shell tiny for iOS ITP), PWA-5 (dual theme-color metas), PWA-6 (maskable icon variant), PWA-7 (NGINX `Cache-Control: no-cache` on `/sw.js`, cache version from build hash), MX-2 (`capture="environment"` opens an action sheet on iOS, not direct camera — adjust user-facing copy not behavior), MX-3 (sticky form actions stack above safe-area), MX-4 (wake-lock re-acquire). **Plan-phase research flag:** prototype the iOS Wake Lock fallback (silent audio loop vs NoSleep.js) on a real iPhone before declaring done.

### Phase 12: Hardening + Tests
**Goal:** Ship-readiness gate. Pytest smoke covers the acceptance-criteria happy path end-to-end. Unit tests pin the load-bearing services (`ai_service` signature + provider fallback under `respx`, `encryption` MultiFernet round-trip + rotation, `analytics` queries against a seeded DB, CSRF middleware positive + negative). Playwright responsive smoke runs at 375×667 and 390×844 and asserts the brew form is usable, the home page cards stack vertically, and no input triggers iOS-style focus zoom. CI grep test forbids `|safe` in `templates/pages/`. CSP audit confirms no inline scripts without nonce. README + `.env.example` + NGINX server-block example are publishable.
**Depends on:** Phase 11
**Requirements:** TEST-01, TEST-02, TEST-03, TEST-04, TEST-05, TEST-06
**Success Criteria** (what must be TRUE):
  1. `pytest` runs green inside the web container; the smoke test covers `setup → create coffee → create equipment → create recipe → log session → home page renders all sections including AI cold-start state if applicable`.
  2. Unit tests pass for `services/ai_service.py` (signature computation, provider fallback paths under `respx` fixtures, citation-block projection, manual-refresh throttle), `services/encryption.py` (encrypt → decrypt round-trip and key rotation under MultiFernet), `services/analytics.py` (top coffees, preference profile, sweet spots, roast freshness against a seeded test DB), and CSRF middleware (positive + negative).
  3. Playwright responsive smoke runs at 375×667 and 390×844 and asserts: bottom nav present and functional, brew session form usable without horizontal scroll, photo upload control present, home page analytics cards stack vertically and remain readable, no form input triggers iOS focus zoom (computed font-size ≥16px on every input/select/textarea).
  4. CI grep test fails the build if `|safe` appears anywhere under `templates/pages/`; a CSP audit (manual or scripted) confirms every `<script>` and `<style>` carries a nonce and no `'unsafe-eval'` or `'unsafe-inline'` is present outside the documented trade-off in `docs/decisions/`.
  5. README is publishable: documents the NGINX server block (including `proxy_set_header X-Forwarded-Proto $scheme`, the `Strict-Transport-Security` line, and `Cache-Control: no-cache` on `/sw.js`), the `.env.example` generation hints, the single-uvicorn-worker requirement (re-stated), the backup restore runbook (per CLAUDE.md), and the iOS Wake-Lock-fallback caveat.
**Plans:** TBD
**Notes:** Carries HX-6 (`|safe` grep test), SEC-1 follow-through (CSP audit), MX-1 (Playwright zoom assertion), SEC-6 (CI grep for `model_dump\(\)` on `ApiCredential`). This phase is the final ship gate; if any item slips, the project does not deploy to the VPS.

## Progress

**Execution Order:**
Phases execute in numeric order: 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 0. Foundation | 0/5   | Ready to execute | - |
| 1. Middleware | 0/10 | Ready to execute | - |
| 2. Auth | 0/TBD | Not started | - |
| 3. Encryption + Settings | 0/TBD | Not started | - |
| 4. Shared Catalog | 0/TBD | Not started | - |
| 5. Brew Sessions | 0/TBD | Not started | - |
| 6. Analytics (Home Page) | 0/TBD | Not started | - |
| 7. AI Services | 0/TBD | Not started | - |
| 8. Scheduler + Backups | 0/TBD | Not started | - |
| 9. Admin | 0/TBD | Not started | - |
| 10. Global Search | 0/TBD | Not started | - |
| 11. PWA + Mobile Polish | 0/TBD | Not started | - |
| 12. Hardening + Tests | 0/TBD | Not started | - |
