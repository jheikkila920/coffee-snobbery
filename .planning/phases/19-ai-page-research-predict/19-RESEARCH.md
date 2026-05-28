# Phase 19: AI Page & Research/Predict — Research

**Researched:** 2026-05-28
**Domain:** FastAPI SSE streaming, AI structured output reconciliation, Chart.js v4 CSP, rolling quota, lazy TTL cache, signature-versioned predictions
**Confidence:** HIGH (core patterns verified against official docs and codebase; NPM/SSE caveat MEDIUM)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: Two free-text research input fields (coffee_name required, roaster_name optional). No catalog autocomplete.
- D-02: Predicted rating as numeric range + confidence label ('Low'|'Medium'|'High') + reasoning prose. Never a single number.
- D-03: Compact single-column result card (title → metadata → tasting notes → predicted rating block → cited sources → wishlist button).
- D-04: Research card pinned at TOP of `/ai`. Cache hit: returns instantly with `· cached` badge, quota NOT decremented.
- D-05: Wishlist add uses existing `POST /ai/wishlist/add` endpoint from Phase 7 verbatim. Pre-fills coffee_name, roaster_name, source_url.
- D-06: New `ai_coffee_research_cache` table (shared across users). cache_key = lowercased+trimmed `coffee_name + '|' + roaster_name`. TTL 30 days. `expires_at` index for lazy eviction.
- D-07: New `ai_rating_predictions` table (per-user). UNIQUE (user_id, research_cache_key). TTL 7 days. Signature-versioned: stale on signature mismatch OR expiry. Separate from `ai_recommendations`.
- D-08: 20 calls per rolling 24h window per user, default. Admin-configurable via `app_settings` key `ai.research_daily_quota`. Improve-brew has its own separate quota (`ai.improve_brew_daily_quota`, default 20).
- D-09: Quota UI above research input: "X/20 remaining today". Exhausted: button disabled + "Resets in Hh Mm" countdown. Server returns 429 + HX-Retarget="#research-card" on exhausted submit.
- D-10: Rewrite Preference Profile card as AI prose (`recommendation_type='preference_profile_prose'`). DELETE Top Flavor Descriptors card from `/ai`. Endpoint `/home/cards/flavor-descriptors` survives.
- D-11: Drop `no_match` from `RecipeSuggestionSchema`. Add required `ratio: str`, `temp_c: int`, `grind_hint: str`. `recipe_id` stays nullable (null = generated recipe).
- D-12: Improve-brew button on brew edit page (`/brew/{id}/edit`). "Coach a brew" link on `/ai` opens session-picker (inline Alpine expandable list). Both land at same inline result card on the edit page.
- D-13: HTMX `hx-indicator` + `htmx-request` class pattern for all AI buttons. Spinner styles in `tailwind.src.css` (not auto-injected — project memory `strict-csp-blocks-htmx-indicator`).
- D-14: Archived-coffee filter: prompt says "only currently-for-sale coffees"; `_verify_buy_url` extended to treat 404/410 as failure. One retry with broadened search for `/home/cards/ai-recommendation`. Research flow renders a "buy URL not verified" chip.
- D-15: Latency targets documented as function-top comments in `ai_service.py` AND in plan frontmatter.
- D-16: SSE on three flows: research, improve-brew, what-to-buy-next refresh. `sse-starlette` server-side; `htmx-ext-sse@2.2.4` client-side with nonce. Event contract: `event: message` deltas → `event: complete` final HTML fragment → `event: error`.
- D-17: Chart.js v4 via jsdelivr CDN, nonce-tagged. Two charts: rating-over-time (line) + flavor distribution (horizontal bar). Alpine watches `<html>` `.dark` for re-theming.

### Claude's Discretion
- SSE event granularity (token vs sentence level) — planner picks per flow.
- Inline error fragment templates — shared `fragments/ai/_ai_error.html` likely.
- "Coach a brew" UI — inline Alpine expandable list (preferred, no modal pattern exists).
- `cited_sources` JSONB placement (inside or parallel to `response_json`).
- Chart label/axis copy.
- One or two chart endpoints (single endpoint simpler).
- Quota counter: eager on page load (recommended — single cheap COUNT query).
- Equipment prompt tuning (no schema/route change).
- `hx-disabled-elt` vs `:has(.htmx-request)` for button disabling.
- New research route in `app/routers/ai.py` or `app/routers/ai_research.py`.
- Quota config uses `app_settings` rows (chosen in D-08, not env vars).

### Deferred Ideas (OUT OF SCOPE)
- Equipment-rec UI redesign.
- SSE on paste-rank + equipment-rec.
- Third trend chart (brew parameters drift).
- Separate `/ai/trends` page.
- Per-month AI cost ceiling (AIF-01).
- Prediction-accuracy tracking (AIF-02) — table foundation built; no UI.
- Pooled daily quota across research + improve-brew.
- Roaster autocomplete on research input.
- Single free-text research input.
- Visual range bar for predicted rating.
- Larger improve-brew UI scope (history, accept/reject tracking).
- Auto-refresh predictions on signature change (lazy on-read is correct).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AIX-01 | Free-text research input returns AI-grounded profile with cited sources | § SSE Streaming + Structured Output Reconciliation, § Standard Stack |
| AIX-02 | Predicted rating as range + confidence + reasoning, never single number | § D-02 schema shape; RatingPredictionSchema pattern |
| AIX-03 | Research gated by existing cold-start threshold | Existing `get_cold_start_counts` — no change needed |
| AIX-04 | Repeat lookups served from cache within TTL — no duplicate web-search charge | § Lazy TTL Cache |
| AIX-05 | Per-user daily quota; remaining quota visible; blocked when exhausted | § Rolling 24h Quota Math |
| AIX-06 | Add researched coffee to wishlist from result card | Existing `POST /ai/wishlist/add` — no change |
| AIX-07 | AI responses stream via SSE | § SSE Streaming — Full Pattern |
| AIX-09 | Preference Profile becomes in-depth AI prose, no descriptor widget | New `preference_profile_prose` rec_type; scheduler one-line extension |
| AIX-10 | Visible progress feedback on every AI button | HTMX `hx-indicator` + `tailwind.src.css` spinner (project memory) |
| AIX-11 | What-to-buy-next always returns concrete recipe + ratio/temp/grind | Drop `no_match`, add required fields to `RecipeSuggestionSchema` |
| AIX-12 | Improve-brew suggestions on any brew session; aware of prior sessions | New `POST /ai/improve-brew/{session_id}` SSE route; button on edit page |
| AIX-13 | Documented p95 latency targets; investigation captures current p50/p95 | § Latency Investigation Query |
| VIZ-01 | Brew/preference trends as Chart.js v4 charts with CSP nonce | § Chart.js Integration |
</phase_requirements>

---

## Summary

Phase 19 extends a mature, well-secured AI service layer with four new flows (research, improve-brew, preference-profile-prose, what-to-buy-next SSE) and two new infrastructure tables. The codebase already provides all the load-bearing primitives — provider abstraction, citation projector, advisory lock, SSRF verifier, `_write_recommendation_row`, `regenerate()` pattern — and this phase reuses them verbatim. The genuinely new technical ground is: (1) SSE streaming via `sse-starlette` reconciled with Anthropic/OpenAI structured tool-use output, (2) Chart.js v4 CSP-clean integration with Alpine dark-mode watching, (3) rolling-24h per-user quota math backed by the existing `ai_recommendations` table, and (4) the two-table cache architecture (shared world-view + per-user signature-versioned prediction).

The SSE pattern is the highest-risk new surface. The key insight is that streaming prose and structured output are incompatible in a single LLM call with strict tool-use schemas: you cannot `stream.text_stream` and also get a validated Pydantic object from the same structured call. The recommended reconciliation pattern is **two-phase streaming**: stream a `summary_prose` text block first, then trigger a second non-streaming structured-output call for the Pydantic fields, then emit the `event: complete` fragment. This pattern keeps streaming feel, validates the schema, and keeps the advisory lock held across both calls.

