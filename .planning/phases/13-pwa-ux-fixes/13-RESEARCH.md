# Phase 13: PWA UX Fixes - Research

**Researched:** 2026-05-24
**Domain:** Tailwind v3 dark-mode class variant / PWA service-worker cache versioning / iOS safe-area CSS / HTMX fragment patterns
**Confidence:** HIGH for C4 and C9 (verified against live codebase + official docs); MEDIUM for C1 (technique confirmed, on-device verification blocked)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** 3-state Auto/Light/Dark toggle (Auto = default, follow system). Tailwind darkMode: 'media' -> 'class'/'selector'. Persist in localStorage as `snobbery:theme`. No-FOUC nonce'd inline `<head>` script. The two `@media (prefers-color-scheme: dark)` blocks in `tailwind.src.css` must become class-driven. All CSS stays in `tailwind.src.css` (MX-1 lock, no `custom.css`).
- **D-02:** Login + setup pages stay always-dark regardless of toggle (Phase 11 D-14 brand lock).
- **D-03:** Create routes (equipment, coffees) return full list fragment, not the row variant. Form collapses on success.
- **D-04:** Create form collapses/closes on success (not clear-and-stay).
- **D-05:** C5 — Add "Guided Brew" action on Home and Log that routes to `/recipes`. Plus regression test covering `recipe_row.html` enabled-vs-no-steps rendering.
- **D-06:** C8 — Move CSV Export + Import to a dedicated page linked from the config-hub account section. Routes `/brew/export` + `/brew/import` are UNCHANGED — only the entry-point moves.
- **D-07:** C10 — Regenerate circular badge + PWA icons from `app/static/img/hero.jpg` (1021x1021 square). Harden `circular_crop()` to center-crop-square-first then resize then mask. Full mascot in circle (not zoomed to bean face). Regenerate: `logo-badge.png`, `icon-192.png`, `icon-512.png`, `icon-512-maskable.png`, `apple-touch-icon.png`. Login hero untouched.

### Claude's Discretion (defaults already set in CONTEXT.md)
- **C1:** `env(safe-area-inset-top)` padding on mobile top strip + any sticky top chrome, mirroring bottom-nav fix. UNVERIFIED on-device.
- **C3:** Equipment card fields grouped as flex-wrap pills (copy coffee card pattern).
- **C6:** Replace confusing `role="switch"` toggles on guided-brew page with clearly-labeled on/off controls. Preserve `snobbery:gbm:cues` localStorage prefs.
- **C7:** Alpine `effect`/watcher on dose+water for ratio recalc on programmatic prefill. Rating stars fit single line at 375px.
- **C9:** SW cache version must bump per deploy. Root-cause: hash is computed from `tailwind.src.css` content — doesn't change when templates or Python routes change. Fix: inject a build-time version constant that changes per Docker build.

### Deferred Ideas (OUT OF SCOPE)
- `hero-alt.jpg` (1149x1149) — unused alternate; ignore or delete.
- `brew_time_seconds` analytics surfacing.
- Per-user settings/preferences page.
- On-device safe-area verification — must be checked on real iPhone by John.
</user_constraints>

---

## Summary

Phase 13 is post-UAT polish on an established codebase. The per-criterion root causes and file:line targets are already fully known from the CONTEXT.md investigation. This research focuses on three genuinely uncertain external mechanics:

**C4 (dark-mode class variant)** requires a correct understanding of the _actual_ Tailwind version in use. The Dockerfile and `tailwind.config.js` confirm the project runs **Tailwind v3.4.17** (standalone CLI), NOT v4. The `@custom-variant dark` syntax from Tailwind v4 does NOT apply. The v3 fix is: change `darkMode: 'media'` to `darkMode: 'selector'` (preferred in v3.4.1+) in `tailwind.config.js`, rewrite the two hand-written `@media (prefers-color-scheme: dark)` blocks in `tailwind.src.css` to `.dark` selectors, and add a nonce'd no-FOUC inline script to `<head>` of `base.html`. The Tailwind `dark:` utilities on `<body>` and all other elements already key off whatever strategy is configured — changing config is sufficient for those.

**C9 (SW cache versioning)** root cause is that `pwa.py` computes `_BUILD_HASH` from `sha256sum app/static/css/tailwind.src.css` at module load. When a Docker rebuild happens without changing `tailwind.src.css` (e.g., only a template or Python route changed), the hash is identical, the SW cache name stays `snobbery-v<same-hash>`, and the new SW's activate-event sees no old caches to purge — PWA users get the stale shell. The fix is to inject a build-time version constant that changes on every `docker compose build`, such as a `BUILD_TIMESTAMP` ARG/ENV in the Dockerfile or a pre-generated `app/static/build_id.txt` file written unconditionally in the Dockerfile RUN step.

