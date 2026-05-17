"""FOUND-10: ``app/config.py`` is the only module that reads ``os.environ``.

This is the Python equivalent of the verbatim shell grep from
``00-RESEARCH.md §Validation Architecture``::

    ! grep -RIn --include='*.py' --exclude-dir=migrations \\
        'os\\.environ' app/ | grep -v 'app/config\\.py:'

Why a Python test instead of a CI shell step? Because the test suite is the
canonical enforcement point, and a unit test gives a precise failure message
listing each offender. A shell grep in CI catches the same violations once
Phase 12 wires GitHub Actions.

The test deliberately greps for the literal string ``os.environ`` — direct
attribute access, indirect calls via ``getattr(os, "environ")``, and reads
through helpers like ``dotenv`` are all out of scope at this layer; the
broader rule (no env reads outside config.py) is socially enforced via code
review.
"""

from __future__ import annotations

from pathlib import Path

# Repo root: tests/ is at repo root, so parent of this file's parent is the root.
REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT / "app"
ALLOWED = {APP_DIR / "config.py"}
# Plan 03 will create app/migrations/; alembic-generated migration code may
# legitimately reference os.environ (e.g., for offline migration mode). Exclude
# preemptively so adding the directory in Plan 03 doesn't break this test.
EXCLUDED_DIRS = {"migrations"}


def test_os_environ_only_in_config() -> None:
    """Walk app/ and assert ``os.environ`` appears only in ``app/config.py``."""
    offenders: list[str] = []
    for py_file in APP_DIR.rglob("*.py"):
        # Skip excluded directories (e.g., migrations/).
        if any(part in EXCLUDED_DIRS for part in py_file.relative_to(APP_DIR).parts):
            continue
        if py_file in ALLOWED:
            continue
        text = py_file.read_text(encoding="utf-8")
        if "os.environ" in text:
            offenders.append(str(py_file.relative_to(REPO_ROOT)))

    assert not offenders, (
        "FOUND-10 violation: os.environ may only be referenced in app/config.py.\n"
        "Offending files:\n  " + "\n  ".join(offenders) + "\n"
        "Fix: add a typed field to Settings in app/config.py and import "
        "`from app.config import settings` instead (CLAUDE.md §'Adding a new env var')."
    )