Chart.js v4.5.1 requires `style-src 'unsafe-inline'` for inline canvas style attributes — which conflicts with Snobbery's strict CSP. The workaround is explicit canvas sizing via `width`/`height` HTML attributes (not CSS) + `maintainAspectRatio: false` in the chart config, which avoids the inline style injection. The script tag itself only needs a CSP nonce (Chart.js does not use `eval`).

NPM (Nginx Proxy Manager) requires explicit `proxy_buffering off` in the Advanced Nginx config for SSE to flow without buffering. The backend should also emit `X-Accel-Buffering: no` response header for defense-in-depth. `sse-starlette` sets `Cache-Control: no-cache` automatically; the planner adds `X-Accel-Buffering: no` to `EventSourceResponse` headers.

**Primary recommendation:** Use the two-phase streaming pattern (prose stream + structured finalize) for all three SSE flows. Add `sse-starlette>=3.4,<4` to requirements.txt. Load Chart.js 4.5.1 via CDN with explicit canvas sizing. Add `proxy_buffering off` to the NPM Advanced config and document in the operator guide.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Coffee research + predicted rating | API / Backend | — | LLM call + cache read/write; no client logic |
| SSE stream delivery | API / Backend | Browser | Server emits events; browser EventSource reconnects |
| Rolling 24h quota enforcement | API / Backend | — | DB-backed COUNT; never client-trusted |
| TTL cache lookup | API / Backend | — | Shared table; must be server-authoritative |
| Preference Profile prose generation | API / Backend | — | Signature-driven; scheduled or on-demand |
| Brew improvement suggestions | API / Backend | — | Session history loaded server-side |
| Chart data queries | API / Backend | Browser | JSON endpoints; Chart.js renders client-side |
| Chart rendering + dark-mode theming | Browser / Client | — | Chart.js + Alpine watching `<html>.dark` |
| HTMX progress feedback | Browser / Client | — | `hx-indicator` / `htmx-request` class; no server change |
| Quota counter render | API / Backend | — | Eager server-side render on page load (single COUNT query) |
| Wishlist add from research result | API / Backend | — | Existing `POST /ai/wishlist/add`; no new capability needed |

---

## Standard Stack

### Core (existing — reuse verbatim)

| Library | Version | Purpose | Source |
|---------|---------|---------|--------|
| anthropic | `>=0.102,<1.0` | Anthropic SDK: streaming + tool use | [VERIFIED: pypi.org/project/anthropic] |
| openai | `>=2.37,<3.0` | OpenAI SDK: Responses API streaming | [VERIFIED: pypi.org/project/openai] |
| htmx.org | 2.0.10 (CDN) | HTMX core: hx-ext, hx-indicator, swaps | [CITED: base.html — already loaded] |
| @alpinejs/csp | 3.15.12 (CDN) | Alpine CSP build: x-data, x-watch | [CITED: base.html — already loaded] |

### New additions

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| sse-starlette | `>=3.4,<4` | `EventSourceResponse` for FastAPI SSE | [VERIFIED: pypi.org/project/sse-starlette] Production/Stable, BSD-3, Starlette 1.0 compatible |
| Chart.js | 4.5.1 (CDN) | Browser chart rendering | [CITED: github.com/chartjs/Chart.js/releases — v4.5.1 Oct 13 2024; no v5 yet] |
| htmx-ext-sse | 2.2.4 (CDN) | HTMX SSE extension (core removed it in v2) | [CITED: htmx.org/extensions/sse/ — latest CDN pin `@2.2.4`] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `sse-starlette` | `StreamingResponse` + hand-rolled SSE framing | ~60 LOC of keepalive + reconnect + ping vs 1 line; no benefit |
| Chart.js 4 | ApexCharts / Plotly | Both need eval or larger bundle; Chart.js nonce-compatible, no eval |
| htmx-ext-sse | Vanilla `EventSource` + JS | Vanilla works but loses HTMX swap integration; requires bespoke JS |

**Installation (add to requirements.txt):**
```
sse-starlette>=3.4,<4
```

Chart.js and htmx-ext-sse are CDN-loaded — not in requirements.txt.

---

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| sse-starlette | PyPI | ~5 yrs (v0.1 2020) | High (production-stable) | github.com/sysid/sse-starlette | [OK] | Approved |
| chart.js | CDN/npm (not PyPI) | ~12 yrs | 50M+/wk on npm | github.com/chartjs/Chart.js | N/A (CDN) | Approved — load via CDN with pinned version `@4.5.1` |
| htmx-ext-sse | CDN/npm (not PyPI) | ~2 yrs | Part of htmx project | github.com/bigskysoftware/htmx | N/A (CDN) | Approved — load via CDN with pinned version `@2.2.4` |

**Packages removed due to slopcheck [SLOP] verdict:** None — `chart.js` and `htmx-ext-sse` flagged SLOP only because they are not PyPI packages; they are CDN-delivered frontend assets and are legitimate.

**Packages flagged as suspicious [SUS]:** None.

---

## Architecture Patterns

### System Architecture Diagram

```
User (browser)
    │ POST /ai/research  (CSRF + HTMX)
    │
    ▼
FastAPI /ai/research
    ├── Quota check → ai_recommendations COUNT (rolling 24h, ai_research type)
    │     └── 429 + HX-Retarget if exhausted
    ├── Cache lookup → ai_coffee_research_cache WHERE cache_key = normalize(input) AND expires_at > now()
    │     └── HIT: load cached response_json → tie prediction → emit event: complete HTML fragment instantly
    │
    └── MISS: acquire advisory lock → EventSourceResponse(async_generator)
              │
              ├── Phase 1: stream summary_prose deltas
              │     Anthropic: client.messages.stream(tools=[web_search, structure_output])
              │     for text in stream.text_stream → yield ServerSentEvent(data=delta, event="message")
              │
              ├── Phase 2: get_final_message() → _project_tool_use_input() → CoffeeResearchSchema.model_validate()
              │     on ValidationError → yield ServerSentEvent(data=error_msg, event="error"); return
              │
              ├── Write ai_coffee_research_cache row
              ├── Write ai_rating_predictions row (or refresh if stale)
              ├── Write ai_recommendations row (cost telemetry, rec_type='coffee_research')
              │
              └── Render research_result.html fragment → yield ServerSentEvent(data=html, event="complete")

Browser (htmx-ext-sse)
    hx-ext="sse" sse-connect="/ai/research-stream?..." sse-swap="complete"
    on "message" events → append delta to prose preview div
    on "complete" event → hx-swap outerHTML of result region
    on "error" event → render error fragment
    EventSource auto-reconnect → advisory lock prevents double-charge
```

### Recommended Project Structure (new files)

```
app/
├── models/
│   ├── ai_coffee_research_cache.py   # D-06 world-view cache table
│   └── ai_rating_prediction.py       # D-07 per-user prediction table
├── services/
│   ├── ai_research.py                # research flow: cache lookup, SSE generator, prediction tying
│   ├── ai_quota.py                   # rolling-24h quota math + cap reader
│   └── charts.py                     # VIZ-01 query helpers
├── migrations/versions/
│   └── p19_ai_research_predict.py    # both new tables + app_settings quota rows + indexes
├── routers/
│   └── ai.py (modified)              # add research, improve-brew, quota, coach, chart routes
│       OR ai_research.py (new)       # planner's discretion
├── templates/fragments/ai/
│   ├── research_form.html            # input form + quota counter + result mount
│   ├── research_result.html          # compact result card (D-03)
│   ├── research_quota_exhausted.html # 429 inline error
│   ├── preference_profile_prose.html # replaces structured preference card
│   ├── trends_card.html              # two canvas + Alpine chart glue
│   └── coach_brew_picker.html        # session picker (inline x-show expandable)
├── templates/fragments/brew/
│   └── improve_result.html           # inline result on brew edit page
└── static/js/alpine-components/
    └── chart-trends.js               # Alpine.data('chartTrends') — CSP-clean
```

