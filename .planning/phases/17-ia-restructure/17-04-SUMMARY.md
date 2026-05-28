---
phase: 17-ia-restructure
plan: 04
type: summary
status: complete
requirements: [IA-02, IA-03, AIX-08]
---

# Plan 17-04 Summary — /ai page shell

## Outcome

Built the `/ai` page shell at the existing AI router prefix root. The page is
the single consolidation point for AI surfaces (D-13 above-gate + key-present
branch) and shows three distinct empty states for the other branches —
cold-start meter (below gate), AIX-08 admin callout (above gate + admin + no
key), AIX-08 non-admin callout (above gate + non-admin + no key). The DIST-07
banner from plan 17-03 is reused at the top of the page; it self-gates on
`is_admin AND not ai_key_present` so admins-with-no-key get banner-plus-callout
coexistence (D-20).

## Files

**Added:**
- `app/templates/pages/ai.html` — 139-line three-branch composition; includes
  the DIST-07 banner at the top of `<main>`, branches on
  `gate.gate_open` → `ai_key_present` → `is_admin`. Mounts existing
  `/home/cards/ai-recommendation`, `/home/cards/preference-profile`,
  `/home/cards/flavor-descriptors`, `/home/cards/sweet-spots` endpoints via
  staggered HTMX lazy loads (100 / 200 / 300 / 500ms). AI tools section
  (paste-rank + wishlist + equipment form) recovered verbatim from the staged
  snippet. Includes `fragments/research_coming_soon.html` as the D-13 stub.
- `app/templates/fragments/ai/_no_key_admin_callout.html` — D-15 callout, amber
  palette, key icon, "AI keys needed" headline, Go to Admin filled button
  linking to `/admin/credentials`. `min-h-[14rem]` matches the cold-start
  card so layout doesn't jump (Pitfall F).
- `app/templates/fragments/ai/_no_key_non_admin_callout.html` — D-16 callout,
  neutral cream/espresso palette, key icon (neutral color), "AI is not set up"
  headline + "Ask the household admin" copy. Zero admin links. `min-h-[14rem]`.
- `app/templates/fragments/research_coming_soon.html` — D-13 disabled stub.
  `opacity-60` section + "Coming in Phase 19" copy + disabled `Coming soon`
  button. Phase 19 replaces this stub with the real research/predict UI.

**Moved (git rename, 94% similarity):**
- `app/templates/fragments/home/_cold_start.html` →
  `app/templates/fragments/ai/_cold_start.html` — body copy updated from
  "In the meantime, your recent brews and catalog are below." to the D-14
  explainer "AI personalization activates after 3 sessions and 5 distinct
  flavor notes." Section wrapper gains `min-h-[14rem]` for layout parity
  with the no-key callouts.

**Modified:**
- `app/routers/ai.py` — added `from app.services import analytics` and
  `from app.services import credentials as credentials_service` to the
  imports; new `GET ""` handler `get_ai_page` mounted before
  `get_paste_rank_page` (resolves to `/ai` due to the router prefix). The
  handler computes `gate` + `ai_key_present` from the canonical primitives
  used by `card_ai_recommendation` and renders `pages/ai.html`.
- `tests/routers/test_ai_router.py` — appended seven new test functions plus
  one parametrize variant (8 collected) covering every branch of pages/ai.html.
  Monkeypatches the router's bound `analytics.get_cold_start_counts` and
  `credentials_service.get_provider_credential` symbols — sidesteps the need
  to seed real brew_sessions + ApiCredential rows. Same strategy as plan
  17-03's `tests/test_dist07_banner.py`.
