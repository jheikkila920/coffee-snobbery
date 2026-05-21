"""Admin backups router — ADMIN-04.

Delivers the backups page (list retained nightly files + per-file download +
"Run backup now" button).

Security invariants (D-08, T-09-20):
  - Download route validates filename against _BACKUP_FILENAME_RE FIRST.
  - Then resolves the absolute path and confirms it stays inside _BACKUP_DIR
    via Path.is_relative_to() (defense-in-depth against any future regex
    relaxation).
  - Both checks run before is_file() so no existence information leaks on
    an invalid name.

Sync/async contract (D-07, T-09-21):
  - run_backup_now is sync def — FastAPI puts sync handlers in the threadpool
    so the long pg_dump never blocks the event loop or the in-process
    APScheduler.

All handlers require require_admin (T-09-24).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from sqlalchemy.orm import Session

from app import events
from app.dependencies.auth import require_admin
from app.dependencies.db import get_session
from app.models.user import User
from app.templates_setup import templates

log = structlog.get_logger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Module-level constants — monkeypatchable by tests (D-08)
# ---------------------------------------------------------------------------

_BACKUP_DIR = Path("/app/data/backups")

# Strict filename regex: db_YYYY-MM-DD.sql or photos_YYYY-MM-DD.tar.gz
# This is the PRIMARY path-traversal defense — any separator, dot-dot, or
# unexpected extension fails here before the filesystem is touched.
_BACKUP_FILENAME_RE = re.compile(
    r"^(?:db|photos)_\d{4}-\d{2}-\d{2}\.(?:sql|tar\.gz)$"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _human_size(size_bytes: int) -> str:
    """Return a human-readable file size string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _list_backup_files(backup_dir: Path) -> list[dict]:
    """Walk backup_dir and return file metadata list, newest-first.

    Returns an empty list if the directory doesn't exist or is empty.
    Each item: {filename, size_bytes, size_human, mtime_iso}.
    Only files matching _BACKUP_FILENAME_RE are included.
    """
    if not backup_dir.exists():
        return []
    entries = []
    for p in backup_dir.iterdir():
        if not p.is_file():
            continue
        if not _BACKUP_FILENAME_RE.match(p.name):
            continue
        stat = p.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        entries.append(
            {
                "filename": p.name,
                "size_bytes": stat.st_size,
                "size_human": _human_size(stat.st_size),
                "mtime_iso": mtime.strftime("%Y-%m-%d %H:%M UTC"),
            }
        )
    # Newest first (by mtime)
    entries.sort(key=lambda e: e["mtime_iso"], reverse=True)
    return entries


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/backups", response_class=HTMLResponse)
def list_backups(
    request: Request,
    user: User = Depends(require_admin),  # noqa: B008
) -> Response:
    """GET /admin/backups — list retained backup files.

    Disk-walks _BACKUP_DIR, collects (filename, size, mtime) for valid-name
    files only, sorted newest-first. Empty dir renders empty-state gracefully.
    HTMX fragment request → fragments/admin_backup_list.html.
    Full-page request → pages/admin_backups.html.
    """
    files = _list_backup_files(_BACKUP_DIR)
    ctx: dict = {"user": user, "files": files}

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request,
            name="fragments/admin_backup_list.html",
            context=ctx,
        )
    return templates.TemplateResponse(
        request=request,
        name="pages/admin_backups.html",
        context=ctx,
    )


@router.get("/backups/{filename}")
def download_backup(
    filename: str,
    request: Request,
    user: User = Depends(require_admin),  # noqa: B008
) -> FileResponse:
    """GET /admin/backups/{filename} — admin-gated file download.

    Dual path-traversal defense (D-08, T-09-20):
    1. Strict regex check FIRST — rejects any name that is not exactly
       db_YYYY-MM-DD.sql or photos_YYYY-MM-DD.tar.gz. Percent-encoded
       separators (``%2f``, ``%5c``) are url-decoded by FastAPI before this
       check, so ``../`` patterns are already plain ``../`` when we see them.
    2. Path.resolve().is_relative_to() — confirms the fully-resolved
       absolute path stays inside _BACKUP_DIR after OS path normalisation.
    3. is_file() — confirms existence (no information leak for invalid names
       since those were already rejected by step 1).
    """
    # Step 1: strict regex — primary traversal defense
    if not _BACKUP_FILENAME_RE.match(filename):
        raise HTTPException(status_code=404)

    # Step 2: resolve and confirm containment — belt-and-braces
    backup_path = (_BACKUP_DIR / filename).resolve()
    backup_dir_resolved = _BACKUP_DIR.resolve()
    if not backup_path.is_relative_to(backup_dir_resolved):
        raise HTTPException(status_code=404)

    # Step 3: existence check
    if not backup_path.is_file():
        raise HTTPException(status_code=404)

    media_type = (
        "application/gzip"
        if filename.endswith(".gz")
        else "application/octet-stream"
    )
    return FileResponse(backup_path, media_type=media_type, filename=filename)


@router.post("/backups/run", response_class=HTMLResponse)
def run_backup_now(
    request: Request,
    user: User = Depends(require_admin),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> Response:
    """POST /admin/backups/run — synchronous "Run backup now" handler.

    D-07: this handler is sync def (NOT async def). FastAPI runs sync
    handlers in the thread pool so the long-running pg_dump never blocks
    the event loop or the in-process APScheduler nightly job.

    CSRF: the CSRFFormFieldShim reads the X-CSRF-Token hidden field from
    the form body and hoists it to the X-CSRF-Token header before
    CSRFMiddleware validates it. This handler does not need to call
    request.form() because no other form fields are needed; the middleware
    has already validated the token before execution reaches here.

    Emits ADMIN_BACKUP_TRIGGERED with user_id only (no secrets, T-09-23).
    Renders admin_backup_result.html with the BackupResult, and includes
    an hx-swap-oob refresh of #admin-backup-list so the file list updates
    in-place without a full-page reload.
    """
    from app.services.backup import run_backup

    result = run_backup(db, by_user_id=user.id)

    log.info(events.ADMIN_BACKUP_TRIGGERED, user_id=user.id)

    # Refresh the file list for OOB swap
    files = _list_backup_files(_BACKUP_DIR)

    return templates.TemplateResponse(
        request=request,
        name="fragments/admin_backup_result.html",
        context={"user": user, "result": result, "files": files},
    )
