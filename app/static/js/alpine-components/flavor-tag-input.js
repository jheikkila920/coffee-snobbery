// Observed-flavor-note tag input — BREW-03, D-09, D-10, D-11.
//
// CLONE of autocomplete.js's `flavorNoteChips` factory, renamed to
// `observedFlavorNotes` and bound to name="flavor_note_ids_observed" (per-
// session, what the user TASTED). ANTI-PATTERN GUARD: this MUST NEVER bind
// advertised_flavor_note_ids (per-coffee, roaster-advertised) — the two
// BIGINT[] → flavor_notes.id relationships mean different things and are kept
// strictly separate (UI-SPEC §Tag Input, RESEARCH §Anti-Patterns).
//
// CSP-build compliant (docs/decisions/0001): registered via Alpine.data, string
// x-data reference, config via data-*; the template binds with :value +
// x-on:input / x-on:click / x-on:keydown (no two-way model binding, no inline
// expressions).
//
// What differs from the Phase-4 advertised widget:
//   - D-09 auto-create: committing (comma / Enter) text that matches no existing
//     note auto-creates a shared flavor_notes row (category="other") via an
//     hx-post to the existing POST /flavor-notes endpoint (as_modal=true). The
//     request goes through htmx.ajax() so the global htmx-listeners.js injects
//     X-CSRF-Token automatically — NO manual fetch, NO hand-set header. The
//     endpoint replies with an empty body + HX-Trigger flavor-note-created
//     {flavor_note_id, name}; the listener below pushes the new chip and flags
//     it isNew=true so the template renders the "new" badge.
//   - D-11 advertised quick-add: server-rendered "Advertised:" suggestion chips
//     live above the input (in the prefill fragment). Tapping one calls
//     addAdvertised(id, name, btnEl) which adds the note to the observed list
//     and dims the suggestion. The suggestion chips are NOT part of this Alpine
//     scope's reactive state (they are server markup that refreshes on the
//     coffee-change hx-get swap); the component only mutates their dimmed class.
//
// Selection commit + keyboard nav mirror flavorNoteChips exactly (Up/Down/Enter/
// Esc + Backspace-removes-last-chip). The visible <input> owns the
// hx-get/hx-trigger/hx-sync attrs for the autocomplete fetch
// (fragments/autocomplete_list.html); this component observes the post-swap DOM
// to commit selections (commitItem) and manage keyboard navigation.