- `app/templates/fragments/home/ai_rec_cold_start.html` (bonus fix, NOT in
  plan's `files_modified` list) — its include path pointed at the OLD
  `fragments/home/_cold_start.html`; after the git mv, the regression
  `tests/routers/test_home.py::test_ai_card_cold_start` fired
  `TemplateNotFound`. Updated the include to
  `fragments/ai/_cold_start.html`. The cleaner alternative would be to
  inline the meter at the AI card cold-start path or skip the duplicate
  include altogether, but that's scope-creep for this plan.

## State machine (`/ai` branch table)

| Auth | gate_open | ai_key_present | is_admin | Renders |
|------|-----------|----------------|----------|---------|
| anon | —         | —              | —        | 401 (require_user) |
| ✓    | false     | —              | —        | cold-start meter (D-14) + Log session CTA |
| ✓    | true      | false          | true     | DIST-07 banner + AIX-08 admin callout (D-15) |
| ✓    | true      | false          | false    | D-16 social-action callout (no admin link) |
| ✓    | true      | true           | —        | AI hero + 3 lazy cards + AI tools + Research stub (D-13) |

Branch order in `pages/ai.html`: `gate_open` check fires FIRST, then
`ai_key_present`, then `is_admin`. A below-gate admin with no key sees the
cold-start meter — not the AIX-08 admin callout — because the gate check
short-circuits.

## Decisions honored

- **D-12**: `/ai` lives at the prefix root via `@router.get("")`; all
  existing `/ai/paste-rank`, `/ai/wishlist`, `/ai/refresh`, `/ai/equipment`,
  `/ai/wishlist/*` routes left intact (verified by re-running the full
  pre-existing `test_ai_router.py` suite alongside the new tests).
- **D-13**: above-gate + key-present renders the AI hero + Preference Profile
  + Top Flavor Descriptors + Sweet Spots + AI tools section + Research stub.
  AI hero `hx-trigger` delay dropped from 600ms (home pre-17-02) to 100ms —
  hero is the first card on /ai, no longer staggered against earlier mounts.
- **D-14**: below-gate users on /ai see the moved cold-start fragment with
  the updated explainer copy + the existing Log session CTA.
- **D-15 / D-16**: distinct callouts for admin vs non-admin no-key state —
  different palettes (amber vs neutral), different headlines, different
  actions (Go to Admin button vs none). Non-admin callout has zero
  `href="/admin"` references.
- **D-20**: DIST-07 banner included at the top of `<main>` on /ai; admins
  with no key see banner + callout coexisting. Banner self-gates so the
  include is safe for every user.

## Pitfall F (layout parity)

`min-h-[14rem]` applied to all three empty-state fragment wrappers
(cold-start, admin callout, non-admin callout) so the page doesn't jump
height as the user's state transitions across the gate or key boundary.

## `card_ai_recommendation` unchanged

`app/routers/home.py:220-288` continues to serve `/home/cards/ai-recommendation`
unchanged. Defense-in-depth: when the /ai page is below-gate or no-key the
hero `hx-get` mount never fires (the parent template branches), but if a race
condition fires it anyway, the endpoint's existing
`fragments/home/ai_rec_not_configured.html` fallback covers the no-key path
and `fragments/home/ai_rec_cold_start.html` covers the below-gate path.

## Gate results

- Container pytest (`tests/routers/test_ai_router.py tests/test_nav.py
  tests/test_dist07_banner.py tests/routers/test_home.py
  tests/services/test_analytics.py`): **108 passed, 24 warnings, ~19s**.
  No regressions in plans 17-01 / 17-02 / 17-03.
- `ruff format --check .`: 224 files already formatted (after a `ruff format`
  pass on the test module).
- `ruff check .`: All checks passed.

## Phase 17 close prerequisites for plan 17-05

- Docker image rebuild needed so the new templates + JS + Tailwind classes
  + SW cache hash are baked.
- Full container test suite as the cumulative gate.
- Manual IA-05 PWA cache-freshness check on physical iPhone PWA install.

## Self-Check: PASSED

All seven (eight with parametrize) new tests pass. Plans 17-01/02/03 tests
still green. Branch order in pages/ai.html matches D-13..D-16. Banner
self-gates correctly. Cold-start fragment moved with rename detection. No
`/setup` change (D-21) and no SW changes.
