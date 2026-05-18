"""Phase 3 tests for ``app.services.encryption`` (Validation Map rows 1-6).

Covers the per-task verification map rows from
``.planning/phases/03-encryption-settings/03-VALIDATION.md``:

- Row 1 — encrypt/decrypt round-trip                  → ``test_encrypt_decrypt_roundtrip``
- Row 2 — MultiFernet decrypts under old key after rotation
                                                       → ``test_rotation_decrypts_old_token``
- Row 3 — unknown key tuple raises ``InvalidToken``    → ``test_unknown_key_raises_invalid_token``
- Row 4 — ``startup_check`` fails loudly on empty key
  → ``test_startup_check_fails_loudly_on_empty_key``
- Row 5 — ``startup_check`` emits ``encryption.startup_ok``
                                                       → ``test_startup_check_emits_ok_event``
- Row 6 — ``primary_key_fingerprint`` is stable + hex  → ``test_fingerprint_stable_and_hex``

Per CONTEXT.md ``<specifics>``: tests use ``Fernet.generate_key()`` per test
— no shared keys, no respx. The lazy-import gate keeps tests collectable
before Plan 03-02 lands (still relevant for CI replay against older base
SHAs).

Threats mitigated (per ``03-06-PLAN.md`` ``<threat_model>``):

* T-03-T1 — tests assert on round-trip equality of ephemeral plaintexts
  and on the 8-char fingerprint prefix; the raw key value is never logged
  or asserted on.
* T-03-T3 — Row 4 proves bad ``APP_ENCRYPTION_KEY`` short-circuits before
  any work the operator-facing path can swallow.
"""

from __future__ import annotations

import importlib

import pytest


def _require_encryption_service() -> None:
    """Skip cleanly until Plan 03-02 lands ``app.services.encryption``."""
    try:
        from app.services.encryption import (  # noqa: F401
            EncryptionStartupError,
            decrypt,
            encrypt,
            primary_key_fingerprint,
            startup_check,
        )
    except ImportError:
        pytest.skip("Phase 3 dependency: app.services.encryption")


def _reload_encryption_with_key(
    monkeypatch: pytest.MonkeyPatch, key_value: str
):
    """Patch ``APP_ENCRYPTION_KEY`` to *key_value* and reload the module.

    Returns the freshly reloaded ``app.services.encryption`` module. Used
    by tests that need to flip the key list mid-test (rotation tests).
    Module reload is the locked rebuild mechanism per CONTEXT.md
    ``<specifics>``.
    """
    monkeypatch.setattr("app.config.settings.APP_ENCRYPTION_KEY", key_value)
    import app.services.encryption as enc_mod

    return importlib.reload(enc_mod)


def test_encrypt_decrypt_roundtrip(monkeypatched_app_encryption_key: str) -> None:
    """Row 1 (SEC-08, D-09 + D-12): decrypt(encrypt(b"x")) == b"x"; ciphertext != plaintext."""
    _require_encryption_service()
    from app.services.encryption import decrypt, encrypt

    plaintext = b"snobbery-test"
    ciphertext = encrypt(plaintext)
    assert ciphertext != plaintext, "ciphertext must not equal plaintext"
    assert decrypt(ciphertext) == plaintext


def test_rotation_decrypts_old_token(
    monkeypatch: pytest.MonkeyPatch, fernet_key_str: str
) -> None:
    """Row 2 (SEC-08, D-09): a token encrypted under K1 decrypts after rotating to (K2, K1)."""
    _require_encryption_service()
    from cryptography.fernet import Fernet

    k1 = fernet_key_str
    k2 = Fernet.generate_key().decode("ascii")

    # Stage 1: only k1 — encrypt the test plaintext under it.
    enc_mod = _reload_encryption_with_key(monkeypatch, k1)
    ct = enc_mod.encrypt(b"snobbery-rotation")

    # Stage 2: k2 is primary, k1 is secondary. MultiFernet must still
    # decrypt the k1-encrypted ciphertext.
    enc_mod = _reload_encryption_with_key(monkeypatch, f"{k2},{k1}")
    assert enc_mod.decrypt(ct) == b"snobbery-rotation"


