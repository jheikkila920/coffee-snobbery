// nav-bar.js — navBar Alpine component (Phase 11 / Plan 03).
//
// Manages the active-tab state for the persistent bottom nav bar (<768px)
// and the nav links in the top header (>=768px). Active tab is derived from
// window.location.pathname via simple startsWith comparisons — no eval.
//
// CSP-build compliant: registered via Alpine.data('navBar', ...) inside
// the 'alpine:init' event; the nav element carries x-data="navBar"
// (string reference — the @alpinejs/csp build rejects inline object literals).
// No eval, no dynamic functions — all handlers are declarative Alpine attributes.
//
// Lifecycle:
//   1. base.html loads this file before the @alpinejs/csp core (script ordering).
//   2. Alpine boots and walks the DOM; the <nav x-data="navBar"> element
//      initialises this component.
//   3. activeTab getter is re-evaluated on each Alpine binding check.
//   4. x-bind:class in the template reads activeTab to apply active styles.

document.addEventListener('alpine:init', () => {
  Alpine.data('navBar', () => ({
    // active tab derived from pathname — no eval needed
    get activeTab() {
      const p = window.location.pathname;
      if (p === '/' || p.startsWith('/home')) return 'home';
      if (p.startsWith('/brew')) return 'brew';
      if (p.startsWith('/config') || p.startsWith('/coffees') ||
          p.startsWith('/equipment') || p.startsWith('/recipes') ||
          p.startsWith('/roasters') || p.startsWith('/flavor-notes')) return 'config';
      if (p.startsWith('/admin')) return 'admin';
      return '';
    },
  }));
});
