/*
 * Alpine.js CSP-build component registry.
 *
 * Every Alpine component lives in this directory as a single .js file
 * registering via:
 *
 *   Alpine.data('componentName', factoryFn);
 *
 * Templates reference the component by name:
 *
 *   <div x-data="componentName"> ... </div>
 *
 * Inline object literals like x-data="{ count: 0 }" are FORBIDDEN — they
 * require runtime expression eval ('unsafe-eval'), which our CSP does
 * not permit. See docs/decisions/0001-csp-strict-no-unsafe-eval.md for
 * the locked rationale (Alpine CSP build + the four banned HTMX
 * patterns + the htmx.config.allowEval = false runtime guard).
 *
 * Phase 4+ adds real components here. This __init.js file is the
 * convention example only — it contains zero live registrations, just
 * a commented-out pattern reference. Phase 4 will wire this file (or
 * its successors) into base.html with a
 *
 *   <script defer src="/static/js/alpine-components/__init.js"
 *           nonce="{{ csp_nonce(request) }}"></script>
 *
 * tag, loaded BEFORE the @alpinejs/csp CDN script so the registrations
 * are present when Alpine boots.
 *
 * Pattern reference (commented out — DO NOT uncomment until Phase 4
 * wires the script tag in base.html):
 *
 *   document.addEventListener('alpine:init', () => {
 *     Alpine.data('counter', () => ({
 *       count: 0,
 *       increment() {
 *         this.count++;
 *       },
 *     }));
 *   });
 *
 * For two-way binding under the CSP build (x-model is unavailable):
 *
 *   <input :value="text" @input="setText($el.value)">
 *
 *   Alpine.data('field', () => ({
 *     text: '',
 *     setText(v) { this.text = v; },
 *   }));
 */
