// dark-toggle.js — darkToggle Alpine component (Phase 13 / Plan 05 C4).
//
// 3-state Auto/Light/Dark theme toggle. Persists choice in localStorage
// under the key 'snobbery:theme'. Manipulates document.documentElement
// classList directly so the no-FOUC head script and this component stay
// in sync via the same key + the same .dark class.
//
// CSP-build compliant (docs/decisions/0001): registered via Alpine.data()
// inside the 'alpine:init' event; HTML carries x-data="darkToggle" (string
// reference — @alpinejs/csp build rejects inline object literals).
// No eval, no dynamic functions, no x-model.
//
// Lifecycle:
//   1. base.html loads this file before the @alpinejs/csp core (script ordering).
//   2. Alpine boots; any element with x-data="darkToggle" initialises with
//      theme = localStorage 'snobbery:theme' || 'auto'.
//   3. User clicks Auto/Light/Dark button → setTheme(val) applies the class
//      immediately and persists to localStorage.
//   4. isActive(val) returns true when val === this.theme (for :class styling).

document.addEventListener('alpine:init', () => {
  Alpine.data('darkToggle', function () {
    return {
      theme: (function () {
        try {
          return localStorage.getItem('snobbery:theme') || 'auto';
        } catch (_e) {
          return 'auto';
        }
      })(),

      setTheme: function (val) {
        this.theme = val;
        if (val === 'auto') {
          try {
            localStorage.removeItem('snobbery:theme');
          } catch (_e) { /* private mode / quota — silent */ }
          if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
            document.documentElement.classList.add('dark');
          } else {
            document.documentElement.classList.remove('dark');
          }
        } else if (val === 'dark') {
          try {
            localStorage.setItem('snobbery:theme', 'dark');
          } catch (_e) { /* private mode / quota — silent */ }
          document.documentElement.classList.add('dark');
        } else {
          // 'light'
          try {
            localStorage.setItem('snobbery:theme', 'light');
          } catch (_e) { /* private mode / quota — silent */ }
          document.documentElement.classList.remove('dark');
        }
      },

      isActive: function (val) {
        return this.theme === val;
      },
    };
  });
});
