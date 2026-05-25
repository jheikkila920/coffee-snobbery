---
phase: 11-pwa-mobile-polish
reviewed: 2026-05-23T00:00:00Z
depth: standard
files_reviewed: 28
files_reviewed_list:
  - app/main.py
  - app/migrations/versions/p11_brew_time_seconds.py
  - app/models/brew_session.py
  - app/routers/brew.py
  - app/routers/brew_guided.py
  - app/routers/config_hub.py
  - app/routers/pwa.py
  - app/schemas/brew_session.py
  - app/services/brew_sessions.py
  - app/static/css/tailwind.src.css
  - app/static/js/alpine-components/account-dropdown.js
  - app/static/js/alpine-components/guided-brew-mode.js
  - app/static/js/alpine-components/ios-banner.js
  - app/static/js/alpine-components/nav-bar.js
  - app/static/js/sw.js
  - app/templates/base.html
  - app/templates/fragments/coffee_row.html
  - app/templates/fragments/equipment_row.html
  - app/templates/fragments/flavor_note_modal.html
  - app/templates/fragments/flavor_note_row.html
  - app/templates/fragments/recipe_row.html
  - app/templates/fragments/roaster_modal.html
  - app/templates/fragments/roaster_row.html
  - app/templates/fragments/session_row.html
  - app/templates/pages/brew_form.html
  - app/templates/pages/brew_guided.html
  - app/templates/pages/config_hub.html
  - app/templates/pages/login.html
  - scripts/generate_pwa_icons.py
  - tests/routers/test_gbm.py
  - tests/test_migrations.py
  - tests/test_nav.py
  - tests/test_pwa.py
findings:
  critical: 2
  warning: 6
  info: 5
  total: 13
status: criticals_resolved
resolved:
  - "CR-01: brew_time_seconds now persists on edit (commit 5ffa4d3) + WR-01 edit-form seed + regression test"
  - "CR-02: '/' removed from SW APP_SHELL so the authenticated home shell is not stale-served across users (commit 5ffa4d3)"
warnings_open: [WR-02, WR-03, WR-05, WR-06]
---

# Phase 11: Code Review Report

> **Post-review resolution (2026-05-23):** Both critical blockers were fixed in
> commit `5ffa4d3` during phase execution. CR-01 (brew_time_seconds dropped on
> edit) — added to `_WRITABLE_FIELDS`, passed through `update_brew`, seeded into
> the edit form, plus a round-trip-on-edit regression test (now 7/7 GBM tests
> green). CR-02 (SW stale-serving the authenticated `/` shell across household
> users) — `/` removed from the precache APP_SHELL; it now uses network-first.
> Remaining WARN/INFO items (WR-02 GBM equal-offset steps, WR-03 advance/finish
> duplication, WR-05 tojson-in-attr regression test, WR-06 manifest media_type)
> are non-blocking and left as tracked follow-ups.

**Reviewed:** 2026-05-23
**Depth:** standard
**Files Reviewed:** 28 (plus 4 supporting files cross-referenced)
**Status:** issues_found

## Summary

Phase 11 ships the PWA scaffold (manifest, service worker, icons), the
`brew_time_seconds` column, the persistent nav frame + sign-out + dark login, and
Guided Brew Mode. The security-sensitive plumbing is mostly sound: the service
worker correctly bypasses non-GET requests (CSRF tokens reach the server),
restricts to same-origin, all Alpine components are CSP-build compliant
(`Alpine.data` + string `x-data`, no `eval`/`new Function`), no `|safe` appears in
the reviewed templates, and the brew schema enforces the `0..86400` range exactly
as specified.

Two correctness defects warrant blocking. First, `brew_time_seconds` is collected
and validated on the **edit** path but never written by the update service —
editing a session silently discards the field (data loss). Second, the service
worker precaches and serves the authenticated `/` app shell with
stale-while-revalidate, which on a shared household device serves one user's
chrome (username, admin link) to the next user and, offline, serves authenticated
HTML after sign-out. Both are reachable in normal multi-user use (John + Farrah,
the stated household).

Remaining findings are robustness and quality issues in the timer, prefill flow,
and template-driven GBM launch.

## Critical Issues

### CR-01: `brew_time_seconds` silently discarded when editing a session

**File:** `app/routers/brew.py:902-923`, `app/services/brew_sessions.py:66-86`, `app/templates/pages/brew_form.html:225-233`

The brew form template renders the `brew_time_seconds` number input in **both**
create and edit mode (`brew_form.html:227`, value seeded from
`values.get('brew_time_seconds')` which edit mode... does not even populate — see
WR-01). `BrewSessionUpdate` inherits the field and validates it. But:

1. `update_brew` (`brew.py:902-923`) builds its `update_brew_session(...)` call
   field-by-field and **omits `brew_time_seconds`** — unlike `create_brew`
   (`brew.py:810`) which passes it.
2. Even if it were passed, `_WRITABLE_FIELDS` (`brew_sessions.py:66-86`) does not
   include `brew_time_seconds`, so `update_brew_session` would filter it out:
   `values = {k: v for k, v in fields.items() if k in _WRITABLE_FIELDS}`
   (`brew_sessions.py:241`).

Net effect: a user who logs a brew via GBM (which seeds brew time), then edits
that session to correct any field, loses the recorded brew time — it is dropped on
save with no error. This is silent data loss on a field the phase exists to add.

**Fix:** Add the field to the writable set and pass it through on update:

```python
# app/services/brew_sessions.py — _WRITABLE_FIELDS
_WRITABLE_FIELDS = frozenset(
    {
        # ... existing fields ...
        "brewed_at",
        "brew_time_seconds",   # ADD
    }
)
```

```python
# app/routers/brew.py — update_brew(), in the update_brew_session(...) call
        brewed_at=form.brewed_at,
        brew_time_seconds=form.brew_time_seconds,   # ADD
    )
```

Note `update_brew_session(**fields)` already forwards arbitrary kwargs, so passing
it from the router plus adding it to `_WRITABLE_FIELDS` is sufficient. Add a
regression test asserting an edit that changes `brew_time_seconds` persists.

### CR-02: Service worker caches and serves the authenticated `/` app shell across users

**File:** `app/static/js/sw.js:11-18, 57-74`

`'/'` is in `APP_SHELL` and is served via the stale-while-revalidate branch
(`sw.js:60-74`), which both returns the cached copy first AND writes every fetched
copy back to the cache (`cache.put(req, response.clone())`). The home route `/` is
`require_user`-gated and renders per-user chrome: the username in the top nav and
mobile strip (`base.html:128,140,159`), the account dropdown, and the admin
link/tab when `request.state.user.is_admin` (`base.html:77-79, 261-270`).

Consequences on the stated multi-user household device:

- **Cross-user disclosure:** User A logs in, `/` is cached with A's username and
  (if A is admin) the admin link. A signs out; B signs in. The next load of `/`
  serves A's cached shell first (B sees A's username, possibly an admin link B
  should not have) until the background revalidate replaces it.
- **Post-logout offline serve:** With no network, `caches.match` returns the
  authenticated shell after sign-out — the app appears logged in.

The SW correctly bypasses non-GET (CSRF) and cross-origin, but does not account
for the auth-state coupling of the cached GET HTML. The home **cards** are fetched
via separate `/home/cards/*` GETs that fall through to the network-first branch, so
the leak is limited to the shell chrome — still user-identifying.

**Fix:** Do not precache or stale-serve authenticated navigations. Either:

1. Remove `'/'` from `APP_SHELL` and route HTML navigations (`req.mode ===
   'navigation'` / `Accept: text/html`) through network-first, caching only an
   offline fallback page; or
2. Restrict the cache to truly static, non-personalized assets (`/static/*`,
   `/manifest.json`, icons) and never cache HTML documents.

```js
// sw.js — drop '/' from APP_SHELL; treat navigations as network-first
const APP_SHELL = [
  '/manifest.json',
  '/static/img/icon-192.png',
  '/static/img/icon-512.png',
  '/static/img/apple-touch-icon.png',
  '/static/img/logo-badge.png',
];
// in fetch handler, before the isAppShell/isStatic branch:
if (req.mode === 'navigation') {
  event.respondWith(fetch(req).catch(() => /* offline fallback */));
  return;
}
```

## Warnings

### WR-01: Edit form never seeds `brew_time_seconds`, so the input is always blank in edit mode

**File:** `app/routers/brew.py:837-855`

`edit_brew_form` builds the `values` dict from the stored session but omits
`brew_time_seconds` entirely (the dict at `brew.py:837-855` has no
`brew_time_seconds` key). The template reads `values.get('brew_time_seconds', '')`
(`brew_form.html:229`), so the field renders empty on every edit even when the
stored session has a recorded brew time. Combined with CR-01 this means: edit
shows blank, and saving writes nothing — the field round-trips to loss. Fixing
CR-01 without this is still wrong (user would have to retype the time on every
edit).

**Fix:** Seed it in the edit values dict:

```python
# app/routers/brew.py — edit_brew_form values{}
        "brewed_at": session.brewed_at.strftime("%Y-%m-%dT%H:%M") if session.brewed_at else "",
        "brew_time_seconds": str(session.brew_time_seconds) if session.brew_time_seconds is not None else "",
```

