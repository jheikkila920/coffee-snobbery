# Architecture — Snobbery

**Project:** Snobbery (self-hosted household coffee log)
**Researched:** 2026-05-16
**Overall confidence:** HIGH for component boundaries and request paths (stack is well-trodden); HIGH for reverse-proxy + PWA gotchas (verified against MDN + uvicorn docs); MEDIUM for build-order specifics (dependency graph is judgment, not citation).

This document validates the spec's architecture, names the component boundaries the spec leaves implicit, walks three load-bearing request paths, gives an explicit build-order DAG, and surfaces the proxy/PWA/scheduler/concurrency gotchas that will bite if ignored.

---

## 1. Component Map

```
              ┌──────────────────────── coffee-snobbery container ───────────────────────┐
              │                                                                          │
   NGINX  ──► │  Uvicorn (1 worker)                                                      │
   (host)     │   └─► FastAPI app                                                        │
              │        ├─ MIDDLEWARES (outer → inner)                                    │
              │        │   1. ProxyHeadersMiddleware  (X-Forwarded-Proto/For trust)      │
              │        │   2. SecurityHeadersMiddleware (CSP, X-Frame-Options, etc.)     │
              │        │   3. RequestLoggingMiddleware (structlog, request-id, redact)   │
              │        │   4. SessionMiddleware (CUSTOM — table-backed, see §5)          │
              │        │   5. CSRFMiddleware (starlette-csrf, double-submit cookie)      │
              │        │   6. SlowAPI limiter middleware (/login, /setup only)           │
              │        │                                                                  │
              │        ├─ ROUTERS (one file per page in app/routers/)                    │
              │        │   ├─ auth.py     /login /logout /setup                          │
              │        │   ├─ home.py     /  (+ partials for lazy-loaded sections)       │
              │        │   ├─ log.py      /log + /log/sessions /log/coffees + partials   │
              │        │   ├─ config.py   /config (equipment + recipes)                  │
              │        │   ├─ admin.py    /admin (users, api-creds, settings, backups)   │
              │        │   ├─ search.py   /search (HTMX live results)                    │
              │        │   ├─ ai.py       /ai/refresh /ai/status /ai/stream (SSE)        │
              │        │   ├─ photos.py   /photos/{id} (served via app, not disk)        │
              │        │   └─ pwa.py      /manifest.json /sw.js (Service-Worker-Allowed) │
              │        │                                                                  │
              │        ├─ SERVICES (app/services/ — pure logic, no FastAPI imports)      │
              │        │   ├─ auth.py        password verify, session create/destroy     │
              │        │   ├─ csrf.py        token mint/verify wrappers (if hand-rolled) │
              │        │   ├─ encryption.py  Fernet wrappers for API keys                │
              │        │   ├─ settings.py    typed app_settings reader + in-memory cache │
              │        │   ├─ photos.py      Pillow magic-byte verify, resize, EXIF strip│
              │        │   ├─ search.py      Postgres FTS / pg_trgm query builder        │
              │        │   ├─ analytics.py   preference derivation SQL (no Python loops) │
              │        │   ├─ ai_service.py  provider abstraction, signature, lock, cache│
              │        │   ├─ backup.py      pg_dump subprocess + photos tarball         │
              │        │   └─ scheduler.py   APScheduler init, job registration          │
              │        │                                                                  │
              │        ├─ TEMPLATES (app/templates/ — Jinja2 + HTMX + Alpine)            │
              │        │   ├─ base.html (CSP nonce, csrf meta, hx-headers, dark mode)    │
              │        │   ├─ pages/  (full-page renders)                                │
              │        │   └─ partials/ (HTMX-target fragments — *.partial.html)         │
              │        │                                                                  │
              │        ├─ STATIC (app/static/)                                           │
              │        │   ├─ css/tailwind.css (built into image, see STACK §3.1)        │
              │        │   ├─ css/custom.css                                              │
              │        │   ├─ js/sw.js (service worker — served from /sw.js, scope=/)    │
              │        │   ├─ js/tag-input.js, rating.js, guided-brew.js                 │
              │        │   ├─ manifest.json (PWA manifest, served from /manifest.json)   │
              │        │   └─ icons/ (192/512/maskable + apple-touch-icon)               │
              │        │                                                                  │
              │        ├─ MODELS (app/models/) — SQLAlchemy 2.0 Mapped[...] per entity   │
              │        ├─ SCHEMAS (app/schemas/) — Pydantic v2 form + AI response models │
              │        └─ MIGRATIONS (app/migrations/ — Alembic, auto-run in entrypoint) │
              │                                                                          │
              │  APScheduler (AsyncIOScheduler, runs INSIDE the uvicorn process)         │
              │   ├─ nightly_ai_refresh  @ 00:00 APP_TIMEZONE                            │
              │   └─ nightly_backup      @ 02:00 APP_TIMEZONE                            │
              │                                                                          │
              └──────────────────────────────────────────────────────────────────────────┘
                                                │
                                                ▼
              ┌────────────────── coffee-snobbery-db container ──────────────────┐
              │  Postgres 16 (internal network only, named volume)               │
              │  Extensions enabled in first migration:                          │
              │    citext, pg_trgm, unaccent                                     │
              └──────────────────────────────────────────────────────────────────┘
```