### Pattern 1: SSE EventSourceResponse with Two-Phase Streaming

**What:** Stream prose deltas in phase 1, validate structured output in phase 2, emit final HTML as `event: complete`.

**When to use:** Any flow requiring both visible streaming (prose) and a validated Pydantic schema (structured fields).

**Why two-phase:** Anthropic's structured output (tool-use) schema suppresses `text_stream` when tools are active — the model writes directly into the tool `input` JSON. To get prose streaming AND validated fields in one flow, use: (a) a two-tool prompt (one `web_search` server tool + one custom `structure_output` tool), (b) stream `text_stream` while the model reasons/searches, (c) after stream completes call `get_final_message()` to extract the `tool_use` block with the structured fields, (d) validate with Pydantic.

**Key insight from existing code:** `_project_tool_use_input` is the critical security layer — call it on `stream.get_final_message().content`, not on intermediate events.

```python
# Source: anthropic-sdk-python helpers.md (verified 2026-05-28)
# + app/services/ai_service.py existing pattern

from sse_starlette.sse import EventSourceResponse, ServerSentEvent
from anthropic import AsyncAnthropic

async def _research_sse_generator(request, user_id, coffee_name, roaster_name, db):
    """Two-phase: stream prose deltas, then validate structured output."""
    client = AsyncAnthropic(api_key=cred.key, max_retries=1)
    
    # Phase 1: stream text deltas
    async with client.messages.stream(
        model=cred.model_name,
        max_tokens=2000,
        system=SYSTEM_PROMPT_VOICE,
        messages=[{"role": "user", "content": prompt}],
        tools=[WEB_SEARCH_TOOL, STRUCTURE_OUTPUT_TOOL],
    ) as stream:
        async for text in stream.text_stream:
            if await request.is_disconnected():
                return
            yield ServerSentEvent(data=text, event="message")
        
        # Phase 2: extract and validate structured output
        final_msg = await stream.get_final_message()
    
    try:
        raw = _project_tool_use_input(final_msg.content, "structure_output")
        result = CoffeeResearchSchema.model_validate(raw)
    except (ValueError, ValidationError) as exc:
        yield ServerSentEvent(data="Could not parse result. Try again.", event="error")
        return
    
    # Write cache, prediction, telemetry rows...
    # Render final fragment
    html = templates.get_template("fragments/ai/research_result.html").render(...)
    yield ServerSentEvent(data=html, event="complete")

@router.post("/research-stream")
async def post_research_stream(request: Request, ...):
    # quota check, cache check, advisory lock...
    return EventSourceResponse(
        _research_sse_generator(request, user_id, coffee_name, roaster_name, db),
        headers={"X-Accel-Buffering": "no"},  # NPM buffering guard
    )
```

### Pattern 2: SSE Client-Side with htmx-ext-sse@2.2.4

```html
<!-- Source: htmx.org/extensions/sse/ (verified 2026-05-28) -->
<!-- Load in base.html with nonce (D-16) -->
<script defer src="https://cdn.jsdelivr.net/npm/htmx-ext-sse@2.2.4/dist/sse.js"
        nonce="{{ csp_nonce(request) }}"></script>

<!-- In research form fragment -->
<div id="research-result-region"
     hx-ext="sse"
     sse-connect="/ai/research-stream"
     sse-close="complete error"
     hx-swap="outerHTML">
  <!-- prose preview accumulates here via "message" events -->
  <div id="prose-preview" hx-swap="beforeend" hx-trigger="sse:message">
  </div>
</div>
```

**HTMX SSE event contract (verified):**
- `event: message` → prose delta text; append to preview region
- `event: complete` → final HTML fragment; replace result region via `sse-swap="complete"` + `hx-swap="outerHTML"`
- `event: error` → error fragment; replace result region
- `sse-close="complete error"` closes the EventSource when either terminal event fires

**Advisory lock + reconnect:** The existing `_get_lock(user_id, "coffee_research")` pattern holds the lock across the generator lifetime. Native EventSource reconnect (exponential backoff in `htmx-ext-sse`) triggers a new POST → the quota check fires → if the lock is held by the original generator, a 429 is returned before a new SSE stream starts. This prevents double-charge.

### Pattern 3: Rolling 24h Quota Math

**What:** DB COUNT on `ai_recommendations` within the last 24 hours for the given user and rec_type. No in-memory state.

**When:** Quota check before every research LLM call.

```python
# Source: inferred from existing ai_recommendations model + analytics.py patterns
from datetime import datetime, timedelta, UTC
from sqlalchemy import func, select

def count_research_calls_last_24h(db: Session, user_id: int, rec_type: str) -> int:
    """Count successful LLM-fired calls in the rolling 24h window."""
    since = datetime.now(UTC) - timedelta(hours=24)
    return db.scalar(
        select(func.count(AIRecommendation.id)).where(
            AIRecommendation.user_id == user_id,
            AIRecommendation.recommendation_type == rec_type,
            AIRecommendation.error_status.is_(None),  # successful only
            AIRecommendation.generated_at >= since,
        )
    ) or 0

def get_quota_reset_time(db: Session, user_id: int, rec_type: str) -> datetime | None:
    """Return when the oldest call in the 24h window expires (quota reset time)."""
    since = datetime.now(UTC) - timedelta(hours=24)
    oldest_at = db.scalar(
        select(func.min(AIRecommendation.generated_at)).where(
            AIRecommendation.user_id == user_id,
            AIRecommendation.recommendation_type == rec_type,
            AIRecommendation.error_status.is_(None),
            AIRecommendation.generated_at >= since,
        )
    )
    if oldest_at is None:
        return None
    return oldest_at + timedelta(hours=24)
```

**"Resets in Hh Mm" computation:** `reset_time - now()` → hours + minutes. Render server-side as a static string (not a JS countdown — avoids eval/CSP).

### Pattern 4: Lazy TTL Cache Eviction

**What:** On every cache read, sweep expired rows for the queried key (lazy eviction). No background job.

```python
def get_cached_research(db: Session, cache_key: str) -> AICoffeeResearchCache | None:
    """Read cache row, evicting expired rows lazily at read time."""
    now = datetime.now(UTC)
    # Delete expired row for this key if present (lazy eviction, D-06)
    db.execute(
        delete(AICoffeeResearchCache).where(
            AICoffeeResearchCache.cache_key == cache_key,
            AICoffeeResearchCache.expires_at <= now,
        )
    )
    return db.scalar(
        select(AICoffeeResearchCache).where(
            AICoffeeResearchCache.cache_key == cache_key,
        )
    )
```

**Cache key normalization:** `(coffee_name.lower().strip() + "|" + (roaster_name or "").lower().strip())` — roaster_name empty string when omitted. Case-insensitive, leading/trailing whitespace stripped. Same key derivation in both write and read paths.

### Pattern 5: Signature-Versioned Prediction Refresh

**What:** Before rendering a research result, check if the user's prediction row is stale (signature mismatch OR past `expires_at`). If stale, regenerate prediction only (not the world-view cache).

```python
def get_or_refresh_prediction(
    db: Session, user_id: int, cache_key: str, cache_row: AICoffeeResearchCache,
    current_signature: str
) -> AIRatingPrediction | None:
    pred = db.scalar(
        select(AIRatingPrediction).where(
            AIRatingPrediction.user_id == user_id,
            AIRatingPrediction.research_cache_key == cache_key,
        )
    )
    now = datetime.now(UTC)
    if pred is None or pred.expires_at <= now or pred.input_signature != current_signature:
        # Regenerate prediction (cheap: no web search, uses cache_row for coffee facts)
        pred = _generate_rating_prediction(db, user_id, cache_row, current_signature)
    return pred
```

