# Feature Research: Snobbery v1.2 New Capabilities

**Domain:** Self-hosted household coffee log, pour-over-primary, 2-user, phone-first
**Researched:** 2026-05-25
**Confidence:** HIGH (Beanconqueror sourced from repo + official site); MEDIUM (cafe quick-rate and AI predict-rating modeled from competitor UX + design reasoning)

---

## Scope of this Document

This is a v1.2-specific research artifact focused on three new capabilities proposed for the milestone:

1. Beanconqueror feature parity audit — what to adopt, adapt, or skip
2. Cafe quick-rate — logging a coffee you did not brew yourself
3. AI research-a-coffee + predict-rating — predict a user's rating for a coffee they haven't brewed yet

Existing v1.1 features are already built. This document does not propose rebuilding them.

---

## Section 1: Beanconqueror Feature Parity Audit

### Source inventory

Beanconqueror is an open-source Ionic/Angular mobile coffee tracker (iOS + Android).
Repository: https://github.com/graphefruit/Beanconqueror
Changelog: https://beanconqueror.com/changelog/
Data/tracking page: https://beanconqueror.com/data-tracking/

### Complete feature inventory with Snobbery fit judgment

#### Bean / Bag Management

| Feature | Beanconqueror Description | Snobbery Fit | Verdict | Reason |
|---|---|---|---|---|
| Coffee catalog with roaster info | Name, origin, process, roaster, variety, altitude, notes | **Already exists** (shared catalog: coffees + roasters tables) | ALREADY SHIPPED | v1.1 |
| Bag-as-instance (per-roast-date purchases) | Each purchase is a separate bag with its own roast date, weight, open/finish dates | **Already exists** (bags table, v1.1 Foundation) | ALREADY SHIPPED | v1.1 migration 1 |
| Bag depletion / archive | Track remaining weight; "finish" a bag to archive it, leaving the coffee row intact for reorders | **Already exists** (archived flag on bags) | ALREADY SHIPPED | v1.1 |
| Running total / inventory weight | Track grams remaining per bag against a starting weight; alert when low | **Partially built** — weight_grams column exists; no "low stock" alert or running depletion UI | SKIP FOR v1.2 | Inventory management explicitly deferred to v2 in PROJECT.md. Two-user household; bags run out fast enough that alerts add complexity without value. |
| Freeze/unfreeze portions | Track sub-portions of a bag in the freezer with separate open dates | SKIP | Anti-feature for Snobbery's minimalist identity. Real use case for competition-circuit espresso folks, not pour-over households. |
| Purchase price / FOB price tracking | Price paid per bag, cost-per-brew analytics | **Already exists** (coffees.price_usd; cost-per-brew derived) | ALREADY SHIPPED (price field) | v1.1 analytics |
| Buy date / best-by date tracking | Date bag purchased; best-before date | SKIP | Roast date is the signal for pour-over. Best-by is marketing; days-off-roast already surfaces this. Buy date adds no analytics value for household use. |
| QR code / NFC scanning to import bean data from roasters | Scan roaster-printed QR on bag packaging to auto-populate catalog entry | SKIP | Requires roaster partnership ecosystem Beanconqueror has built. Not available for arbitrary specialty roasters. Brittle for a two-user household with a rotating roster of indie roasters. Beanconqueror FAQ notes the ecosystem is limited to partner roasters. |
| Bean favoriting + filtering | Star a coffee as favorite; filter catalog by favorites | ADAPT — map to wishlist or a "house staple" flag | DEFER | Two-user household; the catalog is small enough to navigate without filtering. Wishlist is already built (v1.1). Revisit if catalog exceeds 50 coffees. |
| Roasting section (green bean + roast batch tracking) | Log green bean purchases, track roast profiles through the roasting process | SKIP | Out of domain. Neither user is a home roaster. Beanconqueror added this for prosumer users. Hard skip. |
| Package-level rating | Rate the whole bag/coffee at purchase vs per-session rating | SKIP | The existing per-session rating aggregation already serves this purpose via analytics. A separate bag-level rating adds data duplication. |

#### Brew Tracking Parameters

