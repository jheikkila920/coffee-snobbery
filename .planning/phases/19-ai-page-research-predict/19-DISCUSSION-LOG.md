# Phase 19: AI Page & Research/Predict - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-28
**Phase:** 19-ai-page-research-predict
**Areas discussed:** Research-a-coffee flow; Cost controls (cache + rate limit + storage); Existing AI flow polish; SSE streaming + charts

---

## Research-a-coffee flow

### Research input UX (D-01)

| Option | Description | Selected |
|--------|-------------|----------|
| Two free-text inputs: coffee name + optional roaster | Most flexible. Plain HTMX form on /ai; LLM uses both as grounding hints. | ✓ |
| Roaster autocomplete + coffee name | Roaster autocomplete from existing roasters catalog; more guided but adds friction if roaster not in catalog. | |
| Single free-text "paste anything" input | One textarea: paste a name, URL, or description. Maximum mobile-fast; ambiguous inputs produce worse research. | |

**User's choice:** Two free-text inputs.
**Notes:** Researched coffees do not enrich the household catalog — autocomplete from the roasters table would be wrong friction.

### Predicted rating shape (D-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Range + confidence label + reasoning | Numeric range, confidence label (Low/Medium/High), reasoning below. Schema-clean, easy to validate. | ✓ |
| Visual range bar + confidence + reasoning | Same data rendered as horizontal 0–5 bar with shaded range. More visual; harder CSP-clean. | |
| Range + reasoning, confidence implicit in width | No explicit confidence label; range width implies confidence. Simplest visual; risk of misread. | |

**User's choice:** Range + confidence label + reasoning.

### Result card layout (D-03)

| Option | Description | Selected |
|--------|-------------|----------|
| Compact card: profile + predicted rating + cited sources + Add-to-wishlist | Single card, vertical, footnotes for sources, primary button at bottom. Mobile-first. | ✓ |
| Two-section card with sources collapsed | Same data but sources tucked into a disclosure. Cleaner first impression; one extra tap. | |
| Card + separate predicted-rating block below | Profile + sources in one card, prediction in a second visually distinct block. Emphasizes "your taste" separation. | |

**User's choice:** Compact card.

### Surface placement + cache-hit behavior (D-04)

| Option | Description | Selected |
|--------|-------------|----------|
| Research card pinned at top of /ai; cache hit returns instantly | Research is the headline; cache hit shows `· cached` badge with no spinner, quota not decremented. | ✓ |
| Research card below the hero; cache hit instant | Hero stays headline; Research second. Less prominent but preserves recommendation-first narrative. | |
| Research card below hero; cache hit shows brief "served from cache" state | Same placement but 200ms cache-confirmation state for transparency about cost-control. | |

**User's choice:** Research pinned at top.

---

## Cost controls (cache + rate limit + storage)

### Research cache shape (D-06)

| Option | Description | Selected |
|--------|-------------|----------|
| New ai_coffee_research_cache table; key = lowercased(name+roaster); 30-day TTL; shared across users | Net-new dedicated table; world's view is per-coffee not per-user; cleanest cost savings. | ✓ |
| Reuse ai_recommendations with rec_type='coffee_research'; per-user; 30-day TTL | Smallest schema delta; loses cross-user cost savings. | |
| New ai_coffee_research_cache table; 14-day TTL | Same shape but tighter TTL. | |

**User's choice:** New shared 30-day cache table.

### Prediction storage (D-07) — resolves STATE.md open question

| Option | Description | Selected |
|--------|-------------|----------|
| Separate ai_rating_predictions table; (user_id, research_cache_key) unique; signature-versioned; 7-day TTL | Cleanly separates world's view from per-user view; sets foundation for AIF-02 (deferred). | ✓ |
| Reuse ai_recommendations with rec_type='rating_prediction' | Smallest schema delta; harder to query cross-user. | |
| Inline in ai_coffee_research_cache.predictions_by_user JSONB | Single shared row carries map of user_id → prediction. Schema-fluid; bad indexing for per-user lookup. | |

