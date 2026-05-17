"""Cross-cutting middleware; owned by Phase 1.

Each Wave 1 plan lands a middleware module here and re-exports its class
from this package so ``app/main.py`` (Plan 09) can do a single
``from app.middleware import ...`` block instead of N module-level imports.
"""

from __future__ import annotations

from app.middleware.security_headers import SecurityHeadersMiddleware

__all__ = ["SecurityHeadersMiddleware"]