| Feature | Beanconqueror Description | Snobbery Fit | Verdict | Reason |
|---|---|---|---|---|
| Core brew params (dose, water, grind, time) | All four captured with freetext grind setting | **Already exists** | ALREADY SHIPPED | v1.1 |
| First drip timing | Time from start to first drops falling | ADAPT as optional field | CONSIDER | Medium complexity (single nullable int column). Useful signal for pour-over — indicates bloom saturation and grind consistency. Low-friction add if it fits in the brew form without crowding. |
| Bloom time / bloom water | Separate tracking of pre-infusion bloom: amount poured, duration | ADAPT as optional field | CONSIDER | Same reasoning as first drip. Bloom is the primary quality lever for most pour-over recipes. One nullable int column (bloom_duration_sec) and one nullable numeric (bloom_water_grams). |
| Yield / brew-out weight | Weight of liquid in the cup after brewing | **Already exists** (brew_sessions.yield_grams per v1.1 spec) | ALREADY SHIPPED | v1.1 |
| TDS and extraction yield | Refractometer TDS%; computed EY% from dose/yield/TDS | **Already exists** (tds_pct, extraction_yield_pct columns, v1.1) | ALREADY SHIPPED | v1.1 |
| Brew ratio (live display) | Dose:water ratio displayed reactively in form | Spec calls for Alpine.js reactive ratio display | ALREADY SHIPPED | v1.1 (Alpine.js reactive field) |
| 30+ customizable brew parameters | App has a parameter system where users can enable/disable which fields show, in which order | SKIP | Over-engineering for a 2-user household. The single-scroll form with sensible defaults already optimizes for sub-30s re-log. Per-user parameter ordering would add admin complexity for zero gain. |
| Beverage-level cupping / SCA aroma scoring | Structured cupping evaluation using SCA categories (fragrance, aroma, flavor, aftertaste, acidity, body, balance, overall) | SKIP | Snobbery's rating is intentionally simple (0-5, 0.25 steps) + free-text flavor notes from a shared vocabulary. SCA cupping is a professional workflow, not a home-brewer-at-the-kettle workflow. It would compete with and confuse the existing rating + flavor note model. |
| Brix measurement / TDS from brix | Convert refractometer Brix reading to estimated TDS | SKIP | Edge case. The TDS field already accepts direct TDS%; brix conversion is a niche within a niche. |
| Per-step pour logging (multiple pours timed) | Log each pour separately (pour 1: 50g at 0:30, pour 2: 100g at 1:30) | CONSIDER as stretch | DEFER to v1.3 | Medium complexity. Genuinely valuable for Tetsu Kasuya-style multi-pour analysis, but adds significant form complexity. Phase it if Guided Brew Mode gets a multi-step timer (natural coupling point). Not a v1.2 priority. |

#### Brew Timer

| Feature | Beanconqueror Description | Snobbery Fit | Verdict | Reason |
|---|---|---|---|---|
| Basic countdown / count-up timer | Start/stop timer visible during brewing | **Already exists** (Guided Brew Mode, v1.1) | ALREADY SHIPPED | v1.1 |
| Background timer (continues when phone sleeps) | Timer keeps running even if screen goes dark | ADOPT | HIGH value. Kettle-side use means the phone WILL sleep. The v1.1 implementation should be verified against iOS background timer behavior. If not already using a Web Worker timer, this is a real gap to plug in Guided Brew Mode polish. Complexity: LOW if using a Web Worker (system clock-based, survives sleep); HIGH if using setInterval. |
| Auto-start timer on weight detection | BLE scale triggers timer start when first grams detected | SKIP | Requires BLE scale integration (anti-feature, see Section 4). |
| Pressure-threshold timer start | Espresso-specific; pressure reading triggers start | SKIP | Espresso-primary feature; not pour-over relevant. |
| Phase-based step timer (bloom, pour1, pour2…) | Recipe steps each have their own timer target | CONSIDER | MEDIUM complexity. Snobbery already has Guided Brew Mode — whether it already supports multi-step timers from recipe steps should be verified. If not, this is the natural v1.2 polish direction for Guided Brew Mode. Worth adopting as part of the Guided Brew polish work. |
| Customizable timer display (hours/min toggle) | Display format options for the running timer | SKIP | Trivial cosmetic; not worth a phase of work. If Guided Brew Mode is polished, this is a one-line change, not a researched feature. |

#### Flow / Pressure Profiling (Bluetooth Scales)

| Feature | Beanconqueror Description | Snobbery Fit | Verdict | Reason |
|---|---|---|---|---|
| BLE scale integration (Acaia, Felicita, Decent, Hiroia, Skale2, Eureka Precisa, Smart Espresso Profiler, Pressensor) | Real-time weight streaming over Bluetooth Web/Native | SKIP | Anti-feature for Snobbery. Web Bluetooth is unreliable across PWA contexts. Pour-over weights are slow enough to enter manually. This is Beanconqueror's primary differentiator; it is not Snobbery's. Weeks of device-specific work for a feature the spec explicitly excludes. |
| Live brew graph (weight vs time) | Real-time graph generated from scale data during brew | SKIP | Depends on BLE; SKIP follows BLE skip. |
| Visualizer.coffee integration | Export/sync to Visualizer for advanced shot analysis | SKIP | Espresso-primary; requires BLE; out of domain. |
| Average flow quantity display | Derived metric from scale data: grams/second average | SKIP | Requires BLE. |
| Pressure profiling (Smart Espresso Profiler, Pressensor) | Real-time pressure data from compatible sensors | SKIP | Espresso-primary hardware. Hard skip. |

