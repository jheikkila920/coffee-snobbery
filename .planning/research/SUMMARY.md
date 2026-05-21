# Research Synthesis — Snobbery

**Synthesized:** 2026-05-16
**Sources:** STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md, PROJECT.md

---

## 1. TL;DR — Highest-Leverage Findings

1. **Three foundational data-model gaps must be decided in Foundation, not later.** Bag-as-instance (separate from coffee catalog), brew-yield + ratio + optional TDS columns, and a wishlist table. All cheap now; all painful migrations once there are 500+ sessions. Without bag-as-instance, sweet-spots-by-roast-date is unreliable as soon as anyone reorders a bean.
2. **Cost observability must be schema-baked from the first AI migration.** The user opted out of a token ceiling, leaving signature-based regen as the *only* cost control. `ai_recommendations` must persist `web_search_count`, `input_tokens_search`, `tokens_used`, `provider_used`, `model_used`, `tool_version`, `input_signature` — retrofitting after the first surprise bill is the painful path.
3. **The spec's "restrictive CSP, no inline scripts" is incompatible with Alpine + Tailwind CDN + HTMX `hx-on:`.** This needs a documented trade-off *before* the security-hardening phase. Recommended resolution: Alpine CSP build + Tailwind standalone CLI binary in the Dockerfile (no npm), nonce-based CSP, forbid `|safe` in templates. If CDN Tailwind is kept, `unsafe-inline` for styles becomes permanent.
4. **One uvicorn worker is non-negotiable.** APScheduler in-process and module-level in-memory AI locks both require single-process. Document loudly in README so a future `--workers 4` for "performance" doesn't silently fire every nightly job four times.
5. **Build order is rigid for the first 7 phases; flexible after.** Middleware before routes, auth before features, encryption + settings before AI, catalog before sessions, sessions before analytics, analytics before AI, AI before scheduler. Search, PWA, admin slot in later with fewer dependencies.
6. **Stack pins are clean but two spec items are stale.** HTMX 1.9 → use 2.x. Tailwind CDN → use standalone CLI binary baked into Dockerfile. OpenAI SDK is on 2.x with Responses API, not Chat Completions.
7. **iOS is the source of nearly every mobile pitfall.** 16px+ font on inputs (else zoom-and-stick), Wake Lock re-acquire on `visibilitychange`, localStorage 7-day ITP eviction, install banner is mandatory because iOS never prompts, `capture="environment"` opens an action sheet, maskable icons for Android.
8. **CSRF + HTMX needs double-submit-cookie, not rotated-per-request tokens.** Rotated tokens break on the second HTMX POST because fragments don't update `<body>` `hx-headers`. Pick at Phase 1 — refactoring later means touching every form.

---

## 2. Stack Decisions