**C1 (safe-area-inset-top)** mirrors the bottom-nav technique from `982c0e6`. The CSS pattern (`padding-top: env(safe-area-inset-top)`) on the mobile top strip is correct; the technique is unverifiable off-device.

**Primary recommendation:** Fix C9 first (it gates whether any other fix reaches installed PWAs), implement C4 as a single atomic change (config + CSS rewrite + no-FOUC script + Alpine component), then proceed with C1/C2/C3/C5/C6/C7/C8/C10 in dependency order.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Dark mode class toggle (C4) | Browser/Client | Frontend Server (Dockerfile build) | localStorage + `classList` is client-side; Tailwind compile is build-time |
| No-FOUC pre-paint script (C4) | Frontend Server (Jinja) | Browser/Client | Script tag must carry request nonce — Jinja renders it |
| SW cache versioning (C9) | Docker build | Frontend Server (pwa.py) | Version constant must be injected at build time, not runtime |
| iOS safe-area padding (C1) | Browser/Client | Static CSS | Pure CSS `env()` variable; no server involvement |
| HTMX fragment returns (C2) | API/Backend | Browser/Client | Route handler decides which fragment to return |
| Equipment card layout (C3) | Browser/Client | — | Pure Jinja template + Tailwind classes |
| Guided Brew entry link (C5) | Browser/Client | API/Backend | Entry link in templates; regression test in pytest |
| Export/Import relocation (C8) | API/Backend + Frontend | — | New route/page + entry point removal in existing routes |
| Icon regeneration (C10) | Build artifacts | — | Python script run once and committed; no server involvement |

---

## LOAD-BEARING FINDING: Tailwind Version is v3, NOT v4

**This is the most important discovery in this research.**

The CONTEXT.md, CLAUDE.md, and comments in `tailwind.src.css` say "Tailwind v4" but the Dockerfile is authoritative:

```dockerfile
ARG TAILWIND_VERSION=v3.4.17
```

The config file (`tailwind.config.js`) uses `module.exports = { darkMode: 'media', ... }` — this is **Tailwind v3 JS-config syntax**. Tailwind v4 uses CSS-first config (`@import "tailwindcss"; @custom-variant dark ...`) with no `tailwind.config.js`.

**Implication for C4:** The `@custom-variant dark (&:where(.dark, .dark *))` syntax documented in the CONTEXT.md is Tailwind v4 syntax and will NOT work with the v3.4.17 standalone CLI. The correct v3 approach is different (see Standard Stack section below).

[VERIFIED: Dockerfile line 25 `ARG TAILWIND_VERSION=v3.4.17`; tailwind.config.js `module.exports = { darkMode: 'media'... }`]

---

## Standard Stack

### Core (no changes for Phase 13)
| Library | Version | Relevance | Note |
|---------|---------|-----------|------|
| Tailwind CSS | v3.4.17 (standalone CLI) | C4 dark mode | `darkMode: 'selector'` in `tailwind.config.js` |
| Alpine.js | @alpinejs/csp 3.15.12 | C4/C6 toggle components | No `x-model`; use `:value` + `@input` pattern |
| HTMX | 2.0.10 | C2/C7 fragment swap | Existing SWR-cached static assets |
| FastAPI/Jinja2 | per CLAUDE.md | C4 nonce'd script | `csp_nonce(request)` in template |

### No New Dependencies Required
All Phase 13 changes use existing libraries. No new pip packages or CDN scripts are needed.

---

## Architecture Patterns

### System Architecture Diagram

```
User browser (iOS PWA installed)
       |
       | HTTP request
       v
NGINX Proxy Manager (VPS) --> FastAPI/Uvicorn
                                    |
                         [Jinja2 renders base.html]
                                    |
                         [nonce'd <head> scripts]
                                    |
                         [Tailwind v3 compiled CSS]
                                    |
                              Browser renders
                                    |
                    [SW intercepts subsequent navigations]
                                    |
              [stale-while-revalidate static / network-first dynamic]
```

**SW cache invalidation flow (C9 fix):**
```
docker compose build
    |
    [Dockerfile RUN: write build_id.txt with current timestamp/SHA]
    |
    [pwa.py module load: read build_id.txt -> _BUILD_HASH]
    |
    [GET /sw.js: returns sw.js with new CACHE_NAME]
    |
    [Browser: new SW installs with new cache name]
    |
    [SW activate: caches.keys().filter(k != CACHE_NAME).map(delete)]
    |
    [Old shell purged; new shell served]
```

### Pattern 1: Tailwind v3 `darkMode: 'selector'`