document.addEventListener('alpine:init', () => {
  Alpine.data('observedFlavorNotes', () => ({
    selectedChips: [],
    query: '',
    open: false,
    highlightIdx: -1,
    // Names this component asked the server to auto-create (D-09). When the
    // flavor-note-created event arrives we mark the resulting chip isNew=true
    // and clear the pending entry. Lowercased for citext-style matching.
    _pendingNew: [],

    init() {
      // Server seeds the observed chip list as JSON in data-initial-chips
      // (CSP-safe; the @alpinejs/csp build cannot parse object-literal x-data
      // args). Mirrors flavorNoteChips' seed contract.
      let initialChips = [];
      try {
        initialChips = JSON.parse(this.$root.dataset.initialChips || '[]');
      } catch (_err) {
        initialChips = [];
      }
      this.selectedChips = Array.isArray(initialChips) ? initialChips.slice() : [];

      // The template renders the server seed as static pre-hydration markup
      // ([data-seed-chip] spans + hidden inputs inside
      // [data-seed-hidden-container]). Clear both now so the parallel
      // <template x-for> blocks become the single source of truth (no duplicate
      // visible chips, no duplicate submitted ids).
      const root = this.$root;
      if (root) {
        root.querySelectorAll('[data-seed-chip]').forEach((el) => el.remove());
        const seedHidden = root.querySelector('[data-seed-hidden-container]');
        if (seedHidden) {
          Array.from(seedHidden.children).forEach((child) => {
            if (child.tagName === 'INPUT') child.remove();
          });
        }
      }

      // D-09 + D-16 substrate: the POST /flavor-notes (as_modal=true) reply
      // fires flavor-note-created on document.body. Push the new chip; if we
      // requested its creation, flag it isNew for the "new" badge.
      this._onCreated = (evt) => {
        if (!evt || !evt.detail) return;
        const id = evt.detail.flavor_note_id;
        const name = evt.detail.name;
        if (id == null) return;
        // De-dupe (typo + create race): if already a chip, just clear input.
        if (this.selectedChips.some((c) => c.id === id)) {
          this.query = '';
          this.open = false;
          return;
        }
        const lower = (name || '').toLowerCase();
        const pendingIdx = this._pendingNew.indexOf(lower);
        const isNew = pendingIdx !== -1;
        if (pendingIdx !== -1) this._pendingNew.splice(pendingIdx, 1);
        this.selectedChips.push({ id: id, name: name, isNew: isNew });
        this.query = '';
        this.open = false;
      };
      document.body.addEventListener('flavor-note-created', this._onCreated);
    },

    destroy() {
      document.body.removeEventListener('flavor-note-created', this._onCreated);
    },

    addChip(id, name) {
      if (this.selectedChips.some((c) => c.id === id)) {
        this.query = '';
        this.open = false;
        return;
      }
      this.selectedChips.push({ id: id, name: name, isNew: false });
      this.query = '';
      this.open = false;
      this.highlightIdx = -1;
    },

    // Commit a dropdown <li> selection (D-10 link-on-exact-match). Reads
    // id+name off the clicked element's data-* (set by autocomplete_list.html).
    commitItem(el) {
      const id = parseInt(el.dataset.itemId, 10);
      if (!Number.isFinite(id)) return;
      this.addChip(id, el.dataset.itemName || '');
    },

    // D-11 quick-add: tapping an "Advertised:" suggestion chip adds the note to
    // the observed list and dims the suggestion so it isn't double-added. The
    // suggestion button is server markup, so we just toggle its disabled/dim
    // state directly (it carries data-advertised-id / data-advertised-name).
    addAdvertised(el) {
      const id = parseInt(el.dataset.advertisedId, 10);
      if (!Number.isFinite(id)) return;
      this.addChip(id, el.dataset.advertisedName || '');
      el.classList.add('opacity-40', 'pointer-events-none');
      el.setAttribute('aria-disabled', 'true');
    },

    removeChip(id) {
      this.selectedChips = this.selectedChips.filter((c) => c.id !== id);
    },

    onInput(el) {
      this.query = el.value;
      this.open = this.query.length >= 2;
      this.highlightIdx = -1;
    },

    onFocus() {
      if (this.query.length >= 2) this.open = true;
    },

    onBlur() {
      setTimeout(() => {
        this.open = false;
      }, 150);
    },

    // D-09 auto-create on no-match. Called when the user commits typed text
    // (comma / Enter) and the dropdown has no exact match: fire an hx-post to
    // create the shared note, then the flavor-note-created listener pushes the
    // chip with the "new" badge. Going through htmx.ajax() means the global
    // htmx:configRequest handler attaches X-CSRF-Token — no manual fetch.
    createFromQuery() {
      const name = this.query.trim();
      if (name === '') return;
      // If it already exists as a chip, no-op.
      if (this.selectedChips.some((c) => (c.name || '').toLowerCase() === name.toLowerCase())) {
        this.query = '';
        this.open = false;
        return;
      }
      this._pendingNew.push(name.toLowerCase());
      // as_modal=true → the endpoint replies with an empty body + the
      // flavor-note-created HX-Trigger (no row fragment swap). category="other"
      // per D-09. htmx.ajax injects the CSRF header via the global listener.
      htmx.ajax('POST', '/flavor-notes', {
        values: { name: name, category: 'other', as_modal: 'true' },
        swap: 'none',
      });
      this.query = '';
      this.open = false;
    },

    onKeydown(e) {
      const wrapper = e.currentTarget.closest('.field');
      if (!wrapper) return;
      const items = wrapper.querySelectorAll('[role="option"]');
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        this.highlightIdx = Math.min(this.highlightIdx + 1, items.length - 1);
        this._applyHighlight(items);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        this.highlightIdx = Math.max(this.highlightIdx - 1, 0);
        this._applyHighlight(items);
      } else if (e.key === 'Enter' || e.key === ',') {
        // Comma OR Enter commits (UI-SPEC). A highlighted dropdown item wins
        // (link-on-exact / explicit pick); otherwise auto-create from the query.
        e.preventDefault();
        if (this.highlightIdx >= 0 && items[this.highlightIdx]) {
          items[this.highlightIdx].click();
        } else if (this.query.trim() !== '') {
          this.createFromQuery();
        }
      } else if (e.key === 'Escape') {
        this.open = false;
        this.highlightIdx = -1;
      } else if (e.key === 'Backspace' && this.query === '' && this.selectedChips.length > 0) {
        e.preventDefault();
        this.selectedChips.pop();
      }
    },

    _applyHighlight(items) {
      items.forEach((it, i) => {
        if (i === this.highlightIdx) {
          it.classList.add('bg-cream-200', 'dark:bg-espresso-700');
        } else {
          it.classList.remove('bg-cream-200', 'dark:bg-espresso-700');
        }
      });
    },
  }));
});
