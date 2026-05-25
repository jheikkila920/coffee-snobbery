# Phase 11: PWA + Mobile Polish - Pattern Map

**Mapped:** 2026-05-23
**Files analyzed:** 19 new/modified files
**Analogs found:** 17 / 19

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `app/routers/pwa.py` | router | request-response | `app/routers/search.py` + `app/main.py:compute_tailwind_css_path` | role-match |
| `app/routers/brew_guided.py` | router | request-response | `app/routers/home.py` | exact |
| `app/routers/config_hub.py` | router | request-response | `app/routers/home.py` | exact |
| `app/static/js/alpine-components/nav-bar.js` | utility (Alpine component) | event-driven | `app/static/js/alpine-components/search-bar.js` | role-match |
| `app/static/js/alpine-components/account-dropdown.js` | utility (Alpine component) | event-driven | `app/static/js/alpine-components/search-bar.js` | role-match |
| `app/static/js/alpine-components/ios-banner.js` | utility (Alpine component) | event-driven | `app/static/js/alpine-components/search-bar.js` + `brew-draft.js` (localStorage) | role-match |
| `app/static/js/alpine-components/guided-brew-mode.js` | utility (Alpine component) | event-driven | `app/static/js/alpine-components/brew-draft.js` | role-match |
| `app/static/js/sw.js` | utility (service worker) | event-driven | no existing analog | none |
| `app/templates/base.html` | template | request-response | self (modify existing) | self |
| `app/templates/pages/login.html` | template | request-response | self (modify existing) | self |
| `app/templates/pages/config_hub.html` | template | request-response | `app/templates/pages/home.html` | exact |
| `app/templates/pages/brew_guided.html` | template | request-response | `app/templates/pages/home.html` | role-match |
| `app/templates/fragments/*_list.html` (6 files, audit) | template | request-response | self (audit existing) | self |
| `app/static/css/tailwind.src.css` | config/style | transform | self (extend existing) | self |
| `app/models/brew_session.py` | model | CRUD | self (add column) | self |
| `app/migrations/versions/p11_brew_time_seconds.py` | migration | CRUD | `app/migrations/versions/p5_brew_sessions.py` | exact |
| `scripts/generate_pwa_icons.py` | utility | file-I/O | no existing analog (one-time script) | none |

---

## Pattern Assignments

### `app/routers/pwa.py` (router, request-response)

**Analogs:** `app/routers/search.py` (router structure) and `app/main.py:compute_tailwind_css_path` (build hash extraction)

**Imports pattern** — copy from `app/routers/search.py` lines 1-27, adapted:
```python
from __future__ import annotations

from pathlib import Path

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

router = APIRouter()
log = structlog.get_logger(__name__)
```

**Build-hash extraction** — copy from `app/main.py` lines 124-146, simplified for pwa.py:
```python
def _get_build_hash() -> str:
    """Extract 8-char hash from the hashed Tailwind CSS filename.

    Reuses the same hash compute_tailwind_css_path() uses in main.py so all
    cache keys stay in sync with a single build artifact. Returns 'dev' when
    no hashed file is present (e.g. local dev without a Docker build).
    """
    css_dir = Path("app/static/css")
    candidates = sorted(
        p for p in css_dir.glob("tailwind.*.css") if p.name != "tailwind.src.css"
    )
    if candidates:
        return candidates[0].stem.split(".", 1)[1]  # "tailwind.XXXXXXXX.css" → "XXXXXXXX"
    return "dev"

_BUILD_HASH = _get_build_hash()  # compute once at module load
```

**Route with custom headers** — the critical pattern for `/sw.js`. `StaticFiles` cannot set per-file headers; a FastAPI route is required:
```python
@router.get("/sw.js")
def service_worker() -> Response:
    sw_path = Path("app/static/js/sw.js")
    content = sw_path.read_text().replace("__BUILD_HASH__", _BUILD_HASH)
    return Response(
        content=content,
        media_type="application/javascript",
        headers={
            "Service-Worker-Allowed": "/",
            "Cache-Control": "no-cache",
        },
    )
```

