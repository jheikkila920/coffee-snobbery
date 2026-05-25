---
slug: guided-brew-does-nothing
status: resolved
trigger: |
  Clicking "Start guided brew" doesn't do anything. Because I cannot open guided brew, I am not sure about the following: when the guided brew is done, will it give you a button to log the session and then have that prefill the fields?
created: 2026-05-24
updated: 2026-05-24
---

# Debug: Guided brew "Start guided brew" does nothing

## Symptoms

- **Expected:** Tapping "Start guided brew" navigates to `/brew/guided?recipe_id=N` and shows the guided-brew start screen.
- **Actual:** Absolutely nothing happens on tap — no navigation, screen does not change.
- **Scope:** Fails in BOTH the installed iOS PWA AND a regular browser tab. (Rules out the service-worker stale-cache hypothesis — no SW involved in a fresh browser tab.)
- **Timeline:** Never worked. Has never opened since the feature was available. (Consistent with a code/template bug present since the feature shipped, not a regression.)
- **Error messages:** None reported (DevTools console not yet inspected).
- **Reproduction:** Recipes page → tap "Start guided brew" on a recipe row/card.

## Evidence (codebase, pre-gathered)

- Button is a plain `<a href="/brew/guided?recipe_id={{ recipe.id }}">` in `app/templates/fragments/recipe_row.html` (mobile card ~lines 49-52, desktop row ~lines 100-103).
- Earlier scan note: "It only appears when the recipe has steps (disabled state when no steps)." — STRONG LEAD. A plain anchor cannot do "nothing" on click unless it is not a real/enabled anchor (no href, `pointer-events:none`, `aria-disabled`, rendered as `<span>`/`<button disabled>`, or intercepted by an overlay/preventDefault).
- Route exists and is registered: `app/routers/brew_guided.py` (lines 39-76), registered before `brew_router` in `app/main.py` (lines 266-268).
- Page template `app/templates/pages/brew_guided.html` and Alpine component `app/static/js/alpine-components/guided-brew-mode.js` present.
- Tests `tests/routers/test_gbm.py` pass (route-level only — they do NOT exercise the template's enabled/disabled rendering of the link).
- Post-completion behavior (answers the user's secondary question): completing a guided brew DOES redirect to `/brew/new` and prefills coffee, recipe, dose, water, temp, grind, equipment, and measured brew_time (`guided-brew-mode.js:326-334`, `app/routers/brew.py:645-663`).

## Eliminated

- hypothesis: Stale service-worker cache serving an old build.
  reason: Bug also reproduces in a fresh regular browser tab (no service worker), and the feature never worked. SW cache cannot explain either fact.
- hypothesis: Route conflict (/brew/guided captured by /brew/{session_id}).
  reason: brew_guided_router is registered before brew_router in main.py (line 244). No GET /{session_id} route exists in brew.py — only /{session_id}/edit (GET) and /{session_id} (POST). No conflict.
- hypothesis: HTMX or Alpine intercepting the link click.
  reason: No hx-boost is enabled. No Alpine x-on:click on any parent element of the recipe card. htmx-listeners.js only handles htmx:configRequest and htmx:afterSettle — neither intercepts a plain anchor click.
- hypothesis: Service worker returning stale content for /brew/guided.
  reason: sw.js uses network-first for all non-static GETs. /brew/guided is not in the app shell and is not cached — it always goes to the network.

## Resolution

- root_cause: Recipes with no steps (`steps = []`) cause `recipe_row.html` to render "Start guided brew" as an inert `<span>` (not an `<a href>`). The span has no click handler and does nothing on tap. The `title="Recipe has no steps."` tooltip is invisible on iOS touch. The enabled (dark brown) and disabled (light gray border) states look superficially similar at a glance. User's VPS recipes have no steps — so every "Start guided brew" control was a dead span.
- fix: Changed the no-steps disabled branch in `app/templates/fragments/recipe_row.html` (both card and desktop row). Instead of a dead `<span>`, it now renders `<a href="/recipes/{id}/edit">` with label "Start guided brew (add steps)" — navigates to the recipe editor on tap, which is the actionable next step. aria-label explains the intent.
- fix_status: applied
- files_changed:
  - app/templates/fragments/recipe_row.html (lines 53-57 card, lines 104-108 desktop row)
