# Technology Stack — Snobbery

**Project:** Snobbery (self-hosted household coffee log)
**Researched:** 2026-05-16
**Overall confidence:** HIGH for pinned versions and well-documented gaps; MEDIUM for HTMX 2 vs 1.9 trade-off and rate-limit library choice.

The stack is locked by the original spec. This document pins **specific versions** for each named library at the time of research, names a **single recommendation** for every gap the spec leaves open, and flags compatibility traps.

---

## 1. Pinned Stack — Current Versions

All versions verified against PyPI / official sources on 2026-05-16. Pin to the listed minor and accept patch upgrades; pin both lower and upper bounds in `pyproject.toml` to keep migrations predictable.

| Library | Pin to | Latest as of | Caveat / note |
|---|---|---|---|
| **Python** | `3.12` | 3.13 GA, 3.14 released | Stay on 3.12 — Pillow 12, psycopg 3.3, and ruff all support it; jumping to 3.13/3.14 buys nothing for this app and risks build-image churn. |
| **FastAPI** | `>=0.136,<0.137` | 0.136.1 (Apr 23 2026) | Use `lifespan` async context manager **only** — `@app.on_event("startup"/"shutdown")` is deprecated upstream in Starlette and will be removed. |
| **Starlette** | `>=1.0,<2.0` | 1.0.0 (Mar 22 2026) | Starlette went 1.0 in March 2026 — first stable major. FastAPI 0.136 already depends on 1.0.x. |
| **Uvicorn** | `>=0.47,<0.48` | 0.47.0 (May 14 2026) | Use `--proxy-headers` and `--forwarded-allow-ips` from `TRUSTED_PROXY_IPS` for the NGINX trust requirement. |
| **SQLAlchemy** | `>=2.0.49,<2.1` | 2.0.49 stable; 2.1.0b2 in beta | **Stay on 2.0.x.** 2.1 is still beta (b2, Apr 16 2026). Use typed `Mapped[...]` columns and `select()` everywhere — no legacy `Query` API. |
| **Alembic** | `>=1.18,<2.0` | 1.18.4 (Feb 10 2026) | Matches SQLAlchemy 2.0 native; autogenerate handles `Mapped[...]` correctly. |
| **PostgreSQL (server)** | `16` (postgres:16-alpine) | 17 is GA | Stay on 16 per spec lock. Citext, trigram (`pg_trgm`), and `tsvector` FTS all available. Run `CREATE EXTENSION` in the first migration. |
| **Postgres driver** | `psycopg[binary]>=3.3,<3.4` | 3.3.4 (May 1 2026) | Use **psycopg 3**, not psycopg2. SQLAlchemy 2.0 supports both; psycopg 3 has native async, modern packaging (`psycopg[binary]`), and is actively developed. Connection URL: `postgresql+psycopg://...`. |
| **Pydantic** | `>=2.13,<3.0` | 2.13.4 (May 6 2026) | v2 only. Use `model_validate`, `model_dump`, `Field(..., ge=..., le=...)` for the numeric range enforcement in forms. |
| **pydantic-settings** | `>=2.14,<3.0` | 2.14.1 (May 8 2026) | All env reads go through one `Settings` class. No `os.environ` calls elsewhere. |
| **argon2-cffi** | `>=25.1,<26` | 25.1.0 (Jun 3 2025) | CalVer'd in 2025. Defaults are sane; explicitly set memory_cost=64*1024, time_cost=3, parallelism=4 per spec. |
| **cryptography** | `>=48,<49` | 48.0.0 (May 4 2026) | Provides `cryptography.fernet.Fernet`. Pin upper bound — major version bumps occasionally remove deprecated primitives. |
| **itsdangerous** | `>=2.2,<3.0` | 2.2.0 (Apr 16 2024) | Stable, low-velocity. Used by both your session cookie signing and Starlette `SessionMiddleware`. |
| **Jinja2** | `>=3.1.6,<4` | 3.1.6 (Mar 5 2025) | Autoescape ON globally. Never `|safe` user content. |
| **httpx** | `>=0.28,<0.29` | 0.28.1 (Dec 6 2024) | Used for the URL HEAD-check validation step. Wrap in a 5s timeout. Note: 0.28 is the *last* 0.x line; httpx 1.0 has not shipped — pin tight. |
| **Pillow** | `>=12.2,<13` | 12.2.0 (Apr 1 2026) | Used for magic-byte decode validation + thumbnail + EXIF strip. Major-version cadence is annual; lock upper bound. |
| **APScheduler** | `>=3.11,<4` | 3.11.2 (Dec 22 2025); 4.0.0a6 in alpha | **Stay on 3.x.** 4.x is alpha and rewrites the API. 3.11 supports asyncio scheduler in-process — what you want. |
| **anthropic (SDK)** | `>=0.102,<1.0` | 0.102.0 (May 13 2026) | Web search tool supported (see §4). Anthropic SDK has been on a fast 0.x cadence — be willing to bump frequently. |
| **openai (SDK)** | `>=2.37,<3.0` | 2.37.0 (May 15 2026) | OpenAI SDK is now in the **2.x line**. The Responses API (not Chat Completions) is the path for the web search tool. |
| **python-multipart** | `>=0.0.28,<0.1` | 0.0.28 (May 10 2026) | Required by FastAPI for form parsing (photo upload, every CSRF-protected POST). Always installed; pin to current. |
| **HTMX (CDN)** | **2.0.x** — current is 2.0.10 | 2.0.10 | See §4 and §3. The spec says "1.9+" but **2.x is the current line** and is production-ready. Pick 2.x for a greenfield build. Plan for the small migration deltas below. |
| **Alpine.js (CDN)** | `3.x` — current is 3.16.0 | 3.16.0 (Apr 2026) | Defer-load: `<script defer src="https://unpkg.com/alpinejs@3.16.0/dist/cdn.min.js">`. |
| **Tailwind (CDN)** | See §3 — **the spec's "Tailwind CDN, no build pipeline" is in tension with Tailwind v4** | Play CDN is v4, but the docs say "**not for production**" | See §3. The honest answer is: Play CDN is fine for a household-scale app at v1; switch to the standalone CLI binary (no npm) if/when bundle size or CSP nonces become a problem. |