**JSON route with custom Content-Type** — pattern for `/manifest.json`:
```python
@router.get("/manifest.json")
def manifest(request: Request) -> JSONResponse:
    data = { ... }  # locked strings from D-16/UX-02
    return JSONResponse(
        content=data,
        headers={"Content-Type": "application/manifest+json"},
    )
```

**Router registration in `main.py`** — copy the import+include pattern from `main.py` lines 85-244:
```python
# In main.py imports block (after existing router imports):
from app.routers import pwa as pwa_router

# In create_app() routers section (add BEFORE the healthz route,
# BEFORE StaticFiles can intercept /sw.js or /manifest.json):
app.include_router(pwa_router.router)
```

**IMPORTANT:** Register `pwa_router` before `StaticFiles` or at minimum before any other router that might catch the root-level paths. The `StaticFiles` mount at `/static` won't interfere with `/sw.js` or `/manifest.json` but the order matters for documentation clarity.

---

### `app/routers/brew_guided.py` (router, request-response)

**Analog:** `app/routers/home.py` (simple GET page render with `require_user`)

**Imports pattern** (lines 1-37 of home.py, simplified):
```python
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.dependencies.auth import require_user
from app.dependencies.db import get_session
from app.models.user import User
from app.templates_setup import templates

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/brew")
```

**Core GET pattern** (from `home.py` lines 41-67):
```python
@router.get("/guided", response_class=HTMLResponse)
def brew_guided(
    request: Request,
    recipe_id: int,
    coffee_id: int | None = None,
    user: User = Depends(require_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    # load recipe, verify it has steps, return 404 if not found
    return templates.TemplateResponse(
        request=request,
        name="pages/brew_guided.html",
        context={"recipe": recipe, "coffee": coffee},
    )
```

**Auth gate** — `Depends(require_user)` on every handler, exactly as in `home.py`. Unauthenticated callers get 401 from `require_user` (see `app/dependencies/auth.py` lines 33-45).

**404 on missing entity** — copy from `app/routers/brew.py` pattern (HTTPException 404 on service returning None):
```python
if recipe is None:
    raise HTTPException(status_code=404, detail="Recipe not found")
```

---

### `app/routers/config_hub.py` (router, request-response)

**Analog:** `app/routers/home.py` (simple page render with require_user + template context)

This is the simplest new router: a single `GET /config` that renders the catalog hub. It needs no DB queries beyond what `require_user` provides — the hub links are static.

**Imports + route** — stripped-down version of `home.py`:
```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response

from app.dependencies.auth import require_user
from app.models.user import User
from app.templates_setup import templates

router = APIRouter()

@router.get("/config", response_class=HTMLResponse)
def config_hub(
    request: Request,
    user: User = Depends(require_user),  # noqa: B008
) -> Response:
    return templates.TemplateResponse(
        request=request,
        name="pages/config_hub.html",
        context={"user": user},
    )
```

---

### `app/static/js/alpine-components/nav-bar.js` (Alpine component, event-driven)

**Analog:** `app/static/js/alpine-components/search-bar.js` (same file structure, same `alpine:init` registration pattern)

**File structure** — copy exactly from `search-bar.js` lines 1-64:
```javascript
// nav-bar.js — navBar Alpine component (Phase 11 / Plan XX).
//
// [description block mirroring search-bar.js header style]
// CSP-build compliant: registered via Alpine.data('navBar', ...) inside
// the 'alpine:init' event; the nav carries x-data="navBar" (string reference).
// No eval, no new Function — all handlers are declarative Alpine attributes.

document.addEventListener('alpine:init', () => {
  Alpine.data('navBar', () => ({
    // active tab derived from pathname — no eval needed
    get activeTab() {
      const p = window.location.pathname;
      if (p === '/' || p.startsWith('/home')) return 'home';
      if (p.startsWith('/brew')) return 'brew';
      if (p.startsWith('/config') || p.startsWith('/coffees') ||
          p.startsWith('/equipment') || p.startsWith('/recipes') ||
          p.startsWith('/roasters') || p.startsWith('/flavor-notes')) return 'config';
      if (p.startsWith('/admin')) return 'admin';
      return '';
    },
  }));
});
```