| Item | Status | Decision / pin |
|---|---|---|
| Python | Locked | 3.12 |
| FastAPI | Locked | `>=0.136,<0.137` — lifespan only |
| Starlette | Locked | `>=1.0,<2.0` |
| Uvicorn | Locked | `>=0.47,<0.48`, `--workers 1 --proxy-headers --forwarded-allow-ips=<trust list>` |
| SQLAlchemy | Locked | `>=2.0.49,<2.1` (2.1 still beta) |
| Postgres driver | Locked | `psycopg[binary]>=3.3,<3.4`, URL `postgresql+psycopg://` |
| Postgres server | Locked | 16; install `postgresql-client-16` in web image for `pg_dump` version match |
| Pydantic | Locked | `>=2.13,<3.0` |
| HTMX | Decided, deviates from spec | **2.0.x**, not 1.9; `htmx-ext-sse@2.2.4` separately if SSE |
| Tailwind | Decided, deviates from spec | **Standalone CLI binary in Dockerfile**, not CDN (v4 Play CDN forces `unsafe-inline`) |
| Alpine.js | Locked, caveat | 3.x — **CSP build** (`alpinejs/dist/cdn.csp.min.js`) |
| CSRF | Locked | `starlette-csrf>=3.0,<4`, double-submit-cookie |
| Session store | Locked, hand-rolled | ~80 LOC custom middleware + `sessions` table; not Starlette stock |
| Rate limiting | Locked | `slowapi>=0.1.9,<0.2`, single-worker only |
| Logging | Locked | `structlog>=25.5,<26` + stdlib `ProcessorFormatter` |
| AI SDKs | Locked, fast-moving | `anthropic>=0.102,<1.0`, `openai>=2.37,<3.0` (Responses API) |
| Web search tool versions | Decided | `web_search_20250305` at v1; via `app_settings` for swap-without-redeploy; `max_uses=5`/`=3` |
| Image processing | Locked | Pillow `>=12.2,<13` + manual magic-byte check |
| Encryption | Locked | `cryptography>=48,<49`, **`MultiFernet` from day 1** |
| Scheduler | Locked | `APScheduler>=3.11,<4` `AsyncIOScheduler`, `misfire_grace_time=3600`, `coalesce=True`, `max_instances=1`, **`SQLAlchemyJobStore`** |
| Tests | Locked | `pytest>=9.0,<10` + `pytest-asyncio` + `respx` + `playwright>=1.59,<2` |
| Lint/format | Locked | `ruff>=0.15.13,<0.16` |
| Type checker | Locked, revisit | mypy `>=1.13,<2`; revisit `ty` next milestone |
| PWA tooling | Locked, hand-rolled | Static manifest + ~60 LOC SW; no Workbox |
| SSE vs polling for AI | Deferred to Phase 7 | Recommend polling first; SSE = v1.1 polish |
| Search: FTS vs trigram | Deferred to Phase 10 | Both pure-Postgres; prototype both |

---

## 3. Schema Decisions to Make in Foundation Phase

**The first migration set should reflect all of these**, even if v1 UI exposes them minimally.

### 3.1 Bag-as-instance (FEATURES gap #1)

```
bags
├── id (uuid)
├── coffee_id (fk -> coffees.id)
├── roast_date (date, nullable)
├── weight_grams (numeric, nullable)
├── opened_at, finished_at (timestamp, nullable)
├── notes (text, nullable)
└── created_at, updated_at
```

`brew_sessions.bag_id` (FK to bags) is the right grain; `coffee_id` derives via the bag. Roast freshness analytics use `bag.roast_date`, never `coffee.roast_date`.

### 3.2 Wishlist (FEATURES gap #2)

```
wishlist_entries
├── id (uuid)
├── user_id (fk)
├── coffee_id (fk -> coffees.id, nullable)
├── url (text, nullable)
├── name (text — required if no coffee_id)
├── note (text, nullable)
├── source ('manual' | 'ai_recommendation')
└── created_at
```

AI coffee-rec card → "Add to wishlist" closes the loop on the differentiator.

### 3.3 Brew yield / TDS on `brew_sessions` (FEATURES gap #3)

Already on `brew_sessions`: `dose_grams_actual`, `water_grams_actual`. Add:
- `yield_grams_actual` (numeric, nullable)
- `tds_pct` (numeric, nullable)
- `extraction_yield_pct` (numeric, nullable; can be a `GENERATED` column = `(yield_g * tds_pct) / dose_g`)

Ratio (1:N) is purely derived in the UI via Alpine reactivity — **no schema column**.

### 3.4 AI cost-observability columns

```
ai_recommendations
├── id, user_id, recommendation_type
├── input_signature (text, indexed)
├── response_json (jsonb)
├── provider_used ('anthropic' | 'openai')
├── model_used (text)
├── tool_version (text)         -- e.g. 'web_search_20250305'
├── tokens_input (int)
├── tokens_output (int)
├── tokens_input_search (int)
├── web_search_count (int)
├── url_verified (bool, nullable)
├── duration_ms (int)
├── generated_at, generated_by ('scheduler' | 'manual_refresh')
└── error_status (text, nullable)
```

