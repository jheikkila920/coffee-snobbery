"""``api_credentials`` CRUD + :class:`ProviderCredential` dataclass + auto-rewrap.

Implements Phase 3 decisions D-01..D-04, D-09..D-15. This is the **only**
module in the app that touches ``api_credentials`` rows (CLAUDE.md
"Architectural invariants"). It imports
:func:`app.services.encryption.encrypt` / :func:`~app.services.encryption.decrypt`
/ :func:`~app.services.encryption.primary_key_fingerprint` and **NEVER**
reimplements Fernet/MultiFernet — that is the encryption module's sole
responsibility (D-12 two-module split).

Sync per D-07 + D-11: decrypt is microseconds; an ``async`` variant
would buy nothing and would tempt callers to ``await`` inside hot AI
request paths that already pay millisecond network costs.

Public surface (D-09, D-10, D-11, D-14)
---------------------------------------

* :class:`ProviderCredential` — ``@dataclass(frozen=True, slots=True)``
  transient handoff used by Phase 7's AI service. Lives only in caller
  scope, never persisted, never serialized through Pydantic (T-03-T1,
  T-03-T2; SEC-6).
* :func:`get_provider_credential` — returns the decrypted credential or
  ``None`` on any of the four documented failure modes (row missing,
  ``is_enabled=False``, ``key_ciphertext IS NULL``, decrypt fails with
  :class:`cryptography.fernet.InvalidToken`).
* :func:`set_provider_credential` — admin set / rotate path used by
  Phase 9 routes. Encrypts the key, writes the row plus the
  ``last_four`` denormalization, writes the fingerprint baseline when
  one is not yet stored, commits in a single transaction, emits
  ``admin.api_credential_set``.
* :func:`set_provider_enabled` — admin enable/disable toggle that
  leaves the ciphertext intact.
* :func:`rewrap_if_needed` — idempotent rotation routine invoked at
  lifespan startup (Plan 03-05). No-op when the fingerprint matches or
  when no credentials are populated; on mismatch, re-encrypts every
  populated row under the new primary key inside one transaction.

Documented exception (see ``<deviation_note>`` in 03-04-PLAN.md): both
:func:`set_provider_credential` (first-write baseline) and
:func:`rewrap_if_needed` (post-rotation write) update
``app_settings.encryption_key_primary_fingerprint`` via a **direct**
``UPDATE``, bypassing :func:`app.services.settings.set_setting`. This
keeps the fingerprint write atomic with the credentials write (one
transaction) and lets us flip ``value_type`` from ``'null'`` to
``'string'`` on first write (``set_setting`` does not change
``value_type``). Both call sites invalidate the settings cache after
the inline UPDATE so the next ``get_str`` re-reads the new value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import structlog
from cryptography.fernet import InvalidToken
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.events import (
    ADMIN_API_CREDENTIAL_SET,
    ENCRYPTION_DECRYPT_FAILED,
    ENCRYPTION_REWRAP_COMPLETED,
)
from app.models.api_credential import ApiCredential
from app.models.app_setting import AppSetting
from app.services import encryption
from app.services import settings as settings_service

log = structlog.get_logger(__name__)


Provider = Literal["anthropic", "openai"]
"""Type alias mirroring the ``api_credentials_provider_check`` CHECK
constraint at the type-checker layer (D-04). The DB CHECK is the runtime
backstop — an unknown provider trips :class:`IntegrityError` on commit
(T-03-T7)."""


_FINGERPRINT_KEY = "encryption_key_primary_fingerprint"
"""Single source of truth for the ``app_settings`` row name. Used by
:func:`set_provider_credential` (first-write baseline) and
:func:`rewrap_if_needed` (post-rotation write) — both inline-UPDATE the
``app_settings`` row directly per the documented exception in the
plan's ``<deviation_note>``."""


