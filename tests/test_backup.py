"""Unit tests for Phase 8 backup requirements (SCHED-04).

Tests the three behaviours from 08-VALIDATION.md §"Per-Task Verification Map":
- test_retention_prune         (Task 1 — implemented in Plan 08-02)
- test_partial_failure_keeps_good  (Task 2)
- test_backup_status_row_write     (Task 2)

All are pure sync tests — the backup service uses subprocess.run and tarfile,
both of which are sync stdlib.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# SCHED-04 — Backup service: retention prune
# ---------------------------------------------------------------------------


def test_retention_prune(tmp_path: Any) -> None:
    """Filename-based retention prune deletes the correct files.

    Decision D-02: prune by parsing the date in the filename, NOT by mtime.
    Files older than retention_days are deleted; files within the window and
    non-backup files are untouched.
    """
    from app.services.backup import prune_old_backups

    # Fixed "today" = 2026-05-21, retention = 14 days → cutoff = 2026-05-07
    # Anything with a filename date < 2026-05-07 is deleted.
    today = date(2026, 5, 21)

    old_db = tmp_path / "db_2026-05-01.sql"  # 20 days old — delete
    old_photos = tmp_path / "photos_2026-05-01.tar.gz"  # 20 days old — delete
    new_db = tmp_path / "db_2026-05-20.sql"  # 1 day old — keep
    other_file = tmp_path / "other.txt"  # non-backup — keep

    for f in [old_db, old_photos, new_db, other_file]:
        f.write_text("x")

    deleted = prune_old_backups(tmp_path, retention_days=14, _today=today)

    assert deleted == 2
    assert not old_db.exists()
    assert not old_photos.exists()
    assert new_db.exists()  # within retention window
    assert other_file.exists()  # non-backup file untouched


# ---------------------------------------------------------------------------
# SCHED-04 — Backup service: partial failure handling
# ---------------------------------------------------------------------------


def test_partial_failure_keeps_good(tmp_path: Any) -> None:
    """Partial failure keeps the good artifact and flags overall status=error.

    Decision D-03: the two artifacts (pg_dump, photos tarball) are attempted
    independently. If pg_dump fails:
    - the photos tarball is still written and kept on disk.
    - result.status == "error"
    - result.db.ok == False with a non-None error_msg
    - result.photos.ok == True with photos_bytes > 0
    """
    from app.services.backup import run_backup

    # Patch _run_pg_dump to raise; patch set_setting to avoid needing a live DB.
    with (
        patch("app.services.backup._run_pg_dump", side_effect=RuntimeError("disk full")),
        patch("app.services.backup.write_backup_status"),
    ):
        result = run_backup(
            db=object(),  # non-None → run_backup won't open its own session
            backup_dir=str(tmp_path),
            photos_dir=str(tmp_path),  # use tmp_path as photos source (may be empty)
        )

    assert result.status == "error"
    assert result.db.ok is False
    assert result.db.error_msg is not None
    assert "disk full" in result.db.error_msg

    # Photos tarball must have been attempted and succeeded.
    assert result.photos.ok is True
    photos_path = tmp_path / result.photos.filename
    assert photos_path.exists()
    assert result.photos.bytes > 0


# ---------------------------------------------------------------------------
# SCHED-04 — Backup service: status row write
# ---------------------------------------------------------------------------


def test_backup_status_row_write(sync_db: Any) -> None:
    """last_backup_status is written as a valid JSON string to app_settings.

    Verifies SCHED-04: the backup entry point writes a structured JSON string
    to app_settings.last_backup_status (value_type="string" per migration
    0001 — stores a JSON-encoded string, same contract as last_ai_run_status).

    The JSON must include: status (ok/error), db_filename, db_bytes,
    photos_filename, photos_bytes, duration_ms, pruned_count per the
    BACKUP_COMPLETE field shape in events.py.

    Uses write_backup_status() directly to avoid needing pg_dump or the
    photos volume in a unit test.
    """
    if sync_db is None:
        pytest.skip("sync_db not available")

    from sqlalchemy import select

    from app.models.app_setting import AppSetting
    from app.services.backup import write_backup_status
    from app.services.settings import prewarm_cache

    # Seed cache so set_setting can find the row.
    prewarm_cache(sync_db)

    result_dict = {
        "status": "ok",
        "db_filename": "db_2026-05-21.sql",
        "db_bytes": 12345,
        "db_error": None,
        "photos_filename": "photos_2026-05-21.tar.gz",
        "photos_bytes": 6789,
        "photos_error": None,
        "duration_ms": 987,
        "pruned_count": 0,
        "timestamp": "2026-05-21T02:00:00+00:00",
    }

    write_backup_status(sync_db, result_dict)

    # Read back from DB directly (not via get_str — see module docstring).
    row = sync_db.execute(
        select(AppSetting).where(AppSetting.key == "last_backup_status")
    ).scalar_one()

    assert row is not None
    parsed = json.loads(row.value)  # must not raise
    assert parsed["status"] == "ok"
    assert parsed["db_filename"] == "db_2026-05-21.sql"
    assert parsed["db_bytes"] == 12345
    assert parsed["photos_filename"] == "photos_2026-05-21.tar.gz"
    assert parsed["photos_bytes"] == 6789
    assert parsed["duration_ms"] == 987
    assert "pruned_count" in parsed
