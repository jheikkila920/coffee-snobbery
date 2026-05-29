# Phase 20: Guided Brew Polish - Research

**Researched:** 2026-05-29
**Domain:** Alpine.js timer accuracy (iOS PWA), Alembic data migration, JSONB schema evolution, HTMX inline-create pattern
**Confidence:** HIGH (all critical claims verified against codebase source or authoritative web sources)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Water profiles (GBREW-04)**
- D-01: A water profile holds a name + optional freetext notes. No structured mineral fields this phase.
- D-02: Profiles are inline select-or-create on the brew form, shared across household (no admin-only gate, no separate catalog page for v1.2).
- D-03: Migration auto-seeds a water profile per distinct existing water_type freetext value and links historical sessions to the matching profile.

**Recipe step model (GBREW-06)**
- D-04: Each step gains explicit type: Bloom / Pour / Wait / Action.
- D-05: Each step gains optional freetext note (max 200 chars).
- D-06: Each step gains optional per-step water temperature (water_temp_c, 50-100 range).
- D-07: water_grams becomes optional so Wait/Action steps can be pure timed actions.
- Resulting step shape: {type, label, water_grams?, water_temp_c?, time_seconds, note?}

**Phase coaching (GBREW-02)**
- D-08: Transition cues = audio tone + vibration + visual. No TTS.
- D-09: Coaching line auto-composed from step type + target; per-step note shown beneath.
- D-10: Short pre-cue countdown (3-2-1) a few seconds before each phase transition.
- D-11: Full coach view: big current step + countdown + cumulative water target + total elapsed + next step preview.

**First-drip / bloom capture (GBREW-03)**
- D-12: Capture via live tap-to-mark buttons during Guided Brew AND editable on session form.
- D-13: Bloom time auto-derives from the actual elapsed time on the Bloom-type step; remains editable.
- D-14: First-drip time measured from brew start.

**Timer accuracy (GBREW-01)**
- D-15: Wall-clock-truth: elapsed time recomputed from a persisted start timestamp, not accumulated via setInterval ticks. Mechanism is research's job; behavior is locked.

**Mobile polish (GBREW-05)**
- D-16: 375px verification pass — 44px/56px touch targets, px-6 padding, safe-area per Phase 15 commit 982c0e6.

### Claude's Discretion
- Exact JSONB step-schema field names and Pydantic validation bounds.
- Water-profile migration collision/blank-value handling (D-03).
- Timer recovery mechanism for D-15.
- Whether the water-profiles list also gets a lightweight management/edit affordance beyond inline-create.

### Deferred Ideas (OUT OF SCOPE)
- Structured water mineralogy (Ca/Mg/bicarbonate/TDS per profile).
- Spoken voice / TTS coaching.
- Per-step agitation as a structured field.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| GBREW-01 | Timer keeps running when phone screen sleeps | D-15 wall-clock-truth mechanism researched; visibilitychange + timestamp recovery recommended |
| GBREW-02 | Steps through recipe phases as timed, coached steps | Step-type model (D-04) + pre-cue countdown (D-10) + full coach view (D-11) patterns documented |
| GBREW-03 | User can optionally record first-drip and bloom time | New nullable columns on brew_session; tap-to-mark in JS; bloom auto-derives from step type |
| GBREW-04 | Water type selected from named profiles catalog | water_profiles table + Alembic data migration seeding from existing freetext; FK on brew_session |
| GBREW-05 | Guided Brew meets 375px mobile polish bar | Phase 15 safe-area technique (commit 982c0e6) documented; touch-target patterns confirmed from existing templates |
| GBREW-06 | Step builder supports per-step notes and waterless timed steps | StepSchema extension with optional fields; JSONB default-at-read inference pattern documented |

</phase_requirements>

---

## Summary

Phase 20 is a surgical extension of shipped code — the Guided Brew Mode Alpine component, recipe step model, and brew session schema. Nothing requires a new table except `water_profiles`. The dominant implementation risk is GBREW-01 (timer accuracy under iOS screen sleep) and GBREW-04 (the data migration seeding water profiles from freetext while linking historical sessions).

The wall-clock-truth timer is achievable with a small change to the existing `_tick()` method: record `_startTimestamp = Date.now()` at brew start, and on every tick compute `elapsed = Math.floor((Date.now() - _startTimestamp) / 1000)` rather than incrementing a counter. The `visibilitychange` event (already wired in the component for wake-lock re-acquire) becomes the natural hook to call a resync method that silently advances `currentStepIndex` and `remainingSeconds` to match wall-clock truth. This approach requires zero new browser APIs, is already partially scaffolded in the component, and handles both screen-sleep drift and the short background-freeze window iOS allows.

The JSONB step-schema change is purely additive (new optional fields). Existing recipe rows whose steps lack `type`, `note`, and `water_temp_c` must be handled gracefully at read time in the Alpine component — a `step.type || 'Pour'` default costs one line and requires no backfill migration. Pydantic v2's `StepSchema` must change `extra="forbid"` to `extra="ignore"` or loosen it, and all new fields must be `Optional` with appropriate defaults, to avoid breaking existing stored step objects.

**Primary recommendation:** Timestamp-recovery on visibilitychange for the timer (no Web Worker needed); additive StepSchema with `Optional` fields and a default `type`; a single Alembic migration for `water_profiles` with a data-seeding step that normalizes freetext values.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Wall-clock-truth timer | Browser (Alpine JS) | — | Timer is a client-side, real-time UI concern; no server roundtrip appropriate during an active brew |
| Step coaching / cue rendering | Browser (Alpine JS) | — | Coach view is derived from step data already embedded in data-steps; pure client-side render |
| Pre-cue countdown (D-10) | Browser (Alpine JS) | — | Sub-second timing logic; server round-trip would add latency incompatible with "3-2-1 countdown" |
| Tap-to-mark (first-drip) | Browser (Alpine JS) | API (brew form POST) | Live recording is client-side; persisted via existing brew session form POST on done |
| Bloom time auto-derive | Browser (Alpine JS) | — | Derived from step-type at transition time; zero server involvement during brew |
| Water profile inline-create | API (FastAPI router) | Browser (HTMX POST) | Create is a server-side DB write; browser triggers via htmx.ajax(); HX-Trigger reply |
| Water profile select list | API (FastAPI, context) | Browser (Alpine) | Server renders select options; Alpine manages show/hide of create form |
| Step model JSONB extension | API (Pydantic schema) | DB (JSONB column) | Pydantic StepSchema enforces shape at write time; JSONB stores it; no DB CHECK |
| Alembic water_profiles migration | DB | — | New table + FK + data seed; pure database concern |
| brew_session new nullable columns | DB + API | — | Schema addition via Alembic; model + schema updated to add first_drip_seconds, bloom_time_seconds |
| Session form editable timing fields | API (template context) | Browser | Server renders form fields; no Alpine needed for simple optional number inputs |
| 375px mobile audit (D-16) | Browser (template CSS) | — | Verification pass on Tailwind utility classes; no logic change |

