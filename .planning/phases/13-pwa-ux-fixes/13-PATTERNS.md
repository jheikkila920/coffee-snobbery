# Phase 13: PWA UX Fixes - Pattern Map

**Mapped:** 2026-05-24
**Files analyzed:** 18 new/modified files
**Analogs found:** 17 / 18

---

## LOAD-BEARING CORRECTION (from RESEARCH.md)

**Tailwind version is v3.4.17, NOT v4.** The Dockerfile (`ARG TAILWIND_VERSION=v3.4.17`) and `tailwind.config.js` (`module.exports = { darkMode: 'media', ... }`) are authoritative. C4 uses `darkMode: 'selector'` in `tailwind.config.js` (one-line change), NOT `@custom-variant dark` CSS syntax.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `app/templates/base.html` | template | request-response | self (modify) | exact |
| `app/templates/pages/config_hub.html` | template | request-response | self (modify) | exact |
| `app/templates/fragments/equipment_row.html` | fragment | request-response | `coffee_row.html` (pill pattern) | exact |
| `app/templates/fragments/equipment_list.html` | fragment | request-response | self (modify) | exact |
| `app/templates/pages/brew_guided.html` | template | event-driven | self (modify) | exact |
| `app/templates/fragments/recipe_row.html` | fragment | request-response | self (read-only, for test analog) | exact |
| `app/templates/pages/sessions.html` | template | request-response | self (modify) | exact |
| `app/templates/fragments/session_list.html` | fragment | request-response | self (modify) | exact |
| `app/templates/pages/home.html` | template | request-response | self (modify) | exact |
| `app/templates/pages/data_tools.html` (NEW) | template | request-response | `brew_import.html` | role-match |
| `app/routers/equipment.py` | router | request-response | self (modify), `coffees.py` create | exact |
| `app/routers/coffees.py` | router | request-response | self (modify), `equipment.py` create | exact |
| `app/static/js/alpine-components/dark-toggle.js` (NEW) | component | event-driven | `ios-banner.js` (localStorage pattern) | role-match |
| `app/static/js/alpine-components/guided-brew-mode.js` | component | event-driven | self (modify) | exact |
| `app/static/css/tailwind.src.css` | config/style | transform | self (modify) | exact |
| `tailwind.config.js` | config | transform | self (modify) | exact |
| `app/static/js/sw.js` | utility | event-driven | self (modify) | exact |
| `app/routers/pwa.py` | router | request-response | self (modify) | exact |
| `Dockerfile` | config | transform | self (modify) | exact |
| `scripts/generate_pwa_icons.py` | utility | file-I/O | self (modify) | exact |
| `tests/test_pwa.py` | test | request-response | self (extend) | exact |
| `tests/routers/test_equipment_create_fragment.py` (NEW) | test | request-response | `tests/routers/test_brew_router.py` | role-match |
| `tests/templates/test_recipe_row.py` (NEW) | test | request-response | `tests/test_pwa.py` | role-match |

---

## Pattern Assignments

### `app/templates/base.html` (template, request-response) — C1, C4, C10

**Analog:** self (modify in-place)

**Existing nonce'd inline script pattern** (line 59 — the service worker registration):
```html
<script nonce="{{ csp_nonce(request) }}">if ('serviceWorker' in navigator) { navigator.serviceWorker.register('/sw.js').catch(function(){}); }</script>
```
This is the **exact pattern** the no-FOUC C4 script copies: synchronous (no `defer`), nonce-tagged, IIFE.

**No-FOUC script to INSERT before the Tailwind `<link>` tag** (line 21):
```html
{# No-FOUC dark mode class — runs synchronously before first paint.
   Must appear BEFORE the Tailwind CSS link to prevent flash.
   Nonce required by strict CSP (ADR 0001). No defer, no async. #}
<script nonce="{{ csp_nonce(request) }}">(function(){
  var t = localStorage.getItem('snobbery:theme');
  if (t === 'dark' || (t === null && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
    document.documentElement.classList.add('dark');
  }
})();</script>
```

**Alpine component registration pattern** (lines 26-42 — must load BEFORE `@alpinejs/csp` core at line 51):
```html
<script defer src="/static/js/alpine-components/dark-toggle.js" nonce="{{ csp_nonce(request) }}"></script>
```
Add this line in the block between line 42 (ios-banner.js) and line 45 (head_extra block).

**C1 mobile top strip safe-area** (line 164 — the `md:hidden` mobile top strip div):
```html
{# Current: #}
<div x-data="searchBar" class="md:hidden flex h-14 px-4 items-center justify-between bg-cream-100 dark:bg-espresso-900 border-b border-espresso-200 dark:border-espresso-700">

{# C1 change — switch h-14 to min-h-14 + add top safe-area padding: #}
<div x-data="searchBar" class="md:hidden flex min-h-14 px-4 items-center justify-between bg-cream-100 dark:bg-espresso-900 border-b border-espresso-200 dark:border-espresso-700 pt-[env(safe-area-inset-top)]">
```

