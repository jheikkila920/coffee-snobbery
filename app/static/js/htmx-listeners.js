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

// Re-walk swapped subtrees so Alpine binds any new x-data / x-on / :value
// directives on fragment content (plan 04-11). HTMX 2.x fires
// htmx:afterSettle once a swap has settled into the DOM; Alpine.initTree
// is the supported entry point for binding directives on a subtree the
// runtime has not yet seen (Alpine.start() walks document.body once at
// boot, but never again).
//
// Idempotent: Alpine.initTree on a tree it has already initialised is a
// no-op (Alpine tags initialised nodes via a hidden symbol).
//
// Required by:
//   - mini-modal.js (the swapped #modal-mount subtree carries
//     x-data="miniModal" on its root).
//   - autocomplete.js (dropdown <li role="option"> rendered into
//     #roaster-dropdown / #flavor-note-dropdown carry x-on:click
//     bindings that must resolve in the enclosing autocomplete scope).
document.body.addEventListener('htmx:afterSettle', (evt) => {
  if (window.Alpine && evt && evt.target) {
    Alpine.initTree(evt.target);
  }
});

// Coffee form: Remove-origin button delegation (D-04, Phase 15.1).
// The coffee_origin_row.html fragment carries data-action="remove-origin-row"
// on each row's Remove button (first row is non-removable so the user cannot
// drop to zero origins). On click, remove the closest [data-origin-row]
// ancestor from the DOM — purely client-side, no server round-trip.
//
// Delegated on document.body so rows appended via HTMX (the "+ Add another
// origin" hx-get) are covered without re-binding.
document.body.addEventListener('click', (evt) => {
  const target = evt.target;
  if (!(target instanceof Element)) return;
  const button = target.closest('[data-action="remove-origin-row"]');
  if (!button) return;
  const row = button.closest('[data-origin-row]');
  if (row) row.remove();
});