---

## Standard Stack

### Core (all existing — no new packages)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Alpine.js CSP build | 3.x (CDN) | Guided Brew component extension | Already in use; CSP-strict build required |
| HTMX | 2.0.x (CDN) | Water profile inline POST | Already in use; htmx.ajax() handles CSRF via htmx-listeners.js |
| FastAPI | >=0.136,<0.137 | New /water-profiles router | Stack invariant |
| SQLAlchemy 2.0 | >=2.0.49 | water_profiles model | Stack invariant |
| Alembic | >=1.18 | p20_water_profiles migration | Stack invariant |
| Pydantic v2 | >=2.13 | StepSchema extension, WaterProfileCreate | Stack invariant |
| PostgreSQL 16 | 16-alpine | water_profiles table storage | Stack invariant |

**No new packages are required for Phase 20.** All functionality is achievable within the existing stack.

## Package Legitimacy Audit

> No new packages are introduced in Phase 20. This section is N/A.

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

---

## Architecture Patterns

### System Architecture Diagram

```
[User at kettle — iPhone PWA]
        |
        | tap "Start guided brew"
        v
[Alpine guidedBrewMode component]
   |  _startTimestamp = Date.now()     → stored in-memory + localStorage
   |  setInterval tick (1s)            → reads Date.now() - _startTimestamp
   |  visibilitychange (doc visible)   → resync: recompute elapsed, advance steps
   |  step.type determines coaching    → "Bloom"|"Pour N"|"Wait"|step.label
   |  3s before transition             → pre-cue countdown display (3-2-1)
   |  at transition                    → chime + vibrate + visual (D-08)
   |  Bloom step ends                  → auto-record bloom_time (D-13)
   |  user taps "Mark first drip"      → record first_drip_seconds in JS state
        |
        | brew ends: finishBrewing()
        v
[GET /brew/new?gbm=1&recipe_id=N&brew_time=T&first_drip=X&bloom_time=Y]
        |
[brew_form.html — water_profile_id <select> + new timing fields]
        |
        | "Add new..." selected → Alpine x-show toggles inline create fields
        | htmx.ajax POST /water-profiles → HX-Trigger water-profile-created
        | Alpine listener adds new profile to <select>, auto-selects it
        |
[POST /brew with water_profile_id + first_drip_seconds + bloom_time_seconds]
        |
[BrewSessionCreate schema validates + BrewSession saved to DB]
```

```
[Recipe edit page — step builder]
        |
[recipeStepBuilder Alpine component — extended]
   | addStep()     → default type='Pour', water_grams=null for Wait/Action
   | setType(i,v)  → when Wait/Action, dims water_grams field (opacity-40)
   | setNote(i,v), setTemp(i,v) → new setter methods
   | stepsJson     → JSON.stringify(steps) into hidden input
        |
[POST /recipes/{id} — RecipeCreate.steps: list[StepSchema]]
        |
[PostgreSQL JSONB — steps stored as-is]
        |
[GET /brew/guided — steps embedded in data-steps attribute]
   | Alpine reads steps JSON; type defaults to 'Pour' if absent (backward compat)
```

```
[Alembic migration p20_water_profiles]
   1. CREATE TABLE water_profiles (id, name, notes, created_at, updated_at)
   2. INSERT INTO water_profiles SELECT normalized distinct water_type FROM brew_sessions
   3. ALTER TABLE brew_sessions ADD COLUMN water_profile_id FK water_profiles (SET NULL)
   4. UPDATE brew_sessions SET water_profile_id = (SELECT id FROM water_profiles WHERE name = normalized(water_type))
   5. ALTER TABLE brew_sessions ADD COLUMN first_drip_seconds INTEGER NULL
   6. ALTER TABLE brew_sessions ADD COLUMN bloom_time_seconds INTEGER NULL
   (water_type column is RETAINED for backward compat — not dropped in this phase)
```

### Recommended Project Structure

No new directories needed. New files slot into existing layout:

```
app/
├── models/
│   └── water_profile.py          # NEW: WaterProfile model
├── schemas/
│   └── water_profile.py          # NEW: WaterProfileCreate schema
├── routers/
│   └── water_profiles.py         # NEW: POST /water-profiles inline-create endpoint
├── services/
│   └── water_profiles.py         # NEW: create / list service functions
├── migrations/versions/
│   └── p20_water_profiles.py     # NEW: table + data migration + brew_session columns
├── models/recipe.py              # UNCHANGED (steps: Mapped[list[dict]] stays)
├── schemas/recipe.py             # MODIFIED: StepSchema extended
├── models/brew_session.py        # MODIFIED: water_profile_id FK + two new nullable cols
├── schemas/brew_session.py       # MODIFIED: water_profile_id replaces water_type; new timing fields
├── templates/pages/brew_guided.html         # MODIFIED: full coach view, tap-to-mark
├── templates/fragments/recipe_step_builder.html  # MODIFIED: type/note/temp fields
├── templates/fragments/brew_prefill_fields.html  # MODIFIED: water_type → profile select
└── static/js/alpine-components/
    ├── guided-brew-mode.js        # MODIFIED: wall-clock timer + coaching + bloom capture
    └── recipe-step-builder.js    # MODIFIED: type/note/temp setters + stepsJson update
```

### Pattern 1: Wall-Clock-Truth Timer (D-15)