**Bottom nav safe-area analog** (lines 237-240 — the proven technique C1 mirrors):
```html
<nav x-data="navBar"
     class="fixed bottom-0 left-0 right-0 z-40 h-16 pb-[env(safe-area-inset-bottom)]
            bg-cream-100 dark:bg-espresso-900
            border-t border-espresso-200 dark:border-espresso-700
            nav-safe-area-extend md:hidden">
```

**C10 logo src** (lines 74, 167 — two logo badge img tags; both reference `/static/img/logo-badge.png`, no CSS change needed):
```html
<img src="/static/img/logo-badge.png" alt="Snobbery" class="h-12 w-12 rounded-full">
<img src="/static/img/logo-badge.png" alt="Snobbery" class="h-10 w-10 rounded-full">
```
The markup is already correct (`h-N w-N rounded-full`, equal dimensions). The fix is the PNG asset, not the HTML.

---

### `app/templates/pages/config_hub.html` (template, request-response) — C4, C8

**Analog:** self (modify in-place)

**Mobile account section** (lines 54-66 — the attach point for dark toggle + export/import link):
```html
<div class="md:hidden mt-8 border-t border-espresso-200 dark:border-espresso-700 pt-6">
  <p class="text-sm text-espresso-600 dark:text-cream-300">Signed in as</p>
  <p class="text-base font-semibold text-espresso-900 dark:text-cream-100 mb-4">{{ user.username }}</p>
  <form method="post" action="/logout">
    <input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
    <button type="submit"
            class="rounded bg-espresso-700 px-4 py-2 text-base font-semibold text-cream-50 hover:bg-espresso-800 min-h-[44px]">
      Sign out
    </button>
  </form>
</div>
```

**C4 dark toggle insertion point:** After the Sign out button, before `</div>`. Use `x-data="darkToggle"` (CSP pattern — string reference, not inline object):
```html
{# Dark mode toggle — 3-state Auto/Light/Dark (D-01).
   x-data="darkToggle" string reference per docs/decisions/0001 CSP constraint. #}
<div x-data="darkToggle" class="mt-4">
  <p class="text-sm font-semibold text-espresso-700 dark:text-cream-200 mb-2">Display</p>
  <div class="flex gap-2">
    <button x-on:click="setTheme('auto')"  class="..." ...>Auto</button>
    <button x-on:click="setTheme('light')" class="..." ...>Light</button>
    <button x-on:click="setTheme('dark')"  class="..." ...>Dark</button>
  </div>
</div>
```

**C8 export/import link pattern** (copy from `sessions.html` lines 21-29 — use `<a>` not form):
```html
{# Data tools link (D-06) — replaces inline Export/Import controls on the log view. #}
<a href="/data-tools"
   class="mt-4 inline-flex items-center rounded border border-espresso-300 px-4 py-2 text-base text-espresso-800 hover:bg-espresso-50 dark:border-espresso-700 dark:text-cream-200 dark:hover:bg-espresso-900 min-h-[44px]">
  Export / Import sessions
</a>
```

**Catalog card pattern** (lines 14-52 — how tap-target cards render, if a new catalog card is needed):
```html
<a href="/..."
   class="flex items-center gap-3 rounded-xl border border-espresso-200 dark:border-espresso-700 bg-cream-100 dark:bg-espresso-900 px-4 py-4 min-h-[44px] hover:bg-cream-200 dark:hover:bg-espresso-800 transition-colors">
  <svg ...></svg>
  <span class="text-base font-semibold text-espresso-900 dark:text-cream-100">Label</span>
</a>
```

---

### `app/templates/fragments/equipment_row.html` (fragment, request-response) — C2, C3

**Analogs:** self (C2 OOB clear removal), `coffee_row.html` lines 43-50 (C3 flex-wrap pill pattern)

**C3 target: coffee card flex-wrap pill pattern** (`coffee_row.html` lines 43-50):
```html
{# Coffee card mode — how pills and fields group at 375px.
   equipment_row.html card mode must copy this grouping for C3. #}
<div class="mt-1 flex flex-wrap gap-2">
  {% if coffee.process %}
    <span class="inline-flex px-2 py-1 rounded text-sm bg-cream-200 text-espresso-900 dark:bg-espresso-800 dark:text-cream-200">{{ coffee.process }}</span>
  {% endif %}
  {% if coffee.roast_level %}
    <span class="inline-flex px-2 py-1 rounded text-sm bg-cream-200 text-espresso-900 dark:bg-espresso-800 dark:text-cream-200">{{ coffee.roast_level }}</span>
  {% endif %}
</div>
```

