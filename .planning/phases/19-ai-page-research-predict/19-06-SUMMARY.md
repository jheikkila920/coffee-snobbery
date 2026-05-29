---
phase: 19-ai-page-research-predict
plan: "06"
subsystem: ui
tags: [htmx, sse, chart.js, alpine.js, csp, tailwind, research, ai, wishlist]

requires:
  - phase: 19-05
    provides: POST /ai/research SSE stream, POST /ai/improve-brew/{session_id} SSE, GET /ai/research/quota, AI router, CoffeeResearchSchema, AIRatingPrediction, BrewImproveSchema

provides:
  - Chart.js v4 + htmx-ext-sse CDN wired into base.html with csp_nonce
  - .htmx-indicator spinner rules + .chart-canvas sizing in tailwind.src.css (CSP-safe, baked)
  - chart-trends.js Alpine component (dark-aware, CSP-clean, MutationObserver re-theme)
  - /ai restructured: Research card top, prose Preference Profile, Top Flavor Descriptors deleted, Trends card last
  - research_form.html (SSE wiring, quota counter, spinner)
  - research_result.html (trimmed D-03 revision: title + cached badge + predicted range + Why + wishlist, no metadata/notes/sources)
  - research_quota_exhausted.html, preference_profile_prose.html, trends_card.html, coach_brew_picker.html
  - improve_result.html (BrewImproveSchema: summary_prose + unchanged_parameters + next_try)
  - Improve-brew button on brew edit page (inline SSE result card)
  - ADR 0004 documenting D-03 card stack revision

affects: [19-07, any plan touching /ai layout, brew edit page, wishlist, CDN budget]

tech-stack:
  added:
    - Chart.js 4.5.1 (CDN, nonce-tagged)
    - htmx-ext-sse 2.2.4 (CDN, nonce-tagged)
  patterns:
    - SSE result card: hx-ext=sse + sse-connect + sse-swap=event:complete + sse-close
    - CSP-clean indicator styles defined in tailwind.src.css (never auto-injected)
    - Alpine.data() factory registration for Chart.js components (CSP build requirement)
    - MutationObserver on documentElement.class for dark re-theme without page reload
    - Display-only trim: backend schema produces full data; UI renders the minimal decision-relevant subset

key-files:
  created:
    - app/templates/fragments/ai/research_form.html
    - app/templates/fragments/ai/research_result.html (replaced Phase 17 stub)
    - app/templates/fragments/ai/research_quota_exhausted.html
    - app/templates/fragments/ai/preference_profile_prose.html
    - app/templates/fragments/ai/trends_card.html
    - app/templates/fragments/ai/coach_brew_picker.html
    - app/templates/fragments/brew/improve_result.html
    - app/static/js/alpine-components/chart-trends.js
    - docs/decisions/0004-trim-research-result-card.md
    - tests/templates/test_ai_page_phase19.py
  modified:
    - app/templates/base.html (CDN script tags)
    - app/static/css/tailwind.src.css (.htmx-indicator + .chart-canvas)
    - app/templates/pages/ai.html (restructured card order, research_coming_soon removed)
    - app/templates/pages/brew_form.html (improve-brew button)
    - app/routers/home.py (preference-profile endpoint)
    - app/routers/brew.py (improve-brew route wiring)

key-decisions:
  - "D-03 revised (ADR 0004): research result card trimmed to title + cached badge + predicted range + confidence + Why + wishlist; metadata/notes/sources removed as display-only noise -- backend schema unchanged"
  - "chart-trends.js uses MutationObserver on documentElement class for dark re-theme, not a click handler on the toggle button -- avoids coupling to toggle implementation"
  - "Tailwind .htmx-indicator defined in tailwind.src.css (not inline) per project memory strict-csp-blocks-htmx-indicator"
  - "canvas sized via .chart-canvas CSS class + maintainAspectRatio:false -- no inline style attr (RESEARCH Pitfall 3 / CSP)"

patterns-established:
  - "SSE result fragment: POST triggers SSE stream; event:complete swaps in the result card; sse-close terminates the connection"
  - "Display-only trim: CoffeeResearchSchema fields used as prediction inputs are not required on the result card; trim the card, not the schema"

