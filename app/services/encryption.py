"""Fernet/MultiFernet primitives + sentinel startup check.

Implements Phase 3 decisions D-12 (two-module split: pure-crypto here,
credentials CRUD in :mod:`app.services.credentials`), D-13 (sentinel
encrypt/decrypt round-trip at lifespan startup), and the encryption side
of D-14 (primary-key fingerprint helper for the auto-rewrap detector).

CLAUDE.md "Architectural invariants": this is the **only** module in the
app that may instantiate :class:`cryptography.fernet.Fernet` or
:class:`cryptography.fernet.MultiFernet`. ``credentials.py`` and every
other caller MUST go through :func:`encrypt` / :func:`decrypt` — never
reimplement crypto.

The module-level ``_multi_fernet`` singleton is built exactly once at
import time from ``settings.APP_ENCRYPTION_KEY`` (comma-separated raw
string, Phase 0 D-18). First key is primary for encryption; all keys are
attempted for decryption (MultiFernet's rotation contract).
"""

from __future__ import annotations

import hashlib

import structlog
from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.config import settings
from app.events import ENCRYPTION_STARTUP_OK

log = structlog.get_logger(__name__)


class EncryptionStartupError(RuntimeError):
    """Raised by :func:`startup_check` when the sentinel round-trip fails.

    Chains the underlying :class:`cryptography.fernet.InvalidToken`,
    :class:`ValueError`, or :class:`TypeError` via ``__cause__`` so the
    operator sees the root cause in the structured-log chain. Propagates
    out of ``lifespan`` → uvicorn exits non-zero → docker-compose
    healthcheck flips unhealthy. D-13.

    Subclass of :class:`RuntimeError` (not ``Exception``) so the class
    name surfaces clearly in JSON log output.
    """


def _parse_keys() -> list[str]:
    """Split ``APP_ENCRYPTION_KEY`` on commas, strip whitespace, drop empties.

    Phase 0 D-18 stores the env var as a raw comma-separated string; this
    helper is the single conversion point. Used by :func:`_build_multi_fernet`
    and :func:`primary_key_fingerprint` so both see exactly the same key
    list (consistency under rotation).
    """
    return [k.strip() for k in settings.APP_ENCRYPTION_KEY.split(",") if k.strip()]


def _build_multi_fernet() -> MultiFernet:
    """Construct :class:`MultiFernet` from ``APP_ENCRYPTION_KEY``.

    First key is primary for encryption; all keys are attempted for
    decryption (cryptography 48's MultiFernet rotation contract — see
    https://cryptography.io/en/latest/fernet/).

    Raises :class:`ValueError` when the parsed list is empty (Pitfall 1
    in RESEARCH.md). A malformed base64 key surfaces as
    :class:`binascii.Error` from :class:`Fernet` — that exception is a
    subclass of :class:`ValueError`, so :func:`startup_check` catches it
    via the locked ``(InvalidToken, ValueError, TypeError)`` tuple.
    """
    keys = _parse_keys()
    if not keys:
        raise ValueError("APP_ENCRYPTION_KEY is empty after splitting on commas")
    return MultiFernet([Fernet(k) for k in keys])


# Module-level singleton: built once at first import, never reconstructed
# per call. Mirrors :data:`app.signing.session_signer` (Phase 1 pattern).
_multi_fernet: MultiFernet = _build_multi_fernet()


def encrypt(plaintext: bytes) -> bytes:
    """Encrypt under the primary key (first entry in ``APP_ENCRYPTION_KEY``).

    Returns URL-safe base64-encoded bytes per Fernet's contract. The
    caller (``credentials.set_provider_credential``) stores the bytes
    verbatim in the ``api_credentials.key_ciphertext`` ``bytea`` column.
    """
    return _multi_fernet.encrypt(plaintext)


def decrypt(ciphertext: bytes) -> bytes:
    """Decrypt under any key in ``APP_ENCRYPTION_KEY``.

    MultiFernet tries the primary first, then the rest. Raises
    :class:`cryptography.fernet.InvalidToken` if no configured key
    decrypts the token — the caller
    (``credentials.get_provider_credential``) catches that exception and
    translates it to a ``None`` return plus an
    ``encryption.decrypt_failed`` audit event (D-15). This module does
    NOT swallow the exception; the call site owns the graceful-failure
    policy.
    """
    return _multi_fernet.decrypt(ciphertext)


def primary_key_fingerprint() -> str:
    """Return deterministic 64-char lowercase hex SHA-256 of the primary key.

    Used by D-14's auto-rewrap detector
    (``credentials.rewrap_if_needed``): when the SHA-256 of the current
    primary key differs from the value stored in
    ``app_settings.encryption_key_primary_fingerprint``, the rewrap
    routine re-encrypts every populated ``api_credentials`` row under
    the new primary.

    The full hash is never logged. :func:`startup_check` emits only the
    first 8 hex chars as a stability indicator (T-03-T1 mitigation).
    """
    primary = _parse_keys()[0]
    return hashlib.sha256(primary.encode("ascii")).hexdigest()


def startup_check() -> None:
    """Sentinel encrypt/decrypt round-trip at lifespan startup (D-13).

    On success: emits ``encryption.startup_ok`` with an 8-char
    fingerprint prefix and returns ``None``.

    On failure: raises :class:`EncryptionStartupError` with the
    underlying :class:`InvalidToken` / :class:`ValueError` /
    :class:`TypeError` chained via ``from exc``. The exception
    propagates out of ``lifespan`` so uvicorn exits non-zero and the
    docker-compose healthcheck marks the container unhealthy — the
    operator sees a hard fail at boot rather than silent ciphertext that
    nothing can decrypt.

    The integrity-failure branch (round-trip produced wrong plaintext)
    raises without a ``from`` clause because there is no underlying
    exception — only a library bug or memory corruption could trip it.
    """
    try:
        round_trip = decrypt(encrypt(b"snobbery-startup-check"))
        if round_trip != b"snobbery-startup-check":
            raise EncryptionStartupError(
                "Sentinel round-trip produced wrong plaintext (corruption or library bug)"
            )
    except (InvalidToken, ValueError, TypeError) as exc:
        raise EncryptionStartupError(
            "APP_ENCRYPTION_KEY round-trip failed — key may be malformed, missing, or unusable"
        ) from exc
    log.info(ENCRYPTION_STARTUP_OK, fingerprint=primary_key_fingerprint()[:8])


__all__ = [
    "EncryptionStartupError",
    "decrypt",
    "encrypt",
    "primary_key_fingerprint",
    "startup_check",
]