**Apply to equipment card mode** — replace the current one-field-per-line layout (lines 27-33) with:
```html
{# C3: group type + usage_count as flex-wrap pills (mirrors coffee card, lines 43-50). #}
<div class="mt-1 flex flex-wrap gap-2">
  <span class="inline-flex px-2 py-1 rounded text-sm bg-cream-200 text-espresso-900 dark:bg-espresso-800 dark:text-cream-200">{{ equipment.type }}</span>
  <span class="inline-flex px-2 py-1 rounded text-sm bg-cream-200 text-espresso-900 dark:bg-espresso-800 dark:text-cream-200">{{ equipment.usage_count }} session{% if equipment.usage_count != 1 %}s{% endif %}</span>
</div>
{% if equipment.notes %}
  <div class="text-sm mt-1 truncate">{{ equipment.notes }}</div>
{% endif %}
```

**C2 OOB form-clear removal** (lines 88-91 — the `include_oob_form_clear` block):
```html
{# CURRENT — clears form in place on successful create: #}
{% if include_oob_form_clear %}
  <div id="equipment-form-mount" hx-swap-oob="innerHTML"></div>
{% endif %}
```
For C2, this entire block is removed. The create route will return `equipment_list.html` instead of `equipment_row.html`, so the OOB clear is no longer needed (form collapses via the list-swap target replacing the form-mount container).

---

### `app/routers/equipment.py` (router, request-response) — C2

**Analog:** self (modify `create_equipment` handler, lines 174-225)

**Current broken create handler** (lines 217-225 — returns wrong fragment):
```python
return templates.TemplateResponse(
    request=request,
    name="fragments/equipment_row.html",
    context={
        "equipment": equipment,
        "mode": "row",                  # <-- BUG: <tr> in non-table div
        "include_oob_form_clear": True, # <-- BUG: OOB clear instead of list-swap
    },
)
```

**D-03 fix pattern** (return the list fragment, collapse the form). The list route handler at lines 107-133 shows exactly how to build the list context:
```python
groups = equipment_service.list_equipment_grouped_by_type(db, include_archived=False)
return templates.TemplateResponse(
    request=request,
    name="fragments/equipment_list.html",
    context={"groups": groups, "include_archived": False},
)
```

**HTMX target change required in `equipment.html` template:** The create form's `hx-target` must point at `#equipment-list` (the list container) with `hx-swap="innerHTML"`, not at `#equipment-form-mount`. The form must also collapse on success — `hx-target` on the form pointing at the list region causes the form mount div to be replaced with the list, achieving collapse implicitly.

---

### `app/routers/coffees.py` (router, request-response) — C2

**Analog:** `equipment.py` create handler pattern above; self (modify `create_coffee`, lines 350-~415)

**Current broken create handler** (lines 380-~415 — same pattern as equipment):
```python
coffee = coffees_service.create_coffee(...)
return templates.TemplateResponse(
    request=request,
    name="fragments/coffee_row.html",   # <-- BUG: <tr> in non-table div
    context={
        "coffee": coffee,
        "mode": "row",
        "include_oob_form_clear": True,
        ...
    },
)
```

**D-03 fix:** return `coffee_list.html` fragment with full list context (coffees + flavor_note_names + roaster_name_map). The list GET handler already builds this context — copy that pattern:
```python
coffees = coffees_service.list_coffees(db, ...)
flavor_note_names = coffees_service.resolve_flavor_note_names(db, coffees)
roaster_name_map = coffees_service.resolve_roaster_names(db, coffees)
return templates.TemplateResponse(
    request=request,
    name="fragments/coffee_list.html",
    context={
        "coffees": coffees,
        "flavor_note_names": flavor_note_names,
        "roaster_name_map": roaster_name_map,
    },
)
```

---

### `app/templates/pages/data_tools.html` (NEW template, request-response) — C8

**Analog:** `app/templates/pages/brew_import.html` (role-match, same page structure)

**Page structure pattern** (`brew_import.html` lines 1-47 — full page):
```html
{% extends "base.html" %}
{% block page_title %}Import sessions{% endblock %}
{% block content %}
  <main class="mx-auto max-w-2xl px-6 py-12">
    <header class="mb-6">
      <h1 class="text-2xl font-semibold">Import brew sessions</h1>
      <p class="mt-2 text-sm text-espresso-600 dark:text-cream-300">...</p>
    </header>
    <form hx-post="/brew/import"
          hx-encoding="multipart/form-data"
          hx-target="#import-results"
          hx-swap="innerHTML"
          class="rounded-lg border border-espresso-200 bg-cream-100 p-6 dark:bg-espresso-900 dark:border-espresso-800">
      <input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
      ...
    </form>
  </main>
{% endblock %}
```

