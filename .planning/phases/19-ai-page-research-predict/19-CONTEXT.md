# Phase 19: AI Page & Research/Predict - Context

**Gathered:** 2026-05-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Fill the `/ai` page shell built in Phase 17 with the v1.2 AI differentiator: an on-demand "research a coffee + predict my rating" flow with non-negotiable cost controls, plus polish of the existing AI surfaces (preference prose, always-a-recipe, improve-this-brew, latency targets) and trend charts. 13 locked requirements:

- **AIX-01:** Free-text research input (coffee name + optional roaster) returns an AI-grounded profile with cited sources
- **AIX-02:** Predicted personal rating as RANGE + confidence label + reasoning — never a single point estimate
- **AIX-03:** Gated by existing cold-start threshold (`get_cold_start_counts`, already brew+cafe-aware per Phase 16 D-15)
- **AIX-04:** Repeat lookups served from cache within a TTL window — no duplicate web-search charge
- **AIX-05:** Per-user daily quota on research; remaining quota visible; calls blocked when exhausted
- **AIX-06:** Researched coffee can be added to wishlist directly from the result card
- **AIX-07:** AI responses stream via SSE (replacing today's polling pattern on the slow flows)
- **AIX-09:** Preference Profile card on `/ai` becomes an in-depth AI prose summary cross-cutting flavor × process × origin × varietal × rating; the standalone Top Flavor Descriptors card is removed from `/ai`
- **AIX-10:** Every user-triggered AI action shows visible progress feedback (disabled button + inline spinner) until the request completes or errors
- **AIX-11:** The "what to buy next" recommendation ALWAYS returns a concrete recipe (catalog match OR generated) plus actionable ratio/temp/grind suggestions — `no_match=true` is now treated as a bug
- **AIX-12:** User can request AI improvement suggestions on any logged brew session; the AI is aware of prior sessions for that coffee and proposes parameters not yet tried
- **AIX-13:** Each AI flow has a documented p95 latency target; an investigation captures current p50/p95 from `ai_recommendations.duration_ms` and either fixes regressions or documents why current latency is fundamental
- **VIZ-01:** Brew/preference trends presented as charts (rating over time + flavor distribution) using Chart.js v4 via CDN with CSP nonce

Explicitly NOT in this phase:
- **Mobile / visual polish to the "major-company bar"** — Phase 21 owns. Phase 19 reuses Phase 17's existing card shapes.
- **Equipment-rec UI redesign / parameterized form** — keep the existing single-button + structured-output result. Phase 19 only tweaks the equipment prompt (sharper weakest-link criteria) and applies AIX-10 progress feedback. EquipmentRecSchema unchanged; `/ai/equipment` route unchanged.
- **Paste-rank UI redesign** — `/ai/paste-rank` keeps today's behavior; only gains AIX-10 progress feedback. No SSE on paste-rank.
- **Prediction-accuracy tracking (AIF-02)** — deferred to v2; the new `ai_rating_predictions` table sets the foundation but no accuracy-loop UI is built.
- **Cafe-log changes** — Phase 16 already lands cafe data in `compute_input_signature` (D-12), `get_preference_profile` (D-13), `get_flavor_descriptors` (D-13), and `get_cold_start_counts` (D-15). Phase 19 consumes these; does not modify them.
- **New AI dashboard / trends drill-down page** — VIZ-01's two charts live in a single `/ai` card. No `/ai/trends` route.
- **Per-month AI cost ceiling (AIF-01)** — out-of-scope per PROJECT.md; the per-user daily rate limit + cache table are the cost controls.
- **Migrating `/ai/refresh`'s 5-minute throttle or in-flight lock** — both stay; the throttle is independent of the new research daily quota.
- **Renaming `/home/cards/*` endpoints to `/ai/cards/*`** — Phase 17 deferred; remains a planner discretion call in this phase but not a forced rename.

</domain>

<decisions>
## Implementation Decisions

### Research-a-coffee flow (AIX-01, AIX-02, AIX-03, AIX-06)

- **D-01:** Research input is **two free-text fields** — `coffee_name` (required) + `roaster_name` (optional). Plain HTMX POST form on `/ai`. No autocomplete from the roasters catalog (extra friction for a free-form research surface; researched coffees do NOT enrich the shared catalog). The LLM uses both fields as grounding hints when roaster is provided.

- **D-02:** Predicted rating renders as **numeric range + confidence label + reasoning prose**. Shape: `predicted_low` and `predicted_high` (both Numeric(3,2), 0–5, 0.25 steps); `confidence` enum-as-text ('Low' | 'Medium' | 'High'); `reasoning` short prose. AIX-02's "never a single number" satisfied by always rendering `predicted_low – predicted_high` together. The visible reasoning is rendered as a "Why:" block under the range.

- **D-03:** Result card is **compact, single column**, top-to-bottom: title row (roaster + " — " + coffee name), metadata row (origin · process · roast_level), tasting-note chips, predicted-rating block (range + confidence + reasoning), cited sources as small footnote-style links (`¹ url`, `² url`, ...), primary "Add to wishlist" button at the bottom. No collapsed sections, no two-column layout — mobile-first.

- **D-04:** Research card is **pinned at the TOP of `/ai`**, above the "What to buy next" hero. Renders for above-gate users with a key configured (matches existing three-branch shell from Phase 17 D-13/D-14/D-15/D-16). Cache hit returns the same compact result card with a small `· cached` badge in the metadata row; no spinner; quota counter NOT decremented. Cache hits feel instant.

- **D-05:** Wishlist add (AIX-06) uses the existing `POST /ai/wishlist/add` endpoint from Phase 7 — no new route. Pre-fills `coffee_name`, `roaster_name`, `source_url` (the verified buy URL from the research, if any) into the existing form contract. Returns 204 + `HX-Trigger: wishlistUpdated` (same pattern as today).

### Cost controls (AIX-04, AIX-05) + prediction storage (STATE.md open question resolved)

- **D-06:** Net-new **`ai_coffee_research_cache`** table holding the world's view of each coffee. Schema (planner finalizes types): `cache_key TEXT PRIMARY KEY` (lowercased + trimmed `coffee_name + '|' + roaster_name`; empty string when roaster missing), `response_json JSONB NOT NULL` (the validated `CoffeeResearchSchema` payload — coffee/roaster/origin/process/roast_level/tasting_notes/buy_url/sources), `cited_sources JSONB NOT NULL` (parallel list of citation objects), `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `expires_at TIMESTAMPTZ NOT NULL` (created_at + 30 days). **Shared across all household users** — the world's view of a coffee doesn't change per-user. Index on `expires_at` for the lazy-eviction sweep at read time.

- **D-07:** Net-new **`ai_rating_predictions`** table holding the per-user predicted rating tied to a cache row. Schema: `id BIGINT PK`, `user_id BIGINT NOT NULL ondelete=CASCADE`, `research_cache_key TEXT NOT NULL ondelete=CASCADE` (FK to `ai_coffee_research_cache.cache_key`), `predicted_low NUMERIC(3,2) NOT NULL`, `predicted_high NUMERIC(3,2) NOT NULL`, `confidence TEXT NOT NULL` ('Low' | 'Medium' | 'High'), `reasoning TEXT NOT NULL`, `input_signature TEXT NOT NULL` (the user's `compute_input_signature` value at prediction time), `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `expires_at TIMESTAMPTZ NOT NULL` (created_at + 7 days). UNIQUE `(user_id, research_cache_key)` — the latest prediction per (user, coffee) wins; rewrite on regeneration. Signature-versioned: when the user's taste signature changes, the next research call sees the prediction is stale (signature mismatch OR expired) and regenerates JUST the prediction (not the world's-view cache row). This resolves the STATE.md open question explicitly in favor of a SEPARATE table from `ai_recommendations` — chosen to (a) cleanly separate "world's view" from "your view", (b) enable AIF-02 prediction-accuracy tracking later without back-migrating, (c) avoid stretching `ai_recommendations.recommendation_type` to a fourth value.

- **D-08:** Per-user research **rate limit is 20 calls per rolling 24-hour window**, default. Counts only successful LLM-fired research calls — cache hits and prediction-only refreshes do NOT decrement. Cap is configurable via **Admin Settings** (one new row in `app_settings` keyed `ai.research_daily_quota`, default integer 20). Other AI flows (the existing `/ai/refresh` 5-minute throttle, paste-rank, equipment, the new improve-brew) keep their own throttles — they do NOT share this bucket.

- **D-09:** Quota UI: above the Research input on `/ai`, render `"{remaining}/{cap} research calls remaining today"` ; when `remaining == 0`, the Research button disables, the label flips to `"Resets in Hh Mm"` (countdown computed from the user's oldest non-expired research call in the last 24h), and a tooltip explains "Daily quota — resets 24h after each call." On submit when exhausted, the server returns 429 with `HX-Retarget="#research-card"` and a friendly inline error fragment (no full-page error). Calls that hit cache do not show or decrement the counter.

### Existing AI flow polish (AIX-09, AIX-10, AIX-11, AIX-12, AIX-13, archived-coffee filter)

- **D-10 (AIX-09):** **Rewrite the Preference Profile card** on `/ai`. AI-generated prose REPLACES the existing structured rows (origin / roaster / process / roast_level pills). New `ai_recommendations.recommendation_type='preference_profile_prose'` row (single rec_type, one row per (user, signature)). Signature-driven nightly regen + manual refresh button (subject to AIX-10 progress feedback). Prompt input shape: the structured `get_preference_profile` output + `get_flavor_descriptors` output + brew/cafe rating distribution + varietal preferences (Phase 15.1) — all serialized to JSON in the prompt. Output schema: new `PreferenceProfileProseSchema` with a single `summary_prose: str` field (no descriptor count cap, per AIX-09 wording). **DELETE** the standalone Top Flavor Descriptors card from `pages/ai.html` (current lazy mount at `hx-get="/home/cards/flavor-descriptors"` with 300ms delay). The endpoint `/home/cards/flavor-descriptors` remains in `app/routers/home.py` for now (other potential callers) but loses its `/ai` mount. Card stack on `/ai` after this: **Research → What to buy next hero → Preference Profile (prose) → Sweet Spots → AI tools (paste-rank + wishlist + equipment) → Trends**.

- **D-11 (AIX-11):** **Drop `no_match` from `RecipeSuggestionSchema`.** Add required fields `ratio: str` (e.g. "1:15"), `temp_c: int` (Celsius water temp), `grind_hint: str` (e.g. "medium-fine, ~22 clicks Encore"). `recipe_id` stays nullable (null when the LLM generates a fresh recipe rather than picking from the catalog). `recipe_name` stays — populated either from the catalog match or the generated recipe's invented name. Prompt update: "If no recipe in the user's catalog suits the recommended coffee, generate one from scratch — set `recipe_id` to null and populate `recipe_name`, `summary`, `ratio`, `temp_c`, and `grind_hint`. Never claim no recipe is available." Existing Pydantic validation + retry path in `_anthropic_coffee_call` / `_openai_coffee_call` enforces the contract; a response missing any required field triggers the existing retry/fallback. The bug — `no_match=true` — becomes a `ValidationError` because the field no longer exists.

- **D-12 (AIX-12):** **Button on the brew-session detail page** is the PRIMARY entry for improve-this-brew suggestions. Placement: next to the existing Edit button on the session detail view (planner picks exact spot). Plus a **"Coach a brew" link on `/ai`** in the AI tools section that opens a **session-picker** modal (or inline expandable list) showing the user's last ~20 brew sessions; selecting one navigates to the brew-session detail page with the result already requested via `hx-trigger="load"`. Both routes land at the **same inline result UI on the session detail page** (a new card below the session detail). Result schema: new `BrewImproveSchema` with `summary_prose: str`, `unchanged_parameters: list[str]` (the dial settings the user already tried — sanity check that the LLM saw them), `next_try: list[BrewParameterChangeSchema]` (each: `parameter` enum {'grind' | 'ratio' | 'temp_c' | 'brewer' | 'recipe'}, `suggested_value: str`, `rationale: str` 1–2 sentences). Server pre-loads ALL of the user's brew sessions for the session's `coffee_id` and serializes them as prompt input so the LLM can "know prior sessions" and avoid duplicates. New route `POST /ai/improve-brew/{session_id}` (HTMX-friendly). Counts against its OWN daily quota — separate constant for now (default also 20/day, also configurable via app_settings key `ai.improve_brew_daily_quota`), NOT pooled with research (D-08).

- **D-13 (AIX-10):** Every user-triggered AI button uses **HTMX's `hx-indicator` + `htmx-request` class** to disable + show inline spinner during the request. Uniform pattern across `/ai/refresh`, `/ai/equipment`, `/ai/paste-rank`, the new `/ai/research`, the new `/ai/improve-brew/{session_id}`. Spinner shape: small inline SVG (matches existing skeleton-pulse aesthetic) inside the button's `<span class="htmx-indicator">`; button gets `disabled` via the `:has(.htmx-request)` selector OR `[hx-disabled-elt]` attribute (planner picks — both CSP-clean). Indicator styles defined in `tailwind.src.css` per the **strict-csp-blocks-htmx-indicator** project memory (not relying on HTMX auto-injection). On error, button re-enables and an inline error fragment replaces the result region.

- **D-14 (archived-coffee filter, 07-UAT-1 follow-up):** Prompt for `_generate_coffee_rec` and the new research flow explicitly includes: "Only recommend coffees that are currently for sale at the roaster's website. Avoid archived, sold-out, or discontinued lots." The existing `_verify_buy_url` SSRF-hardened verifier already does a ranged GET + 200-class check (Phase 7). Extend it to **treat 404/410 (and explicit `Available: Sold Out` text in the first 64KB Range response if cheap to detect) as a verification failure**. On failure for `/home/cards/ai-recommendation`, the new behavior is **one retry with a broadened-search instruction** (`"Try again with a broader search; the first candidate appears archived."`) before falling through to the existing "no good recommendation today" fragment. For research, an archived first pick just renders the result with a small warning chip ("buy URL not verified — coffee may be sold out") — the user picked the coffee to research; we don't second-guess.

- **D-15 (AIX-13):** Latency targets documented in `19-PLAN.md` AND as one-line module-top comments on each AI flow function in `ai_service.py`:
  - `_generate_coffee_rec` (what-to-buy-next): **p95 ≤ 60s**
  - `generate_equipment_rec`: **p95 ≤ 20s**
  - `generate_sweet_spots_prose`: **p95 ≤ 30s**
  - `rank_pasted_coffees`: **p95 ≤ 45s**
  - new research flow (`generate_coffee_research`): **p95 ≤ 30s**
  - new improve-brew flow (`generate_brew_improvement`): **p95 ≤ 20s**
  - new preference prose (`generate_preference_profile_prose`): **p95 ≤ 30s**

  Investigation step (one-time, before close): SQL query against `ai_recommendations.duration_ms` grouped by `recommendation_type`, last 30 days, computing p50 + p95. Any flow exceeding its target gets a fix attempt or a written justification in `19-VERIFICATION.md` for why current latency is fundamental (e.g., web-search-tool dominates). Phase 22 verification reruns the query as a smoke check.

### SSE streaming + Charts (AIX-07, VIZ-01)

- **D-16 (SSE):** **SSE replaces polling on three flows: research, improve-brew, and "what to buy next" refresh.** Paste-rank and equipment-rec stay request/response (sub-30s typical, structured output doesn't benefit from token streaming). Implementation: `sse-starlette` server-side (`EventSourceResponse`); `htmx-ext-sse@2.2.4` client-side via CDN, loaded with nonce. Contract per SSE response:
  - Each SDK delta (token or sentence — planner picks granularity per flow) yields one `event: message\ndata: {partial_prose}` chunk to the client.
  - On final tool_use block, server validates the Pydantic schema (`CoffeeResearchSchema`, `BrewImproveSchema`, or `CoffeeRecSchema`).
  - On validation success: emit one final `event: complete\ndata: {final_html_fragment}` event with the rendered card HTML, then close the stream. Client `hx-swap` replaces the result div.
  - On validation failure: emit `event: error\ndata: {short_user_facing_message}` and close; client renders an error fragment.

  EventSource reconnect is native on the client; SSE retries are bounded by the existing `_advisory_lock` so a reconnecting client doesn't double-charge. NPM (Nginx Proxy Manager) is confirmed compatible with SSE (`text/event-stream` content-type is treated as streaming without `proxy_buffering off` tweaks); a smoke test is part of the verification.

- **D-17 (Charts, VIZ-01):** **Two charts in a new "Trends" card on `/ai`**, mounted as the LAST section (below Sweet Spots, above the existing AI tools section — planner reorders if it reads cleaner). Library: **Chart.js v4 via jsdelivr CDN**, loaded with `nonce="{{ csp_nonce(request) }}"`. Charts:
  1. **Rating over time** — line chart of `brew_session.rating + cafe_log.rating` UNIONed per-user over the last 90 days. X-axis: date. Y-axis: 0–5. Single line; markers at session points.
  2. **Flavor distribution** — horizontal bar chart of top-N flavor descriptors by appearance count, per-user, UNION of `brew_session.flavor_note_ids_observed` and `cafe_log.flavor_note_ids` (matches existing `get_flavor_descriptors` semantics — but here NO ≥ 4.0 rating filter; descriptors counted across all sessions). N is the count of distinct descriptors capped at 15 for readability.

  Theming: an Alpine.js component watches `<html>` classList for the `dark` class (Tailwind v3 darkMode:'selector') and reconfigures Chart.js colors on toggle. Light: espresso-700 lines on cream-100 background; Dark: cream-200 lines on espresso-900 background. Tested at 375px (chart fits the card width with `maintainAspectRatio:false` + a fixed pixel height).

  Data source: two new lightweight endpoints `GET /ai/charts/rating-over-time` and `GET /ai/charts/flavor-distribution`, each returning JSON. Lazy-mounted via `hx-get` + 700ms stagger (after the existing 500ms Sweet Spots stagger). Client Alpine glue parses JSON and feeds Chart.js.

### Claude's Discretion (planner picks)

- **Exact SSE event granularity** — token-level vs sentence-level streaming. Token-level feels responsive; sentence-level is simpler. Planner picks per flow.
- **Inline error fragment templates** — one-off per flow vs a shared `fragments/ai/_ai_error.html`. Likely shared.
- **The session-picker UI for "Coach a brew"** — modal vs inline expandable list vs a dedicated `/ai/coach` mini-page. Planner picks; modal pattern doesn't exist in the app today, so an inline expandable list (Alpine x-show) is the path of least resistance.
- **Where the `cited_sources` JSONB sits semantically** — full URL list inside `response_json`, or a parallel `cited_sources` JSONB column. The schema lists them separately for indexability later, but if the planner picks "inside response_json" that's fine — change the migration accordingly.
- **Chart label and axis copy** — small details; planner uses sensible defaults.
- **Whether the Trends card lazy-mounts both charts in one endpoint or two** — one is simpler (single HTMX round-trip + Alpine reads two JSON blobs); two is more modular. Planner's call.
- **Whether the Research card's quota counter renders eagerly on page load or lazy-loads with the card** — eager keeps the counter visible immediately; lazy avoids a sync query on the page-shell render. Likely eager because the count is cheap (one COUNT query).
- **Equipment prompt tuning** — sharpening the "weakest link" criteria. No schema/route change; just prompt refinement.
- **HTMX `hx-disabled-elt` vs `:has(.htmx-request)` for button disabling** — both work; pick the one that reads better.
- **Whether the new research route lives in `app/routers/ai.py` or a new module `app/routers/ai_research.py`** — `ai.py` is already 476 lines + 7 endpoints; splitting may help readability. Planner's call.
- **Configurable quota: `app_settings` row vs `pydantic-settings` env var** — one is admin-editable without redeploy (chosen for the cap defaults), one is deploy-time-fixed. Use `app_settings` (chosen in D-08); planner confirms the key name `ai.research_daily_quota` doesn't collide with existing keys.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` § "Phase 19: AI Page & Research/Predict" — goal + 8 success criteria + dependencies (Phase 17 shell, Phase 16 cafe data, Phase 15.1 multi-origin/varietal/no-freshness)
- `.planning/REQUIREMENTS.md` § "AI Page & Research/Predict (AIX)" — AIX-01..AIX-13 wording (minus AIX-08 which Phase 17 closed); § "Data Visualization (VIZ)" — VIZ-01 wording; § "Future / Deferred Requirements" — AIF-01 (per-month ceiling out-of-scope), AIF-02 (prediction-accuracy tracking deferred to v2 — the new `ai_rating_predictions` table sets the foundation)
- `.planning/PROJECT.md` § "Active" — v1.2 milestone scope (AI research-a-coffee + predict-rating); § "Key Decisions" — signature-based regen as cost control invariant, single uvicorn worker invariant, AI: Anthropic by default + OpenAI fallback (both must support web search), "AI streaming via polling, not SSE, in v1 — deferred (still unbuilt)" decision now reversed for the three slow flows
- `.planning/STATE.md` § "Decisions" — "On-demand AI research (Phase 19) removes the nightly cadence gate — cache table + per-user daily rate limit are non-negotiable blocking deliverables, not follow-ups" (locked here as D-06/D-07/D-08/D-09); "v1.2 open: AI prediction storage (`ai_recommendations` reuse vs. new `ai_coffee_predictions` table) — resolve at plan-phase 19" → RESOLVED in D-07 in favor of new `ai_rating_predictions` table
- `.planning/STATE.md` § "Known Gaps" → "Follow-up TODOs from 07-UAT-1" — AI hero regen latency (several minutes vs typical 10-60s) → AIX-13 / D-15 investigation; AI grounding surfaced an ARCHIVED/unavailable coffee → D-14 archived-coffee filter

### Prior phase contexts that constrain Phase 19
- `.planning/phases/17-ia-restructure/17-CONTEXT.md` — the `/ai` page shell composition (D-12..D-16): three-branch state machine (below-gate / above-gate-no-key / above-gate-key-present); the four lazy-mounted cards (hero / Preference Profile / Top Flavor Descriptors / Sweet Spots) Phase 19 modifies; the `fragments/research_coming_soon.html` stub Phase 19 REPLACES; the existing AI tools section (paste-rank link, wishlist link, equipment form). The `/ai/equipment` route mounting (form POST + inline result) is the pattern AIX-10 progress feedback follows.
- `.planning/phases/16-cafe-quick-rate/16-CONTEXT.md` — D-12 (signature payload extension already includes cafe rows), D-13 (preference profile dims already UNION brew+cafe for origin/roaster/flavor), D-15 (cold-start gate already counts brew+cafe), D-14 (top-coffees stays brew-only). **Phase 19 does NOT modify any of these — it consumes them.**
- `.planning/phases/15.1-catalog-session-polish/15.1-CONTEXT.md` — multi-origin schema (`coffee_origins` join table), varietal m2m, roast-freshness removed app-wide. Phase 19's AI prompts (CoffeeRecSchema, PreferenceProfileProseSchema, CoffeeResearchSchema) must NOT reference freshness/roast_date and SHOULD reference varietals + origins as preference dims.

### Code surfaces this phase modifies or creates

**Existing files that MUST be modified:**
- `app/services/ai_service.py` — add `generate_coffee_research` (new flow), `generate_brew_improvement` (new flow), `generate_preference_profile_prose` (new flow); modify `_generate_coffee_rec` (drop `no_match` path, add archived retry); modify `_build_coffee_rec_prompt` and the structured-output prompt for research (add "only recommend currently-for-sale coffees" instruction). Wire all five new flow handlers to SSE for the three streaming ones.
- `app/services/ai_schemas.py` — modify `RecipeSuggestionSchema` (drop `no_match`; add required `ratio`, `temp_c`, `grind_hint`); add `CoffeeResearchSchema` (coffee_name, roaster_name, origin, process, roast_level, tasting_notes[], buy_url, sources[]); add `RatingPredictionSchema` (predicted_low, predicted_high, confidence, reasoning); add `BrewImproveSchema` (summary_prose, unchanged_parameters[], next_try[BrewParameterChangeSchema]); add `PreferenceProfileProseSchema` (summary_prose). Tune `EquipmentRecSchema` prompt only — no schema field change.
- `app/templates/pages/ai.html` — remove the Top Flavor Descriptors lazy mount (D-10); insert Research card at the top (D-04); replace the `fragments/research_coming_soon.html` include with the actual research form fragment; add Trends card after Sweet Spots (D-17); ensure the existing card order/staggers (100/200/300/500/700ms) still apply with the new layout. Preference Profile section header/text may stay; only the mounted endpoint and result-rendering change.
- `app/routers/ai.py` (or a new `app/routers/ai_research.py` / `app/routers/ai_improve.py` — planner's call) — add `POST /ai/research` (SSE), `GET /ai/research/quota` (counter fragment), `GET /ai/coach` (session picker fragment), `POST /ai/improve-brew/{session_id}` (SSE), `GET /ai/charts/rating-over-time` (JSON), `GET /ai/charts/flavor-distribution` (JSON).
- `app/routers/home.py` — `/home/cards/preference-profile` either renames to `/ai/cards/preference-profile` (planner's call) or stays at its URL but starts returning the new prose template instead of the structured-rows template. Either way the response shape changes.
- `app/services/analytics.py` — no schema changes; potentially add a small helper `count_research_calls_in_last_24h(db, user_id)` for the quota counter. Existing `get_preference_profile`, `get_flavor_descriptors`, `get_sweet_spots`, `compute_input_signature`, `get_cold_start_counts` are CONSUMED unchanged.
- `app/services/settings.py` — add reader for `ai.research_daily_quota` and `ai.improve_brew_daily_quota` (integer settings; default 20 each).
- `app/templates/admin_settings.html` — admin UI to edit the two new quota settings (mirror existing setting controls).
- `app/static/css/tailwind.src.css` — define `.htmx-indicator` spinner styles (per project memory `strict-csp-blocks-htmx-indicator`) — keep CSP-clean.
- `app/templates/base.html` — add Chart.js v4 CDN `<script>` with `nonce="{{ csp_nonce(request) }}"`; add `htmx-ext-sse@2.2.4` CDN script with nonce.
- `entrypoint.sh` — no change (migrations auto-run on container start as today).

**New files (planner creates):**
- `app/models/ai_coffee_research_cache.py` — new table model (D-06).
- `app/models/ai_rating_prediction.py` — new table model (D-07).
- `app/migrations/versions/p19_ai_research_predict.py` — new migration creating both tables + the new `app_settings` rows for quota defaults + any indexes.
- `app/services/ai_research.py` — service-layer module for the research flow (cache lookup, quota check, SSE generator, prediction tying); or fold into `ai_service.py` if the planner prefers a single AI service module.
- `app/services/ai_quota.py` — small helper module owning the rolling-24h quota math + admin-configurable cap reader (or a few functions in `ai_service.py` — planner's call).
- `app/services/charts.py` — query helpers for the two VIZ-01 chart endpoints.
- `app/templates/fragments/ai/research_form.html` — research input form + counter + result mount.
- `app/templates/fragments/ai/research_result.html` — the compact result card (D-03).
- `app/templates/fragments/ai/research_quota_exhausted.html` — exhausted-state friendly inline error.
- `app/templates/fragments/ai/preference_profile_prose.html` — replaces the structured Preference Profile fragment for `/ai`.
- `app/templates/fragments/ai/trends_card.html` — wrapper card with two `<canvas>` elements + Alpine glue.
- `app/templates/fragments/ai/coach_brew_picker.html` — session-picker fragment for the "Coach a brew" link.
- `app/templates/fragments/brew/improve_result.html` — the inline result card on the brew-session detail page.
- `app/static/js/alpine-components/chart-trends.js` — Alpine component reading `<html>` `.dark` and rendering Chart.js instances; CSP-clean (no eval).
- `tests/services/test_ai_research.py`, `tests/services/test_ai_quota.py`, `tests/services/test_brew_improve.py`, `tests/services/test_preference_prose.py`, `tests/services/test_archived_retry.py`, `tests/routers/test_ai_research.py`, `tests/routers/test_ai_improve.py`, `tests/routers/test_ai_charts.py`, `tests/templates/test_ai_page_phase19.py` — coverage for new flows + the schema changes (existing tests for `no_match=true` will fail and must be updated).
- A Playwright check for the 375px Research card flow can land in Phase 22 with the v1.2 smoke pass; if the planner wants a Phase 19 smoke, scope it tight to the Research happy-path.

**Pattern files to read before implementing:**
- `app/services/ai_service.py` — provider abstraction (`_build_anthropic_client`, `_build_openai_client`), the `_project_tool_use_input` citation projector (T-07-02 prompt-injection defence), `_verify_buy_url` (T-07-SSRF — extend for archived-coffee detection per D-14), the `_get_lock` + `_THROTTLE` + `_advisory_key` concurrency primitives, the `regenerate(user_id, source, db, force)` entry point pattern. Reuse all of these — do NOT re-implement the security-critical pieces.
- `app/services/ai_schemas.py` — `ConfigDict(extra="forbid")` pattern for prompt-injection defence on every new schema.
- `app/models/ai_recommendation.py` — cost-observability column set (tokens_input/output, web_search_count, tool_version, etc.). New flows write to the SAME `ai_recommendations` table when applicable (preference_profile_prose, brew_improvement) — same `recommendation_type` enum extension pattern. The research-cache and prediction tables are SEPARATE because they're shared-vs-per-user and have different TTLs.
- `app/routers/ai.py:55-85` — the existing `get_ai_page` handler showing the three-branch shell rendering. Phase 19 modifies the "above gate, key present" branch.
- `app/routers/ai.py:195-298` — the `/ai/refresh` handler — pattern for HTMX 429 + `HX-Retarget` + `HX-Reswap` on throttle exhaustion. The new research route's quota-exhausted response follows the same pattern (D-09).
- `app/routers/ai.py:383-421` — the `/ai/wishlist/add` endpoint — the existing surface AIX-06 wires into (D-05).
- `app/services/analytics.py:387-448` — `get_cold_start_counts` — gate-open check the new research flow consults (AIX-03).
- `app/services/analytics.py:456-...` — `compute_input_signature` — input signature the new `ai_rating_predictions.input_signature` ties to (D-07).
- `app/templates/pages/ai.html` — current Phase 17 shell composition + the lazy-mount stagger pattern (100/200/300/500ms). Phase 19's new cards extend the stagger.
- `app/templates/fragments/admin_settings.html` (or wherever admin settings UI lives) — mirror for the two new quota inputs.

### Architectural patterns to follow (project memory + invariants)
- **HTMX 2.x conventions** (CLAUDE.md § 3.2, project memory `tailwind-v3-not-v4`) — kebab-case `hx-on:event`, no `hx-ws` / `hx-sse` attributes (use `htmx-ext-sse@2.2.4` separately for D-16), DELETE-as-POST-with-`_method=DELETE` if any new DELETE-style route is added.
- **Tailwind v3 invariant** (project memory `tailwind-v3-not-v4`) — `darkMode: 'selector'`; never `@custom-variant`. Chart.js theming reads `.dark` class directly.
- **CSP nonce invariant** — every new `<script>` tag (Chart.js CDN, htmx-ext-sse CDN, inline Alpine components) MUST carry `nonce="{{ csp_nonce(request) }}"`. Indicator/spinner styles defined in `tailwind.src.css`, not auto-injected (project memory `strict-csp-blocks-htmx-indicator`).
- **SW cache invariant** (project memory `c9-sw-cache-content-deterministic`) — the build-hash cache name bumps automatically on template/CSS/JS content change. New SSE endpoints + chart endpoints are NOT cached by the SW (they're dynamic JSON / event streams). Service worker config likely doesn't need modification, but the planner verifies — if a new dynamic-content path doesn't match the `/` network-first rule, add it.
- **CSRF + autoescape** — every new state-changing form (research, improve-brew) keeps the double-submit cookie + token pattern. SSE responses are GET-style streams but the initial POST still carries CSRF.
- **Single uvicorn worker** — module-level `_LOCKS`, `_THROTTLE` dicts stay process-local. Quota counter math runs against the DB (per-user query on `ai_recommendations` `generated_at` for research_type), NOT in-memory.
- **Pitfall: full-suite test isolation** (project memory `full-suite-test-isolation-gaps`) — new tests follow the catalog-TRUNCATE + settings-cache-clear conftest pattern landed in Phase 15. Phase 22 verification reruns the suite twice.
- **APScheduler signature regen** — the nightly job already picks up signature changes for the new `recommendation_type='preference_profile_prose'`. No scheduler code change required; only the rec_type list iterated by the nightly job may need a one-line extension (planner reads `app/services/scheduler.py`).
- **Mobile-first @ 375px hard rule** — Research card form + result card, quota counter, Coach-a-brew picker, Trends card with two Chart.js instances ALL tested at 375px before close. Bottom nav <768px, top nav ≥768px (unchanged by Phase 19).

No external specs introduced during discussion — the decisions above are the contract.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Provider abstraction in `ai_service.py`** — `_build_anthropic_client` / `_build_openai_client` already handle key fetch + client construction. Research and improve-brew flows reuse these directly. No new client wiring.
- **Web search tool wiring** (Anthropic `web_search_20250305`, OpenAI Responses API web_search) — already implemented for the coffee-rec flow. Research flow uses the SAME tool with the SAME `_project_tool_use_input` citation projector — the citation projector is the load-bearing T-07-02 prompt-injection defence; reuse verbatim.
- **`_verify_buy_url`** (T-07-SSRF hardened — https-only, no cross-host redirect, 64KB Range cap, 5s timeout) — extend for archived-coffee detection (D-14): treat 404/410 as failure + optional first-64KB "Sold Out" text scan. Used by both `/home/cards/ai-recommendation` (existing) and the new research flow.
- **`compute_input_signature`** — Phase 16 D-12 already extended payload to include cafe rows. The new `ai_rating_predictions.input_signature` (D-07) stores the value at prediction time so the predicted rating can be detected as stale when the user's taste shifts.
- **`_THROTTLE` + `_get_lock` + `_advisory_key`** (process-local concurrency primitives, single uvicorn worker) — the existing 5-min `/ai/refresh` throttle pattern. Quota math for research/improve-brew is DB-backed (rolling 24h query against `ai_recommendations.generated_at` filtered by `recommendation_type`), not in-memory. The advisory lock prevents double-billing on rapid SSE reconnects.
- **`ai_recommendations` table** (Phase 0 model with full cost-observability columns) — research, improve-brew, and preference-profile-prose flows write here with new `recommendation_type` values (`'coffee_research'`, `'brew_improvement'`, `'preference_profile_prose'`). The world's-view research cache (`ai_coffee_research_cache`) is SEPARATE because it's shared across users; rating predictions are SEPARATE because they have a 7-day TTL distinct from the 30-day cache row.
- **`/ai/wishlist/add` endpoint** (Phase 7 D-09) — AIX-06 reuses this verbatim. Research result card's wishlist button HTMX-posts to it with pre-filled fields.
- **Cold-start gate** (`get_cold_start_counts`, Phase 16 D-15) — already brew+cafe-aware. AIX-03 satisfied by the existing Phase 17 three-branch shell wrapping the research card.
- **Lazy-loaded HTMX cards** with skeleton placeholders + staggered delays (100/200/300/500ms on `/ai` today) — pattern extends to Research card (eager mount or lazy 100ms), Preference Profile prose (200ms), Sweet Spots (500ms), Trends (700ms).
- **Alpine.js dark-mode reactive components** — existing dark-toggle component (Phase 13) sets `.dark` on `<html>`. New chart-trends.js component watches the class for chart re-theming.
- **`structlog` event constants** (`AI_GENERATION_START`, `AI_GENERATION_SUCCESS`, etc. in `app/events.py`) — new flows add new event names following the same prefix convention.
- **Pydantic v2 `ConfigDict(extra="forbid")`** — every new AI response schema MUST use this for T-07-02 prompt-injection defence.

### Established Patterns
- **One schema per AI flow** (CoffeeRecSchema, EquipmentRecSchema, PasteRankSchema, SweetSpotsProseSchema) — extend with CoffeeResearchSchema, RatingPredictionSchema, BrewImproveSchema, PreferenceProfileProseSchema. `summary_prose: str` is the AI-18 narrative output convention; carry it on each new top-level schema.
- **`recommendation_type` enum-as-text** in `ai_recommendations` — current values: `'coffee' | 'equipment' | 'paste_rank' | 'sweet_spots'`. Phase 19 adds: `'brew_improvement'`, `'preference_profile_prose'`. The research cache and predictions are NOT new rec_types — they live in separate tables.
- **HTMX HX-* response headers for partial updates** — `HX-Trigger`, `HX-Retarget`, `HX-Reswap` pattern used by `/ai/refresh`. New routes follow the same. SSE responses use a different content-type and bypass these headers; the client side wires SSE via `htmx-ext-sse@2.2.4` + `sse-connect` attribute.
- **CSP nonce on every inline `<script>`** — universal. All new Alpine glue + chart bootstrapping carry `nonce="{{ csp_nonce(request) }}"`.
- **Fragment include path naming** — `fragments/ai/*.html` for AI-page-specific fragments (established Phase 17). New research, trends, preference-prose, coach-brew-picker fragments go here. `fragments/brew/improve_result.html` for the brew-session-detail-page surface.
- **Per-router `_hydrate_form_context()` helper** (Phase 15.1 D-21) — pattern for dual-Edit-button surfaces. AIX-12's "Coach a brew" picker doesn't need the dual-button pattern (it's a one-tap entry, not an edit), but the planner is aware of it.
- **Mobile-first @ 375px** — every new card tested at 375px before close. Trends card with two Chart.js instances is the highest-risk surface for horizontal scroll; planner uses `maintainAspectRatio:false` + fixed pixel height + 100% container width.
- **Test conventions** — `tests/services/test_*.py` + `tests/routers/test_*.py` pair per new feature surface; conftest TRUNCATE for catalog tables + settings cache clear (Phase 15 fix).

### Integration Points
- **`/ai` page shell** (`pages/ai.html` + `get_ai_page` in `app/routers/ai.py`) — single integration point for the new Research card, modified Preference Profile, deleted Top Flavor Descriptors, and new Trends card. All other AI surfaces (paste-rank link, wishlist link, equipment form, what-to-buy-next hero) keep their current placement.
- **Brew-session detail page** (the route + template that renders a single brew session) — new "Suggest improvements" button + the new inline result card. Locate the existing detail surface (likely `app/routers/brew.py` and a template like `pages/brew_detail.html` or a fragment) — the planner reads first.
- **`ai_recommendations` write path** (`_write_recommendation_row` in `ai_service.py:1095`) — extend with the two new rec_types. The cost-observability columns (tokens_input/output, web_search_count, tool_version, duration_ms) populate for the new flows too.
- **`ai_coffee_research_cache` + `ai_rating_predictions` tables** — entirely net-new; the research flow is the only writer. Reads from the research flow + the prediction-refresh path on `/ai`.
- **`compute_input_signature`** — the new `RatingPredictionSchema.input_signature` ties to this value at prediction time. NO modification to the function itself.
- **APScheduler nightly job** (`app/services/scheduler.py`) — the existing per-user signature-driven regen loop already iterates over rec_types. Add the two new rec_types to its iteration list (one-line change). Research cache is NOT regenerated nightly (TTL-driven on read). Predictions are NOT regenerated nightly either (refreshed on next research-result render if stale). Cost stays bounded.
- **`/home/cards/preference-profile`** (current) — either the URL stays and the response shape changes (planner picks if a rename is worth the SW cache churn), or it renames to `/ai/cards/preference-profile`. The home page no longer renders this card per Phase 17 D-07; only `/ai` calls it.
- **Admin Settings UI** — two new integer inputs (`ai.research_daily_quota`, `ai.improve_brew_daily_quota`). Mirror existing setting input shape.
- **Service worker** (`app/static/js/sw.js`) — likely no change. The new endpoints are dynamic (SSE streams + JSON); they don't match the static asset cache rules. Planner verifies. The build-hash cache name auto-bumps on template/CSS/JS content change.
- **NPM (Nginx Proxy Manager)** — confirmed compatible with SSE via standard `text/event-stream` content-type. No NPM config change required; smoke-test the streaming flows end-to-end during verification.
- **No changes to**: auth, CSRF middleware, encryption layer, search router, brew CSV import/export, cafe-log routes/templates, photo pipeline, scheduler backup job, admin user/credential routes.

</code_context>

<specifics>
## Specific Ideas

- **Range + confidence label + reasoning** (D-02) — the explicit interpretation of AIX-02's "range with a confidence level and visible reasoning." Three-part contract: range visible, confidence visible, reasoning visible. No single number ever.
- **Research card pinned at TOP of `/ai`** (D-04) — explicit placement choice. The new feature is the headline; "What to buy next" hero sits below. Cache hits return instantly with a small `· cached` badge in the metadata row (no spinner; no quota decrement).
- **Shared-across-users research cache + per-user prediction** (D-06 / D-07) — explicit two-table split. The world's view doesn't change per user; the personal prediction does. Both expire on different schedules (30d cache, 7d prediction). Predictions are signature-versioned so they invalidate when the user's taste profile shifts.
- **20 research/day, rolling 24h, admin-configurable** (D-08 / D-09) — explicit number + window + UI shape. Counter visible above input ("X/20 remaining today"); exhausted = button disabled + countdown ("Resets in Hh Mm"); cache hits don't decrement; quota cap editable via Admin Settings (default 20).
- **Drop `no_match` entirely** (D-11) — the AIX-11 bug fix is a schema deletion, not a sentinel-to-error path. Pydantic + `extra="forbid"` + the existing retry path enforce the contract.
- **DELETE the Top Flavor Descriptors card from `/ai`** (D-10) — AIX-09's "flavor descriptors are not shown as a standalone top-descriptors widget" interpreted strictly. The endpoint `/home/cards/flavor-descriptors` survives (other callers may exist); only the `/ai` mount is removed.
- **Improve-this-brew entry on the brew-session detail page** (D-12) — explicit "where the user is already looking" choice. The "Coach a brew" link on `/ai` is a discoverability bridge, not a duplicate result surface.
- **SSE for the three slow flows** (D-16) — explicit narrow scope. Research, improve-brew, what-to-buy-next refresh. Paste-rank and equipment stay request/response because they're sub-30s typical and structured-output streaming doesn't help.
- **Chart.js v4 via CDN with nonce** (D-17) — explicit library + version + delivery + CSP wiring. Two charts only: rating-over-time line + flavor distribution horizontal bar.
- **Latency targets as code comments + PLAN.md** (D-15) — targets live next to the code they govern, not in a separate doc. Single source of truth visible at the function definition.
- **Archived-coffee retry-with-broader-search** (D-14) — explicit single-retry semantics for the `/home/cards/ai-recommendation` flow. Research flow renders the result with a "buy URL not verified" chip instead — the user chose to research that exact coffee; we don't second-guess.
- **Quota config in `app_settings`, NOT env var** (D-08) — explicit admin-editable-at-runtime choice. Two new keys: `ai.research_daily_quota`, `ai.improve_brew_daily_quota`. Default 20 each.

</specifics>

<deferred>
## Deferred Ideas

- **Equipment-rec UI redesign (parameterized form, multi-tier recommendations)** — considered in area 4 wrap-up and rejected. Phase 19 limits equipment changes to prompt tuning + AIX-10 progress feedback. Larger redesign deferred to a future polish phase if equipment-rec usage data shows the current shape is the limit.
- **SSE on paste-rank + equipment-rec** — considered in area 4 SSE-scope and rejected. Both are sub-30s typical with structured output; streaming doesn't add value. Could revisit if observed latency rises.
- **Third trend chart (brew parameters drift over time)** — considered for VIZ-01 and rejected at 375px readability. Two charts only on `/ai`. A "see more trends" drill-down page is a future-phase candidate.
- **Separate Trends drill-down page (`/ai/trends`)** — considered as a discoverability bridge and rejected; the two charts inline on `/ai` are sufficient at household scale.
- **Per-month AI cost ceiling (AIF-01)** — out-of-scope per REQUIREMENTS.md and PROJECT.md; the per-user daily rate limit + 30-day shared cache are the cost controls for v1.2. Revisit only if costs surprise.
- **Prediction-accuracy tracking (AIF-02)** — explicitly deferred to v2 by REQUIREMENTS.md. The new `ai_rating_predictions` table sets the foundation (input_signature + per-user + per-coffee row, easy to compare against a future brew-session rating for the same coffee_id). No accuracy-loop UI built.
- **Pooled daily quota across research + improve-brew** — considered in D-08 and rejected. Separate buckets, separate admin-configurable defaults. Pooling risks a heavy improve-brew user starving research; cleaner mental model with separation.
- **Roaster autocomplete on the research input** — considered in D-01 and rejected. Researched coffees do not enrich the household catalog (they're an external lookup); requiring catalog presence would be wrong friction.
- **Single free-text "paste anything" research input** — considered in D-01 and rejected. Ambiguous inputs produce worse research; cache key would be harder to dedupe.
- **Visual range bar for predicted rating** — considered in D-02 and rejected in favor of numeric range + label + reasoning. Simpler to render CSP-clean; satisfies AIX-02 unambiguously.
- **Larger improve-brew UI scope (history of past improvements, accept/reject tracking)** — out of scope for v1.2. Improve-brew is a single-shot suggestion at v1.2; tracking acceptance is a future feature (and a natural pair with AIF-02 prediction accuracy).
- **Forced exhausted-state full-page error** — considered in D-09 and rejected. Inline 429 with `HX-Retarget` is more graceful than a navigation.
- **SSE streaming token-by-token vs sentence-by-sentence** — explicit Claude's-discretion item; planner picks per flow at plan time.
- **Chart.js alternative libraries** (ApexCharts, Plotly) — considered for VIZ-01 and rejected. Chart.js v4 is the canonical Snobbery research pick (CLAUDE.md tech stack), v4 is CSP-nonce-compatible, no eval.
- **Auto-refresh of predictions when signature changes** (instead of TTL + signature check at read time) — considered for D-07 and rejected. Lazy on-read refresh is cheaper and doesn't need a background job. Stale signature is detected on next render and triggers a regen.
- **Renaming `/home/cards/preference-profile` to `/ai/cards/preference-profile`** — Claude's-discretion item left to the planner. Either choice is fine; the planner weighs SW cache churn vs URL clarity.
- **Renaming `/ai/equipment` or migrating to a parameterized form** — out-of-scope per D-10/D-12. Phase 19 keeps `/ai/equipment` shape; only the prompt is tuned.
- **`fragments/research_coming_soon.html` stub** — DELETED by Phase 19 (replaced by the actual research card). Keep in mind for grep when cleaning up.

None of the above are dropped — each is captured for the phase or future iteration that owns it.

</deferred>

---

*Phase: 19-ai-page-research-predict*
*Context gathered: 2026-05-28*