**Key CSP constraint** — `window.location.pathname.startsWith(...)` string comparison is allowed in the Alpine CSP build. No `eval`, no `new Function`. `x-bind:class` uses the `activeTab` getter result via string comparison in the template attribute.

**Registration in `base.html`** — add before the `@alpinejs/csp` core script, following the pattern of lines 17-28 of base.html:
```html
<script defer src="/static/js/alpine-components/nav-bar.js" nonce="{{ csp_nonce(request) }}"></script>
<script defer src="/static/js/alpine-components/account-dropdown.js" nonce="{{ csp_nonce(request) }}"></script>
<script defer src="/static/js/alpine-components/ios-banner.js" nonce="{{ csp_nonce(request) }}"></script>
```

---

### `app/static/js/alpine-components/account-dropdown.js` (Alpine component, event-driven)

**Analog:** `app/static/js/alpine-components/search-bar.js` (open/close + ESC + click-outside pattern)

**Open/close + ESC pattern** — copy from `search-bar.js` lines 19-63, adapted for a dropdown:
```javascript
document.addEventListener('alpine:init', () => {
  Alpine.data('accountDropdown', () => ({
    open: false,

    init() {
      this._onKeydown = (e) => {
        if (e.key === 'Escape' && this.open) {
          this.open = false;
        }
      };
      window.addEventListener('keydown', this._onKeydown);
    },

    destroy() {
      window.removeEventListener('keydown', this._onKeydown);
    },

    toggle() { this.open = !this.open; },
    close() { this.open = false; },
  }));
});
```

**Sign-out form in template** — CSRF-protected POST, copy the CSRF hidden field pattern from `app/templates/pages/login.html` line 9 and `app/routers/auth.py` D-12/D-15:
```html
{# Inside the accountDropdown x-data element — desktop only #}
<form method="post" action="/logout">
  <input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
  <button type="submit" class="...">Sign out</button>
</form>
```

**Click-outside close** — copy the pattern from `mini-modal.js` lines 68-74:
```javascript
onBackdropClick(e) {
  if (e.target === e.currentTarget) { this.close(); }
},
```

---

### `app/static/js/alpine-components/ios-banner.js` (Alpine component, event-driven)

**Analog:** `app/static/js/alpine-components/brew-draft.js` (localStorage read/write in `init()`)

**localStorage namespace pattern** — copy from `brew-draft.js` lines 32-35:
```javascript
// brew-draft.js uses: 'snobbery:draft:brew:' + userId
// ios-banner.js uses a simpler single key (no per-user namespace needed):
const DISMISSED_KEY = 'snobbery:ios-banner-dismissed';
```

**Component structure** — `alpine:init` wrapper from `search-bar.js`:
```javascript
document.addEventListener('alpine:init', () => {
  Alpine.data('iosBanner', () => ({
    show: false,

    init() {
      if (localStorage.getItem('snobbery:ios-banner-dismissed')) return;
      const isIOS = /iPhone|iPad|iPod/.test(navigator.userAgent);
      const isStandalone = window.navigator.standalone === true;
      if (isIOS && !isStandalone) { this.show = true; }
    },

    dismiss() {
      this.show = false;
      try {
        localStorage.setItem('snobbery:ios-banner-dismissed', '1');
      } catch (_err) { /* private mode / quota */ }
    },
  }));
});
```