#### Water Recipes

| Feature | Beanconqueror Description | Snobbery Fit | Verdict | Reason |
|---|---|---|---|---|
| Named water profiles (stored recipe) | Save a named water profile with optional parameters | **Partially exists** — water_type is freetext on brew sessions | ADOPT (lightweight) | Adding a shared `water_profiles` lookup table (id, name, notes) and FK from brew_sessions gives water profiles the same first-class autocomplete treatment as flavor notes. LOW complexity (one table, one FK, one autocomplete field). Enables water as a sweet-spot dimension later. No need for mineral breakdown in v1.2. |
| Water mineral parameters (GH, KH, Na, Ca, Mg, potassium) | Store exact mineral content per profile | SKIP for v1.2 | Niche within pour-over niche. The named profile alone satisfies the UX requirement (Third Wave Water, Lotus Water, Tap). Mineral breakdown adds form complexity with no analytics payoff at 2-user scale. Revisit for v2 if users request it. |
| TDS from water | Track water TDS independently | SKIP | Covered adequately by a named profile. Adding a TDS field to water profiles is trivial if requested; don't pre-build it. |

#### Statistics / Graphs

| Feature | Beanconqueror Description | Snobbery Fit | Verdict | Reason |
|---|---|---|---|---|
| Bean statistics (sessions per bean, avg rating per bean) | Per-coffee aggregated stats | **Already exists** (analytics home page, sweet spots) | ALREADY SHIPPED | v1.1 |
| Consumption statistics (grams used, cost tracking) | How much coffee used over time; spend | **Partially exists** (cost-per-brew; no consumption over time graph) | CONSIDER | A simple "grams consumed this month" derived from dose_grams × session count is cheap to add to the analytics page. Useful for "how long does a bag last?" question. LOW complexity. |
| Brew ratio analytics | Ratio distribution across sessions | SKIP | Derivable from existing data; the SQL analytics page can surface this as a stat line without a dedicated chart. Not a v1.2 priority. |
| Full graph suite (SVG/canvas charts per stat) | Chart.js or similar for brew graphs, consumption trends, etc. | SKIP as a framework | Snobbery's analytics home page is pure SQL + prose, no charting library. Adding a charting library violates KISS; the text-based sweet spots + AI prose is the differentiator. If a specific stat warrants a chart, add a single sparkline via inline SVG, not a library dependency. |

#### Archiving

| Feature | Beanconqueror Description | Snobbery Fit | Verdict | Reason |
|---|---|---|---|---|
| Archive beans / grinders / prep methods | Hide finished items from active lists without deleting | **Already exists** (archived flag on coffees, equipment, etc.) | ALREADY SHIPPED | v1.1 |
| Sort by remaining weight / last-used / best-by date | Multiple sort options for the bag list | SKIP | Two-user household; catalog is small. Sort complexity adds nav overhead. |

#### Photos

| Feature | Beanconqueror Description | Snobbery Fit | Verdict | Reason |
|---|---|---|---|---|
| Photo per brew session | Capture + store brew photo | **Already exists** (hardened photo upload, v1.1) | ALREADY SHIPPED | v1.1 |
| Photo per bean / bag | Store a bag photo (label scan) | SKIP | Not implemented in v1.1 and not prioritized. Adding photo to the coffee/bag catalog is a nice-to-have; the brew session photo is the higher-value capture. |

#### QR Code / NFC Sharing

| Feature | Beanconqueror Description | Snobbery Fit | Verdict | Reason |
|---|---|---|---|---|
| Share bean as QR code | Generate a QR code for a bean entry that another app user can scan to import | SKIP | Snobbery is a household app. No other Snobbery instance exists to scan the QR. Social/sharing is an explicit out-of-scope. This is Beanconqueror's multi-user onboarding mechanism — not needed here. |
| Share brew as image card | Generate a styled image card of your brew stats to share on social media | SKIP | Anti-feature. Counter to Snobbery's private household identity. |
| NFC tag write | Write bean data to an NFC tag, physically attach to a bag | SKIP | Hardware-bound and boutique. |

#### Multiple Prep Methods