@dataclass(frozen=True, slots=True)
class ProviderCredential:
    """Decrypted credential — lives only in caller's local scope (D-09, SEC-6).

    Never persisted, never serialized through Pydantic. Frozen+slots
    block accidental attribute injection AND ``__dict__`` access; an
    attempt to mutate any field raises
    :class:`dataclasses.FrozenInstanceError`.

    The ``key`` field is :class:`str` (NOT bytes) because both the
    Anthropic and OpenAI SDKs declare ``api_key: str | None`` on their
    constructors — handing bytes would force every consumer to decode.

    The ``last_four`` field is the denormalized tail of the plaintext
    key (D-03); it is safe to log and surfaces in the Phase 9 admin
    masked-list view without invoking the encryption service.
    """

    provider: Provider
    key: str
    model_name: str
    last_four: str


def get_provider_credential(db: Session, provider: Provider) -> ProviderCredential | None:
    """Return the decrypted credential for *provider*, or ``None`` on any failure mode.

    Per D-10, returns ``None`` (NOT raise) when any of the four
    fast-paths apply:

    1. No row exists for *provider* (e.g., unknown provider name —
       T-03-T7 backstop).
    2. ``is_enabled=False`` — admin has explicitly disabled the
       provider.
    3. ``key_ciphertext IS NULL`` — seeded empty-state row (D-04); the
       admin has not yet set a key.
    4. :class:`cryptography.fernet.InvalidToken` raised from
       :func:`encryption.decrypt` — the stored ciphertext was encrypted
       under a key no longer in ``APP_ENCRYPTION_KEY`` (D-15
       orphaned-ciphertext path). The function emits
       ``encryption.decrypt_failed`` with ``provider`` and
       ``error_class`` only — NEVER the ciphertext or the failing key
       (T-03-T1: prevents offline-cryptanalysis bait in the logs).

    The app stays up in case (4); Phase 7 sees "no credential" and the
    UI renders the graceful "AI not configured" state.

    A fresh :class:`ProviderCredential` instance is constructed on
    every call. There is no decrypted-value cache (D-11: decrypt is
    microseconds; a cache would extend the leak surface of the
    plaintext key beyond the caller's scope).
    """
    row = db.execute(
        select(ApiCredential).where(ApiCredential.provider == provider)
    ).scalar_one_or_none()
    if row is None or not row.is_enabled or row.key_ciphertext is None:
        return None
    try:
        plain_bytes = encryption.decrypt(row.key_ciphertext)
    except InvalidToken as exc:
        # D-15 + T-03-T1: never log the ciphertext, never include the
        # exception body — only the class name. ``app/logging.py``'s
        # SENSITIVE_KEYS redactor does not cover the literal byte string
        # of a ciphertext, so omission here is the actual mitigation.
        log.warning(
            ENCRYPTION_DECRYPT_FAILED,
            provider=provider,
            error_class=type(exc).__name__,
        )
        return None
    return ProviderCredential(
        provider=provider,
        key=plain_bytes.decode("utf-8"),
        model_name=row.model_name or "",
        last_four=row.last_four or "",
    )


