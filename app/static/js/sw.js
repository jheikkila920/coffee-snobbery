// Service worker — Phase 11, Plan 01.
// Cache name embeds the build hash so each Docker image rebuild triggers
// cache purge on the user's next visit (Pitfall 2).
// __BUILD_HASH__ is substituted by app/routers/pwa.py at serve time.
const CACHE_NAME = 'snobbery-v__BUILD_HASH__';

// App shell URLs to precache on install.
// The hashed Tailwind CSS URL is NOT listed here because its filename is
// dynamic. It is caught by the /static/ stale-while-revalidate branch on
// first navigation (Pattern 2, Assumption A6).
// NOTE: '/' is deliberately NOT precached. The home shell is require_user-gated
// and embeds per-user chrome (username, admin link/tab). Caching it with
// stale-while-revalidate would let the next user on a shared household device
// briefly see the prior user's identity, and serve an authenticated shell after
// sign-out / offline (code review CR-02). '/' therefore falls through to the
// network-first branch below (always fresh online; offline returns the 503
// "you're offline" message — offline writes are deferred in v1).
const APP_SHELL = [
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
    // Skip the waiting phase so the new SW activates immediately on next navigation.
    self.skipWaiting();
});

self.addEventListener('activate', event => {
    // Delete all caches whose name does not match CACHE_NAME.
    // This purges stale shells from previous deploys (T-11-04).
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

    // CSRF-safety guard (T-11-02): never intercept or cache POST/PUT/DELETE.
    // HTMX mutation requests carry CSRF tokens in their headers; letting them
    // bypass the SW ensures they always reach the server with their token intact.
    if (req.method !== 'GET') return;

    const url = new URL(req.url);

    // Only handle same-origin requests. Cross-origin assets (the Alpine + htmx
    // CDN scripts) must be left to the browser: intercepting them returns opaque
    // responses that can break script execution once the SW controls the page,
    // which broke Alpine hydration on in-app navigations (Phase 11-03 checkpoint).
    if (url.origin !== self.location.origin) return;

    const isAppShell = APP_SHELL.includes(url.pathname);
    const isStatic = url.pathname.startsWith('/static/');

    if (isAppShell || isStatic) {
        // Stale-while-revalidate for the app shell and all static assets.
        // Return the cached version immediately (fast), while fetching and
        // caching a fresh copy in the background (correct on next load).
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
        // Network-first for all other GETs (HTMX fragments, search, brew data).
        // If the network fails and nothing is cached, return an offline error
        // so the user knows they cannot save changes right now (T-11-03).
        event.respondWith(
            fetch(req).catch(() =>
                caches.match(req).then(cached =>
                    cached || new Response(
                        'You\'re offline. Changes cannot be saved right now.',
                        {
                            status: 503,
                            headers: { 'Content-Type': 'text/plain' },
                        }
                    )
                )
            )
        );
    }
});
