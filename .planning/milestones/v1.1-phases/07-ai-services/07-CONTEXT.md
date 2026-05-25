# Phase 7: AI Services - Context

**Gathered:** 2026-05-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Ship Snobbery's differentiator: a provider-agnostic `app/services/ai_service.py`
plus the user-facing AI surfaces. This phase delivers 18 requirements
(AI-01, AI-03..AI-18, HOME-06).

In scope:
- **Provider abstraction** (Anthropic default / OpenAI fallback) reading the
  decrypted key + model from `api_credentials` via `credentials.get_provider_credential`.
- **Live coffee recommendation** — three-tier web-search fallback (primary →
  broadened → characteristics-only), ranged-GET URL verification, per-flow
  Pydantic validation after citation projection.
- **Sweet-spots AI prose** (HOME-06) generated alongside the coffee rec and
  cached together (AI-10).
- **Recipe suggestion** (picks from existing recipes, never invents) and
  **alternative-brewer callout** (≥0.5 rating delta) as part of the coffee-rec
  composite.
- **Equipment recommendation** (profile-only, no web search).
- **Paste-and-rank** (on-demand, never cached, never scheduled).
- **Regeneration control** — signature compare (helper already exists),
  in-memory + Postgres advisory lock, 5-minute manual-refresh throttle,
  stale-indicator badge, manual "Refresh recommendations" button.
- **Graceful states** — "AI not configured" (no provider enabled) and
  "Try again" (Pydantic validation failure).
- **Cost telemetry** — every call persists the full `ai_recommendations`
  column set (provider, model, tool version, token splits, web-search count,
  url_verified, duration, generated_by).
- **Wishlist** — "Add to wishlist" hook on the coffee card + a minimal
  wishlist view (see D-10).

Out of scope (belongs to later phases):
- **Nightly scheduled regeneration** (SCHED-02), APScheduler wiring, the
  `last_ai_run_status` write loop — **Phase 8**. Phase 7 builds the
  `regenerate(user_id, generated_by=...)` entry point the scheduler will call,
  but does not schedule it.
- **Admin API-credential vault, model picker, API health panel** (ADMIN-02,
  ADMIN-06) — **Phase 9**. Phase 7 only *reads* credentials/settings.
- **Bottom-tab nav / PWA shell / final aesthetic + dark mode** — **Phase 11**.
  Phase 7 templates must work at 375px but inherit the current `base.html`
  frame.
- **Formal AI-service test suite under `respx`** (TEST-02) — **Phase 12**
  (accrue tests as you go per CLAUDE.md, but the formal suite is Phase 12).

</domain>

<decisions>
## Implementation Decisions

### Home page AI surface
- **D-01: Top-hero placement.** The "what to buy next" coffee-recommendation
  card is the home page headline, above the analytics aggregate cards. It is
  the core-value surface ("what to buy next, grounded in your log"); the data
  cards support it.
- **D-02: Single hero pick.** The home card shows one confident coffee
  recommendation (reasoning + verified buy link + add-to-wishlist), not a
  ranked shortlist. Matches ROADMAP's singular "a coffee suggestion", keeps
  web-search use minimal, and gives a clear CTA at 375px. Multi-candidate
  ranking is served by paste-and-rank (top 3), not the home card.

### AI voice & tone
- **D-03: Confident expert, lightly wry.** The house voice for all AI prose
  (coffee-rec reasoning, sweet-spots interpretation): knows its stuff, a touch
  opinionated, occasionally dry — never performative. Matches PROJECT's
  "snobbery tone without becoming gimmicky." This drives the system-prompt
  design; the full-snob persona was explicitly rejected (gimmick risk).
- **D-04: Tight prose (1-2 sentences).** Every `summary_prose` field stays a
  punchy line or two — fast to read phone-in-hand at the kettle, lower output
  tokens.