def set_provider_credential(
    db: Session,
    provider: Provider,
    *,
    key: str,
    model_name: str,
    by_user_id: int | None,
) -> None:
    """Encrypt *key*, UPDATE the seeded row, write the fingerprint baseline if missing.

    D-01 + D-03 + D-08-style. Single transaction:

    1. Encrypt *key* via :func:`encryption.encrypt` (UTF-8 encode first;
       the SDKs accept ``str``, so encoding lives here rather than at
       the call site — D-09).
    2. UPDATE ``api_credentials`` for *provider* with the new
       ciphertext, ``last_four``, ``model_name``, ``is_enabled=True``,
       ``updated_by_user_id``.
    3. If no fingerprint baseline is stored
       (``encryption_key_primary_fingerprint`` row has
       ``value_type='null'`` per the Plan 03-01 seed), inline-UPDATE
       that row to the current primary fingerprint (value + value_type
       in one statement — see the module docstring's deviation note).
       This is the **only** location in the codebase that writes to
       ``app_settings`` outside :func:`settings_service.set_setting`;
       it is exempt for atomicity + ``value_type`` transition reasons.
    4. Commit.
    5. Emit ``admin.api_credential_set`` with ``provider``,
       ``last_four``, ``model_name``, ``user_id`` ONLY. NEVER include
       ``key`` or ``ciphertext`` (T-03-T1, CLAUDE.md "Never log API
       keys"). The kwarg field is ``user_id`` (not ``by_user_id``) per
       Phase 1 D-14 audit-event taxonomy alignment.

    Args:
        db: Sync :class:`Session`; the caller owns the lifecycle.
        provider: Must be a value satisfying ``Provider`` (mypy/ty
            catches typos; the DB CHECK is the runtime backstop —
            T-03-T7).
        key: Plaintext key from the admin form (e.g.,
            ``"sk-ant-..."``). Encrypted immediately; the local
            variable goes out of scope on function return.
        model_name: The model identifier (e.g.,
            ``"claude-opus-4-7"``); stored verbatim in the row.
        by_user_id: User id recorded on the row's
            ``updated_by_user_id`` column AND emitted as the audit
            event's ``user_id``. ``None`` for system writes.
    """
    ciphertext = encryption.encrypt(key.encode("utf-8"))
    # D-03 denormalization. ``str[-4:]`` is safe past-end in Python:
    # a 1-char key yields ``last_four == "x"`` — a tiny corner case
    # that doesn't break anything (the admin form's min-length
    # validator is the real defense).
    last_four = key[-4:]
    db.execute(
        update(ApiCredential)
        .where(ApiCredential.provider == provider)
        .values(
            key_ciphertext=ciphertext,
            last_four=last_four,
            model_name=model_name,
            is_enabled=True,
            updated_by_user_id=by_user_id,
            updated_at=func.now(),
        )
    )

    # Fingerprint baseline write is unconditional: the ciphertext we just
    # wrote is always encrypted under the current primary key, so the
    # stored fingerprint must always reflect the current primary. A
    # conditional ``if stored_fp is None`` guard left the fingerprint
    # stale after a mid-session APP_ENCRYPTION_KEY rotation (rewrap on
    # next restart self-heals, but the invariant is violated between
    # the set and the restart).
    #
    # Documented exception: direct UPDATE bypasses ``set_setting`` so the
    # fingerprint and credential writes land in ONE transaction AND we
    # can flip ``value_type`` from ``'null'`` to ``'string'`` (set_setting
    # does NOT change ``value_type`` by contract — Plan 03-03 Task 1).
    db.execute(
        update(AppSetting)
        .where(AppSetting.key == _FINGERPRINT_KEY)
        .values(
            value=encryption.primary_key_fingerprint(),
            value_type="string",
            updated_by_user_id=by_user_id,
        )
    )
    # Write-through invalidation, mirroring set_setting's contract.
    settings_service.invalidate(_FINGERPRINT_KEY)

    db.commit()
    log.info(
        ADMIN_API_CREDENTIAL_SET,
        provider=provider,
        last_four=last_four,
        model_name=model_name,
        user_id=by_user_id,
    )


def set_provider_enabled(
    db: Session,
    provider: Provider,
    enabled: bool,
    *,
    by_user_id: int | None,
) -> None:
    """Toggle the ``is_enabled`` flag for *provider* without touching the ciphertext.

    Admin enable/disable surface. The ``key_ciphertext`` and
    ``last_four`` columns are left intact so a disabled provider can be
    re-enabled without re-entering the key.

    Emits ``admin.api_credential_set`` with the ``enabled`` field set;
    the same event name is used for sets and toggles (the ``enabled``
    field disambiguates from a key change at query time).
    """
    db.execute(
        update(ApiCredential)
        .where(ApiCredential.provider == provider)
        .values(
            is_enabled=enabled,
            updated_by_user_id=by_user_id,
            updated_at=func.now(),
        )
    )
    db.commit()
    log.info(
        ADMIN_API_CREDENTIAL_SET,
        provider=provider,
        enabled=enabled,
        user_id=by_user_id,
    )