**LocalStorage try/catch** — copy the defensive pattern from `brew-draft.js` lines 127-133:
```javascript
try {
  const raw = window.localStorage.getItem(this.storageKey);
  return raw ? JSON.parse(raw) : null;
} catch (_err) {
  return null;
}
```

---

### `app/static/js/alpine-components/guided-brew-mode.js` (Alpine component, event-driven)

**Analog:** `app/static/js/alpine-components/brew-draft.js` (localStorage prefs, `init()`/`destroy()` lifecycle, event listener cleanup)

**File header and `alpine:init` wrapper** — copy from `brew-draft.js` lines 1-30:
```javascript
// guided-brew-mode.js — guidedBrewMode Alpine component (Phase 11 / Plan XX).
//
// CSP-build compliant (docs/decisions/0001): registered via Alpine.data,
// string x-data reference, config via data-* attributes. No eval.
//
// Responsibilities:
//   1. Read recipe steps from data-steps attribute (JSON.parse — no eval).
//   2. Timer: setInterval countdown, auto-advance on step elapsed time.
//   3. Audio: AudioContext synthesized chime (unlocked in Start button handler).
//   4. Vibration: navigator.vibrate — fails silently on iOS.
//   5. Wake lock: navigator.wakeLock.request('screen') + NoSleep.js fallback.
//   6. Cue prefs: read/write localStorage 'snobbery:gbm:cues'.

document.addEventListener('alpine:init', () => {
  Alpine.data('guidedBrewMode', () => ({
    // ...
  }));
});
```

**init()/destroy() event listener cleanup** — copy exactly from `brew-draft.js` lines 51-78:
```javascript
init() {
  const ds = this.$root.dataset;
  // Read steps from data-steps attribute (JSON — no eval)
  try {
    this.steps = JSON.parse(ds.steps || '[]');
  } catch (_err) {
    this.steps = [];
  }
  this.recipeId = ds.recipeId || '';
  this.coffeeId = ds.coffeeId || '';

  this._loadCuePrefs();
  this._setupVisibilityReacquire();
},

destroy() {
  this._stopTimer();
  this._releaseWakeLock();
  // Remove any window event listeners added in init()
  if (this._onVisibility) {
    document.removeEventListener('visibilitychange', this._onVisibility);
  }
},
```

**LocalStorage cue prefs** — mirror the brew-draft namespace pattern:
```javascript
_loadCuePrefs() {
  try {
    const raw = localStorage.getItem('snobbery:gbm:cues');
    const prefs = raw ? JSON.parse(raw) : null;
    this.cuePrefs = prefs || { chime: true, vibrate: true };
  } catch (_err) {
    this.cuePrefs = { chime: true, vibrate: true };
  }
},

_saveCuePrefs() {
  try {
    localStorage.setItem('snobbery:gbm:cues', JSON.stringify(this.cuePrefs));
  } catch (_err) { /* quota / private mode */ }
},
```

**Wake lock pattern** — from RESEARCH.md Pattern 3:
```javascript
async requestWakeLock() {
  if ('wakeLock' in navigator) {
    try {
      this.wakeLockSentinel = await navigator.wakeLock.request('screen');
      this.wakeLockState = 'held';
      this.wakeLockSentinel.addEventListener('release', () => {
        this.wakeLockState = 'none';
      });
      return;
    } catch (_e) { /* falls through to NoSleep.js */ }
  }
  if (window.NoSleep) {
    this.noSleep = new window.NoSleep();
    try {
      await this.noSleep.enable();  // MUST be in user gesture handler
      this.wakeLockState = 'fallback';
    } catch (_e) { this.wakeLockState = 'none'; }
  }
},
```

**Audio unlock** — must run inside the Start button click handler (user gesture required by iOS):
```javascript
unlockAudio() {
  // Called from "Start guided brew" button tap — must be user gesture.
  if (!this.audioCtx) {
    this.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  if (this.audioCtx.state === 'suspended') {
    this.audioCtx.resume();
  }
},
```