**What:** Elapsed time derived from `Date.now() - startTimestamp` rather than accumulated `++` counter.

**When to use:** Any timer that must survive iOS screen sleep or tab backgrounding.

**Key insight from research:** iOS freezes ALL JS execution (including Web Workers) after ~5 seconds in the background. The `visibilitychange` event fires when the screen wakes or the app is brought back. The Wake Lock API works in iOS 18.4+ standalone PWAs [VERIFIED: WebKit bug 254545] but does not prevent JS freezing when the user presses the side button (screen off) — it only prevents auto-sleep. Therefore, the reliable approach is:

1. At `start()`: record `this._startTimestamp = Date.now()` and persist to `localStorage` (`snobbery:gbm:start`)
2. At each `_tick()`: compute `const elapsed = Math.floor((Date.now() - this._startTimestamp) / 1000)` — this self-corrects after any drift
3. At `visibilitychange` (page becomes visible): call `_resync()` which recomputes elapsed from the persisted timestamp, silently advances `currentStepIndex` past any transitions that should have fired during sleep, and corrects `remainingSeconds` and `elapsedTotalSeconds`
4. At `pause()`: record `this._pausedAt = Date.now()` and store in localStorage; at `resume()`, add the paused duration to an offset
5. At `destroy()`: clear the localStorage keys

```javascript
// Source: derived from codebase analysis of guided-brew-mode.js + iOS PWA research
// The existing _tick() increments counters. Replace with timestamp-truth:

_startTimer() {
  this._stopTimer();
  // If no start timestamp yet (first start), record now.
  if (!this._startTimestamp) {
    this._startTimestamp = Date.now() - (this.elapsedTotalSeconds * 1000);
    // persist across screen-sleep
    try { localStorage.setItem('snobbery:gbm:start', String(this._startTimestamp)); } catch(_) {}
  }
  this._timer = setInterval(() => this._tick(), 1000);
},

_tick() {
  const elapsed = Math.floor((Date.now() - this._startTimestamp) / 1000) - this._pausedOffset;
  this.elapsedTotalSeconds = elapsed;
  // Derive current step and remaining from elapsed + step durations
  this._syncStateFromElapsed(elapsed);
},

_resync() {
  // Called from visibilitychange when page becomes visible
  if (!this._startTimestamp || !this.isRunning || this.isPaused) return;
  const elapsed = Math.floor((Date.now() - this._startTimestamp) / 1000) - this._pausedOffset;
  this.elapsedTotalSeconds = elapsed;
  this._syncStateFromElapsed(elapsed);
},

_syncStateFromElapsed(elapsed) {
  // Walk steps to find which step should be active at `elapsed` seconds.
  // Steps store cumulative time_seconds (offset from brew start).
  let stepIdx = 0;
  for (let i = 0; i < this.steps.length; i++) {
    if (elapsed >= (this.steps[i].time_seconds || 0)) {
      stepIdx = i + 1;  // this step is done
    } else {
      break;
    }
  }
  if (stepIdx >= this.steps.length) {
    // All steps done — advance to done state without double-cue
    if (!this.isDone) {
      this._stopTimer();
      this.isRunning = false;
      this.isDone = true;
      this._releaseWakeLock();
    }
    return;
  }
  const prevIndex = this.currentStepIndex;
  this.currentStepIndex = stepIdx;
  const stepEnd = this.steps[stepIdx].time_seconds || 0;
  this.remainingSeconds = Math.max(0, stepEnd - elapsed);
  // Fire cues only for newly crossed transitions (not on resync of already-past steps)
  if (stepIdx > prevIndex) {
    if (this.cuePrefs.chime) this.playChime();
    if (this.cuePrefs.vibrate) this.triggerVibration();
  }
},
```

**Pre-cue countdown integration:** The pre-cue (D-10) is a display state, not a separate timer. Add a computed getter:

```javascript
get preCueCountdown() {
  // Returns 3, 2, 1, or 0 (0 = no pre-cue active)
  if (this.remainingSeconds > 3 || this.remainingSeconds <= 0) return 0;
  return this.remainingSeconds;  // 1, 2, or 3
},

get isPreCue() {
  return this.preCueCountdown > 0 && this.preCueCountdown <= 3;
},
```

**NoSleep.js interplay:** The existing `_setupVisibilityReacquire()` already calls `requestWakeLock()` on visibility. Add `this._resync()` to the same handler. Order: resync state first, then re-acquire wake lock (wake lock is async and non-blocking).

---

### Pattern 2: Inline Select-or-Create for Water Profiles (D-02)

**What:** Native `<select>` with an "Add new..." trailing option; on selection, Alpine `x-show` swaps in a small create form; POST via `htmx.ajax()` with CSRF; `HX-Trigger: water-profile-created` event drives Alpine to add the new profile and auto-select it.

**Model:** The existing `observedFlavorNotes` / `flavor-tag-input.js` pattern — specifically its `createFromQuery()` method which calls `htmx.ajax()` and listens for a `flavor-note-created` body event. The water-profile pattern is simpler (single scalar FK, not multi-chip), so the Alpine component can be inline in the template (< 50 LOC) rather than a separate file.

**Key difference from flavor-notes:** Water profile is a scalar FK (one profile per session), not a multi-select chip array. The Alpine state is `{ showCreate: false, profileId: null }` rather than `selectedChips[]`.

**CSRF compliance:** `htmx.ajax()` goes through the global `htmx:configRequest` listener in `htmx-listeners.js`, which injects `X-CSRF-Token` from the cookie on every HTMX request. The `/water-profiles` POST endpoint must read it from `request.form()` or the header (same pattern as `flavor_notes.py`). [VERIFIED: codebase — htmx-listeners.js + flavor_notes.py create_flavor_note handler]

**HX-Trigger pattern (locked from flavor_notes.py):**
```python
# Source: app/routers/flavor_notes.py lines 251-256 — exact mirror for water-profiles
response.headers["HX-Trigger"] = json.dumps({
    "water-profile-created": {
        "water_profile_id": profile.id,
        "name": profile.name,
    }
})
```

