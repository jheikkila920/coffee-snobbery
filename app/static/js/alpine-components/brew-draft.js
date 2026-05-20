// Brew draft persistence — BREW-06, BREW-07, MX-5 (and the prefill touched-
// state that drives the D-04/D-05 pills).
//
// CSP-build compliant (docs/decisions/0001): registered via Alpine.data, string
// x-data reference, config via data-*. No two-way model binding, no inline
// expressions.
//
// Scope: /brew/new ONLY. The edit form is never draft-backed.
//
// Responsibilities:
//   1. localStorage primary store, namespaced per user:
//      snobbery:draft:brew:<user_id> (MX-5 — a shared phone never leaks one
//      user's draft to another). Written on every form input change (BREW-06),
//      including the D-02 disclosure open/closed flag.
//   2. Server autosave backstop: on field blur, POST the serialized payload to
//      /brew/draft (iOS ITP 7-day-eviction backstop). The request goes through
//      htmx.ajax() so the global htmx-listeners.js injects X-CSRF-Token — NO
//      raw fetch, NO hand-set header (T-05-21).
//   3. Reconciliation (BREW-07): on init(), restore from localStorage if
//      present; else fall back to the server draft (data-server-draft JSON).
//   4. Per-field touched-state: a delegated input/change listener removes the
//      prefill pill ([data-prefill-pill="<field>"]) for any field the user
//      edits, so a prefilled-untouched value drops its "from last brew" caption
//      the moment it's touched (UI-SPEC §Prefill Indicators).
//   5. Clear the namespaced localStorage key on successful submit.

