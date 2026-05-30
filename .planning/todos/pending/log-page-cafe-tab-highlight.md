---
type: bug
severity: medium
created: 2026-05-29
source: john-uat-during-phase-20
area: frontend / log-page
---

# Log page: "Cafe tastings" tab doesn't highlight when selected

## Symptom (reported by John)
On the Log page (`/brew`), clicking "Cafe tastings" loads the cafe list but the
active highlight stays on "Sessions" — the Cafe tab never shows as active.

## Root cause (confirmed)
The tab bar in `app/templates/pages/sessions.html:159-175` is rendered OUTSIDE the
`#session-list` element. Both tab anchors use `hx-get="/brew?tab=..."` +
`hx-target="#session-list"`, so an HTMX tab switch swaps only the list fragment
(`fragments/cafe_log_list.html` / `session_list.html`) and never re-renders the tab
bar. The active classes (`border-b-2 border-espresso-700` / `border-amber-500` +
`aria-current`) are computed server-side from `active_tab` at initial page render and
are never updated by the swap → highlight stuck on Sessions.

## Fix plan
- Extract the tab bar into a small partial (e.g. `fragments/log_tabs.html`)
  parameterized by `active_tab`.
- In the brew router's HX-Request list-fragment responses (both `?tab=brew` and
  `?tab=cafe`), include the tab-bar partial with `hx-swap-oob="true"` so the active
  state updates alongside the `#session-list` swap. (Alternative: wrap tabs+list in a
  single swap target — but OOB is less disruptive to the existing filter-bar wiring,
  which also targets `#session-list`.)
- Verify in a real browser (OOB swap + strict nonce-CSP; harness can hide HTMX/CSP
  issues — memory: tojson-attr-quoting-and-live-browser-repro). Confirm aria-current
  moves and the underline color flips (espresso for Sessions, amber for Cafe).
- Router test: assert the `?tab=cafe` HX-Request response contains the OOB tab bar
  with the cafe tab marked active.

## Notes
- Pre-existing (CAFE-03 / Phase 16), not Phase 20.
- Related but SEPARATE: John also asked for a no-data empty-state hint on the cafe
  tab. That is currently blank BY LOCKED DECISION D-08 (Phase 16, at the user's own
  request). Do NOT add hint copy without re-opening D-08. If the user confirms the
  reversal, update 16-CONTEXT.md D-08 and add the `{% else %}` copy in
  `fragments/cafe_log_list.html` (the branch is already stubbed with a LOCKED note).
