# Phase 20: Guided Brew Polish - Pattern Map

**Mapped:** 2026-05-29
**Files analyzed:** 13 (5 new, 8 modified)
**Analogs found:** 13 / 13

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `app/models/water_profile.py` | model | CRUD | `app/models/flavor_note.py` | exact |
| `app/schemas/water_profile.py` | schema | request-response | `app/schemas/flavor_note.py` | exact |
| `app/routers/water_profiles.py` | router | request-response | `app/routers/flavor_notes.py` | exact |
| `app/services/water_profiles.py` | service | CRUD | `app/services/flavor_notes.py` | exact |
| `app/migrations/versions/p20_water_profiles.py` | migration | batch | `app/migrations/versions/p15_1_multi_origin.py` | exact |
| `app/schemas/recipe.py` | schema | request-response | self (extend existing StepSchema) | self-extension |
| `app/models/brew_session.py` | model | CRUD | self (add 3 columns) | self-extension |
| `app/schemas/brew_session.py` | schema | request-response | self (extend BrewSessionCreate) | self-extension |
| `app/static/js/alpine-components/guided-brew-mode.js` | component | event-driven | self (extend existing component) | self-extension |
| `app/static/js/alpine-components/recipe-step-builder.js` | component | event-driven | self (extend existing component) | self-extension |
| `app/templates/pages/brew_guided.html` | template | request-response | self (extend existing timer screen) | self-extension |
| `app/templates/fragments/recipe_step_builder.html` | template | request-response | self (extend existing step row) | self-extension |
| `app/templates/fragments/brew_prefill_fields.html` | template | request-response | self (replace water_type block) | self-extension |

---

## Pattern Assignments

### `app/models/water_profile.py` (model, CRUD)

**Analog:** `app/models/flavor_note.py`

**Imports pattern** (lines 1-22):
```python
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Identity, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base
```