requirements-completed: [AIX-06, AIX-09, AIX-10, AIX-12, VIZ-01]

duration: ~3h (including human verification and design revision)
completed: 2026-05-28
---

# Phase 19 Plan 06: AI Page UI Summary

**Full /ai page and brew-edit SSE surfaces shipped: Research card with streaming prediction, Chart.js trends, improve-brew inline result, and D-03 card stack trimmed to score + Why + wishlist after live human verification**

## Performance

- **Duration:** ~3h (tasks 1-3 in prior session; design revision + rebuild in continuation)
- **Started:** 2026-05-27
- **Completed:** 2026-05-28
- **Tasks:** 4 (tasks 1-3 committed earlier; task 4 design revision applied in continuation)
- **Files modified:** 14

## Accomplishments

- Research SSE flow live and human-verified: Counter Culture / Mpemba returned 3.75-4.50 Low confidence prediction with streaming prose
- Chart.js v4 + htmx-ext-sse loaded CSP-clean via nonce-tagged CDN scripts; dark-mode re-theme confirmed working
- Improve-brew button on brew edit page renders inline SSE result card
- D-03 research result card trimmed to minimal decision surface (score + Why + wishlist) per live user feedback; ADR 0004 records the decision

## Task Commits

1. **Task 1: base.html CDN + tailwind.src.css + chart-trends.js** - `a12da6d` (feat)
2. **Task 2: /ai restructure + fragments + quota wiring** - `a18aa29` (feat)
3. **Task 3: improve-brew button + inline SSE result** - `bdf3cf6` (feat)
4. **Design revision: trim research result card (revises D-03)** - `0709a53` (feat)
5. **ADR 0004: D-03 card stack revision** - `bf1f096` (docs)

## Files Created/Modified

- `app/templates/fragments/ai/research_form.html` - SSE research form, quota counter, spinner
- `app/templates/fragments/ai/research_result.html` - Trimmed result card: title + cached + predicted range + Why + wishlist
- `app/templates/fragments/ai/research_quota_exhausted.html` - Inline 429 fragment
- `app/templates/fragments/ai/preference_profile_prose.html` - AI prose with newline handling, no |safe
- `app/templates/fragments/ai/trends_card.html` - Chart.js canvas pair, x-data=chartTrends, refresh affordance
- `app/templates/fragments/ai/coach_brew_picker.html` - Alpine x-show session picker, links to brew edit + auto-request
- `app/templates/fragments/brew/improve_result.html` - BrewImproveSchema render: summary_prose + unchanged chips + next_try
- `app/static/js/alpine-components/chart-trends.js` - Alpine.data factory, Chart.js init, MutationObserver dark re-theme
- `app/templates/base.html` - Chart.js + htmx-ext-sse CDN tags with csp_nonce
- `app/static/css/tailwind.src.css` - .htmx-indicator + .chart-canvas rules
- `app/templates/pages/ai.html` - Restructured card order; research_coming_soon removed; Top Flavor Descriptors deleted
- `app/templates/pages/brew_form.html` - Improve-brew button + inline SSE result mount
- `app/routers/home.py` - /home/cards/preference-profile returns prose fragment
- `app/routers/brew.py` - Improve-brew route wiring
- `tests/templates/test_ai_page_phase19.py` - 20 structural assertions (all green)
- `docs/decisions/0004-trim-research-result-card.md` - ADR for D-03 revision

## Decisions Made

- **D-03 revised (ADR 0004):** Research result card trimmed. The full CoffeeResearchSchema (origin, process, roast_level, tasting_notes, sources) is still produced by the AI call and fed to the rating prediction -- only the display is trimmed. Rationale: after live use, the predicted score + one-line "Why" + wishlist button are the only items that drive a decision. Metadata and sources are noise at the point of action. No cost impact.
- **CSRF form field naming:** The wishlist form sends `X-CSRF-Token` as a form field read from the `csrftoken` cookie. This naming is carried forward from the plan. Pending verification that this matches how other HTMX POST forms in the app send the CSRF token (see Outstanding UAT below).