**User's choice:** Separate ai_rating_predictions table.

### Daily rate limit + reset (D-08)

| Option | Description | Selected |
|--------|-------------|----------|
| 10/day rolling 24h; disabled+countdown when exhausted; counter visible | Rolling window from each request; fairness; counter "X/10 remaining today". | |
| 10/day calendar UTC reset | Simpler; loses fairness at end of day. | |
| 20/day rolling 24h; same exhausted UI | Higher cap; ~$2.40/user/day worst-case ceiling. | ✓ |
| 5/day rolling 24h; same exhausted UI | Tightest cap; ~$0.60/user/day max. | |

**User's choice:** 20/day rolling 24h with counter + disabled + countdown.

### Quota scope + configurability (D-09)

| Option | Description | Selected |
|--------|-------------|----------|
| Research only; configurable via Admin Settings (default 20) | Successful LLM-fired research only; cache hits don't decrement; other AI flows keep their throttles. | ✓ |
| Research + improve-brew share one daily quota; configurable | Single mental model; heavy improve-brew users get less research headroom. | |
| Research only; hardcoded 20/day | Simplest; no Admin Settings UI work; adjusting later requires deploy. | |

**User's choice:** Research only; admin-configurable; default 20.

---

## Existing AI flow polish

### AIX-12 improve-this-brew entry point (D-12)

| Option | Description | Selected |
|--------|-------------|----------|
| Button on brew-session detail; result inline below details; not on /ai | Most contextual; doesn't clutter /ai. | |
| Button on brew-session detail AND "Coach a brew" link on /ai with session-picker; same inline result on session page | Primary contextual entry + discoverability bridge from /ai. | ✓ |
| Result renders as modal/full-page on /ai, triggered from brew-session detail | Keeps all AI surfaces on /ai; heavier navigation; loses brew context. | |

**User's choice:** Button on brew detail + "Coach a brew" link on /ai with picker.

### AIX-11 always-return-a-recipe (D-11)

| Option | Description | Selected |
|--------|-------------|----------|
| Drop no_match; require recipe_name + summary + ratio + temp_c + grind_hint; prompt generates from scratch if no catalog match | Schema is the contract; single LLM call; existing Pydantic + retry path enforces. | ✓ |
| Keep recipe_id nullable; make no_match a hard error; add explicit ratio/temp_c/grind_hint | Same end result but with explicit retry branching in app code. | |
| Two-tier: server-side similarity match from catalog first, then LLM for prose only | Lower LLM cost but real engineering project for recipe similarity. | |

**User's choice:** Option 1 (drop no_match — Claude's recommendation accepted).
**Notes:** User asked "What do you recommend"; Claude recommended Option 1; user confirmed.

### AIX-09 in-depth preference prose (D-10)

| Option | Description | Selected |
|--------|-------------|----------|
| Rewrite Preference Profile card on /ai: prose replaces structured rows; signature-driven regen; new rec_type='preference_profile_prose'; Top Flavor Descriptors DELETED from /ai | Cleanest interpretation of AIX-09 wording. Card stack: hero + prose + sweet spots (+ Research/Trends). | ✓ |
| Keep structured Preference Profile AND add new "AI Insights" prose section below; delete Top Flavor Descriptors | Structured rows stay; AI prose lives below. Two prose cards on /ai. | |
| Rewrite Preference Profile: rows in collapsed disclosure under prose; Top Flavor Descriptors deleted | Hybrid; prose primary, rows in detail block. | |

**User's choice:** Rewrite with prose; delete Top Flavor Descriptors.

### Polish trio: AIX-10 progress + archived filter + AIX-13 targets (D-13/D-14/D-15)

| Option | Description | Selected |
|--------|-------------|----------|
| All three with recommended defaults | AIX-10 via HTMX hx-indicator + htmx-request; archived filter via prompt + 404/410 retry; latency targets in PLAN.md + code comments per flow; investigation queries duration_ms over 30 days. | ✓ |
| AIX-10 + archived via defaults; AIX-13 deferred to Phase 22 | Same AIX-10 and archived; defer latency investigation to Phase 22 verification. | |
| Discuss each separately (3 more rounds) | More precise; slower. | |

