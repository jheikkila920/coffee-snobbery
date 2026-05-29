// Recipe step builder — D-09 (zero round-trips during editing).
//
// CSP-build compliant: registered via Alpine.data; template uses
// x-data="recipeStepBuilder" (string reference, never an inline object
// literal). Loaded by base.html AFTER the @alpinejs/csp core script, so
// the registration is guaranteed to be in place by the time Alpine boots
// and walks the DOM for x-data bindings (the `alpine:init` listener
// fires synchronously inside Alpine's start-up sequence before its
// initial DOM walk).
//
// Pattern reference: docs/decisions/0001-csp-strict-no-unsafe-eval.md.
// The CSP build forbids x-model (eval-based two-way binding); the
// step-row template uses :value + @input pairs instead. Arbitrary JS
// expression strings in templates are rejected; only method calls
// (e.g. x-on:click="addStep()") and simple member access expressions
// (e.g. :value="step.label") are allowed.
//
// Reactivity note: Alpine 3's CSP build relies on Proxy-based reactivity.
// Direct property writes (`step.label = $el.value`) inside an @input
// handler ARE reactive — Alpine wraps each step dict on push/splice so
// downstream computed getters (totalWater, totalTime, timelineSegments)
// recalc automatically.

document.addEventListener('alpine:init', () => {
  Alpine.data('recipeStepBuilder', () => ({
    steps: [],
    showNote: {},

    init() {
      // The form template stamps data-initial-steps onto the wrapping
      // div via Jinja's `|tojson` filter — safe JSON-in-HTML-attribute
      // encoding (no autoescape-bypass needed). Parse here so the
      // builder seeds with the recipe's current pour timeline on edit
      // (or the default Bloom step on create).
      const initial = this.$root.dataset.initialSteps;
      try {
        const parsed = JSON.parse(initial || '[]');
        this.steps = Array.isArray(parsed) ? parsed : [];
      } catch (_err) {
        this.steps = [];
      }
      if (this.steps.length === 0) {
        this.steps = [{ type: 'Bloom', water_grams: 50, time_seconds: 45, label: 'Bloom', note: null, water_temp_c: null }];
      }
    },

    addStep() {
      const prev = this.steps[this.steps.length - 1] || {
        type: 'Pour', water_grams: 0, time_seconds: 0, label: '', note: null, water_temp_c: null,
      };
      // UI-SPEC: insert pre-filled with (prev.water + 50g, prev.time + 45s).
      this.steps.push({
        type: 'Pour',
        water_grams: (prev.water_grams || 0) + 50,
        time_seconds: (prev.time_seconds || 0) + 45,
        label: '',
        note: null,
        water_temp_c: null,
      });
    },

    removeStep(i) {
      this.steps.splice(i, 1);
    },

    moveUp(i) {
      if (i > 0) {
        const tmp = this.steps[i - 1];
        this.steps[i - 1] = this.steps[i];
        this.steps[i] = tmp;
      }
    },

    moveDown(i) {
      if (i < this.steps.length - 1) {
        const tmp = this.steps[i + 1];
        this.steps[i + 1] = this.steps[i];
        this.steps[i] = tmp;
      }
    },

    setLabel(i, v) {
      this.steps[i].label = v;
    },

    setWater(i, v) {
      const n = parseInt(v, 10);
      this.steps[i].water_grams = Number.isFinite(n) ? n : 0;
    },

    setTime(i, v) {
      const n = parseInt(v, 10);
      this.steps[i].time_seconds = Number.isFinite(n) ? n : 0;
    },

    setType(i, v) {
      this.steps[i].type = v || 'Pour';
      // When type is Wait or Action, clear water_grams (D-07)
      if (v === 'Wait' || v === 'Action') {
        this.steps[i].water_grams = null;
      }
    },

    setNote(i, v) {
      this.steps[i].note = v.trim() || null;
    },

    setWaterTemp(i, v) {
      const n = parseInt(v, 10);
      this.steps[i].water_temp_c = Number.isFinite(n) ? n : null;
    },

    deltaWater(i) {
      if (i === 0) return this.steps[0].water_grams || 0;
      return (this.steps[i].water_grams || 0) - (this.steps[i - 1].water_grams || 0);
    },

    deltaTime(i) {
      if (i === 0) return this.steps[0].time_seconds || 0;
      return (this.steps[i].time_seconds || 0) - (this.steps[i - 1].time_seconds || 0);
    },

    formatTime(secs) {
      const s = Math.max(0, Math.floor(secs || 0));
      const mm = Math.floor(s / 60);
      const ss = (s % 60).toString().padStart(2, '0');
      return mm + ':' + ss;
    },

    formatDelta(i) {
      const dw = this.deltaWater(i);
      const dt = this.deltaTime(i);
      const sign = dw >= 0 ? '+' : '';
      return 'Δ ' + sign + dw + 'g · +' + this.formatTime(dt);
    },

    get totalWater() {
      if (!this.steps.length) return 0;
      return this.steps[this.steps.length - 1].water_grams || 0;
    },

    get totalTime() {
      if (!this.steps.length) return 0;
      return this.steps[this.steps.length - 1].time_seconds || 0;
    },

    get totalLine() {
      return (
        'Total water: ' +
        this.totalWater +
        'g · Total time: ' +
        this.formatTime(this.totalTime)
      );
    },

    get stepsJson() {
      return JSON.stringify(this.steps);
    },

    get timelineSegments() {
      // Each segment's height ratio is its time-delta as a fraction of
      // total time (D-11). Zero-time recipes get a friendly empty
      // placeholder rendered by the template via x-if.
      const total = Math.max(1, this.totalTime);
      let prevTime = 0;
      return this.steps.map((step, idx) => {
        const start = prevTime;
        const end = step.time_seconds || 0;
        const delta = Math.max(0, end - start);
        prevTime = end;
        const ratio = (delta / total) * 100;
        return {
          label: step.label || (step.type || ('Step ' + (idx + 1))),
          water: step.water_grams || 0,
          start: start,
          end: end,
          delta: delta,
          // ratio as a 0–100 percentage; min-height keeps very-short
          // segments visible.
          ratio: ratio,
          // Precomputed here (not in the template) because the @alpinejs/csp
          // build forbids the `Math` global in template expressions.
          barStyle: 'min-height: 32px; flex-basis: ' + Math.max(ratio, 4) + '%;',
          // 0-based alternating shade — precomputed so the template binds a
          // bare property instead of an inline `idx % 2` expression.
          shadeClass: idx % 2 === 0 ? 'bg-espresso-700' : 'bg-espresso-500',
          // Right-aligned summary string (water + cumulative time).
          summary: (step.water_grams || 0) + 'g · ' + this.formatTime(end),
        };
      });
    },
  }));
});
