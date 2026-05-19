// Autocomplete Alpine components (D-13 + D-14 + D-16).
//
// Two factories:
//   - autocomplete         — single-value picker (coffee form's roaster
//                            input; bound to a hidden roaster_id input).
//   - flavorNoteChips      — multi-value chip widget (coffee form's
//                            advertised_flavor_note_ids list). Each chip
//                            mirrors a sibling hidden input via parallel
//                            <template x-for> blocks; FastAPI collects
//                            the repeated form keys via
//                            `Form(default_factory=list)` natively (plan
//                            04-07 contract).
//
// Both components:
//   - Read keyboard ArrowUp / ArrowDown / Enter / Escape on the input
//     (UI-SPEC §Autocomplete Dropdown).
//   - Listen for HX-Trigger {entity}-created CustomEvents on
//     document.body → commit the new entity (D-16 pre-select).
//   - Are CSP-build compliant: registered via Alpine.data with string
//     references; templates bind via :value + @input + x-on:keydown
//     (x-model is banned).
//
// HTMX integration:
//   - The visible <input> still owns the hx-get/hx-trigger/hx-sync attrs
//     for the actual fetch. The Alpine component only observes the
//     DOM-after-swap to commit selections + manage keyboard navigation.
//   - Alpine binds to dropdown <li role="option"> elements via the
//     global htmx:afterSettle → Alpine.initTree hook (htmx-listeners.js).