**What:** Change `darkMode: 'media'` to `darkMode: 'selector'` in `tailwind.config.js`. This makes all `dark:` utility classes key off the presence of a `.dark` class on any ancestor element (conventionally `<html>`).

**v3.4.1+ note:** `'selector'` replaced `'class'` as the canonical value in v3.4.1. Both still work in v3.4.17; `'selector'` is preferred. Behavior is identical: `dark:` variants activate when `.dark` is present on `<html>` or any ancestor.

```js
// tailwind.config.js — change one line
module.exports = {
  // ...
  darkMode: 'selector',  // was: 'media'
  // ...
};
```

[VERIFIED: v3.tailwindcss.com/docs/dark-mode; Tailwind v3.4.1 changelog]
[VERIFIED: tailwindcss.com/docs/dark-mode — same 3-state toggle JS pattern applies to both v3 selector and v4 @custom-variant]

### Pattern 2: Rewrite hand-written `@media` blocks to `.dark` selectors

The two `@media (prefers-color-scheme: dark)` blocks in `tailwind.src.css` (lines 88-97 and 111-116) are independent of Tailwind's `dark:` variant system. When `darkMode: 'selector'` is active, the `dark:` utilities respond to the `.dark` class — but these raw `@media` blocks still fire on system preference regardless of class, defeating an explicit "Light" override.

**Fix:** Replace both blocks with `.dark` class-scoped selectors:

```css
/* BEFORE (tailwind.src.css lines 88-97): */
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

/* AFTER: */
.dark input, .dark select, .dark textarea {
  color: #F4EFE6;
  background-color: #21150C;
  border-color: #3D2817;
}
.dark input::placeholder, .dark textarea::placeholder {
  color: #DACBAE;
}
```

```css
/* BEFORE (tailwind.src.css lines 111-116): */
@media (prefers-color-scheme: dark) {
  a { color: #E3D5C9; }
  a:hover { color: #F4EFE6; }
}

/* AFTER: */
.dark a { color: #E3D5C9; }
.dark a:hover { color: #F4EFE6; }
```

These rules live inside `@layer base` — the `.dark` selector still works correctly inside a `@layer` block in Tailwind v3.

[VERIFIED: Official Tailwind v3 dark mode docs confirm hand-written @media blocks conflict with class-based toggle and must be rewritten as class-scoped selectors]
[ASSUMED: `.dark` selectors inside `@layer base` behave identically to @media blocks inside `@layer base` in Tailwind v3 specificity. This is standard CSS and expected to work correctly, but not explicitly cited in one spot from official docs.]

### Pattern 3: No-FOUC inline script in `base.html` `<head>`

The script must:
1. Run synchronously (before first paint) — so `defer` is NOT used
2. Carry the CSP nonce — because `unsafe-inline` is forbidden in `script-src`
3. Be eval-free — no `eval()`, no `new Function()` (ADR 0001)
4. Set `.dark` on `<html>` based on `localStorage.snobbery:theme` or `matchMedia`

```html
{# No-FOUC dark mode class — runs synchronously, before first paint.
   Must appear before the Tailwind CSS link to prevent FOUC.
   Nonce required by strict CSP (ADR 0001). #}
<script nonce="{{ csp_nonce(request) }}">
(function(){
  var t = localStorage.getItem('snobbery:theme');
  if (t === 'dark' || (t === null && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
    document.documentElement.classList.add('dark');
  }
})();
</script>
```

**Placement:** Must appear in `<head>` BEFORE the `<link rel="stylesheet">` tag to prevent FOUC. The current service worker registration inline script (line 59) shows the established pattern for nonce'd inline scripts in this project.

**CSP compatibility:** `script-src 'self' 'nonce-{nonce}'` in `CSP_TEMPLATE` permits inline scripts with the correct nonce. `style-src-attr 'unsafe-inline'` does NOT cover inline `<script>` tags — the nonce is mandatory.

**Login / setup exemption (D-02):** The login and setup pages use their own templates, not base.html-derived pages with the auth nav. Check whether login.html extends base.html or is standalone. If it extends base.html, the no-FOUC script fires on login too — but login is always-dark (espresso-950 background) so FOUC is not an issue even if `.dark` is incorrectly set or cleared. The dark: utilities on login are always active through the system preference fallback when `snobbery:theme` is null and system is dark, or not active when system is light — which is the correct behavior for login (stays dark by design via template hardcoding, not via the `.dark` class mechanism).

[VERIFIED: ADR 0001 — CSP template, nonce mechanism, inline script pattern]
[VERIFIED: tailwindcss.com/docs/dark-mode — FOUC prevention pattern with localStorage + matchMedia]

### Pattern 4: Alpine dark-toggle component

