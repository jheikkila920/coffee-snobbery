"""FOUND-09: ``.env.example`` documents every ``Settings`` field, and vice versa.

The test parses ``.env.example`` for ``^([A-Z][A-Z0-9_]+)=`` keys (one per
non-blank, non-comment line), compares the resulting set against
``Settings.model_fields.keys()``, and asserts strict equality. Either side
having an extra key fails the test with a diff naming the missing / extra keys.

This is a fast (~10ms) regex test; it does not require a database. The
``conftest.py`` env-var stubs satisfy ``Settings.__init__`` so the import
succeeds in CI.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.config import Settings

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_EXAMPLE = REPO_ROOT / ".env.example"

# Match KEY=anything on a line. Allow optional whitespace before KEY (none
# expected in practice, but tolerant). Comments (#) and blank lines are
# implicitly skipped because they don't match this pattern.
_KEY_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]+)\s*=")


def _parse_env_example_keys() -> set[str]:
    found: set[str] = set()
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        m = _KEY_RE.match(line)
        if m:
            found.add(m.group(1))
    return found


def test_env_example_documents_all_vars() -> None:
    """Every Settings field appears in .env.example and vice versa."""
    expected = set(Settings.model_fields.keys())
    found = _parse_env_example_keys()

    missing = expected - found
    extra = found - expected

    assert not missing and not extra, (
        "FOUND-09 violation: .env.example must document every Settings field "
        "(and no extras).\n"
        f"  Missing from .env.example: {sorted(missing) or 'none'}\n"
        f"  Extra in .env.example:     {sorted(extra) or 'none'}\n"
        "Fix: edit .env.example to match Settings, or update Settings to match."
    )