Also feeds the admin "last AI run status" banner (COST-3 fix).

### 3.5 `sessions` table (architecture-mandated)

```
sessions
├── id (uuid PK — cookie value)
├── user_id (fk)
├── csrf_seed (text, optional)
├── created_at, last_seen, expires_at
└── user_agent (text, nullable)
```

Required for 30-day expiry with refresh-on-activity, admin session-count view, session-ID regeneration on login (SEC-3).

### 3.6 `app_settings` seed rows

Seed in first migration:
- `recommendation_region` = `US`
- `min_sessions_for_ai` = `3`
- `min_flavor_notes_for_ai` = `5` (AI-7)
- `ai_primary_max_searches` = `5`
- `ai_broadened_max_searches` = `3`
- `anthropic_web_search_tool_version` = `web_search_20250305`
- `openai_web_search_tool_version` = `web_search`
- `setup_completed` = `false` (SEC-5)

---

## 4. Cross-Cutting Concerns by Phase

| Concern | Origin | Lands in phase |
|---|---|---|
| Single uvicorn worker; document loudly | ARCH §5.2, PITFALLS AI-6, SH-2 | 0 (Dockerfile, entrypoint, README) |
| Postgres extensions (citext, pg_trgm, unaccent) | STACK §1, ARCH map | 0 (first migration) |
| Proxy-headers + trust list; `Secure` cookie depends on it | ARCH §4.1, SH-6 | 0 + 1 |
| CSP trade-off (Alpine CSP build + Tailwind CLI + forbid `\|safe`) | SEC-1, ARCH §4.5 | 1 (decide before templates) |
| Double-submit-cookie CSRF | HX-1, ARCH §4.5 | 1 |
| `MultiFernet` from day 1 | SEC-2 | 3 |
| `setup_completed` + `SELECT FOR UPDATE` on /setup | SEC-5 | 2 |
| Session-ID regeneration on login/logout/privilege change | SEC-3 | 2 |
| 16px+ font-size on every form input + Playwright assertion | MX-1 | 5 |
| LocalStorage draft keys namespaced by user_id | MX-5 | 5 |
| Tap-on-stars rating (not native range) | MX-6, FEATURES §1 | 5 |
| Live ratio computation in form | FEATURES gap | 5 |
| Staggered lazy-load on home + connection-pool sizing | HX-5, SH-2 | 6 |
| AI cost telemetry columns + `max_uses` + 5-min manual-refresh throttle | AI-1, COST-2, COST-5 | 7 |
| Citation-block projector before Pydantic validation | AI-3 | 7 |
| URL verification: ranged GET, real UA, body-contains-name | AI-2 | 7 |
| Fallback only on non-retryable errors; `max_retries=1` on SDKs | AI-4 | 7 |
| Tool version as `app_settings` row, not hardcoded | AI-5 | 7 |
| Content-hash signature; drop shared `equipment_count`/`recipe_count` | COST-1, COST-4 | 7 |
| Postgres advisory lock alongside in-memory lock | AI-6 | 7 |
| APScheduler config (`SQLAlchemyJobStore`, grace=3600, coalesce, max_instances=1) | SH-1, ARCH §5.4 | 8 |
| `postgresql-client-16` in web image | SH-5 | 0 or 8 |
| `/sw.js` served from root with `Service-Worker-Allowed: /` | PWA-3, ARCH §4.6 | 11 |
| `start_url: "/?source=pwa"` returns 200 (no redirect) | PWA-2 | 11 |
| Dual light/dark `theme-color` meta + maskable icons | PWA-5, PWA-6 | 11 |
| iOS install banner (iOS never prompts) | PWA-1 | 11 |
| Wake Lock re-acquire on `visibilitychange` + indicator + iOS fallback | MX-4, FEATURES §1 | 11 |
| Server-side draft autosave on blur (iOS ITP belt-and-suspenders) | FEATURES §1 | 5 or 11 |
| `Cache-Control: no-store` + `Vary: HX-Request` on fragment routes | HX-2 | 4+ (codify in router base helpers) |
| CI grep test: forbid `\|safe` in `templates/pages/` | HX-6 | 12 |

