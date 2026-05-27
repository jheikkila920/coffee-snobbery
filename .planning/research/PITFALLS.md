# Domain Pitfalls — Snobbery

**Domain:** Self-hosted household coffee log with scheduled AI calls + web search, FastAPI + HTMX + Postgres + PWA on a single VPS
**Researched:** 2026-05-16 (v1.1); updated 2026-05-25 (v1.2 additions)
**Confidence:** HIGH where verified via official docs / WebSearch corroboration; LOW marked inline.

Each pitfall: **Warning signs (observable) → Prevention (one specific action) → Owning phase/layer.**

---

## 1. AI-Flow Pitfalls

| # | Pitfall | Warning Signs | Prevention | Owning Phase / Layer |
|---|---------|---------------|------------|----------------------|
| AI-1 | **Web-search token cost dwarfs the per-search fee.** Anthropic charges $10/1k searches, but each search-returned page is billed as *input tokens* on the next turn — a single coffee-rec call can easily push 30–80k input tokens. Signature-based regen is the only line of defense (the user opted out of a token ceiling). | Token usage in `ai_recommendations.tokens_used` grows linearly with number of search iterations even when prose stays short; nightly job summary shows surprising input-token counts. | Persist `web_search_count` *and* `input_tokens_search` separately in `ai_recommendations`. Cap `max_uses` on the Anthropic web_search tool to a hard ceiling (recommend 5 for primary, 3 for broadened) — both providers accept this. Log a WARN when a single user run exceeds 50k input tokens. | AI service phase (`ai_service.py`) |
| AI-2 | **Hallucinated product URL passes HEAD check then 404s in browser.** Ahrefs study: Claude hallucinates URLs at ~0.58% rate, and many "valid" URLs are bot-blocked. A specialty roaster site behind Cloudflare often returns 403 to `httpx` HEAD but 200 to a real browser — your code marks it unverified even though the link works. Conversely, a soft-404 product page returns 200 with "out of stock" body. | UI shows "couldn't verify" on URLs the user can click and reach fine. Or: verified buy buttons land on category pages, not product pages. | Two-pronged: (a) Use `GET` with `Range: bytes=0-2048` instead of HEAD, since many CDNs block HEAD but allow ranged GET; (b) check status 2xx **and** look for the model-returned coffee name in the response body — if absent on a 200, mark `url_verified=false`. Set `httpx` headers to a realistic UA + Accept-Language; 5s timeout per the spec; do not follow redirects across hosts. | AI service phase (URL validation worker) |
| AI-3 | **Structured-output schema rejects the response when web_search citations are present.** When Anthropic emits `web_search_tool_result` content blocks, the final assistant message can include citation blocks Instructor/Pydantic doesn't expect; schema validation throws and the user sees "Try again". | Logs: `ValidationError` on `CoffeeRecommendation` with mention of `citations` or unexpected content-block types; user reports "Try again" loops only when AI did web search. | In `ai_service.py`, always pass the assistant message through a *projector* that strips citation blocks and extracts only the structured-output tool call result before Pydantic validation. Anthropic's structured output via tool-use returns the schema-matching JSON in the *tool_use* block — read that block directly, do not parse the prose. | AI service phase |
| AI-4 | **Provider fallback double-charges.** Anthropic call fails mid-stream (timeout, rate limit, 529 overload), code falls back to OpenAI — but the Anthropic call may still complete server-side and be billed, *and* OpenAI completes successfully. Worse: fallback fires for transient retry-eligible errors. | Provider-split token costs in the job summary show OpenAI usage on days you didn't expect it. `provider_used` flips to `openai` on otherwise normal nights. | Only fall back on definitively non-retryable errors: `AuthenticationError`, `BadRequestError`, `PermissionDeniedError`, and persistent `OverloadedError` *after* one retry with backoff. Treat connection timeouts and 429 as retry-with-jitter, not as fallback. Set `max_retries=1` on the SDK client to disable its hidden retry loop. | AI service phase |
| AI-5 | **The same Anthropic web_search tool version becomes deprecated.** Spec hard-codes `web_search_20250305`. Anthropic ships new tool versions periodically; the dated name will eventually 400. | API error: `tool_use_failed` or `unknown_tool` from Anthropic; only fires after a model/SDK upgrade. | Read the tool version from `app_settings` (new row, value_type=string, default `web_search_20250305`) and surface it in the admin UI's "AI configuration" panel so John can swap without a redeploy. Same pattern for OpenAI `web_search` vs `web_search_preview` — the preview variant is being deprecated and lacks the `external_web_access` filter ([OpenAI docs](https://platform.openai.com/docs/guides/tools-web-search)). | Admin / AI service phase |
| AI-6 | **In-memory lock leaks on crash.** Spec calls for in-memory per-`(user_id, recommendation_type)` lock to coordinate scheduler vs manual refresh. If the uvicorn worker is killed mid-AI-call (OOM, deploy, SIGTERM), the lock dict in that worker's memory dies with it. On next worker, lock is empty; no problem. But if running >1 worker, two workers can both lock the same key. | Two concurrent AI calls for the same user on the home page; duplicate rows in `ai_recommendations` with overlapping `generated_at`. | Use a DB-backed advisory lock instead: `SELECT pg_try_advisory_xact_lock(hashtext(user_id::text || recommendation_type))` at the start of the AI service call. Falls back to in-memory if you keep uvicorn at `--workers 1` (recommended for household scale — call it out in the README). | AI service phase / deployment phase |
| AI-7 | **Cold-start recommendation triggers for user who reached exactly 3 sessions today, but `flavor_note_ids_observed` is all NULL.** Profile-derivation queries hit `NULL` arrays, return empty top-flavor list; AI model receives a vague profile and produces generic "try an Ethiopia natural" with no actual grounding. The user sees AI but it's not grounded in their data. | `summary_prose` reads like a generic blog post; `why_recommended` does not reference any specific session detail; user complains "this isn't based on my brews." | In `analytics.py`, require **both** `brew_sessions ≥ 3` **and** `count(distinct flavor_note_ids_observed) ≥ 5` before unlocking AI. Bump cold-start threshold to mean the inputs are actually informative, not just present. Document the threshold in `app_settings` (`min_sessions_for_ai`, `min_flavor_notes_for_ai`). | Home page / analytics phase |

---

## 2. HTMX + Jinja Pitfalls