| Feature | Beanconqueror Description | Snobbery Fit | Verdict | Reason |
|---|---|---|---|---|
| Support for V60, Aeropress, Espresso, Mokapot, Chemex, etc. | Prep method is a first-class entity with its own parameter configuration | **Already exists** (equipment table + recipes, multiple method support) | ALREADY SHIPPED | v1.1 |
| Method-specific parameter visibility | Hide espresso-specific fields when logging a V60 brew | SKIP for v1.2 | Worth considering if the brew form gets crowded, but at 2-user household scale with primarily pour-over use, a single-scroll form covers all methods adequately. Not a priority. |

#### Other Capabilities

| Feature | Beanconqueror Description | Snobbery Fit | Verdict | Reason |
|---|---|---|---|---|
| Repeat brew with saved settings ("brew again") | One-tap re-log a previous session, inheriting all parameters | **Already exists** (sub-30s re-log with prefill) | ALREADY SHIPPED | v1.1 |
| Apple Health caffeine integration | Log caffeine intake to Apple Health via HealthKit | SKIP | Requires native iOS API; not available in a web PWA without a bridge app. Not the product's purpose. |
| Multi-language support | App UI in 5+ languages | SKIP | Household app, English-only household. Internationalizing a Jinja2 app requires a proper i18n library (babel/flask-babel pattern). Not worth the complexity for 2 users. |
| CSV export / import | Export all data as CSV; import from CSV | **Already exists** (brew session CSV export + import, v1.1) | ALREADY SHIPPED | v1.1 |
| Backup / restore | Full data backup | **Already exists** (pg_dump nightly + photos tar, v1.1) | ALREADY SHIPPED | v1.1 |
| Community / Discord | Public community for help and feature requests | SKIP | Not a product feature. |

### Beanconqueror parity summary: what to carry into v1.2

Adopting (priority order):

1. **Background timer in Guided Brew Mode** — verify Web Worker timer implementation survives iOS screen sleep. LOW complexity. HIGH value for the core use case.
2. **Water profiles lookup table** — replace freetext water_type with a shared named-profile table, FK from brew_sessions. LOW complexity. Enables future sweet-spot analytics on water.
3. **Phase-based step timer** — adopt as part of Guided Brew Mode polish if not already multi-step. MEDIUM complexity. Natural fit given the v1.2 Guided Brew polish goal.
4. **First drip time + bloom time/water optional fields** — two nullable columns on brew_sessions. LOW complexity. Signals pour-over depth to the audience.

Skip (firm reasoning above):
- BLE scale integration — weeks of work, hardware dependency, anti-feature for this product
- QR/NFC sharing — anti-social, no other Snobbery instances to share with
- SCA cupping — professional workflow that competes with existing simpler rating model
- Roasting section — out of domain
- Freeze portions — espresso competition feature, not household pour-over
- Multi-language — not needed for this household

---

## Section 2: Cafe Quick-Rate

### What it is

A lightweight log entry for a coffee experienced outside the home: at a cafe, a cupping, or while traveling. The user did NOT brew this themselves — no recipe, no dose, no grind, no timer. They just drank it and have an opinion.

### How comparable apps model cafe logs

**CafeConnections**: Drop a pin at a cafe, rate 1-5 stars, tag flavors, note the drink type (latte, pour-over, etc.), add a photo. Geo-anchored.

**Roastguide**: Find the coffee, add a rating, add a note. No parameters. Purely about the coffee's identity, not the brew.

**Tasting Grounds**: Optionally captures brew parameters but allows a "no-recipe" tasting entry.

**Press app (2015, influential)**: Explicitly moved away from regimented forms — coffee name, origin, optional notes; no forced parameters.

The pattern that works: **minimum required fields are the coffee identity (name / brand) and a rating. Everything else is optional.** Apps that force full brew parameters for a cafe entry get skipped in the moment.

### Minimum viable field set

Required:
- Coffee name or description (free text or link to catalog entry if the coffee exists)
- Rating (0-5, same scale as brew sessions)