The new `data_tools.html` page combines Export (link) + Import (form) on one page. It extends `base.html`, uses `max-w-2xl px-6 py-12`, includes the CSRF token on the import form, and reuses the `hx-post="/brew/import"` form action unchanged (D-06: routes are unchanged).

**Export link pattern** (from `sessions.html` lines 21-25):
```html
<a href="/brew/export"
   class="rounded bg-espresso-700 px-4 py-2 text-base font-semibold text-cream-50 hover:bg-espresso-800 dark:text-cream-50">
  Export CSV
</a>
```

---

### `app/static/js/alpine-components/dark-toggle.js` (NEW component) — C4

**Analog:** `app/static/js/alpine-components/ios-banner.js` (same registration pattern, same localStorage approach)

**Registration pattern** (`ios-banner.js` lines 14-48 — the exact boilerplate to copy):
```javascript
document.addEventListener('alpine:init', () => {
  Alpine.data('iosBanner', () => ({
    show: false,

    init() {
      // Read localStorage on init
      if (localStorage.getItem('snobbery:ios-banner-dismissed')) return;
      // ... logic ...
    },

    dismiss() {
      this.show = false;
      try {
        localStorage.setItem('snobbery:ios-banner-dismissed', '1');
      } catch (_e) {
        // Private mode or quota — silent fail
      }
    },
  }));
});
```

**Dark-toggle implementation** following this pattern exactly:
```javascript
// dark-toggle.js — darkToggle Alpine component (Phase 13 / Plan C4).
// CSP-build compliant (docs/decisions/0001): registered via Alpine.data,
// string x-data reference. No eval. localStorage namespaced as snobbery:theme.
document.addEventListener('alpine:init', () => {
  Alpine.data('darkToggle', function() {
    return {
      theme: localStorage.getItem('snobbery:theme') || 'auto',

      setTheme: function(val) {
        this.theme = val;
        if (val === 'auto') {
          localStorage.removeItem('snobbery:theme');
          if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
            document.documentElement.classList.add('dark');
          } else {
            document.documentElement.classList.remove('dark');
          }
        } else if (val === 'dark') {
          localStorage.setItem('snobbery:theme', 'dark');
          document.documentElement.classList.add('dark');
        } else {
          localStorage.setItem('snobbery:theme', 'light');
          document.documentElement.classList.remove('dark');
        }
      },

      isActive: function(val) {
        return this.theme === val;
      },
    };
  });
});
```

**No `x-model`** — forbidden in CSP build. Use `x-on:click="setTheme('dark')"` per button, `:class` for active state.

**localStorage namespacing precedent:**
- `snobbery:ios-banner-dismissed` (`ios-banner.js` line 24)
- `snobbery:gbm:cues` (`guided-brew-mode.js` lines 291, 302)
- `snobbery:draft:brew:<user_id>` (`brew-draft.js` line 35)
- New: `snobbery:theme` (C4, consistent prefix, no user-scoping needed — theme is a device pref)

---

### `app/templates/pages/brew_guided.html` (template, event-driven) — C6

**Analog:** self (modify in-place)

**Current cue controls (START SCREEN, lines 91-119) — the `role="switch"` toggles to replace:**
```html
<div class="rounded-lg border border-espresso-200 dark:border-espresso-700 p-4 flex flex-col gap-4">
  <p class="text-sm font-semibold text-espresso-700 dark:text-cream-200">Audio &amp; haptic cues</p>
  <div class="flex items-center justify-between">
    <label for="gbm-chime" class="text-sm">Chime at each step</label>
    <button type="button"
            id="gbm-chime"
            x-on:click="toggleChime()"
            :aria-checked="cuePrefs.chime.toString()"
            role="switch"
            :class="cuePrefs.chime ? 'bg-espresso-700' : 'bg-espresso-300 dark:bg-espresso-700'"
            class="relative inline-flex h-6 w-11 items-center rounded-full ...">
      <span :class="cuePrefs.chime ? 'translate-x-5' : 'translate-x-1'" ...></span>
    </button>
  </div>
  ...
</div>
```

**C6 replacement pattern** — use clearly-labeled On/Off buttons (same `x-on:click` handler, no `role="switch"`):
```html
{# C6: Replace confusing role=switch toggles with explicit On/Off buttons. #}
<div class="rounded-lg border border-espresso-200 dark:border-espresso-700 p-4 flex flex-col gap-3">
  <p class="text-sm font-semibold text-espresso-700 dark:text-cream-200">Audio &amp; haptic cues</p>
  <div class="flex items-center justify-between gap-3">
    <span class="text-sm">Chime at each step</span>
    <div class="flex gap-2">
      <button type="button"
              x-on:click="toggleChime()"
              :class="cuePrefs.chime ? 'bg-espresso-700 text-cream-50' : 'border border-espresso-300 text-espresso-800 dark:border-espresso-700 dark:text-cream-200'"
              class="rounded px-3 py-1 text-sm min-h-[44px]">On</button>
      <button type="button"
              x-on:click="toggleChime()"
              :class="!cuePrefs.chime ? 'bg-espresso-700 text-cream-50' : 'border border-espresso-300 text-espresso-800 dark:border-espresso-700 dark:text-cream-200'"
              class="rounded px-3 py-1 text-sm min-h-[44px]">Off</button>
    </div>
  </div>
  {# repeat for vibrate #}
</div>
```

