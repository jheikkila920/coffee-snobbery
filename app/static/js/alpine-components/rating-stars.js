// Tap-on-stars rating control — BREW-04 / D-03.
//
// CSP-build compliant (docs/decisions/0001): registered via Alpine.data with a
// string reference; the template binds via :value + x-on:click / x-on:keydown
// (two-way model binding is banned — the @alpinejs/csp build cannot eval it).
// Config is read from data-* attributes in init(), mirroring
// recipe-step-builder.js's data-initial-steps pattern.
//
// Interaction model (D-03):
//   - Each star has TWO tap-zones. Left half of star i sets the value to
//     (i + 0.5); right half sets it to (i + 1.0). Tapping the same value again
//     is idempotent (it does not toggle off). A dedicated "Clear" affordance
//     resets to blank.
//   - Arrow-key parity (UI-SPEC): Left/Right adjust by 0.5, clamped to [0, 5].
//
// The committed value mirrors a hidden <input type="hidden" name="rating"
// :value="hiddenValue"> so the form submits the Decimal natively (blank when
// unrated). The DB/Pydantic column stays multiple_of=0.25, so a 0.5-step UI is
// always valid.
//
// Half-fill is rendered in the template via two stacked SVG paths (a clipped
// left-half filled path over an empty outline); this component only owns the
// numeric state + per-star fill fractions (full / half / empty), precomputed
// here because the CSP build forbids arithmetic-heavy inline expressions.

document.addEventListener('alpine:init', () => {
  Alpine.data('ratingStars', () => ({
    // null = unrated (the hidden input submits ""); a number 0.5..5.0 otherwise.
    value: null,

    init() {
      const raw = this.$root.dataset.initialRating;
      if (raw === undefined || raw === null || raw === '') {
        this.value = null;
        return;
      }
      const parsed = parseFloat(raw);
      this.value = Number.isFinite(parsed) ? this._clamp(parsed) : null;
    },

    _clamp(v) {
      if (v < 0) return 0;
      if (v > 5) return 5;
      return v;
    },

    // The value the hidden input submits. Blank string when unrated so the
    // server's rating field coerces to None (the router maps "" → None).
    get hiddenValue() {
      return this.value === null ? '' : String(this.value);
    },

    // Human-readable echo beside the stars ("3.5 / 5" or "Not rated").
    get echo() {
      return this.value === null ? 'Not rated' : this.value + ' / 5';
    },

    // Set the rating from a star index (0-based) and which half was tapped.
    // half = 'left' → index + 0.5; half = 'right' → index + 1.0.
    setHalf(index, half) {
      const target = half === 'left' ? index + 0.5 : index + 1.0;
      this.value = this._clamp(target);
    },

    clear() {
      this.value = null;
    },

    onKeydown(e) {
      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        const base = this.value === null ? 0.5 : this.value - 0.5;
        this.value = this._clamp(base < 0.5 ? 0 : base);
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        const base = this.value === null ? 0.5 : this.value + 0.5;
        this.value = this._clamp(base);
      }
    },

    // Fill state for star at 0-based index: 'full' | 'half' | 'empty'.
    // Precomputed here so the template binds a bare method call rather than an
    // inline arithmetic expression (CSP build constraint).
    fillState(index) {
      const v = this.value === null ? 0 : this.value;
      const full = index + 1;
      const half = index + 0.5;
      if (v >= full) return 'full';
      if (v >= half) return 'half';
      return 'empty';
    },

    // Accessible per-zone label ("Set rating to 2.5").
    zoneLabel(index, half) {
      const target = half === 'left' ? index + 0.5 : index + 1.0;
      return 'Set rating to ' + target;
    },
  }));
});
