// Photo upload client-side Canvas downscale (D-05).
//
// Reads selected file, draws to canvas at max edge 2000px, re-encodes
// JPEG q=0.85, substitutes the smaller blob into FormData (via
// DataTransfer + File swap) before HTMX submits. Server still
// re-encodes per SEC-4; this is bandwidth UX optimization only.
//
// Hook strategy (LOCKED): a capture-phase `submit` listener on each
// `form[data-photo-form]`. HTMX 2.x serializes the form before
// `htmx:configRequest` fires AND `htmx:configRequest` is synchronous —
// `await` inside it is not supported. The capture-phase submit
// listener intercepts the user-initiated submit, downscales, swaps
// `fileInput.files` via `DataTransfer`, then re-dispatches the submit
// via `htmx.trigger(form, 'submit')`. A processed-flag on the form
// breaks the retrigger loop.
//
// CSP-compliant: no inline handlers, no eval, no innerHTML. Loaded
// after htmx-listeners.js in base.html with the request CSP nonce.
//
// EXIF orientation: skipped at v1 per 04-RESEARCH Pattern 7. Server-
// side Pillow re-encode strips EXIF entirely; preview may display
// sideways but the canonical stored copy is upright (or at least
// consistent).
(function () {
  const MAX_EDGE = 2000;
  const JPEG_QUALITY = 0.85;
  const MIN_SIZE_TO_PROCESS = 500_000; // skip if already small

  function scaleToMaxEdge(w, h) {
    if (w <= MAX_EDGE && h <= MAX_EDGE) return { w: w, h: h };
    const ratio = w > h ? MAX_EDGE / w : MAX_EDGE / h;
    return { w: Math.round(w * ratio), h: Math.round(h * ratio) };
  }

  async function downscale(file) {
    const url = URL.createObjectURL(file);
    try {
      const img = await new Promise(function (resolve, reject) {
        const i = new Image();
        i.onload = function () { resolve(i); };
        i.onerror = reject;
        i.src = url;
      });
      const dims = scaleToMaxEdge(img.naturalWidth, img.naturalHeight);
      const canvas = document.createElement('canvas');
      canvas.width = dims.w;
      canvas.height = dims.h;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, dims.w, dims.h);
      return await new Promise(function (resolve, reject) {
        canvas.toBlob(
          function (blob) {
            if (blob) resolve(blob);
            else reject(new Error('toBlob returned null'));
          },
          'image/jpeg',
          JPEG_QUALITY
        );
      });
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  function wirePhotoForm(form) {
    if (form.__photoUploadWired) return;
    form.__photoUploadWired = true;
    form.addEventListener('submit', async function (evt) {
      // The retrigger path lands here too — let HTMX handle it.
      if (form.__photoUploadProcessed) return;
      evt.preventDefault();
      evt.stopPropagation();

      const fileInput = form.querySelector('input[type="file"][data-photo-input]');
      if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
        // Nothing to process — fall through to the normal submit path.
        form.__photoUploadProcessed = true;
        if (window.htmx) {
          window.htmx.trigger(form, 'submit');
        } else {
          form.submit();
        }
        return;
      }

      const file = fileInput.files[0];
      if (file.type && file.type.indexOf('image/') === 0 && file.size >= MIN_SIZE_TO_PROCESS) {
        try {
          const blob = await downscale(file);
          // Strip the original extension; the downscaled blob is always
          // JPEG. Preserves the original name stem for any UX hint.
          const stem = file.name.replace(/\.[^.]+$/, '');
          const newFile = new File([blob], stem + '.jpg', { type: 'image/jpeg' });
          const dt = new DataTransfer();
          dt.items.add(newFile);
          fileInput.files = dt.files;
        } catch (_err) {
          // Fall through and submit the original; server pipeline handles it.
        }
      }

      form.__photoUploadProcessed = true;
      if (window.htmx) {
        window.htmx.trigger(form, 'submit');
      } else {
        form.submit();
      }
    }, { capture: true });
  }

  function wireAll(root) {
    if (!root) return;
    if (root.matches && root.matches('form[data-photo-form]')) {
      wirePhotoForm(root);
    }
    if (root.querySelectorAll) {
      root.querySelectorAll('form[data-photo-form]').forEach(wirePhotoForm);
    }
  }

  // Initial pass for forms present at document-ready.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      wireAll(document);
    });
  } else {
    wireAll(document);
  }

  // HTMX-swapped fragments may bring in new photo forms. Re-wire on
  // every settle. `__photoUploadWired` keeps it idempotent.
  document.body.addEventListener('htmx:afterSettle', function (evt) {
    wireAll(evt.target || document);
  });
})();