def rewrap_if_needed(db: Session) -> None:
    """Idempotent post-rotation re-encrypt of every populated credential row (D-14).

    Invoked at lifespan startup (Plan 03-05). Sequence:

    1. Compute ``new_fp = encryption.primary_key_fingerprint()``.
    2. Read the stored fingerprint via ``settings_service.get_str``.
       Catch :class:`SettingNotFoundError` for the pre-prewarm path
       (the cache may be empty at this point — Plan 03-05's lifespan
       order puts ``rewrap_if_needed`` before
       ``settings_service.prewarm_cache`` per D-16).
    3. ``SELECT key_ciphertext IS NOT NULL`` rows ``FOR UPDATE``. The
       row lock is belt-and-suspenders (CONTEXT.md ``<deferred>``
       discretion); single-worker invariant (FOUND-04) already
       prevents the race in practice.
    4. Early returns: no-op when ``stored_fp == new_fp`` (the common
       case — same key as last boot) OR when ``stored_fp is None`` AND
       zero populated rows (first deploy, no credentials yet —
       fingerprint stays NULL until ``set_provider_credential`` writes
       it).
    5. Decrypt + re-encrypt each populated row under the new primary
       key. Per-row try/except :class:`InvalidToken` (Pitfall 7):
       a single orphaned ciphertext does NOT abort the whole rewrap;
       it's logged via ``encryption.decrypt_failed`` and skipped.
    6. Inline-UPDATE the fingerprint row (documented exception — see
       module docstring) and invalidate the settings cache.
    7. Commit. Emit ``encryption.rewrap_completed`` with
       ``row_count`` — the count of rows actually rewrapped (NOT
       ``len(rows)``), so a partial rewrap is correctly reflected.

    Per-row attribute assignment (``row.key_ciphertext = ...``) is the
    SQLAlchemy 2.0 ORM idiom and produces the UPDATE on flush at
    commit time.
    """
    new_fp = encryption.primary_key_fingerprint()
    try:
        stored_fp = settings_service.get_str(_FINGERPRINT_KEY)
    except settings_service.SettingNotFoundError:
        # Pre-prewarm path: row exists in DB but cache is empty. The
        # locked lifespan order in Plan 03-05 (D-16) puts
        # rewrap_if_needed BEFORE prewarm_cache, so this is the
        # expected first-call shape.
        stored_fp = None

    rows = (
        db.execute(
            select(ApiCredential).where(ApiCredential.key_ciphertext.is_not(None)).with_for_update()
        )
        .scalars()
        .all()
    )

    # Early-return guards (D-14 + RESEARCH.md Pitfall 6):
    if stored_fp == new_fp:
        # Common case: same primary key as last boot. No work, no audit
        # noise. Returning here keeps the rewrap event a true
        # rotation signal.
        return
    if stored_fp is None and not rows:
        # First deploy, no credentials yet. Fingerprint stays NULL
        # until ``set_provider_credential`` writes the baseline.
        return

    rewrapped_count = 0
    for row in rows:
        try:
            plain = encryption.decrypt(row.key_ciphertext)
        except InvalidToken as exc:
            # Pitfall 7: an orphaned ciphertext (encrypted under a key
            # since dropped from APP_ENCRYPTION_KEY) MUST NOT abort the
            # rewrap. Log + skip; the admin recovers via Phase 9
            # (re-set the key).
            log.warning(
                ENCRYPTION_DECRYPT_FAILED,
                provider=row.provider,
                error_class=type(exc).__name__,
                during="rewrap",
            )
            continue
        row.key_ciphertext = encryption.encrypt(plain)
        row.updated_at = func.now()
        rewrapped_count += 1

    # Documented exception: direct UPDATE of the fingerprint row keeps
    # the rewrap atomic with the credential UPDATEs above. Using
    # set_setting here would commit a separate transaction and break
    # the "credentials + fingerprint move together" invariant.
    db.execute(
        update(AppSetting)
        .where(AppSetting.key == _FINGERPRINT_KEY)
        .values(value=new_fp, value_type="string", updated_by_user_id=None)
    )
    settings_service.invalidate(_FINGERPRINT_KEY)

    db.commit()
    log.info(ENCRYPTION_REWRAP_COMPLETED, row_count=rewrapped_count)


__all__ = [
    "Provider",
    "ProviderCredential",
    "get_provider_credential",
    "rewrap_if_needed",
    "set_provider_credential",
    "set_provider_enabled",
]
