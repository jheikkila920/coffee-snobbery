"""D-07a / SEC-02: CSP nonce correctness + unsafe-directive absence in ``app/templates/``.

Enforces two permanent security invariants:

1. **Nonce on every inline script/style tag (SEC-02):** Every ``<script>`` and
   ``<style>`` open tag under ``app/templates/`` must carry a ``nonce=`` attribute
   before its closing ``>``.  A tag without a nonce would execute outside the
   strict nonce-only CSP the app ships (``docs/decisions/0001``), opening an
   XSS/tampering vector.

2. **No ``'unsafe-eval'`` / ``'unsafe-inline'`` in templates (SEC-02):** These
   CSP directive literals must never appear in a template.  The documented
   trade-off (Alpine CSP build + nonce-only) lives in ``docs/decisions/`` — not
   in template source.

**Comment-strip step.**  Before regex matching this test strips Jinja
(``{# ... #}``) and HTML (``<!-- ... -->``) comments so a template's
documentation comment can mention the forbidden patterns without
self-triggering.  The strip is conservative (regex, single-pass,
non-greedy) — it is not a Jinja parser.

**Rule: fix the source, never loosen the test.**  If a violation is found,
the fix is a missing ``nonce={{ csp_nonce(request) }}`` in the source template,
not a regex adjustment.  CLAUDE.md: never disable CSP or security headers.

When ``app/templates/`` is empty (or absent), pytest's parametrize collects
zero cases and reports the test as skipped — correct "no work to do" state.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Anchor to the repo root (tests/ci/ -> repo root is parents[2]) so the scan is
# CWD-independent — a relative Path() run from any other directory would silently
# collect zero cases and look like a clean pass (12-REVIEW WR-05).
TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "app" / "templates"

# <script> or <style> open tag that lacks a nonce= attribute before the >.
# Negative lookahead: (?![^>]*\bnonce\s*=) asserts no "nonce=" anywhere
# between the tag name and the closing >.
SCRIPT_WITHOUT_NONCE = re.compile(
    r"<(script|style)(?![^>]*\bnonce\s*=)[^>]*>",
    re.IGNORECASE,
)

# Unsafe CSP directive literals that must never appear in template source.
UNSAFE_DIRECTIVES = re.compile(r"'unsafe-eval'|'unsafe-inline'")

_JINJA_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def _strip_comments(source: str) -> str:
    """Remove Jinja and HTML comments before scanning."""
    source = _JINJA_COMMENT.sub("", source)
    source = _HTML_COMMENT.sub("", source)
    return source


@pytest.mark.parametrize(
    "template_path",
    list(TEMPLATES_DIR.rglob("*.html")) if TEMPLATES_DIR.exists() else [],
)
def test_script_style_tags_have_nonce(template_path: Path) -> None:
    """Every ``<script>``/``<style>`` tag under ``app/templates/`` carries a nonce.

    Parametrized over the full template tree at collection time, covering
    ``pages/``, ``fragments/``, and any future subdirs.
    """
    raw = template_path.read_text(encoding="utf-8")
    scannable = _strip_comments(raw)
    match = SCRIPT_WITHOUT_NONCE.search(scannable)
    assert not match, (
        f"{template_path}: <script>/<style> tag is missing nonce= attribute (SEC-02 / D-07a). "
        f"(matched: {match.group(0)!r})  "
        f'Fix: add nonce="{{{{ csp_nonce(request) }}}}" to the tag. '
        f"Never loosen this test."
    )


@pytest.mark.parametrize(
    "template_path",
    list(TEMPLATES_DIR.rglob("*.html")) if TEMPLATES_DIR.exists() else [],
)
def test_no_unsafe_directives(template_path: Path) -> None:
    """No ``'unsafe-eval'`` or ``'unsafe-inline'`` literal in any template (SEC-02 / D-07a).

    The documented CSP trade-off (Alpine CSP build + nonce-only scripts) lives in
    ``docs/decisions/`` — never in template source.
    """
    raw = template_path.read_text(encoding="utf-8")
    scannable = _strip_comments(raw)
    match = UNSAFE_DIRECTIVES.search(scannable)
    assert not match, (
        f"{template_path}: forbidden CSP directive in template source (SEC-02 / D-07a). "
        f"(matched: {match.group(0)!r})  "
        f"Never loosen this test."
    )
