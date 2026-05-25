"""GAP 3 — C4/C1 checker gate wiring (Phase 13, Plan 13-05).

scripts/check_c4_dark.py passes 10/10 checks (default) and 8/8 (--templates),
but nothing runs it in the test suite, meaning a structural regression can
introduce a failure and pass silently.

Wraps both modes via subprocess so any future breakage in the checker itself
or the files it inspects is caught. Uses sys.executable for the interpreter
so the test works inside the baked Docker image (where `python` may not be
on PATH but the venv python is guaranteed).

cwd is set to the repo root because check_c4_dark.py hardcodes repo-root-
relative paths (e.g. tailwind.config.js, app/static/css/tailwind.src.css).
Must NOT skip — the checker has no external deps beyond stdlib + the committed
source files. Pillow, FastAPI, Postgres are all irrelevant here.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Repo root = parent of the tests/ directory.
# pyproject.toml lives there; check_c4_dark.py uses Path(__file__).parent.parent
# to derive it, which resolves correctly when cwd == repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_CHECKER = _REPO_ROOT / "scripts" / "check_c4_dark.py"


def test_check_c4_dark_default_mode_exits_zero() -> None:
    """python scripts/check_c4_dark.py exits 0 (all default checks pass).

    Default mode checks:
      - tailwind.config.js: darkMode is 'selector'/'class', no @custom-variant
      - tailwind.src.css: no @custom-variant, .dark input + .dark a present,
        no @media prefers-color-scheme: dark
      - dark-toggle.js: Alpine.data('darkToggle') registered, snobbery:theme key,
        no eval(), no x-model

    A non-zero exit means at least one check failed — the output is captured and
    included in the assertion message so the failure is self-diagnosing.
    """
    assert _CHECKER.exists(), (
        f"scripts/check_c4_dark.py not found at {_CHECKER}. "
        "The checker must exist for the gate to work (Plan 13-05)."
    )
    result = subprocess.run(  # noqa: S603 — sys.executable + hardcoded checker path, no untrusted input
        [sys.executable, str(_CHECKER)],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "check_c4_dark.py (default mode) exited non-zero — one or more C4/C1 "
        "structural checks failed.\n\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def test_check_c4_dark_templates_mode_exits_zero() -> None:
    """python scripts/check_c4_dark.py --templates exits 0 (all template checks pass).

    --templates mode additionally checks:
      - base.html: snobbery:theme reference before Tailwind link (no-FOUC),
        no-FOUC script has nonce=, dark-toggle.js loaded with defer+nonce,
        dark-toggle.js before @alpinejs/csp core, safe-area-inset-top present
      - config_hub.html: x-data="darkToggle" present, setTheme() calls present

    A non-zero exit means at least one check failed.
    """
    assert _CHECKER.exists(), (
        f"scripts/check_c4_dark.py not found at {_CHECKER}. "
        "The checker must exist for the gate to work (Plan 13-05)."
    )
    result = subprocess.run(  # noqa: S603 — sys.executable + hardcoded checker path, no untrusted input
        [sys.executable, str(_CHECKER), "--templates"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "check_c4_dark.py --templates exited non-zero — one or more C4/C1 "
        "template structural checks failed.\n\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