### Flow delivery model
- **D-05: Equipment recommendation is on-demand, surfaced on the home page.**
  A "analyze my setup" button/card on the home page generates the equipment rec
  only when clicked — never scheduled, never part of the nightly cached bundle.
  Rationale: it is profile-only (cheap) but equipment changes rarely and
  "no changes recommended" is a common output; an always-on nightly card would
  be permanent clutter and a wasted LLM call.
- **D-06: Coffee rec + sweet-spots prose are the cached, nightly-regenerated
  bundle** (AI-10, locked). Recipe suggestion and the alternative-brewer
  callout are part of the coffee-rec *composite* (same bean style), rendered on
  the same hero card when they fire — not separate cards. The alt-brewer
  callout appears inline on the coffee card only when historical data shows the
  ≥0.5 delta (AI-07).

### Paste-and-rank
- **D-07: Dedicated page.** Paste-and-rank lives on its own "Rank these for me"
  page (linked from home/config), not embedded on the home page. Keeps the home
  surface focused on the cached pick; gives room for a paste box + the top-3
  ranked results with one-sentence reasoning each (AI-09).
- **D-08: Accepts both pasted text and URLs.** One input box; detect whether
  the user pasted freeform coffee descriptions or product URLs. URL input
  requires fetch + extract before ranking — this is *separate* from the
  live-rec web search and should reuse/extend the AI-05 ranged-GET machinery
  (realistic UA, 5s timeout, no cross-host redirects) to pull page text.
  See research flag.

### Wishlist
- **D-09: Add hook + minimal view.** Ship the "Add to wishlist" action on the
  coffee card (writes to the existing `wishlist_entries` table, `source=
  "ai_recommendation"`) AND a simple wishlist view: list saved coffees, mark
  purchased (`purchased_at`), remove. Closes the loop so saves aren't
  write-only — the reason the table exists (PROJECT: "otherwise the rec is
  suggest-and-forget"). Full wishlist CRUD (reorder, tags, move-to-catalog on
  purchase) is deferred.

### Locked upstream — do NOT re-litigate (carried from ROADMAP / REQUIREMENTS / PROJECT)
- **Provider:** Anthropic default, OpenAI fallback only on non-retryable errors
  (`AuthenticationError`, `BadRequestError`, `PermissionDeniedError`, persistent
  `OverloadedError` after one retry); SDK clients built with `max_retries=1`
  (AI-01).
- **Three-tier fallback:** primary (origin + process + roast level) → broadened
  (relax process → roast level → origin, in that order) → characteristics-only
  (no specific bean, no URL); response indicates which tier produced it (AI-03).
- **Delivery:** HTMX **polling, not SSE**, in v1 (PROJECT key decision; ROADMAP
  SC-3). Manual refresh while a run is in flight → 429 + HX-Retarget to a
  "please wait" message.
- **Citation handling:** citation/tool-result blocks projected/stripped before
  Pydantic validation (AI-04); schema mismatch → "Try again" UI, never garbled
  JSON.
- **URL verification:** ranged GET (not HEAD), realistic User-Agent,
  body-contains-roaster-or-coffee-name check, no cross-host redirects, 5s
  timeout; unverified URL renders as plain text with a "couldn't verify" note
  (AI-05).
- **Recipe suggestion:** picks from the user's existing `recipes` ranked by
  historical avg rating for matching origin + process + roast level; never
  invents; if none match, says so and links to the recipe builder (AI-06).
- **Locking:** in-memory per-`(user_id, recommendation_type)` lock + Postgres
  advisory-lock backstop (AI-13); single uvicorn worker makes the in-memory
  lock process-local and the advisory lock the real cross-process guard.
- **Cost controls (load-bearing):** signature-based regen (helper exists),
  5-minute manual-refresh throttle (AI-14, COST-2), `max_uses` 5 primary / 3
  broadened from `app_settings` (AI-17, COST-5), `recommendation_region=US`
  scoping. Signature = content hash of the user's OWN rated sessions only
  (COST-4; Phase 6 D-08/D-09) — never shared catalog counts.