### Pattern 6: Chart.js v4 CSP-Clean Initialization

**What:** Load Chart.js via CDN with nonce. Avoid inline style injection. Dark-mode reactive via Alpine watching `document.documentElement.classList`.

**CSP constraint:** Chart.js v4 requires `style-src 'unsafe-inline'` ONLY if it applies inline styles to the canvas element. The workaround: set `width` and `height` HTML attributes on `<canvas>` (px values) and `maintainAspectRatio: false` in chart options. Chart.js respects explicit canvas size and skips the style injection.

```html
<!-- In base.html: load with nonce -->
<script defer src="https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js"
        nonce="{{ csp_nonce(request) }}"></script>

<!-- In trends_card.html -->
<div x-data="chartTrends({{ ratings_json|tojson }}, {{ flavors_json|tojson }})"
     x-init="init()">
  <canvas id="rating-chart" width="100%" height="220"
          style="display:block;max-width:100%"></canvas>
  <canvas id="flavor-chart" width="100%" height="300"
          style="display:block;max-width:100%"></canvas>
</div>
```

**Note on `style` attribute:** The two `style="display:block;max-width:100%"` attributes on the canvas are static (not injected by Chart.js). They need `style-src 'unsafe-inline'` OR must be moved to a CSS class in `tailwind.src.css`. Prefer the CSS class approach: `.chart-canvas { display: block; max-width: 100%; }`.

```javascript
// Source: app/static/js/alpine-components/chart-trends.js
// Alpine.data pattern matches existing components (base.html loads before Alpine boots)
// [ASSUMED] — pattern inferred from existing Alpine component files

Alpine.data('chartTrends', (ratingsData, flavorsData) => ({
    ratingChart: null,
    flavorChart: null,
    
    init() {
        this.createCharts();
        // Watch <html> classList for dark class (Tailwind v3 darkMode:'selector')
        const observer = new MutationObserver(() => this.updateTheme());
        observer.observe(document.documentElement, {
            attributes: true, attributeFilter: ['class']
        });
    },
    
    isDark() {
        return document.documentElement.classList.contains('dark');
    },
    
    createCharts() {
        const dark = this.isDark();
        const lineColor = dark ? '#e8d5b0' : '#5C2E0A'; // cream-200 / espresso-700
        const gridColor = dark ? '#3d1a0a33' : '#d4b89833';
        
        this.ratingChart = new Chart(document.getElementById('rating-chart'), {
            type: 'line',
            data: {
                labels: ratingsData.map(d => d.date),
                datasets: [{ data: ratingsData.map(d => d.rating), borderColor: lineColor,
                    pointRadius: 4, tension: 0.3 }]
            },
            options: {
                maintainAspectRatio: false,
                scales: { y: { min: 0, max: 5 }, x: { grid: { color: gridColor } } },
                plugins: { legend: { display: false } }
            }
        });
        // ... flavorChart horizontal bar similarly
    },
    
    updateTheme() {
        if (!this.ratingChart) return;
        const dark = this.isDark();
        const lineColor = dark ? '#e8d5b0' : '#5C2E0A';
        this.ratingChart.data.datasets[0].borderColor = lineColor;
        this.ratingChart.update();
        // same for flavorChart
    }
}));
```

### Pattern 7: New Schema Definitions (extending ai_schemas.py)

```python
# Source: ai_schemas.py conventions (extra="forbid" required, summary_prose convention)

class RecipeSuggestionSchema(BaseModel):
    """D-11: Drop no_match; add required ratio/temp_c/grind_hint."""
    model_config = ConfigDict(extra="forbid")
    recipe_id: int | None = Field(None, ...)
    recipe_name: str | None = Field(None, ...)
    summary: str = Field(...)
    ratio: str = Field(description="e.g. '1:15' coffee-to-water ratio")
    temp_c: int = Field(description="Brew water temperature in Celsius")
    grind_hint: str = Field(description="e.g. 'medium-fine, ~22 clicks Encore'")

class CoffeeResearchSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    coffee_name: str = Field(...)
    roaster_name: str | None = Field(None, ...)
    origin: str | None = Field(None, ...)
    process: str | None = Field(None, ...)
    roast_level: str | None = Field(None, ...)
    tasting_notes: list[str] = Field(default_factory=list, ...)
    buy_url: str | None = Field(None, description="https:// only; null if not found")
    sources: list[str] = Field(default_factory=list, description="Cited source URLs")
    summary_prose: str = Field(description="2-3 sentence narrative for the result card")

class RatingPredictionSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    predicted_low: float = Field(ge=0, le=5, description="Lower bound, 0.25 increments")
    predicted_high: float = Field(ge=0, le=5, description="Upper bound, 0.25 increments")
    confidence: Literal["Low", "Medium", "High"] = Field(...)
    reasoning: str = Field(description="1-2 sentence 'Why:' block for the result card")

class BrewParameterChangeSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parameter: Literal["grind", "ratio", "temp_c", "brewer", "recipe"] = Field(...)
    suggested_value: str = Field(...)
    rationale: str = Field(description="1-2 sentence rationale")

class BrewImproveSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary_prose: str = Field(description="2-3 sentence coaching narrative")
    unchanged_parameters: list[str] = Field(
        description="Dial settings the user already tried (LLM sanity check)"
    )
    next_try: list[BrewParameterChangeSchema] = Field(
        description="Ordered list of parameter changes to attempt next"
    )

class PreferenceProfileProseSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary_prose: str = Field(
        description="In-depth AI prose cross-cutting flavor × process × origin × varietal × rating"
    )
```

### Anti-Patterns to Avoid

- **Streaming structured-output-only call without prose phase:** Anthropic's tool_use schema suppresses the text stream. Do not try to `async for text in stream.text_stream` when using only a `structure_output` tool — no text events will fire. Use text_stream only when the model has a text reasoning phase (two-tool approach) or when generating prose schemas (BrewImproveSchema.summary_prose, PreferenceProfileProseSchema.summary_prose).
- **Calling `_verify_buy_url` inside the SSE generator:** The URL verifier is async + network-bound. Call it as a `BackgroundTask` after the SSE stream closes, same pattern as `_verify_and_persist_url` in `ai.py`.
- **Quota check inside the SSE generator:** Check quota BEFORE initiating the EventSourceResponse. An SSE stream that starts and then returns 429 mid-stream confuses HTMX swap.
- **Putting advisory lock inside EventSourceResponse generator:** The lock MUST be acquired before `EventSourceResponse(generator)` is returned. The generator is lazy — FastAPI doesn't start it until the response is sent. Use `asyncio.wait_for` with a timeout to avoid infinite lock waits.
- **Relying on in-memory throttle for quota (research quota):** Unlike the 5-minute `_THROTTLE` dict, research quota is DB-backed because it must survive process restart and be visible to the admin settings UI.
- **Loading Chart.js before Alpine:** Chart.js initialization fires in the Alpine `x-init` callback. Chart.js must load before Alpine finishes booting and processes `x-data`. Add the Chart.js CDN script tag BEFORE the Alpine CDN tag in `base.html` (use `defer` on both — they execute in DOM order when both use `defer`).
- **Using `|safe` to render AI prose:** Never. All prose renders through Jinja2 autoescaping. Newlines → `<br>` via `|replace('\n', '<br>')` or a custom Jinja filter, never `|safe`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SSE framing / keepalive / reconnect | Custom StreamingResponse with manual SSE formatting | `sse-starlette` `EventSourceResponse` | Handles ping, spec-compliant framing, client disconnect detection |
| Chart rendering | Canvas 2D drawing API | Chart.js v4 | Animation, responsive resize, axis labels, tooltip — 30K LOC of edge cases |
| SSE client reconnect logic | Vanilla EventSource with manual retry | `htmx-ext-sse@2.2.4` | HTMX-integrated swap, exponential backoff, htmx events |
| Citation projector (T-07-02) | New extraction logic | Existing `_project_tool_use_input` | Security-critical; already reviewed; verbatim reuse mandatory |
| SSRF-hardened URL verifier | New HTTP client | Existing `_verify_buy_url` + `_assert_public_host` | Security-critical; scheme allowlist + IP gate + redirect block; verbatim reuse |
| Provider client construction | New API key fetch + client init | Existing `_build_anthropic_client` / `_build_openai_client` | Key handling (T-07-03); no key ever logged |

