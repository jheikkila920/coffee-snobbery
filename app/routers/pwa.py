"""PWA installability routes — Phase 11, Plan 01.

Serves two root-level public endpoints:
  - GET /manifest.json — Web App Manifest with locked UX-02 strings.
  - GET /sw.js        — Service worker script with build-hash substitution,
                        Service-Worker-Allowed: / and Cache-Control: no-cache.

Both routes are intentionally PUBLIC (no require_user). The service worker
must install before the user has ever logged in, and the manifest is a static
brand document containing no user-specific data (T-11-01).

Build hash: extracted once at module load from the hashed Tailwind CSS
filename (tailwind.XXXXXXXX.css). Mirrors compute_tailwind_css_path() in
main.py so all cache-busting keys stay in sync with the same build artifact.
Returns "dev" in development environments where no hashed CSS exists.
"""

from __future__ import annotations

from pathlib import Path

import structlog
from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

router = APIRouter()
log = structlog.get_logger(__name__)


def _get_build_hash() -> str:
    """Return a build identifier for use in the service-worker CACHE_NAME.

    Priority order (C9 — cache must bump on every docker compose build):

    1. ``app/static/build_id.txt`` — written unconditionally by the Dockerfile
       stage-1 RUN block on every build (timestamp format: YYYYmmddHHMMSS).
       Preferred because it changes per build regardless of which source files
       changed, fixing the root cause where only editing templates or Python
       files left the CSS hash (and therefore the SW cache key) unchanged.
       Truncated to 16 chars to keep CACHE_NAME compact.

    2. Hashed Tailwind CSS filename (``tailwind.XXXXXXXX.css``) — used when
       running from the source tree (no baked build_id.txt) so that a dev
       rebuild that touches tailwind.src.css still bumps the cache.

    3. ``"dev"`` — fallback for source-tree runs without compiled CSS
       (CI source-tree checkout, unit-test runs without a Docker build).
       The SW still registers and operates; cache purge behaviour is not
       exercised but no exception is raised.
    """
    build_id_path = Path("app/static/build_id.txt")
    if build_id_path.exists():
        return build_id_path.read_text(encoding="utf-8").strip()[:16]

    css_dir = Path("app/static/css")
    candidates = sorted(p for p in css_dir.glob("tailwind.*.css") if p.name != "tailwind.src.css")
    if candidates:
        # "tailwind.XXXXXXXX.css" → split stem on "." → second token is the hash
        return candidates[0].stem.split(".", 1)[1]
    return "dev"


_BUILD_HASH: str = _get_build_hash()


@router.get("/manifest.json")
def manifest() -> JSONResponse:
    """Return the Web App Manifest with locked UX-02 strings (MOB-09).

    Content-Type is set explicitly to ``application/manifest+json`` so browsers
    (and Chrome's installability checker) recognise the manifest correctly.
    The manifest is non-user-specific so no auth is required (T-11-01).
    """
    data = {
        "name": "Snobbery — Coffee Log",
        "short_name": "Snobbery",
        "description": "Self-hosted coffee log for households who take pour-over seriously",
        "display": "standalone",
        "start_url": "/?source=pwa",
        "background_color": "#FAF7F2",
        "theme_color": "#FAF7F2",
        "icons": [
            {
                "src": "/static/img/icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
            },
            {
                "src": "/static/img/icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
            },
            {
                "src": "/static/img/icon-512-maskable.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
            {
                "src": "/static/img/apple-touch-icon.png",
                "sizes": "180x180",
                "type": "image/png",
            },
        ],
    }
    return JSONResponse(
        content=data,
        headers={"Content-Type": "application/manifest+json"},
    )


@router.get("/sw.js")
def service_worker() -> Response:
    """Serve the service worker script with required PWA headers (MOB-10).

    Reads ``app/static/js/sw.js``, substitutes the literal ``__BUILD_HASH__``
    token with the computed build hash, and returns the result with:

    - ``Service-Worker-Allowed: /``  — grants SW scope over the entire origin
      even though the file is served from root (Pitfall 1).
    - ``Cache-Control: no-cache``    — prevents stale SW registration on redeploy;
      NGINX must NOT override this header on the ``/sw.js`` location (PWA-7,
      documented in README).

    The ``__BUILD_HASH__`` substitution is performed at serve time (not baked
    in at Dockerfile build time) because the hash is derived at module load
    from the already-compiled CSS filename — zero extra cost per request.
    """
    sw_path = Path("app/static/js/sw.js")
    content = sw_path.read_text(encoding="utf-8").replace("__BUILD_HASH__", _BUILD_HASH)
    return Response(
        content=content,
        media_type="application/javascript",
        headers={
            "Service-Worker-Allowed": "/",
            "Cache-Control": "no-cache",
        },
    )