- **Cold-start gate:** <3 sessions OR <5 distinct observed flavor notes → progress
  meter, no AI section (AI-11). Already built in Phase 6 (`get_cold_start_counts`,
  D-02).
- **Schemas:** per-flow Pydantic validation; every response schema includes a
  `summary_prose` field (AI-18).
- **Telemetry:** every call writes the full `ai_recommendations` row including
  token splits and `web_search_count` (AI-02).

### Claude's Discretion
Resolve these with sensible defaults; note the choice in the plan.
- **Coffee-rec card composition** — fields to render on the hero card (name,
  roaster, origin/process/roast level, why-prose, buy link + verify state,
  add-to-wishlist, recipe suggestion, alt-brewer callout when it fires) as one
  composite card. Recommend a single composite card.
- **URL-verify UX timing** — recommend render the card immediately with a
  "verifying…" link state, run the ranged-GET verification async, and let the
  existing polling pattern swap in verified/unverified (matches AI-05 wording);
  planner confirms vs blocking on verification before first paint.
- **`ai_recommendations` row shape for the cached bundle** — the model enum has
  a distinct `sweet_spots` type, but AI-10 says coffee + sweet-spots prose are
  cached together. Recommend generating both in one regen transaction; planner
  picks whether sweet-spots prose is its own row (`recommendation_type=
  "sweet_spots"`) or embedded in the coffee `response_json`. Keep them
  regenerated/expired together either way.
- **`recommendation_type` value set** — use the documented `coffee` |
  `equipment` | `paste_rank` | `sweet_spots` (from the model).
- **Route/module layout** — recommend `app/services/ai_service.py` (provider
  clients + flow functions + citation projector + URL verifier + schemas),
  `app/services/wishlist.py` (add/list/mark-purchased/remove), and a new
  `app/routers/ai.py` for the AI routes (manual refresh, in-flight poll,
  equipment-rec generate, paste-rank page+submit, wishlist) — vs extending
  `home.py`. Planner picks.
- **`regenerate()` entry-point signature** — design so Phase 8's scheduler can
  call it directly with `generated_by="scheduler"` (SCHED-02).
- **Default model IDs** — read from `api_credentials.model_name` (admin-set in
  Phase 9). Planner documents a sensible default but does not hardcode.
- **Paste-rank URL extraction depth** — how much page text to feed the model;
  planner picks a bounded extraction.
- **`ai.*` event taxonomy** in `app/events.py` (generation start/success/error,
  fallback-tier, url_verify, throttle_block).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level
- `.planning/ROADMAP.md` §"Phase 7: AI Services" — goal sentence, 5 success
  criteria, and Notes (carries pitfalls AI-1 token cost, AI-2 URL verify via
  ranged GET + body-contains-name + 5s + no cross-host redirects, AI-3 citation
  projector before Pydantic, AI-4 fallback only on non-retryable, AI-5 tool
  version in `app_settings`, AI-6 advisory-lock backstop, COST-2 5-min throttle,
  COST-4 signature scope, COST-5 max_uses 5/3). Also lists the two plan-phase
  research flags.
- `.planning/REQUIREMENTS.md` §"AI Services (AI)" — AI-01, AI-03..AI-18 verbatim
  + §"Home Page Analytics" HOME-06. §"AI Run Scheduling" SCHED-02 for the
  scheduler entry-point contract Phase 8 will consume.
- `.planning/PROJECT.md` §"AI Integration" (the 18-line flow list), §"Context"
  ("AI flows are the differentiator", "Cost discipline matters … signature-based
  regeneration is load-bearing"), §"Key Decisions" (signature-based regen only —
  no token ceiling; polling not SSE; `wishlist_entries` added for the rec card;
  Anthropic default / OpenAI fallback both web-search-capable),
  §"Architectural invariants".