document.addEventListener('alpine:init', () => {
  Alpine.data('brewDraft', () => ({
    storageKey: '',
    restored: false,

    init() {
      const ds = this.$root.dataset;
      const userId = ds.userId || 'anon';
      this.storageKey = 'snobbery:draft:brew:' + userId;

      // The <form> this scope wraps. All field reads/writes operate on it.
      this._form = this.$root.querySelector('form') || this.$root;

      // BREW-07 reconciliation: localStorage primary, server fallback.
      let draft = this._readLocal();
      if (draft === null) {
        draft = this._readServer(ds.serverDraft);
      }
      if (draft && typeof draft === 'object') {
        this._applyDraft(draft);
        this.restored = true;
      }

      // BREW-06: persist to localStorage on every input change; autosave to the
      // server on blur. Delegated on the form so dynamically-swapped prefill
      // fields (the coffee/recipe re-prefill) are covered too.
      this._onInput = (e) => {
        this._clearPillFor(e.target);
        this._writeLocal();
      };
      this._onBlur = (e) => {
        if (this._isFormField(e.target)) this._autosave();
      };
      this._form.addEventListener('input', this._onInput);
      this._form.addEventListener('change', this._onInput);
      // Blur bubbles only in capture phase.
      this._form.addEventListener('blur', this._onBlur, true);

      // Clear the namespaced draft on a successful submit. The router responds
      // 204 + HX-Redirect, so htmx:beforeRequest on the form's POST is the
      // reliable "user submitted" signal (the redirect tears down the page).
      this._onSubmit = () => this.clearDraft();
      this._form.addEventListener('submit', this._onSubmit);
    },

    destroy() {
      if (!this._form) return;
      this._form.removeEventListener('input', this._onInput);
      this._form.removeEventListener('change', this._onInput);
      this._form.removeEventListener('blur', this._onBlur, true);
      this._form.removeEventListener('submit', this._onSubmit);
    },

    _isFormField(el) {
      if (!el || !el.tagName) return false;
      const tag = el.tagName.toUpperCase();
      return (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') && !!el.name;
    },

    // Serialize the form's named fields into a plain object. Repeated keys
    // (flavor_note_ids_observed) collect into an array. The D-02 disclosure
    // open flag rides along under a synthetic key so a restore reopens it.
    _serialize() {
      const out = {};
      if (!this._form || !this._form.elements) return out;
      Array.from(this._form.elements).forEach((el) => {
        if (!this._isFormField(el)) return;
        if (el.name === 'X-CSRF-Token') return;
        if (out[el.name] === undefined) {
          out[el.name] = el.value;
        } else if (Array.isArray(out[el.name])) {
          out[el.name].push(el.value);
        } else {
          out[el.name] = [out[el.name], el.value];
        }
      });
      const details = this._form.querySelector('details');
      if (details) out.__disclosure_open = details.open ? '1' : '0';
      return out;
    },

    _applyDraft(draft) {
      if (!this._form || !this._form.elements) return;
      Object.keys(draft).forEach((key) => {
        if (key === '__disclosure_open') {
          const details = this._form.querySelector('details');
          if (details) details.open = draft[key] === '1';
          return;
        }
        const els = this._form.elements[key];
        if (!els) return;
        const value = draft[key];
        // RadioNodeList / repeated keys: best-effort single-value restore for
        // scalar fields (the chip widget owns its own seed for the array case).
        if (els.value !== undefined && !Array.isArray(value)) {
          els.value = value;
        }
      });
    },

    _readLocal() {
      try {
        const raw = window.localStorage.getItem(this.storageKey);
        return raw ? JSON.parse(raw) : null;
      } catch (_err) {
        return null;
      }
    },

    _writeLocal() {
      try {
        window.localStorage.setItem(this.storageKey, JSON.stringify(this._serialize()));
      } catch (_err) {
        /* quota / private mode — server autosave is the backstop. */
      }
    },

    _readServer(raw) {
      if (!raw) return null;
      try {
        const parsed = JSON.parse(raw);
        return parsed && typeof parsed === 'object' ? parsed : null;
      } catch (_err) {
        return null;
      }
    },

    // Server autosave (BREW-07 backstop). htmx.ajax → the global
    // htmx:configRequest listener attaches X-CSRF-Token. Silent (the router
    // replies 204; nothing swaps).
    _autosave() {
      const payload = this._serialize();
      try {
        htmx.ajax('POST', '/brew/draft', {
          values: payload,
          swap: 'none',
        });
      } catch (_err) {
        /* network hiccup — localStorage already holds the canonical draft. */
      }
    },

    _clearPillFor(el) {
      if (!this._isFormField(el)) return;
      const pill = this.$root.querySelector('[data-prefill-pill="' + el.name + '"]');
      if (pill) pill.remove();
    },

    // Discard the restored draft and start blank, staying on /brew/new
    // (UI-SPEC §Draft Persistence — the inline restore-notice "Discard").
    discard() {
      this.clearDraft();
      this._clearServerDraft();
      if (this._form && typeof this._form.reset === 'function') this._form.reset();
      this.restored = false;
    },

    // Abandon the in-progress form entirely and navigate away (the sticky-bar
    // "Discard changes" on /brew/new). Wipes localStorage + the server backstop,
    // then leaves the page. The sessions list (/brew) is a later plan's route, so
    // we navigate home ("/"). The localStorage clear is synchronous and
    // authoritative for BREW-07 reconciliation; the server clear is best-effort.
    discardAndLeave() {
      this.clearDraft();
      this._clearServerDraft();
      window.location.assign('/');
    },

    clearDraft() {
      try {
        window.localStorage.removeItem(this.storageKey);
      } catch (_err) {
        /* nothing to do */
      }
    },

    // Delete the server backstop draft (POST /brew/draft/clear). Routed through
    // htmx.ajax so the global htmx:configRequest listener attaches X-CSRF-Token
    // (T-05-21) — no raw fetch, no hand-set header. Best-effort: localStorage is
    // the canonical reconciliation source.
    _clearServerDraft() {
      try {
        htmx.ajax('POST', '/brew/draft/clear', { swap: 'none' });
      } catch (_err) {
        /* network hiccup — localStorage clear already happened. */
      }
    },
  }));
});
