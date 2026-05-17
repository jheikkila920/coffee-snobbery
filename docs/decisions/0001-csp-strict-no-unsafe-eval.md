# ADR 0001: Strict CSP, No `'unsafe-eval'`

- Status: Accepted
- Date: 2026-05-16
- Phase: 1 (Middleware)
- Requirements: SEC-02, SEC-05
- Supersedes: (none)

## Context

SEC-02 requires a nonce-based Content Security Policy with no `'unsafe-eval'` and no `'unsafe-inline'` in `script-src`. The frontend stack — HTMX 2.0.10 + Alpine.js 3.x + Tailwind CSS — has historical friction with strict CSP:

- **Alpine.js** uses `new Function(...)` under the hood to evaluate the expressions in `x-data`, `x-show`, `x-on:`, `x-if`, `x-text`, `x-html`, etc. With the standard Alpine build, every directive value is a string passed through dynamic-eval — `'unsafe-eval'` is mandatory.
- **HTMX 2.x** retains four eval-using features: `hx-on:*` attribute event handlers; `hx-vals='js:...'`; `hx-headers='js:...'`; and `eval` filter expressions in `hx-trigger`.
- **Tailwind** historically shipped a "Play CDN" that injected a `<script>` blob into the page (no nonce). Phase 0 chose the standalone Tailwind CLI binary, which emits a hashed `.css` file — strict-CSP compatible.

A plan-phase research flag (RESEARCH §16 open question 2) asked whether `'unsafe-eval'` could be dropped entirely. The answer is yes, via the `@alpinejs/csp` build + a small list of banned HTMX patterns.

## Decision

