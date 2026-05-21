"""Wave 0 test stubs for Phase 8 backup requirements (SCHED-04).

All tests are marked xfail(strict=False) until Plan 08-02 lands the
backup service implementation. The stub body encodes the intended assertion
shape as a comment so the implementing plan only removes the xfail marker.

Per 08-VALIDATION.md §"Per-Task Verification Map":
- SCHED-04: test_retention_prune, test_partial_failure_keeps_good,
            test_backup_status_row_write

These are pure sync tests — the backup service uses subprocess.run and
tarfile, both of which are sync stdlib. No @pytest.mark.asyncio needed.
"""

from __future__ import annotations

from typing import Any

import pytest

# ---------------------------------------------------------------------------
# SCHED-04 — Backup service: retention prune
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=False, reason="Plan 08-02 implements prune_old_backups()")
def test_retention_prune(tmp_path: Any) -> None:
    """Filename-based retention prune deletes the correct files.

    Decision D-02: prune by parsing the date in the filename, NOT by mtime.
    Files older than BACKUP_RETENTION_DAYS days (default 14) are deleted.
    Files within the retention window are kept. Non-backup files are not
    touched.

    Intended assertion (remove xfail when Plan 08-02 lands):

        from app.services.backup import prune_old_backups
        from datetime import date, timedelta

        # Create fake backup files with explicit dates
        today = date.today()
        old_date = today - timedelta(days=15)  # outside retention
        new_date = today - timedelta(days=5)   # inside retention

        old_db = tmp_path / f"db_{old_date}.sql"
        old_photos = tmp_path / f"photos_{old_date}.tar.gz"
        new_db = tmp_path / f"db_{new_date}.sql"
        other_file = tmp_path / "other.txt"
        for f in [old_db, old_photos, new_db, other_file]:
            f.write_text("x")

        deleted = prune_old_backups(tmp_path, retention_days=14)

        assert deleted == 2
        assert not old_db.exists()
        assert not old_photos.exists()
        assert new_db.exists()      # within retention
        assert other_file.exists()  # non-backup file untouched
    """
    try:
        from app.services.backup import prune_old_backups  # noqa: F401
    except ImportError:
        pytest.skip("app.services.backup.prune_old_backups not yet implemented")

    pytest.fail("xfail stub — remove marker and fill assertion when Plan 08-02 lands")


# ---------------------------------------------------------------------------
# SCHED-04 — Backup service: partial failure handling
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=False, reason="Plan 08-02 implements run_backup() with D-03 partial failure"
)
def test_partial_failure_keeps_good(tmp_path: Any) -> None:
    """Partial failure keeps the good artifact and flags overall status=error.

    Decision D-03: two artifacts (pg_dump, photos tarball) are attempted
    independently. If one fails, the other is still written and kept. The
    overall result has status="error" and the per-artifact error field
    is populated. The good artifact remains on disk.

    Highest-risk behavior #3 per 08-VALIDATION.md: partial failures must
    never silently discard a good artifact (a failed photos tarball should
    not delete a successful DB dump).

    Intended assertion (remove xfail when Plan 08-02 lands):

        from unittest.mock import patch
        from app.services.backup import run_backup

        with patch("app.services.backup._run_pg_dump", side_effect=RuntimeError("disk full")):
            result = run_backup(backup_dir=tmp_path, db_url="...", photos_dir=tmp_path)

        assert result.status == "error"
        assert result.db_error is not None       # DB dump failed
        photos_path = tmp_path / result.photos_filename
        assert photos_path.exists()              # photos tarball still written
        assert result.photos_bytes > 0
    """
    try:
        from app.services.backup import run_backup  # noqa: F401
    except ImportError:
        pytest.skip("app.services.backup.run_backup not yet implemented")

    pytest.fail("xfail stub — remove marker and fill assertion when Plan 08-02 lands")


# ---------------------------------------------------------------------------
# SCHED-04 — Backup service: status row write
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=False, reason="Plan 08-02 implements last_backup_status write")
def test_backup_status_row_write(sync_db: Any) -> None:
    """last_backup_status is written as a valid JSON string to app_settings.

    Verifies SCHED-04: the backup entry point writes a structured JSON string
    to app_settings.last_backup_status (value_type="string" per migration
    0001 — stores a JSON-encoded string, same contract as last_ai_run_status).

    The JSON must include: status (ok/error), db_filename, db_bytes,
    photos_filename, photos_bytes, duration_ms, pruned_count, and an
    optional error_msg per the BACKUP_COMPLETE field shape in events.py.

    Intended assertion (remove xfail when Plan 08-02 lands):

        import json
        from app.services.backup import write_backup_status
        from app.services.settings import get_setting

        write_backup_status(sync_db, result_dict)
        row = get_setting(sync_db, "last_backup_status")
        parsed = json.loads(row.value)  # must not raise
        assert "status" in parsed
        assert "db_filename" in parsed
        assert "duration_ms" in parsed
    """
    if sync_db is None:
        pytest.skip("sync_db not available")

    try:
        from app.services.backup import write_backup_status  # noqa: F401
    except ImportError:
        pytest.skip("app.services.backup.write_backup_status not yet implemented")

    pytest.fail("xfail stub — remove marker and fill assertion when Plan 08-02 lands")
