// account-dropdown.js — accountDropdown Alpine component (Phase 11 / Plan 03).
//
// Manages the account dropdown in the top horizontal nav (>=768px).
// Shows username + "Sign out" CSRF POST. Closes on ESC or click-outside.
//
// CSP-build compliant: registered via Alpine.data('accountDropdown', ...) inside
// the 'alpine:init' event; the trigger element carries x-data="accountDropdown"
// (string reference — the @alpinejs/csp build rejects inline object literals).
// No eval, no dynamic functions — all handlers are declarative Alpine attributes.
//
// Lifecycle:
//   1. base.html loads this file before the @alpinejs/csp core (script ordering).
//   2. Alpine boots and walks the DOM; the trigger button's parent carries
//      x-data="accountDropdown" and initialises with open: false.
//   3. Click trigger → toggle(). ESC key → close(). Click outside → onBackdropClick().
//   4. Destroy cleans up the window keydown listener.

document.addEventListener('alpine:init', () => {
  Alpine.data('accountDropdown', () => ({
    open: false,

    init() {
      // ESC closes the dropdown. Registered on window (not the component root)
      // so it fires even when focus is inside the dropdown panel.
      this._onKeydown = (e) => {
        if (e.key === 'Escape' && this.open) {
          this.open = false;
        }
      };
      window.addEventListener('keydown', this._onKeydown);
    },

    destroy() {
      // Remove listener to prevent memory leaks when the component is torn down.
      window.removeEventListener('keydown', this._onKeydown);
    },

    toggle() { this.open = !this.open; },
    close() { this.open = false; },

    onBackdropClick(e) {
      // Only close when the click hit the backdrop itself (the bound element),
      // not a descendant that bubbled up — mirrors mini-modal.js pattern.
      if (e.target === e.currentTarget) {
        this.close();
      }
    },
  }));
});