**Core model pattern** (lines 26-49 of flavor_note.py — mirror, simpler):
```python
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

Key differences from FlavorNote: plain `Text` for `name` (not CITEXT — dedup handled by migration normalization, not DB-level citext), no `archived` column, no `CheckConstraint` in `__table_args__`, no `category` field.

---

### `app/schemas/water_profile.py` (schema, request-response)

**Analog:** `app/schemas/flavor_note.py` (entire file, lines 1-37)

**Full file pattern** (mirrors FlavorNoteCreate, simplified):
```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class WaterProfileCreate(BaseModel):
    """Water-profile inline-create form. Validation errors returned as JSON."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=80)
    notes: str | None = Field(None, max_length=500)


__all__ = ["WaterProfileCreate"]
```

Key differences from FlavorNoteCreate: no `category` field, adds optional `notes` field, `max_length=80` on name (UI-SPEC §1 says "Profile name" input is `maxlength="80"`).

---

### `app/routers/water_profiles.py` (router, request-response)

**Analog:** `app/routers/flavor_notes.py`

**Imports pattern** (lines 44-61 of flavor_notes.py):
```python
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.dependencies.auth import require_user
from app.dependencies.db import get_session
from app.models.user import User
from app.schemas.water_profile import WaterProfileCreate
from app.services import water_profiles as water_profiles_service
from app.services.form_validation import DuplicateNameError, errors_by_field
from app.templates_setup import templates

router = APIRouter(prefix="/water-profiles")
```

**Core POST handler pattern** (lines 183-264 of flavor_notes.py — the `as_modal` path is the entire use case for water profiles):
```python
@router.post("", response_class=HTMLResponse)
async def create_water_profile(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    form_data = await request.form()
    skip = {"X-CSRF-Token"}
    raw = {k: v for k, v in form_data.items() if k not in skip}
    try:
        form = WaterProfileCreate(**raw)
    except ValidationError as exc:
        # Return JSON error for Alpine to display inline (no fragment swap needed)
        from fastapi.responses import JSONResponse
        return JSONResponse(
            {"errors": errors_by_field(exc)},
            status_code=422,
        )
    try:
        profile = water_profiles_service.create_water_profile(
            db, name=form.name, notes=form.notes, by_user_id=user.id
        )
    except DuplicateNameError:
        from fastapi.responses import JSONResponse
        return JSONResponse({"errors": {"name": "Profile name already exists."}}, status_code=422)

    # HX-Trigger pattern locked from flavor_notes.py lines 251-264
    response = templates.TemplateResponse(
        request=request,
        name="fragments/empty.html",
        context={},
    )
    response.headers["HX-Trigger"] = json.dumps({
        "water-profile-created": {
            "water_profile_id": profile.id,
            "name": profile.name,
        }
    })
    return response
```

**GET list endpoint** (needed to populate the select on brew form load):
```python
@router.get("", response_class=HTMLResponse)
def list_water_profiles(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    profiles = water_profiles_service.list_water_profiles(db)
    # Returns JSON for Alpine to consume, OR rendered fragment
    # (follow the flavor_notes HX-Request branch pattern)
    ...
```

Note: The water profile inline-create POST returns JSON errors (not an HTML fragment re-render) because the create form is Alpine-managed, not an HTMX fragment swap. This deviates from flavor_notes.py intentionally — the inline Alpine component handles error display without a server-rendered form fragment.

**Auth pattern** (consistent across all routers):
```python
user: User = Depends(require_user),  # noqa: B008 — FastAPI canonical Form 1.
db: Session = Depends(get_session),  # noqa: B008 — FastAPI canonical Form 1.
```

---

### `app/services/water_profiles.py` (service, CRUD)

**Analog:** `app/services/flavor_notes.py` (lines 1-100 cover the relevant pattern)

**Imports pattern** (lines 37-53 of flavor_notes.py):
```python
from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.water_profile import WaterProfile
from app.services.form_validation import DuplicateNameError

log = structlog.get_logger(__name__)
```

**Core create function pattern** (lines 56-80 of flavor_notes.py):
```python
def create_water_profile(
    db: Session,
    *,
    name: str,
    notes: str | None,
    by_user_id: int,
) -> WaterProfile:
    profile = WaterProfile(name=name, notes=notes)
    db.add(profile)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DuplicateNameError(name)
    db.refresh(profile)
    log.info("water_profile.created", water_profile_id=profile.id, name=profile.name,
             by_user_id=by_user_id)
    return profile


def list_water_profiles(db: Session) -> list[WaterProfile]:
    return list(db.scalars(select(WaterProfile).order_by(WaterProfile.name)))


def get_water_profile(db: Session, *, water_profile_id: int) -> WaterProfile | None:
    return db.get(WaterProfile, water_profile_id)
```

Key simplification from flavor_notes service: no `archived` flag, no `usage_count` join, no audit events needed at this scope (water profiles are low-stakes shared catalog).

---

### `app/migrations/versions/p20_water_profiles.py` (migration, batch)

**Analog:** `app/migrations/versions/p15_1_multi_origin.py` (entire file)
**Down revision source:** `app/migrations/versions/p19_ai_research_predict.py` line 44: `revision: str = "p19_ai_research_predict"`

**Header / revision boilerplate pattern** (lines 30-40 of p15_1_multi_origin.py):
```python
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "p20_water_profiles"
down_revision: str | Sequence[str] | None = "p19_ai_research_predict"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
```

**op.create_table pattern** (lines 47-60 of p15_1_multi_origin.py — adapt):
```python
def upgrade() -> None:
    # 1. Create water_profiles table
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
```

**op.execute data-seed pattern** (lines 63-76 of p15_1_multi_origin.py — COALESCE/NULLIF convention):
```python
    # 2. Seed from distinct normalized water_type values (INITCAP/TRIM normalization)
    op.execute("""
        INSERT INTO water_profiles (name)
        SELECT DISTINCT INITCAP(TRIM(water_type)) AS name
        FROM brew_sessions
        WHERE water_type IS NOT NULL
          AND TRIM(water_type) != ''
        ORDER BY INITCAP(TRIM(water_type))
    """)

    # 3. Add water_profile_id FK (nullable; SET NULL on profile delete)
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
    # water_type column is RETAINED — deprecated but not dropped this phase
```

**downgrade pattern** (lines 86-93 of p15_1_multi_origin.py):
```python
def downgrade() -> None:
    op.drop_column("brew_sessions", "bloom_time_seconds")
    op.drop_column("brew_sessions", "first_drip_seconds")
    op.drop_index("ix_brew_sessions_water_profile_id", table_name="brew_sessions")
    op.drop_column("brew_sessions", "water_profile_id")
    op.drop_index("ix_water_profiles_name", table_name="water_profiles")
    op.drop_table("water_profiles")
```

---

### `app/schemas/recipe.py` — StepSchema extension (schema, request-response)

**Analog:** self (lines 37-44 — the existing StepSchema to extend)

**Current StepSchema** (lines 37-44 of recipe.py):
```python
class StepSchema(BaseModel):
    """One step in a recipe's JSONB ``steps`` array (D-10)."""

    model_config = ConfigDict(extra="forbid")

    water_grams: int = Field(..., ge=0, le=2000)
    time_seconds: int = Field(..., ge=0, le=3600)
    label: str = Field("", max_length=80)
```

**Extended StepSchema** — surgical replacement of the class body:
```python
from typing import Literal

