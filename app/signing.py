"""Session-cookie signing via :mod:`itsdangerous`.

The cookie carries **just the signed session_id** — the DB row is the
authoritative expiry source (T-04-04 mitigation; RESEARCH §5
"URLSafeSerializer vs URLSafeTimedSerializer"). Using
:class:`itsdangerous.URLSafeSerializer` (no embedded timestamp) avoids
putting two clocks (cookie + DB) in play with no benefit.

The serializer is bound to :attr:`app.config.settings.APP_SECRET_KEY`
with ``salt="session"`` per CONTEXT D-10 + RESEARCH §5.

Phase 2 will use these helpers from the ``/login`` and ``/logout`` routes
(via :mod:`app.services.sessions`); Phase 1's
:class:`app.middleware.session.SessionMiddleware` is the first consumer.
"""

from __future__ import annotations

import uuid

from itsdangerous import BadSignature, URLSafeSerializer

from app.config import settings

# Module-level signer: built once at import time, bound to the configured
# APP_SECRET_KEY. The salt namespaces this serializer against any future
# signed-value usage (e.g., admin password-reset links) so a token signed
# for one purpose cannot be replayed for another.
session_signer = URLSafeSerializer(secret_key=settings.APP_SECRET_KEY, salt="session")


def sign_session_id(session_id: uuid.UUID) -> str:
    """Return the signed cookie value for *session_id*.

    The wire format is opaque to the browser; the server inverts it via
    :func:`load_session_id`.
    """
    return session_signer.dumps(str(session_id))


def load_session_id(signed_cookie_value: str) -> uuid.UUID | None:
    """Verify *signed_cookie_value* and return the embedded UUID.

    Returns ``None`` on either:

    * :class:`itsdangerous.BadSignature` — the cookie was tampered with,
      forged, or signed by a different secret (T-04-01 mitigation).
    * :class:`ValueError` — the embedded payload is not a valid UUID; this
      can only happen if a developer hand-rolls a cookie with the right
      signature key but a non-UUID payload, but is cheap to defend against.

    Callers MUST treat ``None`` as "no session" and clear the cookie via
    :func:`app.services.sessions.build_session_clear_cookie`.
    """
    try:
        raw = session_signer.loads(signed_cookie_value)
        return uuid.UUID(raw)
    except (BadSignature, ValueError):
        return None


__all__ = ["session_signer", "sign_session_id", "load_session_id"]