**Key insight:** Every security-critical primitive in `ai_service.py` was built, reviewed, and hardened in Phases 7 and 14. Phase 19 extends by addition, not substitution. Any new AI flow function must call these primitives — not reimplement them.

---

## Common Pitfalls

### Pitfall 1: SSE Behind NPM Without proxy_buffering Off

**What goes wrong:** EventSource connection opens successfully, but the browser receives all SSE events in a burst after the stream completes — not incrementally. Looks like polling.

**Why it happens:** Nginx Proxy Manager (OpenResty under the hood) buffers the upstream response by default. `text/event-stream` is not automatically excluded.

**How to avoid:** Add to the NPM Advanced Config for the Snobbery proxy host:
```nginx
proxy_buffering off;
proxy_http_version 1.1;
proxy_read_timeout 300s;
proxy_send_timeout 300s;
```
AND add `X-Accel-Buffering: no` response header from the backend (defense-in-depth — `sse-starlette` does NOT add this automatically in v3.x).

**Warning signs:** SSE spinner appears to hang until the full response arrives; all delta events appear simultaneously.

**Verification:** Smoke test SSE flows end-to-end through NPM before closing the phase, not just locally.

### Pitfall 2: Double-Charge on EventSource Reconnect

**What goes wrong:** Browser's EventSource reconnects after a network hiccup; a second research LLM call fires for the same user/coffee; cost doubles.

**Why it happens:** `htmx-ext-sse` implements exponential backoff reconnect. A new POST to the SSE endpoint triggers the research flow again before the first call completes.

**How to avoid:** The existing `_get_lock(user_id, "coffee_research")` pattern prevents double-entry: if the lock is held (first call in progress), the second POST returns 429 before the generator starts. The advisory lock covers the PostgreSQL layer for the same guarantee.

**Warning signs:** `ai_recommendations` table shows duplicate `coffee_research` rows with identical `cache_key` within seconds of each other.

### Pitfall 3: Chart.js Inline Style CSP Violation

**What goes wrong:** Chart.js sets `style` attributes on the canvas element for dimensions. Strict `style-src` without `'unsafe-inline'` blocks this, causing a CSP violation logged to the console and potentially broken chart rendering.

**Why it happens:** Chart.js v4 (including v4.5.1) applies responsive sizing via inline style. [CITED: github.com/chartjs/Chart.js/issues/8108]

**How to avoid:**
1. Set explicit `width` and `height` attributes on the `<canvas>` element (px values or responsive via CSS class).
2. Set `maintainAspectRatio: false` in chart options.
3. Move canvas sizing to a CSS class in `tailwind.src.css` rather than inline style (avoids `unsafe-inline` for that element).
4. Do NOT enable `style-src 'unsafe-inline'` — it would weaken the global CSP.

**Warning signs:** Browser console shows `Content-Security-Policy: The page's settings blocked a resource` for `style-src` on the canvas element.

### Pitfall 4: `no_match=true` Tests Fail After Schema Change

**What goes wrong:** Existing tests for `RecipeSuggestionSchema` that construct `no_match=True` instances fail with `ValidationError` after D-11 removes the field.

**Why it happens:** D-11 drops `no_match` entirely. `ConfigDict(extra="forbid")` rejects it. Any test factory or fixture that passes `no_match=True` breaks.

**How to avoid:** Search for `no_match` in all test files before the wave that modifies `ai_schemas.py`. Update every occurrence. The planner lists this as a Wave 0 dependency in `test_ai_service.py`.

**Warning signs:** `test_schemas_importable`, `test_coffee_rec_schema_validate_complete` pass but new tests building `RecipeSuggestionSchema(no_match=True)` raise `ValidationError`.

### Pitfall 5: Alpine Component Loads After Chart.js Init

**What goes wrong:** `new Chart(...)` is called before Chart.js has loaded, throwing `ReferenceError: Chart is not defined`.

**Why it happens:** `defer` scripts execute in DOM order, but only if they appear before the triggering element. If `chart-trends.js` is a `defer` script that appears before the Chart.js CDN tag, it may run first on some browsers.

**How to avoid:** Add the Chart.js `<script defer src="...">` tag in `base.html` BEFORE the `chart-trends.js` component `<script>` tag. Both use `defer`, so they execute in source order after DOM parsing. The Alpine CSP core must remain last (after all component registrations).

**Load order in base.html:**
```html
<!-- 1. All Alpine component registrations (defer) -->
<script defer src="/static/js/alpine-components/chart-trends.js" nonce="..."></script>
<!-- 2. Chart.js CDN (defer) — must precede Alpine CSP so Chart is defined when init() runs -->
<script defer src="https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js" nonce="..."></script>
<!-- 3. htmx-ext-sse CDN (defer) -->
<script defer src="https://cdn.jsdelivr.net/npm/htmx-ext-sse@2.2.4/dist/sse.js" nonce="..."></script>
<!-- 4. Alpine CSP core — ALWAYS LAST (already in base.html) -->
<script defer src="https://cdn.jsdelivr.net/npm/@alpinejs/csp@3.15.12/dist/cdn.min.js" nonce="..."></script>
```

**Wait:** The Alpine component (`chart-trends.js`) registers `Alpine.data('chartTrends', ...)` which is a function definition — it does NOT call `new Chart()` at registration time. Chart.js is only called inside `init()`, which Alpine fires after it boots and processes `x-data`. Since Alpine boots last (after all `defer` scripts), Chart.js is always loaded before `init()` is called. The order constraint is therefore: chart-trends.js must precede Alpine CSP, which is already the existing pattern. Chart.js CDN can appear anywhere before Alpine CSP.

### Pitfall 6: Scheduler Skips New Rec Types

**What goes wrong:** `preference_profile_prose` and (if applicable) `brew_improvement` rows are never regenerated nightly despite signature changes.

**Why it happens:** `run_nightly_ai_refresh` calls `regenerate(uid, "scheduler", db=db)` which only handles `rec_type="coffee"`. New rec types are not yet in the scheduler's iteration loop.

**How to avoid:** Extend the nightly job to iterate over the list of active rec_types: `["coffee", "sweet_spots", "preference_profile_prose"]`. Each gets its own `regenerate()` call variant. Note: `brew_improvement` is on-demand (per-session) — it does NOT belong in the nightly loop.

**Warning signs:** `ai_recommendations` table shows stale `preference_profile_prose` rows with old `input_signature` days after a user logs new sessions.

### Pitfall 7: Stale Service Worker Caches New Dynamic Endpoints

**What goes wrong:** `/ai/research-stream`, `/ai/charts/rating-over-time`, `/ai/charts/flavor-distribution` are served from the SW cache, returning stale empty JSON or old SSE streams.

**Why it happens:** The service worker's `network-first` strategy covers `/` but may not cover new path prefixes.

**How to avoid:** Verify `sw.js` routes for the new endpoints. SSE streams are inherently non-cacheable (`Cache-Control: no-cache` set by `sse-starlette`). Chart JSON endpoints should be network-first or excluded from cache. The SW cache version auto-bumps on content change (project memory `c9-sw-cache-content-deterministic`) — no manual bump needed for the new endpoints as long as the SW's routing handles them correctly.

### Pitfall 8: settings.py `SettingNotFoundError` on New Quota Keys