| # | Pitfall | Warning Signs | Prevention | Owning Phase / Layer |
|---|---------|---------------|------------|----------------------|
| HX-1 | **CSRF token rotation breaks HTMX requests after first POST.** Spec says CSRF on every state-changing form. If tokens rotate per-session (good) and `hx-headers` is set on `<body>`, the *first* HTMX POST sends the right token; the server rotates and responds with a *partial fragment*, which does not update `<body>`'s `hx-headers`. Second POST sends a stale token → 403. | Browser network tab: first POST succeeds, second returns 403 with HX-Reswap headers absent. Users see "session expired" toasts after a sequence of HTMX actions on the brew form. | Use a per-request token but expose it via a hidden `<meta name="csrf-token">` in the **fragment response**, plus an `htmx:configRequest` listener that reads `document.querySelector('meta[name=csrf-token]').content` on every request. Alternatively: double-submit-cookie pattern where the cookie value is the token — no token rotation per request needed, and HTMX automatically sends the cookie. (Recommend double-submit-cookie for this stack; simpler with HTMX.) | Security hardening phase |
| HX-2 | **Browser back button on home page after edit shows stale HTMX fragment instead of full home.** Lazy-loaded analytics cards arrive as HTMX fragments. User edits a coffee, hits back — browser bfcache restores the last *fragment* response for `/`, not the full page. User sees a single card filling the viewport. | Bug reports: "I clicked back and the page looks broken / blank / shows only one card." | Three measures: (a) on every fragment-returning endpoint, send `Cache-Control: no-store` and `Vary: HX-Request`; (b) put `hx-history="false"` on the lazy-load containers so they don't get cached in localStorage history; (c) when returning a fragment with `hx-push-url`, return the **full body** with `hx-select` to extract the swap target — per HTMX docs, this is the recommended fix. | Home page / HTMX patterns phase |
| HX-3 | **`hx-swap-oob` on the flavor-note tag-input creates duplicate IDs.** When a user types a new flavor note ("nectarine") in the brew-session tag input, the server returns the new chip plus an OOB swap of the global flavor-notes datalist. If the user submits twice quickly, two OOB responses both target `id="flavor-notes-datalist"` — HTMX matches by id and only swaps the *first* match; subsequent responses no-op silently. | Network shows 200s for both POSTs; UI shows the second new note didn't appear in the datalist; refresh fixes it. | Use HTMX 1.9.10+ which supports `hx-swap-oob="outerHTML:#flavor-notes-datalist"` (explicit selector). Better: serve the datalist as its own endpoint via `hx-get` on the input's focus event with `hx-trigger="focus once"` — no OOB swap needed. | Brew session form phase |
| HX-4 | **HTMX live-search hammers the DB at 250ms debounce × multi-character typing on global search.** Spec: debounce 250ms; the user typing "ethiopia" sends 8 separate trigram-search queries because each keystroke after 250ms idle fires a request. With `pg_trgm` ILIKE searches across coffees + roasters + flavor_notes + brew_session notes, this is 8 queries × 6 tables = 48 LIKE scans before the user finishes the word. | Postgres logs show repeated near-identical search queries with sequential `WHERE name ILIKE '%e%'`, `%et%`, `%eth%`; pg_stat_statements top hits are search queries. | Two changes: (a) bump debounce to 350ms — perceptually still instant, halves the request rate; (b) on the client, cancel the in-flight HTMX request when a new keystroke fires using `hx-sync="this:replace"`. Also: require minimum 2 characters before search executes (`hx-trigger="input changed delay:350ms[target.value.length >= 2]"`). | Search phase |
| HX-5 | **Lazy-load thundering herd on home page.** Spec: each home-page section lazy-loads via HTMX. Six sections (top coffees, preference profile, sweet spots, AI rec, recent brews, unrated coffees) all fire `hx-trigger="load"` simultaneously. If AI rec or analytics queries are slow, six in-flight HTMX requests block other interactions; on mobile cell data, page feels janky. | DevTools: 6 simultaneous requests on `/` load; Time-To-Interactive on mobile >2s; users say "the home page is slow." | Stagger lazy loads with `hx-trigger="load delay:100ms"` increments per section. Critical AI sections last (delay 400ms). The AI recommendation specifically should use `hx-trigger="revealed"` (intersection-observer based) so it only fires when scrolled into view — saves one expensive request when the user lands on home and clicks "Log" before scrolling. | Home page phase |
| HX-6 | **`autoescape on` plus `\|safe` in AI prose injection.** Spec: never use `\|safe` on user-provided content. AI prose isn't user-provided, but the model can include user-provided strings (coffee names, flavor notes) in the prose. If someone names a coffee `<script>alert(1)</script>` and that name surfaces in `summary_prose`, autoescape catches it — but only if the templater never sees `\|safe`. The temptation: render `why_recommended` with `\|safe` to allow markdown bold for emphasis. | Coffee name with HTML renders as actual HTML in the AI section; XSS lint catches `\|safe` near AI output. | Hard rule, enforced by grep test in CI: `\|safe` is forbidden in any template under `templates/pages/`. If markdown is needed, server-side render the AI prose through `markdown` library with `safe_mode=True` (or bleach the output), then pass as `Markup()` from the route — single chokepoint, easier to audit. | AI integration phase / security hardening |

---

## 3. PWA Pitfalls (2026 reality)

