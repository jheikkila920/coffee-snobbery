# Phase 20: Guided Brew Polish - Context

**Gathered:** 2026-05-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Polish the EXISTING Guided Brew Mode so it feels like a purpose-built mobile brewing coach. Scope is fixed by ROADMAP Phase 20 / GBREW-01..06:

- **GBREW-01** — Guided Brew timer keeps accurate time when the phone screen sleeps at the kettle (background-safe)
- **GBREW-02** — Guided Brew steps through recipe phases (bloom, pours) as timed, coached steps with phase-specific cues
- **GBREW-03** — User can optionally record first-drip time and bloom time on any brew session
- **GBREW-04** — Water type selected from a managed named water-profiles catalog instead of freetext
- **GBREW-05** — Guided Brew Mode meets the 375px mobile polish bar end-to-end (touch targets, safe-area, no horizontal scroll)
- **GBREW-06** — Recipe step builder supports per-step notes AND timed steps with neither coffee nor water (e.g. "open switch for drawdown"); both inherit into Guided Brew as coached steps

This is polish/extension of shipped code, not a rebuild. Prefer surgical changes to the existing Guided Brew, recipe-step, and brew-session surfaces.

</domain>

<decisions>
## Implementation Decisions

### Water profiles (GBREW-04)
- **D-01:** A water profile holds a **name + optional freetext notes** (e.g. "Third Wave Water (remineralized)"). No structured mineral fields (Ca/Mg/bicarbonate/TDS) in this phase — keep it KISS for a polish milestone.
- **D-02:** Profiles are **inline select-or-create on the brew form**, like the flavor-note tag pattern — any household user can add one, and profiles are **shared** across the household (matches the shared-catalog invariant: coffees/recipes/flavor-notes are shared). No admin-only gate, no separate required catalog page for v1.2.
- **D-03:** Migration **auto-seeds** a water profile per distinct existing `water_type` freetext value and **links** historical sessions to the matching profile. Preserve history; no manual cleanup expected. (Mechanism — collision handling, blank/garbage values — left to research/planning.)

### Recipe step model (GBREW-06)
- **D-04:** Each step gains an explicit **type from a preset list: Bloom / Pour / Wait / Action**, alongside its existing freetext `label`. Type drives Guided Brew coaching ("Bloom", "Pour 2") and lets Wait/Action steps exist without water.
- **D-05:** Each step gains an **optional freetext note** (e.g. "Hario Switch closed for immersion"), inheritable into Guided Brew as a coached cue. Directly satisfies GBREW-06.
- **D-06:** Each step gains an **optional per-step water temperature** (some recipes drop temp across pours). Optional — most steps will leave it blank.
- **D-07:** `water_grams` becomes **optional** so Wait/Action steps can be pure timed actions (only `time` + `label`/`note` required). Satisfies GBREW-06's "neither coffee nor water" requirement. Resulting step shape: `{type, label, water_grams?, water_temp_c?, time_seconds, note?}`.

### Phase coaching (GBREW-02)
- **D-08:** Transition cues are **audio tone + vibration + visual change** — keep the three already implemented. **No spoken voice / TTS** this phase (explicitly not selected).
- **D-09:** The coaching line is **auto-composed** from step type + target (e.g. "Pour 2 — to 250g") with the **per-step note shown beneath it**. Uses all the new step fields (D-04/05/06).
- **D-10:** Add a **short pre-cue countdown** ("get ready", e.g. 3-2-1) a few seconds before each phase transition, so it feels like a coach guiding the pour — not just a signal at the moment of change.
- **D-11:** On-screen during a step = **full coach view**: big current step (type + target) + countdown to next + cumulative water target + total elapsed + small next-step preview.

### First-drip / bloom capture (GBREW-03)
- **D-12:** Capture via **live tap-to-mark buttons during Guided Brew, AND editable on the session form** afterward (including on non-guided / manually-logged sessions — GBREW-03 says "any brew session"). New nullable fields on `brew_session`.
- **D-13:** **Bloom time auto-derives** from the actual elapsed time on the Bloom-type step (zero extra taps now that step type exists), and remains editable. First-drip is a live tap (or manual entry).
- **D-14:** **First-drip time is measured from brew start** (the conventional whole-brew reading), not from first pour / bloom end.

### Timer accuracy (GBREW-01)
- **D-15:** The Guided Brew timer must be **wall-clock-truth**: elapsed time is recomputed from a persisted start timestamp (not accumulated via `setInterval` ticks), so on wake from sleep it self-corrects and silently catches up any missed phase transitions. Current code uses plain `setInterval` + Wake Lock/NoSleep.js with no timestamp recovery — that is the gap to close. **Mechanism is research's job** (timestamp recovery vs Web Worker vs `visibilitychange` re-sync); the locked decision is the *behavior*: accurate-on-wake, no drift, no double-counting.