**What goes wrong:** `settings_service.get_int("ai.research_daily_quota")` raises `SettingNotFoundError` because the migration that INSERTs the default rows hasn't run yet (or ran but `prewarm_cache` was called before the migration).

**Why it happens:** `settings.py` reads from the in-memory cache pre-warmed at lifespan startup. New `app_settings` rows added by a migration are not picked up until the next `prewarm_cache()` call (i.e., next container restart).

**How to avoid:** The migration must INSERT the two new `app_settings` rows. Since migrations run before lifespan (via `entrypoint.sh` → `alembic upgrade head` before uvicorn starts), the rows will be present when `prewarm_cache()` runs. Use `get_int("ai.research_daily_quota") or 20` as a defensive fallback in the quota reader for the first deploy.

---

## Code Examples

### SSE EventSourceResponse (verified pattern)

```python
# Source: sysid/sse-starlette README + github.com (verified 2026-05-28)
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

async def _event_generator(request):
    for i in range(5):
        if await request.is_disconnected():
            break
        yield ServerSentEvent(data=f"chunk {i}", event="message")
    yield ServerSentEvent(data="<div>final html</div>", event="complete")

@router.post("/ai/research-stream")
async def post_research_stream(request: Request, ...):
    return EventSourceResponse(
        _event_generator(request),
        headers={"X-Accel-Buffering": "no"},
    )
```

### Anthropic Async Stream + get_final_message

```python
# Source: anthropic-sdk-python helpers.md (verified 2026-05-28)
from anthropic import AsyncAnthropic

client = AsyncAnthropic(api_key=cred.key, max_retries=1)

async with client.messages.stream(
    model=cred.model_name,
    max_tokens=2000,
    messages=[...],
    tools=[WEB_SEARCH_TOOL, STRUCTURE_OUTPUT_TOOL],
) as stream:
    async for text in stream.text_stream:
        yield ServerSentEvent(data=text, event="message")
    final_msg = await stream.get_final_message()

raw = _project_tool_use_input(final_msg.content, "structure_output")
result = CoffeeResearchSchema.model_validate(raw)
usage = final_msg.usage  # .input_tokens, .output_tokens
```

### Rolling 24h Quota Counter Fragment

```html
{# fragments/ai/research_form.html — quota counter rendered eagerly on page load #}
<p class="text-sm text-espresso-600 dark:text-cream-400">
  {% if remaining > 0 %}
    {{ remaining }}/{{ cap }} research calls remaining today
  {% else %}
    Resets in {{ reset_h }}h {{ reset_m }}m
  {% endif %}
</p>
<button type="submit"
        {% if remaining == 0 %}disabled{% endif %}
        hx-post="/ai/research"
        hx-target="#research-result"
        hx-indicator="#research-spinner"
        class="...">
  <span class="htmx-indicator" id="research-spinner">
    {# Spinner SVG defined in tailwind.src.css — project memory strict-csp-blocks-htmx-indicator #}
  </span>
  Research
</button>
```

### Latency Investigation Query (D-15)

```sql
-- Run against ai_recommendations to capture current p50/p95 per rec_type
SELECT
    recommendation_type,
    COUNT(*) AS call_count,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY duration_ms) AS p50_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_ms
FROM ai_recommendations
WHERE
    generated_at >= NOW() - INTERVAL '30 days'
    AND error_status IS NULL
    AND duration_ms IS NOT NULL
GROUP BY recommendation_type
ORDER BY p95_ms DESC;
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Polling `/home/cards/ai-recommendation` for recommendation | SSE streaming via `sse-starlette` + `htmx-ext-sse@2.2.4` | Phase 19 | Eliminates polling spinner; visible token stream |
| `no_match=true` sentinel in `RecipeSuggestionSchema` | Drop `no_match`; require `ratio`, `temp_c`, `grind_hint` | Phase 19 | Pydantic enforces contract; no more nil recipe responses |
| Preference Profile as structured rows (origin/process pills) | AI prose via `PreferenceProfileProseSchema` | Phase 19 | Richer narrative; easier to read on mobile |
| `ai_recommendations` for all AI storage | Two new tables: `ai_coffee_research_cache` (shared) + `ai_rating_predictions` (per-user) | Phase 19 | Cleanly separates world-view vs personal view; different TTLs |
| HTMX polling indicator (see Phase 7 pattern) | `hx-indicator` + spinner in `tailwind.src.css` (D-13) | Phase 19 | CSP-clean; consistent across all AI flows |
| No trend charts | Chart.js v4 line + horizontal bar via CDN | Phase 19 | VIZ-01 fulfilled; CSP-nonce-compatible |

**Deprecated/outdated:**
- `no_match` field in `RecipeSuggestionSchema`: removed by D-11. All tests referencing it must be updated.
- `fragments/research_coming_soon.html`: deleted by Phase 19. The include in `pages/ai.html` is replaced by the actual research form.
- Top Flavor Descriptors lazy mount in `pages/ai.html` (line 72–84): deleted by D-10.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Chart.js v4.5.1 does not use `eval` (CSP `script-src` nonce sufficient) | Chart.js Integration, Pitfall 3 | If eval is used, CSP will block chart rendering entirely — test in browser before releasing |
| A2 | Alpine `x-init` fires after all `defer` scripts complete, ensuring Chart.js is loaded | Pitfall 5 | Charts silently fail to initialize on first load |
| A3 | `htmx-ext-sse@2.2.4` CDN URL `https://cdn.jsdelivr.net/npm/htmx-ext-sse@2.2.4/dist/sse.js` is the correct pinned path | SSE client pattern | Wrong URL causes 404; SSE connection silently falls back to no-op |
| A4 | NPM (Nginx Proxy Manager) requires explicit `proxy_buffering off` in Advanced config — `X-Accel-Buffering: no` header alone is insufficient | Pitfall 1, NPM SSE section | SSE events arrive in burst (effectively no streaming) behind NPM |
| A5 | OpenAI Responses API streaming with tool use follows a similar two-phase pattern to Anthropic | SSE streaming reconciliation | OpenAI fallback path may not stream prose; would silently degrade to non-streaming on OpenAI |
| A6 | `ai_recommendations.recommendation_type` is TEXT (not a DB enum) | Existing ai_recommendation.py model | Adding new rec_types ('coffee_research', 'brew_improvement', 'preference_profile_prose') requires only application-level validation |
| A7 | No brew session detail page exists; improve-brew button attaches to the edit page (`/brew/{id}/edit`) | D-12 / brew router analysis | If a detail page is added separately, the button placement needs revisiting |
| A8 | The settings cache invalidation pattern (`_cache.pop(key, None)` after commit) works correctly for the two new quota keys on first deploy | Pitfall 8 | `SettingNotFoundError` on first request after migration if cache is warmed before migration commits |

---

## Open Questions