class StepSchema(BaseModel):
    """One step in a recipe's JSONB ``steps`` array (D-10, extended Phase 20)."""

    model_config = ConfigDict(extra="forbid")

    # Existing fields — water_grams is now optional (D-07: Wait/Action steps)
    water_grams: int | None = Field(None, ge=0, le=2000)
    time_seconds: int = Field(..., ge=0, le=3600)
    label: str = Field("", max_length=80)

    # New fields (Phase 20 — all optional/defaulted for backward compat)
    type: Literal["Bloom", "Pour", "Wait", "Action"] = Field("Pour")
    note: str | None = Field(None, max_length=200)
    water_temp_c: int | None = Field(None, ge=50, le=100)
```

The `Literal` import must be added at the top of `recipe.py`. The `from __future__ import annotations` is already present. The `ConfigDict(extra="forbid")` is retained — all new fields have defaults so old stored step dicts (lacking `type`/`note`/`water_temp_c`) remain valid.

---

### `app/models/brew_session.py` — column additions (model, CRUD)

**Analog:** self — surgical column additions after `brew_time_seconds` (line 133-136)

**Existing anchor column** (lines 133-136 of brew_session.py):
```python
    brew_time_seconds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
```

**New columns to add immediately after** (FK pattern from lines 86-110):
```python
    # --- water profile (GBREW-04 / D-03) ---
    # water_type is RETAINED but deprecated; new sessions use water_profile_id
    water_profile_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("water_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )

    # --- brew timing (GBREW-03 / D-12..D-14) ---
    first_drip_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bloom_time_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

Import additions required at top of file: `ForeignKey` is already imported. Verify `BigInteger` is imported (it is, line 44).

---

### `app/schemas/brew_session.py` — field additions (schema, request-response)

**Analog:** self — surgical additions to `BrewSessionCreate`

**Existing anchor field** (line 99 of brew_session.py):
```python
    brew_time_seconds: int | None = Field(None, ge=0, le=86400)
```

**New fields to add immediately after** (pattern from existing optional FK fields lines 82-86):
```python
    # --- water profile (GBREW-04) — replaces water_type freetext in new sessions
    water_profile_id: int | None = Field(None, ge=1)

    # --- brew timing (GBREW-03) ---
    first_drip_seconds: int | None = Field(None, ge=0, le=86400)
    bloom_time_seconds: int | None = Field(None, ge=0, le=86400)
```

`water_type` field on line 88 (`water_type: str = Field("", max_length=100)`) is retained in the schema for backward compat but will no longer be written by new form submissions. The router that processes the brew form must treat the empty-string `water_profile_id` case: `raw.get('water_profile_id') or None` before passing to Pydantic (pattern from line 197-199 of flavor_notes.py: `skip = {"X-CSRF-Token", "as_modal"}`).

---

### `app/static/js/alpine-components/guided-brew-mode.js` — timer + coaching (component, event-driven)

**Analog:** self (entire file, 374 lines) — extend in-place

**Current state block** (lines 17-34 — new state properties to add):
```javascript
// Add to the state object after line 34:
_startTimestamp: null,   // Date.now() at brew start — wall-clock truth
_pausedOffset: 0,        // accumulated pause duration in seconds
firstDripSeconds: null,  // tap-to-mark; null = not yet marked
bloomTimeSeconds: null,  // auto-set when Bloom step transitions
```

**Replace `_startTimer()` lines 146-149** with:
```javascript
_startTimer() {
  this._stopTimer();
  if (!this._startTimestamp) {
    this._startTimestamp = Date.now() - (this.elapsedTotalSeconds * 1000);
    try { localStorage.setItem('snobbery:gbm:start', String(this._startTimestamp)); } catch(_) {}
  }
  this._timer = setInterval(() => this._tick(), 1000);
},
```

**Replace `_tick()` lines 158-168** with:
```javascript
_tick() {
  const elapsed = Math.floor((Date.now() - this._startTimestamp) / 1000) - this._pausedOffset;
  this.elapsedTotalSeconds = elapsed;
  this._syncStateFromElapsed(elapsed);
},
```

**New `_resync()` method** (insert after `_tick`):
```javascript
_resync() {
  if (!this._startTimestamp || !this.isRunning || this.isPaused) return;
  const elapsed = Math.floor((Date.now() - this._startTimestamp) / 1000) - this._pausedOffset;
  this.elapsedTotalSeconds = elapsed;
  this._syncStateFromElapsed(elapsed);
},
```

**New `_syncStateFromElapsed()` method** (replaces `_advanceStep` auto-advance logic):
```javascript
_syncStateFromElapsed(elapsed) {
  // steps[i].time_seconds is a CUMULATIVE offset from brew start (not per-step duration).
  // Walk steps to find which should be active at elapsed seconds.
  let stepIdx = 0;
  for (let i = 0; i < this.steps.length; i++) {
    if (elapsed >= (this.steps[i].time_seconds || 0)) {
      stepIdx = i + 1;
    } else {
      break;
    }
  }
  if (stepIdx >= this.steps.length) {
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
  if (stepIdx > prevIndex) {
    const completedStep = this.steps[prevIndex];
    if ((completedStep.type || 'Pour') === 'Bloom') {
      this.bloomTimeSeconds = this.elapsedTotalSeconds;
    }
    if (this.cuePrefs.chime) this.playChime();
    if (this.cuePrefs.vibrate) this.triggerVibration();
  }
},
```

**Extend `_setupVisibilityReacquire()` lines 282-289** (add resync call — resync first, then wake lock):
```javascript
_setupVisibilityReacquire() {
  this._onVisibility = async () => {
    if (document.visibilityState === 'visible' && this.isRunning && !this.isPaused) {
      this._resync();                    // NEW: self-correct before re-acquiring lock
      await this.requestWakeLock();
    }
  };
  document.addEventListener('visibilitychange', this._onVisibility);
},
```

**Extend `pause()` lines 125-129** (record pause timestamp):
```javascript
pause() {
  if (!this.isRunning || this.isPaused) return;
  this.isPaused = true;
  this._pausedAt = Date.now();
  this._stopTimer();
},
```

**Extend `resume()` lines 131-135** (add paused duration to offset):
```javascript
resume() {
  if (!this.isRunning || !this.isPaused) return;
  this.isPaused = false;
  if (this._pausedAt) {
    this._pausedOffset += Math.floor((Date.now() - this._pausedAt) / 1000);
    this._pausedAt = null;
  }
  this._startTimer();
},
```

**New computed getters** (insert after `formattedElapsed` getter):
```javascript
get coachingLine() {
  const step = this.currentStep;
  if (!step) return '';
  const type = step.type || 'Pour';
  const w = step.water_grams;
  const pourNum = this.steps
    .slice(0, this.currentStepIndex + 1)
    .filter(s => (s.type || 'Pour') === 'Pour').length;
  switch (type) {
    case 'Bloom': return w ? 'Bloom — ' + w + 'g' : 'Bloom';
    case 'Pour':  return 'Pour ' + pourNum + ' — to ' + (w ? w + 'g' : '?');
    case 'Wait':  return 'Wait — ' + this._formatTime(step.time_seconds || 0);
    case 'Action': return step.label || 'Action';
    default: return step.label || 'Step ' + (this.currentStepIndex + 1);
  }
},

get stepTypeBadge() {
  const step = this.currentStep;
  return step ? (step.type || 'Pour').toUpperCase() : '';
},

get stepNote() {
  const step = this.currentStep;
  return (step && step.note) ? step.note : '';
},

get stepWaterTemp() {
  const step = this.currentStep;
  return (step && step.water_temp_c) ? 'at ' + step.water_temp_c + '°C' : '';
},

get preCueCountdown() {
  if (this.remainingSeconds > 3 || this.remainingSeconds <= 0) return 0;
  return this.remainingSeconds;
},

get isPreCue() {
  return this.preCueCountdown > 0;
},
```

**Extend `destroy()` lines 54-61** (clear localStorage keys):
```javascript
destroy() {
  this._stopTimer();
  this._releaseWakeLock();
  if (this._onVisibility) {
    document.removeEventListener('visibilitychange', this._onVisibility);
    this._onVisibility = null;
  }
  try {
    localStorage.removeItem('snobbery:gbm:start');
  } catch(_) {}
},
```

**Extend `finishBrewing()` lines 357-365** (add timing params):
```javascript
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

**New `markFirstDrip()` action method**:
```javascript
markFirstDrip() {
  if (this.firstDripSeconds === null) {
    this.firstDripSeconds = this.elapsedTotalSeconds;
  }
},

clearFirstDrip() {
  this.firstDripSeconds = null;
},
```

---

### `app/static/js/alpine-components/recipe-step-builder.js` — type/note/temp (component, event-driven)

**Analog:** self (entire file, 174 lines) — extend in-place

**Extend `init()` default step** (lines 41-44 — seed the new fields on the Bloom default):
```javascript
if (this.steps.length === 0) {
  this.steps = [{ type: 'Bloom', water_grams: 50, time_seconds: 45, label: 'Bloom', note: null, water_temp_c: null }];
}
```

**Extend `addStep()` lines 46-58** (add type/note/water_temp_c to new step object):
```javascript
addStep() {
  const prev = this.steps[this.steps.length - 1] || {
    type: 'Pour', water_grams: 0, time_seconds: 0, label: '', note: null, water_temp_c: null,
  };
  this.steps.push({
    type: 'Pour',
    water_grams: (prev.water_grams || 0) + 50,
    time_seconds: (prev.time_seconds || 0) + 45,
    label: '',
    note: null,
    water_temp_c: null,
  });
},
```

**New setter methods** (insert after `setTime()` line 91 — same pattern as existing setters):
```javascript
setType(i, v) {
  this.steps[i].type = v || 'Pour';
  // When type is Wait or Action, clear water_grams (D-07)
  if (v === 'Wait' || v === 'Action') {
    this.steps[i].water_grams = null;
  }
},

setNote(i, v) {
  this.steps[i].note = v.trim() || null;
},

setWaterTemp(i, v) {
  const n = parseInt(v, 10);
  this.steps[i].water_temp_c = Number.isFinite(n) ? n : null;
},
```

**Computed `timelineSegments` getter** (lines 141-172 — update `label` fallback to include type):
```javascript
// In the return map, update label fallback:
label: step.label || (step.type || 'Step ' + (idx + 1)),
```

The `stepsJson` getter on line 137 requires no change — `JSON.stringify(this.steps)` serializes all new fields automatically.

---

### `app/templates/pages/brew_guided.html` — timer screen redesign (template, request-response)

**Analog:** self (lines 136-228, the TIMER SCREEN block) — extend in-place

**Script loading** (lines 21-25 — no change needed, recipe-step-builder.js is not loaded here):
The existing `guided-brew-mode.js` defer/nonce pattern is the canonical form for this page. New JS is added to that file, not as a separate script tag.

**data-steps attribute** (line 33 — critical, no change needed):
```html
data-steps='{{ recipe.steps | tojson }}'
```
Single-quoted attr + `|tojson` is the correct pattern per project memory "tojson attr quoting + live browser repro". User-typed `note` values with single quotes are escaped by `|tojson`.

**Step preview list on START SCREEN** (lines 72-80 — add type badge):
```html
<span class="text-sm font-medium">
  {{ step.type or 'Pour' }} — {{ step.label or ('Step ' ~ loop.index) }}
</span>
```

**TIMER SCREEN changes** — replace the `x-show="isRunning && !isDone"` block content following this structure:

Wake lock indicator (lines 141-149): no change needed — already wired.

Step counter (lines 151-154): no change needed.

**Insert pre-cue countdown** BEFORE the main countdown (after step counter):
```html
{# Pre-cue countdown (D-10) — shown 3s before step transition #}
<div x-show="isPreCue" aria-live="polite" class="text-center">
  <p class="text-2xl font-semibold text-espresso-600 dark:text-cream-300">Get ready&hellip;</p>
  <p class="text-5xl font-semibold tabular-nums text-espresso-700 dark:text-cream-100"
     x-text="preCueCountdown"></p>
</div>
```

**Replace current step card** (lines 167-173) with full coach view card:
```html
<div class="rounded-lg bg-espresso-700 text-cream-50 px-4 py-5 flex flex-col gap-1"
     aria-live="assertive">
  <span class="text-xs font-semibold uppercase tracking-wide opacity-70"
        x-text="stepTypeBadge"></span>
  <p class="text-xl font-semibold" x-text="coachingLine"></p>
  <p class="text-sm opacity-80" x-show="stepNote" x-text="stepNote"></p>
  <p class="text-sm opacity-70" x-show="stepWaterTemp" x-text="stepWaterTemp"></p>
</div>
```

**Tap-to-mark button** (insert after coach card, before next-step preview):
```html
{# First-drip tap-to-mark (D-12 / D-14) #}
<div x-show="firstDripSeconds === null">
  <button type="button"
          x-on:click="markFirstDrip()"
          aria-label="Mark first drip time"
          class="w-full rounded bg-espresso-700 text-cream-50 text-base font-semibold
                 min-h-[56px] flex items-center justify-center hover:bg-espresso-800">
    Mark first drip
  </button>
</div>
<div x-show="firstDripSeconds !== null"
     class="rounded border border-espresso-200 dark:border-espresso-700 px-4 py-3
            flex items-center justify-between text-sm">
  <span class="tabular-nums">First drip: <span x-text="_formatTime(firstDripSeconds)"></span></span>
  <button type="button" x-on:click="clearFirstDrip()"
          aria-label="Clear first drip time"
          class="text-espresso-600 dark:text-cream-300 underline min-h-[44px] inline-flex items-center">
    Clear
  </button>
</div>
```

**Bloom auto-record indicator** (insert after coach card when Bloom step is active):
```html
<p x-show="currentStep && (currentStep.type || 'Pour') === 'Bloom'"
   class="text-sm text-espresso-600 dark:text-cream-300 text-center">
  Bloom will auto-record
</p>
<p x-show="bloomTimeSeconds !== null"
   class="text-sm text-espresso-600 dark:text-cream-300 tabular-nums text-center">
  Bloom: <span x-text="bloomTimeSeconds !== null ? _formatTime(bloomTimeSeconds) : ''"></span>
</p>
```

**Safe-area for bottom cancel button** (lines 220-227 — extend existing `mt-auto` div per UI-SPEC §Safe-Area):
```html
<div class="mt-auto pt-2 flex justify-center pb-[max(env(safe-area-inset-bottom),_16px)]">
  <button type="button" x-on:click="cancelWithoutLogging()"
          class="text-sm text-espresso-600 dark:text-cream-300 underline min-h-[44px] inline-flex items-center">
    &times; Cancel without logging
  </button>
</div>
```

The `pb-[max(env(safe-area-inset-bottom),_16px)]` value follows the Phase 15 safe-area technique (commit `982c0e6`). The existing `.content-nav-safe-area` CSS class is NOT used here — that class is for body content under the fixed nav; the brew screen is full-screen `fixed inset-0 z-50` and owns its own safe-area padding.

---

### `app/templates/fragments/recipe_step_builder.html` — type/note/temp fields (template, request-response)

**Analog:** self (lines 29-88) — extend step row inside `<template x-for>`

**Extend the flex row** (lines 49-77) by adding a Type select and Temp input to the existing `flex flex-wrap gap-3 items-end` row:

**Type select** (insert BEFORE the Label input, width `w-32`):
```html
<label class="flex flex-col gap-1 w-32">
  <span class="text-sm font-semibold">Type</span>
  <select :value="step.type || 'Pour'"
          x-on:change="setType(idx, $event.target.value)"
          :aria-label="'Step type for step ' + (idx + 1)"
          class="rounded border border-espresso-200 px-2 py-3 text-base">
    <option value="Pour">Pour</option>
    <option value="Bloom">Bloom</option>
    <option value="Wait">Wait</option>
    <option value="Action">Action</option>
  </select>
</label>
```

**Water (g) field** (lines 59-67) — add `:disabled` and `opacity` for Wait/Action:
```html
<label class="flex flex-col gap-1 w-24"
       :class="(step.type === 'Wait' || step.type === 'Action') ? 'opacity-40' : ''">
  <span class="text-sm font-semibold">Water (g)</span>
  <input type="number"
         :value="step.water_grams"
         x-on:input="setWater(idx, $event.target.value)"
         :disabled="step.type === 'Wait' || step.type === 'Action'"
         min="0" max="2000"
         inputmode="decimal"
         class="rounded border border-espresso-200 px-2 py-3 text-base tabular-nums">
</label>
```

**Temp (°C) field** (insert after Time (s) field, same `w-24` pattern):
```html
<label class="flex flex-col gap-1 w-24">
  <span class="text-sm font-semibold">Temp (&deg;C)</span>
  <input type="number"
         :value="step.water_temp_c || ''"
         x-on:input="setWaterTemp(idx, $event.target.value)"
         min="50" max="100"
         inputmode="decimal"
         placeholder="&mdash;"
         class="rounded border border-espresso-200 px-2 py-3 text-base tabular-nums">
</label>
```

**Per-step note** (insert after the `formatDelta` paragraph on line 78, inside `<div class="flex-1 flex flex-col gap-2">`):
```html
{# Per-step note (D-05) — hidden until user clicks "Add note" or step already has a note #}
<div>
  <button type="button"
          x-show="!step.note && !showNote[idx]"
          x-on:click="showNote[idx] = true"
          class="text-sm text-espresso-600 dark:text-cream-300 underline cursor-pointer min-h-[44px] inline-flex items-center">
    Add note
  </button>
  <textarea rows="2"
            maxlength="200"
            x-show="step.note || showNote[idx]"
            :value="step.note || ''"
            x-on:input="setNote(idx, $event.target.value)"
            placeholder="Optional step note (e.g. Hario Switch closed for immersion)"
            class="w-full rounded border border-espresso-200 px-2 py-2 text-base"></textarea>
</div>
```

Note: `showNote` must be added to `recipeStepBuilder` Alpine state as `showNote: {}` (a dict keyed by step index). The `x-show` expressions above require adding `showNote` to the component state — add `showNote: {}` to the state object in `recipe-step-builder.js`.

**Touch targets:** The up/down/remove `w-11 h-11` buttons (lines 36-46, 80-85) are retained unchanged.

---

### `app/templates/fragments/brew_prefill_fields.html` — water profile select (template, request-response)

**Analog:** self (lines 120-138 — the water_type block to replace)

**Replace** the entire `<label>` block lines 124-138 (water_type datalist input) with an Alpine-managed profile select-or-create. The Alpine component is inline (< 50 LOC per RESEARCH Pattern 2).

**New water profile select block**:
```html
{# --- Water profile (GBREW-04 / D-02): inline select-or-create, Alpine-managed ---
   Replaces water_type datalist. Alpine component is inline (< 50 LOC).
   htmx.ajax() POST goes through htmx-listeners.js CSRF injection (no manual header). #}
<div x-data="waterProfileSelect"
     data-initial-profiles='{{ water_profiles | tojson }}'
     data-initial-value='{{ values.get("water_profile_id", "") }}'>
  <label class="flex flex-col gap-1">
    <span class="text-sm font-semibold">Water profile</span>
    <select name="water_profile_id"
            x-show="!showCreate"
            x-on:change="onSelectChange($event.target.value)"
            class="w-full rounded border border-espresso-200 px-2 py-2 text-base
                   text-espresso-900 dark:text-cream-100">
      <option value="">—</option>
      <template x-for="p in profiles" :key="p.id">
        <option :value="p.id" :selected="profileId == p.id" x-text="p.name"></option>
      </template>
      <option value="__new__">Add new&hellip;</option>
    </select>
  </label>

  {# Inline create form (x-show toggle on "Add new...") #}
  <div x-show="showCreate" class="flex flex-col gap-2 mt-2">
    <input type="text"
           x-ref="newName"
           placeholder="Profile name (e.g. Third Wave Water)"
           maxlength="80"
           class="w-full rounded border border-espresso-200 px-2 py-2 text-base">
    <textarea rows="2"
              x-ref="newNotes"
              placeholder="Optional notes"
              class="w-full rounded border border-espresso-200 px-2 py-2 text-base"></textarea>
    <p x-show="createError" x-text="createError"
       class="text-sm text-red-600"></p>
    <div class="flex gap-2 items-center">
      <button type="button"
              x-on:click="saveProfile()"
              class="rounded bg-espresso-700 text-cream-50 px-4 text-sm font-semibold min-h-[44px]">
        Save profile
      </button>
      <button type="button"
              x-on:click="showCreate = false; createError = ''"
              class="text-sm text-espresso-600 underline min-h-[44px] inline-flex items-center">
        Cancel
      </button>
    </div>
  </div>
</div>
```

The `waterProfileSelect` Alpine component must be registered in a new file `app/static/js/alpine-components/water-profile-select.js` (or inline via a `<script nonce=...>` if under 50 LOC — inline is cleaner here since it's page-specific):

```javascript
// Core Alpine state for the water profile inline select-or-create
// Mirrors observedFlavorNotes._onCreated pattern from flavor-tag-input.js lines 79-98
Alpine.data('waterProfileSelect', () => ({
  profiles: [],
  profileId: null,
  showCreate: false,
  createError: '',

  init() {
    try { this.profiles = JSON.parse(this.$root.dataset.initialProfiles || '[]'); } catch(_) {}
    this.profileId = this.$root.dataset.initialValue || null;

    // HX-Trigger listener — mirrors flavor-tag-input.js lines 79-98
    this._onCreated = (evt) => {
      if (!evt || !evt.detail) return;
      const { water_profile_id, name } = evt.detail;
      if (water_profile_id == null) return;
      if (!this.profiles.some(p => p.id === water_profile_id)) {
        this.profiles.push({ id: water_profile_id, name: name });
      }
      this.profileId = water_profile_id;
      this.showCreate = false;
      this.createError = '';
    };
    document.body.addEventListener('water-profile-created', this._onCreated);
  },

  destroy() {
    document.body.removeEventListener('water-profile-created', this._onCreated);
  },

  onSelectChange(v) {
    if (v === '__new__') {
      this.showCreate = true;
      this.profileId = null;
    } else {
      this.profileId = v || null;
    }
  },

  saveProfile() {
    const name = (this.$refs.newName && this.$refs.newName.value || '').trim();
    if (!name) { this.createError = 'Profile name is required.'; return; }
    const notes = this.$refs.newNotes ? this.$refs.newNotes.value : '';
    this.createError = '';
    // htmx.ajax goes through htmx-listeners.js → X-CSRF-Token injected automatically
    // (mirrors flavor-tag-input.js createFromQuery() lines 175-180)
    htmx.ajax('POST', '/water-profiles', {
      values: { name: name, notes: notes },
      swap: 'none',
    });
  },
}));
```

This component must be loaded (nonce-tagged) before Alpine boots, following the same pattern as `guided-brew-mode.js` and `recipe-step-builder.js` in `brew_guided.html` and `recipe_form.html`. For `brew_form.html` (which includes `brew_prefill_fields.html`), add the script tag in the appropriate `head_extra` block.

---

## Shared Patterns

### Auth guard
**Source:** `app/routers/flavor_notes.py` lines 112-113 (canonical FastAPI Form 1)
**Apply to:** `app/routers/water_profiles.py` — all endpoint signatures
```python
user: User = Depends(require_user),  # noqa: B008 — FastAPI canonical Form 1.
db: Session = Depends(get_session),  # noqa: B008 — FastAPI canonical Form 1.
```

### CSRF compliance
**Source:** `app/static/js/alpine-components/flavor-tag-input.js` lines 175-180 — `htmx.ajax()` with `swap: 'none'`
**Apply to:** `app/templates/fragments/brew_prefill_fields.html` — water profile `saveProfile()` call
The global `htmx:configRequest` listener in `htmx-listeners.js` injects `X-CSRF-Token` for ALL `htmx.ajax()` calls. No manual `fetch()` is needed. The `/water-profiles` POST endpoint must strip `X-CSRF-Token` from form data before passing to Pydantic:
```python
skip = {"X-CSRF-Token"}
raw = {k: v for k, v in form_data.items() if k not in skip}
```

### HX-Trigger response pattern
**Source:** `app/routers/flavor_notes.py` lines 249-264
**Apply to:** `app/routers/water_profiles.py` POST handler success path
```python
response = templates.TemplateResponse(request=request, name="fragments/empty.html", context={})
response.headers["HX-Trigger"] = json.dumps({
    "water-profile-created": {"water_profile_id": profile.id, "name": profile.name}
})
return response
```

### Alpine body event listener lifecycle
**Source:** `app/static/js/alpine-components/flavor-tag-input.js` lines 79-103
**Apply to:** `waterProfileSelect` Alpine component `init()` / `destroy()` pattern
Register `_onCreated` in `init()`, remove in `destroy()`. De-dupe check before pushing to local array.

### Form data raw parsing
**Source:** `app/routers/flavor_notes.py` lines 195-198
**Apply to:** `app/routers/water_profiles.py`
```python
form_data = await request.form()
skip = {"X-CSRF-Token"}
raw = {k: v for k, v in form_data.items() if k not in skip}
```

### DuplicateNameError handling
**Source:** `app/routers/flavor_notes.py` lines 228-246 and `app/services/flavor_notes.py` IntegrityError catch
**Apply to:** `app/services/water_profiles.py` create function + `app/routers/water_profiles.py` POST handler

### SQLAlchemy 2.0 model pattern
**Source:** `app/models/brew_session.py` lines 66-161 / `app/models/flavor_note.py` lines 27-49
**Apply to:** `app/models/water_profile.py`
All columns use `Mapped[T]` + `mapped_column(...)`. No legacy `Column(...)` without `Mapped`. `BigInteger + Identity(always=False)` for PK. `TIMESTAMP(timezone=True)` for datetimes.

### Alembic inline-DDL convention
**Source:** `app/migrations/versions/p15_1_multi_origin.py` docstring + `p19_ai_research_predict.py` docstring
**Apply to:** `app/migrations/versions/p20_water_profiles.py`
Migration body does NOT import from `app.models`. Schema described inline with `sa.Column / sa.ForeignKey`. `from __future__ import annotations` at top. No `op.bulk_insert` — use `op.execute("""SQL""")` for data operations.

### Tailwind dark mode convention
**Source:** `app/templates/pages/brew_guided.html` throughout + `app/templates/fragments/brew_prefill_fields.html` throughout
**Apply to:** All new template code
Pattern: `bg-cream-50 dark:bg-espresso-950`, `text-espresso-700 dark:text-cream-200`, `border-espresso-200 dark:border-espresso-700`. Never `@media (prefers-color-scheme: dark)`. Class applied via `.dark` selector on `<html>`.

### Touch target enforcement
**Source:** `app/templates/pages/brew_guided.html` lines 122-127 (primary CTA) and lines 95-101 (secondary buttons)
**Apply to:** All new buttons in `brew_guided.html` and `brew_prefill_fields.html`
- Primary CTA (Start, Log, Save): `min-h-[56px]`
- Secondary / toggle: `min-h-[44px]`
- Icon-only reorder: `w-11 h-11` (retained from step builder)
- Tap-to-mark buttons are PRIMARY actions: `min-h-[56px] w-full`

### tojson single-quoted attribute
**Source:** `app/templates/pages/brew_guided.html` line 33; project memory "tojson attr quoting + live browser repro"
**Apply to:** `brew_prefill_fields.html` `data-initial-profiles` attribute
```html
data-initial-profiles='{{ water_profiles | tojson }}'
data-steps='{{ recipe.steps | tojson }}'
```
ALWAYS single-quoted. `|tojson` escapes single quotes within values.

---

## No Analog Found

None. All 13 files have close or exact analogs in the codebase.

---

## Metadata

**Analog search scope:** `app/models/`, `app/schemas/`, `app/routers/`, `app/services/`, `app/migrations/versions/`, `app/templates/pages/`, `app/templates/fragments/`, `app/static/js/alpine-components/`
**Files read:** 17 source files
**Pattern extraction date:** 2026-05-29
