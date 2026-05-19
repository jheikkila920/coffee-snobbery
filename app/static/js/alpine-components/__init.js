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
 *   - mini-modal.js           (Phase 4 plan 04-11) — Alpine.data(
 *     'miniModal', ...) for the "+ Create new roaster / flavor note"
 *     mini-modal flow launched from inside the coffee form's autocomplete
 *     dropdowns. ESC + backdrop + dirty check. Close-on-success driven by
 *     the global HX-Trigger {entity}-created listeners emptying
 *     #modal-mount.
 *   - autocomplete.js         (Phase 4 plan 04-11) — Alpine.data(
 *     'autocomplete', ...) for single-value pickers (roaster) +
 *     Alpine.data('flavorNoteChips', ...) for multi-value chip widgets
 *     (advertised_flavor_note_ids). Keyboard nav + HX-Trigger pre-select
 *     consumer. Two registrations from one file because they share the
 *     same keyboard-handler shape.
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
