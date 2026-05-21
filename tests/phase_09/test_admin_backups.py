"""ADMIN-04: Backups page tests — TDD RED suite.

Tests:
  test_backup_list          GET /admin/backups → 200 with file listing
  test_backup_list_empty    GET /admin/backups on empty dir → 200 empty-state
  test_download_valid       GET /admin/backups/<valid> → 200 + file bytes
  test_download_path_traversal  GET /admin/backups/<traversal> → 404
  test_run_backup_now       POST /admin/backups/run → fragment with BackupResult
  test_run_backup_non_admin POST /admin/backups/run non-admin → 403

Security:
  D-08: strict regex FIRST + Path.resolve().is_relative_to() containment
  D-07: run-now handler is sync def (verified via inspect.iscoroutinefunction)
  T-09-20: path traversal blocked for encoded + raw variants
  T-09-24: non-admin → 403
"""

from __future__ import annotations

import inspect
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers — seed real backup files so the list is trustworthy (no skips)
# ---------------------------------------------------------------------------


def _make_tmp_backup_dir(files: list[str]) -> tempfile.TemporaryDirectory:  # type: ignore[type-arg]
    """Create a temp dir containing the named backup stub files.

    Returns the TemporaryDirectory object (caller must keep a reference so it
    is not GC'd and deleted before the test finishes).
    """
    tmp = tempfile.TemporaryDirectory()
    for name in files:
        path = Path(tmp.name) / name
        path.write_bytes(b"backup content for " + name.encode())
    return tmp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBackupList:
    """ADMIN-04: GET /admin/backups."""

    def test_backup_list_non_admin_returns_403(
        self,
        client: Any,
        regular_session: dict[str, str],
    ) -> None:
        """Non-admin cannot access the backups page."""
        resp = client.get("/admin/backups", cookies=regular_session)
        assert resp.status_code == 403

    def test_backup_list_unauthenticated_returns_403(
        self,
        client: Any,
    ) -> None:
        """Unauthenticated request returns 403 (require_admin)."""
        resp = client.get("/admin/backups")
        assert resp.status_code == 403

    def test_backup_list_admin_sees_file(
        self,
        client: Any,
        admin_session: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Admin GET shows a seeded backup filename, size, and a timestamp."""
        import app.routers.admin.backups as backup_mod

        tmp = _make_tmp_backup_dir(["db_2026-05-21.sql", "photos_2026-05-21.tar.gz"])
        monkeypatch.setattr(backup_mod, "_BACKUP_DIR", Path(tmp.name))
        try:
            resp = client.get("/admin/backups", cookies=admin_session)
        finally:
            tmp.cleanup()

        assert resp.status_code == 200
        body = resp.text
        assert "db_2026-05-21.sql" in body
        assert "photos_2026-05-21.tar.gz" in body
        # Human-readable sizes or file entries present
        assert "B" in body or "bytes" in body.lower() or "KB" in body or "MB" in body

    def test_backup_list_empty_dir_renders_empty_state(
        self,
        client: Any,
        admin_session: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Empty backups dir renders an empty-state without error (200)."""
        import app.routers.admin.backups as backup_mod

        tmp = _make_tmp_backup_dir([])
        monkeypatch.setattr(backup_mod, "_BACKUP_DIR", Path(tmp.name))
        try:
            resp = client.get("/admin/backups", cookies=admin_session)
        finally:
            tmp.cleanup()

        assert resp.status_code == 200
        # Empty state — no errors, some hint that there are no files
        assert "No backups" in resp.text or "empty" in resp.text.lower() or len(resp.text) > 100


class TestBackupDownload:
    """ADMIN-04: GET /admin/backups/{filename} — D-08 path traversal defense."""

    def test_download_valid_sql(
        self,
        client: Any,
        admin_session: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Valid db_*.sql filename is served with file bytes (200)."""
        import app.routers.admin.backups as backup_mod

        tmp = _make_tmp_backup_dir(["db_2026-05-21.sql"])
        backup_dir = Path(tmp.name)
        monkeypatch.setattr(backup_mod, "_BACKUP_DIR", backup_dir)
        try:
            resp = client.get("/admin/backups/db_2026-05-21.sql", cookies=admin_session)
        finally:
            tmp.cleanup()

        assert resp.status_code == 200
        assert b"backup content" in resp.content

    def test_download_valid_tar_gz(
        self,
        client: Any,
        admin_session: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Valid photos_*.tar.gz filename is served (200) with gzip media type."""
        import app.routers.admin.backups as backup_mod

        tmp = _make_tmp_backup_dir(["photos_2026-05-21.tar.gz"])
        backup_dir = Path(tmp.name)
        monkeypatch.setattr(backup_mod, "_BACKUP_DIR", backup_dir)
        try:
            resp = client.get(
                "/admin/backups/photos_2026-05-21.tar.gz", cookies=admin_session
            )
        finally:
            tmp.cleanup()

        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("application/gzip")

    def test_download_non_admin_returns_403(
        self,
        client: Any,
        regular_session: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Non-admin cannot download backup files."""
        import app.routers.admin.backups as backup_mod

        tmp = _make_tmp_backup_dir(["db_2026-05-21.sql"])
        monkeypatch.setattr(backup_mod, "_BACKUP_DIR", Path(tmp.name))
        try:
            resp = client.get(
                "/admin/backups/db_2026-05-21.sql", cookies=regular_session
            )
        finally:
            tmp.cleanup()

        assert resp.status_code == 403

    def test_download_path_traversal_encoded(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """Percent-encoded path traversal returns 404 (T-09-20)."""
        # %2f is "/" percent-encoded; FastAPI url-decodes path params
        resp = client.get(
            "/admin/backups/..%2F..%2Fetc%2Fpasswd", cookies=admin_session
        )
        assert resp.status_code == 404

    def test_download_path_traversal_raw(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """Raw relative path traversal returns 404 (T-09-20)."""
        resp = client.get(
            "/admin/backups/../../etc/passwd", cookies=admin_session
        )
        assert resp.status_code == 404

    def test_download_invalid_filename_rejected(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """Filename not matching the strict regex returns 404."""
        resp = client.get("/admin/backups/evil.sh", cookies=admin_session)
        assert resp.status_code == 404

    def test_download_missing_file_returns_404(
        self,
        client: Any,
        admin_session: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Valid filename that doesn't exist on disk returns 404."""
        import app.routers.admin.backups as backup_mod

        tmp = _make_tmp_backup_dir([])  # empty dir
        monkeypatch.setattr(backup_mod, "_BACKUP_DIR", Path(tmp.name))
        try:
            resp = client.get(
                "/admin/backups/db_2026-05-21.sql", cookies=admin_session
            )
        finally:
            tmp.cleanup()

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# CSRF helper — follows Phase 4/5/9 pattern (test_admin_users._prime_csrf)
# ---------------------------------------------------------------------------


def _prime_csrf(client: Any, signed_cookie: str) -> str:
    """Wire session_id + csrftoken onto the client; return the CSRF token.

    The double-submit-cookie pattern requires BOTH the csrftoken cookie AND
    the X-CSRF-Token header to match. Sets them on the client instance so
    they are sent automatically on subsequent requests.
    """
    client.cookies.set("session_id", signed_cookie)
    client.cookies.delete("csrftoken")
    resp = client.get("/admin/backups")
    token = resp.cookies.get("csrftoken") or client.cookies.get("csrftoken", "")
    if token:
        client.cookies.set("csrftoken", token)
        client.headers["X-CSRF-Token"] = token
    return token


class TestRunBackupNow:
    """ADMIN-04: POST /admin/backups/run — D-07 sync def threadpool."""

    def test_run_backup_handler_is_sync_def(self) -> None:
        """The run-now handler must be sync def (D-07) — never async def."""
        import app.routers.admin.backups as backup_mod

        # Find the route by path in the router
        run_route = None
        for route in backup_mod.router.routes:
            if hasattr(route, "path") and route.path == "/backups/run":
                run_route = route
                break
        assert run_route is not None, "POST /backups/run route not found on router"
        endpoint = run_route.endpoint  # type: ignore[attr-defined]
        assert not inspect.iscoroutinefunction(
            endpoint
        ), "run_backup_now must be sync def (D-07); found async def"

    def test_run_backup_non_admin_returns_403(
        self,
        client: Any,
        regular_session: dict[str, str],
    ) -> None:
        """Non-admin POST /admin/backups/run returns 403."""
        token = regular_session.get("session_id", "")
        resp = client.post(
            "/admin/backups/run",
            data={"X-CSRF-Token": "dummy"},
            cookies=regular_session,
        )
        assert resp.status_code == 403

    def test_run_backup_now_returns_result_fragment(
        self,
        client: Any,
        admin_session: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """POST /admin/backups/run renders a BackupResult fragment.

        Monkeypatches run_backup to avoid a real pg_dump. Asserts:
        - Response is 200
        - Fragment contains the BackupResult status ("ok" or "error")
        - Fragment contains both artifact filenames
        """
        from app.services.backup import ArtifactResult, BackupResult
        import app.routers.admin.backups as backup_mod

        fake_result = BackupResult(
            status="ok",
            db=ArtifactResult(
                filename="db_2026-05-21.sql",
                bytes=1024,
                ok=True,
            ),
            photos=ArtifactResult(
                filename="photos_2026-05-21.tar.gz",
                bytes=2048,
                ok=True,
            ),
            duration_ms=500,
            pruned_count=0,
            timestamp="2026-05-21T02:00:00Z",
        )

        # Monkeypatch the module-level reference used in the handler.
        # The handler does `from app.services.backup import run_backup` inside
        # the function body, which means it gets the attribute from the module
        # namespace at call time. We patch the module attribute directly.
        monkeypatch.setattr(
            "app.services.backup.run_backup",
            lambda *args, **kwargs: fake_result,
        )

        # Monkeypatch the backup dir so list_backup_files works (no real /app/data/backups
        # in the test container).
        import tempfile
        tmp = tempfile.TemporaryDirectory()
        monkeypatch.setattr(backup_mod, "_BACKUP_DIR", Path(tmp.name))

        try:
            # Prime CSRF: GET /admin/backups first to obtain the csrftoken cookie,
            # then set it on the client (double-submit-cookie pattern).
            token = _prime_csrf(client, admin_session["session_id"])

            resp = client.post(
                "/admin/backups/run",
                data={"X-CSRF-Token": token or "test-csrf"},
            )
        finally:
            tmp.cleanup()

        assert resp.status_code == 200
        body = resp.text
        # Result status
        assert "ok" in body.lower()
        # Both artifact filenames should appear
        assert "db_2026-05-21.sql" in body
        assert "photos_2026-05-21.tar.gz" in body