The `toggleChime()` and `toggleVibrate()` methods in `guided-brew-mode.js` are preserved unchanged — only the template markup changes.

**In-brew cue mute buttons** (lines 207-224) — also replace emoji buttons with labeled text buttons following the same On/Off pattern.

---

### `app/static/js/alpine-components/guided-brew-mode.js` (component) — C6

**Analog:** self (the `toggleChime` / `toggleVibrate` / `_loadCuePrefs` / `_saveCuePrefs` methods are unchanged)

**Preserve unchanged** (lines 289-315 — cue prefs localStorage read/write):
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
toggleChime() {
  this.cuePrefs = { ...this.cuePrefs, chime: !this.cuePrefs.chime };
  this._saveCuePrefs();
},
toggleVibrate() {
  this.cuePrefs = { ...this.cuePrefs, vibrate: !this.cuePrefs.vibrate };
  this._saveCuePrefs();
},
```
C6 is a template-only change. The JS component is not modified.

---

### Brew form templates — C7 ratio recalc + star wrap

**C7a: `brew-ratio.js` ratio recalc on programmatic prefill**

**Analog:** `brew-ratio.js` `init()` pattern (lines 31-36 — already reads `data-*` for seed values):
```javascript
init() {
  this.dose = this._parse(this.$root.dataset.initialDose);
  this.water = this._parse(this.$root.dataset.initialWater);
  this.yieldGrams = this._parse(this.$root.dataset.initialYield);
  this.tds = this._parse(this.$root.dataset.initialTds);
},
```
The problem: when HTMX swaps prefill values programmatically, `x-on:input` doesn't fire on form elements that weren't touched by the user. The fix is to add an Alpine `$watch` in `init()` that re-reads the dose/water fields when Alpine detects a value change:
```javascript
init() {
  // existing seed reads ...
  // Add watchers so programmatic HTMX prefill swaps trigger ratio recalc.
  this.$watch('dose', () => {}); // watchers cause reactivity re-eval
  this.$watch('water', () => {}); // the getters recompute automatically
},
```
Alternatively, the prefill HTMX swap endpoint (`/brew/prefill`) should return updated `data-initial-*` attributes on the `brewRatio` root element, causing Alpine to re-init. Check how `GET /brew/prefill` returns the fragment — the root element's `data-initial-dose` / `data-initial-water` must carry the new values.

**C7b: rating stars single-line at 375px**

**Analog:** `rating-stars.js` (no JS change) + the brew form template's star row. The layout fix is CSS/template: the star container uses `flex flex-wrap` when it should use `flex flex-nowrap` or constrain star sizes. Each star zone is `min-h-[44px] min-w-[44px]` — at 375px, 5 stars × 44px = 220px which fits. Check if the issue is outer container flex-wrap or padding. Use `flex-nowrap` on the rating star container row.

---

### `app/static/css/tailwind.src.css` (config/style) — C1, C4

**Analog:** self (modify in-place)

**C4: Two `@media (prefers-color-scheme: dark)` blocks to rewrite** (lines 88-97 and 111-116 inside `@layer base`):

```css
/* CURRENT — lines 88-97: */
@media (prefers-color-scheme: dark) {
  input, select, textarea {
    color: #F4EFE6;
    background-color: #21150C;
    border-color: #3D2817;
  }
  input::placeholder, textarea::placeholder {
    color: #DACBAE;
  }
}

/* REPLACE WITH: */
.dark input, .dark select, .dark textarea {
  color: #F4EFE6;
  background-color: #21150C;
  border-color: #3D2817;
}
.dark input::placeholder, .dark textarea::placeholder {
  color: #DACBAE;
}

