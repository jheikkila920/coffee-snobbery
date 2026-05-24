"""D-07b / SEC-6: ``model_dump()`` must never be called in files that reference ``ApiCredential``.

Enforces the SEC-6 invariant: the decrypted API key must never enter a
serializable dict.

Design context (``app/models/api_credential.py`` module docstring):
  The ``last_four`` column is denormalized so the admin list view can mask
  the key without invoking the encryption service.  This keeps audit log
  lines and error messages safely tail-masked (SEC-6: never put the
  decrypted key in a Pydantic schema that could leak via ``model_dump()``).

``app/services/credentials.py`` returns a frozen ``@dataclass ProviderCredential``
(NOT a Pydantic model) holding the decrypted key — so ``model_dump`` is
structurally impossible there.  This grep makes that invariant permanent:
if anyone ever refactors ``ProviderCredential`` to a Pydantic model and
calls ``model_dump()`` in a credential-referencing file, this test fails the
build immediately.

**Early-return guard:** files that do not reference ``ApiCredential`` or
``api_credential`` are skipped to avoid false positives on unrelated files
that legitimately call ``model_dump()`` for other models.

**Comment/docstring strip:** Python triple-quoted docstrings and ``# comments``
are stripped before scanning so documentation that *mentions* ``model_dump()``
as an example of the forbidden pattern does not self-trigger (see
``app/models/api_credential.py`` line 16 — the module docstring that
describes this exact invariant).

**Rule: fix the source, never loosen the test.**  If a violation is found,
move the dump off the credential code path or replace the Pydantic model
with a frozen dataclass.  CLAUDE.md: never log API keys.

When ``app/`` is absent, pytest collects zero cases and reports the test
as skipped — correct "no work to do" state.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

APP_DIR = Path("app")

# Matches a model_dump() call — word boundary prevents partial matches.
MODEL_DUMP_PATTERN = re.compile(r"\bmodel_dump\s*\(")

# Strip triple-double-quoted docstrings before scanning to avoid matching
# documentation that discusses model_dump() as a forbidden example.
_PY_TRIPLE_DOUBLE = re.compile(r'""".*?"""', re.DOTALL)
_PY_TRIPLE_SINGLE = re.compile(r"'''.*?'''", re.DOTALL)
# Strip single-line comments.
_PY_COMMENT = re.compile(r"#[^\n]*")


def _strip_python_non_code(source: str) -> str:
    """Remove triple-quoted strings and ``#`` comments before scanning.

    Prevents docstrings that *document* the model_dump invariant from
    self-triggering the grep (e.g. ``app/models/api_credential.py``
    module docstring line 16).
    """
    source = _PY_TRIPLE_DOUBLE.sub("", source)
    source = _PY_TRIPLE_SINGLE.sub("", source)
    source = _PY_COMMENT.sub("", source)
    return source


@pytest.mark.parametrize(
    "source_path",
    [p for p in APP_DIR.rglob("*.py") if p.exists()] if APP_DIR.exists() else [],
)
def test_no_api_credential_model_dump(source_path: Path) -> None:
    """``model_dump()`` must not be called in any file that references ``ApiCredential``.

    Parametrized over every ``app/**/*.py`` at collection time.  Files that do
    not reference ``ApiCredential`` or ``api_credential`` are skipped (early
    return) to keep the scan narrow and avoid false positives on unrelated
    models.
    """
    src = source_path.read_text(encoding="utf-8")

    # Early-return: skip files that don't reference credentials at all.
    if "ApiCredential" not in src and "api_credential" not in src.lower():
        return

    scannable = _strip_python_non_code(src)
    match = MODEL_DUMP_PATTERN.search(scannable)
    assert not match, (
        f"{source_path}: model_dump() called in a file that references ApiCredential "
        f"(SEC-6 / D-07b). "
        f"Line: {src[:match.start()].count(chr(10)) + 1}. "
        f"Fix: keep the decrypted key in a frozen dataclass (ProviderCredential), "
        f"never in a Pydantic model that can be serialized via model_dump(). "
        f"Never loosen this test."
    )