**Vibration — graceful skip on iOS:**
```javascript
triggerVibration() {
  if (this.cuePrefs.vibrate && navigator.vibrate) {
    navigator.vibrate([100, 50, 100]);
  }
  // navigator.vibrate is undefined on iOS Safari — silent skip, no error.
},
```

**Data attribute config** — copy the data-* pattern from `autocomplete.js` lines 43-53:
```javascript
// Config comes from data-* attributes on the component root element.
// The @alpinejs/csp build cannot parse inline object-literal x-data arguments.
// Template sets: data-recipe-id, data-coffee-id, data-steps (JSON).
const ds = this.$root.dataset;
```

**Cancel confirmation** — copy window.confirm pattern from `mini-modal.js` line 53:
```javascript
cancelWithoutLogging() {
  if (window.confirm('Cancel brew? This cannot be undone.')) {
    window.location.assign('/brew');
  }
},
```

---

### `app/static/js/sw.js` (service worker, event-driven)

**No existing analog.** Use the pattern from RESEARCH.md Pattern 2. Key points:
- `__BUILD_HASH__` placeholder replaced at serve-time by `pwa.py`
- Non-GET bypass is the primary CSRF-safety guard
- Stale-while-revalidate for app shell + static assets
- Network-first for all other GETs

---

### `app/templates/base.html` (template, modify existing)

**Analog:** self — extend rather than replace

**Add `{% block head_extra %}` block** — insert between existing Alpine component scripts and the `@alpinejs/csp` core (between lines 28 and 34 of current base.html):
```html
{# Phase 11: per-page head extras (e.g. GBM's NoSleep.js). Empty by default.
   Populate from page templates via {% block head_extra %}...{% endblock %}. #}
{% block head_extra %}{% endblock %}
```

**Add new Alpine component script tags** — insert after existing `search-bar.js` line (line 28 of base.html), BEFORE `@alpinejs/csp` core (line 34). Copy the nonce pattern from lines 17-28:
```html
<script defer src="/static/js/alpine-components/nav-bar.js" nonce="{{ csp_nonce(request) }}"></script>
<script defer src="/static/js/alpine-components/account-dropdown.js" nonce="{{ csp_nonce(request) }}"></script>
<script defer src="/static/js/alpine-components/ios-banner.js" nonce="{{ csp_nonce(request) }}"></script>
```

**Service worker registration** — add after `htmx-listeners.js` script tag (line 38 of base.html). Inline script must carry nonce:
```html
<script nonce="{{ csp_nonce(request) }}">
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(function() {});
  }
</script>
```

**Nav frame** — replace the Phase 10 `<header x-data="searchBar" ...>` block (lines 47-151 of base.html) with the new nav frame. Keep the `{% if request.state.user %}` guard from line 46 — nav stays auth-gated.

**Bottom tab nav** (mobile, `<768px`) — copy structural classes from the existing search header (lines 89-98 of base.html):
```html
{# Bottom tab nav: fixed bottom-0, auth-gated #}
{% if request.state.user %}
<nav x-data="navBar"
     class="fixed bottom-0 left-0 right-0 z-40 h-16 pb-[env(safe-area-inset-bottom)]
            bg-cream-100 dark:bg-espresso-900
            border-t border-espresso-200 dark:border-espresso-700 md:hidden">
  {# tabs ... #}
</nav>
{% endif %}
```

**Top nav** (desktop, `>=768px`) — copy structural classes from search header desktop div (lines 49-86 of base.html):
```html
<header class="hidden md:flex h-14 px-6 items-center justify-between
               bg-cream-100 dark:bg-espresso-900
               border-b border-espresso-200 dark:border-espresso-700">
  {# logo + search (absorbed from Phase 10) + accountDropdown #}
</header>
```

**iOS banner** — add BEFORE `</body>`, after `#modal-mount`:
```html
{# iOS install banner — shown only on iOS Safari non-standalone #}
<div x-data="iosBanner" x-show="show" ...>...</div>
```

