// Live brew-ratio readout — BREW-05.
//
// Alpine-computed 1:N.NN, no schema column. The Dose + Water inputs report into
// this scope via x-on:input; a computed getter returns water / dose to 2
// decimals. CSP-build compliant (docs/decisions/0001): registered via
// Alpine.data, template binds via x-on:input + x-text (no two-way model
// binding, no inline arithmetic expressions — the division + formatting
// live here).
//
// Edge cases (UI-SPEC lock): dose 0 or empty → "—" (em dash), never NaN /
// Infinity. Both blank → "—". Seed values are read from data-* in init() so a
// prefilled / validation-re-rendered form shows the right ratio before the user
// touches anything.

document.addEventListener('alpine:init', () => {
  Alpine.data('brewRatio', () => ({
    dose: null,
    water: null,

    init() {
      this.dose = this._parse(this.$root.dataset.initialDose);
      this.water = this._parse(this.$root.dataset.initialWater);
    },

    _parse(raw) {
      if (raw === undefined || raw === null || raw === '') return null;
      const n = parseFloat(raw);
      return Number.isFinite(n) ? n : null;
    },

    setDose(v) {
      this.dose = this._parse(v);
    },

    setWater(v) {
      this.water = this._parse(v);
    },

    // The right-hand side of "1:N.NN". Returns the em dash for any non-finite /
    // zero-dose case so the readout never shows NaN or Infinity.
    get ratio() {
      if (this.dose === null || this.water === null || this.dose <= 0) {
        return '—';
      }
      const r = this.water / this.dose;
      if (!Number.isFinite(r)) return '—';
      return r.toFixed(2);
    },
  }));
});