---

## 5. Hard Ordering Constraints

1. Middleware (Phase 1) before any router. Routers depend on `request.state.user`, CSRF, CSP nonce.
2. Custom SessionMiddleware before `/login` exists.
3. `sessions` table migration before SessionMiddleware tests pass (same Phase 1).
4. `MultiFernet` encryption service before `api_credentials` table — else first encrypted row is single-key.
5. `api_credentials` (Phase 3) before `ai_service` (Phase 7).
6. `app_settings` (Phase 3) before `ai_service` — service reads region, tool versions, max_uses, min_sessions_for_ai.
7. Shared catalog (Phase 4) before `brew_sessions` (Phase 5) — FK dependencies.
8. `bags` (Phase 4) before `brew_sessions` (Phase 5) — sessions FK `bag_id`; backfill later has no source of truth for roast date.
9. `brew_sessions` (Phase 5) before `analytics` (Phase 6).
10. `analytics` (Phase 6) before `ai_service` (Phase 7) — AI consumes profile-derivation queries and signature compute.
11. `ai_recommendations` table (Phase 7) before scheduler (Phase 8) — nightly job writes it.
12. `ai_service` (Phase 7) before `nightly_ai_refresh` job (Phase 8).
13. Scheduler (Phase 8) before backup admin UI (Phase 9) — admin reads job status the scheduler populates.
14. CSP design (Phase 1) before any template uses Alpine or HTMX `hx-on:` (Phase 2+).
15. Tailwind decision (Phase 0) before any template uses Tailwind classes (Phase 2+).
16. `postgresql-client-16` in web image (Phase 0) before backup job runs (Phase 8).
17. PWA (Phase 11) after most UI exists (Phases 5–6 min) — else cache churns with templates.

---

## 6. Top 10 Pitfalls (Filtered)

| # | Pitfall | Phase | Mitigation (one-liner) |
|---|---|---|---|
| 1 | AI-1: web-search input tokens dominate the bill | 7 | Persist token/search counts in `ai_recommendations`; `max_uses=5/3`; admin warn at >50k tokens/run |
| 2 | SH-1: APScheduler misses nightly jobs after restart | 8 | `SQLAlchemyJobStore` + grace=3600 + coalesce; start in `lifespan` |
| 3 | SEC-1: strict CSP incompatible with Alpine + Tailwind CDN + HTMX `hx-on:` | 1 | Alpine CSP build, Tailwind CLI (no CDN), forbid `\|safe`; document any residual `'unsafe-eval'` in `docs/decisions/` |
| 4 | HX-1: CSRF token rotation breaks HTMX on 2nd POST | 1 | Double-submit-cookie pattern |
| 5 | MX-1: iOS Safari auto-zoom on form focus, stays zoomed | 5 | Global CSS `input,select,textarea { font-size: 16px; }`; Playwright assertion |
| 6 | AI-2: hallucinated/blocked product URLs verify wrong | 7 | Ranged GET, realistic UA, body-contains-name check, no cross-host redirects |
| 7 | COST-4: shared `equipment_count`/`recipe_count` in signature → 2× bill | 7 | Drop those fields; content-hash of user's own sessions only |
| 8 | SEC-3: session not regenerated on login → fixation | 2 | Delete old session row, mint new ID on every login/privilege change |
| 9 | PWA-3: service worker scope too narrow under `/static/` | 11 | Serve `/sw.js` from root with `Service-Worker-Allowed: /` |
| 10 | SH-6: `X-Forwarded-Proto` not honored → Secure cookie dropped → redirect loop | 0 + 1 | `uvicorn --proxy-headers --forwarded-allow-ips=<trusted>`; `/debug/proxy` smoke check |