### WR-02: GBM timer auto-advances through zero-duration steps within a single tick boundary, can skip cues / over-advance

**File:** `app/static/js/guided-brew-mode.js:155-180, 99-109`

`_tick` decrements then advances when `remainingSeconds === 0` (`gbm.js:155-165`).
`_advanceStep` sets `remainingSeconds = this._stepDuration(currentStepIndex)`
(`gbm.js:177`). If a recipe step has a cumulative `time_seconds` equal to the
previous step's offset (duration 0 — a legitimate user mistake or two steps at the
same time marker), the new `remainingSeconds` becomes 0, but `_advanceStep` does
**not** re-check and advance again within that call. The next condition only
re-evaluates on the following 1s tick, so a 0-duration step consumes a full second
of wall-clock and elapsed time it should not, and the displayed countdown sits at
`00:00` for a second. Worse, a chain of equal-offset steps advances one-per-second
regardless of their intended (zero) duration, desynchronizing the timer from the
recipe. There is no validation that step offsets are strictly increasing.

**Fix:** Loop the advance for zero-duration steps, or skip them, and guard against a
negative/zero duration producing an immediate re-fire:

```js
_tick() {
  this.elapsedTotalSeconds++;
  if (this.remainingSeconds > 0) this.remainingSeconds--;
  // advance through any run of zero-length steps in this tick
  while (this.remainingSeconds === 0 && this.isRunning && !this.isDone) {
    const before = this.currentStepIndex;
    this._advanceStep();
    if (this.currentStepIndex === before) break; // _advanceStep finished/clamped
    if (this.remainingSeconds > 0) break;
  }
}
```

(Alternatively validate in the recipe builder that step offsets strictly increase;
either way the runtime must not assume positive durations.)

### WR-03: `_advanceStep` and `nextStep_action` duplicate the same advance/finish logic

**File:** `app/static/js/guided-brew-mode.js:167-196`

`_advanceStep` (`gbm.js:167-180`) and `nextStep_action` (`gbm.js:183-196`) are
near-identical: same end-of-steps finish branch, same increment + reschedule + cue
block. Divergence risk: a fix to one (e.g. the WR-02 zero-duration handling, or a
cue change) will be missed in the other, and the manual "Next step" button already
behaves subtly differently (it has an `isDone`/`isRunning` guard the auto path
lacks). Consolidate to a single `_advanceStep({ manual })` used by both.

**Fix:** Extract one method:

```js
_goToNextStep() {
  if (this.currentStepIndex >= this.steps.length - 1) {
    this._stopTimer(); this.isRunning = false; this.isDone = true;
    this._releaseWakeLock(); return;
  }
  this.currentStepIndex++;
  this.remainingSeconds = this._stepDuration(this.currentStepIndex);
  if (this.cuePrefs.chime) this.playChime();
  if (this.cuePrefs.vibrate) this.triggerVibration();
}
// _advanceStep and nextStep_action both delegate to _goToNextStep()
```

### WR-04: GBM "Cancel without logging" / "Done without logging" use `window.confirm` and full-page navigation that bypass the SPA-ish HTMX flow, and `cancelWithoutLogging` discards elapsed time with no recovery

**File:** `app/static/js/guided-brew-mode.js:318-340`