A new Alpine CSP component (`dark-toggle.js`) handles the 3-state UI. The toggle component:
- Reads `localStorage.getItem('snobbery:theme')` on init to set button state
- On Auto: `localStorage.removeItem('snobbery:theme')` + `classList` based on `matchMedia`
- On Light: `localStorage.setItem('snobbery:theme', 'light')` + `classList.remove('dark')` on `<html>`
- On Dark: `localStorage.setItem('snobbery:theme', 'dark')` + `classList.add('dark')` on `<html>`

Follows the existing `Alpine.data('darkToggle', () => ({ ... }))` registration pattern.

**No `x-model`** (not available in CSP build). Use `:value` + `@input` or `x-on:click` on individual buttons per ADR 0001.

### Pattern 5: SW cache version — build-time injection

**Root cause confirmed:** `pwa.py:_get_build_hash()` globs `app/static/css/tailwind.*.css` and takes `sha256sum` of `tailwind.src.css` in the Dockerfile. The hash reflects source CSS content only. A rebuild that only changes templates or Python files produces an identical hash → no cache purge on installed PWAs.

**Fix approach — write `app/static/build_id.txt` in the Dockerfile:**

```dockerfile
# In Stage 1 (tailwind-builder), after the Tailwind CSS build:
RUN echo "$(date -u +%Y%m%d%H%M%S)" > app/static/build_id.txt
```

Then in Stage 2 (runtime), COPY the file:
```dockerfile
COPY --from=tailwind-builder /build/app/static/build_id.txt ./app/static/build_id.txt
```

Then update `pwa.py:_get_build_hash()`:
```python
def _get_build_hash() -> str:
    # Try build_id.txt first (written unconditionally on every docker build)
    build_id_path = Path("app/static/build_id.txt")
    if build_id_path.exists():
        return build_id_path.read_text(encoding="utf-8").strip()[:12]
    # Fallback: hash from Tailwind CSS filename (dev environment)
    css_dir = Path("app/static/css")
    candidates = sorted(p for p in css_dir.glob("tailwind.*.css") if p.name != "tailwind.src.css")
    if candidates:
        return candidates[0].stem.split(".", 1)[1]
    return "dev"
```

**Alternative approach** — use a build ARG:
```dockerfile
ARG BUILD_ID
ENV BUILD_ID=${BUILD_ID:-dev}
```
But this requires passing `--build-arg BUILD_ID=$(date +%s)` on every build, which is error-prone. The `build_id.txt` approach is unconditional and requires no operator discipline.

**Verification:** After rebuild, `docker compose exec coffee-snobbery cat /app/static/build_id.txt` should show a new timestamp. `curl http://localhost:8000/sw.js | grep CACHE_NAME` should show a different cache name than before.

[VERIFIED: pwa.py source code — _get_build_hash() implementation; Dockerfile — hash derivation from sha256sum tailwind.src.css]
[CITED: MDN Service Worker API/Using_Service_Workers — SW lifecycle, skipWaiting, clients.claim, activate-event cache purge]

### Pattern 6: iOS safe-area-inset-top (C1)

Mirror the bottom-nav technique from `982c0e6`. The mobile top strip (`div.md:hidden` at base.html line 164) needs `pt-[env(safe-area-inset-top)]` or equivalent. With `viewport-fit=cover` (already set in `<meta name="viewport">`), the CSS env variable is nonzero on notch/Dynamic Island devices in standalone mode.

```html
{# base.html mobile top strip — add safe-area top padding #}
<div class="md:hidden flex h-14 px-4 items-center ... pt-[env(safe-area-inset-top)]">
```

Or via a CSS rule in `tailwind.src.css` (outside `@layer` to prevent purge):
```css
.top-safe-area { padding-top: env(safe-area-inset-top); }
```

**The `h-14` height may be too short** once the safe-area padding is added — the strip total height becomes `3.5rem + safe-area-inset-top (~50px on iPhone 14 Pro)`. Either increase the base height (e.g., `h-auto min-h-14`) or use `calc(3.5rem + env(safe-area-inset-top))` for `min-height`.

**Unverified:** The bottom-nav technique (`982c0e6`) is itself unverified on-device (memory `snobbery-safe-area-fix-unverified`). This approach reuses the same pattern — if the bottom fix is confirmed to work, this will too. If neither works, both need a revised approach.

[ASSUMED: The technique is correct per CSS spec and standard MDN guidance. Unverifiable without real iOS hardware. Confidence: MEDIUM.]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Dark mode FOUC prevention | Custom localStorage polling after paint | Synchronous inline `<head>` script (no library needed) | Only synchronous pre-paint execution prevents flash |
| SW cache invalidation | Complex message-passing between SW and page | Simple CACHE_NAME change + activate-event purge (already in sw.js) | The existing pattern is correct; just fix the hash source |
| Tailwind dark class switching | Custom CSS-in-JS | `darkMode: 'selector'` in config + `.dark` class on `<html>` | Tailwind already handles this |

