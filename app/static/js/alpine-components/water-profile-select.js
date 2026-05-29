// Water profile inline select-or-create — GBREW-04, D-02, D-04.
//
// Bound to name="water_profile_id" in brew_prefill_fields.html via
// x-data="waterProfileSelect". Profiles are seeded from the server-rendered
// data-initial-profiles JSON attr (CSP-safe — no object-literal x-data args
// in the @alpinejs/csp build). The selected profile id is tracked in profileId
// and drives the <select> :selected binding.
//
// Inline create flow (D-02):
//   1. User picks "Add new…" → showCreate=true, select hidden
//   2. User types name + optional notes → saveProfile() calls htmx.ajax()
//   3. POST /water-profiles succeeds → server fires HX-Trigger water-profile-created
//   4. _onCreated listener pushes new profile, sets profileId, hides create form
//
// CSRF: htmx.ajax() goes through htmx:configRequest in htmx-listeners.js which
// injects X-CSRF-Token from the meta[name="csrf-token"] tag automatically.
// No manual fetch(), no manual header. Mirrors flavor-tag-input.js createFromQuery().
//
// CSP-build compliant (docs/decisions/0001): registered via Alpine.data, string
// x-data reference, config via data-*; template binds with :value / x-on:change
// (no two-way x-model, no inline expressions that Alpine CSP can't evaluate).

document.addEventListener('alpine:init', () => {
  Alpine.data('waterProfileSelect', () => ({
    profiles: [],
    profileId: null,
    showCreate: false,
    createError: '',

    init() {
      // Seed profiles from server-rendered JSON attr (single-quoted, |tojson safe)
      try {
        this.profiles = JSON.parse(this.$root.dataset.initialProfiles || '[]');
      } catch (_err) {
        this.profiles = [];
      }
      // Seed initial selection (edit mode pre-fill / GBM path)
      const raw = this.$root.dataset.initialValue || '';
      this.profileId = raw !== '' ? raw : null;

      // HX-Trigger listener — mirrors flavor-tag-input.js lines 79-98.
      // Fired by POST /water-profiles on success (water-profile-created event).
      this._onCreated = (evt) => {
        if (!evt || !evt.detail) return;
        const { water_profile_id, name } = evt.detail;
        if (water_profile_id == null) return;
        // De-dupe: if profile already in list (double-submit race), just select it.
        if (!this.profiles.some((p) => p.id === water_profile_id)) {
          this.profiles.push({ id: water_profile_id, name: name });
        }
        this.profileId = water_profile_id;
        this.showCreate = false;
        this.createError = '';
      };
      document.body.addEventListener('water-profile-created', this._onCreated);
    },

    destroy() {
      document.body.removeEventListener('water-profile-created', this._onCreated);
    },

    onSelectChange(v) {
      if (v === '__new__') {
        this.showCreate = true;
        this.profileId = null;
      } else {
        this.showCreate = false;
        this.profileId = v || null;
      }
    },

    saveProfile() {
      const name = ((this.$refs.newName && this.$refs.newName.value) || '').trim();
      if (!name) {
        this.createError = 'Profile name is required.';
        return;
      }
      const notes = (this.$refs.newNotes && this.$refs.newNotes.value) || '';
      this.createError = '';
      // htmx.ajax goes through htmx-listeners.js → X-CSRF-Token injected automatically
      // (mirrors flavor-tag-input.js createFromQuery() lines 175-180)
      htmx.ajax('POST', '/water-profiles', {
        values: { name: name, notes: notes },
        swap: 'none',
      });
    },
  }));
});