/* CURRENT — lines 111-116: */
@media (prefers-color-scheme: dark) {
  a { color: #E3D5C9; }
  a:hover { color: #F4EFE6; }
}

/* REPLACE WITH: */
.dark a { color: #E3D5C9; }
.dark a:hover { color: #F4EFE6; }
```

**C1: Top safe-area CSS rule** — add outside `@layer` (mirror the existing bottom safe-area rules at lines 18-51):
```css
/* Top safe-area padding for iOS standalone PWA (C1 — mirrors .nav-safe-area-extend pattern).
 * Applied to the mobile top strip via pt-[env(safe-area-inset-top)] utility class.
 * min-h-14 + auto height accommodates variable inset on notch / Dynamic Island devices. */
.top-safe-area { padding-top: env(safe-area-inset-top); }
```

---

### `tailwind.config.js` (config) — C4

**Analog:** self (one-line change)

```javascript
// CURRENT (line 27):
darkMode: 'media',

// CHANGE TO:
darkMode: 'selector',  // v3.4.1+ canonical value; activates .dark class on <html>
```

---

### `app/routers/pwa.py` (router, request-response) — C9

**Analog:** self (modify `_get_build_hash()`, lines 30-46)

**Current implementation** (lines 30-46):
```python
def _get_build_hash() -> str:
    css_dir = Path("app/static/css")
    candidates = sorted(p for p in css_dir.glob("tailwind.*.css") if p.name != "tailwind.src.css")
    if candidates:
        return candidates[0].stem.split(".", 1)[1]
    return "dev"
```

**C9 fix** — read `build_id.txt` first, fall back to CSS hash for dev:
```python
def _get_build_hash() -> str:
    """Return build hash for SW cache name.

    Primary: app/static/build_id.txt written unconditionally on every
    docker compose build (Dockerfile stage 1 RUN step). Always changes
    per build regardless of which source files changed — fixes the root
    cause where only editing tailwind.src.css bumped the cache name.
    Fallback: CSS hash (dev environment where build_id.txt is absent).
    """
    build_id_path = Path("app/static/build_id.txt")
    if build_id_path.exists():
        return build_id_path.read_text(encoding="utf-8").strip()[:16]
    css_dir = Path("app/static/css")
    candidates = sorted(
        p for p in css_dir.glob("tailwind.*.css") if p.name != "tailwind.src.css"
    )
    if candidates:
        return candidates[0].stem.split(".", 1)[1]
    return "dev"
```

---

### `app/static/js/sw.js` (utility, event-driven) — C9

**Analog:** self (read-only for C9 — the existing `skipWaiting` + `clients.claim` + activate cache purge pattern is already correct)

**Preserve unchanged** (lines 26-44 — the install + activate handlers that C9 must not break):
```javascript
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => cache.addAll(APP_SHELL))
    );
    self.skipWaiting();  // MUST preserve — iOS standalone never "closes"
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(
                keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
            )
        )
    );
    self.clients.claim();  // MUST preserve
});
```
The `CACHE_NAME = 'snobbery-v__BUILD_HASH__'` token substitution is already in place (line 5). The C9 fix is purely in `pwa.py` + `Dockerfile` — `sw.js` itself is not modified.

---

### `Dockerfile` (config) — C9

**Analog:** self (modify stage 1 RUN block, lines 53-60)

**Current stage 1 RUN** (lines 53-60):
```dockerfile
RUN set -eux; \
    HASH="$(sha256sum app/static/css/tailwind.src.css | cut -c1-8)"; \
    tailwindcss \
      -i app/static/css/tailwind.src.css \
      -o "app/static/css/tailwind.${HASH}.css" \
      --minify; \
    echo "Built: app/static/css/tailwind.${HASH}.css"
```

**C9 addition** — append to the same RUN block (same stage 1):
```dockerfile
RUN set -eux; \
    HASH="$(sha256sum app/static/css/tailwind.src.css | cut -c1-8)"; \
    tailwindcss \
      -i app/static/css/tailwind.src.css \
      -o "app/static/css/tailwind.${HASH}.css" \
      --minify; \
    echo "Built: app/static/css/tailwind.${HASH}.css"; \
    echo "$(date -u +%Y%m%d%H%M%S)" > app/static/build_id.txt; \
    echo "Build ID: $(cat app/static/build_id.txt)"
```

**Stage 2 COPY block** (after line 104 — copy the hashed CSS from stage 1):
```dockerfile
COPY --from=tailwind-builder --chown=app:app /build/app/static/css/tailwind.*.css ./app/static/css/
COPY --from=tailwind-builder --chown=app:app /build/app/static/build_id.txt ./app/static/build_id.txt
```

---

### `scripts/generate_pwa_icons.py` (utility, file-I/O) — C10

**Analog:** self (modify `SRC` constant + harden `circular_crop()`)

**Current SRC and circular_crop** (lines 29, 33-47):
```python
SRC = Path("app/static/img/snobbery-login.jpg")  # BUG: 2816x1536 landscape

def circular_crop(img: Image.Image, size: int) -> Image.Image:
    img = img.convert("RGBA").resize((size, size), Image.LANCZOS)  # BUG: squishes non-square
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size - 1, size - 1), fill=255)
    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    result.paste(img, mask=mask)
    return result
```

**C10 fix:**
```python
SRC = Path("app/static/img/hero.jpg")  # 1021x1021 square — the correct source