---

## Common Pitfalls

### Pitfall 1: Using Tailwind v4 `@custom-variant` syntax with v3 CLI
**What goes wrong:** CONTEXT.md mentions `@custom-variant dark (&:where(.dark, .dark *))` — this is v4 CSS-first syntax. Adding it to `tailwind.src.css` while using the v3.4.17 CLI will produce a CSS parse error or be silently ignored, breaking the entire stylesheet.
**Why it happens:** The project comments say "Tailwind v4" but the actual CLI is v3.4.17.
**How to avoid:** Use `darkMode: 'selector'` in `tailwind.config.js` (one-line change). The v3 CLI reads `tailwind.config.js`; it does NOT read CSS-first `@custom-variant` directives.
**Warning signs:** If the compiled CSS is unexpectedly small or all `dark:` utilities disappear after changing `tailwind.src.css` to add `@custom-variant`, the v4 syntax was applied to the v3 CLI.

### Pitfall 2: SW hash unchanged after rebuild
**What goes wrong:** A Docker rebuild without changing `tailwind.src.css` produces the same CSS hash → same CACHE_NAME → no cache purge → installed PWA users still see the old shell.
**Why it happens:** `_get_build_hash()` hashes the _source_ CSS, not a build timestamp. The source is stable unless `tailwind.src.css` is edited.
**How to avoid:** Write `build_id.txt` with a fresh timestamp in the Dockerfile `RUN` step (unconditional, not gated on CSS changes).

### Pitfall 3: No-FOUC script without `nonce` fails silently
**What goes wrong:** An inline `<script>` without `nonce="{{ csp_nonce(request) }}"` is blocked by `script-src 'nonce-...'` CSP policy. The browser's DevTools console shows a CSP violation. The `.dark` class is never set pre-paint → FOUC on every page load for dark-preference users.
**Why it happens:** The strict CSP (`SecurityHeadersMiddleware`) blocks all inline scripts that lack the current request's nonce.
**How to avoid:** Always carry `nonce="{{ csp_nonce(request) }}"` on inline `<script>` tags. See line 59 of base.html for the existing service worker registration script as the reference pattern.

### Pitfall 4: No-FOUC script with `defer` attribute
**What goes wrong:** Adding `defer` to the no-FOUC script causes it to execute after DOM parsing completes — which is AFTER the browser has already rendered the first frame. FOUC occurs.
**Why it happens:** `defer` is appropriate for most scripts (including Alpine components) but defeats the purpose of the no-FOUC script.
**How to avoid:** The no-FOUC script must be synchronous (no `defer`, no `async`). Place it early in `<head>`, ideally before the Tailwind CSS `<link>` tag.

### Pitfall 5: Dark toggle on login/setup pages causes unexpected behavior
**What goes wrong:** Login and setup pages extend `base.html` (confirmed — login at `app/templates/pages/login.html` likely). The no-FOUC script will run and potentially set or clear `.dark` on `<html>` for these pages too. If login's dark styling relies entirely on `dark:` Tailwind utilities (not hardcoded dark palette), it might flash light for Auto/Light users whose system is light-preferring.
**Why it happens:** D-02 says login stays always-dark, but "always-dark" is implemented via the template's use of espresso-950 background (hardcoded, not `dark:` variant). So the no-FOUC script's class toggling is irrelevant for login.
**How to avoid:** Confirm login/setup background is hardcoded dark (`bg-espresso-950` not `bg-cream-50 dark:bg-espresso-950`). If it's already hardcoded, the no-FOUC script on login is a no-op in terms of visual appearance.

### Pitfall 6: `h-14` top strip too short with safe-area-inset-top padding (C1)
**What goes wrong:** The mobile top strip is `h-14` (56px). Adding `pt-[env(safe-area-inset-top)]` (up to ~59px on iPhone 14 Pro Dynamic Island) means logo and content are pushed down further than the strip height, clipping the content or expanding the strip unexpectedly.
**Why it happens:** Fixed height doesn't accommodate variable safe-area inset.
**How to avoid:** Switch to `min-h-14` + auto height, or use `calc(3.5rem + env(safe-area-inset-top))` for explicit height. The main content's `pt-14` spacer needs to match.

### Pitfall 7: Old caches not purged if `skipWaiting` is missing
**What goes wrong:** If `self.skipWaiting()` is removed from the install handler, the new SW waits for all tabs to close before activating. On iOS standalone, the user never "closes" the app — the old SW stays active indefinitely and the new cache name is never activated.
**Why it happens:** Default SW waiting behavior.
**How to avoid:** The existing `sw.js` already has `self.skipWaiting()` in the install handler and `self.clients.claim()` in the activate handler. Preserve both when modifying `sw.js`.