- `.planning/STATE.md` §"Blockers/Concerns" — Phase 7 research flags (citation
  projection; polling-vs-SSE [resolved: polling]).

### Prior phase context (decisions Phase 7 inherits)
- `.planning/phases/06-analytics-home-page/06-CONTEXT.md` — `compute_input_signature`
  composition (D-08 per-session fields; D-09 rated-sessions-only), the unified
  cold-start gate (D-02), the home shell/router + lazy-fragment + `FragmentCacheHeadersMiddleware`
  conventions, and the `fragments/home/sweet_spots.html` card where HOME-06 prose attaches.
- `.planning/phases/03-encryption-settings/03-CONTEXT.md` — `credentials.get_provider_credential`
  → `ProviderCredential(provider, model_name, key)` dataclass (decrypted key
  NEVER in a Pydantic model / `model_dump`), the typed `settings` reader + cache,
  and the seeded AI `app_settings` keys.
- `.planning/phases/01-middleware/01-CONTEXT.md` — CSP-strict Alpine (CSP build,
  `Alpine.data(...)`, no `hx-on:` inline, no `|safe`), `FragmentCacheHeadersMiddleware`,
  CSRF double-submit-cookie (every state-changing AI POST carries the token).
- `.planning/phases/02-auth/02-CONTEXT.md` — `require_user` + `request.state.user`
  (full User row); every AI route gated + scoped by `request.state.user.id`;
  cross-user id → 404 (IDOR), matching the Phase 5 router pattern.
- `.planning/phases/00-foundation/00-CONTEXT.md` — `ai_recommendations` and
  `wishlist_entries` tables shipped in migration 1 (no migration expected this
  phase); single-uvicorn-worker rule; sync `SessionLocal` pattern + the
  sync-DB-in-async-handler caveat.

### Operational + spec
- `CLAUDE.md` §"Architectural invariants" ("AI keys live encrypted in the DB …
  Never bypass `services/encryption.py`"; "Signature-based AI regeneration … the
  nightly job only regenerates when input signature changed … Don't break this —
  it's the cost control"; per-user AI recs; mobile-first 375px; CSRF + security
  headers), §"Stack invariants", §"Files worth knowing" (`app/services/ai_service.py`
  = provider abstraction + structured-output schemas; `scheduler.py`; `encryption.py`),
  §"Code conventions" (ruff, type hints, Pydantic v2, SQLAlchemy 2.0 `select()`),
  §"When to ask vs proceed" (changes to AI scheduling / cost-control = ask first),
  §"Things to never do silently" (never bypass encryption layer; never log keys;
  no `|safe`).
- `CLAUDE.md` "Technology Stack" §1 + §4 — `anthropic>=0.102,<1.0`
  (`web_search_20250305` basic is the v1 tool; `web_search_20260209` exists),
  `openai>=2.37,<3.0` (Responses API + web-search tool — NOT Chat Completions),
  `httpx>=0.28,<0.29` (URL verify, wrap in 5s timeout), Pydantic v2.
- `docs/snobbery-gsd-prompt.md` — original brief; the "what to buy next,
  grounded in your actual log" framing and the AI-flow intent originate here.
  `.planning/` docs are authoritative where they diverge.

### External library docs (planner verifies via Context7/ctx7 at plan-phase)
- `anthropic` SDK — `tool_use` structured output, the `web_search` tool +
  `max_uses`, citations as a separate content block (research flag — confirm the
  projector strips them before Pydantic), `usage` token accounting incl.
  search-billed input tokens, `max_retries`, error classes
  (`AuthenticationError`/`BadRequestError`/`PermissionDeniedError`/`OverloadedError`).
- `openai` SDK 2.x — Responses API + `web_search` tool, structured outputs,
  error classes for the fallback predicate.
- `httpx` — ranged GET (`Range` header), redirect control (no cross-host),
  timeouts.
