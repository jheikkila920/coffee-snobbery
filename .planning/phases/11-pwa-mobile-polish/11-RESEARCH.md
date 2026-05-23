# Phase 11: PWA + Mobile Polish — Research

**Researched:** 2026-05-23
**Domain:** PWA installability, service workers, Wake Lock API, Guided Brew Mode, mobile-first layout polish
**Confidence:** HIGH (platform APIs verified against MDN/caniuse/WebKit release notes; library versions verified against npm registry; codebase patterns verified by direct file read)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Navigation frame (MOB-01, MOB-02):**
- D-01: Four-tab bottom nav (<768px) / top horizontal nav (>=768px). Tabs: Home / Log / Config / Admin. Admin hidden for non-admins. `env(safe-area-inset-bottom)` required.
- D-02: Absorb Phase 10 search header into nav frame. Search stays auth-gated.
- D-03: Config tab = catalog hub landing. Account + sign-out at the bottom of this hub on mobile.
- D-04: AI pages (wishlist, paste-and-rank) stay on Home. Not promoted to nav tabs.
- D-05: Desktop identity + sign-out = Alpine CSP accountDropdown (top-right). Sign-out is a CSRF-protected POST form button, NOT a plain link.
- D-06: Log tab → sessions list (`/brew`) + sticky "+ Log brew" button. History primary.

**Guided Brew Mode (BREW-12, BREW-13):**
- D-07: Two entry points — brew-log form (coffee+recipe selected) and recipe detail page (recipe only). "Done brewing" prefills session form accordingly.
- D-08: Auto-advance on step time offset + manual "Next step" skip.
- D-09: Chime on/off + vibration on/off in localStorage (`snobbery:gbm:cues`). Live in-brew toggle too.
- D-10: Add `brew_time_seconds` (nullable int) to `brew_sessions`. Additive migration. `brew_time_seconds` is user-editable on session form.
- D-11: Wake lock + iOS fallback — prototype on real iPhone before declaring done (carried research flag).

**Branding / install assets (UX-01..04, MOB-09, MOB-11):**
- D-12: Circular mascot badge = logo AND PWA icon. Same badge for both.
- D-13: Login = centered mascot hero + form card below.
- D-14: Login page is ALWAYS dark (espresso-950), regardless of system preference.
- D-15: Pre-generate + check in derived assets via one-time Pillow script. No runtime generation.
- D-16: Palette / dark mode largely shipped. UX-02 strings LOCKED: `name="Snobbery — Coffee Log"`, `short_name="Snobbery"`, `description="Self-hosted coffee log for households who take pour-over seriously"`.
- D-17: Snobbery-tone empty states.

**Mobile layout polish (MOB-03, MOB-04, MOB-07, MOB-08, MOB-13):**
- D-18: Home keeps lists-first order. Cold-start meter stays where shipped.
- D-19: Modals = full-screen sheet <768px / dialog >=768px.
- D-20: Bottom nav hides only in GBM full-screen and search sheet.
- D-21: Table→card collapse is verify-and-fix, not redesign.

### Claude's Discretion

- Service-worker cache strategy locked by ROADMAP success criterion #2 (stale-while-revalidate app shell, network-first other GETs, cache name embeds build hash).
- iOS install banner: one-time, localStorage-dismissed, shown only on iOS Safari when not standalone.
- `start_url: "/?source=pwa"` must return 200 — verify home route passes query param through.
- `brew_time_seconds` display location (session detail/list) — planner's call; analytics deferred.
- Active-tab highlighting, icon set, catalog-hub layout, GBM timer layout, cancel-without-logging confirmation, wake-lock indicator copy.

### Deferred Ideas (OUT OF SCOPE)