### Pitfall 8: Maskable icon safe-zone
**What goes wrong:** Regenerating the maskable icon (`icon-512-maskable.png`) without the 10% safe-zone padding causes Android to crop visible content (the mascot) in circle/squircle masks.
**Why it happens:** Android launchers apply their own geometric mask to the icon and clip anything outside the safe zone.
**How to avoid:** The existing `generate_pwa_icons.py` already handles maskable padding. When hardening `circular_crop()`, preserve the existing padding logic for the maskable variant.

---

## Code Examples

### Dark mode — tailwind.config.js change
```js
// Source: v3.tailwindcss.com/docs/dark-mode
module.exports = {
  darkMode: 'selector',  // change from 'media'
  // ... rest unchanged
};
```

### Dark mode — no-FOUC inline script (base.html)
```html
{# Source: tailwindcss.com/docs/dark-mode + ADR 0001 (nonce requirement) #}
<script nonce="{{ csp_nonce(request) }}">(function(){
  var t = localStorage.getItem('snobbery:theme');
  if (t === 'dark' || (t === null && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
    document.documentElement.classList.add('dark');
  }
})();</script>
```

### Dark mode — Alpine toggle component skeleton
```js
// Source: ADR 0001 (Alpine CSP registration pattern)
// app/static/js/alpine-components/dark-toggle.js
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
    }
  };
});
```

### SW build_id.txt — Dockerfile addition
```dockerfile
# Source: verified against pwa.py _get_build_hash() + Dockerfile structure
# In Stage 1 (tailwind-builder), after the Tailwind CSS build RUN:
RUN echo "$(date -u +%Y%m%d%H%M%S)" > app/static/build_id.txt

# In Stage 2 (runtime), in the COPY block:
COPY --from=tailwind-builder /build/app/static/build_id.txt ./app/static/build_id.txt
```