def circular_crop(img: Image.Image, size: int) -> Image.Image:
    """Crop the image to a circle with a transparent background.

    Steps:
    1. Center-crop to a square first (defensive — correct even for non-square sources).
    2. Resize the square to (size, size) with LANCZOS resampling.
    3. Apply circular mask.
    """
    # 1. Center-crop to square (no distortion for any aspect ratio).
    w, h = img.size
    min_dim = min(w, h)
    left = (w - min_dim) // 2
    top = (h - min_dim) // 2
    img = img.crop((left, top, left + min_dim, top + min_dim))
    # 2. Resize the square.
    img = img.convert("RGBA").resize((size, size), Image.LANCZOS)
    # 3. Apply circular mask.
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size - 1, size - 1), fill=255)
    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    result.paste(img, mask=mask)
    return result
```

**`maskable_icon()` is unchanged** (lines 50-67 — already handles safe-zone padding + cream-50 background; the center-crop fix propagates through `circular_crop` it calls).

**Outputs regenerated** (lines 72-97): `icon-192.png`, `icon-512.png`, `icon-512-maskable.png`, `apple-touch-icon.png`, `logo-badge.png`. The `snobbery-login-hero.jpg` generation block (lines 93-97) is removed or commented (D-07 says the login hero is NOT regenerated — out of scope).

---

### `app/templates/pages/home.html` + `app/templates/fragments/session_list.html` — C5

**Analog:** `config_hub.html` catalog card link pattern (lines 14-52 — `<a>` with icon + label)

**C5 insertion in `home.html`** — add a "Guided Brew" action button in the header actions div (lines 11-23), alongside the existing "Log session" button:
```html
<div class="flex items-center gap-3">
  {% if request.state.user and request.state.user.is_admin %}
    <a href="/admin" class="...">Admin</a>
  {% endif %}
  <a href="/recipes"
     class="rounded border border-espresso-300 dark:border-espresso-600 px-3 py-1 text-sm font-semibold hover:bg-espresso-100 dark:hover:bg-espresso-800">
    Guided Brew
  </a>
  <a href="/brew/new" class="rounded bg-espresso-700 px-4 py-2 text-base font-semibold text-cream-50 hover:bg-espresso-800 dark:text-cream-50">
    Log session
  </a>
</div>
```

**C5 insertion in `sessions.html`** (lines 17-33, in the header flex div) — add a "Guided Brew" link alongside the existing Export/Import/Log buttons:
```html
<a href="/recipes"
   class="rounded border border-espresso-300 px-4 py-2 text-base text-espresso-800 hover:bg-espresso-50 dark:border-espresso-700 dark:text-cream-200 dark:hover:bg-espresso-900">
  Guided Brew