---

### `app/templates/pages/login.html` (template, modify existing)

**Analog:** self — redesign the existing file (currently 21 lines)

**Always-dark body override** — the existing body class in `base.html` is `bg-cream-50 dark:bg-espresso-950`. Login must always be dark. Do NOT modify the base body class. Instead, wrap the login content in a full-screen div override:
```html
{% extends "base.html" %}
{% block page_title %}Sign in{% endblock %}
{% block content %}
  <div class="min-h-screen bg-espresso-950 flex flex-col items-center justify-center px-6 py-12">
    {# Mascot hero #}
    <img src="/static/img/snobbery-login-hero.jpg" alt="Snobbery"
         class="max-w-[280px] mx-auto rounded-xl mb-6">
    {# Login card #}
    <div class="bg-espresso-900 rounded-xl p-6 shadow-xl max-w-sm w-full">
      {% if error %}<p class="text-red-400 mb-4">{{ error }}</p>{% endif %}
      <form method="post" action="/login" class="flex flex-col gap-4">
        <input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
        {# ... form fields ... #}
      </form>
    </div>
  </div>
{% endblock %}
```

**CSRF hidden field** — copy exactly from existing `login.html` line 9 and `setup.html` line 9:
```html
<input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
```

---

### `app/templates/pages/config_hub.html` (template, new)

**Analog:** `app/templates/pages/home.html` (extends base.html, page_title block, main layout)

**Template structure** — copy the extends + block pattern from `home.html` lines 1-25:
```html
{% extends "base.html" %}
{% block page_title %}Catalog{% endblock %}
{% block content %}
  <main class="mx-auto max-w-6xl px-6 py-12">
    <header class="flex flex-wrap items-center justify-between gap-4 mb-6">
      <h1 class="text-2xl font-semibold">Catalog</h1>
    </header>
    {# Catalog hub links ... #}

    {# Mobile-only: account + sign-out (D-03, md:hidden) #}
    <div class="md:hidden mt-8 border-t border-espresso-200 dark:border-espresso-700 pt-6">
      <p class="text-sm text-espresso-600 dark:text-cream-300">Signed in as {{ user.username }}</p>
      <form method="post" action="/logout" class="mt-3">
        <input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
        <button type="submit" class="rounded bg-espresso-700 px-4 py-2 text-base font-semibold text-cream-50">
          Sign out
        </button>
      </form>
    </div>
  </main>
{% endblock %}
```

**Admin gating** — copy from `home.html` lines 13-14:
```html
{% if request.state.user and request.state.user.is_admin %}
  {# admin link #}
{% endif %}
```

---

### `app/templates/pages/brew_guided.html` (template, new)

**Analog:** `app/templates/pages/home.html` (extends base.html structure) + the search full-screen sheet pattern from `base.html` lines 101-149

**Template structure** — extends base.html; uses `{% block head_extra %}` for NoSleep.js:
```html
{% extends "base.html" %}
{% block page_title %}Guided brew{% endblock %}
{% block head_extra %}
  {# NoSleep.js only on GBM page — nonce-tagged per CSP requirement #}
  <script defer src="/static/js/vendor/NoSleep.min.js" nonce="{{ csp_nonce(request) }}"></script>
{% endblock %}
{% block content %}
  <div x-data="guidedBrewMode"
       data-recipe-id="{{ recipe.id }}"
       data-coffee-id="{{ coffee.id if coffee else '' }}"
       data-steps="{{ recipe.steps | tojson }}"
       class="min-h-screen bg-cream-50 dark:bg-espresso-950">
    {# GBM start screen + timer screen + completion screen #}
    {# Bottom nav hidden per D-20 — this page does not include the nav block #}
  </div>
{% endblock %}
```

**Data attribute pattern** — copy from `autocomplete.js` lines 43-53 and RESEARCH.md Pattern 4 (GBM Step Data in Template):
```html
data-steps="{{ recipe.steps | tojson }}"
```