Alpine listener in the template:
```javascript
// In Alpine init() — mirrors observedFlavorNotes._onCreated pattern
document.body.addEventListener('water-profile-created', (evt) => {
  if (!evt || !evt.detail) return;
  const { water_profile_id, name } = evt.detail;
  // Add to local options array and select
  this.profiles.push({ id: water_profile_id, name: name });
  this.profileId = water_profile_id;
  this.showCreate = false;
});
```

---

### Pattern 3: Alembic Data Migration — water_profiles Seed (D-03)

**What:** Single migration that (1) creates `water_profiles` table, (2) seeds one row per distinct normalized `water_type` from `brew_sessions`, (3) adds `water_profile_id` FK column to `brew_sessions`, (4) links historical sessions to their matching profile, (5) adds `first_drip_seconds` and `bloom_time_seconds` columns.

**Normalization for collision handling:** The existing `p15_1_multi_origin.py` uses `NULLIF(x, '')` and `COALESCE` for normalization — follow the same pattern. [VERIFIED: app/migrations/versions/p15_1_multi_origin.py]

**Concrete SQL shape (D-03 mechanism):**

```python
# Source: established Alembic inline-DDL convention from p15_1_multi_origin.py
def upgrade() -> None:
    # 1. Create water_profiles table (household-shared catalog)
    op.create_table(
        "water_profiles",
        sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_water_profiles_name", "water_profiles", ["name"])

    # 2. Seed from distinct normalized water_type values.
    #    Normalization: TRIM + LOWER for dedup; store INITCAP for display.
    #    Blank / NULL water_type rows are excluded (see blank-value handling below).
    op.execute("""
        INSERT INTO water_profiles (name)
        SELECT DISTINCT
            INITCAP(TRIM(water_type)) AS name
        FROM brew_sessions
        WHERE water_type IS NOT NULL
          AND TRIM(water_type) != ''
        ORDER BY INITCAP(TRIM(water_type))
    """)

    # 3. Add water_profile_id FK (nullable; historical rows get NULL if no match found)
    op.add_column("brew_sessions",
        sa.Column("water_profile_id", sa.BigInteger,
                  sa.ForeignKey("water_profiles.id", ondelete="SET NULL"),
                  nullable=True))
    op.create_index("ix_brew_sessions_water_profile_id",
                    "brew_sessions", ["water_profile_id"])

    # 4. Link historical sessions to matching profile
    op.execute("""
        UPDATE brew_sessions bs
        SET water_profile_id = wp.id
        FROM water_profiles wp
        WHERE INITCAP(TRIM(bs.water_type)) = wp.name
          AND bs.water_type IS NOT NULL
          AND TRIM(bs.water_type) != ''
    """)

    # 5. Add first_drip_seconds and bloom_time_seconds (nullable integers)
    op.add_column("brew_sessions",
        sa.Column("first_drip_seconds", sa.Integer, nullable=True))
    op.add_column("brew_sessions",
        sa.Column("bloom_time_seconds", sa.Integer, nullable=True))
```

**Blank / NULL handling:** Sessions with `water_type IS NULL` or `TRIM(water_type) = ''` get `water_profile_id = NULL`. No "Unknown" profile seeded — NULL is the correct representation of "user didn't specify water". [ASSUMED] — this is the cleanest approach but should be confirmed with John if he prefers an "Unspecified" profile.

**water_type column retention:** The existing `water_type` Text column is NOT dropped in this migration. It is deprecated (form field replaced by `water_profile_id` going forward) but retained for historical data safety. If the team wants to drop it, that is a separate cleanup migration in a future phase.

**Down revision:** `p19_ai_research_predict` (the current HEAD). [VERIFIED: codebase — p19_ai_research_predict.py]

---

### Pattern 4: JSONB Step Schema Extension (D-04..D-07)

**What:** `StepSchema` gains `type`, `note`, `water_temp_c` fields; `water_grams` becomes optional.