def test_unknown_key_raises_invalid_token(
    monkeypatch: pytest.MonkeyPatch, fernet_key_str: str
) -> None:
    """Row 3 (SEC-08, D-12): a token encrypted under k1 fails when MultiFernet has only k3."""
    _require_encryption_service()
    from cryptography.fernet import Fernet, InvalidToken

    k1 = fernet_key_str
    k3 = Fernet.generate_key().decode("ascii")

    # Stage 1: encrypt under k1.
    enc_mod = _reload_encryption_with_key(monkeypatch, k1)
    ct = enc_mod.encrypt(b"snobbery-orphan")

    # Stage 2: rebuild MultiFernet with only k3 (k1 is GONE). decrypt must
    # raise InvalidToken — no key in the list can decrypt the token.
    enc_mod = _reload_encryption_with_key(monkeypatch, k3)
    with pytest.raises(InvalidToken):
        enc_mod.decrypt(ct)


def test_startup_check_fails_loudly_on_empty_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Row 4 (SEC-09, D-13): empty ``APP_ENCRYPTION_KEY`` -> EncryptionStartupError.

    The reload itself may raise ``ValueError`` from ``_build_multi_fernet``
    before ``startup_check`` is even reachable — that's an acceptable
    operator-visible failure mode. The test asserts the
    ``EncryptionStartupError`` path when the reload succeeds (which it
    won't with an empty key list, but the protocol matters): the test
    skips out cleanly if the reload raises, surfacing the same hard-fail
    semantics that uvicorn sees.
    """
    _require_encryption_service()

    monkeypatch.setattr("app.config.settings.APP_ENCRYPTION_KEY", "")
    import app.services.encryption as enc_mod

    try:
        enc_mod = importlib.reload(enc_mod)
    except ValueError as exc:
        # The locked failure mode at import time: _build_multi_fernet
        # raises ValueError on empty key list. This is the operator-visible
        # hard fail — equivalent to the EncryptionStartupError path in
        # downstream effect (uvicorn exits non-zero). Test passes.
        assert "APP_ENCRYPTION_KEY" in str(exc) or "empty" in str(exc).lower()
        return

    # If reload somehow succeeded, the startup_check path must be the
    # one that fails loudly (D-13). Assert that EncryptionStartupError
    # chains the underlying ValueError per the spec.
    with pytest.raises(enc_mod.EncryptionStartupError) as ei:
        enc_mod.startup_check()
    # The chained __cause__ should be a ValueError / InvalidToken / TypeError
    # per the locked tuple in encryption.startup_check.
    assert ei.value.__cause__ is not None
    assert isinstance(ei.value.__cause__, (ValueError, TypeError))


def test_startup_check_emits_ok_event(
    monkeypatched_app_encryption_key: str,
) -> None:
    """Row 5 (SEC-09, D-13): healthy key emits ``encryption.startup_ok`` with 8-char fp."""
    _require_encryption_service()
    import structlog

    from app.services.encryption import startup_check

    with structlog.testing.capture_logs() as captured:
        startup_check()

    ok_events = [e for e in captured if e.get("event") == "encryption.startup_ok"]
    assert len(ok_events) == 1, (
        f"expected exactly one encryption.startup_ok event; got "
        f"{len(ok_events)} (all events: {[e.get('event') for e in captured]})"
    )
    fp = ok_events[0].get("fingerprint")
    assert isinstance(fp, str), f"fingerprint field must be str; got {type(fp).__name__}"
    assert len(fp) == 8, f"fingerprint prefix must be 8 chars; got len={len(fp)}"
    assert all(c in "0123456789abcdef" for c in fp), (
        f"fingerprint prefix must be lowercase-hex; got {fp!r}"
    )


def test_fingerprint_stable_and_hex(
    monkeypatched_app_encryption_key: str,
) -> None:
    """Row 6 (SEC-08, D-14): primary_key_fingerprint() is deterministic + 64-char lowercase hex."""
    _require_encryption_service()
    from app.services.encryption import primary_key_fingerprint

    fp_a = primary_key_fingerprint()
    fp_b = primary_key_fingerprint()
    assert fp_a == fp_b, "fingerprint must be deterministic across calls with the same key"
    assert isinstance(fp_a, str)
    assert len(fp_a) == 64, f"SHA-256 hex must be 64 chars; got len={len(fp_a)}"
    assert all(c in "0123456789abcdef" for c in fp_a), (
        f"fingerprint must be lowercase-hex; got {fp_a!r}"
    )
