// Live brew-ratio readout — BREW-05 — plus the live Extraction-Yield preview.
//
// Alpine-computed 1:N.NN, no schema column. The Dose + Water inputs report into
// this scope via x-on:input; a computed getter returns water / dose to 2
// decimals. CSP-build compliant (docs/decisions/0001): registered via
// Alpine.data, template binds via x-on:input + x-text (no two-way model
// binding, no inline arithmetic expressions — the division + formatting
// live here).
//
// Extraction Yield (D-02 disclosure): the persisted value is the DB-GENERATED
// column extraction_yield_pct (rendered read-only server-side; never submitted).
// On /brew/new there is no persisted row yet, so the disclosure shows a LIVE
// preview computed here from dose + yield + tds, matching the Postgres formula
// exactly:  EY = (yield * tds / 100) / dose * 100  (tds is whole-percent, e.g.
// 1.35). Needs all three present; otherwise "—". The dose input already reports
// into this scope (it drives the ratio); the yield/tds inputs in the disclosure
// report in via x-on:input too.
//
// Edge cases (UI-SPEC lock): dose 0 or empty → "—" (em dash), never NaN /
// Infinity. Both blank → "—". Seed values are read from data-* in init() so a
// prefilled / validation-re-rendered form shows the right ratio (and EY) before
// the user touches anything.

document.addEventListener('alpine:init', () => {
  Alpine.data('brewRatio', () => ({
    dose: null,
    water: null,
    yieldGrams: null,
    tds: null,

    init() {
      this.dose = this._parse(this.$root.dataset.initialDose);
      this.water = this._parse(this.$root.dataset.initialWater);
      this.yieldGrams = this._parse(this.$root.dataset.initialYield);
      this.tds = this._parse(this.$root.dataset.initialTds);
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

    setYield(v) {
      this.yieldGrams = this._parse(v);
    },

    setTds(v) {
      this.tds = this._parse(v);
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

    // Live Extraction-Yield preview "N.NN%" for the disclosure. Mirrors the
    // Postgres GENERATED formula. Needs dose + yield + tds all present (and a
    // positive dose); otherwise the bare em dash "—" (no trailing % so a blank
    // field never reads "—%"). Rendered to 2 decimals to match the numeric(5,2)
    // stored column.
    get extractionYield() {
      if (
        this.dose === null ||
        this.yieldGrams === null ||
        this.tds === null ||
        this.dose <= 0
      ) {
        return '—';
      }
      const ey = (this.yieldGrams * this.tds) / 100 / this.dose * 100;
      if (!Number.isFinite(ey)) return '—';
      return ey.toFixed(2) + '%';
    },
  }));
});
