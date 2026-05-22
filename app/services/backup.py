"""Backup service — pg_dump + photos tarball + filename-date prune (SCHED-04).

Single reusable entry point ``run_backup()`` called by the nightly scheduler job
and (in Phase 9) the admin "Run backup now" button. Both paths receive the same
structured ``BackupResult``.

Phase 9 contract (cross-phase, DO NOT BREAK):
    The ``last_backup_status`` app_settings row is written as a JSON STRING
    (value_type="string" per migration 0001). Phase 9's admin panel MUST read
    it via a raw DB query (``SELECT value FROM app_settings WHERE key = ...``),
    NOT via ``get_str("last_backup_status")``. Reason: ``set_setting`` pops
    the cache key after every write. Until the next ``prewarm_cache()`` call,
    calling ``get_str()`` would raise ``SettingNotFoundError``. The admin panel
    is infrequently accessed and can absorb a direct DB read.

Threat mitigations enforced here:
    T-08-03 (PGPASSWORD info-disclosure): passed via env dict, never as a CLI
        arg and never logged; accepted per single-tenant container context.
    T-08-04 (subprocess injection): ``subprocess.run([...], shell=False)`` with
        a LIST of args — shell metacharacters in DATABASE_URL cannot inject.
    T-08-06 (credentials in logs): BACKUP_* events carry filenames/byte-counts/
        status only — never the password or DATABASE_URL.
"""

from __future__ import annotations

import json
import re
import subprocess
import tarfile
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy.engine import make_url

