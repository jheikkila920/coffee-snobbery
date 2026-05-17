// app/static/js/htmx-listeners.js
//
// Runtime defense-in-depth: complements the D-04 grep-test ban on
// inline HTMX event-handler attributes and js:-prefix expressions
// (see .planning/phases/01-middleware/01-CONTEXT.md D-04) by
// disabling HTMX's four eval-using features at runtime. CSP also
// blocks them via the 'unsafe-eval' omission in script-src; this is
// belt-and-braces.
//
// Loaded by base.html (Plan 08) AFTER the htmx 2.x core script with:
//   <script defer src="/static/js/htmx-listeners.js"
//           nonce="{{ csp_nonce(request) }}"></script>
//
// This file is HTMX-only. Alpine.js components live in
// app/static/js/alpine-components/*.js (Plan 10 scaffolds the convention).
htmx.config.allowEval = false;

// Attach the double-submit CSRF token to every HTMX request.
//
// Reads `<meta name="csrf-token" content="...">` at REQUEST TIME (not page-
// load time) so a fragment swap that updates the meta tag — should that ever
// happen — is honored on the next request. The starlette-csrf cookie does
// NOT rotate per response (RESEARCH §3 + PITFALL HX-1), so the meta value
// is stable across HTMX swaps in practice; the per-request read is a
// belt-and-braces guarantee.
//
// If the meta tag is absent (e.g., a public page rendered before the
// CSRF middleware has set the cookie, or a future template that
// deliberately omits it), do nothing — no console error. starlette-csrf
// is configured with `sensitive_cookies={"session_id"}` so an
// unauthenticated request without a CSRF token is not enforced; an
// authenticated request without the token will correctly receive a 403
// from the middleware, which is the desired surfacing path.
document.body.addEventListener('htmx:configRequest', (evt) => {
  const tokenMeta = document.querySelector('meta[name="csrf-token"]');
  if (tokenMeta) {
    evt.detail.headers['X-CSRF-Token'] = tokenMeta.content;
  }
});

// Future Alpine.data() factories and HTMX event delegations go here.
// Add as needed in Phase 4+. The Plan 10 ADR documents the
// Alpine.data convention; this file remains the home for HTMX
// configRequest / beforeRequest / afterSwap handlers that would
// otherwise need to live in banned inline HTMX event attributes.
