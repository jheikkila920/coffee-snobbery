# Phase 7: AI Services - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-20
**Phase:** 7-AI Services
**Areas discussed:** Home AI card UX, AI voice & tone, Equipment-rec delivery, Paste-rank + wishlist

---

## Home AI card UX

### Placement

| Option | Description | Selected |
|--------|-------------|----------|
| Top hero | Above the analytics cards; the recommendation is the headline. | ✓ |
| Below analytics | Renders beneath recent brews + aggregate cards as a conclusion. | |
| Under Sweet Spots | Grouped mid-page with the sweet-spots prose. | |

**User's choice:** Top hero
**Notes:** Matches the core value ("what to buy next, grounded in your log"); analytics support the pick.

### Pick count

| Option | Description | Selected |
|--------|-------------|----------|
| Single hero pick | One confident "buy this next"; lowest web-search cost; clearest CTA. | ✓ |
| Up to 3 ranked | A ranked shortlist on the home card; more cost + busier at 375px. | |

**User's choice:** Single hero pick
**Notes:** Paste-and-rank still shows top 3 separately.

---

## AI voice & tone

### Voice

| Option | Description | Selected |
|--------|-------------|----------|
| Confident expert, lightly wry | House style: knows its stuff, lightly opinionated, never performative. | ✓ |
| Full snob persona | Performative coffee-snob voice throughout; gimmick risk. | |
| Neutral / factual | Plain reasoning; tone only in empty states + headings. | |

**User's choice:** Confident expert, lightly wry
**Notes:** Matches PROJECT's "snobbery tone without becoming gimmicky."

### Length

| Option | Description | Selected |
|--------|-------------|----------|
| Tight (1-2 sentences) | Fast to read at the kettle; lower output tokens. | ✓ |
| Short paragraph (3-5 sentences) | More room to explain; more tokens + scrolling. | |

**User's choice:** Tight (1-2 sentences)

---

## Equipment-rec delivery

| Option | Description | Selected |
|--------|-------------|----------|
| On-demand in Config | "Analyze my setup" button near equipment mgmt; generate-on-click. | |
| On-demand on home | Same generate-on-click behavior, entry point on the home page. | ✓ |
| Bundled nightly on home | Always-visible card regenerated nightly with the coffee rec. | |

**User's choice:** On-demand on home
**Notes:** Profile-only (cheap) but equipment changes rarely and "no changes recommended" is common — on-demand avoids permanent clutter and a wasted nightly LLM call, while keeping the entry point discoverable next to the coffee pick.

---

## Paste-rank + wishlist

### Paste-and-rank location

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated page | "Rank these for me" page; keeps home focused on the cached pick. | ✓ |
| Home section | Inline expandable paste box on the home page. | |
| Config area | Lives under Config as a utility. | |

**User's choice:** Dedicated page

### Paste-and-rank input

| Option | Description | Selected |
|--------|-------------|----------|
| Freeform text | Paste descriptions; no fetching. | |
| URLs (app fetches) | Paste product URLs; app fetches + extracts. | |
| Both | Accept text or URLs in one box, detect which. | ✓ |

**User's choice:** Both
**Notes:** URL path reuses/extends the AI-05 ranged-GET machinery for extraction (separate from the live-rec web search). Flagged for research.

### Wishlist scope

| Option | Description | Selected |
|--------|-------------|----------|
| Add + minimal view | Add hook plus a list-saved / mark-purchased / remove view. | ✓ |
| Add hook only | Write to `wishlist_entries` only; defer any view. | |

**User's choice:** Add + minimal view
**Notes:** Closes the loop so saves aren't write-only — the reason the table exists. Full wishlist CRUD deferred.

---

## Claude's Discretion

- Coffee-rec card composition (single composite card with name/roaster/origin/process/roast, why-prose, buy link + verify state, add-to-wishlist, recipe suggestion, alt-brewer callout when it fires).
- URL-verify UX timing (recommend render-then-verify-via-poll vs block-on-verify).
- `ai_recommendations` row shape for the cached coffee + sweet-spots bundle (separate `sweet_spots` row vs embedded JSON; regenerated/expired together either way).
- Route/module layout (`ai_service.py` + `wishlist.py` + `ai.py` router vs extending `home.py`).
- `regenerate()` entry-point signature (must be reusable by Phase 8's scheduler).
- Default model IDs (read from `api_credentials.model_name`; documented, not hardcoded).
- Paste-rank URL extraction depth.
- `ai.*` event taxonomy in `app/events.py`.

## Deferred Ideas

- 3-pick home shortlist (rejected: cost + 375px clutter).
- Full snob persona prose (rejected: gimmick risk).
- Bundled nightly equipment-rec card (rejected: cost + clutter).
- Full wishlist CRUD beyond the minimal view.
- Per-user/month AI cost ceiling (v2).
- SSE streaming (v1.1; v1 uses polling).
- Auto-surfacing equipment rec on weak-link detection (on-demand only).