| # | Pitfall | Warning Signs | Prevention | Owning Phase / Layer |
|---|---------|---------------|------------|----------------------|
| PWA-1 | **iOS Safari never shows an install prompt.** Spec says "must be installable on iOS Safari and Android Chrome." On iOS, there is **no** `beforeinstallprompt` event; users must tap Share → Add to Home Screen manually. Farrah will not discover this on her own. | User complaint: "I can't find the install button on iOS." Android works fine, iPhone doesn't. | Detect iOS user-agent + standalone-mode-absent and show a one-time educational banner: "To install Snobbery on your iPhone, tap [share icon] then 'Add to Home Screen'." Persist dismissal in localStorage. The banner is required because iOS will *never* prompt. | Mobile/PWA phase |
| PWA-2 | **`start_url` redirects on first install, install prompt silently fails.** If `start_url: "/"` and the user isn't authenticated, `/` redirects to `/login`. Chrome marks the manifest invalid for installability because start_url must return 2xx without redirect. PWA never becomes installable. | Chrome DevTools → Application → Manifest shows "start_url is not reachable" or installability warning. Add to Home Screen menu absent in Chrome. | Set `start_url: "/?source=pwa"` and serve `/` with a 200 + login-aware shell (not a redirect). The login redirect should be client-side via a small HTML page that includes JS `location.replace('/login')` — preserves the 200 status and keeps the manifest valid. | Mobile/PWA phase |
| PWA-3 | **Service worker scope too narrow because `sw.js` lives under `/static/`.** Common mistake: register `/static/sw.js`, scope defaults to `/static/`, SW does not control any actual page. App-shell caching does nothing. | Network tab shows SW registered but no requests intercepted; "from cache" missing on app-shell requests. | Serve the service worker file at the root path via a dedicated FastAPI route (`@app.get("/sw.js")` returning `FileResponse` with `Service-Worker-Allowed: /` header). Register with `navigator.serviceWorker.register('/sw.js', { scope: '/' })`. Static-mounted files cannot escape their mount scope. | Mobile/PWA phase |
| PWA-4 | **iOS evicts the PWA cache after 7 days of non-use.** iOS imposes ~50MB cache + IndexedDB limit and evicts aggressively if the PWA is not opened weekly. The brew-session form's localStorage *draft* survives (different storage), but the cached app shell is gone — next open over cell data feels slow. | User complaint about PWA being slow on Monday after a weekend off; iOS only. Devtools (if you can attach) shows empty caches. | Two responses: (a) keep the cached shell **tiny** (HTML skeleton + Tailwind CDN reference + manifest + 2 icons) — well under 1MB so eviction less likely; (b) on launch from home-screen, fetch fresh shell in the background regardless of cache state (`stale-while-revalidate`), so any eviction is invisible after first online launch. | Mobile/PWA phase |
| PWA-5 | **Theme color flickers on dark-mode launch.** Spec: warm + minimalist + system-preference dark mode. `manifest.json` has a single `theme_color` — iOS uses it for the status bar on launch, but the actual page is dark-mode and the status bar stays light, looking broken for a beat. | Visual flicker of status bar from cream → espresso when launching from home screen in dark mode. | Provide both via `<meta name="theme-color" content="#FAF7F2" media="(prefers-color-scheme: light)">` and `<meta name="theme-color" content="#1A1110" media="(prefers-color-scheme: dark)">`. Manifest `theme_color` falls back when meta tag absent. Confirmed working iOS 16.4+ and Chrome. | Aesthetic / Mobile/PWA phase |
| PWA-6 | **Manifest icons missing maskable variant — Android shows white square.** Android Adaptive Icons require icons with `purpose: "maskable"`. Without it, Android crops the icon into a white-padded square; looks unbranded next to other apps. | Pixel/Samsung home-screen install of Snobbery shows centered icon on white circle/square instead of full bleed; QA screenshot at install time. | Generate both: `icons[].purpose: "any"` (192, 512) **and** a separate `icons[].purpose: "maskable"` (192, 512) with safe-zone padding (80% of the 192/512 canvas; bleed background fills the rest). Use [maskable.app](https://maskable.app/editor) to verify. | Mobile/PWA phase |
| PWA-7 | **Service worker cached the old `sw.js` itself; deploy doesn't propagate.** If the SW caches its own URL (or NGINX serves `sw.js` with the same `Cache-Control: max-age` as other static assets), the browser keeps serving the old SW for 24h after deploy. Old SW keeps serving old shell → user reports "the app didn't update." | After deploy, two devices report different behavior; clearing app data fixes one device. NGINX access logs show 304 on `/sw.js` for hours after deploy. | NGINX rule: `location = /sw.js { add_header Cache-Control "no-cache, no-store, must-revalidate"; }`. Add a `CACHE_VERSION` constant in `sw.js` derived from build/commit SHA (inject via FastAPI templating: serve sw.js as a Jinja template that includes the app version) — forces SW to install when the constant changes and clean old caches in `activate`. | Mobile/PWA phase / deployment |

---

## 4. Self-Hosting Pitfalls

| # | Pitfall | Warning Signs | Prevention | Owning Phase / Layer |
|---|---------|---------------|------------|----------------------|
| SH-1 | **APScheduler misses the 00:00 AI run after a Docker restart.** Default `MemoryJobStore` + `BackgroundScheduler` loses scheduled jobs on restart; spec says nightly at 00:00. If the VPS reboots at 23:55, scheduler starts at ~23:58, jobs registered at app startup — but at 00:00 trigger, `misfire_grace_time` default is 1 second. Add load: web request blocks for 2s, job's next fire missed entirely. The 02:00 backup is also at risk. | Scheduler log: `Run time of job "ai_nightly" was missed by 0:00:03`; users see "Outdated" badges on home page next morning; no backup at 02:00 the day after a restart. | Configure scheduler explicitly: `misfire_grace_time=3600` (1h), `coalesce=True` (don't run 5 catch-up times), and `replace_existing=True` on `add_job`. Use `SQLAlchemyJobStore(url=DATABASE_URL)` so missed jobs are detected on restart — APScheduler will fire them once with `coalesce=True` if within grace window. | Scheduler phase |
| SH-2 | **Postgres connection pool exhaustion under sync HTMX traffic + 1 long AI call.** SQLAlchemy default pool_size=5, max_overflow=10 → 15 connections. The home page's 6 lazy-loaded sections each grab a connection (FastAPI sync handler holds the DB session for the duration). Add an in-flight async AI call also holding one. With 2 users hitting refresh simultaneously, you're at 14+; the next request waits, then times out at pool_timeout=30s. | uvicorn logs: `TimeoutError: QueuePool limit of size 5 overflow 10 reached`; intermittent 500s on home page during AI runs. | At household scale, the right knobs are explicit not large: `pool_size=10, max_overflow=5, pool_timeout=5, pool_pre_ping=True, pool_recycle=300`. Even more important: **stagger** the lazy-loaded sections (see HX-5) so they don't all grab connections simultaneously. Postgres 16 default `max_connections=100` is fine; don't raise it. Run `--workers 1` (household scale doesn't need more, and avoids the multi-engine connection multiplication). | Database/deployment phase |
| SH-3 | **`coffee-snobbery-db` volume permissions break after `chown` on host.** Spec uses named volume `coffee_snobbery_postgres_data`, which Docker manages — fine. But if John ever does a `docker compose down -v` + restore from a host-side `pg_dump` SQL by copying files into the volume, ownership reverts to host UID and Postgres (UID 999 inside container) refuses to start. | Container logs: `FATAL: data directory "/var/lib/postgresql/data" has invalid permissions / wrong ownership`; container restart-loops. | Document in CLAUDE.md restore procedure: **always restore via `psql < dump.sql`, never by copying data files**. Never `chown` on the host side of a named volume. The current CLAUDE.md restore section already does the right thing; add a "DO NOT do file-level restore" warning. | Backup/restore phase |
| SH-4 | **Photos bind-mount permission denied when uvicorn runs as non-root.** If Dockerfile creates a non-root user (good practice) and the photos volume is a bind mount (e.g., `/opt/snobbery/photos`), the host directory is owned by `root:root` or the deploy user (1000:1000) but the container user is something else (e.g., 1001). Image uploads fail with `PermissionError: [Errno 13]`. | Pillow throws on save: `Permission denied: '/app/data/photos/<uuid>.jpg'`; user reports photo upload spinning indefinitely. | Use named volumes (`coffee_snobbery_photos`) not bind mounts — Docker handles UID alignment. If forced to bind-mount: in Dockerfile, `RUN useradd -u 1000 -m app` to match a known host UID and document it. Pre-create the host directory with `chown -R 1000:1000`. | Deployment phase |
| SH-5 | **Nightly `pg_dump` runs inside the web container, hits the DB container — `pg_dump` version mismatch.** Web container based on python:3.12-slim doesn't have `pg_dump`; if you install Postgres 15 client (default in slim repos) and the DB is Postgres 16, `pg_dump` errors out: `server version: 16.x; pg_dump version: 15.x`. Backup silently fails. | `/app/data/backups/` empty or missing recent entries; admin "last backup" panel shows N days ago; scheduler log: `pg_dump: error: server version: 16.x` | Two options: (a) install `postgresql-client-16` from PostgreSQL apt repo in the web container Dockerfile (preferred, since the spec runs backup from web container); (b) run `pg_dump` via `docker exec coffee-snobbery-db pg_dump` from the host — but that requires Docker socket access from the web container, which is a security hole. Go with (a). | Backup phase |
| SH-6 | **`X-Forwarded-Proto` not honored — login cookie set without `Secure`, browser drops it under HTTPS.** Behind NGINX with TLS termination, FastAPI sees `http://` unless `ProxyHeadersMiddleware` is configured. Cookie middleware sees scheme=http, omits `Secure` flag, browser warns or drops it on next request. Spec mandates Secure cookies. | Login appears to succeed but immediately bounces back to /login; browser console: cookie set with Secure on a non-HTTPS scheme rejected. | Use `uvicorn --proxy-headers --forwarded-allow-ips="*"` (or set `TRUSTED_PROXY_IPS` env var per spec) **and** verify in code with a `/debug/proxy` admin-only endpoint that returns `request.url.scheme` so you can confirm `https` end-to-end. Add this to the smoke test. | Auth/security phase |

---

## 5. Security Pitfalls (stack-specific)

| # | Pitfall | Warning Signs | Prevention | Owning Phase / Layer |
|---|---------|---------------|------------|----------------------|
| SEC-1 | **Strict CSP blocks Alpine.js, HTMX inline `hx-on:`, and Tailwind CDN preflight scripts.** Spec says "restrictive CSP, no inline scripts, use nonces if required." Alpine attributes like `x-data`, `x-on:click` need `'unsafe-eval'` (Alpine compiles expressions at runtime). HTMX's `hx-on:click` and event handlers similarly. Tailwind CDN injects a `<style>` block at runtime. A strict `script-src 'self'` + `style-src 'self'` breaks all three. | Browser console: `Refused to execute inline event handler because it violates CSP`; Alpine components show raw markup; Tailwind styles missing. | Realistic CSP for this stack: `script-src 'self' 'unsafe-eval' https://cdn.tailwindcss.com https://unpkg.com; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'`. Yes — `unsafe-eval` is required for Alpine; document this trade-off in `docs/decisions/`. Mitigations: never use `\|safe` (HX-6), strict input validation, and consider self-hosting Tailwind output as a CSS file in a later phase to drop `cdn.tailwindcss.com` from the allowlist. | Security hardening phase |
| SEC-2 | **Fernet key rotation has no plan; rotating `APP_ENCRYPTION_KEY` orphans every stored API key.** Spec doesn't mention rotation, and `cryptography.Fernet(key)` only accepts one key. If John ever needs to rotate (employee handoff, key exposure), changing the env var renders every `api_credentials.api_key_encrypted` row undecryptable. | Decryption error on every AI call after rotating the env var; admin UI shows API keys cannot be loaded. | Use `MultiFernet([Fernet(new_key), Fernet(old_key)])` from day one in `services/encryption.py`. Read `APP_ENCRYPTION_KEY` as a comma-separated list (first = primary for encryption, all attempted for decryption). Add an admin "Rotate API key" button that decrypts → re-encrypts under the new primary. Document the rotation process in the README. | Security/encryption phase |
| SEC-3 | **CSRF token regeneration on login fixates the session.** Spec: signed session cookies via itsdangerous, refresh on activity. If you don't regenerate the *session ID* (not just the CSRF token) on successful login, an attacker who set the pre-auth session cookie via XSS or other vector now shares the authenticated session. | Security audit (or post-mortem): one user can log in as another via a pre-set cookie; session table shows two different user_ids attached to the same session_id over time. | On successful login: **delete the old session row, mint a new session_id, set the new cookie**. Do not just update `user_id` on the existing session row. The `sessions` table should have unique `session_id` UUID and login generates a fresh one. Same for password reset and privilege change (toggle admin). | Auth phase |
| SEC-4 | **Image upload accepts polyglot file (valid JPEG + JS).** Spec: validate magic bytes, decode via Pillow, strip EXIF. Magic bytes alone are insufficient — a file can have a valid JPEG header but contain HTML/JS appended, served back at `/photos/<uuid>` and rendered if Content-Type sniffed by the browser. EXIF strip doesn't address this. | Security scan flags `/photos/*.jpg` as text/html or executable JS. User uploads weird-looking JPEG that downloads in Safari instead of inlining. | Three steps: (a) re-encode the image after Pillow decode — `img.save(new_path, format=img.format)` strips trailing data; (b) serve photos with explicit `Content-Type: image/jpeg` (or png/webp) + `X-Content-Type-Options: nosniff` header on the photo route; (c) `Content-Disposition: inline` only, never `attachment` (which can trigger downloads of disguised files). | Photo upload phase / security |
| SEC-5 | **`/setup` race condition: two requests during cold start both create admin users.** Spec: `/setup` works only when zero users exist. If the route checks `SELECT COUNT(*) FROM users` then `INSERT`, two concurrent requests both see count=0, both insert, both become admin. Low probability in production but trivial to exploit before NGINX is even fronting the app. | `users` table after `/setup` shows two admin rows with `created_at` within milliseconds of each other. | Wrap the check + insert in a transaction with `SELECT COUNT(*) FROM users FOR UPDATE` (table-level lock) or use a Postgres unique partial index: `CREATE UNIQUE INDEX one_admin_at_setup ON users (is_admin) WHERE is_admin = true` — wait, that breaks the multi-admin case. Better: a separate `setup_completed` row in `app_settings` (boolean), wrapped in `SELECT ... FOR UPDATE` during the setup flow; once true, the route 404s. | Auth/setup phase |
| SEC-6 | **API key leaks via Pydantic `model_dump()` in error responses.** Spec: API keys never logged, only last-4 in UI. Pydantic v2 by default includes all fields in `model_dump()`. If `ApiCredential` schema includes `api_key` (decrypted) for any internal use and an exception handler does `JSONResponse(content=model.model_dump())`, the key leaks in a 500 response. | Grep `model_dump\(\)` in routes; any path that touches `ApiCredential` is suspect. CI/test that hits a poisoned endpoint sees `api_key` in JSON. | Two layers: (a) `ApiCredential` Pydantic model never includes the decrypted key — store decrypted key only in a transient `dataclass` passed to `ai_service`, never in a Pydantic model; (b) custom Pydantic config `model_config = ConfigDict(json_schema_extra={"forbidden_fields": ["api_key", "password_hash"]})` plus a CI test that introspects schemas for those names. | Encryption/AI phase |

---

## 6. Mobile UX Pitfalls

| # | Pitfall | Warning Signs | Prevention | Owning Phase / Layer |
|---|---------|---------------|------------|----------------------|
| MX-1 | **iOS Safari auto-zooms on every focus into rating/dose/water inputs.** `inputmode="decimal"` doesn't prevent it — only computed font-size ≥ 16px does. Tailwind's default `text-sm` (14px) on form inputs triggers zoom on focus; zoom *does not* automatically reverse on blur. User taps "dose" → 16px zoom → taps "water" → still zoomed → form fields now off-screen. | Test at 375px on real iPhone (or DevTools iOS simulator): tapping any input fires a zoom-in animation; viewport-width meta unchanged but visual scale increased. User complaint: "the form jumps when I tap a field." | Hard rule in `app/static/css/custom.css`: `input, select, textarea { font-size: 16px; }` — or use Tailwind's `text-base` (16px) on all form inputs, never `text-sm`. Add a smoke test at 375px that checks computed font-size on every form input. Do **not** use `viewport meta maximum-scale=1` — violates WCAG. | Brew session form / mobile phase |
| MX-2 | **`capture="environment"` on iOS opens the photo library instead of camera.** iOS Safari does not honor `capture` attribute the same way Android Chrome does. On iOS, `<input type="file" accept="image/*" capture="environment">` opens an action sheet with "Photo Library / Take Photo / Choose File" — capture is a hint, not a forcing parameter. Spec acceptance criterion: "Camera opens directly when tapping the bag photo upload control on mobile" — strictly impossible on iOS. | iOS user reports: "It asks me which one I want, it doesn't go straight to the camera"; QA fails the acceptance criterion. | Adjust the acceptance criterion to reality: on iOS the action sheet appears with camera as one of three obvious options. Add helper text below the input on iOS: "Tap to take a photo or choose one from your library." Do not over-engineer; this is platform behavior, not a bug. | Coffee catalog / mobile phase |
| MX-3 | **Sticky form actions overlap iOS bottom-nav home indicator.** Spec: sticky bottom form actions (Save/Cancel) on long forms; bottom tab nav at <768px with iOS safe-area padding. The combination: sticky form actions render *above* the bottom nav (which has safe-area padding), but on a phone where the form-action bar is also fixed, the action bar can land on or below the iOS home indicator (the bar at the bottom of the screen), making the Save button hard to tap accurately. | User reports needing two taps to hit Save; or sticky bar visually below the iOS swipe-up indicator. | Sticky form actions must use `padding-bottom: env(safe-area-inset-bottom)` and live **above** the bottom nav stacking: form actions are `bottom: calc(env(safe-area-inset-bottom) + 64px)` (assuming 64px bottom nav). Hide bottom nav entirely on long forms (Brew Session create/edit, Recipe builder) so form actions own the bottom safe-area exclusively. | Mobile phase / form patterns |
| MX-4 | **Wake lock released by tab switch, not re-acquired on return → kitchen timer dies mid-brew.** Spec: guided brew mode requests wake lock to keep screen on. iOS / Android both release the wake lock when the user switches apps (to read a message, check timer) or when the tab loses visibility. The timer keeps running, but screen darkens and locks; user comes back, lock screen, brew is past the next step. | Tester reports the screen turned off in the middle of a pour despite "Keep screen on" being active. `WakeLockSentinel.released === true` in console. | On `visibilitychange` event, when `document.visibilityState === 'visible'` and the brew is in progress, re-request the wake lock. Also: show a visible "Screen will stay on" indicator in guided brew mode that toggles to a warning if the lock is released, so the user knows. | Guided brew mode phase |
| MX-5 | **`localStorage` brew-session draft survives logout, leaks across users on a shared phone.** Spec: localStorage draft persistence across reload. If Farrah logs out and John logs in on the same device (rare but plausible for a household app), John sees Farrah's in-progress draft prefilled. | Two-user test: User A starts a brew draft, logs out without submitting; User B logs in and the brew form is pre-populated. | Namespace the localStorage key by user ID: `snobbery:draft:brew:<user_id>` instead of `snobbery:draft:brew`. Clear all `snobbery:draft:*` keys on logout. On login, only restore drafts matching the current user_id. | Auth / brew session phase |
| MX-6 | **Rating input "0.25 step" slider unusable with thumb at 375px.** Native `<input type="range" step="0.25" min="0" max="5">` rendered at full width (~343px after padding) gives ~17px per quarter-star — well below 44px tap target. User tries to tap "4.25" with a thumb, gets 4.0 or 4.5. | User complaint: "I can never give exactly the rating I want, it always snaps wrong." | Replace native range with a tap-on-stars component: 5 stars visible, each star is a 56×56px tap target, tap left-half=quarter, center-half=half, right-half=three-quarter, second-tap-on-same-star=full. Alpine.js component reading clientX. Half-star + quarter-star granularity by tap zones. | Brew session form / mobile phase |

---

## 7. Cost-Related Pitfalls

| # | Pitfall | Warning Signs | Prevention | Owning Phase / Layer |
|---|---------|---------------|------------|----------------------|
| COST-1 | **Signature collision: hash uses only count + max(updated_at), misses session edits that net-out to no count change.** Spec input signature: `(session_count, max(updated_at), equipment_count, recipe_count)`. If a user edits *and saves without changing anything*, `updated_at` advances, signature changes, nightly regen fires — actually correct. But if a user deletes a session and adds one with an older `brewed_at`, count stays the same, max(updated_at) might or might not advance depending on tx ordering. False negatives possible. | Spot check: regen-skip logs say "signature unchanged" on days the user clearly logged a new brew. | Use a more robust signature: `md5(concat_ws('|', count(*), max(updated_at), sum(rating), array_agg(coffee_id ORDER BY brewed_at)))` — captures content, not just shape. Compute in a single SQL `SELECT ... INTO ai_signature`. | AI service / scheduler phase |
| COST-2 | **Manual "refresh recommendations" button has no throttle — user spams it during a 30s AI run.** Spec: in-memory lock prevents concurrent runs, but the lock only prevents *concurrent* execution. After the first run completes (30s later), the next click queues another run. A bored user clicking 5x in 2 minutes triggers 5 sequential calls, each with web search costs. | `ai_recommendations` rows for one user clustered within minutes. Anthropic monthly bill higher than expected. | Backend throttle: refuse manual refresh if last manual refresh was <5 minutes ago (return 429 + HX-Retarget to a "please wait" message). Frontend: button disabled state for 60s after click; show countdown. Both required because client-side alone is bypassable. | AI service / home page phase |
| COST-3 | **Model deprecation breaks the entire AI flow — admin doesn't know until users report it.** `api_credentials.model` stored as text (`claude-opus-4-7`, `gpt-4o`). Anthropic and OpenAI deprecate models on a regular cadence. The nightly scheduler will log a 400 per user, then move on; admin doesn't see the error unless they tail logs. | Logs: `model_not_found` or `404 not_found` from SDK; admin page shows API key as configured but no recommendations regenerate. Users see "Outdated — refresh?" badge forever. | Two parts: (a) `app_settings` health-check row updated each scheduler run with `last_ai_run_status` (success/error + message); admin home shows a banner if last status was error; (b) at app startup, perform a tiny test call against each enabled provider (`messages.create` with max_tokens=10) and log/store the result. Surface failures in the admin "API credentials" panel as a red badge. | Admin / scheduler phase |
| COST-4 | **Web-search runs on every nightly job even when the user has zero new sessions — because of `equipment_count` or `recipe_count` shared changes.** Equipment and recipes are *shared* across the household. If John buys a new grinder, equipment_count goes up *for everyone* — Farrah's signature changes too, triggering an AI regen for her despite zero changes in her sessions. With 2 users, this doubles the AI bill for any shared-catalog change. | Multi-user days show 2× expected AI runs; Anthropic dashboard spike correlates with admin adding equipment/recipes. | Two options: (a) Remove `equipment_count` and `recipe_count` from the signature — they rarely change taste profile meaningfully, and the manual refresh button is available; (b) per-user signature includes only the equipment/recipes that *user* has actually used in a session (`SELECT DISTINCT brewer_id FROM brew_sessions WHERE user_id = ?`). Option (b) is more accurate; option (a) is simpler. Recommend (a) for v1. | AI service / scheduler phase |
| COST-5 | **`max_uses` on web_search tool not set; model runs 8+ searches per recommendation.** Anthropic's `web_search_20250305` defaults to no `max_uses` limit; on a "find me a Hario Switch friendly natural Ethiopia" query, Claude can iteratively search 6–10 times if results are weak. Each = $0.01 + thousands of input tokens. | `ai_recommendations.web_search_used` true with token usage 4–10× a non-search call; bill higher than expected per recommendation. | Always pass `max_uses=5` for primary search and `max_uses=3` for the broadened fallback. Document the values in `app_settings` (`ai_primary_max_searches`, `ai_broadened_max_searches`) so John can tighten if costs surprise. | AI service phase |

---

## 8. v1.2 Feature-Specific Pitfalls

These pitfalls are specific to new v1.2 capabilities: on-demand AI research + predict-rating, cafe quick-rate, prebuilt-image distribution, IA restructure, and the mobile-first full rework. They are in addition to the v1.1 pitfalls above, not replacements.

---

### v1.2-AI-1: On-Demand Research Removes the Cadence Gate — Surprise Bill Risk

**What goes wrong:**
The existing AI cost control is a single gate: signature-based nightly regen fires at most once per user per night. An on-demand "research a coffee + predict rating" button is a different contract — the user can tap it as many times as they want, each call consuming web-search quota. Two users tapping on 10 different coffees in an afternoon can spike costs 10–20× the normal nightly baseline.

**Why it happens:**
The nightly flow has natural throttling (one run per day per user, 30s+ execution, UI shows "Generating..." for a long time). The on-demand button does not — it returns fast for already-cached results and costs nothing, but on a cache miss it fires the full web-search stack.

**How to avoid:**
- DB cache table `coffee_research(coffee_id, provider, model, research_text, researched_at)` keyed on `(coffee_id, provider, model)`. Serve cached results if fresher than 7 days. Prediction from cached research is a non-search LLM call — cheap.
- `slowapi` per-user per-day limit on `POST /ai/research` (recommend 10 calls/user/day). Return a 429 with a human-readable message including the reset time.
- Expose remaining quota in the UI: "5 of 10 daily research calls used."
- Separate the two steps at the API level: `POST /ai/research` (web search, cached) vs. `POST /ai/predict` (non-search, uses stored research text). The predict endpoint has no web-search cost.

**Warning signs:**
- No DB cache table for research results.
- No `slowapi` decorator on the research route.
- Research and prediction are a single atomic endpoint with no result reuse.
- The endpoint accepts arbitrary free-text coffee names — not `coffee_id` FK — making caching impossible.

**Phase to address:** AI Research + Predict phase. Both cache table and rate limit are blocking requirements, not optional polish.

---

### v1.2-AI-2: Predicted Rating Presented Without Uncertainty — Trust Erosion

**What goes wrong:**
The model returns a number. The UI displays it next to the coffee name using the same star-rating component as real brew sessions. The user brews the coffee, gives it a 2.5 when it predicted 4.2, and stops trusting the feature. On a 0–5 scale with 0.25 steps, a ±1 prediction window covers 40% of the range.

**How to avoid:**
- Display as a range or confidence band: "Likely 3.5–4.5" — not a point estimate.
- Include the basis: "Based on your 12 sessions, 4 matching flavor notes."
- Use a visually distinct component — not the star-rating widget used for real sessions. A text description ("probably a good fit," "may not match your preferences") is more honest than a false-precision number.
- Gate prediction behind the cold-start threshold: ≥3 sessions AND ≥5 distinct flavor notes. The same gate that guards the nightly recommendation — reuse `analytics.get_ai_eligibility(user_id)`.
- Store the prediction with `sessions_at_prediction` count so the UI can note "predicted when you had N sessions" — transparency about staleness.

**Warning signs:**
- Prediction displayed with the `<star-rating>` component used for real brew ratings.
- No minimum-session gate on the prediction path.
- The LLM prompt does not instruct the model to express uncertainty.

**Phase to address:** AI Research + Predict phase.

---

### v1.2-CAFE-1: Cafe Sessions Pollute Brew Analytics and AI Signal

**What goes wrong:**
Cafe sessions have no grind, dose, ratio, or recipe — they're taste-only. If stored as `brew_sessions` rows with NULL fields, the analytics home page includes them in ratio preference derivations, equipment usage counts, and the AI input signature. A user with 20 cafe sessions gets skewed analytics (apparent grind preferences from NULL rows) and the AI signature changes on every cafe log, triggering unnecessary nightly regens.

**Why it happens:**
The obvious shortcut is to reuse `brew_sessions` with NULL columns for the brew-method fields. It avoids a migration and reuses the existing list/filter UI. But `analytics.py` queries assume NULLs mean "user didn't fill this in," not "this is a structurally different record type."

**How to avoid:**
- Add `session_type ENUM('brew', 'cafe')` to `brew_sessions` in one migration.
- Filter `session_type = 'brew'` in ALL analytics queries: ratio derivations, equipment usage, grind preference, sweet spots. This is backward-compatible — all existing rows are `'brew'`.
- AI input signature generator must exclude cafe sessions: `WHERE session_type = 'brew'`.
- `equipment.usage_count` increments skip NULL `equipment_id` (already true for the FK path) — but explicitly verify the cafe create route does not touch `usage_count` at all.
- Prefill resolver for `/brew/new` must filter `session_type = 'brew'` when finding the "last session."
- CSV export: include `session_type` column. Import: reject rows with `session_type=cafe` that also have `recipe_id` set.

**Warning signs:**
- `brew_sessions` has no discriminator column.
- `analytics.py` queries lack a `session_type` filter.
- The prefill "last session" query does not filter by type.
- `equipment.usage_count` count drifts after logging cafe sessions.

**Phase to address:** Cafe Quick-Rate phase. The migration and analytics query updates are not optional cleanup — they must ship with the feature.

---

### v1.2-CAFE-2: Cafe Log "Prefill Fast Path" Pulls Irrelevant Data

**What goes wrong:**
The brew-session prefill logic resolves equipment, recipe, bag, and grind from the last session. A cafe quick-rate has none of these. If the prefill path is naively extended to the cafe form, it may pre-populate brew-specific fields (grinder, recipe) that have no meaning in a cafe context — and those "prefilled" nulls may be stored as intended values rather than omitted fields.

**How to avoid:**
- The cafe log form is a separate, simpler form — not the brew form with fields hidden. It should have: brand/name, origin (optional), brew method (select: espresso, filter, pour-over, etc.), rating, notes. No grind, no dose, no recipe, no equipment.
- Do not route cafe logs through the brew prefill resolver. They have their own prefill: repeat the last cafe's brand/name if it's a regular spot (useful for "same cafe, different coffee").
- Return `session_type` in the prefill fragment so the client knows which form context it's in.

**Warning signs:**
- The cafe form shares a Jinja template with the brew form, with fields conditionally hidden via Alpine.
- The cafe create route calls `resolve_prefill()` and discards most of the result.
- Brew-specific fields appear in the cafe database row with placeholder values.

**Phase to address:** Cafe Quick-Rate phase.

---

### v1.2-IMAGE-1: Prebuilt Image Bakes Secrets Into Layers

**What goes wrong:**
A developer runs `docker compose build` locally with a `.env` file present. The Dockerfile has `ARG DATABASE_URL` or `ARG SECRET_KEY`. The build-time arg value ends up in the image layer metadata. Anyone who pulls the image can run `docker history <image>` and read the secrets.

**How to avoid:**
- `.dockerignore` must exclude `.env*`. Verify with `cat .dockerignore | grep env`.
- No `ARG` for secrets in the Dockerfile. Secrets are runtime env vars only — never build-time.
- Add a CI step before push: `docker history ghcr.io/org/snobbery:latest --no-trunc | grep -i "secret\|key\|pass\|database"` → fail if any match.
- The published `docker-compose.yml` references only named env vars to be set by the operator — never default values for secrets.

**Warning signs:**
- `docker history <image>` output contains any of: `SECRET_KEY`, `DATABASE_URL`, `API_KEY`, `PASSWORD`.
- Dockerfile has `ARG SECRET_KEY` or equivalent.
- `.dockerignore` is missing or empty.

**Phase to address:** Self-Host Packaging phase. Secret audit is a blocking gate before any registry push.

---

### v1.2-IMAGE-2: Fresh Operator Hits /login, Not /setup — Can't Bootstrap

**What goes wrong:**
A new operator pulls the image, runs `docker compose up`, navigates to the app. If zero users exist, the app serves the login form (because `/` redirects to `/login` when not authenticated). The operator tries to log in, fails, and thinks the app is broken. They have no way to know about `/setup`.

**How to avoid:**
- When `setup_completed = false` in `app_settings`, the `/` route should redirect to `/setup` instead of `/login`. This is a one-line change in the existing `require_user` dependency or the root route handler.
- `entrypoint.sh` should log a startup message when setup is incomplete: `INFO: No users configured. Visit /setup to create the first admin account.`
- The README deploy section must include "First run: visit /setup before anything else" as the first step after `docker compose up`.
- Test this path explicitly: fresh volume + `docker compose up` → verify `/setup` is reachable and the redirect fires.

**Warning signs:**
- The root route only redirects authenticated users to `/`; unauthenticated users always see `/login`.
- No startup log message for setup_completed=false.
- README deploy section starts with "Log in" rather than "/setup."

**Phase to address:** Self-Host Packaging phase.

---

### v1.2-IMAGE-3: G-01 Class Bug Recurs — Root-Owned Volumes on Operator Deploy

**Prior art:** Snobbery already hit this. G-01 (STATE.md Deferred Items, still open): VPS named volumes were root-owned, blocking backup and photo writes. The Dockerfile was fixed to create app-owned mountpoints for fresh volumes, but this fix only applies to volumes created after the Dockerfile change. Existing volumes on the VPS predate the fix.

**What goes wrong:**
An operator runs `docker compose up` for the first time. If any volume was pre-created by a previous failed start (or by Docker's default initialization, which can run the container as root), the `/app/data` directory inside the container is owned by root. The app user cannot write backups or photos. The failure is silent — no error in the web UI, the backup scheduler logs a failure but continues.

**How to avoid:**
- Fix permanently in `entrypoint.sh`: before running alembic, check and fix ownership:
  ```bash
  chown -R app:app /app/data 2>/dev/null || true
  ```
  This requires the entrypoint to start as root and drop to the app user after the chown, via `exec gosu app uvicorn ...` or `su-exec`. This is the canonical fix for G-01 — not the Dockerfile `RUN chown` which only covers fresh volume creation.
- Add a startup health check: verify `/app/data/backups` and `/app/data/photos` are writable; log a WARN if not.
- G-01 is marked open in STATE.md. Closing it requires the entrypoint fix, not just documentation.

**Warning signs:**
- `entrypoint.sh` does not contain a runtime chown or ownership check.
- The backup scheduler logs failures but the app continues running (silent failure pattern).
- `ls -la /app/data` in the container shows `root root`.

**Phase to address:** Self-Host Packaging phase (v1.1 debt cleanup). G-01 closes only when the entrypoint runtime chown is shipped.

---

### v1.2-IMAGE-4: Migration Race on First Boot — Postgres Not Ready

**What goes wrong:**
`docker compose up` starts both containers simultaneously. The web container reaches `alembic upgrade head` before the db container has finished initializing a fresh Postgres data directory (5–15 seconds). Alembic fails with a connection error. uvicorn starts against an empty schema. Every request returns 500.

**How to avoid:**
- Add `depends_on: condition: service_healthy` for the web service in `docker-compose.yml`, with a healthcheck on the db service:
  ```yaml
  coffee-snobbery-db:
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 10
  coffee-snobbery:
    depends_on:
      coffee-snobbery-db:
        condition: service_healthy
  ```
- As a belt-and-suspenders backup, `entrypoint.sh` can also include a `pg_isready` wait loop — this helps operators using `docker run` directly without compose.

**Warning signs:**
- `docker-compose.yml` has `depends_on: coffee-snobbery-db` without `condition: service_healthy`.
- On first `docker compose up`, the web container exits immediately with a database connection error.

**Phase to address:** Self-Host Packaging phase.

---

### v1.2-IMAGE-5: Multi-Arch Image Missing — Breaks ARM Operators

**What goes wrong:**
The image is built on John's amd64 VPS and published as a single-arch manifest. Operators on Apple Silicon Macs or ARM VPSes (Hetzner ARM, AWS Graviton) either run under emulation (slow) or see a `no matching manifest` pull error.

The Tailwind CLI binary download in the Dockerfile is the only arch-sensitive step. The current Dockerfile likely hardcodes `tailwindcss-linux-x64`.

**How to avoid:**
- Use `docker buildx build --platform linux/amd64,linux/arm64` in the CI publish job.
- In the Dockerfile, use Docker's `TARGETARCH` build arg to select the correct Tailwind binary:
  ```dockerfile
  ARG TARGETARCH
  RUN ARCH=${TARGETARCH:-amd64}; \
      curl -fsSL "https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.17/tailwindcss-linux-${ARCH}" \
      -o /usr/local/bin/tailwindcss && chmod +x /usr/local/bin/tailwindcss
  ```
  Note: Tailwind uses `x64` not `amd64` in its binary names — map `amd64→x64`, `arm64→arm64`.
- Verify the multi-arch manifest after push: `docker manifest inspect ghcr.io/org/snobbery:latest` should show both digests.

**Warning signs:**
- Dockerfile has a hardcoded `tailwindcss-linux-x64` URL.
- Registry manifest has a single digest, not a manifest list.
- CI uses `docker build` not `docker buildx build`.

**Phase to address:** Self-Host Packaging phase. Multi-arch must be part of the initial image publishing setup.

---

### v1.2-IMAGE-6: Tailwind Glob Misses New Template Directories

**What goes wrong:**
The Dockerfile bakes the compiled Tailwind CSS at build time. New templates added for v1.2 (cafe quick-rate form, AI research page, reworked nav) live in new or existing directories. If `tailwind.config.js` content glob does not cover them, their utility classes are stripped from the compiled output. The feature looks correct in development (where Tailwind is run locally or CDN is used) but broken in the container.

**Why it happens:**
The glob `./app/templates/**/*.html` covers all subdirectories, so this is only a risk if templates are placed outside `app/templates/`. But it's worth verifying the glob also covers `*.js` files for Alpine component classes.

**How to avoid:**
- Keep the glob broad: `["./app/templates/**/*.html", "./app/static/js/**/*.js"]`. Verify it covers Alpine component files.
- Add a Dockerfile step that fails the build if the compiled CSS is suspiciously small: `wc -c app/static/css/tailwind.css | awk '$1 < 50000 { exit 1 }'` (adjust threshold based on current compiled size).
- Any phase that adds new templates must verify the glob catches them as an acceptance criterion.

**Warning signs:**
- Compiled `tailwind.css` is smaller after a build that added new templates.
- New UI elements appear unstyled in the container but styled in dev.
- Alpine component `.js` files use Tailwind classes that don't appear in the compiled CSS.

**Phase to address:** Every phase adding new templates. Glob audit belongs in the phase plan's acceptance criteria.

---

### v1.2-IA-1: Service Worker Serves Stale Nav After IA Restructure Deploy

**What goes wrong:**
Snobbery's service worker precaches the app shell including the nav. After deploying the IA restructure (Admin off bottom nav, new AI page added), installed PWA users get the old nav for days — Admin still visible, no AI tab — until they manually clear site data.

**Prior art:** Project memory documents: "Phase 13 C9 cache name bumps on template/CSS/JS content change (stage-1 COPY-gated), NOT every build; Python-only/no-op rebuilds don't bump (SWR backstops)." The existing content-deterministic cache versioning works, but only if template changes (including nav partial changes) actually change the baked CSS or SW cache string. If the IA change only modifies Python route handlers and Jinja template logic without touching any file that changes the compiled CSS, the SW cache key may not change.

**How to avoid:**
- Verify that the content-deterministic cache version string changes when `base.html` or the nav partial changes. If it only tracks CSS file content (not HTML), add a hash of the nav template to the version string.
- The safest approach: include a `CACHE_VERSION` based on a hash of all files that affect the shell (CSS + nav templates), regenerated at build time and injected into the SW file.
- After the IA deploy, add to the UAT checklist: install the old PWA on a test device, deploy, open the app, verify the new nav appears without a manual cache clear.
- Ensure the SW `activate` event deletes all caches except the current version — this evicts stale shells on the next tab open.

**Warning signs:**
- The SW cache version string is hardcoded, not content-derived.
- The nav partial is not included in the content hash used for SW versioning.
- No on-device PWA cache-busting test in the deploy checklist.

**Phase to address:** IA Restructure phase. Cache-busting verification is a required acceptance criterion.

---

### v1.2-IA-2: Nonce-CSP Blocks New AI Page Inline Scripts or HTMX Indicators

**What goes wrong:**
Adding a new AI page with HTMX progress indicators or Alpine components can re-trigger the nonce-CSP blocking issue Snobbery already hit. Project memory: "strict nonce-CSP previously blocked htmx's injected .htmx-indicator style; define it in tailwind.src.css or hx-indicator spinners show forever (Phase 9 backups stuck Running)."

The AI research page likely needs a progress indicator while the web-search call runs (15–30s). If implemented with `hx-indicator` and the `.htmx-indicator` style is not defined in the compiled CSS, the spinner shows permanently.

**How to avoid:**
- Verify `.htmx-indicator { display: none; }` and `.htmx-request .htmx-indicator { display: inline-flex; }` (or equivalent) are present in `tailwind.src.css`. The Phase 9 fix covers this, but verify it survives the v1.2 Tailwind rebuild.
- Every new `<script>` tag on the AI page must include `nonce="{{ csp_nonce }}"`. No exceptions.
- Any new Alpine `x-data` expression must not use patterns that require `unsafe-eval` beyond what Alpine already needs. The existing `unsafe-eval` in the CSP covers Alpine's expression compiler — but do not add `new Function` or `eval()` calls in custom JS.
- Add a CSP violation detection step to the AI page's acceptance criteria: open the page in a browser with DevTools, check the Console for any `Content Security Policy` errors.

**Warning signs:**
- HTMX indicators are always visible or always hidden on the AI page.
- Browser console shows CSP violations after adding a new `<script>` without a nonce.
- A new template includes `<script>` without `nonce="{{ csp_nonce }}"`.

**Phase to address:** AI Page phase and IA Restructure phase.

---

### v1.2-MOBILE-1: iOS Safe-Area Bug Spread by Rework (Unverified Prior Fix)

**What goes wrong:**
Snobbery committed an iOS safe-area fix (commit `982c0e6`) that is explicitly marked as UNVERIFIED on-device (project memory: "safe-area fix unverified — commit 982c0e6 iOS bottom-nav safe-area fix is committed but UNVERIFIED on-device"). Phase 13 reused the same unproven technique for a top safe-area fix. The v1.2 mobile-first rework will touch every screen — if the safe-area approach is wrong, it propagates the bug across all screens.

**How to avoid:**
- Treat on-device verification of the safe-area fix as a blocking prerequisite before the mobile rework begins. This is a single task: install the PWA on an iPhone, verify bottom nav and sticky form buttons do not overlap the home indicator.
- Document the verified CSS pattern in the `CLAUDE.md` Conventions section so every reworked screen uses it consistently.
- The correct pattern: `padding-bottom: env(safe-area-inset-bottom, 0px)` on the bottom nav wrapper. Note `env()` is only available in PWA standalone mode — not in plain Safari tab. Test in PWA mode, not browser.
- `constant()` (deprecated iOS 11 syntax) must not appear anywhere; use `env()` only.
- The rework phase acceptance criteria must specify on-device testing, not just DevTools responsive mode.

**Warning signs:**
- The rework phase starts without an on-device verification step for the existing safe-area fix.
- CSS uses `constant(safe-area-inset-bottom)` instead of `env(safe-area-inset-bottom)`.
- The acceptance criteria say "tested at 375px" without specifying physical device + PWA install.

**Phase to address:** Pre-rework: verify the safe-area fix on-device as a blocking task (own plan, own acceptance criterion). Mobile-First Rework phase: device testing in every screen's acceptance criteria.

---

### v1.2-MOBILE-2: Alpine |tojson Quoting Breaks New Templates

**What goes wrong:**
Project memory records: "`|tojson` MUST be in SINGLE-quoted attrs (it doesn't escape "); and how to mint an auth session + drive the live app in Edge/Playwright to repro Alpine/CSP/PWA bugs (a harness can hide them)."

New templates for cafe quick-rate (Alpine tag input for flavor notes) and AI research page (Alpine-driven state for progress/result display) will inject server-side data via `|tojson`. If any developer writes `x-data="{{ data|tojson }}"` (double-quoted outer attribute), the JSON double-quotes break the HTML attribute — silent Alpine parse failure, visible only in the browser.

**How to avoid:**
- Project convention (add to `CLAUDE.md` Conventions): all Alpine `x-data` attributes containing server-injected data MUST use single-quoted outer HTML attributes: `x-data='{{ data|tojson }}'`.
- Add a template linting check to CI: grep for the pattern `"x-data="{{ ` and fail if found.
- Playwright smoke tests must cover Alpine-driven interactions on the new pages — the test harness catches what unit tests miss.

**Warning signs:**
- New template has `x-data="{{ ... |tojson }}"` (double-quoted outer).
- Alpine `x-data` object appears correct in HTML source but Alpine logs a parse error in browser console.
- The feature passes all unit tests but fails in the browser.

**Phase to address:** Cafe Quick-Rate phase and AI Page phase. Convention enforcement before templates ship.

---

## 9. Top 5 — Most Critical (required reading for every planner)

Ranked by **likelihood × impact × difficulty to retrofit later**.

| Rank | Pitfall | Why It Matters Most |
|------|---------|---------------------|
| **1** | **AI-1: Web-search input-token cost dwarfs the per-search fee** | This is the cost story. The user has explicitly opted out of a token ceiling and is relying on signature-based regen alone. Without `max_uses` caps (also COST-5), per-search token counts, and visible warnings in the admin panel, a single AI run can balloon to 100k+ input tokens. Retrofitting cost telemetry after the first surprise bill is painful. **Build cost observability into `ai_recommendations` schema from the first migration**, not later. |
| **2** | **v1.2-AI-1: On-demand research removes the cadence gate** | Adding an on-demand research button without a DB cache + per-user rate limit turns a bounded cost model into an unbounded one. At 10 calls/user/day × 2 users × web-search cost, the bill can surprise. The cache table and slowapi decorator must be in the initial plan, not a follow-up. |
| **3** | **v1.2-CAFE-1: Cafe sessions pollute brew analytics** | Without a discriminator column in the migration, every analytics query and the AI signature generator will include cafe sessions in brew-specific computations. Retrofitting this after data is in production requires a data migration. The discriminator must be part of the schema from day one. |
| **4** | **v1.2-IMAGE-3: G-01 class root-volume bug (still open)** | G-01 is marked open in STATE.md. The Dockerfile fix only covers fresh volumes. An operator on a system with pre-existing root-owned volumes will hit silent backup and photo-write failures. The entrypoint runtime chown is the correct fix — it must ship with the prebuilt image. |
| **5** | **v1.2-MOBILE-1: Unverified safe-area fix spread by rework** | The existing safe-area fix has never been verified on-device. The mobile-first rework will apply the same pattern to every screen. If the fix is wrong, the bug is now everywhere. Verifying it on a physical device before the rework starts is a cheap, mandatory prerequisite. |

---

## Sources

- [Anthropic Web Search Tool — official docs](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/web-search-tool)
- [Anthropic API Pricing 2026 — Finout breakdown](https://www.finout.io/blog/anthropic-api-pricing)
- [Using Anthropic's Web Search with Instructor](https://python.useinstructor.com/blog/2025/05/07/using-anthropics-web-search-with-instructor-for-real-time-data/)
- [OpenAI Web Search Guide](https://platform.openai.com/docs/guides/tools-web-search)
- [How Often Do AI Assistants Hallucinate Links? — Ahrefs](https://ahrefs.com/blog/how-often-do-ai-assistants-hallucinate-links/)
- [HTMX Docs](https://htmx.org/docs/)
- [HTMX CSRF Issue Discussion](https://github.com/bigskysoftware/htmx/issues/70)
- [HTMX and CSP — Sjoerd Langkemper](https://www.sjoerdlangkemper.nl/2024/06/26/htmx-content-security-policy/)
- [APScheduler User Guide](https://apscheduler.readthedocs.io/en/3.x/userguide.html)
- [PWA on iOS — Brainhub 2025 guide](https://brainhub.eu/library/pwa-on-ios)
- [PWA iOS Limitations 2026 — MagicBell](https://www.magicbell.com/blog/pwa-ios-limitations-safari-support-complete-guide)
- [16px or Larger Prevents iOS Zoom — CSS-Tricks](https://css-tricks.com/16px-or-larger-text-prevents-ios-form-zoom/)
- [Screen Wake Lock API — MDN](https://developer.mozilla.org/en-US/docs/Web/API/Screen_Wake_Lock_API)
- [SQLAlchemy QueuePool Exhaustion — FastAPI Discussion #10450](https://github.com/fastapi/fastapi/discussions/10450)
- [Docker PostgreSQL Permission Guide](https://www.w3tutorials.net/blog/permission-issue-with-postgresql-in-docker-container/)
- [Fernet symmetric encryption — pyca/cryptography](https://cryptography.io/en/latest/fernet/)
- [MultiFernet key rotation](https://www.geeksforgeeks.org/multifernet-module-in-python/)
- [PWA Cache Invalidation — Infinity Interactive](https://iinteractive.com/resources/blog/taming-pwa-cache-behavior)
- Snobbery project memory (authoritative, project-specific): G-01 root-volume incident, service-worker staleness pattern, nonce-CSP/htmx-indicator incident, safe-area unverified fix, `|tojson` Alpine quoting requirement, Phase 13 C9 content-deterministic SW cache, test-isolation gaps
- Snobbery `.planning/PROJECT.md` Key Decisions and Known Gaps
- Snobbery `.planning/STATE.md` Deferred Items: G-01 (open), T-INFRA-1 (open)