document.addEventListener('alpine:init', () => {
  // --------------------------------------------------------------------- //
  // Single-value autocomplete (roaster input on the coffee form).         //
  // --------------------------------------------------------------------- //
  Alpine.data('autocomplete', () => ({
    entityKey: '',
    hiddenInputName: '',
    selectedId: null,
    selectedLabel: '',
    query: '',
    open: false,
    highlightIdx: -1,

    init() {
      // Config comes from data-* attributes on the wrapper (CSP-safe — the
      // @alpinejs/csp build cannot parse object-literal x-data arguments;
      // this mirrors recipeStepBuilder's data-initial-steps pattern).
      const ds = this.$root.dataset;
      this.entityKey = ds.entityKey || '';
      this.hiddenInputName = ds.hiddenInputName || '';
      const rawId = parseInt(ds.initialId, 10);
      this.selectedId = Number.isFinite(rawId) ? rawId : null;
      this.selectedLabel = ds.initialName || '';
      this.query = this.selectedLabel;

      // D-16: HX-Trigger {entity}-created → pre-select. The payload key
      // for the id follows the {entity_with_underscores}_id convention
      // (roaster → roaster_id; flavor-note → flavor_note_id) — locked by
      // plan 04-04 (roasters) + plan 04-05 (flavor notes) HX-Trigger
      // payload contracts.
      const eventName = this.entityKey + '-created';
      const idKey = this.entityKey.replace(/-/g, '_') + '_id';
      this._onCreated = (evt) => {
        if (!evt || !evt.detail) return;
        this.selectedId = evt.detail[idKey];
        this.selectedLabel = evt.detail.name;
        this.query = evt.detail.name;
        this.open = false;
      };
      document.body.addEventListener(eventName, this._onCreated);
    },

    destroy() {
      const eventName = this.entityKey + '-created';
      document.body.removeEventListener(eventName, this._onCreated);
    },

    onInput(el) {
      this.query = el.value;
      this.open = this.query.length >= 2;
      this.highlightIdx = -1;
      // If the user mutates the visible text away from the committed
      // selection, the hidden FK id is no longer valid — clear it so
      // the form submits null and the server validates per the schema.
      if (el.value !== this.selectedLabel) {
        this.selectedId = null;
      }
    },

    onFocus() {
      if (this.query.length >= 2) {
        this.open = true;
      }
    },

    onBlur() {
      // Delay so a click on a dropdown <li> fires before the dropdown
      // collapses (the click handler needs the element to still be in
      // the DOM tree).
      setTimeout(() => {
        this.open = false;
      }, 150);
    },

    select(id, label) {
      this.selectedId = id;
      this.selectedLabel = label;
      this.query = label;
      this.open = false;
      this.highlightIdx = -1;
    },

    // Uniform dropdown-item commit: reads id+name off the clicked <li>'s
    // data-* attributes (set by autocomplete_list.html) so the template
    // handler stays a CSP-safe `commitItem($el)` with no string literals.
    commitItem(el) {
      const id = parseInt(el.dataset.itemId, 10);
      this.select(Number.isFinite(id) ? id : null, el.dataset.itemName || '');
    },

    onKeydown(e) {
      // The dropdown <ul> is rendered as a sibling of the input inside
      // the wrapper. Read its <li role="option"> children for keyboard
      // navigation. The "+ Create new" affordance is included by design
      // — Enter on it triggers an HTMX request via its hx-get.
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
      } else if (e.key === 'Enter') {
        if (this.highlightIdx >= 0 && items[this.highlightIdx]) {
          e.preventDefault();
          items[this.highlightIdx].click();
        }
      } else if (e.key === 'Escape') {
        this.open = false;
        this.highlightIdx = -1;
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

  // --------------------------------------------------------------------- //
  // Multi-value chip widget (advertised_flavor_note_ids on coffee form).  //
  //                                                                       //
  // Locked deliverable per plan 04-11: maintain a selectedChips array;    //
  // render via TWO parallel <template x-for> blocks (visible chips +      //
  // hidden inputs) so every chip has a matching hidden input sibling at   //
  // submit time. FastAPI's Form(default_factory=list) collects the        //
  // repeated keys natively — no comma-separated string fallback.          //
  // --------------------------------------------------------------------- //
  Alpine.data('flavorNoteChips', () => ({
    selectedChips: [],
    query: '',
    open: false,
    highlightIdx: -1,

    init() {
      // Server seeds the chip list via the form context's
      // `selected_flavor_notes` list of {id, name} dicts so the form
      // survives a 200 validation re-render BEFORE Alpine hydrates
      // (plan 04-07 contract). Passed as JSON in data-initial-chips
      // (CSP-safe — the @alpinejs/csp build cannot parse object-literal
      // x-data arguments; mirrors recipeStepBuilder's data-* pattern).
      let initialChips = [];
      try {
        initialChips = JSON.parse(this.$root.dataset.initialChips || '[]');
      } catch (_err) {
        initialChips = [];
      }
      this.selectedChips = Array.isArray(initialChips)
        ? initialChips.slice()
        : [];

      // Plan 04-11: the form fragment also renders the server seed as
      // static no-JS / pre-hydration markup (see coffee_form.html):
      //   - `<span data-seed-chip>` siblings in #flavor-note-chip-list
      //   - `<input type="hidden" name="advertised_flavor_note_ids">`
      //     children of `<div data-seed-hidden-container>` (the static
      //     hidden inputs MUST NOT carry extra attributes — plan 04-07's
      //     test contract pins their exact HTML string).
      // Clear both seed locations now so the parallel <template x-for>
      // blocks become the single source of truth post-hydration (no
      // duplicate visible chips, no duplicate submitted ids).
      const root = this.$root;
      if (root) {
        root.querySelectorAll('[data-seed-chip]').forEach((el) => el.remove());
        const seedHidden = root.querySelector('[data-seed-hidden-container]');
        if (seedHidden) {
          // Remove only the direct <input> children — the <template>
          // placeholder for x-for stays so Alpine can populate from it.
          Array.from(seedHidden.children).forEach((child) => {
            if (child.tagName === 'INPUT') {
              child.remove();
            }
          });
        }
      }

      this._onCreated = (evt) => {
        if (!evt || !evt.detail) return;
        const id = evt.detail.flavor_note_id;
        const name = evt.detail.name;
        if (id == null) return;
        // De-dupe: if this id is already a chip (user typo + create-new
        // race), do nothing.
        if (this.selectedChips.some((c) => c.id === id)) {
          this.query = '';
          this.open = false;
          return;
        }
        this.selectedChips.push({ id: id, name: name });
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
        // Already added; just clear the query.
        this.query = '';
        this.open = false;
        return;
      }
      this.selectedChips.push({ id: id, name: name });
      this.query = '';
      this.open = false;
      this.highlightIdx = -1;
    },

    // Uniform dropdown-item commit (mirrors autocomplete.commitItem): reads
    // id+name off the clicked <li>'s data-* attributes so the template
    // handler stays a CSP-safe `commitItem($el)`.
    commitItem(el) {
      const id = parseInt(el.dataset.itemId, 10);
      if (!Number.isFinite(id)) return;
      this.addChip(id, el.dataset.itemName || '');
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
      if (this.query.length >= 2) {
        this.open = true;
      }
    },

    onBlur() {
      setTimeout(() => {
        this.open = false;
      }, 150);
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
      } else if (e.key === 'Enter') {
        if (this.highlightIdx >= 0 && items[this.highlightIdx]) {
          e.preventDefault();
          items[this.highlightIdx].click();
        }
      } else if (e.key === 'Escape') {
        this.open = false;
        this.highlightIdx = -1;
      } else if (e.key === 'Backspace' && this.query === '' && this.selectedChips.length > 0) {
        // Quality-of-life: backspace at empty query removes the last chip.
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