Optional, tappable-to-add:
- Roaster / brand (autocomplete from catalog or freetext)
- Brew method (autocomplete from equipment catalog or freetext like "pour-over" / "espresso" / "filter")
- Flavor notes (same chip-autocomplete as brew sessions)
- Cafe name (free text; geo-pin explicitly out of scope per Snobbery's no-social-features rule)
- Photo (same upload flow as brew sessions)
- Free-text notes

Explicitly NOT included (anti-pattern for quick-rate):
- Dose / water / grind / time — they don't know these
- Recipe FK — there is no recipe
- Refractometer fields — they don't have one at the cafe
- Bag FK — this coffee is probably not in their bag catalog

### Data model approach

Two options:

**Option A: Unified brew_sessions with null recipe/bag** — a cafe log is a brew_session with `bag_id = NULL`, `recipe_id = NULL`, `is_cafe_log = TRUE`, and a new `cafe_coffee_name` text field for the freetext coffee identity when it's not in the catalog. Filter the brew list to split "home brews" from "cafe tastings."

**Option B: Separate `cafe_logs` table** — distinct entity with its own simpler schema.

Recommendation: **Option A (unified table)**. Rationale:
- The AI analytics and preference derivation should be able to learn from cafe logs too (a 4.5 rating on a washed Kenyan at a cafe is valid signal)
- Avoids duplicating the rating + flavor note + photo infrastructure
- A boolean `is_cafe_log` is a cheap discriminator; NULL bag/recipe is already handled
- Option B would require forking the analytics queries, the flavor note many-to-many, and the photo storage — disproportionate cost

Schema additions needed:
- `brew_sessions.is_cafe_log` boolean default false
- `brew_sessions.cafe_name` nullable text (name of the cafe or event)
- `brew_sessions.cafe_coffee_name` nullable text (freetext coffee description if not in catalog)
- `brew_sessions.bag_id` already nullable — stays nullable for cafe logs
- `brew_sessions.recipe_id` already nullable — stays nullable for cafe logs
- All existing optional fields (flavor notes, photo, notes) work unchanged

### How it feeds analytics and AI

Cafe logs SHOULD contribute to:
- User flavor profile (flavor notes from cafe logs are valid preference signal)
- Origin / process preference derivation (a 4.5 on a washed Ethiopian at a cafe counts)
- AI recommendation input (the user's full taste history, not just home brews)

Cafe logs SHOULD NOT contribute to:
- Recipe sweet spots (no recipe; would pollute brew parameter analytics)
- Grinder-specific analytics (no grind setting)
- Freshness analytics (no roast date)
- Bag depletion / inventory

The analytics queries in `services/analytics.py` that compute sweet spots by recipe/grinder should filter `WHERE is_cafe_log = FALSE`. The AI signature and flavor profile queries should include all logs.

### UX fast-entry path

The goal is: phone out at the cafe table, logged in 20 seconds, before the coffee gets cold.

Entry point options:
- A "Tasted at a cafe" button on the home page or a quick-entry fab
- Or: the existing "Log Brew" form with a "This was at a cafe" toggle at the top that collapses the recipe/dose/grind/time fields

Recommendation: **toggle on the existing Log Brew form**, not a separate entry point. Rationale:
- Avoids a third separate flow (home brew log, cafe log, guided brew) cluttering the nav
- The form already has HTMX — collapsing sections on a toggle is a small Alpine.js add
- Keeps the codebase's CRUD in one place (brew_sessions CRUD)

The toggle should collapse: bag, recipe, dose, water, grind, time, refractometer fields.
The toggle should reveal: cafe_name, cafe_coffee_name text fields.

Rating and flavor notes stay visible in both modes — they're the point.

### Complexity

MEDIUM overall:
- Schema migration: LOW (3 nullable columns + 1 boolean)
- Analytics query updates: LOW (add `WHERE NOT is_cafe_log` in 3-4 places)
- Form UI: MEDIUM (Alpine.js toggle + conditional field visibility + HTMX form handling)
- AI signature: LOW (cafe_log_count added to signature inputs so adding cafe logs triggers regen consideration)

Dependencies: brew_sessions table (v1.1), flavor note M2M (v1.1), photo upload (v1.1), analytics service (v1.1). All dependencies already shipped.

---

## Section 3: AI Research-a-Coffee + Predict Rating

### What it does

The user types a coffee name (e.g., "Onyx Coffee Lab Colombia Huila Natural") into a search box. The AI:
1. Researches the coffee via web search (same mechanism as the existing recommendation flow)
2. Retrieves the user's derived preference profile from the analytics service
3. Produces a predicted rating (e.g., "3.5–4.0 / 5") with a prose explanation of why

This is a new AI interaction, distinct from the existing "what to buy next" recommendation.

### Relationship to existing AI features

The existing AI recommendation flow answers: "Based on my history, what should I buy next?" and returns a specific vetted buy URL.

The predict-rating flow answers: "Here's a specific coffee I'm considering — how will I like it?" and returns a prediction without a buy URL.

They are complementary:
- Recommendation: unprompted, AI chooses the coffee, outputs a buy link
- Predict-rating: user-initiated, user names the coffee, outputs a rating prediction + reasoning

The predict-rating flow should live on the new AI page (v1.2 IA restructure). It does not replace the recommendation — it adds an on-demand research mode alongside it.

### What good UX looks like

The interaction should be:
1. Single text input, prominent "Research this coffee" button
2. Loading state: "Researching [coffee name] and comparing to your taste profile..." — 5-15 seconds is realistic
3. Output card:

```
Onyx Colombia Huila Natural

Predicted rating: 3.5 – 4.0 / 5
Confidence: moderate

Why: Your highest-rated coffees are naturals (avg 4.2) and your top origin
is Ethiopia and Colombia. This Colombian natural aligns well. You've rated
fruity/boozy notes like "blueberry" and "wine" highly. This coffee is
described as having those profiles. Main uncertainty: you've logged only
2 Colombian coffees, so origin data is thin.

What reviewers say: [prose from web search, 2-3 sentences]
Known roasters offering this: [optional, if found via web search]
```

Key UX decisions:
- **Range, not point estimate** — "3.5–4.0" not "3.7". A point estimate implies false precision. The range signals honest uncertainty. Industry research on food preference modeling (see sources) confirms even well-fitted models have ±0.5 typical error.
- **Reasoning is required** — the user must see WHY, not just a number. Without reasoning the feature is a black-box oracle, which erodes trust immediately when it's wrong.
- **Confidence level is explicit** — "high / moderate / low" with a one-line explanation of the basis. Low confidence = fewer logged sessions, thin data for this origin or process. High confidence = extensive data, strong pattern match.
- **Caveats are first-class, not footnote** — display the uncertainty as a primary element of the card, not fine print. "This prediction is based on 23 of your brew sessions" is part of the answer, not a disclaimer.
- **No guarantee language** — "Predicted" not "You'll rate" or "AI says you'll love it". Framing matters.

### Realistic accuracy expectations

Based on research:

- The existing preference derivation (pure SQL, group-by origin/process/rating) provides a reliable signal when the user has ≥10 sessions on that dimension. It degrades to noise below 5.
- LLM prediction for novel inputs (a coffee the user has never tried from an unfamiliar origin/roaster) will have ±1.0 typical error — meaning the prediction is a rough directional signal, not a prescription.
- The AI's main value is the research (pulling roaster descriptions, known tasting notes from reviews, brewing recommendations) combined with matching those descriptors to the user's stated flavor preferences. The prediction number is secondary to the prose reasoning.

Accuracy framing for the user:
- "High confidence" → 4+ sessions matching this origin + process; model predicts within ±0.5 reliably
- "Moderate confidence" → 2-3 matching sessions; ±1.0 typical error
- "Low confidence" → 0-1 matching sessions; directional only; prediction based on flavor descriptor matching, not personal history

Cold-start gate: apply the same ≥3-session gate as the existing recommendation. Below that threshold, show a "Log more brews to unlock" message rather than a low-confidence prediction that could mislead.

### AI implementation approach

Reuse the existing AI service architecture:
- Same provider abstraction (Anthropic primary, OpenAI fallback)
- Same web search tool invocation
- New prompt template: include the user's preference profile summary (already generated by analytics service), the coffee name as the research subject, and instructions to output a structured prediction

The prompt should pass to the model:
- The user's top-5 origins by average rating
- The user's top-5 processes by average rating
- Their top-rated flavor notes (top 10 by frequency among high-rated sessions)
- The input coffee name
- Instruction to research via web search and produce a prediction with reasoning + explicit uncertainty

Output format: structured (JSON schema), same pattern as the existing recommendation flow. Parse to a `CoffeePrediction` Pydantic schema before rendering.

Do NOT stream the output for v1.2 — same reasoning as the existing recommendation (polling is simpler, avoids `proxy_buffering off`, easier to debug). If SSE is added in a future phase, extend both flows together.

### Cost and rate limiting

A predict-rating call uses the web search tool (same cost driver as the recommendation). At 2-user scale this is not a budget concern, but:
- The call is on-demand (user-initiated), so there is no nightly signature gate
- A per-user rate limit of 5 predict calls per hour is reasonable to prevent accidental hammering
- Log each call in a new `ai_coffee_predictions` table (user_id, coffee_name_input, predicted_rating_low, predicted_rating_high, confidence, reasoning_prose, created_at, model_used) for auditability and future analytics

The `ai_coffee_predictions` table also feeds future features:
- "Did the prediction hold up?" — after the user brews the coffee and logs a session, compare prediction vs actual
- Aggregate: "Your AI predictions are ±0.4 accurate over 12 predictions" — trust-building transparency

### Complexity

MEDIUM-HIGH overall:
- AI service: MEDIUM (new prompt template + new Pydantic schema; same provider/web-search infrastructure)
- New DB table: LOW (ai_coffee_predictions, ~8 columns)
- UI: MEDIUM (new component on the AI page, text input + loading state + result card)
- Rate limiting: LOW (slowapi decorator, same as login rate limit)
- Analytics integration: LOW (read existing preference derivation; no new queries needed)

Dependencies:
- Analytics service preference derivation (v1.1 — already ships this)
- AI service provider abstraction (v1.1 — already ships this)
- Web search tool (v1.1 — already ships this)
- New AI page (v1.2 IA restructure — must be built first or concurrently)

---

## Feature Landscape (Template Format)

### Table Stakes for v1.2 (Users Expect These Given v1.1 Shipped)

| Feature | Why Expected | Complexity | Notes |
|---|---|---|---|
| Background timer survives phone sleep | Kettle-side brews require the phone to dim; a timer that stops is useless | LOW | Verify Web Worker vs setInterval; fix if needed |
| Cafe quick-rate form toggle | 90% phone-first users will want to capture a cafe tasting; missing it means rating goes unlogged | MEDIUM | Toggle on existing brew form; schema migration |
| Water profiles as named lookup | Freetext water_type is already there; named profiles are the natural next step for serious users | LOW | One table, one FK, autocomplete |

### Differentiators for v1.2

| Feature | Value Proposition | Complexity | Notes |
|---|---|---|---|
| AI predict-rating for a named coffee | No other self-hosted household coffee log does this; turns the preference engine into an interactive research tool | MEDIUM-HIGH | New AI flow; on-demand web search; honesty about uncertainty is the differentiator |
| Cafe logs feed AI preference profile | Taste data from outside home brews makes the AI recommendation smarter; cross-context preference learning | LOW (once cafe log schema exists) | Filter cafe logs from recipe analytics; include in flavor/origin analytics |
| Phase-based step timer in Guided Brew Mode | Transforms Guided Brew from a stopwatch into a brewing coach | MEDIUM | Natural v1.2 polish direction for Guided Brew |
| First drip + bloom time optional fields | Signals the app understands the specific craft of pour-over at a depth competitors miss | LOW | 2 nullable columns; add to Guided Brew Mode as captured data points |

### Anti-Features (Do Not Build in v1.2)

| Feature | Why Not | What to Do Instead |
|---|---|---|
| BLE scale integration (Acaia, Felicita, Decent) | Weeks of device-specific work; Web Bluetooth fragile in PWA; pour-over weights are hand-entered; explicitly out of scope | Manual dose + water entry already works; Guided Brew Mode timer covers the timing need |
| QR code / NFC bean sharing | No other Snobbery instances to share with; social/sharing is an explicit out-of-scope | Share via catalog description text or a bag note |
| SCA cupping scoresheet | Competes with and complicates the existing simple rating + flavor note model; professional workflow, not home-brewer-at-the-kettle | The existing 0-5 rating + flavor notes already captures the signal needed |
| AI auto-generated tasting notes | Trains users to trust the AI's palate instead of developing their own; undermines the core value of the log | Let the AI describe the coffee's expected profile (research), but the user's own notes remain user-authored |
| Social sharing of brew cards | Counter to the private household identity; adds no household value | The log is the output; no sharing needed |
| Roasting section (green bean to roast batch) | Out of domain; neither user is a home roaster | Skip entirely |
| Coffee finder / cafe discovery map | Out of domain per PROJECT.md; brings in mapping infra | The cafe quick-rate covers "I was at a cafe" without becoming a discovery tool |
| Point-estimate AI rating ("you'll rate this 4.2") | False precision destroys trust when wrong | Use range + confidence level; require reasoning prose |
| Per-user brew parameter field ordering | Configuration complexity for zero practical gain at 2-user scale | Single-scroll form with sensible pour-over defaults covers both users |

---

## Feature Dependencies

```
AI predict-rating
    requires --> Analytics preference derivation (SHIPPED v1.1)
    requires --> AI service abstraction (SHIPPED v1.1)
    requires --> Web search tool (SHIPPED v1.1)
    requires --> New AI page (v1.2 IA restructure)
    optional -> Cafe log ratings (enriches prediction accuracy)

Cafe quick-rate
    requires --> brew_sessions table (SHIPPED v1.1)
    requires --> Flavor note M2M (SHIPPED v1.1)
    requires --> Photo upload (SHIPPED v1.1)
    feeds ---> AI preference derivation (origin/process/flavor signal)

Phase-based step timer
    requires --> Guided Brew Mode (SHIPPED v1.1)
    requires --> Recipes with step definitions (SHIPPED v1.1)

Water profiles lookup
    requires --> brew_sessions table (SHIPPED v1.1)
    feeds ---> Sweet spots analytics (future dimension)

First drip + bloom fields
    requires --> brew_sessions schema migration
    optional -> Guided Brew Mode (natural place to capture these mid-brew)
```

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---|---|---|---|
| Background timer (Web Worker) | HIGH | LOW | P1 |
| Cafe quick-rate (form toggle + schema) | HIGH | MEDIUM | P1 |
| AI predict-rating | HIGH | MEDIUM-HIGH | P1 |
| Water profiles lookup table | MEDIUM | LOW | P2 |
| First drip + bloom optional fields | MEDIUM | LOW | P2 |
| Phase-based step timer in Guided Brew | MEDIUM | MEDIUM | P2 |
| Consumption stats (grams/month) | LOW | LOW | P3 |

---

## Sources

### Beanconqueror
- [Beanconqueror GitHub repository](https://github.com/graphefruit/Beanconqueror) — feature inventory, open-source code inspection
- [Beanconqueror official site](https://beanconqueror.com/) — marketing feature list
- [Beanconqueror changelog](https://beanconqueror.com/changelog/) — feature evolution history
- [Beanconqueror data tracking page](https://beanconqueror.com/data-tracking/) — tracked brew actions
- [Beanconqueror FAQ (Gitbook)](https://beanconqueror.gitbook.io/beanconqueror/resources/faq) — QR/NFC ecosystem notes, scale limitations
- [Release v6.1.0 notes](https://github.com/graphefruit/Beanconqueror/releases/tag/v.6.1.0) — QR scan, scale integrations, graph overhaul, purchase tracking
- [Beanconqueror + Decent Scale blog](https://decentespresso.com/blog/beanconqueror_and_the_decent_scale) — BLE scale integration detail
- [Home-barista.com Beanconqueror thread](https://www.home-barista.com/knockbox/beanconqueror-app-t68236-170.html) — user critique of pour-over parameter coverage

### Cafe log / quick-rate research
- [CafeConnections App Store](https://apps.apple.com/us/app/cafeconnections-coffee-log/id6756827606) — drop-pin + rate + flavor tag model
- [Tasting Grounds App Store](https://apps.apple.com/us/app/tasting-grounds/id1526958511) — optional params on tasting entries
- [Roastguide App Store](https://apps.apple.com/us/app/roastguide/id1454418262) — search-and-rate minimal model
- [Press app (DailyCoffeeNews)](https://dailycoffeenews.com/2015/02/03/meet-press-a-new-coffee-brewing-and-origin-logging-app/) — explicit philosophy of avoiding regimented forms
- [iBrewCoffee](https://ibrew.coffee/) — tasting profile fields (aroma, sweetness, acidity, body, bitterness)

### AI prediction / recommendation UX
- [arxiv: Coffee bean recommendation from robot assistant](https://arxiv.org/pdf/2008.13585) — preference vector approach; directional accuracy claims
- [Nature: AI-driven prediction of consumer liking from sensory data](https://www.nature.com/articles/s41538-026-00779-7) — ±0.5 typical model error; ensemble methods; confidence calibration importance
- [arxiv: Coffee ratings prediction from attributes](https://arxiv.org/pdf/2509.18124) — feature importance for rating prediction; Extra Trees / XGBoost outperform simpler models
- [ResearchGate: Coffee recommendations from search/preference history](https://www.researchgate.net/publication/361291090_An_approach_to_coffee_recommendations_according_to_the_history_of_searches_and_preferences) — collaborative filtering vs content-based; hybrid approach

### Confidence assessment
- **HIGH** — Beanconqueror feature inventory (sourced directly from repo, official site, changelogs)
- **HIGH** — Adopt/skip verdicts for BLE/social/cupping (anti-features confirmed by competitor outcomes + Snobbery's explicit out-of-scope list)
- **MEDIUM** — Cafe quick-rate data model recommendation (Option A vs B reasoning is sound but not validated against existing schema in production)
- **MEDIUM** — AI predict-rating accuracy claims (academic sources; real-world accuracy in this specific household context is unknown until shipped)
- **HIGH** — Anti-feature calls (each tied to a specific Snobbery out-of-scope constraint or confirmed competitor failure mode)

---

*Feature research for: Snobbery v1.2 new capabilities (Beanconqueror parity, cafe quick-rate, AI predict-rating)*
*Researched: 2026-05-25*