### Component ownership

| Component | Owns | Does NOT own |
|---|---|---|
| **Routers** | HTTP boundary, form parsing, CSRF dep, session dep, template rendering, redirects | Business logic, SQL queries, AI calls (delegate to services) |
| **Services** | Business logic, SQL via SQLAlchemy session, external API calls, hashing/encryption | Anything FastAPI-specific (`Request`, `Depends`, `Form`) — keeps services unit-testable |
| **Middleware** | Cross-cutting concerns: proxy headers, security headers, structured logging, session lookup, CSRF token enforcement, rate limit | Page-specific logic, business rules |
| **Models** | SQLAlchemy table definitions, relationships, indexes | Query construction (lives in services) |
| **Schemas** | Pydantic v2 form validation, AI response schemas, CSV export shapes | DB persistence |
| **Templates** | HTML rendering, HTMX attributes, Alpine directives, Tailwind classes | Logic beyond simple conditionals; no fetches, no business decisions |
| **Static** | Tailwind-compiled CSS, hand-rolled JS modules, PWA manifest + service worker, icons | Any user-generated content (photos go to `/app/data/photos`) |
| **Scheduler** | Triggering nightly AI refresh + nightly backup; that's it | Long-running coordination across processes (single uvicorn worker rule, see §5.4) |
| **Migrations** | Schema evolution, extension creation, seed rows for `app_settings` | Application logic |

### Explicit boundary calls (where the spec is ambiguous)