- PWA offline write queue + background sync — v2.
- Manual dark/light toggle — v2.
- `brew_time_seconds` in analytics — future phase.
- Per-user settings/preferences page — v2.
- Cold-start meter / analytics-first home reorder — explicitly declined.
- Bottom-sheet partial-height modals — full-screen chosen.
- "Inline add new coffee from brew-form coffee select" — not Phase 11 scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BREW-12 | Guided Brew Mode full-screen interface: large countdown timer, current step highlighted with cumulative water target and elapsed time, audio chime + vibration at step transitions (configurable), pause/resume, cancel-without-logging, "Done brewing" returns to session form with timer data + recipe + selected coffee prefilled | GBM route pattern, Alpine.js CSP component, AudioContext synthesized tone, Vibration API graceful degradation |
| BREW-13 | Guided Brew Mode requests `wakeLock`; re-acquires on `visibilitychange`; iOS Safari fallback via silent audio loop or NoSleep.js; visible indicator when wake lock is held | Wake Lock API iOS 18.4 fix, NoSleep.js v0.12.0 CDN, re-acquisition pattern |
| MOB-01 | Bottom tab nav (Home/Log/Config/Admin) at <768px with iOS safe-area inset; top horizontal nav at >=768px | Alpine CSP navBar component, `env(safe-area-inset-bottom)`, fixed positioning pattern |
| MOB-02 | Admin tab hidden for non-admins | `request.state.user.is_admin` gating in Jinja template |
| MOB-03 | Tables collapse to card lists at mobile widths; no horizontal scroll anywhere | Existing dual `hidden md:block` / `md:hidden` pattern — audit and fix |
| MOB-04 | All tap targets >=44x44px | `min-h-[44px] min-w-[44px]` Tailwind pattern (already used in search-bar.js) |
| MOB-07 | Native `<select>` for short dropdowns; searchable HTMX dropdown for long lists (coffees only) | Audit pass — already mostly implemented |
| MOB-08 | Modals are full-screen sheets at <768px, dialogs at >=768px | mini-modal.js structural class swap pattern |
| MOB-09 | `manifest.json` with name, short_name, description, icons, display: standalone, dual theme-color, start_url returning 200 | FastAPI JSON response route, locked strings from D-16 |
| MOB-10 | Service worker from `/sw.js` with `Service-Worker-Allowed: /` header; app shell cache; explicit version + cache-bust on deploy | Custom header on FastAPI route, build hash from `compute_tailwind_css_path()` pattern |
| MOB-11 | Apple touch icon + iOS install meta tags; in-app "Add to Home Screen" banner for iOS Safari | Alpine CSP `iosBanner` component, navigator.standalone detection, localStorage dismiss |
| MOB-12 | Installable to home screen on iOS Safari and Android Chrome | Manifest + SW + HTTPS + icons — all required |
| MOB-13 | Responsive smoke check (Playwright) at 375x667 and 390x844 — NOTE: automated Playwright test itself is Phase 12 (TEST-06); Phase 11 only manually verifies at these viewports | Manual verification during implementation |
| UX-01 | Warm minimalist palette implemented as Tailwind theme; system-preference dark mode | Palette already shipped (confirm, don't rebuild) |
| UX-02 | PWA branding strings locked (D-16) | LOCKED — copied verbatim into manifest |
| UX-03 | Browser tab title format `Snobbery — {Page Name}`; desktop wordmark / mobile icon-only | Already enforced by base.html; new pages must set `{% block page_title %}` |
| UX-04 | Empty states in snobbery tone | Copywriting contract in UI-SPEC already approved |
</phase_requirements>

---

## Summary

Phase 11 is the final polish sprint before hardening. It has three distinct technical clusters of unequal difficulty:

**Easy (established patterns, mostly audit work):** The mobile layout polish (D-19 through D-21) — table-to-card audit, tap target sweep, modal-to-sheet structural class change — is mechanical work against templates that already have the dual patterns in place. The manifest.json and login page redesign are JSON + Jinja edits. The icon generation is a one-time Pillow script.

**Medium (new but conventional):** The persistent nav frame (D-01 through D-06) follows the Alpine CSP component pattern already established in search-bar.js. The service worker is ~80 lines of vanilla JS served as a static route with a custom header. The iOS install banner is a straightforward Alpine component with localStorage persistence.

**Hard (platform-specific, requires real-device testing):** Guided Brew Mode's Wake Lock + iOS fallback (BREW-13) is the research flag that has been carried through multiple phases. The key finding: iOS 18.4 (March 2025) fixed the long-standing bug that broke Wake Lock in installed PWAs (WebKit bug 108573133). For devices on iOS 18.4+, `navigator.wakeLock` works in standalone mode. For devices on iOS 16.4–18.3, the API exists in regular Safari but silently fails in standalone. For those devices the silent-audio-loop (NoSleep.js) fallback applies. NoSleep.js v0.12.0 is the last stable release (December 2020) — stale but widely deployed and available at `https://cdn.jsdelivr.net/npm/nosleep.js@0.12.0/dist/NoSleep.min.js`. However, given iOS 18.4 fully fixed the bug and iOS 18.x is the current release train, the practical fallback window is narrow. The vibration API does NOT exist on iOS Safari at all (caniuse confirms `Not supported` across all iOS versions) — this is a hard unsupported capability, not a flag. Plan for graceful silent skip.

The CSP implications cut across both medium and hard work: every new `<script>` tag, service worker registration call, and the GBM AudioContext require nonce coverage. The existing pattern (nonce in base.html script tags, all JS registered via `Alpine.data()` factories) is well-established and should extend cleanly, but there are two non-obvious edge cases detailed in the CSP section below.

**Primary recommendation:** Ship the nav frame and PWA manifest/service-worker first (they unblock installability validation). Then Guided Brew Mode. Then the polish audit sweep last, since it's less risky but wide.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Bottom/top nav frame | Frontend (Jinja2 template, base.html) | Client JS (Alpine navBar) | Nav is server-rendered HTML; Alpine owns only active-tab state derivation |
| PWA manifest | FastAPI route (JSON response) | — | Manifest is a JSON document served as a route, not a static file (needs Content-Type: application/manifest+json) |
| Service worker | FastAPI route (JS file response) + NGINX | — | Must be served from root with Service-Worker-Allowed header; cannot be static mount without header override |
| Guided Brew Mode timer | Client JS (Alpine guidedBrewMode component) | FastAPI route (page render) | Timer state is entirely client-side; server only renders the initial page with recipe steps |
| Wake Lock + iOS fallback | Client JS (guidedBrewMode component) | — | Browser API; no server involvement |
| Audio chime | Client JS (AudioContext, guidedBrewMode) | — | Web Audio API, synthesized in-browser |
| Vibration | Client JS (navigator.vibrate, graceful skip) | — | Browser API; iOS skips silently |
| iOS install banner | Client JS (Alpine iosBanner component) | — | Client-side UA detection + localStorage |
| PWA icon generation | Build artifact (one-time Pillow script) | CI/deploy artifact | Pre-generated PNGs checked in; no runtime generation |
| `brew_time_seconds` schema | Database (Alembic migration) | FastAPI route (session form) | Additive nullable column on existing brew_sessions table |
| Table-to-card collapse | Frontend (Jinja2 templates) | — | CSS class audit in existing fragment templates |
| Modal-to-sheet | Frontend (Alpine miniModal) + CSS | — | Structural Tailwind class change in mini-modal.js + base.html |

---

## Standard Stack

### Core (no new dependencies — all existing)

| Library | Version | Purpose | Note |
|---------|---------|---------|------|
| Alpine.js CSP build | 3.15.12 (pinned in base.html) | Nav, GBM, banner, dropdown components | [VERIFIED: base.html CDN pin] |
| HTMX | 2.0.10 (pinned in base.html) | Fragment swaps within nav, GBM entry points | [VERIFIED: base.html CDN pin] |
| Tailwind CSS v3 standalone | 3.4.17 (Dockerfile ARG) | All layout — nav, GBM, sheets, safe-area | [VERIFIED: Dockerfile] |
| FastAPI | >=0.136,<0.137 | PWA routes, GBM page route, manifest route | [VERIFIED: CLAUDE.md stack] |
| SQLAlchemy 2.0 / Alembic | pinned | `brew_time_seconds` migration | [VERIFIED: CLAUDE.md stack] |
| Pillow | >=12.2,<13 | One-time icon generation script | [VERIFIED: CLAUDE.md stack] |

### New CDN-loaded library (conditional)

| Library | Version | Purpose | CDN URL | Confidence |
|---------|---------|---------|---------|------------|
| NoSleep.js | 0.12.0 | iOS Wake Lock fallback (pre-18.4 devices only) | `https://cdn.jsdelivr.net/npm/nosleep.js@0.12.0/dist/NoSleep.min.js` | [VERIFIED: jsDelivr package listing] |

**Important:** NoSleep.js v0.12.0 was released December 2020 and has had no releases since. It is technically stale but still functions correctly as an iOS silent-audio-loop fallback. The library's use is conditional: if `navigator.wakeLock` succeeds, NoSleep.js is never loaded or called. Load the script only on GBM pages, not globally. Given iOS 18.4 fixed Wake Lock in PWAs, the practical audience for NoSleep.js is devices on iOS 16.4–18.3 running installed PWAs, which is a shrinking population.

**Alternatives considered:**
- `@zakj/no-sleep` (npm, 0.13.6, active) — newer fork but not available as UMD CDN; would require download and self-hosting in `app/static/js/vendor/`. Self-hosting is acceptable given the no-npm constraint. Recommend self-hosting `@zakj/no-sleep` ESM build as a fallback if the production test on iOS reveals NoSleep.js UMD issues.
- Silent audio loop (hand-rolled) — ~30 lines of AudioContext + `createBufferSource` looping silence. Viable but re-implements what NoSleep.js does. NoSleep.js also handles the older `<video>` trick for pre-16.4 iOS. Recommend NoSleep.js.

**No new Python packages required.** All Phase 11 backend work uses existing dependencies.

---

## Architecture Patterns

### System Architecture Diagram

```
Browser request (GET /)
        │
        ▼
NGINX reverse proxy
  ├─ /sw.js → FastAPI route (sw_router) → Cache-Control: no-cache + Service-Worker-Allowed: /
  ├─ /manifest.json → FastAPI route (pwa_router) → application/manifest+json
  └─ all others → FastAPI app (existing middleware stack)
                        │
                        ▼
              RequestContextMiddleware
              (mints csp_nonce per request)
                        │
                        ▼
              SecurityHeadersMiddleware
              (applies CSP_TEMPLATE with nonce)
                        │
                        ▼
              Jinja2 template (base.html)
              ├─ <head>: new Alpine component scripts (nonce tagged)
              │          nav-bar.js, account-dropdown.js, ios-banner.js
              │          + existing components
              ├─ <body>: nav frame (bottom tab mobile / top desktop)
              │          auth-gated via request.state.user
              └─ {% block content %}: page content

Browser Service Worker (sw.js, scope: /)
  ├─ install: precache app shell (tailwind.HASH.css, Alpine, HTMX, manifest, icons)
  ├─ fetch: stale-while-revalidate for app shell URLs
  │          network-first for all other GETs
  └─ activate: delete old caches (cache name embeds BUILD_HASH)

GBM Page (/brew/guided?recipe_id=N[&coffee_id=M])
  ├─ Server: renders full-screen page with recipe steps JSON in data attribute
  └─ Client: Alpine guidedBrewMode component
             ├─ Timer: setInterval countdown, auto-advance on step elapsed
             ├─ Audio: AudioContext synthesized tone (pre-warmed on Start tap)
             ├─ Vibration: navigator.vibrate (fails silently on iOS)
             ├─ Wake lock: navigator.wakeLock.request('screen')
             │             → re-acquire on visibilitychange
             │             → NoSleep.js fallback if wakeLock throws
             └─ Done: navigate to /brew/new?gbm=1&recipe_id=N[&coffee_id=M]&brew_time=T
```

### Recommended Project Structure (new files only)

```
app/
├── routers/
│   ├── pwa.py                    # manifest.json + sw.js routes
│   └── brew_guided.py            # GBM page route (/brew/guided)
├── static/
│   ├── js/
│   │   ├── alpine-components/
│   │   │   ├── nav-bar.js         # navBar component
│   │   │   ├── account-dropdown.js # accountDropdown component
│   │   │   ├── ios-banner.js      # iosBanner component
│   │   │   └── guided-brew-mode.js # guidedBrewMode component
│   │   └── vendor/
│   │       └── NoSleep.min.js     # self-hosted fallback
│   ├── css/
│   │   └── tailwind.src.css       # extend with nav + GBM + safe-area tokens
│   └── img/
│       ├── icon-192.png
│       ├── icon-512.png
│       ├── icon-512-maskable.png
│       ├── apple-touch-icon.png
│       ├── logo-badge.png
│       └── snobbery-login-hero.jpg
├── templates/
│   ├── base.html                  # absorb nav frame + iOS install banner
│   ├── pages/
│   │   ├── login.html             # dark hero redesign
│   │   ├── config_hub.html        # new: /config catalog hub
│   │   └── brew_guided.html       # new: GBM full-screen page
│   └── fragments/
│       └── (existing *_list.html files — audit touch only)
├── models/
│   └── brew_session.py            # add brew_time_seconds
└── migrations/versions/
    └── p11_brew_time_seconds.py   # additive nullable column

scripts/
└── generate_pwa_icons.py          # one-time Pillow icon generation

nginx.conf (README docs update)
└── # Cache-Control: no-cache on /sw.js
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Wake Lock on iOS pre-18.4 | Custom video/audio loop | NoSleep.js v0.12.0 | NoSleep.js handles the `<video>` silent loop trick and AudioContext approach with cross-browser fallbacks; ~16KB |
| Service worker versioning | Hash injected via Jinja template rendering | Computed from existing `tailwind_css_path` pattern (see Pattern 3 below) | The build hash already exists as part of the CSS filename; reuse it |
| Tab active state | Complex JS URL matching | `window.location.pathname.startsWith('/brew')` comparison in Alpine `x-bind:class` | Alpine CSP build supports simple string comparisons without eval |
| Maskable icon safe zone | Manual pixel calculation | 40% radius = content must fit in center 80% circle; `maskable.app` for preview validation | Chrome's Lighthouse audit enforces this |
| Circular crop with Pillow | Custom crop math | `ImageDraw.ellipse` mask + RGBA mode | Standard PIL pattern; see Code Examples |

---

## Pattern 1: Service Worker Route with Required Headers

The service worker MUST be served from the root path `/sw.js` (not `/static/sw.js`) with two critical headers:
1. `Service-Worker-Allowed: /` — grants the SW scope over the entire origin even though the file is served from root.
2. `Cache-Control: no-cache` — documented in NGINX config; prevents stale SW registration on redeploy.

**Implementation:** A dedicated FastAPI route (not `StaticFiles` mount) is required because `StaticFiles` does not support per-file custom response headers without subclassing. [VERIFIED: FastAPI GitHub issue #1433]

The Tailwind CSS build hash already exists in `compute_tailwind_css_path()` as `tailwind.XXXXXXXX.css`. The service worker cache name should embed this same hash so each Docker image build triggers SW cache purge on the next user visit.

```python
# app/routers/pwa.py
# Source: Pattern derived from existing compute_tailwind_css_path() in main.py
import hashlib
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import Response, JSONResponse

router = APIRouter()

def _get_build_hash() -> str:
    """Extract build hash from the hashed Tailwind CSS filename.
    
    Returns the 8-char SHA prefix embedded in tailwind.XXXXXXXX.css,
    reusing the same hash the CSS file carries so all cache keys
    stay in sync with a single build artifact.
    """
    css_dir = Path("app/static/css")
    candidates = sorted(
        p for p in css_dir.glob("tailwind.*.css") if p.name != "tailwind.src.css"
    )
    if candidates:
        # filename is "tailwind.XXXXXXXX.css" → extract the hash segment
        return candidates[0].stem.split(".", 1)[1]  # e.g. "a3f9b12c"
    return "dev"


_BUILD_HASH = _get_build_hash()  # compute once at module load (app startup)


@router.get("/manifest.json")
def manifest(request: Request) -> JSONResponse:
    data = {
        "name": "Snobbery — Coffee Log",
        "short_name": "Snobbery",
        "description": "Self-hosted coffee log for households who take pour-over seriously",
        "display": "standalone",
        "start_url": "/?source=pwa",
        "background_color": "#FAF7F2",
        "theme_color": "#FAF7F2",
        "icons": [
            {"src": "/static/img/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/img/icon-512.png", "sizes": "512x512", "type": "image/png"},
            {
                "src": "/static/img/icon-512-maskable.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
            {"src": "/static/img/apple-touch-icon.png", "sizes": "180x180", "type": "image/png"},
        ],
    }
    return JSONResponse(
        content=data,
        headers={"Content-Type": "application/manifest+json"},
    )


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

**Note on sw.js BUILD_HASH injection:** The approach above reads `sw.js` as a template and substitutes `__BUILD_HASH__` at serve time. This is zero-cost because the SW file is small and the Python `str.replace` is trivial. An alternative is to bake the hash into the static file at Dockerfile build time (a `sed` in the Dockerfile `RUN` step), but that adds Dockerfile complexity for little gain. The serve-time substitution is simpler and consistent with how the app already manages hashed CSS paths. [ASSUMED: serve-time substitution pattern; not verified against existing codebase conventions outside `compute_tailwind_css_path`]

### Pattern 2: Service Worker Cache Strategy

```javascript
// app/static/js/sw.js
// BUILD_HASH is substituted by the Python route at serve time.
const CACHE_NAME = 'snobbery-v__BUILD_HASH__';

// App shell URLs to precache on install.
// The Tailwind CSS URL is dynamic — we cannot hardcode it here without knowing
// the hash. Strategy: precache the page HTML (which references the hashed CSS),
// then the CSS is cached on first navigation via stale-while-revalidate.
const APP_SHELL = [
    '/',
    '/manifest.json',
    '/static/img/icon-192.png',
    '/static/img/icon-512.png',
    '/static/img/apple-touch-icon.png',
    '/static/img/logo-badge.png',
];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => cache.addAll(APP_SHELL))
    );
    self.skipWaiting();
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(
                keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
            )
        )
    );
    self.clients.claim();
});

self.addEventListener('fetch', event => {
    const req = event.request;
    // Bypass non-GET requests (POST/PUT/DELETE — CSRF-protected forms, HTMX mutations)
    if (req.method !== 'GET') return;

    // Stale-while-revalidate for app shell and static assets
    const isAppShell = APP_SHELL.includes(new URL(req.url).pathname);
    const isStatic = new URL(req.url).pathname.startsWith('/static/');

    if (isAppShell || isStatic) {
        event.respondWith(
            caches.open(CACHE_NAME).then(cache =>
                cache.match(req).then(cached => {
                    const network = fetch(req).then(response => {
                        cache.put(req, response.clone());
                        return response;
                    });
                    return cached || network;
                })
            )
        );
    } else {
        // Network-first for all other GETs (API fragments, search, etc.)
        event.respondWith(
            fetch(req).catch(() =>
                caches.match(req).then(cached =>
                    cached || new Response('You\'re offline. Changes cannot be saved right now.', {
                        status: 503,
                        headers: {'Content-Type': 'text/plain'},
                    })
                )
            )
        );
    }
});
```

**iOS ITP concern:** iOS aggressively evicts `CacheStorage` after 7 days of non-use (for PWAs in browser tab mode). For installed PWAs (home screen), this eviction is less aggressive. Keep the precache shell small — the list above totals roughly 50–100KB, well within iOS's ~50MB PWA cache limit. [CITED: vinova.sg/navigating-safari-ios-pwa-limitations + MDN PWA caching guide]

**Static CSS in precache:** The hashed Tailwind CSS file (`/static/css/tailwind.XXXXXXXX.css`) is not listed in `APP_SHELL` because its filename is dynamic. However it will be cached on first navigation via the `isStatic` catch. This is acceptable — on first load the CSS is always fresh from the network; on subsequent loads it comes from cache with background revalidation. [ASSUMED: this ordering is acceptable for a household-scale app]

### Pattern 3: Wake Lock + iOS Fallback

iOS Safari 16.4–18.3 supports `navigator.wakeLock` in regular Safari but silently fails in installed PWAs (was broken until iOS 18.4 fixed it). [VERIFIED: WebKit blog, WebKit bug 108573133, Safari 18.4 release notes]

The strategy: try native Wake Lock first; catch failure and fall back to NoSleep.js (which uses a silent audio loop on iOS). Wrap all of this in the Alpine `guidedBrewMode` component.

```javascript
// app/static/js/alpine-components/guided-brew-mode.js (relevant excerpt)
// Source: MDN Screen Wake Lock API + WebKit Safari 18.4 release notes

document.addEventListener('alpine:init', () => {
  Alpine.data('guidedBrewMode', () => ({
    wakeLockSentinel: null,
    noSleep: null,
    wakeLockState: 'none',  // 'held' | 'fallback' | 'none'

    async requestWakeLock() {
      // Try native Wake Lock first (works on iOS 16.4+ in Safari;
      // works in PWA/standalone on iOS 18.4+; Chrome/Android always)
      if ('wakeLock' in navigator) {
        try {
          this.wakeLockSentinel = await navigator.wakeLock.request('screen');
          this.wakeLockState = 'held';
          this.wakeLockSentinel.addEventListener('release', () => {
            this.wakeLockState = 'none';
          });
          return;
        } catch (e) {
          // Falls through to NoSleep.js fallback
        }
      }
      // NoSleep.js fallback for iOS pre-18.4 installed PWAs and devices
      // that don't support the Wake Lock API at all.
      // NoSleep.min.js must be loaded (nonce-tagged) before this runs.
      if (window.NoSleep) {
        this.noSleep = new window.NoSleep();
        try {
          await this.noSleep.enable();
          this.wakeLockState = 'fallback';
        } catch (e) {
          this.wakeLockState = 'none';  // Silent degradation
        }
      }
    },

    async releaseWakeLock() {
      if (this.wakeLockSentinel) {
        await this.wakeLockSentinel.release();
        this.wakeLockSentinel = null;
      }
      if (this.noSleep) {
        this.noSleep.disable();
        this.noSleep = null;
      }
      this.wakeLockState = 'none';
    },

    // Called from init() — re-acquires on tab visibility restore.
    // NoSleep.js does NOT auto-re-acquire; the sentinel does not either.
    _setupVisibilityReacquire() {
      document.addEventListener('visibilitychange', async () => {
        if (document.visibilityState === 'visible' && this.isRunning) {
          await this.requestWakeLock();
        }
      });
    },
  }));
});
```

**CSP and NoSleep.js loading:** NoSleep.js must be loaded with a nonce tag since the page CSP is nonce-based. The script loads as a `<script defer src="/static/js/vendor/NoSleep.min.js" nonce="{{ csp_nonce(request) }}">` in the GBM page template (not in base.html globally). Because Alpine component scripts must load before `@alpinejs/csp`, and the GBM template extends base.html, the nonce-tagged NoSleep.js `<script>` tag goes in a `{% block head_extra %}` that the GBM template populates. [ASSUMED: `{% block head_extra %}` does not yet exist in base.html and must be added as an empty block]

**User gesture requirement for NoSleep.js on iOS:** NoSleep.js's `enable()` uses `AudioContext.resume()` internally. This call must happen in response to a user gesture. The "Start guided brew" button (which begins the timer) IS a user gesture — call `noSleep.enable()` inside that click handler, not at component init. [VERIFIED: MDN Web Audio API best practices, iOS AudioContext behavior confirmed in developer forum thread]

### Pattern 4: Audio Chime via Web Audio API (CSP-safe)

No external audio file needed. A synthesized tone via `OscillatorNode` works fully under strict CSP (no eval, no inline) and satisfies the iOS gesture requirement when called from the Start button handler.

```javascript
// Source: MDN Web Audio API + Autoplay guide — synthesized OscillatorNode pattern

// AudioContext is created ONCE at component init but kept suspended.
// It is unlocked (resumed) inside the "Start guided brew" button handler.
init() {
  this.audioCtx = null;
  // ...
},

unlockAudio() {
  // Called from the "Start guided brew" button tap — must be user gesture.
  if (!this.audioCtx) {
    this.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  if (this.audioCtx.state === 'suspended') {
    this.audioCtx.resume();
  }
},

playChime() {
  if (!this.audioCtx || this.audioCtx.state !== 'running') return;
  const osc = this.audioCtx.createOscillator();
  const gain = this.audioCtx.createGain();
  osc.type = 'sine';
  osc.frequency.setValueAtTime(880, this.audioCtx.currentTime);  // A5
  gain.gain.setValueAtTime(0.3, this.audioCtx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, this.audioCtx.currentTime + 0.5);
  osc.connect(gain);
  gain.connect(this.audioCtx.destination);
  osc.start();
  osc.stop(this.audioCtx.currentTime + 0.5);
},
```

**iOS re-lock concern:** There are reports (iOS 18.5 specifically) of `AudioContext` silently re-suspending after ~5 seconds of inactivity. Mitigation: call `audioCtx.resume()` inside the step-advance handler (each auto-advance or manual skip) to re-ensure it is running. [CITED: Apple Developer Forums thread on audio context re-suspension]

### Pattern 5: Vibration API (with Graceful Degradation)

```javascript
// iOS Safari: navigator.vibrate is NOT defined. Returns false or throws on some browsers.
// Source: caniuse.com/mdn-api_navigator_vibrate — confirmed iOS = Not supported

triggerVibration() {
  if (this.cuePrefs.vibrate && navigator.vibrate) {
    navigator.vibrate([100, 50, 100]);
  }
  // If navigator.vibrate is undefined (iOS) — silent skip. No error. No UI message.
},
```

Do not show an error or indicator when vibration is unavailable. It is simply absent on iOS. [VERIFIED: caniuse.com — iOS Safari 3.2 through 26.5: Not supported]

### Pattern 6: iOS Install Banner Detection

```javascript
// Source: MDN PWA Enhancements guide, web.dev/learn/pwa/enhancements

document.addEventListener('alpine:init', () => {
  Alpine.data('iosBanner', () => ({
    show: false,

    init() {
      const dismissed = localStorage.getItem('snobbery:ios-banner-dismissed');
      if (dismissed) return;

      // navigator.standalone is iOS-only (non-standard, WebKit-only).
      // On Android/Chrome, use matchMedia display-mode instead.
      const isIOS = /iPhone|iPad|iPod/.test(navigator.userAgent);
      const isStandalone = window.navigator.standalone === true;

      if (isIOS && !isStandalone) {
        this.show = true;
      }
    },

    dismiss() {
      this.show = false;
      localStorage.setItem('snobbery:ios-banner-dismissed', '1');
    },
  }));
});
```

**EU DMA note:** In early 2024, Apple briefly removed standalone PWA support in the EU under iOS 17.4. They reversed the decision after developer backlash. As of 2025/2026, standalone PWA support in the EU is restored and functioning. [VERIFIED: Apple Developer support page, WebKit blog] EU users will see the iOS install banner and standalone mode works as expected.

### Pattern 7: Maskable Icon Generation (Pillow)

The maskable icon safe zone is a circle centered in the icon with 40% radius — meaning content must fit within the central 80% of the image. For a 512px icon: the safe zone is ~410px centered. [VERIFIED: web.dev/articles/maskable-icon, MDN icons reference]

```python
# scripts/generate_pwa_icons.py (one-time Pillow script)
# Source: note.nkmk.me/en/python-pillow-square-circle-thumbnail + MDN maskable spec

from PIL import Image, ImageDraw
from pathlib import Path

SRC = Path("app/static/img/snobbery-login.jpg")
OUT = Path("app/static/img")

def circular_crop(img: Image.Image, size: int) -> Image.Image:
    """Crop to a circle with transparent background."""
    img = img.convert("RGBA").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size - 1, size - 1), fill=255)
    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    result.paste(img, mask=mask)
    return result

def maskable_icon(img: Image.Image, size: int) -> Image.Image:
    """Create a maskable icon — content in center 80%, solid background fill."""
    # Safe zone: 40% margin on each side = 20% padding each side of a 512px icon
    # Pad to put the circle within the safe zone
    padding = int(size * 0.1)  # 10% padding = safe zone is center 80%
    inner_size = size - 2 * padding
    circle = circular_crop(img, inner_size)
    result = Image.new("RGBA", (size, size), (250, 247, 242, 255))  # cream-50 bg
    result.paste(circle, (padding, padding), mask=circle.split()[3])
    return result

if __name__ == "__main__":
    src = Image.open(SRC)
    circular_crop(src, 192).save(OUT / "icon-192.png")
    circular_crop(src, 512).save(OUT / "icon-512.png")
    maskable_icon(src, 512).save(OUT / "icon-512-maskable.png")
    circular_crop(src, 180).save(OUT / "apple-touch-icon.png")
    circular_crop(src, 64).save(OUT / "logo-badge.png")
    # Login hero: resize and compress, not circular-crop
    hero = src.convert("RGB")
    hero.thumbnail((720, 720), Image.LANCZOS)
    hero.save(OUT / "snobbery-login-hero.jpg", "JPEG", quality=75, optimize=True)
    print("Icons generated.")
```

**Validate with maskable.app before committing.** The maskable icon should have no transparent background — Chrome's Lighthouse audit will flag `purpose: maskable` icons with transparency. [CITED: web.dev/articles/maskable-icon]

---

## Common Pitfalls

### Pitfall 1: Service Worker Scope Mismatch
**What goes wrong:** SW registered at `/static/js/sw.js` with no `Service-Worker-Allowed` header has scope limited to `/static/js/` — it intercepts zero page requests.
**Why it happens:** SW scope defaults to the directory of the SW script file.
**How to avoid:** Serve the SW from a FastAPI route at `/sw.js` (not from StaticFiles) and set `Service-Worker-Allowed: /` in the response headers. [VERIFIED: service worker spec behavior]
**Warning signs:** Browser DevTools → Application → Service Workers shows "scope: /static/js/" instead of "scope: /".

### Pitfall 2: Cache Name Not Changing on Deploy
**What goes wrong:** Users on re-deploy continue to see the old cached app shell; the SW does not activate the new version because the cache name is identical.
**Why it happens:** If `BUILD_HASH` is hardcoded or derived from a non-changing source.
**How to avoid:** Derive `BUILD_HASH` from the `tailwind.XXXXXXXX.css` filename, which changes on every `docker compose build` because Dockerfile stage 1 recomputes `sha256sum tailwind.src.css`. The SW cache name `snobbery-v{BUILD_HASH}` therefore changes whenever the image rebuilds. [VERIFIED: Dockerfile tailwind build stage]
**Warning signs:** Lighthouse "installable" check passes but content updates never reach users.

### Pitfall 3: Wake Lock Silently Failing on iOS Pre-18.4 Installed PWAs
**What goes wrong:** `navigator.wakeLock.request('screen')` throws a `NotAllowedError` on iOS devices in standalone mode before iOS 18.4.
**Why it happens:** WebKit bug 254545, fixed in iOS 18.4 (March 2025).
**How to avoid:** Always wrap `wakeLock.request()` in try/catch. Fall through to NoSleep.js on failure. Prototype on a real iPhone running iOS before 18.4 to confirm fallback behavior. [VERIFIED: WebKit bug tracker, Apple Safari 18.4 release notes]
**Warning signs:** `wakeLockState` stays 'none' even though the API nominally exists.

### Pitfall 4: AudioContext Suspended on iOS (User Gesture Required)
**What goes wrong:** GBM's chime is silent because `audioCtx.state === 'suspended'` and `resume()` was not called within a user gesture handler.
**Why it happens:** iOS Safari requires AudioContext to be unlocked inside a click/touchend handler. Creating the context or calling resume() at component init() does not satisfy this requirement.
**How to avoid:** Create the AudioContext AND call `resume()` inside the "Start guided brew" button's click handler (which IS a user gesture). [VERIFIED: MDN Web Audio API best practices, iOS AudioContext threading behavior]
**Warning signs:** `audioCtx.state` is 'suspended' after init; calling `osc.start()` without resuming throws `InvalidStateError`.

### Pitfall 5: CSP Blocking NoSleep.js or Service Worker Registration Script
**What goes wrong:** Service worker registration script tag or NoSleep.js loads without a nonce and is blocked by CSP (`script-src 'nonce-...'` does not include `'unsafe-inline'`).
**Why it happens:** Every `<script>` tag must carry `nonce="{{ csp_nonce(request) }}"` — the existing CSP is strict. Static assets served by `StaticFiles` never receive a nonce because they bypass the Jinja2 render pipeline.
**How to avoid:** Service worker registration: the SW file itself is served directly from a FastAPI route (no Jinja), but the **registration call** (`navigator.serviceWorker.register('/sw.js')`) must live in a nonce-tagged script in `base.html` or a nonce-tagged Alpine component. NoSleep.js on the GBM page: load via nonce-tagged `<script>` in a `{% block head_extra %}` that base.html exposes. [VERIFIED: existing `CSP_TEMPLATE` in `app/middleware/security_headers.py` — no `'unsafe-inline'` in script-src]
**Warning signs:** DevTools Console: "Refused to execute inline script because it violates the following Content Security Policy directive: 'script-src'".

### Pitfall 6: start_url "/?source=pwa" Redirect
**What goes wrong:** The Chrome install banner shows a console warning "start_url does not return a 200 status code" if `GET /?source=pwa` redirects to `/login` for unauthenticated requests.
**Why it happens:** The home router currently redirects unauthenticated requests. The `source=pwa` query param must pass through without triggering a different response code.
**How to avoid:** The home router redirects to `/login` (not the manifest's `start_url`), which is fine — an unauthenticated PWA launch will redirect to login and login will eventually reach `/`. The installability check is done by Chrome against the **manifest's start_url at the time Lighthouse runs**, authenticated. This may surface as a spurious Lighthouse warning in CI but not in real use. Verify by logging in and running Lighthouse. [ASSUMED: this analysis of redirect behavior; needs Lighthouse validation]

### Pitfall 7: `env(safe-area-inset-bottom)` and Sticky Elements Stacking
**What goes wrong:** On iPhone, sticky Save/Cancel buttons on the brew form overlap the bottom nav bar, or the bottom nav cuts into the content area.
**Why it happens:** Multiple `fixed bottom-0` elements fight for the same z-index layer; `env(safe-area-inset-bottom)` is not applied to both.
**How to avoid:** Bottom nav: `fixed bottom-0 pb-[env(safe-area-inset-bottom)]` + `h-16`. Sticky form actions offset: `sticky bottom-16 pb-[env(safe-area-inset-bottom)]`. Main content: `pb-16` (or `pb-20` with safe area) to ensure content scrolls above the nav. `viewport-fit=cover` is already set in `base.html`. [VERIFIED: UI-SPEC §Spacing, existing base.html meta viewport tag]
**Warning signs:** Content hidden behind nav at bottom of page on iPhone.

### Pitfall 8: Maskable Icon with Transparent Background
**What goes wrong:** Lighthouse "Maskable icon" audit fails: "Manifest doesn't have a maskable icon".
**Why it happens:** A PNG with transparent background does not fulfill the `purpose: maskable` contract — the OS expects a solid background to fill the adaptive shape.
**How to avoid:** `icon-512-maskable.png` must have a solid fill (cream-50 `#FAF7F2`) in the corners outside the circle. See Pattern 7. [VERIFIED: web.dev/articles/maskable-icon]

### Pitfall 9: `window.confirm()` Blocked in PWA Standalone Mode (Possible)
**What goes wrong:** `window.confirm('Cancel brew?')` may be suppressed by some browser implementations in standalone PWA mode.
**Why it happens:** Chrome for Android has historically suppressed `window.confirm()` in standalone PWAs. iOS Safari allows it.
**How to avoid:** Test on both platforms. If Chrome for Android blocks it, replace with a custom Alpine confirm dialog. Keep `window.confirm` for v1 and flag for Phase 12 testing. [ASSUMED — behavior varies by browser version; needs real-device verification]

---

## Code Examples

### Service Worker Registration (nonce-tagged, in base.html)
```html
{# Place in base.html <head> after the existing Alpine/HTMX scripts #}
{# Registers the SW once per page load — the browser deduplicates #}
<script nonce="{{ csp_nonce(request) }}">
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(function() {});
  }
</script>
```

### Nav Active State (Alpine CSP — no eval)
```javascript
// nav-bar.js — x-bind:class uses simple string comparison, no eval required
document.addEventListener('alpine:init', () => {
  Alpine.data('navBar', () => ({
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

### Account Dropdown Sign-out (CSRF-protected, Alpine CSP)
```html
{# Inside the accountDropdown x-data element — desktop only #}
<form method="post" action="/logout">
  <input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">
  <button type="submit" class="w-full text-left px-4 py-2 text-sm hover:bg-cream-200">
    Sign out
  </button>
</form>
```

### GBM Step Data in Template
```html
{# Pass recipe steps as a JSON data attribute to the Alpine component #}
{# Alpine reads it in init() with JSON.parse(this.$el.dataset.steps) #}
<div x-data="guidedBrewMode"
     data-recipe-id="{{ recipe.id }}"
     data-coffee-id="{{ coffee.id if coffee else '' }}"
     data-steps="{{ recipe.steps | tojson }}"
     class="...">
```

### Alembic Migration: brew_time_seconds
```python
# app/migrations/versions/p11_brew_time_seconds.py
# Source: existing migration pattern from p5_brew_sessions.py

def upgrade() -> None:
    op.add_column(
        "brew_sessions",
        sa.Column("brew_time_seconds", sa.Integer(), nullable=True),
    )

def downgrade() -> None:
    op.drop_column("brew_sessions", "brew_time_seconds")
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Wake Lock broken in iOS PWA | Fixed in iOS 18.4 (March 2025) | Safari 18.4 | NoSleep.js fallback is now a narrow edge case (pre-18.4 devices only) |
| HTMX 1.9 (spec wording) | HTMX 2.0 (current line) | Mid-2024 | Already on 2.x per project decisions |
| iOS EU PWA restriction | Reversed by Apple | March 2024 | Standalone PWAs work in EU again |
| navigator.vibrate on iOS | Still unsupported | — | Silent skip remains the correct approach |
| Alpine 3.14.9 (silent eval breakage) | Alpine 3.15.x (CSP expression evaluator rewrite) | Early 2025 | Already upgraded per base.html pin |

**Deprecated / avoid:**
- `<video>` silent-loop wake lock trick without NoSleep.js: fragile, codec-dependent, don't hand-roll.
- `@app.on_event("startup"/"shutdown")`: removed in Starlette 1.0; use `lifespan` (already in use).
- `bleach` for HTML sanitization: deprecated since 2023 (Mozilla). Not needed here — all user content goes through Jinja2 autoescape.

---

## Runtime State Inventory

> Skip condition: This is a greenfield feature phase (new routes, new column, new static files). No rename, refactor, or data migration. Only the `brew_time_seconds` migration touches existing runtime state.

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | `brew_sessions` table — no existing `brew_time_seconds` column | Additive migration (nullable); no data migration needed |
| Live service config | None | — |
| OS-registered state | None | — |
| Secrets/env vars | None new required | — |
| Build artifacts | Docker image does not contain generated PWA icons — they must be generated once and committed before first build | Run `generate_pwa_icons.py` locally, commit outputs, then build image |

---

## Open Questions

1. **iOS Wake Lock fallback: real-device prototype required**
   - What we know: iOS 18.4 fixed Wake Lock in installed PWAs; NoSleep.js v0.12.0 provides silent audio loop fallback for older devices; the "Start guided brew" button gesture satisfies both AudioContext unlock and NoSleep.js enable().
   - What's unclear: On the specific iOS device(s) in use, what iOS version is running? If both devices are on iOS 18.4+, NoSleep.js may be unnecessary.
   - Recommendation: Plan an explicit "Wave N: iOS manual test" task that tests on real hardware before closing BREW-13. If iOS < 18.4 is in use, NoSleep.js is required. If both devices are 18.4+, the fallback path still exists in code but will never be exercised.

2. **window.confirm() in standalone mode**
   - What we know: UI-SPEC D-19 specifies `window.confirm()` for GBM cancel confirmation; Chrome for Android has suppressed this in standalone PWAs in past versions.
   - What's unclear: Current Chrome for Android behavior in 2025/2026.
   - Recommendation: Ship with `window.confirm()` and add a Phase 12 Playwright/manual test note. If suppressed, Phase 12 can replace with a simple Alpine confirm dialog.

3. **start_url "/?source=pwa" Lighthouse warning**
   - What we know: Unauthenticated `GET /?source=pwa` will redirect to `/login` (not return 200).
   - What's unclear: Whether this triggers a Lighthouse installability error or just a warning; whether Chrome's install prompt is blocked by this.
   - Recommendation: Test Chrome installability with Lighthouse while logged in. The spec requirement is that the URL returns 200, which it does for authenticated users. For the install criteria check, ensure the home route passes through the `source` query param without redirecting (just ignore it).

4. **`{% block head_extra %}` does not exist in base.html**
   - What we know: The GBM template needs to load NoSleep.js only on the GBM page, not globally.
   - What's unclear: The exact mechanism for inserting page-specific nonce-tagged scripts into `<head>` when extending base.html.
   - Recommendation: Add `{% block head_extra %}{% endblock %}` in `base.html` `<head>`, between existing component scripts and the Alpine core script. GBM template populates it with the nonce-tagged NoSleep.js and SW registration lines.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker (build) | Icon generation + image rebuild | Assumed (project requirement) | — | — |
| Pillow | generate_pwa_icons.py | In `requirements.txt` (confirmed in CLAUDE.md stack) | >=12.2,<13 | — |
| Real iPhone (iOS 16-18) | BREW-13 iOS wake lock validation | Not verified | — | Skip and flag as manual test debt |
| Real Android Chrome | MOB-12 Android installability | Not verified | — | Use DevTools mobile simulation for installability check |

---

## Validation Architecture

> `workflow.nyquist_validation: true` — section required.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (existing) |
| Config file | Existing conftest.py |
| Quick run command | `docker compose exec coffee-snobbery python -m pytest tests/ -q -k "pwa or manifest or gbm or brew_time"` |
| Full suite command | `docker compose exec coffee-snobbery python -m pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| MOB-09 | GET /manifest.json returns 200 with correct Content-Type and locked strings | unit (HTTP smoke) | `pytest tests/test_pwa.py::test_manifest_200 -x` | ❌ Wave 0 |
| MOB-10 | GET /sw.js returns 200 with Service-Worker-Allowed: / header and Cache-Control: no-cache | unit (HTTP smoke) | `pytest tests/test_pwa.py::test_sw_headers -x` | ❌ Wave 0 |
| MOB-09 | start_url "/?source=pwa" returns 200 for authenticated user | unit (HTTP smoke) | `pytest tests/test_pwa.py::test_start_url_returns_200 -x` | ❌ Wave 0 |
| D-10 | brew_time_seconds column exists on brew_sessions table, nullable | migration smoke | `pytest tests/test_migrations.py -x` (extend existing) | Extends existing ✅ |
| BREW-13 | Wake Lock requested on GBM start, re-acquired on visibilitychange | manual (real device) | **Manual only** — Wake Lock API cannot be asserted in headless Playwright | N/A |
| BREW-13 | iOS NoSleep.js fallback activates when wakeLock throws | manual (real device, iOS < 18.4) | **Manual only** | N/A |
| MOB-01 | Bottom nav present at 375px, top nav present at 768px+ | manual + Phase 12 Playwright (TEST-06) | Manual during implementation; Playwright deferred to Phase 12 | N/A |
| MOB-12 | App is installable on Chrome (Lighthouse audit) | manual | Chrome DevTools → Lighthouse → PWA | N/A |
| MOB-13 | No horizontal scroll at 375px | manual during implementation | DevTools → Responsive 375px, scroll check | N/A |

### Sampling Rate
- **Per task commit:** `pytest tests/test_pwa.py -q` (once that file exists)
- **Per wave merge:** `pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_pwa.py` — covers MOB-09, MOB-10, start_url 200 check (3 tests)
- [ ] `{% block head_extra %}` empty block added to `base.html` (needed for GBM NoSleep script)

**Manual test gates (cannot be automated):**
- BREW-13: Wake Lock on real iPhone — must run before the phase is declared complete
- MOB-12: Chrome installability — Lighthouse PWA audit, logged-in session
- MOB-01, MOB-13: 375px responsive verification in DevTools during implementation of each template change

*(Phase 12 owns TEST-06 Playwright automation — Phase 11 manual-verifies only)*

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No new auth surface | — |
| V3 Session Management | No new session logic | — |
| V4 Access Control | Admin tab hidden (MOB-02), GBM route requires `require_user` | `Depends(require_user)` on `/brew/guided` route |
| V5 Input Validation | `brew_time_seconds` in session form submit | Pydantic v2 schema on `BrewSessionCreate` — add `brew_time_seconds: int | None = None` with `ge=0, le=86400` range |
| V6 Cryptography | No new crypto | — |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| GBM route accessed by unauthenticated user | Elevation | `Depends(require_user)` on `/brew/guided` |
| `brew_time_seconds` negative or absurd value submitted | Tampering | Pydantic `ge=0, le=86400` (max 24h brew) |
| SW intercepting HTMX mutation requests (POST/PUT/DELETE) | Tampering | SW `fetch` handler: bypass non-GET requests (`if req.method !== 'GET') return;`) |
| iOS install banner LocalStorage poisoning | Info disclosure | Minimal data stored — only a boolean dismiss flag. No user-identifying data. |
| `source=pwa` query param in start_url injection | Tampering | home router must read but ignore `source` param — do NOT pass to templates or log without sanitization |

**Additional security notes:**
- The service worker does NOT cache POST responses or HTMX mutation fragments. The `if (req.method !== 'GET') return` guard ensures this.
- NoSleep.js (v0.12.0) is self-hosted at `/static/js/vendor/NoSleep.min.js` — no CDN dependency at runtime. This eliminates CDN availability as a single point of failure and satisfies `connect-src 'self'` in the existing CSP.
- The `/sw.js` route intentionally bypasses SecurityHeadersMiddleware's CSP header addition (the SW file itself has no HTML or scripts to protect). The `Cache-Control: no-cache` and `Service-Worker-Allowed: /` headers are set directly on the Response object.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Serve-time `__BUILD_HASH__` substitution in `sw.js` route is acceptable; no race between build hash read at module load vs first request | Pattern 1 | If `_BUILD_HASH = _get_build_hash()` runs before Tailwind CSS is compiled (e.g., dev environment without the hashed file), it returns "dev". In production Docker builds this is always correct because stage 2 COPY brings the compiled CSS. |
| A2 | `{% block head_extra %}` does not yet exist in base.html and must be added | Pattern 3 + Open Questions | If base.html already has an extension point for per-page head scripts, use it instead of adding a new block. Verify by reading base.html before planning. (Already verified — base.html does NOT have this block as of this research.) |
| A3 | `start_url "/?source=pwa"` redirect behavior does not block Chrome install prompt | Pitfall 6 + Open Questions | If Chrome's install prompt requires start_url to return 200 for unauthenticated users, a redirect-to-login would break it. Needs Lighthouse verification on real device. |
| A4 | `window.confirm()` works in standalone Chrome for Android on current Chrome version | Pitfall 9 | If Chrome for Android suppresses confirm() in standalone, cancel-without-logging has no confirmation flow. Acceptable at v1; flag for Phase 12. |
| A5 | NoSleep.js v0.12.0 UMD build (`dist/NoSleep.min.js`) functions correctly when loaded as a nonce-tagged static script | Pattern 3 | If the UMD build calls `eval` or uses Function() constructor internally, the CSP will block it. Verify by checking the NoSleep.js source — it should be a simple UMD wrapper with no eval. |
| A6 | The hashed Tailwind CSS static URL for the precache shell need not be hardcoded in APP_SHELL | Pattern 2 | If the CSS is not in the precache, first load always needs the network. Acceptable for SWR strategy — it gets cached after first successful navigation. |

---

## Sources

### Primary (HIGH confidence)
- WebKit blog: https://webkit.org/blog/16574/webkit-features-in-safari-18-4/ — Wake Lock fix in PWAs
- Apple Safari 18.4 Release Notes — confirms Home Screen Web Apps Wake Lock fix (item 108573133)
- caniuse.com/wake-lock — iOS Safari 16.4+ support, full PWA support from 18.4
- caniuse.com/mdn-api_navigator_vibrate — iOS Safari: Not supported (all versions)
- jsDelivr package listing for nosleep.js@0.12.0 — version confirmed, dist/NoSleep.min.js confirmed
- app/middleware/security_headers.py (direct file read) — CSP_TEMPLATE verified: nonce-based, no unsafe-inline in script-src
- app/templates/base.html (direct file read) — Alpine 3.15.12 pin, HTMX 2.0.10 pin, nonce pattern
- Dockerfile (direct file read) — Tailwind 3.4.17, SHA-8 build hash mechanism
- app/main.py (direct file read) — compute_tailwind_css_path() pattern, StaticFiles mount
- MDN Screen Wake Lock API — re-acquire on visibilitychange pattern

### Secondary (MEDIUM confidence)
- MDN Web Audio API best practices — iOS user gesture requirement for AudioContext
- web.dev/articles/maskable-icon — 40% safe zone radius, solid background requirement
- FastAPI GitHub issue #1433 — StaticFiles cannot set per-file custom headers; custom subclass or dedicated route required
- Apple Developer Forums thread — AudioContext re-suspension on iOS 18.5 (single source, flag as LOW)
- MDN PWA Enhancements — navigator.standalone iOS detection
- vinova.sg PWA iOS guide — 7-day ITP eviction for service worker caches

### Tertiary (LOW confidence — flag for validation)
- iOS 18.5 AudioContext re-suspension after ~5s: single developer forum report, not confirmed in official docs. Mitigation is cheap (call `resume()` on each step advance) so implement defensively regardless.
- `window.confirm()` blocked in Chrome for Android standalone: historical behavior, current state unverified. Test on real Android device.

**Research date:** 2026-05-23
**Valid until:** 2026-06-23 (30 days — platform APIs stable; NoSleep.js version stable; iOS UA detection not changing)