**Critical constraint — `extra="forbid"` on StepSchema:** The current schema has `model_config = ConfigDict(extra="forbid")`. Existing stored JSONB steps have shape `{water_grams, time_seconds, label}`. After the schema change, reading those old rows will deserialize them through `StepSchema` — they will lack `type`, `note`, `water_temp_c`. If `extra="forbid"` remains, old steps validate fine (they don't have extra fields). But if any code tries to round-trip old step dicts through the schema (e.g., edit-recipe form submits old steps + new UI fields), the submitted steps will include `type` which old-schema would reject. Solution: keep `extra="forbid"` but add the new fields with defaults. [VERIFIED: app/schemas/recipe.py]

**Updated StepSchema:**

```python
# Source: app/schemas/recipe.py — surgical extension of existing class
from typing import Literal

class StepSchema(BaseModel):
    """One step in a recipe's JSONB steps array (extended in Phase 20)."""

    model_config = ConfigDict(extra="forbid")

    # Existing fields (water_grams now optional for Wait/Action steps)
    water_grams: int | None = Field(None, ge=0, le=2000)
    time_seconds: int = Field(..., ge=0, le=3600)
    label: str = Field("", max_length=80)

    # New fields (Phase 20 — all optional so existing stored steps remain valid)
    type: Literal["Bloom", "Pour", "Wait", "Action"] = Field("Pour")
    note: str | None = Field(None, max_length=200)
    water_temp_c: int | None = Field(None, ge=50, le=100)
```

**Backward compatibility at read time (Alpine component):** Existing stored steps have no `type` field. When the steps JSON is embedded in `data-steps` and read by the Alpine component, the JS should default:

```javascript
// In guided-brew-mode.js — _syncStateFromElapsed and coaching line
const stepType = step.type || 'Pour';  // backward compat default
```

**No backfill migration needed:** The JSONB column stores raw dicts. Existing steps missing `type` are valid per the new schema (field has a default). The Pydantic validator fills in the default when reading stored data. A backfill would touch every recipe row unnecessarily. [ASSUMED] — confirm this "default-at-read" approach is acceptable; an alternative is a single `UPDATE recipes SET steps = ...` to add `type: "Pour"` to all existing Pour steps, but this is risky (touching all recipe JSONB in production) and unnecessary.

**Coaching line computation in Alpine (D-09):**

```javascript
// In guided-brew-mode.js — computed coaching line
get coachingLine() {
  const step = this.currentStep;
  if (!step) return '';
  const type = step.type || 'Pour';
  const w = step.water_grams;
  // Pour number = how many Pour steps (including this one) up to current index
  const pourNum = this.steps
    .slice(0, this.currentStepIndex + 1)
    .filter(s => (s.type || 'Pour') === 'Pour').length;

  switch (type) {
    case 'Bloom':
      return w ? 'Bloom — ' + w + 'g' : 'Bloom';
    case 'Pour':
      return 'Pour ' + pourNum + ' — to ' + (w ? w + 'g' : '?');
    case 'Wait':
      return 'Wait — ' + this._formatTime(step.time_seconds || 0);
    case 'Action':
      return step.label || 'Action';
    default:
      return step.label || 'Step ' + (this.currentStepIndex + 1);
  }
},
```

**Cumulative water target (D-11):** The `brew_guided.html` already shows `currentStep.water_grams + 'g / {{ recipe.water_grams }}g total'`. The `water_grams` on steps is cumulative (confirmed from `recipe-step-builder.js` `deltaWater()` and the step preview in `brew_guided.html` line 172). For coaching, the current step's `water_grams` is already the cumulative target. [VERIFIED: app/templates/pages/brew_guided.html + recipe-step-builder.js]

---

### Pattern 5: Bloom Time Auto-Derive (D-13)

**What:** When `currentStep.type === 'Bloom'` and the step transitions (in `_advanceStep()` / `_syncStateFromElapsed()`), auto-record `bloom_time_seconds = elapsedTotalSeconds`.

```javascript
// In _syncStateFromElapsed — when a step completes and we advance
if (stepIdx > prevIndex) {
  const completedStep = this.steps[prevIndex];
  if ((completedStep.type || 'Pour') === 'Bloom') {
    this.bloomTimeSeconds = this.elapsedTotalSeconds;
  }
  // fire cues...
}
```

State additions:
```javascript
firstDripSeconds: null,    // tap-to-mark; null = not yet marked
bloomTimeSeconds: null,    // auto-set when Bloom step transitions
```

Both are passed to `/brew/new` via query params on `finishBrewing()`:
```javascript
if (this.firstDripSeconds !== null) url += '&first_drip=' + this.firstDripSeconds;
if (this.bloomTimeSeconds !== null) url += '&bloom_time=' + this.bloomTimeSeconds;
```

---

### Anti-Patterns to Avoid

- **Incrementing elapsed counter in `_tick()`.** Current code does `this.elapsedTotalSeconds++`. After Phase 20, this must be replaced with `Date.now() - _startTimestamp` computation. Keeping the increment means drift accumulates from iOS freeze gaps.
- **Using Web Workers for the timer.** Web Workers on iOS are also frozen when the screen sleeps. A wall-clock-truth timestamp approach is simpler and more reliable on the target device.
- **Dropping `water_type` column in the migration.** Backward-compatible: retain the column. A future phase can drop it.
- **Backfilling JSONB steps with `type: "Pour"`.** Unnecessary and risky. Use JavaScript-side defaults in the Alpine component and Pydantic-side defaults in StepSchema.
- **Setting `extra="forbid"` then adding required fields without defaults.** Old recipe edit round-trips would fail Pydantic validation if `type` lacked a default. All new StepSchema fields must have defaults.
- **Putting the water-profile create in a separate full-page route.** The inline pattern (like flavor notes) avoids page navigation during the brew setup flow.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CSRF injection on htmx.ajax() | Manual fetch() with custom header logic | Existing `htmx:configRequest` listener in `htmx-listeners.js` | Already handles X-CSRF-Token injection for all HTMX requests; htmx.ajax() routes through it |
| Dedup of freetext during migration | Python loop iterating brew_sessions | PostgreSQL `SELECT DISTINCT INITCAP(TRIM(...))` in migration SQL | DB set operation is transactional; Python loop creates a separate round-trip per row |
| Wake Lock for iOS 16-18.3 | New polyfill | NoSleep.js (already self-hosted at `app/static/js/vendor/NoSleep.min.js`) | Already implemented and wired in the component; Wake Lock native works in iOS 18.4+ |
| Timestamp persistence across page reload | IndexedDB | `localStorage` | Phase 20 does not require reload survival; localStorage is sufficient and already used for cue prefs |
| Per-step coaching routing | Switch statement in template Jinja | Computed getter `coachingLine` in Alpine component | CSP build forbids complex expressions in templates; computed JS getter is the established pattern |

**Key insight:** Every hard problem in this phase has an existing pattern in the codebase to follow. The timer is the only genuinely new technical territory, and the solution (wall-clock timestamp) is simpler than the current approach, not more complex.

---

## Common Pitfalls

### Pitfall 1: setInterval Drift on iOS Screen Sleep
**What goes wrong:** The current `_tick()` does `this.elapsedTotalSeconds++`. If iOS freezes the tab for 30s, `_tick` does not fire, so `elapsedTotalSeconds` reads 30s low when the screen wakes. Steps that should have advanced don't advance.
**Why it happens:** iOS freezes JS after ~5s in background (screen sleep via side button triggers this). [CITED: search results from firt.dev + progressier.com + iOS PWA behavior research]
**How to avoid:** Wall-clock-truth timer pattern (Pattern 1 above). Compute elapsed from `Date.now() - _startTimestamp` on every tick and on `visibilitychange`.
**Warning signs:** After pressing the side button and returning to the brew, `formattedElapsed` shows the time before sleep rather than current time.

### Pitfall 2: AudioContext Re-Suspend Interaction with Pre-Cue
**What goes wrong:** Pre-cue countdown (D-10) fires 3 seconds before transition. If the chime is supposed to fire at the transition moment, the AudioContext may have been re-suspended after the 3s pre-cue window (iOS re-suspends AudioContext after ~5s inactivity per the existing code comment at line 215 of guided-brew-mode.js).
**Why it happens:** Existing code already handles this: `playChime()` calls `audioCtx.resume()` before playing. The pre-cue uses no audio (per D-08: audio fires at transition, not pre-cue). Verify that the pre-cue display update at T-3s does NOT attempt to play the chime — only the transition at T-0 does.
**How to avoid:** Pre-cue is visual only. Chime fires in `_advanceStep()` / step transition, not in the pre-cue countdown display logic.

### Pitfall 3: Pydantic `extra="forbid"` Breaking Existing Step Round-Trips
**What goes wrong:** The recipe edit form loads existing recipe steps (old JSONB shape: `{water_grams, time_seconds, label}`), then the JS adds `type` to them (default "Pour") and submits. If `StepSchema` has `extra="forbid"` and the old-shape step lacks `type`, the validation succeeds (no extra fields). But if the submitting JS sends `type`, `note`, `water_temp_c` as new fields, validation succeeds only if all new fields are declared with defaults. The risk is the other direction: if test fixtures submit steps with `type` to the old schema, they get a 400/ValidationError.
**Why it happens:** `ConfigDict(extra="forbid")` rejects undeclared fields. Old tests or fixtures may submit step dicts without the new fields, which is fine. But any step dict with `type="Pour"` submitted to old schema (before migration) would fail if `type` is not declared.
**How to avoid:** Add all new fields to `StepSchema` with defaults before any form submission path sends them. Migrations run before the app starts, so DB schema is consistent on boot.

### Pitfall 4: data-steps Attribute Escaping on Complex Step Objects
**What goes wrong:** `data-steps='{{ recipe.steps | tojson }}'` works correctly for the current simple step dicts. After adding `note` and `label` fields with user-typed text (potentially containing quotes or backslashes), the `|tojson` filter must still produce valid JSON in a single-quoted HTML attribute.
**Why it happens:** The Jinja `|tojson` filter escapes to valid JSON. In a single-quoted HTML attribute, the double-quotes in JSON are safe. However, if `note` contains a single quote, the HTML attribute breaks. [CITED: project memory "tojson attr quoting + live browser repro" — `|tojson` MUST be in SINGLE-quoted attrs]
**How to avoid:** Keep `data-steps='{{ recipe.steps | tojson }}'` (single-quoted attribute). `|tojson` escapes all characters that could break JSON encoding; double-quotes in JSON are safe inside single-quoted HTML attrs. Single quotes in user data ARE escaped by `|tojson` to `'`.

### Pitfall 5: Step Time_Seconds Is Cumulative, Not Per-Step Duration
**What goes wrong:** A new developer may treat `step.time_seconds` as the duration of that step. In the existing schema and JS, it is the cumulative offset from brew start (confirmed in `_stepDuration()` in `guided-brew-mode.js` lines 99-109 which computes duration as `offset[N] - offset[N-1]`).
**Why it happens:** The design choice (cumulative offsets) enables easy "where are we at time T" queries but is non-obvious.
**How to avoid:** The wall-clock-truth `_syncStateFromElapsed()` in Pattern 1 uses `steps[i].time_seconds` as a cumulative offset (comparing `elapsed >= step.time_seconds`). This is correct and consistent with existing code.

### Pitfall 6: Water Profile NULL vs Empty String
**What goes wrong:** After migration, new sessions POST `water_profile_id=''` (from an empty select or unselected state) which hits the schema as `water_profile_id: int | None = Field(None, ge=1)` and fails validation.
**Why it happens:** HTML form `<select>` without a selection submits an empty string; Pydantic's `int | None` with `Field(None)` coerces empty string to None or raises ValidationError depending on form data parsing.
**How to avoid:** In `BrewSessionCreate`, declare `water_profile_id: int | None = Field(None, ge=1)`. In the router's form parsing, treat empty string as None before passing to Pydantic (standard pattern in this codebase — `raw.get('field') or None`).

### Pitfall 7: visibilitychange Resync During Pause
**What goes wrong:** If the brew is paused and the screen sleeps, on wake `visibilitychange` fires and calls `_resync()`. If `_resync()` does not check `this.isPaused`, it will try to advance elapsed time while paused, messing up the step index.
**Why it happens:** `visibilitychange` fires regardless of pause state.
**How to avoid:** Add `if (!this.isRunning || this.isPaused) return;` at the top of `_resync()`.

---

## Code Examples

### Finishbrewing with Timing Data

```javascript
// Source: app/static/js/alpine-components/guided-brew-mode.js finishBrewing() — extend
finishBrewing() {
  let url = '/brew/new?gbm=1&recipe_id=' + encodeURIComponent(this.recipeId);
  if (this.coffeeId) {
    url += '&coffee_id=' + encodeURIComponent(this.coffeeId);
  }
  url += '&brew_time=' + encodeURIComponent(this.elapsedTotalSeconds);
  if (this.firstDripSeconds !== null) {
    url += '&first_drip=' + encodeURIComponent(this.firstDripSeconds);
  }
  if (this.bloomTimeSeconds !== null) {
    url += '&bloom_time=' + encodeURIComponent(this.bloomTimeSeconds);
  }
  window.location.assign(url);
},
```

### Water Profile Model

```python
# New: app/models/water_profile.py
from __future__ import annotations
from datetime import datetime
from sqlalchemy import BigInteger, Identity, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.models.base import Base

class WaterProfile(Base):
    """Household-shared water profile catalog (GBREW-04, D-01)."""
    __tablename__ = "water_profiles"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
```

### BrewSession Model Changes

```python
# app/models/brew_session.py — add these columns (surgery; existing cols unchanged)
water_profile_id: Mapped[int | None] = mapped_column(
    BigInteger,
    ForeignKey("water_profiles.id", ondelete="SET NULL"),
    nullable=True,
)
first_drip_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
bloom_time_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
# water_type: Mapped[str | None] — RETAINED (deprecated, not dropped)
```

### BrewSessionCreate Schema Changes

```python
# app/schemas/brew_session.py — replace water_type handling, add timing fields
water_profile_id: int | None = Field(None, ge=1)
first_drip_seconds: int | None = Field(None, ge=0, le=86400)
bloom_time_seconds: int | None = Field(None, ge=0, le=86400)
# water_type: str = Field("", max_length=100)  — REMOVE or deprecate
```

---

## Runtime State Inventory

> Rename/refactor check: `water_type` → `water_profile_id` is a data migration, not just a rename.

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | `brew_sessions.water_type` — freetext in PostgreSQL. Current data: "Tap", "Filtered", "Bottled", "Third Wave Water" per datalist values in brew_prefill_fields.html | Data migration: seed water_profiles, link sessions via FK update |
| Live service config | None — no external services store water_type | None |
| OS-registered state | None | None |
| Secrets/env vars | None — water_type is not a key name anywhere | None |
| Build artifacts | None — water_type is a DB column, no compiled artifacts | None |

**Nothing found in categories 2-5:** Verified by codebase grep — `water_type` appears only in `brew_session.py` (model), `brew_session.py` (schema), `brew_prefill_fields.html` (template), and the datalist options. No config files, no env vars, no scheduler references.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| setInterval accumulation | Wall-clock timestamp recovery | Phase 20 | Timer self-corrects after screen sleep |
| freetext water_type | Named water_profiles catalog | Phase 20 | Consistent tracking; analytics-ready |
| Steps: {label, water_grams, time_seconds} | Steps: {type, label, water_grams?, water_temp_c?, time_seconds, note?} | Phase 20 | Enables coaching, Wait/Action steps |
| No first-drip / bloom tracking | first_drip_seconds + bloom_time_seconds on brew_session | Phase 20 | Brew data on par with Beanconqueror |
| Wake Lock broken in iOS PWA | Wake Lock API works in iOS 18.4+ standalone PWA | iOS 18.4 (Mar 2025) | Current iPhones get native screen-on; NoSleep.js fallback still needed for iOS < 18.4 |

**Deprecated:**
- `brew_session.water_type` Text column: deprecated in favor of `water_profile_id` FK; retained but no longer written by new code.
- `_tick()` counter increment pattern: replaced by wall-clock-truth computation.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `water_type` column is retained (not dropped) in Phase 20 migration | Architecture Patterns §Migration | Low — safe to drop in a future cleanup if confirmed; retaining it is safe |
| A2 | Blank/NULL water_type sessions get `water_profile_id = NULL` (no "Unspecified" seed) | Pattern 3 (migration) | Low — if John prefers an "Unspecified" profile, add one seed row and link those sessions |
| A3 | Default-at-read (JS `step.type \|\| 'Pour'`) is acceptable for old recipe steps without backfill | Pattern 4 (JSONB) | Medium — if backfill is required for analytics queries against the JSONB, add a migration; if it's JS-only UX, no migration needed |
| A4 | `water_temp_c` range on StepSchema is `ge=50, le=100` | Code Examples | Low — can adjust to `ge=0` if cold-brew or ambient-temp steps are desired |
| A5 | iOS Web Workers are also frozen on screen sleep (so Web Workers don't help for timer) | Pattern 1 (timer) | Low — authoritative MDN / WebKit sources confirm JS execution freeze includes workers; wall-clock approach handles this regardless |

---

## Open Questions

1. **Water_type column drop timing**
   - What we know: column is deprecated after Phase 20 migration
   - What's unclear: whether John wants it dropped in this phase or deferred
   - Recommendation: defer the DROP to a future cleanup migration; retaining it is zero-cost and safer

2. **Water profile management UI beyond inline-create**
   - What we know: D-02 says inline-create is the floor; no admin-only gate
   - What's unclear: whether the phase should include a lightweight list/edit/archive page for water profiles
   - Recommendation: omit for Phase 20 (Polish milestone); inline-create + the ability to see existing profiles in the select is sufficient

3. **INITCAP normalization for seeded profile names**
   - What we know: `INITCAP(TRIM(water_type))` converts "tap" → "Tap", "FILTERED" → "Filtered"
   - What's unclear: whether existing production data has any unusual casing that would produce ugly profile names
   - Recommendation: `INITCAP(TRIM(...))` is correct for typical values; edge case is all-caps abbreviations like "TDS" → "Tds"; only John can confirm if that matters

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker Compose | Build + test | Assumed ✓ | — | — |
| PostgreSQL 16 | Migration | Assumed ✓ | 16-alpine | — |
| NoSleep.js | Wake lock fallback for iOS < 18.4 | ✓ (self-hosted) | v0.12.0 | None needed — already present |
| Wake Lock API | Screen-on for iOS 18.4+ | ✓ (iOS 18.4+) | — | NoSleep.js fallback already wired |

Step 2.6: No blocking missing dependencies. All required tools are present.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.x + httpx TestClient |
| Config file | none — see conftest.py |
| Quick run command | `docker compose exec coffee-snobbery python -m pytest -q tests/test_phase20_water_profiles.py tests/test_phase20_step_schema.py tests/test_phase20_brew_session.py -x` |
| Full suite command | `docker compose exec coffee-snobbery python -m pytest -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GBREW-01 | Timer state: elapsed computed from Date.now() - startTimestamp (not counter increment) | unit (JS) | Manual browser verification on iPhone PWA | ❌ Wave 0 — manual |
| GBREW-01 | finishBrewing() URL includes brew_time from elapsedTotalSeconds | unit (Python) | `pytest tests/test_phase20_brew_session.py::test_gbm_finish_url_has_brew_time -x` | ❌ Wave 0 |
| GBREW-02 | coachingLine computed correctly for each step type | unit (Python — via StepSchema validation) | `pytest tests/test_phase20_step_schema.py::test_coaching_line_by_type -x` | ❌ Wave 0 |
| GBREW-03 | first_drip_seconds + bloom_time_seconds accepted by BrewSessionCreate schema | unit | `pytest tests/test_phase20_brew_session.py::test_timing_fields_schema -x` | ❌ Wave 0 |
| GBREW-03 | New columns present in DB after migration | migration | `pytest tests/test_migrations.py -k test_phase20` | ❌ Wave 0 |
| GBREW-04 | POST /water-profiles creates a profile and fires HX-Trigger | integration | `pytest tests/test_phase20_water_profiles.py::test_create_water_profile -x` | ❌ Wave 0 |
| GBREW-04 | Migration seeds water_profiles from distinct brew_session.water_type values | migration | `pytest tests/test_phase20_water_profiles.py::test_migration_seeds_profiles -x` | ❌ Wave 0 |
| GBREW-04 | Migration links historical sessions to correct profile FK | migration | `pytest tests/test_phase20_water_profiles.py::test_migration_links_sessions -x` | ❌ Wave 0 |
| GBREW-04 | Sessions with blank/NULL water_type get NULL water_profile_id | migration | `pytest tests/test_phase20_water_profiles.py::test_migration_null_water_type -x` | ❌ Wave 0 |
| GBREW-05 | Guided Brew pages load without errors at 375px | smoke | `pytest tests/test_phase20_mobile.py::test_brew_guided_loads -x` | ❌ Wave 0 |
| GBREW-06 | StepSchema accepts Wait step with water_grams=None | unit | `pytest tests/test_phase20_step_schema.py::test_wait_step_no_water -x` | ❌ Wave 0 |
| GBREW-06 | StepSchema validates water_temp_c range 50-100 | unit | `pytest tests/test_phase20_step_schema.py::test_step_water_temp_range -x` | ❌ Wave 0 |
| GBREW-06 | Old step dicts without `type` field still validate via StepSchema | unit | `pytest tests/test_phase20_step_schema.py::test_backward_compat_no_type -x` | ❌ Wave 0 |
| D-15 (timer) | Timer accuracy on wake is a manual test on physical device | manual | Playwright at 375px covers layout; timer accuracy is human-verified | N/A |

**Highest-value automated tests:**
1. Migration data-seed test: insert synthetic `brew_sessions` rows with varied water_type values (including blank, NULL, cased variants), run migration, assert correct `water_profiles` rows and FK links.
2. StepSchema backward compatibility: old `{water_grams: 100, time_seconds: 45, label: "Bloom"}` dict must validate without errors after the schema extension.
3. Water profile inline-create: POST `/water-profiles` returns 200 + HX-Trigger header with correct payload.

### Sampling Rate

- **Per task commit:** `python -m pytest -q tests/test_phase20_*.py -x`
- **Per wave merge:** `python -m pytest -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_phase20_water_profiles.py` — covers GBREW-04 migration + endpoint
- [ ] `tests/test_phase20_step_schema.py` — covers GBREW-06 schema + backward compat
- [ ] `tests/test_phase20_brew_session.py` — covers GBREW-03 timing fields + schema
- [ ] `tests/test_phase20_mobile.py` — smoke: guided brew pages load, 375px check

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | All new endpoints use `Depends(require_user)` — same as existing |
| V3 Session Management | no | No session changes |
| V4 Access Control | yes | Water profiles are household-shared; no per-user ownership gate needed; POST /water-profiles requires authenticated user only |
| V5 Input Validation | yes | Pydantic v2 WaterProfileCreate + StepSchema; `extra="forbid"` on all schemas |
| V6 Cryptography | no | No crypto changes |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| CSRF on POST /water-profiles | Tampering | CSRF middleware (starlette-csrf) covers all POST; new endpoint is not exempt |
| Mass assignment on WaterProfileCreate | Tampering | `ConfigDict(extra="forbid")` on schema; router reads raw form then validates |
| XSS via water profile name in template | Tampering | Jinja2 autoescape ON globally; `|tojson` for JS contexts; no `|safe` on user data |
| Stored JSONB step `note` field rendered | Tampering | Template autoescape handles; note is plain text, no HTML rendering |
| water_profile_id integer tampering | Tampering | `ge=1` in schema + FK constraint in DB; SET NULL ondelete means invalid FK simply nulls |

---

## Sources

### Primary (HIGH confidence)
- `app/static/js/alpine-components/guided-brew-mode.js` — exact current timer implementation (setInterval counter, visibilitychange wake lock re-acquire, step state)
- `app/schemas/recipe.py` — StepSchema exact current shape (`extra="forbid"`, water_grams required)
- `app/schemas/brew_session.py` — BrewSessionCreate exact current shape (water_type freetext)
- `app/models/brew_session.py` — brew_sessions column set (water_type Text nullable)
- `app/models/recipe.py` — JSONB steps column
- `app/templates/pages/brew_guided.html` — exact current timer screen layout
- `app/templates/fragments/brew_prefill_fields.html` — water_type datalist input
- `app/templates/fragments/recipe_step_builder.html` — current step builder fields
- `app/static/js/alpine-components/recipe-step-builder.js` — recipeStepBuilder: addStep(), setters, stepsJson
- `app/static/js/alpine-components/flavor-tag-input.js` — observedFlavorNotes: createFromQuery(), htmx.ajax(), HX-Trigger listener
- `app/routers/flavor_notes.py` — inline-create pattern: HX-Trigger header payload, as_modal POST, form data reading
- `app/migrations/versions/p15_1_multi_origin.py` — canonical data migration pattern (inline DDL, COALESCE normalization)
- `app/migrations/versions/p19_ai_research_predict.py` — down_revision = p19 (current HEAD)
- WebKit bug 254545 — Wake Lock API fixed in iOS 18.4 (March 2025): https://bugs.webkit.org/show_bug.cgi?id=254545

### Secondary (MEDIUM confidence)
- firt.dev "Understanding JavaScript in the Background" — iOS ~5s background freeze before JS stops; `visibilitychange` is the recovery hook
- progressier.com — Page Lifecycle API freeze/resume not implemented on iOS Safari; `visibilitychange` is the substitute
- iOS PWA behavior research — Web Workers also frozen on iOS screen sleep (same process freeze)

### Tertiary (LOW confidence)
- Training knowledge on Alpine.js CSP build computed getter patterns (consistent with codebase evidence)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages; existing stack verified from codebase
- Timer mechanism (GBREW-01): HIGH — wall-clock-truth pattern derived from code analysis + iOS behavior confirmed via WebKit bug tracker
- Migration shape (GBREW-04): HIGH — pattern derived from existing p15_1_multi_origin.py; SQL syntax verified from migration
- StepSchema extension (GBREW-06): HIGH — current schema read directly from source
- iOS Wake Lock / freeze behavior: MEDIUM — confirmed via WebKit bug 254545 and multiple secondary sources; not directly testable in this research context

**Research date:** 2026-05-29
**Valid until:** 2026-06-28 (stable stack; iOS behavior unlikely to change)