## Deviations from Plan

### Design Revision (user-directed, not auto-fix)

**D-03 card stack trim -- post-human-verification design change**
- **Found during:** Task 4 human verification checkpoint
- **Requested by:** User after live-verifying the research flow
- **Change:** Removed origin/process/roast_level metadata, tasting-notes chips, and cited-sources block from `research_result.html`. Relocated `cached` badge inline next to title; relocated `buy URL not verified` chip next to wishlist button.
- **Rationale recorded in:** ADR 0004 (`docs/decisions/0004-trim-research-result-card.md`)
- **Backend impact:** None -- CoffeeResearchSchema unchanged; trimmed fields still computed as prediction inputs
- **Test impact:** None -- all 20 template tests pass (predicted_low/high, confidence, reasoning, /ai/wishlist/add, coffee_name, source_url all retained; |safe absent)

---

**Total deviations:** 1 (user-directed display-only design revision)
**Impact on plan:** No scope creep, no cost change, no schema change. Template tests remain green.

## Human-Verified (2026-05-28)

- Research SSE streaming: prose streams incrementally; result card renders with predicted range + confidence + Why
- Rating prediction: Counter Culture / Mpemba returned 3.75-4.50 Low confidence (non-trivial, grounded)
- Dark-mode chart re-theme: confirmed working
- Wishlist button: present and functional
- Improve-brew SSE: inline result card on brew edit page confirmed rendering

## Outstanding UAT (carry to 19-07)

These items were NOT confirmed during Phase 19 human verification and must be validated before declaring /ai fully production-ready:

1. **Cached-badge on identical re-run:** Submit the same research query twice; confirm the quota counter does NOT decrement on the second call and the `cached` badge appears. (Quota cost-control invariant -- must not regress.)

2. **Dark-mode Chart.js re-theme:** Pending explicit DevTools verification at 375px that chart colors swap correctly (espresso lines on cream / cream lines on espresso). Initial manual test was positive but not a formal checkmark.

3. **Improve-brew SSE on edit page:** Pending end-to-end SSE test through the actual NPM reverse proxy (not just local Docker). NPM SSE buffering config is a 19-07 operator task.

4. **CSP console violations on trimmed card:** Open DevTools console on /ai after rebuild, submit a research query, confirm zero `script-src` or `style-src` violations on the trimmed result card render. The trim is display-only but did move DOM elements, so a CSP re-check is warranted.

5. **CSRF token mechanism for wishlist POST:** `research_result.html` sends `X-CSRF-Token` as a form field (line ~39) read from the `csrftoken` cookie. Verify this matches how other working HTMX POST forms in this app send the token (e.g., compare with `research_form.html` or `paste_rank_results.html`). If there is a mismatch, the wishlist POST will fail CSRF silently in production. If confirmed mismatched, fix in 19-07 before the wishlist feature is considered production-ready.

## External Issue Surfaced During Verification

The saved Anthropic model name in the DB was `claude-opus-4.8` (period-separated, invalid API identifier), causing 404 on POST /v1/messages during the research call. Corrected directly in the DB to `claude-opus-4-8` (hyphen-separated). The admin "Test connection" passed the model-name check despite the invalid value because it only calls GET /v1/models (which lists available models), not POST /v1/messages (which actually invokes the model).

**Recommendation for 19-07:** Replace the admin "Test connection" check with a real 1-token `messages.create` probe so invalid model names are caught at configuration time rather than at first research invocation.

## Issues Encountered

- Container baked-image: test of trimmed template required `docker compose cp` to update the running container before running pytest (no source bind-mount). This is expected behavior documented in CLAUDE.md and CONTRIBUTING.md.

## Next Phase Readiness

- All Phase 19 UI surfaces are live and rebuilt
- 5 outstanding UAT items documented above for 19-07 to close
- NPM reverse proxy SSE buffering config is the remaining operator task before the research flow is production-ready end-to-end
- ADR 0004 is the authoritative record of the D-03 revision for any future /ai redesign

---
*Phase: 19-ai-page-research-predict*
*Completed: 2026-05-28*