</a>
```

---

### `app/templates/fragments/recipe_row.html` — C5 (read-only reference for test)

**No change needed.** The `eafc6e3` fix is already in this file (lines 49-60 card mode, lines 103-115 row mode):
```html
{% if recipe.steps %}
  <a href="/brew/guided?recipe_id={{ recipe.id }}"
     class="rounded bg-espresso-700 text-cream-50 px-3 py-1 text-sm min-h-[44px] inline-flex items-center hover:bg-espresso-800">
    Start guided brew
  </a>
{% else %}
  <a href="/recipes/{{ recipe.id }}/edit"
     class="... text-espresso-500 ..."
     aria-label="Start guided brew — add steps to this recipe first">
    Start guided brew
    <span class="ml-1 text-xs opacity-75">(add steps)</span>
  </a>
{% endif %}
```
The C5 regression test reads these exact lines to verify the two branches.

---

### `app/templates/pages/sessions.html` + `app/templates/fragments/session_list.html` — C8

**Analog:** self (remove export/import controls from both files)

**`sessions.html` lines 21-29 to REMOVE** (export/import buttons):
```html
{# REMOVE these two <a> tags: #}
<a id="export-csv-link" href="/brew/export..." class="...">Export CSV</a>
<a href="/brew/import" class="...">Import sessions</a>
```
Keep only "Log session" (`<a href="/brew/new">`) in the sessions header.

**`session_list.html` lines 20-24 to REMOVE** (the OOB export link update):
```html
{# REMOVE: #}
{% if is_fragment %}
<a id="export-csv-link" hx-swap-oob="true" href="/brew/export...">Export CSV</a>
{% endif %}
```
The OOB swap is no longer needed once the export link moves off this page.

---

### Tests (NEW files) — C2, C5, C9

**Analog:** `tests/test_pwa.py` + `tests/routers/test_brew_router.py`

**Test file pattern** (`test_pwa.py` lines 1-20 — imports + docstring + client fixture usage):
```python
from __future__ import annotations

def test_foo(client) -> None:
    r = client.get("/...")
    assert r.status_code == 200
    assert "expected string" in r.text
```

**`tests/routers/test_equipment_create_fragment.py`** (C2 — new file):
```python
"""C2: POST to /equipment and /coffees returns the list fragment, not a <tr> row."""
from __future__ import annotations

def test_equipment_create_returns_list_fragment(authed_client, ...) -> None:
    r = authed_client.post("/equipment", data={...})
    assert r.status_code == 200
    assert "<table" not in r.text  # no bare <tr> dumped into non-table div
    assert "equipment-form-mount" not in r.text  # OOB clear is gone
    # The list fragment container is present:
    assert 'class="hidden md:block"' in r.text or "space-y-3" in r.text
```

**`tests/templates/test_recipe_row.py`** (C5 — new file, template render test):
```python
"""C5: recipe_row.html enabled-vs-no-steps rendering regression test."""
from __future__ import annotations
from jinja2 import Environment

def test_recipe_with_steps_renders_guided_brew_link(templates_env, ...) -> None:
    """recipe_row with steps renders <a href='/brew/guided?recipe_id=...'>"""
    ...

def test_recipe_no_steps_renders_edit_link(templates_env, ...) -> None:
    """recipe_row without steps renders <a href='/recipes/{id}/edit'>"""
    ...
```

**`tests/test_pwa.py` extension** (C9 — extend existing file):
```python
def test_sw_cache_name_is_versioned(client) -> None:
    """GET /sw.js body contains snobbery-v + a non-'dev' hash when build_id.txt exists."""
    r = client.get("/sw.js")
    assert r.status_code == 200
    import re
    match = re.search(r"snobbery-v([A-Za-z0-9]+)", r.text)
    assert match, "SW CACHE_NAME must contain snobbery-v<hash>"
    # In dev environment (no build_id.txt), hash = "dev" — skip assertion.
    # In baked image, hash is a timestamp that is never "dev".
    # (Add pytest.skip guard for CI source-tree runs per memory ci-source-tree-vs-baked-image-divergence)
```

---

## Shared Patterns

### Alpine CSP Component Registration
**Source:** `app/static/js/alpine-components/ios-banner.js` (lines 14-48)
**Apply to:** `dark-toggle.js` (new), cue-control changes in `brew_guided.html`

Mandatory pattern:
1. `document.addEventListener('alpine:init', () => { ... })` wrapper
2. `Alpine.data('componentName', () => ({ ... }))` registration
3. String `x-data="componentName"` reference in HTML (no inline object literals)
4. No `x-model`, no `eval`, no inline arithmetic — use named methods
5. Script tag: `<script defer src="..." nonce="{{ csp_nonce(request) }}"></script>`
6. Load order: BEFORE the `@alpinejs/csp` core script in `base.html`

### localStorage Namespacing
**Source:** `brew-draft.js` line 35, `ios-banner.js` line 24, `guided-brew-mode.js` lines 291/302
**Apply to:** `dark-toggle.js` (new key: `snobbery:theme`)

Pattern: `snobbery:<feature>[:<user_id>]` — all lowercase, colon-delimited, no spaces.

### Nonce'd Inline Script
**Source:** `base.html` line 59 (service worker registration)
**Apply to:** No-FOUC dark mode script (C4 addition to `base.html`)

Pattern:
```html
<script nonce="{{ csp_nonce(request) }}">(function(){ /* synchronous logic */ })();</script>
```
No `defer`. No `async`. Placed in `<head>` before the `<link rel="stylesheet">` tag.

### HTMX Fragment Response (Create → List Swap)
**Source:** `equipment.py` list handler (lines 122-128), `coffee_list.html` (lines 16-50)
**Apply to:** `equipment.py` create handler, `coffees.py` create handler (C2 fix)

Pattern: On successful create, return the full list fragment with `Cache-Control: no-store` implicit (HTMX fragment route). The HTMX form's `hx-target` must point at the list container element, not the form-mount div.

### Error Handling in CRUD Routes
**Source:** `equipment.py` lines 197-207 (ValidationError → 200 + form re-render)
**Apply to:** unchanged — the create routes already implement this; C2 only changes the success branch.

### CSRF on State-Changing Forms
**Source:** `config_hub.html` line 60 / `brew_import.html` line 23
**Apply to:** `data_tools.html` (new import form)

```html
<input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| — | — | — | All files have close analogs in the codebase |

The one genuinely new pattern (C4 `darkMode: 'selector'` in Tailwind v3 + no-FOUC inline script) has no existing analog in the codebase but is fully specified in RESEARCH.md with verified code excerpts.

---

## Metadata

**Analog search scope:** `app/templates/`, `app/routers/`, `app/static/js/alpine-components/`, `app/static/css/`, `app/static/js/`, `scripts/`, `tests/`, `Dockerfile`, `tailwind.config.js`
**Files read:** 23 source files
**Pattern extraction date:** 2026-05-24
**PATTERNS.md location:** `.planning/phases/13-pwa-ux-fixes/13-PATTERNS.md`