| Question the spec doesn't pin down | Recommendation |
|---|---|
| Is CSRF token issuance a service or middleware? | **Middleware.** Token is minted on first GET, set as a cookie + injected into a `<meta name="csrf-token">` via context processor. Verification on POST/PUT/DELETE happens in middleware before the route handler. Single global enforcement point. |
| Where does session lookup happen? | **Custom SessionMiddleware** runs after CSRF middleware but before any router. It reads the signed cookie, queries the `sessions` table, attaches `request.state.user` (or `None`). Routers that require auth use a `current_user` dependency that 401/redirects when `request.state.user is None`. |
| Where does the AI provider abstraction live? | **`services/ai_service.py`**, single file. Exposes `async def get_coffee_recommendation(user_id, force=False)` and `async def get_equipment_recommendation(user_id, force=False)`. Internal classes `AnthropicProvider` and `OpenAIProvider` implement a small `Provider` protocol. Routers never import provider SDKs directly. |
| Photo storage on disk — what owns the path? | **`services/photos.py`** owns the path layout: `/app/data/photos/{uuid_prefix_2}/{uuid}.jpg` and `/{uuid_prefix_2}/{uuid}_thumb.jpg`. Two-char prefix sharding to keep directory size sane. Models store only the `photo_path` text column; the service resolves it. |
| Photos served by app vs static mount? | **By app, via `routers/photos.py`.** Sets cache headers (`Cache-Control: private, max-age=31536000, immutable` because the URL is content-addressed by UUID), enforces session auth (don't serve photos to unauthenticated requests), and lets the future addition of per-user photo ACLs land in one place. **Do not** add `app.mount("/photos", StaticFiles(...))` — it skips the security middleware chain. |
| Where does the in-memory AI lock live? | **In `ai_service.py` module-level dict** `Dict[Tuple[UUID, RecType], asyncio.Lock]`. Single uvicorn worker means single process means a module-level dict is sufficient. If you ever scale workers, replace with a Postgres advisory lock — but that's a v2 problem. |
| Where does the input-signature hash live? | **`ai_service.compute_input_signature(user_id) -> str`**, pure SQL aggregate (single round-trip). Stored on `ai_recommendations.input_signature`. The home-page template gets `is_stale = stored != current` from the route handler, not from the template. |
| HTMX partials — where do they live? | **`templates/partials/*.partial.html`**, named to match the HTMX target. e.g. `home/top_coffees.partial.html`, `home/coffee_recommendation.partial.html`. Pages reference them via `{% include %}` in the initial render and as `hx-get` targets after. |

---

## 2. Request Path Walkthroughs

Three load-bearing paths, with the exact middleware order and service hops. The middleware order is **outer to inner** — i.e., a request flows through them top-to-bottom on the way in and bottom-to-top on the way out.

### Path A — Login (POST /login)

```
NGINX (TLS, sets X-Forwarded-Proto: https, X-Forwarded-For: <client>)
  │
  ▼
Uvicorn  --proxy-headers --forwarded-allow-ips=127.0.0.1
  │  ProxyHeadersMiddleware (built into uvicorn)
  │  rewrites request.url.scheme = "https", request.client.host = <client>
  │
  ▼
[1] SecurityHeadersMiddleware
        Sets CSP nonce on request.state.csp_nonce. Headers added on response.
[2] RequestLoggingMiddleware
        Generates request-id, binds to structlog context. Logs path + method
        on entry. Does NOT log body (would leak password).
[3] SessionMiddleware (custom)
        Reads `session_id` cookie. SELECT FROM sessions WHERE id=? AND expires_at>now().
        For /login on a fresh client: no cookie → request.state.user = None.
        Touch session if found (updates last_seen).
[4] CSRFMiddleware (starlette-csrf)
        Reads csrftoken cookie + X-CSRF-Token header (or form _csrf field).
        For POST /login: required. 403 if mismatch.
        Note: csrf cookie was set on the GET /login render.
[5] SlowAPI limiter
        Decorated on the /login route: @limiter.limit("5/15minutes")
        Key function uses request.client.host (post-ProxyHeaders).
        429 if exceeded.
  │
  ▼
Route: auth.login_post
  → schemas.LoginForm.model_validate(form data)   (Pydantic)
  → services.auth.authenticate(username, password)
       └─ SELECT user WHERE username=? (citext eq)
       └─ argon2.verify(stored_hash, password)    (constant-time)
       └─ structlog.info("auth.login_attempt", username, success, ip)
  → services.auth.create_session(user_id)
       └─ INSERT INTO sessions (id, user_id, csrf_seed, expires_at, last_seen)
       └─ returns signed cookie value
  → response = RedirectResponse(url="/", status_code=303)
       Set-Cookie: session_id=<signed>; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=2592000
  │
  ▼ (on the way OUT, response flows back through middlewares)
CSRFMiddleware → rotates csrftoken cookie (good hygiene post-auth)
SessionMiddleware → no-op (handler already set the cookie)
RequestLoggingMiddleware → logs status, duration
SecurityHeadersMiddleware → attaches CSP/XFO/etc to the redirect response too
  │
  ▼
Uvicorn → NGINX (with response) → browser follows redirect to GET /
```

**Failure modes worth naming:**
- Wrong password → `auth.authenticate` returns None → 200 with login template re-rendered + error message. Argon2 verify runs even when user not found (timing-safe), to avoid user enumeration.
- 6th attempt within 15 min from same IP → SlowAPI 429 before the handler runs.
- Stolen CSRF token (cross-site form) → CSRFMiddleware 403.
- Browser sends `http://` because NGINX is misconfigured → cookie has `Secure` flag → browser refuses to send it back → app sees no session → endless redirect loop. (See §4 for the trust-list config that prevents this.)

### Path B — Log brew session (POST /log/sessions)

This is the highest-frequency write path. It must be fast and bulletproof.

```
NGINX → Uvicorn → middleware chain (same 5 layers as above)
  Note: SessionMiddleware now finds the session cookie and attaches
        request.state.user = User(id=..., is_admin=...).
  CSRFMiddleware enforces double-submit cookie on this POST.
  │
  ▼
Route: log.create_session_post
  → schemas.BrewSessionForm.model_validate(form data)
       - rating: Field(ge=0, le=5, multiple_of=0.25)
       - dose_grams_actual: Field(gt=0, le=100)
       - water_grams_actual: Field(gt=0, le=2000)
       - water_temp_c_actual: Field(ge=0, le=100)
       - coffee_id, brewer_id FK existence validated by services layer
       - flavor_notes: list[str] — service resolves to existing IDs or creates new rows
  → current_user dep (returns 303 to /login if not authed)
  → services.flavor_notes.upsert_many(observed_names) → list[UUID]
       SELECT existing WHERE LOWER(name) IN (...)
       INSERT any missing in a single statement (ON CONFLICT DO NOTHING + re-SELECT)
  → services.coffees.assert_exists(coffee_id), .equipment.assert_exists(...)
  → INSERT INTO brew_sessions (...)
  → COMMIT
  → Response:
       If hx-request: 200 with brew_session_row.partial.html (HTMX swaps it into the table)
       Else: 303 redirect to /log
  → No AI call. No analytics recompute. Stats are computed at read-time on /.
       The signature changes (max(updated_at) bumped). UI will show "Outdated — refresh?"
       on next /home render; the nightly scheduler picks up the regen at 00:00 anyway.
  │
  ▼ middlewares on the way out, no special behavior.
```

**Notable design choices:**
- **No write-time analytics recomputation.** The home page derives everything from SQL queries on read. At household scale this stays fast — no materialized views needed in v1. Index `brew_sessions(user_id, brewed_at)` and `brew_sessions(user_id, coffee_id)`.
- **No write-time AI trigger.** The signature mismatch is enough — the home page itself shows a "stale" badge, and the nightly job catches up. Avoids per-write LLM cost.
- **Flavor-note tag upsert in the same transaction** as the session insert. If the session insert fails, the upserted notes orphan — that's fine (they're a shared vocabulary; nobody minds an unused tag). If a constraint moves to require notes be used, add a cleanup job.
- **HTMX-aware response.** Check `request.headers.get("hx-request") == "true"`. If yes, return the partial that swaps into the sessions table; if no, full redirect. Same pattern for every write endpoint.

### Path C — Home page (GET /)

The page has 7+ sections. AI sections are slow (10–30s with web search). The spec says each section lazy-loads via HTMX after initial render.