from app.config import settings, subprocess_env
from app.events import (
    BACKUP_ARTIFACT_ERROR,
    BACKUP_ARTIFACT_OK,
    BACKUP_COMPLETE,
    BACKUP_PRUNED,
    BACKUP_STARTED,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

log = structlog.get_logger(__name__)

# Default backup directory — the coffee_snobbery_backups volume
_DEFAULT_BACKUP_DIR = "/app/data/backups"
# Default photos directory — the coffee_snobbery_photos volume
_DEFAULT_PHOTOS_DIR = "/app/data/photos"


# ---------------------------------------------------------------------------
# Result types (Phase 9 forward-dependency contract D-01)
# ---------------------------------------------------------------------------


@dataclass
class ArtifactResult:
    """Per-artifact outcome for the DB dump or photos tarball."""

    filename: str
    bytes: int
    ok: bool
    error_msg: str | None = None


@dataclass
class BackupResult:
    """Structured result returned by ``run_backup()``.

    Phase 9 "Run backup now" button and the scheduler job both receive this
    type. The JSON serialisation of this result (via ``_result_to_dict``) is
    what gets stored in ``app_settings.last_backup_status``.

    Fields:
        status:        "ok" if all artifacts succeeded, "error" otherwise.
        db:            Per-artifact result for the pg_dump SQL file.
        photos:        Per-artifact result for the photos tarball.
        duration_ms:   Wall-clock duration of the entire run in milliseconds.
        pruned_count:  Number of old backup files deleted.
        timestamp:     ISO-8601 UTC timestamp for when the run completed.
    """

    status: str  # "ok" | "error"
    db: ArtifactResult = field(default_factory=lambda: ArtifactResult("", 0, False))
    photos: ArtifactResult = field(default_factory=lambda: ArtifactResult("", 0, False))
    duration_ms: int = 0
    pruned_count: int = 0
    timestamp: str = ""


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_db_url(url: str) -> dict[str, str]:
    """Parse a SQLAlchemy ``DATABASE_URL`` into pg_dump connection components.

    Uses ``sqlalchemy.engine.make_url`` so that percent-encoded characters,
    reserved chars in passwords (``@``, ``:``, etc.), optional ports, and
    query-string suffixes are all handled correctly (CR-01).

    Raises ``ValueError`` when host or database is missing (required by
    pg_dump), or ``sqlalchemy.exc.ArgumentError`` on a completely malformed
    URL (V5 input-validation, T-08-04).
    """
    u = make_url(url)  # raises ArgumentError on truly malformed input
    if not u.host or not u.database:
        raise ValueError(f"DATABASE_URL missing host/database for pg_dump: {url!r}")
    return {
        "user": u.username or "",
        "password": u.password or "",  # already percent-decoded by make_url
        "host": u.host,
        "port": str(u.port or 5432),
        "dbname": u.database,
    }


def _run_pg_dump(dest_path: str) -> None:
    """Invoke pg_dump as a subprocess, writing a plain uncompressed .sql file.

    Security notes:
    - Args are a LIST (no shell=True) — shell injection impossible (T-08-04).
    - PGPASSWORD passed via env dict — never as a CLI arg or logged (T-08-03).
    - Plain format (no -Fc) — keeps the CLAUDE.md ``psql < file.sql`` runbook intact.

    Flags:
        --clean:          Emit DROP before CREATE (idempotent restore).
        --if-exists:      Suppress "does not exist" warnings on first restore.
        --no-owner:       Don't emit ALTER OWNER (restore as any user).
        --no-privileges:  Don't emit GRANT/REVOKE.

    Raises ``RuntimeError`` (with stderr) on a non-zero pg_dump exit code.
    """
    conn = _parse_db_url(settings.DATABASE_URL)
    env = subprocess_env(PGPASSWORD=conn["password"])
    result = subprocess.run(  # noqa: S603
        [  # noqa: S607 — pg_dump is a version-matched known binary (Phase 0, SH-5)
            "pg_dump",
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges",
            "-h",
            conn["host"],
            "-p",
            conn["port"],
            "-U",
            conn["user"],
            "-d",
            conn["dbname"],
            "-f",
            dest_path,
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,  # 5-minute hard cap; a household DB should dump in seconds
    )
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump failed (exit {result.returncode}): {result.stderr}")


def _no_symlinks(ti: tarfile.TarInfo) -> tarfile.TarInfo | None:
    """tarfile filter that skips symbolic and hard links (WR-04).

    Prevents the tarball from dereferencing symlinks into arbitrary host
    paths — a hardening measure for user-upload-fed backup archives.
    """
    if ti.issym() or ti.islnk():
        return None  # skip links; archive only regular files and dirs
    return ti


def _tar_photos(dest_path: str, photos_dir: str = _DEFAULT_PHOTOS_DIR) -> None:
    """Write a gzip tarball of the photos directory to ``dest_path``.

    Tolerates a missing or empty photos directory — creates an empty but
    structurally valid tarball rather than crashing the whole backup run. This
    is intentional: a new install with no photos yet should not cause a backup
    job error (D-03: artifacts are attempted independently).

    Symlinks are skipped via the ``_no_symlinks`` filter to prevent archiving
    arbitrary host-reachable paths from the container (WR-04).
    """
    photos_path = Path(photos_dir)
    with tarfile.open(dest_path, "w:gz") as tar:
        if photos_path.is_dir():
            tar.add(photos_path, arcname="photos", filter=_no_symlinks)
        # If photos_dir doesn't exist or is empty, the tarball is valid but empty.


def prune_old_backups(
    backup_dir: Path | str,
    retention_days: int,
    *,
    _today: date | None = None,
) -> int:
    """Delete backup files older than ``retention_days`` by parsing the filename date.

    Decision D-02: date is parsed from the filename (not mtime) — mtime is
    unreliable after ``docker compose cp`` or a volume re-mount.

    Matches filenames of the form:
        db_YYYY-MM-DD.sql
        photos_YYYY-MM-DD.tar.gz

    Non-matching filenames are silently ignored (no crash on stray files).

    Args:
        backup_dir:     Directory to scan.
        retention_days: Files with a parsed date older than this many days
                        before ``_today`` (inclusive) are deleted.
        _today:         Injectable "today" for unit tests. Defaults to
                        ``date.today()`` at call time.

    Returns:
        Count of files deleted.
    """
    today = _today or date.today()
    cutoff = today - timedelta(days=retention_days)
    pattern = re.compile(r"(?:db|photos)_(\d{4}-\d{2}-\d{2})\.(sql|tar\.gz)$")
    deleted = 0
    for f in list(Path(backup_dir).iterdir()):
        m = pattern.match(f.name)
        if m:
            file_date = date.fromisoformat(m.group(1))
            if file_date < cutoff:
                try:
                    f.unlink()
                    deleted += 1
                except Exception as exc:
                    # One undeletable file must not stop pruning the rest (WR-03).
                    log.warning(
                        "backup.prune_file_failed",
                        filename=f.name,
                        error_class=type(exc).__name__,
                        error_msg=str(exc),
                    )
    return deleted


# ---------------------------------------------------------------------------
# Status persistence helper (exposed for test_backup_status_row_write)
# ---------------------------------------------------------------------------


def write_backup_status(db: Session, result_dict: dict) -> None:
    """Write ``last_backup_status`` to ``app_settings`` as a JSON string.

    The row has ``value_type="string"`` (migration 0001), so the caller MUST
    pass a JSON STRING — not a dict. This helper performs the ``json.dumps``
    call and delegates to ``set_setting``.

    Phase 9 contract: admin panel reads this row via a raw DB query, not via
    ``get_str()`` (see module docstring for why).
    """
    from app.services import settings as settings_service

    settings_service.set_setting(
        db,
        "last_backup_status",
        json.dumps(result_dict),
        by_user_id=None,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_backup(
    db: Session | None = None,
    *,
    backup_dir: str = _DEFAULT_BACKUP_DIR,
    photos_dir: str = _DEFAULT_PHOTOS_DIR,
    by_user_id: int | None = None,
) -> BackupResult:
    """Run the full backup: pg_dump + photos tarball + prune + status write.

    Design decisions honoured:
    - D-01: Returns a structured ``BackupResult``; both the scheduler and Phase
      9's "Run backup now" button call this same entry point.
    - D-02: Date-only filenames (``db_YYYY-MM-DD.sql``, ``photos_YYYY-MM-DD.tar.gz``);
      same-day runs overwrite the day's file.
    - D-03: Keep-partial — each artifact is wrapped in its own try/except; a
      pg_dump failure does not prevent the photos tarball from being attempted.
      Overall ``status="error"`` if ANY artifact failed.

    Args:
        db:           Optional ``Session`` to use for the status write. If None,
                      a new ``SessionLocal()`` is opened and closed inside this
                      function. A Phase 9 synchronous handler can pass its own
                      session; the scheduler job lets run_backup own one.
        backup_dir:   Target directory for backup files (default: the
                      ``coffee_snobbery_backups`` volume at ``/app/data/backups``).
        photos_dir:   Source directory for the photos tarball (default: the
                      ``coffee_snobbery_photos`` volume at ``/app/data/photos``).
        by_user_id:   User id for the ``app_settings`` audit trail; ``None`` for
                      system/scheduler writes.

    Returns:
        ``BackupResult`` with per-artifact outcomes, overall status, duration, and
        pruned file count.
    """
    from app.db import SessionLocal

    log.info(BACKUP_STARTED)

    start_time = time.monotonic()
    # Use APP_TIMEZONE so "today" matches the household's local calendar day,
    # not the container's UTC clock (e.g. an evening run in America/Chicago
    # would otherwise produce a file dated tomorrow).
    today = datetime.now(ZoneInfo(settings.APP_TIMEZONE)).date()
    today_str = today.isoformat()  # YYYY-MM-DD

    Path(backup_dir).mkdir(parents=True, exist_ok=True)

    db_filename = f"db_{today_str}.sql"
    photos_filename = f"photos_{today_str}.tar.gz"
    db_dest = str(Path(backup_dir) / db_filename)
    photos_dest = str(Path(backup_dir) / photos_filename)

    result = BackupResult(status="ok")
    result.db = ArtifactResult(filename=db_filename, bytes=0, ok=False)
    result.photos = ArtifactResult(filename=photos_filename, bytes=0, ok=False)

    # --- Artifact 1: pg_dump (plain .sql) ---
    try:
        _run_pg_dump(db_dest)
        db_bytes = Path(db_dest).stat().st_size
        result.db = ArtifactResult(filename=db_filename, bytes=db_bytes, ok=True)
        log.info(BACKUP_ARTIFACT_OK, artifact="db", filename=db_filename, bytes=db_bytes)
    except Exception as exc:
        error_msg = str(exc)
        result.db = ArtifactResult(filename=db_filename, bytes=0, ok=False, error_msg=error_msg)
        result.status = "error"
        log.warning(
            BACKUP_ARTIFACT_ERROR,
            artifact="db",
            error_class=type(exc).__name__,
            error_msg=error_msg,
        )

    # --- Artifact 2: photos tarball ---
    try:
        _tar_photos(photos_dest, photos_dir=photos_dir)
        photos_bytes = Path(photos_dest).stat().st_size
        result.photos = ArtifactResult(filename=photos_filename, bytes=photos_bytes, ok=True)
        log.info(
            BACKUP_ARTIFACT_OK,
            artifact="photos",
            filename=photos_filename,
            bytes=photos_bytes,
        )
    except Exception as exc:
        error_msg = str(exc)
        result.photos = ArtifactResult(
            filename=photos_filename, bytes=0, ok=False, error_msg=error_msg
        )
        result.status = "error"
        log.warning(
            BACKUP_ARTIFACT_ERROR,
            artifact="photos",
            error_class=type(exc).__name__,
            error_msg=error_msg,
        )

    # --- Prune old backups ---
    # Isolated try/except so a prune failure degrades gracefully (D-03 keep-partial):
    # both artifacts have already been attempted; a filesystem error here must not
    # prevent last_backup_status from being written (WR-03).
    try:
        pruned_count = prune_old_backups(backup_dir, settings.BACKUP_RETENTION_DAYS, _today=today)
    except Exception as exc:
        pruned_count = 0
        log.warning("backup.prune_failed", error_class=type(exc).__name__, error_msg=str(exc))
    result.pruned_count = pruned_count
    log.info(
        BACKUP_PRUNED,
        pruned_count=pruned_count,
        retention_days=settings.BACKUP_RETENTION_DAYS,
    )

    # --- Finalise timing ---
    duration_ms = int((time.monotonic() - start_time) * 1000)
    result.duration_ms = duration_ms

    result.timestamp = datetime.now(tz=UTC).isoformat()

    # --- Write last_backup_status ---
    status_dict = {
        "status": result.status,
        "db_filename": result.db.filename,
        "db_bytes": result.db.bytes,
        "db_error": result.db.error_msg,
        "photos_filename": result.photos.filename,
        "photos_bytes": result.photos.bytes,
        "photos_error": result.photos.error_msg,
        "duration_ms": result.duration_ms,
        "pruned_count": result.pruned_count,
        "timestamp": result.timestamp,
    }

    own_session = db is None
    _db: Session
    if own_session:
        _db = SessionLocal()
    else:
        _db = db  # type: ignore[assignment]

    try:
        write_backup_status(_db, status_dict)
    finally:
        if own_session:
            _db.close()

    log.info(
        BACKUP_COMPLETE,
        status=result.status,
        db_filename=result.db.filename,
        db_bytes=result.db.bytes,
        photos_filename=result.photos.filename,
        photos_bytes=result.photos.bytes,
        duration_ms=result.duration_ms,
        pruned_count=result.pruned_count,
    )

    return result


__all__ = [
    "ArtifactResult",
    "BackupResult",
    "prune_old_backups",
    "run_backup",
    "write_backup_status",
]