Honorable mentions to flag in their phase: HX-5 (lazy-load thundering herd), COST-1 (signature collision), MX-4 (wake lock not re-acquired), PWA-7 (SW caching itself), SEC-4 (polyglot image upload), SEC-2 (Fernet key rotation orphans data), AI-6 (advisory-lock backstop).

---

## 7. Open Questions for Roadmap Creator

1. **Include `bags` table in v1 Foundation?** Strong recommend yes; deviates from spec's single-row coffee model. Needs John sign-off.
2. **Wishlist in v1?** Recommend yes — landing pad for the AI coffee rec.
3. **TDS / yield columns in v1?** Recommend yes — 2 nullable + 1 derived; signals audience awareness.
4. **CSV import alongside export in v1?** Recommend yes, scope-limited to "import sessions; refuse if coffee not in catalog." Day-1 data unlocks AI.
5. **SSE or polling for AI streaming?** Recommend polling for v1; SSE v1.1 polish.
6. **Tailwind CLI in Dockerfile** (not CDN) — needs sign-off because it deviates from spec wording.
7. **HTMX 2.x vs 1.9** — recommend 2.x; needs sign-off because spec wording ("1.9+") predates 2.x stable.
8. **Onboarding seed for cold start?** AI gates at ≥3 sessions + ≥5 distinct flavor notes. Decide: "Add 3 sample brews" UI, CSV import, or accept the cliff.
9. **Lock down the Alpine CSP trade-off in Phase 1.** Phase 1 planner should prototype intended Alpine directives against the CSP build to confirm `'unsafe-eval'` can be avoided.
10. **Admin "API health" panel scope.** Not in spec; required to surface AI failures (COST-3, AI-5). Recommend Phase 9.
11. **Server-side draft autosave-on-blur in v1?** Spec defers offline writes; iOS ITP 7-day eviction creates a real but narrow data-loss path for non-installed iOS users. Cheap belt-and-suspenders if added in Phase 5.

---

## Confidence Summary

| Area | Confidence | Notes |
|---|---|---|
| Stack pins | HIGH | PyPI authoritative as of 2026-05-16 |
| HTMX 2.x deltas | HIGH | Official migration guide |
| Tailwind CDN/CLI trade-off | MEDIUM | Production warning firm; operational impact judgment |
| Anthropic/OpenAI tool versions | HIGH | Verified against official docs |
| Feature gaps (bag, wishlist, yield/TDS) | HIGH | Multiple shipping competitors confirm |
| iOS PWA limits (ITP, Wake Lock, install, capture) | HIGH | MDN + WebKit bugs corroborated |
| Architecture component boundaries | HIGH | FastAPI/Starlette/uvicorn docs |
| Build-order DAG | MEDIUM | Defensible but judgment-based |
| SSE vs polling | MEDIUM | Genuine trade-off |
| Slowapi as rate-limit pick | MEDIUM | Works widely; no recent releases — yellow flag |
| AI cost-telemetry necessity | HIGH | Anthropic billing semantics + Ahrefs hallucination data |

---

## Suggested Phase Count

**13 phases** (mirrors ARCHITECTURE.md DAG).

**Research flags — needs deeper per-phase research:** Phase 1 (CSP/Alpine prototype), Phase 7 (AI service — SSE vs polling, URL verification approach, citation-block projection), Phase 10 (Search — FTS vs trigram prototype), Phase 11 (PWA on iOS — Wake Lock fallback testing).

**Standard patterns — skip dedicated phase research:** Phase 0 (Docker/Compose), Phase 2 (auth), Phase 4 (CRUD), Phase 8 (APScheduler + pg_dump), Phase 9 (admin CRUD).
