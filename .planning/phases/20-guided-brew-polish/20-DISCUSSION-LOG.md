# Phase 20: Guided Brew Polish - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-29
**Phase:** 20-guided-brew-polish
**Areas discussed:** Water profiles, Step model & types, Phase coaching feel, First-drip/bloom capture

---

## Water profiles (GBREW-04)

### Profile data
| Option | Description | Selected |
|--------|-------------|----------|
| Name + optional notes | Name plus freetext note; KISS for a polish milestone | ✓ |
| Structured minerals | Ca/Mg/bicarbonate/TDS numbers; power-user, bigger form | |
| Name only | Just a label | |

### Management
| Option | Description | Selected |
|--------|-------------|----------|
| Inline select-or-create, shared | Type-to-add on brew form like flavor notes; shared household catalog | ✓ |
| Dedicated catalog page | Managed list page like coffees/recipes | |
| Admin-only | Only admin curates the list | |

### Migration
| Option | Description | Selected |
|--------|-------------|----------|
| Auto-seed + link | Profile per distinct freetext value; link historical sessions | ✓ |
| Leave freetext as-is | Old sessions keep strings; only new use profiles | |
| You decide | Pick cleanest approach in planning | |

**Notes:** Matches the shared-catalog invariant; preserves brew history.

---

## Step model & types (GBREW-06)

### Step types
| Option | Description | Selected |
|--------|-------------|----------|
| Preset types + label | Fixed list Bloom/Pour/Wait/Action plus freetext label; drives coaching, enables water-less steps | ✓ |
| Label + no-water flag | Freetext label only + a "timed action, no water" checkbox | |
| You decide | Pick model in planning | |

### Step notes
| Option | Description | Selected |
|--------|-------------|----------|
| Optional note per step | Freetext note, inheritable into Guided Brew as a coached cue | ✓ |
| No per-step notes | Label only | |

### Step fields (beyond type/label/water/time/note)
| Option | Description | Selected |
|--------|-------------|----------|
| No, keep it minimal | Five fields cover everything; extras go in the note | |
| Per-step water temp | Optional temperature per step | ✓ |
| Per-step agitation | Structured swirl/stir cue per step | |

**Notes:** Resulting step shape `{type, label, water_grams?, water_temp_c?, time_seconds, note?}`. Water made optional for Wait/Action (GBREW-06).

---

## Phase coaching feel (GBREW-02)

### Cues (multi-select)
| Option | Description | Selected |
|--------|-------------|----------|
| Audio tone | Already implemented; keep | ✓ |
| Vibration | Already implemented; keep | ✓ |
| Visual change | Already implemented; keep | ✓ |
| Spoken voice (TTS) | Speech-synthesis reads the step aloud; new work | |

### Coach text
| Option | Description | Selected |
|--------|-------------|----------|
| Auto-compose + note | Coached line from type + target with per-step note beneath | ✓ |
| Label + note only | Freetext label and note, no auto targets | |
| Note only | Just the per-step note | |

### Pre-cue
| Option | Description | Selected |
|--------|-------------|----------|
| Short pre-cue countdown | "Get ready" 3-2-1 before each transition | ✓ |
| Signal at the moment only | Fire cue exactly at step change | |

### On-screen
| Option | Description | Selected |
|--------|-------------|----------|
| Full coach view | Current step + target + countdown + cumulative water + elapsed + next preview | ✓ |
| Minimal | Current step + time remaining only | |

**Notes:** TTS deferred. "Coach feel" via pre-cue + full view + auto-composed line.

---

## First-drip / bloom capture (GBREW-03)

### Capture
| Option | Description | Selected |
|--------|-------------|----------|
| Live tap + editable | Tap-to-mark in Guided Brew, editable on any session form | ✓ |
| Live tap only | Only inside Guided Brew | |
| Manual entry only | Numeric fields on form, no live tap | |

### Bloom time
| Option | Description | Selected |
|--------|-------------|----------|
| Auto-derive from bloom step | Use actual elapsed on Bloom-type step; editable | ✓ |
| Explicit tap | User marks bloom start/end | |

### First-drip reference
| Option | Description | Selected |
|--------|-------------|----------|
| From brew start | Seconds from timer start; conventional reading | ✓ |
| From first pour / bloom end | Seconds from main pour | |
| You decide | Pick in planning | |

**Notes:** GBREW-03 requires availability on "any brew session," so manual fields exist on non-guided sessions too.

---

## Claude's Discretion

- JSONB step-schema field names + Pydantic bounds.
- Water-profile migration collision/blank-value handling.
- GBREW-01 timer recovery mechanism (behavior locked as wall-clock-truth; mechanism is research's call).
- Optional water-profile edit affordance beyond inline-create.

## Deferred Ideas

- Structured water mineralogy (Ca/Mg/bicarbonate/TDS) + water-vs-taste analytics.
- Spoken voice / TTS coaching.
- Per-step agitation as a structured field (lives in the note for now).

## Not asked (and why)

- **GBREW-01** (timer survives sleep): correctness mechanism, not a vision choice — locked as wall-clock-truth in CONTEXT D-15, mechanism flagged for research.
- **GBREW-05** (375px audit): reuses the established mobile pattern + Phase 15 safe-area fix — verification pass, no new decisions (CONTEXT D-16).
