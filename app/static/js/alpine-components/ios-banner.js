// ios-banner.js — iosBanner Alpine component (Phase 11 / Plan 03).
//
// Shows a "Add to Home Screen" install banner on iOS Safari when the app is
// not already running in standalone (home screen) mode. One-time show per
// device: dismissal is stored in localStorage key 'snobbery:ios-banner-dismissed'.
//
// CSP-build compliant: registered via Alpine.data('iosBanner', ...) inside
// the 'alpine:init' event; the banner div carries x-data="iosBanner"
// (string reference — the @alpinejs/csp build rejects inline object literals).
// No eval, no dynamic functions — all handlers are declarative Alpine attributes.
//
// Lifecycle:
//   1. base.html loads this file before the @alpinejs/csp core (script ordering).
//   2. Alpine boots and walks the DOM; the banner div initialises with show: false.
//   3. init() checks localStorage + UA. On iOS Safari non-standalone: show = true.
//   4. Tap dismiss button → dismiss() → hide + write localStorage flag.

document.addEventListener('alpine:init', () => {
  Alpine.data('iosBanner', () => ({
    show: false,

    init() {
      // Already dismissed — never show again.
      if (localStorage.getItem('snobbery:ios-banner-dismissed')) return;

      // Detect iOS Safari (non-standard navigator.standalone is iOS-only).
      const isIOS = /iPhone|iPad|iPod/.test(navigator.userAgent);
      // navigator.standalone is true when launched from iOS home screen.
      // matchMedia display-mode covers Chrome on Android and future-proofing.
      const isStandalone = window.navigator.standalone === true ||
                           window.matchMedia('(display-mode: standalone)').matches;

      if (isIOS && !isStandalone) {
        this.show = true;
      }
    },

    dismiss() {
      this.show = false;
      try {
        localStorage.setItem('snobbery:ios-banner-dismissed', '1');
      } catch (_e) {
        // Private mode or quota exceeded — banner will reappear next visit,
        // which is acceptable. No user-visible error.
      }
    },
  }));
});
