"""Argon2id password hashing + user-enumeration timing defense.

Three public helpers, no I/O, no DB: ``hash_password``, ``verify_password``,
and ``dummy_verify``. They wrap :mod:`argon2-cffi` 25.1 so the rest of the
codebase never imports :class:`argon2.PasswordHasher` directly — every call
site goes through this module's audited surface.

Why ``dummy_verify`` exists
---------------------------
The ``/login`` POST handler (Plan 02-07) calls ``dummy_verify(password)``
whenever the username lookup returns ``None``. Without it, the
"user-not-found" branch returns in ~0.1 ms while the "wrong-password"
branch spends ~100 ms inside argon2 verify — an attacker can enumerate
valid usernames purely from wall-clock timing (T-02-02-01, ASVS V2.2.5).
``dummy_verify`` runs argon2 verify against a precomputed module-level
hash so both branches consume the same time.

Why the kwargs are explicit
---------------------------
``argon2-cffi`` 25.1's defaults already match the AUTH-04 floor
(m=65536 KiB = 64 MiB, t=3, p=4, type=argon2id), but passing them
explicitly makes a future ops change a one-line code diff that surfaces
in code review — not a silent library-default drift (T-02-02-02,
ASVS V2.4.1). ``test_password_hasher_params`` is the regression test.

Why ``_DUMMY_HASH`` is module-level, not function-level
-------------------------------------------------------
RESEARCH Pitfall 2: if ``_DUMMY_HASH`` were computed inside
``dummy_verify`` per call, the ``hash()`` cost (~100 ms) would dominate
the ``verify()`` cost — ``dummy_verify`` would be ~2× slower than a
real failed verify and itself become a side channel. Computing it once
at import time is the fix; ``test_dummy_verify_timing`` is the gate.

Public surface vs private singletons
------------------------------------
``__all__`` exports only the three helper functions. ``_ph`` and
``_DUMMY_HASH`` are leading-underscore private; tests reach into ``_ph``
to assert the parameter pins (sanctioned test-side access, not a public
contract).
"""

from __future__ import annotations

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerifyMismatchError

# Module-level PasswordHasher singleton. Kwargs are pinned per AUTH-04
# (`.planning/REQUIREMENTS.md`) — argon2-cffi 25.1 defaults already match,
# but the explicit form is the documentation-as-code (D-04) and the
# regression-test surface (`test_password_hasher_params`).
_ph = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # KiB → 64 MiB
    parallelism=4,
    type=Type.ID,  # argon2id (memory-hard + side-channel-resistant)
)

# Precomputed once at import time. RESEARCH Pitfall 2: computing this per
# `dummy_verify()` call would make the function ~2× slower than
# `verify_password()` (the hash() cost dominates verify() at these
# parameters), reopening the user-enumeration timing channel that
# `dummy_verify` exists to close.
#
# The literal value is intentionally not a real password and carries no
# production secret; structlog redactors don't apply because it isn't
# keyed as "password" anywhere it appears.
_DUMMY_HASH: str = _ph.hash(
    "snobbery-dummy-for-timing-defense-not-a-real-secret"  # noqa: S106
)


def hash_password(plaintext: str) -> str:
    """Return an argon2id-encoded hash for *plaintext*.

    The encoded string is ~95–110 chars (Modular Crypt Format) and is what
    the ``users.password_hash`` TEXT column stores. Phase 9's
    rehash-on-login path consumes :meth:`PasswordHasher.check_needs_rehash`
    separately — keep that logic out of this module.
    """
    return _ph.hash(plaintext)


def verify_password(stored_hash: str, candidate_password: str) -> bool:
    """Return ``True`` if *candidate_password* matches *stored_hash*; else ``False``.

    Catches :class:`VerifyMismatchError` (wrong password) and
    :class:`InvalidHashError` (malformed / corrupted column value). Other
    exceptions propagate so genuine bugs surface. argon2's ``verify()`` is
    constant-time by design.
    """
    try:
        return _ph.verify(stored_hash, candidate_password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def dummy_verify(candidate_password: str) -> None:
    """Constant-time defense for the user-not-found branch (Phase 1 D-15).

    Runs argon2 verify against the precomputed :data:`_DUMMY_HASH` so the
    wall-clock cost matches a real :func:`verify_password` failure. The
    result is intentionally discarded — :class:`VerifyMismatchError` is
    the expected outcome.

    Callers MUST invoke this on every code path that would otherwise
    short-circuit (e.g., ``user is None`` after the username lookup);
    skipping it reopens the user-enumeration channel that this module
    exists to close (T-02-02-01, ASVS V2.2.5).
    """
    try:
        _ph.verify(_DUMMY_HASH, candidate_password)
    except VerifyMismatchError:
        pass  # expected — defense is the timing, not the result


__all__ = ["dummy_verify", "hash_password", "verify_password"]
