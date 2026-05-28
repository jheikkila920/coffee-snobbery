---
phase: 17-ia-restructure
plan: 03
type: summary
status: complete
requirements: [DIST-07]
---

# Plan 17-03 Summary — DIST-07 AI key setup banner

## Outcome

Wired the post-`/setup` AI-key-configuration nudge per D-19/D-20. Admin users
whose `api_credentials` table holds no decryptable AI key see an amber-bordered
banner at the top of `<main>` on Home (mounted in this plan) and `/ai` (mounted
by plan 17-04 — it includes the same fragment). Banner is dismissable for the
current browser tab via `sessionStorage`; the dismiss clears on tab close so
the banner reappears next visit until a key resolves. Admin-gated server-side
(defense-in-depth) — non-admins never see it; admins with a working key never
see it.

## Files

**Added:**
- `app/static/js/alpine-components/banner-dismiss.js` — Alpine CSP component;
  `Alpine.data('bannerDismiss', …)` inside `alpine:init`; sessionStorage key
  `snobbery:dist07-dismissed`; `init()` reads, `dismiss()` writes inside a
  try/catch (private-mode tolerant).
- `app/templates/fragments/ai_key_setup_banner.html` — shared banner fragment
  guarded by `{% if request.state.user.is_admin and not ai_key_present %}`;
  `x-data="bannerDismiss" x-show="!dismissed" style="display: block"`;
  amber-50 card; "Welcome — add your AI API key in Admin to enable
  recommendations." headline; `/admin/credentials` button; 24×24 stroke-X
  dismiss button.
- `tests/test_dist07_banner.py` — five assertions (admin+no-key shows, admin+key
  hides, non-admin always hides [parametrised], script registration, button
  href = `/admin/credentials`).

**Modified:**
- `app/templates/base.html` — one new `<script defer src="…/banner-dismiss.js"
  nonce="{{ csp_nonce(request) }}"></script>` line inserted after the
  `ios-banner.js` registration (before `dark-toggle.js`, before
  `@alpinejs/csp` core).
- `app/routers/home.py` — `home_shell` now computes `ai_key_present` from two
  `credentials_service.get_provider_credential(db, …)` calls (anthropic +
  openai); added to the template context dict.
- `app/templates/pages/home.html` — replaced the DIST-07 placeholder Jinja
  comment (left by plan 17-02 at line 11) with
  `{% include "fragments/ai_key_setup_banner.html" %}`.

## Banner visibility matrix

| User role  | AI key state | Banner renders? |
|------------|--------------|-----------------|
| Admin      | none         | **YES**         |
| Admin      | ≥1 resolves  | no              |
| Non-admin  | none         | no              |
| Non-admin  | ≥1 resolves  | no              |

## Test seed strategy (for plan 17-04 reuse)

Tests monkeypatch `app.routers.home.credentials_service.get_provider_credential`
on the home router module's bound symbol — not the source module's. This
matches the seed-strategy approach pinned in `17-03-PLAN.md` `<interfaces>`.

**Why monkeypatch over real `ApiCredential` rows:**

- Fernet encryption round-trip is already covered by
  `tests/services/test_credentials.py` — duplicating it here would add no
  signal and would couple template tests to encryption test infra.
- `get_provider_credential` is the canonical primitive used by
  `card_ai_recommendation`. Stubbing it at the call site exercises the same
  decision boundary the production code uses.
- Symmetric and trivially copyable for plan 17-04's AIX-08 callout tests.

The monkeypatch helpers `_patch_no_key(monkeypatch)` and
`_patch_with_key(monkeypatch, *, provider="anthropic")` live in
`tests/test_dist07_banner.py`. Plan 17-04 should copy and adapt these for
`tests/routers/test_ai_router.py`.

## Decisions honored

- **D-19**: Persistent admin banner on Home (this plan) + `/ai` (plan 17-04);
  session-dismissable but reappears until a key resolves.
- **D-20**: Banner gates on `is_admin AND not ai_key_present` — non-admins
  silent, admins-with-key silent. AIX-08 callout on `/ai` (plan 17-04 lands)
  coexists with this banner.
- **D-21**: `app/routers/auth.py` `/setup` redirect to `/` (line ~209) was NOT
  touched. No interstitial wizard. The banner is the nudge.

## Pitfall E (accepted v1)

Shared-device sessionStorage leak: user A dismisses the banner, signs out,
user B signs in on the same device in the same tab and inherits the
dismissal. Accepted v1 per RESEARCH; future improvement would be a
logout-time `sessionStorage.clear()` in the login template's `script` block.

## Gate results

- Container pytest (`tests/test_dist07_banner.py tests/test_nav.py
  tests/routers/test_home.py tests/services/test_analytics.py`): **82 passed,
  17 warnings, 16.89s**. No regressions in plans 17-01 / 17-02 tests.
- `ruff format --check .`: 224 files already formatted.
- `ruff check .`: All checks passed.

## Self-Check: PASSED

All five tests pass, ruff is clean, no regression in earlier-wave tests, the
banner fragment is admin- AND no-key-gated server-side, and the DIST-07
placeholder comment from plan 17-02 is replaced with a live `{% include %}`.
