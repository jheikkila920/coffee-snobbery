# Phase 10: Global Search - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-21
**Phase:** 10-Global Search
**Areas discussed:** Search placement, Result content, Ordering & limits, Link targets, Archived rows

---

## Search placement

### Mount point
| Option | Description | Selected |
|--------|-------------|----------|
| Minimal header in base.html | Thin persistent header in base.html holding just the search component; Phase 11 grows it into the full nav. Mirrors Phase 9 D-03. | ✓ |
| Per-page header injection | Drop the component into each page's own header block; duplicated across ~15 pages. | |
| Component only, defer mount | Build endpoint + component, mount on a single page; Phase 11 wires into nav. Not persistent. | |

### Desktop UI
| Option | Description | Selected |
|--------|-------------|----------|
| Floating dropdown | Overlay panel anchored under the input, grouped, dismiss on outside-click/Esc. | ✓ |
| Inline results region | Results render below the bar, pushing page content down. | |

### Mobile sheet
| Option | Description | Selected |
|--------|-------------|----------|
| X + Esc + tap-scrim | Tap result navigates and closes; X/Esc/backdrop dismiss; no history entry. | ✓ |
| Also wire browser Back | pushState so the back gesture dismisses the sheet; more JS. | |

### Results page
| Option | Description | Selected |
|--------|-------------|----------|
| Live results only | Dropdown/sheet is the whole feature; Enter does nothing special. | ✓ |
| Add a full /search page | Enter / 'see all' opens a paginated full-results page. | |

**User's choice:** Minimal persistent header in base.html; floating dropdown (desktop); full-screen sheet closed via X/Esc/scrim (mobile); live results only.
**Notes:** Success criterion #4 locks the inline model, so the only open question was the mount point given base.html has no nav. Resolved as the Phase 9 D-03 analog.

---

## Result content

### Row detail
| Option | Description | Selected |
|--------|-------------|----------|
| Name + key context | Coffee→name+roaster+origin; equipment→name+type; recipe→name+desc; roaster/flavor note→name; brew note→coffee+date+snippet. | ✓ |
| Name only | Just the entity name per row. Most compact; risks ambiguity. | |
| Name + full metadata | Rich multi-field rows; heavier at 375px. | |

### Highlight
| Option | Description | Selected |
|--------|-------------|----------|
| Highlight the match | Mark matched text (safe server markup, autoescape on, no \|safe). | ✓ |
| No highlight | Plain rows. | |

### Brew notes
| Option | Description | Selected |
|--------|-------------|----------|
| Snippet → session edit | coffee+date+snippet; links to /brew/{id}/edit. | ✓ |
| Snippet → sessions list | Same, but links to the filtered sessions list. | |

**User's choice:** Name + key context; highlight the match; brew note → snippet → session edit.
**Notes:** Highlight must avoid `|safe` — flagged as the phase's one correctness trap.

---

## Ordering & limits

### Group order
| Option | Description | Selected |
|--------|-------------|----------|
| Fixed: catalog → notes | Coffees, Roasters, Recipes, Equipment, Flavor Notes, Your Brew Notes — matches success #1. | ✓ |
| By relevance/count | Strongest/most matches float up; layout shifts while typing. | |

### Within group
| Option | Description | Selected |
|--------|-------------|----------|
| Relevance (best match first) | Prefix/exact above mid-string (trigram similarity or ts_rank). | ✓ |
| Alphabetical | Simple but buries near-exact matches. | |

### Per-group cap
| Option | Description | Selected |
|--------|-------------|----------|
| Cap ~5 + 'refine' hint | Top ~5 per group; non-clickable '+N more — keep typing' line. | ✓ |
| Cap ~5, no overflow hint | Top ~5, silently omit the rest. | |
| No cap | Show every match; can flood the dropdown. | |

### Empty states
| Option | Description | Selected |
|--------|-------------|----------|
| Closed until 2 chars; tasteful 'no results' | Closed below 2 chars; snobbery-tone empty line; no stored state. | ✓ |
| Show hint / recent searches first | Pre-search hint or recent searches; needs new per-user state. | |

**User's choice:** Fixed group order; relevance within group; cap ~5 + '+N more' hint; closed below 2 chars + snobbery-tone no-results.

---

## Link targets

### Coffee target
| Option | Description | Selected |
|--------|-------------|----------|
| Coffee detail page | /coffees/{id} — richer read view; edit one tap away. | ✓ |
| Coffee edit form | /coffees/{id}/edit directly. | |

### Catalog target (roasters/equipment/recipes/flavor notes)
| Option | Description | Selected |
|--------|-------------|----------|
| Their edit page | /{entity}/{id}/edit — the only stable per-entity URL. | ✓ |
| Their list page (anchored) | Open the list scrolled/highlighted to the row. | |

**User's choice:** Coffee → detail page; other catalog entities → their edit page.

---

## Archived rows

| Option | Description | Selected |
|--------|-------------|----------|
| Exclude archived | Search only the active catalog; simplest WHERE clause. | |
| Include with a badge | Show archived coffees/equipment marked with an 'Archived' badge. | ✓ |

**User's choice:** Include archived rows with an 'Archived' badge.
**Notes:** Surfaced by Claude as an extra gray area; John opted in to re-finding discontinued beans.

---

## Claude's Discretion

- FTS vs `pg_trgm` — deferred to plan-phase research (prototype both, pick one); fixes the relevance mechanism + index DDL.
- Cross-entity query shape (six queries vs one UNION ALL) — planner's call, keep p95 < 100ms.
- Enter / arrow-key behavior — planner's call; keep minimal.
- `aria-live` results region — planner adds per accessibility.
- Brew-note snippet length — planner's call.

## Deferred Ideas

- Full global nav + sign-out + brand wordmark — Phase 11.
- Dedicated full results page + pagination — live-only in v1.
- Recent searches / pre-search suggestions — needs per-user state.
- Expanding coffee search to origin/process/roast-level fields — beyond SEARCH-01's name fields.
- Keyboard arrow-navigation through results — nice-to-have.
- Searching recipe step text — only name + description in scope.