```
NGINX → Uvicorn → middleware chain
  Session resolves to authenticated user.
  CSRF check is a no-op on GET (token is read on next POST).
  │
  ▼
Route: home.home_get
  → current_user dep
  → If user.brew_session_count < 3:
       Render templates/pages/home_cold_start.html — done.
  → Else:
       1. SELECT recent 10 sessions (cheap)
       2. SELECT current input_signature (single aggregate query)
       3. SELECT stored ai_recommendations FOR user
       4. is_stale_coffee = stored.coffee.input_signature != current
          is_stale_equipment = stored.equipment.input_signature != current
       5. Render templates/pages/home.html with:
            - eager: recent brews, sweet spots SQL chips, stale badges
            - lazy: <div hx-get="/home/sections/top_coffees" hx-trigger="load">…</div>
                    <div hx-get="/home/sections/preference_profile" hx-trigger="load">…</div>
                    <div hx-get="/home/sections/ai_coffee_rec" hx-trigger="load">…</div>
                    (etc.)
  → 200 OK
  │
  ▼ then 5+ HTMX GET requests fire from the browser, each its own request through
    the full middleware chain. The router for /home/sections/* checks current_user,
    runs the relevant analytics query OR pulls cached AI from ai_recommendations,
    returns a *.partial.html that swaps into the placeholder div.
```

**AI coffee rec section specifically:**
- `/home/sections/ai_coffee_rec` returns the cached `ai_recommendations.response_json` rendered as a card. Includes a "Refresh" button that POSTs to `/ai/refresh`.
- POST /ai/refresh returns 202 + an `hx-get`-driven polling endpoint at `/ai/status?type=coffee` that returns "still working" until the async LLM call (with web search) completes, then swaps the new card in.
- The actual LLM call runs inside the POST handler via `asyncio.create_task(...)` so the HTTP response returns immediately. The task acquires the per-user lock, calls the provider, runs the HEAD-check on the URL, writes to `ai_recommendations`, releases the lock.
- If SSE is chosen instead of polling: `/ai/stream` uses `sse-starlette` with `htmx-ext-sse@2.2.4` on the client side. **Recommendation: start with polling.** It's simpler, easier to debug, survives proxy buffering issues. SSE is a v1.1 polish.

**Render-order issue worth pre-empting:** The lazy-load divs must each render with a `hx-get` and a placeholder shimmer. If the shimmer renders inside a flex container, set explicit `min-height` so the page doesn't reflow as sections fill in — bad UX on mobile.

---

## 3. Build Order

Strict dependency DAG. Earlier phases unblock later ones. Phases that don't depend on each other can run in parallel if you have multiple engineers (you don't, but treat the lack of dependency as freedom to reorder).

