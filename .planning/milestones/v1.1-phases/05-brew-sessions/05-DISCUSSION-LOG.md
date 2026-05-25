# Phase 5: Brew Sessions - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-19
**Phase:** 5-Brew Sessions
**Areas discussed:** Form surface & controls, Prefill & smart defaults, Flavor-note tag input, CSV import & export

---

## Form surface & controls

### Where the add/edit form lives
| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated page (/brew/new) | Real routes + Brew-again deep-link; cleaner for long form, sticky save, draft autosave, future Guided Brew handoff | ✓ |
| Inline-expand on sessions list | Matches Phase 4 D-02 catalog pattern; awkward at 375px for a long form | |

### Refractometer field placement
| Option | Description | Selected |
|--------|-------------|----------|
| Collapsed "Advanced" disclosure | Closed by default; keeps <30s path clean; draft remembers open state | ✓ |
| Always inline | Simplest; clutters every fast log | |

### Rating tap interaction
| Option | Description | Selected |
|--------|-------------|----------|
| Repeated-tap cycles the star | Whole 56px star stays target (honors 44px); up to 4 taps to max | |
| Tap-zones (quarters) | One-tap fractions; ~14px quarter zones, under 44px | |
| Half-steps only (tap-zones) | Whole+half via ~28px left/right zones | ✓ |

**User's choice:** Half-steps only (tap-zones).
**Notes:** Reconciled by Claude — DB/Pydantic column stays `multiple_of=0.25` (forward-compat + CSV quarter values validate); UI emits 0.5 only. ~28px zones are a recorded, accepted deviation from the strict 44px tap-target rule at household scale.

---

## Prefill & smart defaults

### "Last session" meaning
| Option | Description | Selected |
|--------|-------------|----------|
| Hybrid: global last, then per-coffee | Open from global most-recent; re-prefill per-coffee on coffee change | ✓ |
| Global last session only | Always global last; wrong dose/grind when switching beans | |
| Per-selected-coffee only | Prefill only after coffee pick; opens emptier | |

### Recipe vs last-session conflict
| Option | Description | Selected |
|--------|-------------|----------|
| Recipe wins on select | Recipe overwrites dose/water/temp/grind; last-session fills rest; all editable | ✓ |
| Last session always wins | Recipe only fills blanks; undercuts recipes | |

### Bag handling on coffee select
| Option | Description | Selected |
|--------|-------------|----------|
| Auto-select newest open bag | Default to newest opened/unfinished bag; editable/clearable; feeds HOME-04 freshness | ✓ |
| Leave blank, user picks | Explicit but slower; degrades freshness analytics | |

### water_type input
| Option | Description | Selected |
|--------|-------------|----------|
| Dropdown of common types + Other | Native select + free-text escape; consistent values | ✓ |
| Free text only | Flexible but inconsistent | |

---

## Flavor-note tag input

### New note on commit
| Option | Description | Selected |
|--------|-------------|----------|
| Auto-create as category 'other' | Instant; recategorize later on catalog page; "new" chip badge | ✓ |
| Quick inline category picker | More correct; per-note interruption | |
| Pick-existing-only here | Cleanest vocabulary; contradicts BREW-03 | |

### Duplicate guard
| Option | Description | Selected |
|--------|-------------|----------|
| Auto-create only on exact no-match | Autocomplete-first; link existing on citext match; create only on no-match | ✓ |
| Require explicit "+ Create" tap | Zero accidental creates; one extra tap | |

### Advertised notes as quick-add chips
| Option | Description | Selected |
|--------|-------------|----------|
| Yes, show advertised as quick-add | One-tap chips from coffees.advertised_flavor_note_ids; aids cold-start gate | ✓ |
| No, blank tag input only | Simpler; misses speed win | |

---

## CSV import & export

### Coffee match key
| Option | Description | Selected |
|--------|-------------|----------|
| Name, roaster-qualified when present | citext name; +roaster when column present; refuse unresolved | ✓ |
| Name only | Ambiguous across roasters sharing a name | |

### Bag matching strictness
| Option | Description | Selected |
|--------|-------------|----------|
| Bag optional; refuse only named-but-unmatched | Link if resolves (coffee+roast_date); null if unnamed | ✓ |
| Bag required | Strict integrity; rejects much legacy history | |

### Re-import dedup
| Option | Description | Selected |
|--------|-------------|----------|
| Skip duplicates idempotently | Key (user_id, coffee_id, brewed_at); report skipped | ✓ |
| Insert everything | Re-import doubles the log | |

### Export shape
| Option | Description | Selected |
|--------|-------------|----------|
| Name-based, round-trip-safe | Resolve IDs to names + computed columns; re-imports cleanly | ✓ |
| ID-based round-trip | Exact but unreadable/brittle | |
| Rich read-only (no round-trip) | Best spreadsheet; loses round-trip | |

---

## Claude's Discretion
- `brewed_at` default (now) + editability for back-dating; tz-aware UTC storage, render in `APP_TIMEZONE`.
- Server draft store model (one active draft per user; autosave on `/brew/new` only; edit is a normal save); localStorage-primary reconciliation.
- `equipment.usage_count` increment mechanism (service-layer recommended over trigger).
- Sessions-list default sort (newest first).
- Edit-session form shows actual values, not ghost prefill.
- Exact Beanconqueror column-to-field mapping (plan-phase research).
- Filter widgets styling; whether live ratio readout also shows EY.

## Deferred Ideas
- Guided Brew Mode + wake lock (BREW-12/13) → Phase 11.
- Inline recategorization of auto-created flavor notes.
- Bag-required strict import mode.
- CSV import of catalog entities (import is sessions-only by design).
- Hard UNIQUE on (user_id, coffee_id, brewed_at) — deferred to import-time dedup.
- One-tap "repeat exact last brew".
- Standalone /bags page (carried from Phase 4).