- `pydantic` v2 — per-flow response schemas + validation-error surfacing.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (all on disk)
- **`app/services/credentials.py::get_provider_credential`** → `ProviderCredential`
  (provider, `model_name`, decrypted key); returns `None` on no-row / disabled /
  decrypt-fail (drives the "AI not configured" state, AI-16). Decrypted key must
  NEVER enter a Pydantic model (SEC-6, Phase 12 grep).
- **`app/services/settings.py`** typed reader + cache → `recommendation_region`
  (US), `min_sessions_for_ai`, `min_flavor_notes_for_ai`, `ai_primary_max_searches`
  (5), `ai_broadened_max_searches` (3), the web-search tool-version rows,
  `last_ai_run_status`.
- **`app/services/analytics.py`** — `compute_input_signature(user_id)`,
  `get_cold_start_counts`, plus the sweet-spots / preference derivations the AI
  flows read for grounding and stale comparison.
- **`app/models/ai_recommendation.py`** — full AI-02 column set;
  `recommendation_type` ∈ {coffee, equipment, paste_rank, sweet_spots};
  `generated_by` ∈ {scheduler, manual_refresh}; indexes `ix_ai_recs_input_signature`
  and `ix_ai_recs_user_type_generated`.
- **`app/models/wishlist_entry.py`** — `coffee_name`, `roaster_name`,
  `source_url`, `source`, `notes`, `added_at`, `purchased_at`;
  `ix_wishlist_entries_user_id`.
- **`app/routers/home.py` + `app/templates/pages/home.html` + `app/templates/fragments/home/`**
  — the home shell, lazy-card fragment pattern, and `sweet_spots.html` (where
  HOME-06 prose attaches).
- **`app/dependencies/auth.py::require_user`** + `request.state.user` — gate +
  scope every AI route.
- **`app/services/encryption.py`** MultiFernet — already wired into credentials;
  the AI service consumes the decrypted key via credentials, never touches
  Fernet directly.
- **CSP-strict Alpine components + `app/templates/base.html`** (HTMX 2.0.10,
  CSP nonce, CSRF meta) — polling via `hx-trigger`/`hx-get`, spinner states.

### Established Patterns (Phase 7 follows)
- "Cross-cutting → middleware; feature surface → router; stateful logic →
  service." New: `app/services/ai_service.py`, `app/services/wishlist.py`,
  `app/routers/ai.py` (planner may instead extend `home.py`).
- Per-user scoping on every read/write (`request.state.user.id`); cross-user id
  → 404 (IDOR), matching the Phase 5 brew router.
- HTMX fragment + `FragmentCacheHeadersMiddleware` (`no-store` + `Vary: HX-Request`)
  for every AI fragment/poll response.
- CSP-strict: no `|safe` (AI prose rendered as escaped text + `<br>` only — never
  raw HTML), no `hx-on:`, no `unsafe-eval`; Alpine via `Alpine.data`.
- "async where it pays" — AI service uses the async SDK clients; read inputs
  sync up front, call the LLM async, write back sync. Do NOT issue sync DB calls
  inside an async handler on the event loop (CLAUDE Tech Stack §3.3).
- Single uvicorn worker — the in-memory lock is process-local; the Postgres
  advisory lock is the real concurrency backstop.

### Integration Points
- `app/routers/home.py` / `pages/home.html` — add the top-hero coffee-rec card,
  the on-demand equipment-rec button, the stale badge + manual-refresh button;
  attach sweet-spots prose to the existing `fragments/home/sweet_spots.html`.
- `app/services/ai_service.py` — NEW. Provider clients, the flow functions
  (coffee rec w/ 3-tier search, sweet-spots prose, equipment rec, alt-brewer,
  recipe suggestion, paste-rank), citation projector, Pydantic schemas, ranged-GET
  URL verifier, signature compare + persistence, and a `regenerate()` entry point
  reusable by Phase 8's scheduler.
