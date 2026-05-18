"""Typed ``app_settings`` reader + write-through cache (D-05 through D-08).

Module-level ``_cache`` populated at lifespan startup via
:func:`prewarm_cache`. Reads are pure cache lookups; writes go through
the DB then invalidate the affected key. Single-worker invariant
(FOUND-04 / Phase 0 D-13) makes the cache consistent across requests.
Do NOT call from inside a ``SELECT ... FOR UPDATE`` transaction — the
cache does not compose with row locks; use raw SQL there (CONTEXT.md
``<specifics>`` — Phase 2 ``setup_completed`` read site).

Public surface (D-05)
---------------------

* :func:`prewarm_cache` — single ``SELECT * FROM app_settings`` populates
  the module-level cache. Idempotent — safe to call multiple times.
* :func:`get_str`, :func:`get_int`, :func:`get_bool`, :func:`get_json` —
  typed accessors; each raises :class:`SettingTypeError` if the row's
  ``value_type`` doesn't match the accessor, or :class:`SettingNotFoundError`
  on unknown keys. ``value_type='null'`` rows return ``None``.
* :func:`get_raw` — returns ``(value, value_type)`` for the Phase 9
  admin editor that needs to render arbitrary types.
* :func:`set_setting` — UPDATE the row in one transaction, pop the
  cache entry, emit a structured ``admin.app_setting_changed`` event
  (D-08). Does NOT change ``value_type``; callers needing a type
  transition do a direct UPDATE.
* :func:`invalidate` — test-only hook for out-of-band SQL edits.

Why a module-level cache (D-06)
-------------------------------
At household scale + single uvicorn worker, every ``app_settings`` row
fits in a tiny dict and every read is sub-microsecond. The auth /
catalog / scheduler / Phase 7 AI service all consume settings on hot
paths; a per-request DB round-trip would be wasteful. The cache is
populated once at lifespan startup; writes go through ``set_setting``
which invalidates the key after committing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.events import ADMIN_APP_SETTING_CHANGED
from app.models.app_setting import AppSetting

log = structlog.get_logger(__name__)


class SettingNotFoundError(KeyError):
    """Raised when a typed accessor receives an unknown key."""


class SettingTypeError(TypeError):
    """Raised when an accessor's expected type doesn't match the row's ``value_type``."""


@dataclass(frozen=True, slots=True)
class _CachedSetting:
    """One row of the in-memory app_settings cache.

    Per CONTEXT.md ``<specifics>``, ``value_type='null'`` is the
    typed-null sentinel; every typed accessor returns ``None`` for that
    row regardless of the accessor's expected type.
    """

    value: str | None
    value_type: str  # 'string' | 'int' | 'float' | 'bool' | 'json' | 'null'
    coerced: Any  # pre-coerced Python value (None for value_type='null')


# Single-worker invariant (FOUND-04) means this dict is consistent across
# every request. Empty until prewarm_cache() runs in lifespan startup.
_cache: dict[str, _CachedSetting] = {}


def _coerce(value: str | None, value_type: str) -> Any:
    """Coerce a stored text value to its native Python type.

    Phase 0 stores booleans as the strings ``"true"`` / ``"false"``;
    ``json`` values are :func:`json.loads`-decoded. ``value_type='null'``
    is the typed-null sentinel and returns ``None`` regardless of the
    stored value.
    """
    if value_type == "null":
        return None
    if value is None:
        # Defensive: value=None with a non-'null' value_type is an
        # invalid row, but we surface it as Python None rather than
        # crash inside the coercer.
        return None
    if value_type == "string":
        return value
    if value_type == "int":
        return int(value)
    if value_type == "float":
        return float(value)
    if value_type == "bool":
        return value.lower() == "true"
    if value_type == "json":
        return json.loads(value)
    raise SettingTypeError(f"Unknown value_type: {value_type!r}")


def prewarm_cache(db: Session) -> None:
    """Populate the module-level cache from one ``SELECT * FROM app_settings`` (D-06).

    Idempotent — safe to call multiple times; the existing cache is
    cleared first so re-running during tests resets cleanly. Read-only
    (no ``db.commit()``).
    """
    _cache.clear()
    rows = db.execute(select(AppSetting)).scalars().all()
    for row in rows:
        _cache[row.key] = _CachedSetting(
            value=row.value,
            value_type=row.value_type,
            coerced=_coerce(row.value, row.value_type),
        )


def _get(key: str, expected_type: str) -> Any:
    """Shared typed-accessor body. Returns ``None`` for ``value_type='null'`` rows.

    Raises :class:`SettingNotFoundError` if the key is not in the cache
    (which per the prewarm contract means it doesn't exist in
    ``app_settings``), or :class:`SettingTypeError` if the row's
    ``value_type`` doesn't match *expected_type*.
    """
    cached = _cache.get(key)
    if cached is None:
        raise SettingNotFoundError(key)
    if cached.value_type == "null":
        return None
    if cached.value_type != expected_type:
        raise SettingTypeError(
            f"Setting {key!r} has value_type={cached.value_type!r}; "
            f"caller expected {expected_type!r}"
        )
    return cached.coerced