**User's choice:** All three with recommended defaults.

---

## SSE streaming + charts

### SSE scope (D-16)

| Option | Description | Selected |
|--------|-------------|----------|
| SSE for research + improve-brew + what-to-buy-next refresh; paste-rank + equipment stay request/response | Three slow flows stream; sub-30s structured-output flows stay request/response. | ✓ |
| SSE for ALL AI flows | Uniform pattern; more plumbing; structured-output flows don't benefit from streaming. | |
| SSE for research only; everything else stays request/response | Minimum viable; tightest blast radius; may not satisfy strict reading of AIX-07. | |

**User's choice:** SSE for the three slow flows.

### Charts library + scope (D-17)

| Option | Description | Selected |
|--------|-------------|----------|
| Two charts in new "Trends" card on /ai: rating-over-time (line) + flavor distribution (horizontal bar); Chart.js v4 via CDN with nonce | CSP-clean; lazy-mount with stagger; tested at 375px. | ✓ |
| Three charts (add brew parameters trend) | Useful for power users but crowds the card at 375px. | |
| Two charts on /ai + separate "Trends" page link for deeper drill-down (deferred) | Same two inline charts; adds a future-phase deep-dive link. | |

**User's choice:** Two charts; Chart.js v4 via CDN.

### SSE behavior + chart theming + equipment-rec scope (D-15/D-17 wrap)

| Option | Description | Selected |
|--------|-------------|----------|
| SSE: stream complete tokens, close on Pydantic validation success; chart theming reads .dark via Alpine; equipment-rec rewrite = prompt tweak only | Single bundled approach for the tactical wrap-up. | ✓ |
| Same SSE + chart theming; equipment-rec = larger scope (parameterized form + expanded schema) | More work; better UX; adds Phase 19 scope. | |
| Discuss SSE error handling + chart theming + equipment rewrite separately (3 more rounds) | More precise; slower. | |

**User's choice:** Bundled defaults; equipment-rec stays minimal (prompt tweak only).

---

## Claude's Discretion

The following items were explicitly left to the planner — not discussed in detail:
- Exact SSE event granularity (token-level vs sentence-level streaming) per flow.
- Shared vs per-flow inline error-fragment templates.
- "Coach a brew" session-picker UI (modal vs inline expandable vs mini-page).
- Whether `cited_sources` lives in a parallel JSONB column or inside `response_json`.
- Chart label/axis copy.
- Single vs split endpoints for the two Trends charts.
- Whether the Research quota counter renders eagerly or lazy with the card.
- Equipment prompt tuning specifics.
- HTMX `hx-disabled-elt` vs `:has(.htmx-request)` selector for button disabling.
- Whether new research/improve routes live in `ai.py` or split into new modules.
- The exact `app_settings` row creation in the migration (default values + admin UI mirror).

## Deferred Ideas

Captured under CONTEXT.md `<deferred>`:
- Equipment-rec UI redesign (parameterized form, multi-tier).
- SSE on paste-rank + equipment.
- Third trend chart (brew parameters drift).
- Separate `/ai/trends` drill-down page.
- Per-month AI cost ceiling (AIF-01) — out of scope.
- Prediction-accuracy tracking (AIF-02) — deferred to v2.
- Pooled daily quota across research + improve-brew.
- Roaster autocomplete on research input.
- Single free-text "paste anything" research input.
- Visual range bar for predicted rating.
- Larger improve-brew UI scope (history, accept/reject tracking).
- Forced exhausted-state full-page error.
- Token-level vs sentence-level SSE streaming granularity (Claude's discretion).
- Chart.js alternative libraries.
- Auto-refresh predictions when signature changes (vs lazy on-read).
- Renaming `/home/cards/preference-profile` to `/ai/cards/preference-profile` (Claude's discretion).
- Renaming `/ai/equipment` or migrating to a parameterized form.
