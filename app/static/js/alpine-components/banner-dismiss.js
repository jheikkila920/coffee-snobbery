// banner-dismiss.js — bannerDismiss Alpine component (Phase 17 / Plan 17-03).
//
// DIST-07 banner dismiss — sessionStorage-backed (NOT persistent across tab
// close). Mirrors ios-banner.js but uses sessionStorage so the banner
// reappears on the next visit until at least one AI key is configured (D-19).
// CSP-build compliant:
// Alpine.data registered inside the 'alpine:init' event; banner div carries
// x-data="bannerDismiss" (string reference — @alpinejs/csp rejects inline
// object literals).

document.addEventListener('alpine:init', () => {
  Alpine.data('bannerDismiss', () => ({
    dismissed: false,

    init() {
      // sessionStorage clears on tab close → banner reappears next visit
      // until at least one ApiCredential resolves on the server side.
      this.dismissed = sessionStorage.getItem('snobbery:dist07-dismissed') === '1';
    },

    dismiss() {
      this.dismissed = true;
      try {
        sessionStorage.setItem('snobbery:dist07-dismissed', '1');
      } catch (_e) {
        // Private mode or quota exceeded — banner will reappear on next
        // navigation in this tab, which is acceptable. No user-visible error.
      }
    },
  }));
});