### SW _get_build_hash() — updated pwa.py
```python
# Source: verified against current pwa.py implementation
def _get_build_hash() -> str:
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

## Runtime State Inventory

Phase 13 involves no renaming, refactoring, or migration. No runtime state inventory required.

---

## Environment Availability

Step 2.6: SKIPPED for most criteria (pure code/template/CSS changes, no external tools beyond Docker).

**C10 icon regeneration** requires Python Pillow in the development environment to run `scripts/generate_pwa_icons.py`. The generated PNGs are committed (D-15 workflow) — not a runtime dependency.

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Pillow | C10 icon gen (dev-time) | [assumed ✓ — project dep] | >=12.2 | Install: `pip install Pillow` |
| hero.jpg | C10 source | ✓ | 1021x1021 px | — |

---

## Validation Architecture

Nyquist validation is enabled. Map each criterion to test approach.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.x (installed into container) |
| Config file | `pyproject.toml` (pytest section) |
| Quick run command | `docker compose exec coffee-snobbery python -m pytest tests/test_pwa.py tests/routers/test_gbm.py -q` |
| Full suite command | `docker compose exec coffee-snobbery python -m pytest -q` |

### Phase Requirements (Criterion) to Test Map

| Criterion | Behavior | Test Type | Automated Command | File Exists? |
|-----------|----------|-----------|-------------------|-------------|
| C2 create-route | Create equipment/coffee returns list fragment (not row) | unit/route | `pytest tests/routers/test_brew_router.py -k equipment_create -x` (new test needed) | ❌ Wave 0 |
| C5 recipe_row regression | `recipe_row.html` with steps -> `<a href=/brew/guided>`, no steps -> `<a href=/recipes/{id}/edit>` | template/integration | `pytest tests/templates/ -k recipe_row -x` (new test file needed) | ❌ Wave 0 |
| C9 SW cache version | `GET /sw.js` response body contains `snobbery-v` + a version that differs from `"dev"` when running from a Docker image | route | `pytest tests/test_pwa.py::test_sw_cache_name_is_versioned -x` (extend existing) | ❌ Wave 0 |
| C9 SW activate purge | SW activate handler deletes old caches | JS static analysis | Verify `caches.keys().filter(k !== CACHE_NAME).map(delete)` pattern in sw.js | ✅ (exists) |
| Manifest icons | icon-192/512/maskable/apple-touch all reachable | route | `pytest tests/test_pwa.py` (already covers manifest; add icon-file-existence check) | ✅ (partial) |

### C4 Dark Mode — Not Pytest-Testable in Full

| Sub-criterion | Test Type | Approach |
|---------------|-----------|----------|
| `dark:` utilities active with `.dark` on `<html>` | Visual | Manual DevTools: add `.dark` to `<html>`, confirm `bg-espresso-950` applies |
| No FOUC | Visual | Manual: slow 3G throttle, hard reload, observe flash |
| No-FOUC script carries nonce | Unit | `pytest tests/ci/test_no_unsafe_jinja.py` (existing CSP checks); add grep for `nonce=` on the no-FOUC script tag |
| Light override on dark system | Manual/Device | Set system to dark, choose Light in toggle, confirm light palette |
| Login stays dark | Visual | `pytest` can assert `dark:` classes absent from login template's `<body>` if login is hardcoded |

### Criteria with No Automated Test (Manual-only)

| Criterion | Why Manual | Validation Approach |
|-----------|-----------|---------------------|
| C1 safe-area-inset-top | Requires real iOS device; `env()` = 0 in Playwright | John verifies on-device after deploy |
| C3 equipment card height | Visual 375px layout | Playwright smoke at 375px (existing e2e) OR manual DevTools |
| C4 FOUC + dark toggle visual | Timing-sensitive; theme-color behavior | Manual — see above |
| C6 cue control redesign | Interaction + localStorage | Manual smoke on guided-brew page |
| C7 ratio recalc + star wrap | Alpine computed values + layout | Manual brew form at 375px |
| C8 Export/Import location | UI/navigation | Manual — navigate to config hub, confirm export link present |
| C10 icon visual | Image content | Manual visual check of generated PNGs |

### Wave 0 Gaps (test files to create)

- [ ] `tests/routers/test_equipment_create_fragment.py` — C2: POST to equipment create returns list fragment, not `<tr>` row. Covers the coffees create route too.
- [ ] `tests/templates/test_recipe_row.py` — C5: Template rendering test. `recipe_row.html` with steps renders `<a href="/brew/guided?recipe_id=...">`. Without steps renders `<a href="/recipes/{id}/edit">` (the `eafc6e3` fix). This is the mandated regression test.
- [ ] Extend `tests/test_pwa.py` with `test_sw_cache_name_is_versioned()` — C9: Assert `GET /sw.js` body contains `snobbery-v` followed by something other than `dev` (in the baked container). This test will fail in dev (no baked `build_id.txt`) — document the skip guard.

### Sampling Rate
- **Per task commit:** `docker compose exec coffee-snobbery python -m pytest tests/test_pwa.py -q`
- **Per wave merge:** `docker compose exec coffee-snobbery python -m pytest -q`
- **Phase gate:** Full suite green + C9 verification (cache name changes between two builds) before `/gsd-verify-work`

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|-----------------|--------|
| Tailwind v3 `darkMode: 'class'` | Tailwind v3 `darkMode: 'selector'` (since v3.4.1) | Identical behavior; `'selector'` is canonical in v3.4.x |
| SW cache version = CSS source hash | SW cache version = build timestamp (unconditional per build) | Ensures cache busts on every deploy, not just CSS edits |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `.dark` selectors inside `@layer base` work correctly in Tailwind v3 (same specificity behavior as `@media` blocks inside `@layer base`) | Pattern 2 | Tailwind v3 `@layer` ordering might affect specificity differently; would need to move rules outside `@layer` |
| A2 | Login page extends `base.html` (and thus will receive the no-FOUC script) | Pitfall 5 | If login is fully standalone, the no-FOUC script comment about login is moot — no change needed |
| A3 | The `env(safe-area-inset-top)` technique works in iOS standalone PWA (C1) | Pattern 6 | Unverifiable off-device; technique matches CSS spec but the bottom-nav fix itself is also unverified on-device |
| A4 | `docker build` is always `docker compose build coffee-snobbery` — not a bare `docker pull` of a pre-built image | C9 fix | If team ever pulls a pre-built image, `build_id.txt` is stale; timestamp approach is still better than CSS hash |
| A5 | Pillow is available in the dev environment for running `generate_pwa_icons.py` | C10 | Minor — install with `pip install Pillow` if absent |

---

## Open Questions

1. **Does login.html extend base.html?**
   - What we know: CONTEXT.md references `base.html` as the template for nav + scripts; login is always-dark.
   - What's unclear: Whether the no-FOUC script fires on login.
   - Recommendation: Planner reads login.html before the C4 plan task. If login extends base.html, the no-FOUC script fires but is visually irrelevant (login is always hardcoded dark). If it's standalone, no change to login.

2. **Should `build_id.txt` include the git commit SHA instead of (or in addition to) a timestamp?**
   - What we know: Timestamps are unconditional but non-deterministic across parallel builds. Git SHAs are deterministic but require `git` in the build image.
   - What's unclear: Whether the Dockerfile builder stage has git available.
   - Recommendation: Use timestamp (simple, always available in Debian bookworm-slim stage 1). Can be enhanced to include git SHA later.

3. **`darkMode: 'class'` vs `'selector'` in tailwind.config.js**
   - What we know: Both work in v3.4.17; `'selector'` is the canonical name since v3.4.1.
   - What's unclear: Whether the standalone CLI binary respects both values identically.
   - Recommendation: Use `'selector'` per official v3 docs. If it doesn't work (rare edge case with the binary), fall back to `'class'`.

---

## Project Constraints (from CLAUDE.md)

- **Stack invariants:** Tailwind standalone CLI (no npm), no custom.css (MX-1), Alpine CSP build only, no eval.
- **Mobile-first:** All UI changes tested at 375px viewport.
- **Security:** CSRF on all state-changing forms; CSP nonce on all scripts; no `unsafe-inline` in script-src.
- **PWA invariants:** Don't break manifest, SW, or install flow. C9 fix must not remove `skipWaiting` or `clients.claim`.
- **Template rebuild required:** No bind-mount; changes require `docker compose build coffee-snobbery && docker compose up -d coffee-snobbery`.
- **Commits:** Conventional commits (`feat:`, `fix:`, `chore:`); work on `main` for small changes.
- **Dark mode architectural invariant:** `snobbery:theme` in localStorage (like `snobbery:gbm:cues` pattern).

---

## Security Domain

> `security_enforcement` not explicitly false — included.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | No auth changes |
| V3 Session Management | No | No session changes |
| V4 Access Control | No | No new routes with auth |
| V5 Input Validation | Partial | New export/import page reuses existing validated routes |
| V6 Cryptography | No | No encryption changes |
| V7 Error Handling | No | — |

### Phase 13 Specific Security Notes

| Pattern | Risk | Mitigation |
|---------|------|------------|
| No-FOUC inline script | Must carry nonce | Template: `nonce="{{ csp_nonce(request) }}"` — same as service worker reg script |
| New Alpine component files | Must be `'self'`-served, nonce-tagged `<script defer>` | Follow existing component pattern in base.html |
| New export/import dedicated page | Must carry CSRF token | Reuse existing `brew/export` + `brew/import` routes — CSRF already enforced there |
| SW cache version change | No security impact | The CACHE_NAME is a cache key, not a secret |
| `localStorage.snobbery:theme` | No sensitive data | Theme preference is non-sensitive; no encryption needed |

---

## Sources

### Primary (HIGH confidence)
- Dockerfile (`TAILWIND_VERSION=v3.4.17`) — verified actual Tailwind version in use
- `tailwind.config.js` (`darkMode: 'media'`, JS-config format) — confirms v3 config style
- `app/static/css/tailwind.src.css` — the two `@media (prefers-color-scheme: dark)` blocks to rewrite
- `app/routers/pwa.py` (`_get_build_hash()` implementation) — confirmed C9 root cause
- `app/static/js/sw.js` — confirmed existing `skipWaiting` + `clients.claim` + activate purge pattern
- `app/templates/base.html` — confirmed CSP nonce pattern, script ordering, `<html>` tag, mobile top strip structure
- [tailwindcss.com/docs/dark-mode](https://tailwindcss.com/docs/dark-mode) — official dark mode docs (class toggle, FOUC prevention script, localStorage pattern)
- [v3.tailwindcss.com/docs/dark-mode](https://v3.tailwindcss.com/docs/dark-mode) — v3-specific `darkMode: 'selector'` docs
- [MDN Using Service Workers](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API/Using_Service_Workers) — SW lifecycle, skipWaiting, clients.claim, activate cache purge

### Secondary (MEDIUM confidence)
- WebSearch results confirming `'selector'` replaced `'class'` in Tailwind v3.4.1
- ADR 0001 (`docs/decisions/0001-csp-strict-no-unsafe-eval.md`) — CSP template, nonce requirements, Alpine CSP build constraints

### Tertiary (LOW confidence / assumptions flagged)
- Assumption A1: `.dark` selectors work correctly inside Tailwind `@layer base`
- Assumption A2: login.html extends base.html

---

## Metadata

**Confidence breakdown:**
- C9 root cause + fix: HIGH — code verified against live source; SW lifecycle from MDN
- C4 Tailwind v3 config approach: HIGH — official docs + live Dockerfile/config
- C4 no-FOUC script: HIGH — official Tailwind docs + CSP constraints from ADR 0001
- C1 safe-area technique: MEDIUM — CSS spec correct; unverifiable on-device
- C2/C3/C5/C6/C7/C8/C10: already fully specified in CONTEXT.md; no additional research needed

**Research date:** 2026-05-24
**Valid until:** 2026-06-24 (stable stack; library versions locked)