**Full-screen layout without nav** — copy from the search sheet `fixed inset-0` pattern in `base.html` lines 101-104:
```html
class="fixed inset-0 z-50 flex flex-col bg-cream-50 dark:bg-espresso-950"
```

---

### `app/templates/fragments/*_list.html` (6 files, audit-and-fix)

**Analog:** self — these already have the dual `hidden md:block` / `md:hidden` pattern

**Existing pattern to preserve** — from `session_list.html` lines 29-57:
```html
<div class="hidden md:block">
  <table class="w-full text-base">
    {# desktop table #}
  </table>
</div>
<div class="md:hidden space-y-3">
  {# mobile cards #}
</div>
```

**44px tap target fix** — wherever interactive elements are smaller, add:
```html
class="... min-h-[44px] min-w-[44px]"
```
This is already the project standard from `base.html` line 93 (search button).

**Empty state tone** — copy the existing snobbery-tone empty state from `session_list.html` lines 76-84 as the reference pattern for config hub and GBM:
```html
<div class="flex flex-col items-center justify-center text-center py-16 gap-3">
  <h2 class="text-lg font-semibold">No brews logged yet.</h2>
  <p class="text-base text-espresso-700 dark:text-cream-200">The snobbery awaits.</p>
  ...
</div>
```

---

### `app/static/css/tailwind.src.css` (config/style, extend existing)

**Analog:** self — extend the existing file

**Existing patterns to follow** (lines 1-83):
- `.htmx-indicator` rule outside `@layer` (so Tailwind purge cannot remove it) — lines 22-25
- `@layer base` for global element rules — lines 27-82
- `@media (prefers-color-scheme: dark)` nested inside `@layer base` — lines 53-62

**New additions follow the same pattern:**
```css
/* Nav safe-area padding — outside @layer so it is not purged */
.nav-safe-area { padding-bottom: env(safe-area-inset-bottom); }

/* GBM full-screen page — hide bottom nav */
/* No custom CSS needed — done via Tailwind utilities on the page template */
```

All nav/GBM/sheet layout is achievable with existing Tailwind utilities per UI-SPEC. Add to `tailwind.src.css` only if a specific utility cannot be expressed as a class (e.g. `env(safe-area-inset-bottom)` in a non-standard context).

---

### `app/models/brew_session.py` (model, add column)

**Analog:** self — additive change only

**New column pattern** — copy the nullable column pattern from `brew_session.py` lines 95-96 (any existing nullable column):
```python
brew_time_seconds: Mapped[int | None] = mapped_column(
    sa.Integer,  # not BigInteger — seconds fit in int
    nullable=True,
)
```

Place after the `notes` column, before the `# --- timestamps` comment block.

---

### `app/migrations/versions/p11_brew_time_seconds.py` (migration, CRUD)

**Analog:** `app/migrations/versions/p5_brew_sessions.py` — copy the migration file header and `add_column` pattern

**Migration header pattern** — copy from `p5_brew_sessions.py` lines 43-60:
```python
"""Phase 11: add brew_time_seconds to brew_sessions (D-10).

Revision ID: p11_brew_time_seconds
Revises: p10_search_indexes
Create Date: 2026-05-XX

Additive nullable column — no data migration required. Safe to run on
production with existing data. downgrade() drops the column.

Alembic-safe convention (mirrors p5_brew_sessions.py:32-35): this
migration body does NOT import from app.models.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "p11_brew_time_seconds"
down_revision: str | Sequence[str] | None = "p10_search_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
```

**upgrade/downgrade pattern** — from RESEARCH.md Code Examples:
```python
def upgrade() -> None:
    op.add_column(
        "brew_sessions",
        sa.Column("brew_time_seconds", sa.Integer(), nullable=True),
    )

def downgrade() -> None:
    op.drop_column("brew_sessions", "brew_time_seconds")
```

---