1. **Alpine CSP build**. Use [`@alpinejs/csp`](https://www.npmjs.com/package/@alpinejs/csp) at version **3.14.9**, loaded from `https://cdn.jsdelivr.net/npm/@alpinejs/csp@3.14.9/dist/cdn.min.js` with `nonce="{{ csp_nonce(request) }}"`. The CSP build evaluates directives via property lookup on a registered factory object rather than `new Function(...)` — eliminating the `'unsafe-eval'` requirement at the cost of `x-model` and inline-literal `x-data="{ ... }"` support. Alpine components register via `Alpine.data('name', factoryFn)` from `app/static/js/alpine-components/*.js`.

2. **Canonical CSP directive set** — transcribed from `app/middleware/security_headers.py:CSP_TEMPLATE`:

   ```
   default-src 'self';
   script-src 'self' 'nonce-{nonce}';
   style-src-elem 'self' 'nonce-{nonce}';
   style-src-attr 'unsafe-inline';
   img-src 'self' data: blob:;
   connect-src 'self';
   font-src 'self';
   object-src 'none';
   base-uri 'self';
   frame-ancestors 'none';
   form-action 'self';
   report-uri /csp-report;
   report-to csp-report
   ```

3. **`'unsafe-eval'` is forbidden** in `script-src`. **`'unsafe-inline'` is forbidden** in `script-src` and `style-src-elem`. `SecurityHeadersMiddleware` ships a module-load `RuntimeError` invariant that asserts `'unsafe-eval'` does NOT appear in `CSP_TEMPLATE` — a future edit that adds it cannot start the app.

4. **`style-src-attr 'unsafe-inline'` is intentional.** This directive governs `setAttribute('style', ...)` and `cssText` writes — typically inline `style="..."` attributes in HTML literals and Alpine's `x-bind:style` string form. It does **not** affect `element.style.X = Y` direct property assignment, which is what Alpine's `x-transition` uses internally. The risk of `style="..."` injection is low (Jinja autoescape kills the obvious paths) but the operational value is high (designers reach for inline width/margin overrides).

5. **`hx-on:*` is banned** in templates. All HTMX behavior lives in `app/static/js/htmx-listeners.js`, attached via event delegation on `htmx:configRequest`, `htmx:beforeRequest`, and `htmx:afterSwap`. Belt-and-braces enforcement: `htmx.config.allowEval = false` is the first executable line in `htmx-listeners.js`, so even if a stray `hx-on:` slipped through review the browser would refuse to evaluate it.

6. **`hx-vals='js:...'`, `hx-headers='js:...'`, and eval-using `hx-trigger` event filters are also banned.** Plan 01-01's grep test (`tests/ci/test_no_unsafe_jinja.py`) fails the build on any of these four patterns appearing under `app/templates/pages/`.

7. **`x-model` is unavailable** under the Alpine CSP build (it requires runtime expression eval). For two-way binding use `:value="property"` + `@input="setValue($el.value)"` — this is the pattern documented at github.com/alpinejs/alpine discussion #3996.

8. **CSP violation reporting**: emit BOTH `report-uri /csp-report` (universal browser support) AND `report-to csp-report` (the newer Reporting API) plus a matching `Reporting-Endpoints: csp-report="/csp-report"` header. The `/csp-report` endpoint (D-06, Plan 01-03) is log-only — every violation lands as a `csp.violation` structured log line, rate-limited to 30/min/IP via slowapi (D-17).

## Consequences

- Every page template MUST extend `app/templates/base.html` to inherit the per-request nonce in its `<script>` and `<style>` tags.
- Phase 4+ Alpine components register via `Alpine.data('name', factory)` in `app/static/js/alpine-components/*.js`. Inline `x-data="{ count: 0 }"` literals are forbidden — they require `'unsafe-eval'` and will fail under the CSP build.
- Phase 12's CSP audit reads this ADR and the `CSP_TEMPLATE` constant to verify no drift. A future contributor who needs to relax CSP MUST write a superseding ADR — this one is binding until then.
- The Alpine CSP build's missing-directive list (`x-model`, inline `x-data` object literals, certain `x-init` forms) is a real ergonomic cost that future contributors will encounter. The replacement recipes from RESEARCH §1 are the answer; this ADR is the entry point.
- Phase 7 streaming: if v1.1 switches from polling to SSE, the SSE source endpoint must serve `text/event-stream` from the same origin (`connect-src 'self'` already permits this). No CSP change needed.

## Alternatives Considered

- **Standard Alpine.js + `'unsafe-eval'`** — rejected. Defeats the entire point of nonce-based CSP and contradicts SEC-02.
- **`'unsafe-hashes'`** for inline event handlers — rejected. More brittle than the CSP-build approach (every template change requires re-hashing all inline handlers; CI must maintain a hash manifest).
- **No CSP at all** — rejected. Violates SEC-02 explicitly and removes the primary mitigation for stored-XSS in user-supplied flavor notes (Phase 4) and AI prose (Phase 7).
- **Alpine v2 (which had simpler eval semantics)** — rejected. EOL'd and not receiving security patches.

## Enforcement

- `app/middleware/security_headers.py` raises `RuntimeError` at module load if `CSP_TEMPLATE` contains `'unsafe-eval'`.
- `tests/ci/test_no_unsafe_jinja.py` grep-checks `app/templates/pages/` for the four banned HTMX patterns (`|safe`, `hx-on:`, `hx-vals='js:`, `hx-headers='js:`).
- `tests/middleware/test_security_headers.py` asserts the CSP header is present on every response with the correct nonce.
- Phase 12 may add a Playwright check that visits the rendered home page and confirms the browser logs no CSP violations.

## References

- SEC-02, SEC-05 (`.planning/REQUIREMENTS.md`)
- D-01..D-06 (`.planning/phases/01-middleware/01-CONTEXT.md`)
- RESEARCH.md §1 (Alpine CSP build), §2 (HTMX 2.0.10 eval features), §9 (CSP directive set + Reporting API)
- `app/middleware/security_headers.py` (`CSP_TEMPLATE`, `CSP_FALLBACK`)
- `app/static/js/htmx-listeners.js` (`htmx.config.allowEval = false`)
- `app/static/js/alpine-components/__init.js` (registration-pattern example)
- https://alpinejs.dev/advanced/csp
- https://htmx.org/docs/#csp
- https://github.com/alpinejs/alpine/discussions/3996 (x-model replacement recipe)