### Mobile polish (GBREW-05)
- **D-16:** Treat as a **375px verification pass** against the established mobile pattern (44px min touch targets, 56px primary CTAs, `px-6` padding, safe-area handled per the Phase 15 `982c0e6` fix verified on John's iPhone PWA). New UI added in this phase (water-profile inline create, step-type/note/temp builder fields, tap-to-mark buttons, full coach view) must conform to that bar. Not a separate redesign.

### Claude's Discretion
- Exact JSONB step-schema field names and Pydantic validation bounds (extend `app/schemas/recipe.py StepSchema`).
- Water-profile migration collision/blank-value handling (D-03).
- Timer recovery mechanism for D-15.
- Whether the water-profiles list also gets a lightweight management/edit affordance beyond inline-create (not required; inline-create is the floor).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` §"Phase 20: Guided Brew Polish" — goal, success criteria, UI hint
- `.planning/REQUIREMENTS.md` — GBREW-01..06 definitions

### Existing code to extend (from codebase scout)
- `app/routers/brew_guided.py` — Guided Brew route
- `app/templates/pages/brew_guided.html` — Guided Brew screens (start / timer / done); 44px/56px touch-target examples
- `app/static/js/alpine-components/guided-brew-mode.js` — timer (`_startTimer`/`_tick` `setInterval`), Wake Lock + NoSleep.js (`navigator.wakeLock`, `visibilitychange` re-acquire); the GBREW-01 + GBREW-02 + GBREW-03 work centers here
- `app/models/recipe.py` — `steps: Mapped[list[dict]] = JSONB` (GBREW-06 step-model change)
- `app/schemas/recipe.py` — `StepSchema {water_grams, time_seconds, label}` (extend per D-04..D-07)
- `app/templates/fragments/recipe_step_builder.html` — step builder UI to extend with type/note/temp
- `app/models/brew_session.py` — `water_type: Text` (GBREW-04 → profile FK); add first-drip/bloom fields (GBREW-03); existing `brew_time_seconds`
- `app/schemas/brew_session.py` — session schema (`water_type` freetext today)

### Established patterns to reuse
- Flavor-note inline tag/select-or-create pattern (`app/static/js/tag-input.js` per project docs) — model for D-02 water-profile inline create
- Phase 15 safe-area fix commit `982c0e6` (verified on physical iPhone PWA) — the canonical safe-area technique for D-16

*No external ADRs were referenced during discussion; requirements and decisions above are the contract.*

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Guided Brew Alpine component** (`guided-brew-mode.js`) already has audio/vibration/visual cue plumbing and Wake Lock/NoSleep — extend, don't rebuild.
- **Shared-catalog + inline tag-create pattern** (flavor notes) — direct template for water profiles (D-02).
- **JSONB `steps` column** already exists — adding type/note/temp is a schema-light JSONB shape change, not a new table.
- **`brew_time_seconds`** already captures total elapsed from Guided Brew — first-drip/bloom are sibling nullable fields.

### Established Patterns
- Shared vs per-user split: coffees/recipes/flavor-notes/**water-profiles (new)** are SHARED; brew sessions are per-user.
- Mobile bar: 44px secondary / 56px primary touch targets, `px-6` padding, Phase 15 safe-area technique.
- CSRF on all state-changing forms + nonce-CSP — new water-profile create + step builder + tap-to-mark POSTs must comply (no endpoints that skip CSRF/headers).

### Integration Points
- New `water_profiles` table + FK from `brew_session.water_type` (with Alembic data migration auto-seeding from existing freetext — D-03).
- New nullable `brew_session` columns for first-drip and bloom (D-12), surfaced on both the Guided Brew flow and the standard session form.
- Step-shape change in `recipe.py`/`recipe.py` schema flows into both the recipe step builder UI and the Guided Brew coaching renderer.

</code_context>

<specifics>
## Specific Ideas

- "Coach feel" is the north star: pre-cue countdown (D-10) + full coach view (D-11) + auto-composed coaching line (D-09) are what make it feel purpose-built rather than a bare timer.
- Step types map to real pour-over phases: Bloom, Pour, Wait, Action (e.g. Hario Switch open/close for drawdown) — D-04.
- Bloom time should cost zero taps (auto-derived) — D-13.

</specifics>

<deferred>
## Deferred Ideas

- **Structured water mineralogy** (Ca/Mg/bicarbonate/TDS per profile, water-vs-taste analytics) — considered for D-01, deferred; would be its own data/analytics feature, not polish.
- **Spoken voice / TTS coaching** — considered for D-08, deferred (hands-free is appealing but new work beyond this phase's bar).
- **Per-step agitation as a structured field** — considered for D-06, lives in the per-step note for now.

None of these are blockers; revisit in a future milestone if validated.

</deferred>

---

*Phase: 20-guided-brew-polish*
*Context gathered: 2026-05-29*