1. **OpenAI Responses API streaming with tool use**
   - What we know: Anthropic's `client.messages.stream()` + `get_final_message()` pattern is well-documented and verified. OpenAI 2.x Responses API supports `stream=True`.
   - What's unclear: Whether OpenAI 2.x's streaming response exposes incremental text deltas (for the prose streaming phase) when tool calls are in use.
   - Recommendation: For the OpenAI fallback path, use a non-streaming structured call for research/improve-brew (same as today's `_openai_coffee_call`). Only stream on the Anthropic path. The fallback is rare and the quality difference (no prose preview) is acceptable.

2. **SSE advisory lock release timing**
   - What we know: `_try_advisory_lock` holds the lock for the transaction lifetime. The SSE generator is async and holds the lock across network I/O (LLM call).
   - What's unclear: Whether wrapping the generator in a transaction that spans the entire SSE stream duration is the right approach. Long-running transactions can increase lock contention.
   - Recommendation: Acquire the advisory lock in a short pre-check transaction. Track in-flight state in `_LOCKS` dict (process-local, same as today). The process-local lock is sufficient for single uvicorn worker; the advisory lock provides a Postgres-level backstop for reconnect.

3. **Two-phase streaming: prose quality**
   - What we know: When using tool_use, Anthropic's model may produce minimal or no text stream (the model reasons in the tool input JSON, not in text blocks).
   - What's unclear: Whether the Anthropic model produces meaningful `text_stream` deltas alongside `web_search` + `structure_output` tool use.
   - Recommendation: If text deltas are sparse, fall back to a skeleton prose template rendered immediately ("Researching {coffee_name}...") with CSS pulse animation, then replace on `event: complete`. This is a client-side UX decision; the planner documents behavior in the plan.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `sse-starlette` | D-16 SSE flows | Must install | 3.4.4 (PyPI) | None — install required |
| Chart.js v4.5.1 | VIZ-01 charts | CDN (always available) | 4.5.1 | Inline `<script>` fallback if CDN down (not needed) |
| `htmx-ext-sse@2.2.4` | D-16 SSE client | CDN (always available) | 2.2.4 | — |
| PostgreSQL `PERCENTILE_CONT` | D-15 latency investigation | ✓ (PG 16) | 16 | — |
| PostgreSQL `JSONB` | D-06 cache + D-07 prediction tables | ✓ (already used) | 16 | — |
| NPM `proxy_buffering off` | D-16 SSE through reverse proxy | Must configure | — | Without it: SSE bursts instead of streams (functional but not streaming UX) |

**Missing dependencies with no fallback:**
- `sse-starlette`: add `sse-starlette>=3.4,<4` to `requirements.txt` in Wave 0.

**Missing dependencies requiring configuration (not code):**
- NPM Advanced Config: planner adds `proxy_buffering off` block; operator must apply it to the proxy host. Document in CONTRIBUTING.md.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio |
| Config file | `pytest.ini` or `pyproject.toml` (check existing) |
| Quick run command | `docker compose exec coffee-snobbery python -m pytest tests/services/test_ai_research.py tests/services/test_ai_quota.py -x -q` |
| Full suite command | `docker compose exec coffee-snobbery python -m pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AIX-01 | CoffeeResearchSchema validates complete + rejects extra fields | unit | `pytest tests/services/test_ai_research.py::test_coffee_research_schema_validates -x` | ❌ Wave 0 |
| AIX-01 | Cache miss triggers LLM call; cache hit skips LLM | unit (mock) | `pytest tests/services/test_ai_research.py::test_cache_miss_calls_llm tests/services/test_ai_research.py::test_cache_hit_skips_llm -x` | ❌ Wave 0 |
| AIX-02 | RatingPredictionSchema rejects point estimate (low==high only) | unit | `pytest tests/services/test_ai_research.py::test_rating_prediction_schema -x` | ❌ Wave 0 |
| AIX-03 | Research endpoint returns 403/redirect when gate_open=False | integration | `pytest tests/routers/test_ai_research.py::test_research_blocked_below_gate -x` | ❌ Wave 0 |
| AIX-04 | Cache key normalizes case + whitespace; hits same row | unit | `pytest tests/services/test_ai_research.py::test_cache_key_normalization -x` | ❌ Wave 0 |
| AIX-04 | Expired cache row is evicted on read, triggers new LLM call | unit | `pytest tests/services/test_ai_research.py::test_expired_cache_eviction -x` | ❌ Wave 0 |
| AIX-05 | Quota counter returns correct remaining count | unit | `pytest tests/services/test_ai_quota.py::test_quota_count -x` | ❌ Wave 0 |
| AIX-05 | POST /ai/research returns 429 when quota exhausted | integration | `pytest tests/routers/test_ai_research.py::test_research_429_quota_exhausted -x` | ❌ Wave 0 |
| AIX-05 | Reset time computed from oldest call in window | unit | `pytest tests/services/test_ai_quota.py::test_reset_time_computation -x` | ❌ Wave 0 |
| AIX-06 | POST /ai/wishlist/add accepts research-sourced fields | integration (existing) | `pytest tests/routers/test_ai_router.py::test_wishlist_add -x` | ✅ existing |
| AIX-07 | SSE generator yields `event: message`, `event: complete` in order | unit (mock) | `pytest tests/services/test_ai_research.py::test_sse_event_contract -x` | ❌ Wave 0 |
| AIX-07 | Advisory lock blocks second SSE request while first in-flight | unit | `pytest tests/services/test_ai_research.py::test_advisory_lock_blocks_duplicate -x` | ❌ Wave 0 |
| AIX-09 | PreferenceProfileProseSchema has summary_prose field, ConfigDict extra=forbid | unit | `pytest tests/services/test_preference_prose.py::test_preference_prose_schema -x` | ❌ Wave 0 |
| AIX-10 | `.htmx-indicator` styles present in tailwind.src.css | behavioral | `pytest tests/test_pwa.py` (add assertion) or separate test | ❌ Wave 0 (add to existing) |
| AIX-11 | RecipeSuggestionSchema raises ValidationError on no_match field | unit | `pytest tests/services/test_ai_service.py::test_recipe_schema_no_match_rejected -x` | ❌ Wave 0 (modify existing) |
| AIX-11 | RecipeSuggestionSchema requires ratio, temp_c, grind_hint | unit | `pytest tests/services/test_ai_service.py::test_recipe_schema_required_fields -x` | ❌ Wave 0 (modify existing) |
| AIX-12 | BrewImproveSchema validates complete + rejects extra fields | unit | `pytest tests/services/test_brew_improve.py::test_brew_improve_schema -x` | ❌ Wave 0 |
| AIX-12 | POST /ai/improve-brew/{session_id} returns 404 on cross-user session | integration | `pytest tests/routers/test_ai_improve.py::test_improve_brew_cross_user_404 -x` | ❌ Wave 0 |
| AIX-13 | duration_ms written for all new rec_types | unit (mock) | `pytest tests/services/test_ai_research.py::test_duration_ms_written -x` | ❌ Wave 0 |
| AIX-13 | p50/p95 query executes without error against existing data | integration | `pytest tests/services/test_analytics_perf.py::test_latency_percentile_query -x` | ❌ Wave 0 |
| VIZ-01 | GET /ai/charts/rating-over-time returns valid JSON shape | integration | `pytest tests/routers/test_ai_charts.py::test_rating_chart_json -x` | ❌ Wave 0 |
| VIZ-01 | GET /ai/charts/flavor-distribution returns valid JSON shape | integration | `pytest tests/routers/test_ai_charts.py::test_flavor_chart_json -x` | ❌ Wave 0 |
| D-06 | ai_coffee_research_cache table created by migration | migration test | `pytest tests/test_migrations.py` (extends existing) | ❌ Wave 0 |
| D-07 | ai_rating_predictions table created; UNIQUE constraint enforced | migration test | `pytest tests/test_migrations.py` | ❌ Wave 0 |
| D-14 | _verify_buy_url returns False on 404/410 | unit | `pytest tests/services/test_archived_retry.py::test_verify_url_rejects_404 -x` | ❌ Wave 0 |
| D-14 | Coffee rec flow retries with broader search on verify failure | unit (mock) | `pytest tests/services/test_archived_retry.py::test_archived_retry_logic -x` | ❌ Wave 0 |

**Existing tests that will break after D-11 (must fix in the same wave):**

```bash
# Search for no_match usage before planning waves
grep -rn "no_match" tests/
```

Expected hits: `tests/services/test_ai_service.py` — update to test new `ratio`/`temp_c`/`grind_hint` fields instead.

### Sampling Rate
- **Per task commit:** `python -m pytest tests/services/test_ai_research.py tests/services/test_ai_quota.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd-verify-work` + SSE smoke test through NPM

### Wave 0 Gaps

- [ ] `tests/services/test_ai_research.py` — schema validation, cache logic, SSE event contract, advisory lock
- [ ] `tests/services/test_ai_quota.py` — rolling-24h COUNT, reset time, admin cap reader
- [ ] `tests/services/test_brew_improve.py` — BrewImproveSchema, prior-sessions loading
- [ ] `tests/services/test_preference_prose.py` — PreferenceProfileProseSchema
- [ ] `tests/services/test_archived_retry.py` — `_verify_buy_url` 404/410 behavior, retry logic
- [ ] `tests/routers/test_ai_research.py` — POST research endpoint, 429 quota, gate check
- [ ] `tests/routers/test_ai_improve.py` — POST improve-brew, IDOR 404
- [ ] `tests/routers/test_ai_charts.py` — GET chart JSON endpoints
- [ ] Update `tests/services/test_ai_service.py` — remove `no_match=True` usage; add `ratio`/`temp_c`/`grind_hint` tests
- [ ] `app/migrations/versions/p19_ai_research_predict.py` — new tables + app_settings rows
- [ ] `app/models/ai_coffee_research_cache.py` — new model
- [ ] `app/models/ai_rating_prediction.py` — new model
- [ ] Framework install: `sse-starlette>=3.4,<4` to requirements.txt

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | All routes gated by `Depends(require_user)` (existing) |
| V3 Session Management | no | Existing session infrastructure unchanged |
| V4 Access Control | yes | Research quota keyed to `request.state.user.id` (never form param); IDOR: improve-brew `GET /brew/{session_id}` verifies user ownership |
| V5 Input Validation | yes | `CoffeeResearchSchema` / `BrewImproveSchema` with `extra="forbid"` (T-07-02 prompt injection defense); cache key normalization; CSRF on all POST forms |
| V6 Cryptography | no | No new cryptographic surfaces |
| V7 Error Handling | yes | SSE `event: error` must not leak stack traces; log with structlog, return user-facing message only |
| V10 Malicious Code | yes | `_project_tool_use_input` MUST be used on all tool_use responses — do not pass raw content to Pydantic (T-07-02) |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection via web-search results in AI response | Tampering | `_project_tool_use_input` discards all non-tool_use blocks; `ConfigDict(extra="forbid")` rejects injected fields (T-07-02 — existing) |
| SSRF via AI-provided buy_url | Spoofing | `_verify_buy_url` + `_assert_public_host` (T-07-01 — existing, extended for 404/410) |
| Quota bypass via direct POST | Elevation | Quota check uses `request.state.user.id` only; DB-backed count not in-memory |
| Cross-user improve-brew access | Elevation | `brew_sessions_service.get_brew_session(db, session_id, by_user_id=user.id)` returns None/404 on IDOR |
| Cache key collision (different coffees → same key) | Tampering | Normalized key includes both coffee_name AND roaster_name; empty string separator `|` for missing roaster. Not perfect — document as known limitation. |
| SSE stream keeps session alive for attacker reconnect | Repudiation | Advisory lock + process-local lock prevent multiple concurrent generations per user; session expiry still enforced by session sweep |
| AI prose rendered as HTML | Tampering | Jinja2 autoescaping; never `|safe` on AI output; newlines → `<br>` via filter |

---

## Sources

### Primary (HIGH confidence)
- `app/services/ai_service.py` — existing advisory lock, citation projector, URL verifier, client builders (codebase read 2026-05-28)
- `app/services/ai_schemas.py` — schema patterns (codebase read 2026-05-28)
- `app/routers/ai.py` — 429 HX-Retarget pattern, throttle pattern (codebase read 2026-05-28)
- `app/services/analytics.py` — `get_cold_start_counts`, `compute_input_signature` (codebase read 2026-05-28)
- `app/services/scheduler.py` — nightly job rec_type loop (codebase read 2026-05-28)
- `app/models/ai_recommendation.py` — existing cost-observability columns (codebase read 2026-05-28)
- `app/templates/pages/ai.html` — Phase 17 shell composition, lazy-mount stagger pattern (codebase read 2026-05-28)
- pypi.org/project/sse-starlette/ — version 3.4.4, May 12 2026, Production/Stable (verified 2026-05-28)
- github.com/sysid/sse-starlette — EventSourceResponse API, ServerSentEvent fields, async generator pattern (verified 2026-05-28)
- platform.claude.com/docs/en/build-with-claude/streaming — Anthropic SDK stream + get_final_message (verified 2026-05-28)
- github.com/anthropics/anthropic-sdk-python blob/main/helpers.md — async streaming with text_stream, tool_use events (verified 2026-05-28)
- htmx.org/extensions/sse/ — sse-connect, sse-swap, sse-close attributes, CDN URL (verified 2026-05-28)
- github.com/chartjs/Chart.js/releases — v4.5.1 latest stable, Oct 13 2024 (verified 2026-05-28)
- github.com/chartjs/Chart.js/issues/8108 — canvas inline style CSP issue (verified 2026-05-28)

### Secondary (MEDIUM confidence)
- medium.com/@dsherwin/surviving-sse-behind-nginx-proxy-manager-npm — NPM requires `proxy_buffering off` explicitly (single source, verified plausible)
- nginx.org/en/docs/http/ngx_http_proxy_module.html — `X-Accel-Buffering` header behavior (verified)

### Tertiary (LOW confidence)
- WebSearch result on OpenAI 2.x Responses API streaming — needs direct verification against openai SDK before implementing fallback path

---

## Project Constraints (from CLAUDE.md)

| Directive | Impact on Phase 19 |
|-----------|--------------------|
| Python 3.12 + FastAPI, no new framework | sse-starlette is Starlette/FastAPI-native; no framework change |
| No npm build pipeline | Chart.js + htmx-ext-sse via CDN only |
| Jinja2 + HTMX 2.x + Tailwind v3 (darkMode:'selector') + Alpine.js | Chart themes use `.dark` class; never `@custom-variant` |
| CSP nonce on every `<script>` | Chart.js + htmx-ext-sse CDN tags need `nonce="{{ csp_nonce(request) }}"` |
| CSRF on all state-changing forms | Research POST + improve-brew POST both carry CSRF token |
| Single uvicorn worker | Module-level `_LOCKS` dict stays process-local; research quota is DB-backed |
| Mobile-first @ 375px | Trends card, research form, result card all tested at 375px before close |
| Autoescape on all Jinja templates | Never `|safe` on AI prose; use `|replace` for line breaks |
| `ruff format` + `ruff check` before committing | New files must pass; planner includes ruff step in each wave |
| `Mapped[...]` columns + `select()` constructs in SQLAlchemy 2.0 | Both new table models use typed mapped columns |
| `ConfigDict(extra="forbid")` on all AI schemas | All 5 new schemas include this |
| Argon2 + Fernet + itsdangerous for auth | No new auth surfaces; existing middleware unchanged |
| APScheduler in-process, no Celery | New rec_types added to nightly loop; no new scheduler dependency |
| `app/services/encryption.py` for all API key access | New AI flows use `credentials_service.get_provider_credential` (existing pattern) |

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages verified on PyPI/official sources; CDN URLs verified
- SSE pattern: HIGH — Anthropic SDK streaming verified against official docs; two-phase reconciliation MEDIUM (text_stream behavior with tool_use empirically unverified)
- Chart.js CSP: MEDIUM — canvas inline style issue is documented; `no eval` not explicitly stated but inferred from UMD bundle structure
- NPM SSE proxy: MEDIUM — single high-quality source; confirmed plausible given known NPM/OpenResty behavior
- Architecture: HIGH — based on deep codebase read; all integration points located and verified
- Pitfalls: HIGH for scheduler/schema/lock pitfalls (codebase-derived); MEDIUM for Chart.js/SSE/NPM (web-source-derived)

**Research date:** 2026-05-28
**Valid until:** 2026-06-28 (stable libraries; Anthropic SDK fast-moving — check for 0.103+ before implementing)
