// Search bar Alpine component (Phase 10 / Plan 03).
//
// Manages the mobile full-screen sheet for the persistent search header.
// Desktop mode (>=768px) is always visible; mobile mode shows a magnifying-glass
// icon that opens a full-screen sheet.
//
// CSP-build compliant: registered via Alpine.data('searchBar', ...) inside
// the 'alpine:init' event; the header element carries x-data="searchBar"
// (string reference — the @alpinejs/csp build rejects inline object literals).
// No eval, no new Function — all handlers are declarative Alpine attributes.
//
// Lifecycle:
//   1. base.html loads this file before the @alpinejs/csp core (script ordering).
//   2. Alpine boots and walks the DOM; the <header x-data="searchBar"> element
//      initialises this component with sheetOpen: false.
//   3. Mobile: tap the magnifying-glass icon → openSheet() → auto-focus input.
//   4. Close: X button, Esc key (window keydown listener), or backdrop click.

document.addEventListener('alpine:init', () => {
  Alpine.data('searchBar', () => ({
    sheetOpen: false,

    init() {
      // ESC closes the mobile sheet. Registered on window (not the component
      // root) so it fires even when focus is inside the sheet's input.
      this._onKeydown = (e) => {
        if (e.key === 'Escape' && this.sheetOpen) {
          this.closeSheet();
        }
      };
      window.addEventListener('keydown', this._onKeydown);
    },

    destroy() {
      // Remove listener to prevent memory leaks when the component is torn down.
      window.removeEventListener('keydown', this._onKeydown);
    },

    openSheet() {
      this.sheetOpen = true;
      // Auto-focus the sheet input after Alpine renders the x-show element.
      this.$nextTick(() => {
        const input = this.$root.querySelector('[data-sheet-input]');
        if (input) {
          input.focus();
        }
      });
    },

    closeSheet() {
      this.sheetOpen = false;
      // Clear the sheet input value so a reopened sheet starts clean (UI-SPEC).
      const input = this.$root.querySelector('[data-sheet-input]');
      if (input) {
        input.value = '';
      }
      // Clear the sheet results container innerHTML (UI-SPEC closeSheet contract).
      const results = this.$root.querySelector('[data-sheet-results]');
      if (results) {
        results.innerHTML = '';
      }
    },
  }));
});
