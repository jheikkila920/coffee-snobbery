"""Wave 1 tests for AUTH-04 + AUTH-03 — argon2-cffi password service.

Covers the per-task verification map rows from
``.planning/phases/02-auth/02-VALIDATION.md``:

- AUTH-04 argon2id roundtrip + format  → ``test_argon2_roundtrip``
- AUTH-04 PasswordHasher params         → ``test_password_hasher_params``
- AUTH-03 dummy-verify timing defense   → ``test_dummy_verify_timing``
- Defensive: invalid hash → False       → ``test_verify_password_handles_invalid_hash``

Plan 02-02 Task 2 lands ``app.services.auth``. Until then the lazy-import
helper makes the tests skip cleanly (analog: ``tests/services/test_sessions.py``).

The ``test_dummy_verify_timing`` ratio gate (0.5x..2.0x) is the regression
test for RESEARCH §"Pitfall 2: argon2 dummy hash NOT computed at import
time → timing leak". If ``_DUMMY_HASH`` is recomputed per call,
``dummy_verify`` is dominated by the ``hash()`` cost (~100ms) and the
ratio collapses near 2.0+.
"""

from __future__ import annotations

import statistics
import time

import pytest


def _require_auth_service() -> None:
    """Skip cleanly while Plan 02-02 Task 2 has not yet shipped the module.

    Once ``app.services.auth`` exists (Task 2 in the same plan), the four
    tests below execute normally.
    """
    try:
        from app.services.auth import (  # noqa: F401
            dummy_verify,
            hash_password,
            verify_password,
        )
    except ImportError:
        pytest.skip("app.services.auth not yet present (Plan 02-02 Task 2)")


def test_argon2_roundtrip() -> None:
    """AUTH-04: hash → verify match, mismatch returns False (no exception)."""
    _require_auth_service()
    from app.services.auth import hash_password, verify_password

    stored = hash_password("password")
    assert stored.startswith("$argon2id$v=19$m=65536,t=3,p=4$"), (
        f"hash_password must produce an argon2id-encoded string with the "
        f"AUTH-04 parameters in the header; got: {stored[:40]!r}..."
    )
    assert verify_password(stored, "password") is True
    assert verify_password(stored, "wrong") is False  # no exception escapes


def test_password_hasher_params() -> None:
    """AUTH-04: PasswordHasher instantiated with explicit m=65536, t=3, p=4, type=ID.

    argon2-cffi 25.1 exposes these as public attributes (``memory_cost``,
    ``time_cost``, ``parallelism``, ``type``). The plan's leading-underscore
    forms (``_memory_cost`` etc.) did not exist on the installed version;
    falling back to the public-attribute form per Plan 02-02
    <action> note ("If the executor finds the attribute names have
    changed in the installed version, fall back...").
    """
    _require_auth_service()
    from argon2 import Type

    from app.services.auth import _ph  # noqa: PLC2701 — sanctioned test-side reach

    assert _ph.memory_cost == 65536, (
        f"memory_cost must be 65536 (64 MiB) per AUTH-04, got {_ph.memory_cost}"
    )
    assert _ph.time_cost == 3, f"time_cost must be 3 per AUTH-04, got {_ph.time_cost}"
    assert _ph.parallelism == 4, f"parallelism must be 4 per AUTH-04, got {_ph.parallelism}"
    assert _ph.type == Type.ID, (
        f"type must be argon2.Type.ID (argon2id) per AUTH-04, got {_ph.type}"
    )


def test_dummy_verify_timing() -> None:
    """AUTH-03: ``dummy_verify`` wall-clock within 0.5x..2.0x of a real failed verify.

    Proves ``_DUMMY_HASH`` was precomputed at import time. If it were
    recomputed per call, the ratio would collapse near or above 2.0x
    (the hash() cost dominates the verify() cost at these parameters).
    """
    _require_auth_service()
    from app.services.auth import dummy_verify, hash_password, verify_password

    real_hash = hash_password("real-password-for-timing-test")

    def t_real() -> float:
        s = time.perf_counter()
        verify_password(real_hash, "wrong")
        return time.perf_counter() - s

    def t_dummy() -> float:
        s = time.perf_counter()
        dummy_verify("anything")
        return time.perf_counter() - s

    # Warm-up — first call sometimes pays an extra JIT / page-fault tax.
    t_real()
    t_dummy()

    real_med = statistics.median([t_real() for _ in range(5)])
    dummy_med = statistics.median([t_dummy() for _ in range(5)])
    ratio = dummy_med / real_med
    assert 0.5 < ratio < 2.0, (
        f"dummy_verify timing must be within 0.5x..2.0x of verify_password — "
        f"got dummy={dummy_med * 1000:.1f}ms, real={real_med * 1000:.1f}ms, "
        f"ratio={ratio:.2f}. If ratio is ~2x, _DUMMY_HASH is likely being "
        f"recomputed per call (RESEARCH Pitfall 2)."
    )


def test_verify_password_handles_invalid_hash() -> None:
    """Defensive: a malformed/corrupted hash returns False, never raises.

    Covers ``InvalidHashError`` in the except tuple — without it a stray
    bad column value would 500 the login route.
    """
    _require_auth_service()
    from app.services.auth import verify_password

    assert verify_password("not-a-valid-argon2-hash", "x") is False