```
PHASE 0 — Foundation (no app logic yet)
├── A. docker-compose.yml + Dockerfile + entrypoint.sh
├── B. app/main.py (lifespan only, no routes), config.py (pydantic-settings)
├── C. SQLAlchemy engine + session factory + base model
├── D. Alembic init + first migration: extensions (citext, pg_trgm, unaccent) + users table
└── E. Static Tailwind build pipeline in Dockerfile (per STACK §3.1)

PHASE 1 — Cross-cutting middleware (everything depends on these)
DEPENDS ON: PHASE 0
├── F. ProxyHeadersMiddleware verified (test with curl + X-Forwarded-Proto)
├── G. SecurityHeadersMiddleware + CSP nonce generator + base.html with nonce
├── H. Structured logging (structlog) + request-id middleware
├── I. Custom SessionMiddleware + sessions table migration
├── J. CSRFMiddleware (starlette-csrf) + base.html meta tag + hx-headers config
└── K. SlowAPI limiter wired (used by /login, /setup only)
        Why first: every later router relies on session, CSRF, CSP. If you bolt these
        on after building routers, every router needs revisiting.

PHASE 2 — Auth + user model (gates all other features)
DEPENDS ON: PHASE 1
├── L. User model + migration
├── M. services/auth.py (argon2 hash/verify, session create/destroy)
├── N. /setup route (first-run admin creation)
├── O. /login, /logout routes
├── P. current_user dependency + is_admin guard
└── Q. Smoke: setup → login → see "home" stub
        Why second: you cannot meaningfully test ANY other route without auth.

PHASE 3 — Encryption + settings infrastructure
DEPENDS ON: PHASE 2
├── R. services/encryption.py (Fernet wrappers) + unit tests
├── S. app_settings model + migration + seed rows
├── T. services/settings.py (typed reader + in-memory cache + invalidation on write)
└── U. api_credentials model + migration (uses encryption.py for at-rest storage)
        Why before AI: AI service reads keys from api_credentials, which requires
        encryption. AI service reads recommendation_region from app_settings.

PHASE 4 — Shared catalog (coffees, equipment, recipes, roasters, flavor_notes)
DEPENDS ON: PHASE 2
├── V. Five models + migrations + indexes
├── W. Routers for /log (coffees tab) + /config (equipment + recipes)
├── X. Autocomplete endpoints for roasters + flavor_notes
├── Y. services/photos.py + /photos/{id} route + Pillow magic-byte verify
└── Z. Step builder for recipes (Alpine.js + Jinja)
        Independent of AI; can land in parallel with PHASE 3 if engineers exist.

PHASE 5 — Brew sessions (the daily-use surface)
DEPENDS ON: PHASE 4
├── AA. brew_sessions model + migration + indexes ((user_id, brewed_at), (user_id, coffee_id))
├── BB. /log/sessions routes (list, add, edit, delete)
├── CC. Aggressive-prefill logic (last session + selected recipe)
├── DD. LocalStorage draft persistence (vanilla JS in app/static/js/)
├── EE. Quick re-log action (server returns prefilled form, no special endpoint)
├── FF. Tag input component (Alpine + autocomplete via HTMX hx-get)
├── GG. Rating control (Alpine over hidden numeric input)
└── HH. CSV export route
        Why before analytics: analytics queries against brew_sessions.

PHASE 6 — Analytics (home-page non-AI)
DEPENDS ON: PHASE 5
├── II. services/analytics.py — every query is pure SQL
├── JJ. Home page route + lazy-load partials (top coffees, preference profile, sweet spots,
│       recent brews, unrated coffees, roast freshness buckets)
├── KK. Index review: confirm sub-50ms p95 on each query at 1000-session dataset
└── LL. Stale-data badge plumbing (signature compute + comparison)
        Why before AI: AI section is a card on top of an otherwise-functional home page.
        Cold start can land here.

PHASE 7 — AI service (the differentiator)
DEPENDS ON: PHASE 3 (encryption + settings) + PHASE 6 (analytics provides AI input)
├── MM. services/ai_service.py provider abstraction (Anthropic + OpenAI)
├── NN. Pydantic AI response schemas (CoffeeRecommendation, EquipmentRecommendation)
├── OO. URL HEAD-check (httpx, 5s timeout)
├── PP. ai_recommendations model + migration (response_json, input_signature, etc.)
├── QQ. Compute-input-signature SQL aggregate
├── RR. /ai/refresh + polling endpoint /ai/status (or SSE — see §4)
├── SS. Per-(user_id, type) asyncio.Lock dict
├── TT. Alternative-brewer callout logic (data-derived, in ai_service)
├── UU. Sweet-spots AI prose (generated alongside coffee rec)
├── VV. Paste-and-rank route (no caching, no scheduling)
├── WW. Cold-start empty state (<3 sessions)
└── XX. Graceful "AI not configured" when no provider enabled

PHASE 8 — Scheduler + backups (operational)
DEPENDS ON: PHASE 7 (AI service needs to exist before its scheduled job)
├── YY. services/scheduler.py — APScheduler AsyncIOScheduler, started in lifespan
├── ZZ. nightly_ai_refresh job (00:00 APP_TIMEZONE, signature check, per-user loop)
├── AAA. services/backup.py — pg_dump subprocess + photos tarball + retention
├── BBB. nightly_backup job (02:00 APP_TIMEZONE)
└── CCC. Admin backup UI (list, download, "Run backup now")

PHASE 9 — Admin
DEPENDS ON: PHASE 2 (auth) + PHASE 3 (settings + encryption)
├── DDD. /admin/users (CRUD)
├── EEE. /admin/api-credentials (encrypted at rest, last-4 display)
├── FFF. /admin/settings (value_type-driven inputs)
├── GGG. /admin/system (versions, storage usage, session count)
└── HHH. /admin/backups (depends on PHASE 8)

PHASE 10 — Search
DEPENDS ON: PHASE 4 + PHASE 5
├── III. Decide: Postgres FTS (tsvector) vs pg_trgm — prototype both, pick one
├── JJJ. Index migration + search query builder in services/search.py
├── KKK. /search route + live results partial
└── LLL. Top-nav search input + mobile full-screen sheet

PHASE 11 — PWA + responsive polish
DEPENDS ON: PHASE 6 (home page renders) + most UI in place
├── MMM. /manifest.json route (or static file with correct content-type)
├── NNN. /sw.js route with Service-Worker-Allowed: / header
├── OOO. App-shell precache (base.html, tailwind.css, icons, app/static/js)
├── PPP. Stale-while-revalidate on the shell
├── QQQ. Apple touch icon + iOS install meta tags
├── RRR. Bottom-tab nav at <768px, top nav at ≥768px
├── SSS. Card-list collapse for tables on mobile
├── TTT. Guided Brew Mode (full-screen timer, wake lock, audio + haptic)
└── UUU. Playwright smoke test at 375×667 and 390×844

PHASE 12 — Hardening + smoke tests
├── VVV. Pytest smoke covering acceptance-criteria happy path
├── WWW. Unit tests: ai_service signature, encryption round-trip, analytics queries, CSRF middleware
├── XXX. Audit-log review (auth events captured, no PII)
├── YYY. CSP audit — confirm no inline-script-without-nonce in production templates
└── ZZZ. README + .env.example + NGINX server block example
```

**Why this order, in one sentence per phase:**
- 0 → 1: middleware must exist before routers can rely on session/CSRF/CSP.
- 1 → 2: auth needs session middleware.
- 2 → 3: encryption + settings are tested infrastructure other features depend on.
- 2 → 4: catalog routes need auth.
- 4 → 5: brew sessions reference catalog entities.
- 5 → 6: analytics aggregates sessions.
- 6 → 7: AI consumes analytics-style queries and writes a card alongside the page.
- 7 → 8: scheduled nightly AI refresh needs the AI service to exist.
- 4 + 5 → 10: search indexes catalog + own sessions.
- 6 + UI bulk → 11: PWA caches the shell that the UI has settled into.

---

## 4. Reverse Proxy + PWA Considerations