- `app/services/wishlist.py` — NEW. add / list / mark-purchased / remove.
- `app/events.py` — add the `ai.*` event taxonomy.
- `app/migrations/versions/` — likely NO migration (tables already exist); add
  one only if a genuinely new index/column is needed.
- **Phase 8 dependency:** `regenerate(user_id, generated_by="scheduler")` is the
  contract SCHED-02 will call; design it now, schedule it there.

</code_context>

<specifics>
## Specific Ideas

- **Cost discipline is the load-bearing constraint.** Web search is the
  expensive line. The controls — signature-based regen, 5-min manual throttle,
  `max_uses` 5/3, single hero pick (D-02), equipment-rec on-demand (D-05),
  paste-rank never-cached — all exist to keep the bill sane. Do not add a
  separate token ceiling (explicitly v2-deferred).
- **Decrypted API key must never enter a Pydantic model or `model_dump()`**
  (SEC-6; Phase 12 ships the grep test).
- **AI prose is rendered as escaped text with `<br>` only — never `|safe`**
  (gap-library guidance + SEC-05). The "snobbery, not gimmicky" voice (D-03) is
  a system-prompt concern, not a markup one.
- **`recommendation_region=US`** scopes web search to US roasters/retailers by
  default; configurable in admin (Phase 9).
- **Anthropic `web_search_20250305` (basic)** is the v1 tool version per Tech
  Stack §4; the value lives in `app_settings` and is logged to
  `ai_recommendations.tool_version` — never hardcoded (AI-05).
- **Paste-rank "both" input (D-08)** adds a user-supplied-URL fetch path that is
  distinct from the live-rec web search; reuse the AI-05 ranged-GET safety rules
  (UA, 5s timeout, no cross-host redirects) for extraction.

## No SPEC.md
No `*-SPEC.md` exists for this phase — requirements are captured in the
decisions above plus the canonical refs (REQUIREMENTS.md AI-01, AI-03..AI-18,
HOME-06).

## Research flags (for gsd-phase-researcher)
- **Confirm Anthropic structured-output via `tool_use` returns citations as a
  separate content block** and that the projector strips them correctly before
  Pydantic validation (AI-04). Carried from STATE.md.
- **Polling-vs-SSE: resolved → polling for v1** (no further research needed;
  noted here so it isn't re-opened).
- **Paste-rank URL extraction** — confirm a safe, bounded fetch+extract approach
  reusing the AI-05 ranged-GET machinery (SSRF posture: no cross-host redirects
  already required); decide how much page text to feed the model.
- **OpenAI Responses API web-search tool** shape + error classes for the
  non-retryable fallback predicate (AI-01).

</specifics>

<deferred>
## Deferred Ideas

- **3-pick home shortlist** — rejected for v1 (D-02): cost + 375px clutter;
  paste-and-rank already covers multi-candidate ranking. Revisit if a single
  pick feels too thin.
- **Full snob persona prose** — rejected (D-03) on gimmick risk. The voice is
  "confident expert, lightly wry."
- **Bundled nightly equipment-rec card on home** — rejected (D-05): cost +
  permanent "no changes recommended" clutter. Equipment rec is on-demand.
- **Full wishlist CRUD** (priority reorder, tags, auto-move-to-catalog on
  purchase) — beyond the D-09 minimal view; revisit if the wishlist earns it.
- **Per-user/month AI cost ceiling** — already v2-deferred (PROJECT); signature
  regen + throttle + max_uses is the v1 control.
- **SSE streaming for AI responses** — v1.1 polish; v1 uses polling (locked).
- **Auto-surfacing equipment rec when a weak link is detected** — out of scope;
  on-demand only.

### Reviewed Todos (not folded)
None — `todo.match-phase 7` returned 0 matches. The one open todo ("inline
add-new-coffee from the brew form") is Phase 4 / catalog scope, unrelated to
this phase.

</deferred>

---

*Phase: 7-AI Services*
*Context gathered: 2026-05-20*