def get_str(key: str) -> str | None:
    """Return the string value of *key*.

    Raises :class:`SettingTypeError` if ``value_type`` is not
    ``'string'``; returns ``None`` for ``value_type='null'`` rows.
    """
    return _get(key, "string")


def get_int(key: str) -> int | None:
    """Return the integer value of *key*.

    Raises :class:`SettingTypeError` if ``value_type`` is not ``'int'``;
    returns ``None`` for ``value_type='null'`` rows.
    """
    return _get(key, "int")


def get_bool(key: str) -> bool | None:
    """Return the boolean value of *key*.

    Raises :class:`SettingTypeError` if ``value_type`` is not ``'bool'``;
    returns ``None`` for ``value_type='null'`` rows.
    """
    return _get(key, "bool")


def get_json(key: str) -> Any:
    """Return the JSON-decoded value of *key*.

    Raises :class:`SettingTypeError` if ``value_type`` is not ``'json'``;
    returns ``None`` for ``value_type='null'`` rows.
    """
    return _get(key, "json")


def get_raw(key: str) -> tuple[str | None, str]:
    """Return ``(value, value_type)`` for the Phase 9 admin editor.

    The admin editor needs the raw text plus the type tag so it can
    render the right input control. Unlike the typed accessors,
    ``value_type='null'`` rows are NOT collapsed to ``None`` —
    callers need the typed-null marker to render the correct UI.

    Raises :class:`SettingNotFoundError` for unknown keys.
    """
    cached = _cache.get(key)
    if cached is None:
        raise SettingNotFoundError(key)
    return cached.value, cached.value_type


def set_setting(
    db: Session,
    key: str,
    value: Any,
    *,
    by_user_id: int | None,
) -> None:
    """UPDATE *key* in ``app_settings``, invalidate the cache, emit audit event (D-08).

    ``set_setting`` does NOT change ``value_type``; callers needing a
    ``value_type`` transition (e.g., the ``value_type='null'`` →
    ``value_type='string'`` first-write of
    ``encryption_key_primary_fingerprint``) must perform a direct UPDATE
    — see ``credentials.rewrap_if_needed`` for the documented exception.

    Args:
        db: Sync :class:`Session`; the caller owns lifecycle.
        key: The ``app_settings`` row key. Must exist (raises
            ``NoResultFound`` from SQLAlchemy if not).
        value: The new value. Coerced to text for storage according to
            the row's existing ``value_type``:

            * ``None`` → ``NULL``
            * ``json`` → ``json.dumps(value)``
            * ``bool`` → ``"true"`` / ``"false"``
            * otherwise → ``str(value)``
        by_user_id: User id to record on the row's
            ``updated_by_user_id`` column; ``None`` for lifespan /
            system writes (e.g., the auto-rewrap path).
    """
    existing = db.execute(select(AppSetting).where(AppSetting.key == key)).scalar_one()
    old_value = existing.value
    value_type = existing.value_type

    # Coerce the incoming Python value back to the text representation
    # stored in the ``value`` TEXT column. Note we read ``value_type``
    # from the existing row; ``set_setting`` never changes it.
    text_value: str | None
    if value is None:
        text_value = None
    elif value_type == "json":
        text_value = json.dumps(value)
    elif value_type == "bool":
        text_value = "true" if value else "false"
    else:
        text_value = str(value)

    db.execute(
        update(AppSetting)
        .where(AppSetting.key == key)
        .values(value=text_value, updated_by_user_id=by_user_id)
    )
    db.commit()
    # Write-through invalidate: drop the key so the next accessor call
    # surfaces SettingNotFoundError (forcing a re-prewarm) or the next
    # prewarm re-populates from the freshly-committed row. Ordering is
    # critical — invalidation must follow commit so we never serve a
    # post-write read from a stale cache that committed-then-crashed
    # could re-populate.
    _cache.pop(key, None)

    # D-08 audit event. Field name is ``user_id`` (Phase 1 D-14
    # taxonomy alignment), NOT ``by_user_id``. The structlog redactor
    # in ``app/logging.py`` does NOT match ``setting_key`` /
    # ``old_value`` / ``new_value`` — no current ``app_settings`` row
    # holds sensitive data (CONTEXT.md ``<deferred>``).
    log.info(
        ADMIN_APP_SETTING_CHANGED,
        setting_key=key,
        old_value=old_value,
        new_value=text_value,
        value_type=value_type,
        user_id=by_user_id,
    )


def invalidate(key: str) -> None:
    """Drop *key* from the cache.

    Test-only hook for out-of-band SQL edits; production callers use
    :func:`set_setting` which already invalidates after committing.
    """
    _cache.pop(key, None)


__all__ = [
    "SettingNotFoundError",
    "SettingTypeError",
    "get_bool",
    "get_int",
    "get_json",
    "get_raw",
    "get_str",
    "invalidate",
    "prewarm_cache",
    "set_setting",
]
