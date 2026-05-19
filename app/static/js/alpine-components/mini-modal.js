// Mini-modal Alpine component (D-15).
//
// Open / close + ESC + backdrop-click + dirty-check + HX-Trigger-driven
// close-on-success. CSP-build compliant: registered via Alpine.data; the
// modal-body fragment carries x-data="miniModal" (string reference, not
// an inline object literal — eval is banned per CSP and the
// @alpinejs/csp build rejects it at parse time).
//
// Lifecycle:
//   1. Parent autocomplete dropdown's "+ Create new" <li role="option">
//      fires `hx-get /{entity}/new?as_modal=true` → server returns the
//      modal-body fragment → HTMX swaps it into #modal-mount.
//   2. Alpine boots the new subtree (the global htmx:afterSettle hook in
//      htmx-listeners.js calls Alpine.initTree on every settled target),
//      so the miniModal component initialises with `open: true`.
//   3. ESC key or backdrop click → close(). Dirty flag → confirm prompt.
//   4. Successful POST: server returns 200 + empty body + HX-Trigger:
//      {entity}-created header. HTMX dispatches the CustomEvent on
//      document.body; the global listener below empties #modal-mount,
//      which destroys the Alpine component along with its DOM.
//
// LOCKED MECHANISM (plan 04-11 N1): modal close == emptying #modal-mount
// from the global roaster-created / flavor-note-created listeners. The
// fragile `modal._alpineState.open = false` path was rejected — Alpine
// does not expose component state via a stable public property. The
// empty-mount path is deterministic: server emits HX-Trigger → HTMX
// dispatches the event → listener empties the mount. The Alpine
// component itself never has to "know" the entity was created; its DOM
// is just removed.

document.addEventListener('alpine:init', () => {
  Alpine.data('miniModal', () => ({
    open: true,
    dirty: false,

    init() {
      // ESC closes the modal (UI-SPEC §Mini-Modal). Registered on window
      // (not the component root) because focus may have moved into the
      // form and a keydown on a child input still bubbles to the window.
      this._onKeydown = (e) => {
        if (e.key === 'Escape' && this.open) {
          this.close();
        }
      };
      window.addEventListener('keydown', this._onKeydown);
    },

    destroy() {
      window.removeEventListener('keydown', this._onKeydown);
    },

    close() {
      if (this.dirty && !window.confirm('Discard unsaved changes?')) {
        return;
      }
      this.open = false;
      this.dirty = false;
      const mount = document.getElementById('modal-mount');
      if (mount) {
        mount.innerHTML = '';
      }
    },

    markDirty() {
      this.dirty = true;
    },

    onBackdropClick(e) {
      // Only close when the click hit the backdrop itself (the bound
      // element), not a descendant that bubbled up. The modal panel
      // stops propagation via x-on:click.stop in the template.
      if (e.target === e.currentTarget) {
        this.close();
      }
    },
  }));
});

// Global HTMX-event consumers: empty #modal-mount when the server emits
// HX-Trigger: {entity}-created. The parent coffee form's autocomplete
// component owns the pre-select side; this side just tears the modal
// down. Both listeners are idempotent — if the mount is already empty,
// `innerHTML = ''` is a no-op.
document.body.addEventListener('roaster-created', () => {
  const mount = document.getElementById('modal-mount');
  if (mount) {
    mount.innerHTML = '';
  }
});

document.body.addEventListener('flavor-note-created', () => {
  const mount = document.getElementById('modal-mount');
  if (mount) {
    mount.innerHTML = '';
  }
});