### `scripts/generate_pwa_icons.py` (utility, file-I/O)

**No existing analog in this codebase.** Use the pattern from RESEARCH.md Pattern 7. The script is one-time, not run in Docker or at runtime. Key Pillow methods: `Image.open`, `Image.convert("RGBA")`, `Image.resize`, `ImageDraw.ellipse` for circular crop mask.

---

## Shared Patterns

### Authentication gate (`require_user` / `require_admin`)
**Source:** `app/dependencies/auth.py` lines 33-45 and 48-62
**Apply to:** All new route handlers in `brew_guided.py`, `config_hub.py`, `pwa.py`

```python
# Every authenticated route handler:
user: User = Depends(require_user),  # noqa: B008

# Admin-gated routes only:
user: User = Depends(require_admin),  # noqa: B008
```

The `pwa.py` routes (`/manifest.json`, `/sw.js`) are PUBLIC — no `require_user`. These are intentionally unauthenticated since the service worker must install before login.

### CSRF on all state-changing forms
**Source:** `app/templates/pages/login.html` line 9, `app/templates/pages/setup.html` line 9
**Apply to:** All POST form templates (account dropdown sign-out in `base.html`, mobile sign-out in `config_hub.html`)

```html
<input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
```

### CSP nonce on every `<script>` tag
**Source:** `app/templates/base.html` lines 17-40
**Apply to:** Every new `<script>` tag in `base.html` and `brew_guided.html`

```html
<script defer src="..." nonce="{{ csp_nonce(request) }}"></script>
{# inline scripts also require nonce: #}
<script nonce="{{ csp_nonce(request) }}">...</script>
```

**Critical:** The `{% block head_extra %}` content renders INSIDE the Jinja template pipeline, so `csp_nonce(request)` is available in block overrides. `StaticFiles` responses bypass Jinja and therefore bypass the nonce — this is why the service worker and NoSleep.js must be loaded via nonce-tagged `<script>` tags in templates, not served as raw static files.

### Alpine component registration order
**Source:** `app/templates/base.html` lines 16-34
**Apply to:** All new Alpine component `<script>` tags

New component scripts MUST load with `defer` BEFORE the `@alpinejs/csp` core script (line 34 of base.html). The `alpine:init` event fires after the CSP build boots and walks the DOM — registrations in the component files must already be in place.

### Page title block
**Source:** `app/templates/base.html` line 11, `app/templates/pages/home.html` line 2
**Apply to:** All new page templates

```html
{% block page_title %}Guided brew{% endblock %}
```
Format is `Snobbery — {value}` assembled in `base.html`.

### Template response pattern
**Source:** `app/routers/home.py` lines 59-63
**Apply to:** All new page routes

```python
return templates.TemplateResponse(
    request=request,
    name="pages/brew_guided.html",
    context={...},
)
```

### Structlog logging
**Source:** `app/routers/auth.py` lines 84, `app/routers/home.py` line... (import pattern)
**Apply to:** New routers that have auditable events

```python
import structlog
log = structlog.get_logger(__name__)
log.info("event.name", key=value)
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `app/static/js/sw.js` | utility | event-driven | No service workers exist in the codebase; no other file uses the Cache API, ServiceWorkerGlobalScope, or `self.addEventListener('install')` pattern |
| `scripts/generate_pwa_icons.py` | utility (one-time script) | file-I/O | No Pillow scripts exist in the repo; one-time build artifact, not a FastAPI route or Alpine component |

Both files have complete patterns in RESEARCH.md (Pattern 2 for sw.js, Pattern 7 for generate_pwa_icons.py) that serve as the reference.

---

## Metadata

**Analog search scope:** `app/routers/`, `app/static/js/`, `app/templates/`, `app/models/`, `app/migrations/versions/`, `app/middleware/`, `app/dependencies/`, `app/static/css/`
**Files scanned:** 22
**Pattern extraction date:** 2026-05-23