---

## 2. Gap Libraries — Recommendations

Each gap has a single recommendation. Alternatives considered are listed for traceability — do not use them.

| Gap | Recommendation | Pin | Rationale | Alternatives rejected |
|---|---|---|---|---|
| **CSRF protection** | `starlette-csrf` (CSRFMiddleware via `app.add_middleware`) | `>=3.0,<4` | Pure ASGI middleware, double-submit-cookie, single line to install, **token via cookie + header** is exactly what HTMX needs — emit the token on every response in a cookie, expose it on the page via a `<meta name="csrf-token">`, configure HTMX globally with `htmx.config.requestClass` or `hx-headers='{"X-CSRF-Token": "..."}'` from a base template. Doesn't need to know about HTMX. | **`fastapi-csrf-protect`** (1.0.7, Sep 2025) — works but requires per-route `Depends`, more verbose for a templated app with dozens of forms. Use `starlette-csrf` middleware for a single global enforcement point. |
| **Session storage (table-backed per spec)** | Hand-roll a small Starlette middleware backed by a `sessions` SQLAlchemy table. Signed cookie holds session ID only; server side stores `{user_id, csrf_seed, last_seen, expires_at}`. | n/a (own code) | The spec explicitly requires a table-backed session store. Starlette's stock `SessionMiddleware` is **cookie-only** (stores serialized data in the cookie itself). For 30-day expiry, server-side rotation on activity, and an admin "session count" view, you must persist server-side. ~80 LOC of middleware + a model. | **`starlette-session-middleware`** PyPI package — niche, low star count, do not depend on it. **Redis-backed sessions** — adds a service that's otherwise unnecessary at household scale. |
| **Rate limiting (login: 5/IP/15min)** | `slowapi` | `>=0.1.9,<0.2` | Used widely in FastAPI production. In-memory limiter is sufficient at household scale (one uvicorn worker recommended for this app anyway — see §3). Decorator-based, integrates cleanly with FastAPI dependency injection. | **`fastapi-limiter`** — requires Redis. Overkill. **`fastapi-throttle`** — newer, smaller user base. **Hand-rolled** — fine but slowapi's `@limiter.limit("5/15minutes")` is shorter than re-implementing it. Note: slowapi self-describes as "alpha" but is in widespread production use; treat its API as stable. |
| **Structured logging** | `structlog` | `>=25.5,<26` | The spec requires audit-friendly logging for auth + admin events. `structlog`'s processor chain makes redaction (passwords, API keys, session tokens, request bodies) explicit and testable. Route it through stdlib `ProcessorFormatter` so uvicorn/FastAPI/SQLAlchemy logs merge cleanly into the same JSON output. | **`loguru`** — easier setup but its model fights stdlib (FastAPI + uvicorn + SQLAlchemy all use stdlib), creating two log formats. **stdlib `logging` alone** — works but you'll re-implement structlog's redactors. |
| **HTML sanitization** | **Not needed at v1.** | — | Every user-supplied text field is rendered through Jinja2 with autoescape ON. No field allows HTML input. No rich-text editor. No imported coffee descriptions from external sources rendered as HTML. If/when AI prose output is rendered, render it as plain text with `<br>` for line breaks — do **not** allow HTML through. If a future feature needs to allow Markdown, add **`markdown-it-py` + `mdit-py-plugins`** (actively maintained) — not `bleach` (deprecated since 2023, still receiving releases but officially EOL'd by Mozilla). |
| **Image processing** | `Pillow` (already pinned in §1). | — | Magic-byte check via `imghdr` replacement (`puremagic` or `filetype`) **before** Pillow decode. Use `filetype>=1.2` if you want stricter MIME inference; otherwise `Pillow.Image.open()` + `.verify()` + `.convert()` is sufficient. Recommendation: just use Pillow + manual signature check on the first 8 bytes — no extra dep. |
| **PWA tooling (manifest + service worker)** | **Hand-rolled.** Static `manifest.json` + ~60 LOC service worker doing precache-on-install + stale-while-revalidate on the app shell. | — | Workbox is overkill for an app shell + cache-then-network read use case. Workbox shines when you have complex routing, background sync, or push notifications — you have none of those (v1 explicitly defers offline writes). Use the [MDN service worker offline cookbook](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Offline_Service_workers) pattern. For manifest icons, generate 192/512 + maskable via [PWA Image Generator](https://www.pwabuilder.com/imageGenerator) once and check in. | **Workbox** (`workbox-sw` CDN) — fine but adds a third frontend dependency for ~30 LOC of cache logic you'd write anyway. **`vite-plugin-pwa`** — requires npm, violates the stack lock. |
| **Test runner** | `pytest` + `pytest-asyncio` + `httpx.AsyncClient` for in-process FastAPI testing. Use FastAPI's `TestClient` (which wraps httpx) for sync tests. | pytest `>=9.0,<10` | pytest 9.0 (Apr 2026) is the current line. Test the FastAPI app in-process — no need for live uvicorn. Use a transactional rollback fixture so each test starts with a clean DB. | `unittest` — verbose, no fixtures. `pytest-httpserver` — for outbound calls you'd rather mock with `respx`. |
| **HTTP mocking (for AI/HEAD-check tests)** | `respx` | latest | Drop-in mock for httpx. Mock the AI provider HTTP calls *and* the URL HEAD validation step without a network. | `responses` (works on `requests` only), `vcr.py` (cassette-based, brittle for AI output that varies). |
| **Browser/responsive smoke test** | `playwright` (Python) at 375×667 and 390×844 | `>=1.59,<2` | Spec explicitly calls for it. One file: spin up the docker stack, log in, navigate the four primary pages, assert no horizontal scroll and bottom-nav visibility. Headed in dev, headless in CI. | Selenium — slower, flakier, larger driver footprint. |
| **Linter / formatter** | `ruff` (lint + format) | `>=0.15.13,<0.16` | Replaces black + isort + flake8 + parts of pylint with one tool. `ruff format` for formatting, `ruff check` for linting. Lock down a `ruff.toml` early. | black + isort separately — extra deps for no gain. |
| **Type checker (CI)** | `mypy` or **`ty` (Astral, type-checker, beta)** — pick mypy for now | mypy `>=1.13,<2` | mypy is the boring correct choice. ty is faster but still beta as of mid-2026; revisit at the next milestone. | pyright — works fine but adds a Node dependency for CLI use. |
| **Coverage (optional but recommended for the critical-path units)** | `pytest-cov` | latest | Cover `ai_service.py` signature logic, `encryption.py` round-trip, `analytics.py` queries, and CSRF middleware specifically — per spec's test posture. |  |
| **SSE (server-side, for AI streaming)** | `sse-starlette` | latest 2.x | FastAPI/Starlette-native, async generator → SSE stream, integrates with the HTMX SSE extension (`htmx-ext-sse@2.2.4`) on the client. | Hand-rolled `StreamingResponse` — works but reinventing keepalive + reconnect. |
| **HTMX SSE extension (client)** | `htmx-ext-sse` 2.2.4 from CDN, loaded *after* the htmx 2 core script | — | htmx 2.x split SSE out of the core. Required for the streamed AI prose flow per spec. |  |
| **Backup tooling** | **Just shell out to `pg_dump` from a Python `subprocess.run`** wrapped by APScheduler. Tar photos via `tarfile` stdlib. | — | The Postgres image ships `pg_dump`. Don't add a Python pg-backup library. The whole backup service is ~50 LOC. |  |
| **Tag input UI (flavor notes)** | **Alpine.js component, hand-rolled** in `app/static/js/tag-input.js` | — | ~50 LOC. Tagify and similar third-party tag libs are 30KB+ and overkill. Spec calls for chips + autocomplete + create-new — trivial with Alpine + an HTMX `hx-get` for the autocomplete list. | Tagify, Choices.js — heavier than the entire current JS footprint. |
| **Rating control (0–5 in 0.25 steps)** | Hand-rolled HTML + Alpine.js | — | A `<input type="range" step="0.25" min="0" max="5">` styled with Tailwind is the minimum-viable thumb-operable control. If stars are required, ~30 LOC of Alpine over a hidden numeric input. |  |

---

## 3. Compatibility Gotchas

### 3.1 Tailwind CDN vs production (highest-impact gotcha)

**The Tailwind Play CDN for v4 explicitly says: "designed for development purposes only, and is not intended for production."** This is a real change from Tailwind v3, where the Play CDN was tolerated for production in low-traffic scenarios.

The CDN ships a ~400KB JS file that JIT-compiles CSS in the user's browser on every page load. At household scale and behind aggressive HTTP caching, the practical impact is small — but it conflicts with the spec's CSP requirements (the Play CDN evaluates inline `<style>` tags and requires looser CSP).

**Three options, ranked:**

1. **Best (recommended): Standalone Tailwind CLI binary, baked into the Docker image.**
   - Download the static binary in the `Dockerfile` (`https://github.com/tailwindlabs/tailwindcss/releases/.../tailwindcss-linux-x64`), run `tailwindcss -i input.css -o app/static/css/tailwind.css --minify` at image build time.
   - Output is a tiny static CSS file served by FastAPI's `StaticFiles`.
   - No npm. No Node.js. Spec lock preserved.
   - CSP can be `style-src 'self'` with no inline allowances.
   - Adds ~10s to image build and one extra COPY step. Worth it.
2. **Acceptable for v1: Play CDN, accept the warning, document the migration path.**
   - Faster to ship. Acceptable at 2-user scale.
   - CSP must allow `style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'` — that `unsafe-inline` is the cost.
3. **Not recommended: `pytailwindcss`** (PyPI wrapper around the binary). Adds a Python dep over what's effectively a single binary download.

**Decision needed by plan-phase.** Recommendation is to go with option 1 from the start because it removes a CSP exception you'd otherwise carry forever.

### 3.2 HTMX 2.x vs 1.9 (the spec says "1.9+")

The spec was written when 2.x was still in beta. As of 2026-05, **2.x is the stable line** (current 2.0.10). Differences that matter for this app:

| Change | Action |
|---|---|
| `hx-on` syntax changed to `hx-on:event` (kebab-case event names) | New code only — no migration needed since this is greenfield. Stick to the new syntax. |
| `hx-ws` and `hx-sse` attributes removed | Already accounted for — use `htmx-ext-sse@2.2.4` extension. |
| DELETE requests now use URL params, not form-encoded body | If you wire any DELETE endpoint to read from form body, you must move to query params. Recommendation: don't use DELETE at all — use POST with a hidden `_method=DELETE` if you want REST semantics. |
| Cross-origin requests blocked by default (`selfRequestsOnly=true`) | Good — keep the default. Your app is same-origin. |
| Smooth-scroll default removed | Cosmetic. Set `htmx.config.scrollBehavior = 'smooth'` once in a global script if you want the old feel. |
| Extensions no longer bundled — must include separately | Already a known change. Load `htmx-ext-sse` separately. |
| IE11 support dropped | Not relevant. |

**Recommendation: go with HTMX 2.x.** The migration list above is trivial for a greenfield build, and 1.9 is now legacy.

### 3.3 SQLAlchemy 2.0 + psycopg 3 + asyncio

The spec is "synchronous handlers fine; async where it pays (AI calls)." That maps to:

- A **synchronous** SQLAlchemy `Engine` for the bulk of CRUD (use `psycopg` driver, URL `postgresql+psycopg://...`).
- An **async** path only for the AI service code, which uses the `anthropic` / `openai` async clients via `httpx.AsyncClient`. The AI service doesn't usually need DB access mid-call — it reads inputs synchronously up front, calls the LLM async, then writes back synchronously.
- Don't mix `async def` handlers with sync DB calls. FastAPI will run sync handlers in a threadpool — that's fine. Async handlers calling sync `Session.execute()` will block the event loop.

**Gotcha:** SQLAlchemy 2.0 + psycopg 3 + `JSONB` column needs `from sqlalchemy.dialects.postgresql import JSONB` for the recipe `steps` field. Plain `JSON` works but you lose GIN indexing.

### 3.4 FastAPI lifespan vs startup/shutdown

Use `lifespan` async context manager **only**:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # APScheduler start, DB pool warmup, etc.
    yield
    # APScheduler shutdown
```

`@app.on_event("startup")` is deprecated upstream in Starlette and will be removed. Don't use it even in tests.

### 3.5 APScheduler in-process + uvicorn workers

APScheduler in-process means **one and only one uvicorn worker**. If you scale to `--workers 2`, you'll fire every job twice. For household scale this is fine — set `uvicorn --workers 1` and document it.

If you ever scale up, you'd need an external lock (`apscheduler-redis-store` or a row-lock in Postgres). Note this in the README so a future operator doesn't get bitten.

### 3.6 Starlette `SessionMiddleware` collision with custom session store

Don't install Starlette's stock `SessionMiddleware` and a custom one. The spec mandates a table-backed store. Build the custom middleware and **skip** Starlette's `SessionMiddleware`.

### 3.7 OpenAI SDK is now on 2.x

If anyone copy-pastes pre-2026 examples expecting `openai.ChatCompletion.create(...)` it won't compile. The 2.x SDK uses `client.responses.create(...)` (Responses API) with a `tools=[{"type": "web_search"}]` argument for the web search tool. This is the API path the spec needs.

### 3.8 httpx 0.x — narrow pin

httpx is still 0.x (current 0.28.1, Dec 2024 — no release in 18 months). httpx 1.0 has been on the horizon but is not out. Pin tight (`>=0.28,<0.29`) and re-evaluate every milestone. Both `anthropic` and `openai` SDKs depend on httpx internally.

---

## 4. Recent Shifts (last 12 months) — what changed

| Shift | When | Impact on this build |
|---|---|---|
| **Tailwind v4 + Play CDN production warning** | Tailwind v4 GA late 2024; warning made explicit through 2025–26 | See §3.1 — recommend the standalone CLI binary in the Dockerfile, not the CDN. |
| **HTMX 2.x stable** | 2.0.0 final mid-2024, 2.0.10 current | The spec's "HTMX 1.9+" is stale. Go straight to 2.x — see §3.2. |
| **Starlette 1.0 GA** | March 22, 2026 | First stable major. FastAPI 0.136 ships against it. Lifespan-only is now the official path. |
| **Anthropic SDK web search tool versions** | `web_search_20250305` (basic) still available; `web_search_20260209` (dynamic filtering) added Feb 2026 | For v1, use `web_search_20250305` — simpler, no code-execution-tool prerequisite. Revisit dynamic filtering when token costs become noticeable. Tool ID strings are user-facing in the API, so log which one was used in `ai_recommendations.model_used` for future audit. |
| **Anthropic SDK rapid 0.x cadence** | SDK went 0.99 → 0.102 in two weeks of May 2026 | Pin loosely (`>=0.102,<1.0`), expect a bump per milestone, watch the SDK CHANGELOG for tool-schema changes. |
| **OpenAI SDK at 2.x with Responses API** | 2.x line current (2.37, May 15 2026) | The Responses API + web search tool is the path. Don't use Chat Completions for this. |
| **psycopg 3.3 stable, native async** | 3.3.4 (May 2026) | Use `psycopg[binary]` not `psycopg2-binary`. SQLAlchemy 2.0 supports the URL prefix `postgresql+psycopg://`. |
| **Pillow 12** | 12.x line through 2026 | API-stable from 11.x; the magic-byte + EXIF strip pattern unchanged. |
| **APScheduler 4.x still alpha** | 4.0.0a6 Apr 2025; no GA | Stay on 3.x. |
| **bleach deprecation** | Mozilla deprecation notice 2023, still receiving releases | Don't add bleach. If sanitization becomes needed, use markdown-it-py or nh3 (Rust-backed ammonia bindings). |
| **slowapi minimal updates** | 0.1.9 released Feb 2024, no releases since | API is stable, used widely, still the right pick — but note the staleness and be prepared to fork or replace if it breaks. |

---

## 5. Open Questions (surface for plan-phase)

1. **Tailwind: CDN vs standalone CLI in Dockerfile.** Strong recommendation is CLI in Dockerfile (§3.1). Needs explicit John sign-off because the spec says "Tailwind CDN" and switching adds one build step — small but non-zero deviation from the stack lock.
2. **HTMX 1.9 vs 2.x.** The spec says "1.9+". 2.x is current stable. Recommendation is 2.x for a greenfield build, with the migration deltas in §3.2. Needs sign-off only because the spec is ambiguous.
3. **Search implementation (Postgres FTS vs `pg_trgm`).** Spec defers this to plan-phase. Recommendation will live in a `FEATURES.md` companion. For stack purposes: both are pure Postgres — no Python library choice needed. The `unaccent` extension may also be wanted for diacritics.
4. **Web search tool version: `web_search_20250305` vs `web_search_20260209`.** v1 should use the older simpler one. The newer one requires the `code_execution` tool to also be enabled — more moving parts, not justified at v1 cost levels.
5. **Type-checker (mypy vs ty).** Recommendation is mypy through this milestone, revisit at next milestone when ty is closer to GA.
6. **SSE client vs HTMX polling for AI streaming.** Spec mentions both. SSE is cleaner UX, but polling with `hx-trigger="every 2s"` on a job-status endpoint is simpler to implement and debug. Pick during the AI-flow plan-phase; the stack (sse-starlette + htmx-ext-sse) supports both.

---

## Sources (all consulted 2026-05-16)

- [FastAPI on PyPI](https://pypi.org/project/fastapi/) — 0.136.1
- [SQLAlchemy on PyPI](https://pypi.org/project/sqlalchemy/) — 2.0.49 stable, 2.1.0b2 beta
- [Alembic on PyPI](https://pypi.org/project/alembic/) — 1.18.4
- [Starlette on PyPI](https://pypi.org/project/starlette/) — 1.0.0
- [Uvicorn on PyPI](https://pypi.org/project/uvicorn/) — 0.47.0
- [Pydantic on PyPI](https://pypi.org/project/pydantic/) — 2.13.4
- [pydantic-settings on PyPI](https://pypi.org/project/pydantic-settings/) — 2.14.1
- [Jinja2 on PyPI](https://pypi.org/project/Jinja2/) — 3.1.6
- [httpx on PyPI](https://pypi.org/project/httpx/) — 0.28.1
- [Pillow on PyPI](https://pypi.org/project/Pillow/) — 12.2.0
- [argon2-cffi on PyPI](https://pypi.org/project/argon2-cffi/) — 25.1.0
- [cryptography on PyPI](https://pypi.org/project/cryptography/) — 48.0.0
- [itsdangerous on PyPI](https://pypi.org/project/itsdangerous/) — 2.2.0
- [APScheduler on PyPI](https://pypi.org/project/apscheduler/) — 3.11.2 (4.x alpha)
- [anthropic SDK on PyPI](https://pypi.org/project/anthropic/) — 0.102.0
- [openai SDK on PyPI](https://pypi.org/project/openai/) — 2.37.0
- [python-multipart on PyPI](https://pypi.org/project/python-multipart/) — 0.0.28
- [psycopg on PyPI](https://pypi.org/project/psycopg/) — 3.3.4
- [ruff on PyPI](https://pypi.org/project/ruff/) — 0.15.13
- [pytest on PyPI](https://pypi.org/project/pytest/) — 9.0.3
- [playwright on PyPI](https://pypi.org/project/playwright/) — 1.59.0
- [structlog on PyPI](https://pypi.org/project/structlog/) — 25.5.0
- [starlette-csrf on PyPI](https://pypi.org/project/starlette-csrf/) — 3.0.0
- [fastapi-csrf-protect on PyPI](https://pypi.org/project/fastapi-csrf-protect/) — 1.0.7
- [slowapi on PyPI](https://pypi.org/project/slowapi/) — 0.1.9
- [bleach on PyPI](https://pypi.org/project/bleach/) — 6.3.0 (deprecated)
- [Tailwind CSS — Play CDN docs](https://tailwindcss.com/docs/installation/play-cdn) — production warning
- [Tailwind CSS — Standalone CLI](https://tailwindcss.com/blog/standalone-cli)
- [HTMX 1.x → 2.x Migration Guide](https://htmx.org/migration-guide-htmx-1/)
- [HTMX SSE Extension](https://htmx.org/extensions/sse/)
- [Alpine.js Releases](https://github.com/alpinejs/alpine/releases)
- [Anthropic web search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool) — `web_search_20250305` and `web_search_20260209`
- [OpenAI Responses API + web search](https://platform.openai.com/docs/guides/tools-web-search?api-mode=responses)
- [FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/events/)
- [structlog vs Loguru — FastAPI structured logging](https://oneuptime.com/blog/post/2026-02-02-fastapi-structured-logging/view)
- [psycopg2 vs psycopg3 performance benchmark](https://www.tigerdata.com/blog/psycopg2-vs-psycopg3-performance-benchmark)

**Confidence assessment:**
- HIGH for pinned library versions (PyPI is authoritative).
- HIGH for the Anthropic web search tool (verified against official docs).
- HIGH for HTMX 2.x migration deltas (official migration guide).
- MEDIUM for the Tailwind CDN/CLI recommendation (the production warning is firm; the operational impact at household scale is judgment).
- MEDIUM for the rate-limit pick (slowapi works, but the lack of recent releases is a yellow flag — revisit if it breaks against newer Starlette).
- LOW (single recent source) on the structlog "25% faster" performance claim — treat it as directional, not load-bearing.
