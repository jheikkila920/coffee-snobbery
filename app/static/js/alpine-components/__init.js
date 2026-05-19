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
 * a commented-out pattern reference.
 *
 * Live components (loaded directly by base.html, each with its own
 * <script defer> tag BEFORE the @alpinejs/csp core script so the
 * Alpine.data registrations are present when Alpine boots):
 *
 *   - recipe-step-builder.js  (Phase 4 plan 04-08) — Alpine.data(
 *     'recipeStepBuilder', ...) for the multi-step pour timeline + live
 *     cumulative water/time readouts + zero-round-trip add/remove/reorder.
 *
 * Future plans (e.g., plan 04-11 mini-modal + autocomplete) add more
 * component files here following the same pattern: one file per
 * Alpine.data factory, loaded via its own <script defer> in base.html.
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