`cancelWithoutLogging` (`gbm.js:318-324`) calls `window.confirm(...)` then
`window.location.assign('/brew')`, discarding the brew entirely. If the user has
been brewing for minutes and taps Cancel by reflex (it sits top-left where a back
button lives), all elapsed time is lost with only a generic confirm. The "Done"
screen has the proper "Log this brew" path, but the in-progress Cancel offers no
"log what I have so far." This is a UX-robustness gap on the primary value path
(the phase's reason to exist is fast, trustworthy logging). At minimum the confirm
copy should warn that timing will be lost; better, offer "log anyway."

**Fix:** Make the cancel confirm explicit ("Your brew timing will be discarded.")
and/or route cancel-with-elapsed to the same `finishBrewing()` prefill so the user
can still log. Low effort, meaningful on the core flow.

### WR-05: `recipe.steps | tojson` rendered into an HTML attribute relies on Jinja autoescape that `tojson` does not provide for `'` — verify the attribute quoting

**File:** `app/templates/pages/brew_guided.html:32`, `app/templates/pages/brew_form.html:95`

`data-steps="{{ recipe.steps | tojson }}"` (and `data-initial-chips='{{
selected_flavor_notes | tojson }}'` in `brew_form.html:95`). Jinja's `tojson`
filter HTML-escapes `<`, `>`, `&`, and `'` to `<` etc. by default in
Jinja2 ≥2.11, which makes it safe inside both single- and double-quoted attributes
— **provided** the project has not overridden `policies['json.dumps_kwargs']` or
the `tojson` filter. The two call sites use different quote styles (`"` in
brew_guided, `'` in brew_form), so safety depends entirely on `tojson` escaping
quotes. Recipe step `label`/`notes` are user-supplied free text. This is almost
certainly safe with stock Jinja2 3.1, but it is the one place in the phase where
user data is injected into an attribute via a filter rather than autoescape, and it
is worth an explicit test (assert a step label containing `"` and `</script>`
renders without breaking the attribute or the DOM).

**Fix:** Add a template-rendering test feeding a recipe whose step label is
`a"><img src=x onerror=alert(1)>` and assert the rendered `data-steps` attribute is
intact and the payload appears only as escaped text. Keep quote style consistent
(prefer double-quoted attributes with `tojson`).

### WR-06: `/manifest.json` JSONResponse sets `Content-Type` via both the JSONResponse default and an explicit header, risking a duplicate/again header

**File:** `app/routers/pwa.py:94-97`

`JSONResponse` already emits `content-type: application/json`. Passing
`headers={"Content-Type": "application/manifest+json"}` sets a second value;
Starlette's header handling will keep the explicitly-passed one, but relying on
override-by-late-set is fragile and the test only checks `in content_type`
(`test_pwa.py:23`). If a future Starlette version appends rather than replaces, the
manifest could ship `application/json` and fail Chrome's installability check
silently. Use `media_type` instead of a header to set it authoritatively.

**Fix:**

```python
return JSONResponse(content=data, media_type="application/manifest+json")
```

## Info

### IN-01: `service_worker()` reads `sw.js` from disk on every request

**File:** `app/routers/pwa.py:117-118`

`sw.js` is read + token-substituted per request (`Path(...).read_text(...)`). With
`Cache-Control: no-cache` clients revalidate often. The build hash is fixed at
module load (`_BUILD_HASH`), so the substituted content is constant for the process
lifetime — read once at startup and serve from memory. Performance is out of v1
scope; flagged only because the per-request file read is avoidable with no
behavior change.

### IN-02: `tests/routers/test_gbm.py` f-strings with no placeholders + over-broad cleanup

**File:** `tests/routers/test_gbm.py:106-109`

`text(f"DELETE FROM brew_sessions")` and `text(f"DELETE FROM brew_drafts")` are
f-strings with no interpolation (ruff F541). More importantly the fixture
`DELETE FROM brew_sessions` / `brew_drafts` is unscoped — it wipes ALL users' rows,
not just the test's, which can mask cross-test pollution and matches the known
"full-suite test isolation gaps" issue. Scope deletes by the test user or recipe
prefix where possible.

### IN-03: `test_brew_time_seconds_validation_rejects_86401` accepts 422 but the route never returns 422

**File:** `tests/routers/test_gbm.py:286-288`, `app/routers/brew.py:785-788`

The test asserts `status_code in (200, 422)`. `create_brew` catches
`ValidationError` and re-renders at 200 (`brew.py:787-788`, SEC-06) — it can never
return 422 for this input. The `422` branch is dead in this codebase; the assertion
passes only via the `200` arm. Tighten to `== 200` so a future regression that
starts 422-ing (losing the friendly re-render) is caught.

### IN-04: `nav-bar.js` `activeTab` reads `window.location.pathname` in a getter with no reactivity trigger

**File:** `app/static/js/nav-bar.js:21-31`

`activeTab` is a getter over `window.location.pathname`. On a full page load this is
correct, but any in-app HTMX navigation that changes the URL via `hx-push-url`
without re-evaluating Alpine bindings will leave the active tab stale. Given the
nav links are plain `<a href>` (full navigations), this is fine today; noting it so
a future move to HTMX-boosted nav does not silently break the active indicator.

### IN-05: Magic-string cache name and build-hash token are duplicated across `pwa.py` and `sw.js`

**File:** `app/routers/pwa.py:30-48`, `app/static/js/sw.js:5`

The `tailwind.*.css` glob + "second dot token is the hash" logic is duplicated in
`pwa.py:_get_build_hash` and `main.py:compute_tailwind_css_path` (DRY). And the
`__BUILD_HASH__` sentinel + `snobbery-v...` cache-name convention is split between
the Python substitution and the JS literal. Not a bug — both currently agree — but a
single shared helper for "resolve the hashed CSS filename / hash" would prevent the
two from drifting if the build output naming changes.

---

_Reviewed: 2026-05-23_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