Real, specific, with config rather than handwaving.

### 4.1 Uvicorn proxy headers — required flags

```bash
# Inside the container, in entrypoint.sh after migrations run:
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8080 \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips "127.0.0.1"
```

- `--proxy-headers`: tells uvicorn to honor `X-Forwarded-Proto` and `X-Forwarded-For` from the trust list.
- `--forwarded-allow-ips`: the **list of upstream IPs uvicorn will trust to set those headers**. From inside the container, NGINX on the Docker host appears via the Docker bridge gateway — but if you publish port 8080 only on `127.0.0.1` (i.e. `ports: ["127.0.0.1:8080:8080"]` in docker-compose.yml), the request enters the container with source IP `127.0.0.1`. That's what to trust.
- If you bind on `0.0.0.0:8080` instead, the source IP is the Docker bridge gateway (commonly `172.17.0.1`); set the trust list accordingly. **Recommendation: bind to `127.0.0.1:8080:8080` in compose** so the container is never directly reachable from the public internet.

`TRUSTED_PROXY_IPS` env var should be a comma-separated string parsed into the uvicorn flag in `entrypoint.sh` so deployment topology can change without a code change.

**Source:** [Uvicorn Settings](https://uvicorn.dev/settings/) — proxy-headers and forwarded-allow-ips, [FastAPI Behind a Proxy](https://fastapi.tiangolo.com/advanced/behind-a-proxy/), [DeepWiki: Uvicorn Proxy Headers Middleware](https://deepwiki.com/encode/uvicorn/7.2-proxy-headers-middleware).

### 4.2 FastAPI `root_path` — when needed

`root_path` is only needed if the app is mounted at a subpath like `/snobbery/` rather than at a hostname's root. The spec says NGINX proxies a hostname to `localhost:8080`, which means **the app IS at root**, which means **`root_path=""` (default) is correct**. Do **not** set `root_path` unless you later move to a subpath deployment.

If a future deployment puts this behind `/coffee/`, the change is:
1. NGINX: `location /coffee/ { proxy_pass http://localhost:8080/; ... }`
2. App: `FastAPI(root_path="/coffee")` — uvicorn `--root-path` flag also works.

### 4.3 NGINX server block — required headers

For documentation; the README must include a working example. Critical lines:

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;

    # For SSE / long-running AI responses:
    proxy_buffering off;
    proxy_read_timeout 60s;
}
```

`proxy_buffering off` matters specifically if you choose SSE for AI streaming. Without it, NGINX buffers the whole response before sending it, defeating SSE. If you stick with HTMX polling, buffering is fine.

`Strict-Transport-Security` is set at the NGINX layer per spec — leave it out of the app.

### 4.4 Session cookie + SameSite + reverse proxy

The session cookie is `HttpOnly; Secure; SameSite=Lax`. With reverse proxy:

- **`Secure` requires HTTPS.** If uvicorn doesn't believe the request is HTTPS (because `--proxy-headers` isn't on, or trust list is wrong, or NGINX isn't setting `X-Forwarded-Proto: https`), the browser sets the cookie over the apparent-HTTP connection but then refuses to send it back because the public URL is HTTPS. Result: invisible auth failures, redirect loops. **The single most common reverse-proxy bug.** Test path: GET `/setup` over public HTTPS, create user, POST `/login`, confirm cookie persists.
- **`SameSite=Lax` is correct** for an app that's mostly internal links. It blocks cookies on cross-site POSTs (good CSRF defense layer on top of the explicit CSRF token). If you ever embed Snobbery in an iframe on another origin: don't, but if forced, `SameSite=None; Secure` is required.

### 4.5 CSP nonces + HTMX + Alpine — the inline-script trap

The spec mandates a restrictive CSP with no inline scripts. HTMX and Alpine both have known interactions:

- **Alpine.js** uses `new Function()` to evaluate expressions in `x-data`, `x-show`, etc. This requires `'unsafe-eval'` in `script-src` — which **violates the spec's restrictive CSP intent**. The fix is to use the **Alpine CSP build** (`alpinejs/dist/cdn.csp.min.js` instead of the default). It supports almost all of the inline expression syntax but does not allow arbitrary JS in directives. Confirm any custom directives in advance — most everyday Alpine usage still works.
- **HTMX** has an `htmx.config.inlineScriptNonce` option that auto-injects the page's CSP nonce into any inline scripts HTMX processes from server responses. **This is a security footgun**: it negates the protection the nonce was supposed to provide. Don't enable it unless absolutely necessary. Recommendation: **don't return inline `<script>` tags from HTMX partials.** Keep all JS in `app/static/js/*.js` files and use Alpine's `x-init` / `x-on` attributes for inline behaviors — those still work under Alpine CSP.
- **Nonce generation**: middleware mints a per-request 16-byte random nonce, attaches to `request.state.csp_nonce`. Jinja `base.html` exposes it via a context processor as `{{ csp_nonce }}` and applies it to every legitimate `<script>` tag the app emits. CSP header: `script-src 'self' 'nonce-{nonce}'; style-src 'self' 'nonce-{nonce}'; img-src 'self' data:; …`

**Source:** [Alpine.js CSP docs](https://alpinejs.dev/advanced/csp), [HTMX CSP discussion](https://www.sjoerdlangkemper.nl/2024/06/26/htmx-content-security-policy/), [DeepWiki: HTMX CSP and Script Handling](https://deepwiki.com/bigskysoftware/htmx/9.2-csp-and-script-handling).

### 4.6 PWA service worker — scope, location, and update strategy

- **Scope: the whole app.** The service worker must control every route. The default scope of a service worker is the directory it's served from. If you serve it from `/static/sw.js`, the scope is `/static/` — useless.
  - **Fix:** serve `sw.js` from `/sw.js` (root path). Add a dedicated route `routers/pwa.py:sw` that returns the file with header `Service-Worker-Allowed: /`. Same for `/manifest.json`. Don't bury either under `/static/`.
  - Register on the client: `navigator.serviceWorker.register('/sw.js', { scope: '/' })`.
- **Strategy:** stale-while-revalidate on the app shell (`/`, `/static/css/tailwind.css`, `/static/js/*.js`, `/manifest.json`, icons). **Network-first** on every other GET, **bypass** on every non-GET. This matches the spec's "cached read-only pages — write operations still require connectivity."
- **Update flow:** the service worker file's bytes act as the cache key for browsers. To force an update, embed a build hash in a comment: `// build: {{ BUILD_HASH }}`. Render `sw.js` via a Jinja template (yes, JS through Jinja) injected with the git SHA at container build time. When a new container deploys, the SHA changes, browsers detect the worker changed, install the new one. The new worker calls `self.skipWaiting()` and clients refresh on next navigation.
- **Cache versioning:** name the cache `snobbery-shell-v{BUILD_HASH}` so each deploy uses a fresh cache. Worker's `activate` event purges any cache name that doesn't match.

**Source:** [MDN Using Service Workers](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API/Using_Service_Workers) — covers Service-Worker-Allowed header and scope rules.

### 4.7 PWA + reverse proxy + camera

`<input type="file" accept="image/*" capture="environment">` requires a **secure context** (HTTPS) on mobile. Since NGINX terminates TLS and the app receives `X-Forwarded-Proto: https`, the browser always sees HTTPS. No special config — but confirm during the responsive smoke test.

The `Permissions-Policy: camera=(self)` header from the spec is exactly right for this; it allows the camera on same-origin only.

---

## 5. Concurrency Model

### 5.1 Recommendation

**One uvicorn worker. Async everywhere FastAPI handlers touch the AI service or any external HTTP call. Synchronous handlers + sync SQLAlchemy session everywhere else.**

### 5.2 Why one worker

The spec mandates in-process APScheduler. APScheduler in-process with N workers fires every job N times. The spec also assumes module-level in-memory locks (per-user AI lock). Both require single-process.

Household scale (2 users) makes this a non-issue capacity-wise. A single uvicorn worker on a small VPS handles dozens of requests/second on this style of app. The cap is the LLM call latency, not the worker count.

**Document this in the README explicitly so a future operator doesn't `--workers 4` "for performance" and break the scheduler.**

If/when scaling beyond a single household (not in scope), the fixes are:
- APScheduler → external Postgres-backed job store + leader election OR move scheduled jobs to a separate sidecar container.
- In-memory locks → Postgres advisory locks (`pg_try_advisory_lock`).
- Single worker → multiple workers behind uvicorn's own loop.

### 5.3 Async/sync mix — when to use which

| Code path | Mode | Why |
|---|---|---|
| Routers calling `services/analytics`, `services/auth`, etc. | **`def` (sync)** | FastAPI runs sync handlers in a threadpool — fine. SQLAlchemy 2.0 sync `Session` is simpler than `AsyncSession` and the DB calls are local + fast. |
| Routes calling `ai_service.*` | **`async def`** | AI calls are 10–30s with web search. Blocking a worker thread that long is wasteful. The AI service exposes async methods; routes await them. |
| Routes returning SSE streams (`/ai/stream`) | **`async def`** | `sse-starlette` requires async generators. |
| Routes that just kick off background work (`/ai/refresh`) | **`async def`** | Uses `asyncio.create_task(...)` to run the AI call without blocking the response. Returns 202 immediately. |
| `ai_service.compute_input_signature` | **sync** | It's a single SQL aggregate. Wrap in `await asyncio.to_thread(...)` if called from an async context, or just call from a sync helper. |
| `services/photos.py` (Pillow) | **sync** | Pillow is sync. CPU-bound thumbnail generation runs in the threadpool when called from a sync handler — that's fine. |
| `services/backup.py` (pg_dump) | **sync** | `subprocess.run`. Called only from APScheduler, never from a request handler. |
| APScheduler job functions | **async** | `AsyncIOScheduler` runs jobs in the same event loop. AI refresh job is async (it calls ai_service async). Backup job is async but does sync work via `await asyncio.to_thread(run_pg_dump)`. |

**Anti-pattern to refuse:** `async def` handler that calls a sync `Session.execute()`. Blocks the event loop. If a handler must be async (because it awaits something), make sure DB calls go through `await asyncio.to_thread(...)` or use an async SQLAlchemy session for that path. **Do not mix.**

### 5.4 APScheduler specifics — what to set

```python
# services/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler(
    timezone=settings.APP_TIMEZONE,
    job_defaults={
        "misfire_grace_time": 60 * 30,   # 30 min — if app was down at fire time, run if it comes up within 30
        "coalesce": True,                # if we missed N firings, run once not N times
        "max_instances": 1,              # never run a job in parallel with itself
    },
)
```

- **`misfire_grace_time`**: if the container was restarting during the scheduled fire, run on next start as long as <30 minutes have passed. After that, skip — wait for the next nightly run. This avoids a 4-hour-late nightly run after a long outage.
- **`coalesce: True`**: if the container was down for two nightly cycles, run once not twice.
- **`max_instances: 1`**: if a nightly run takes longer than 24h (it shouldn't, but defensive), the next fire skips.

**Start the scheduler in the lifespan**, not in a module side effect:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    yield
    scheduler.shutdown(wait=True)
```

### 5.5 In-memory AI lock

```python
# services/ai_service.py
_locks: dict[tuple[UUID, RecType], asyncio.Lock] = {}
_locks_guard = asyncio.Lock()

async def _get_lock(user_id: UUID, rec_type: RecType) -> asyncio.Lock:
    async with _locks_guard:
        if (user_id, rec_type) not in _locks:
            _locks[(user_id, rec_type)] = asyncio.Lock()
        return _locks[(user_id, rec_type)]
```

Single-process means a single `_locks` dict. The scheduler's nightly run and a user's manual refresh contend on the same `asyncio.Lock` and exactly one wins. Document the single-worker requirement in the docstring of `_get_lock` so the constraint is visible at the code site.

---

## 6. Open Questions

1. **SSE vs polling for AI streaming.** Recommendation: **start with polling** (simpler, no NGINX buffering issue, easier to debug). Revisit during the AI flow phase. The stack supports both (sse-starlette + htmx-ext-sse already in STACK.md).
2. **Where to render the CSRF token in HTMX partials.** Each partial swap may need a fresh token. Options: (a) HTMX `hx-headers='{"X-CSRF-Token": "{{ csrf_token }}"}'` interpolated into every partial — verbose. (b) Single global config in `base.html` reading the cookie value via JS at request time — cleaner. Recommendation: (b), set once via `htmx.config.headers['X-CSRF-Token'] = getCookie('csrftoken')` in a small inline-with-nonce script in `base.html`.
3. **Photo route caching with private content.** If a future feature shares photos between users, the `Cache-Control: private` might bite. For v1 the catalog is shared but the user is always authenticated, so private caching is fine and avoids stale shared caches.
4. **Backup file location vs Docker volume layout.** Spec says `/app/data/backups`. Confirm the named volume `coffee_snobbery_backups` is mounted there in compose. Also confirm photos at `/app/data/photos` (named volume `coffee_snobbery_photos`). Trivial but explicit in the compose plan-phase.
5. **Search choice deferred.** STACK.md surfaces this as plan-phase decision. Both options are pure-Postgres. No architecture impact — both go through `services/search.py`.
6. **Service-worker update during long-running session.** If a user is mid-Guided-Brew when a new SW activates, the page is forcibly refreshed → timer state is lost. Mitigation: don't activate during navigation if `document.visibilityState === 'visible'` and a `data-brew-active` attribute is set on `<body>`. Implementation detail for PHASE 11.

---

## Sources

- [FastAPI Behind a Proxy](https://fastapi.tiangolo.com/advanced/behind-a-proxy/) — `root_path`, X-Forwarded-* trust.
- [Uvicorn Settings](https://uvicorn.dev/settings/) — `--proxy-headers`, `--forwarded-allow-ips`.
- [DeepWiki: Uvicorn Proxy Headers Middleware](https://deepwiki.com/encode/uvicorn/7.2-proxy-headers-middleware) — trust-list semantics.
- [MDN — Using Service Workers](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API/Using_Service_Workers) — scope, Service-Worker-Allowed header.
- [MDN — ServiceWorkerContainer.register()](https://developer.mozilla.org/en-US/docs/Web/API/ServiceWorkerContainer/register) — registration scope rules.
- [Alpine.js CSP docs](https://alpinejs.dev/advanced/csp) — Alpine CSP build, expression evaluator.
- [HTMX and Content Security Policy](https://www.sjoerdlangkemper.nl/2024/06/26/htmx-content-security-policy/) — nonce injection footgun.
- [DeepWiki: HTMX CSP and Script Handling](https://deepwiki.com/bigskysoftware/htmx/9.2-csp-and-script-handling) — `inlineScriptNonce` config.
- [FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/events/) — APScheduler start/stop pattern.

**Confidence assessment:**
- HIGH for component boundaries, request flow, middleware ordering, and the reverse-proxy + service-worker scope guidance (all verified against official docs).
- HIGH for the single-worker APScheduler rule (canonical pattern documented across multiple sources).
- HIGH for the CSP + Alpine + HTMX trap (Alpine's own docs are explicit; HTMX footgun documented in their wiki).
- MEDIUM for the build-order DAG (it's defensible but reflects judgment about phase boundaries — alternative orderings could work).
- MEDIUM for the SSE-vs-polling recommendation (genuine trade-off; revisit in plan-phase).
