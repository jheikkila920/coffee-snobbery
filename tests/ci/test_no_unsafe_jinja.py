"""SEC-05 + D-04: forbidden patterns in ``app/templates/pages/`` templates.

Source of truth: ``.planning/phases/01-middleware/01-RESEARCH.md`` §18.5 and
``.planning/phases/01-middleware/01-CONTEXT.md`` §"Specific Ideas". Decisions
covered:

- **SEC-05 (Jinja2 autoescape + |safe ban):** ``|safe`` is forbidden under
  ``app/templates/pages/``. Autoescape stays ON globally; if a template
  ever needs to render trusted HTML, it does so via a typed component, not
  via the |safe filter.
- **D-04 (ban hx-on:* inline handlers):** HTMX's ``hx-on:click="..."``
  attribute compiles its argument with ``new Function()`` and requires CSP
  ``'unsafe-eval'``. We commit to Alpine CSP build + nonce-only scripts, so
  ``hx-on:`` MUST NOT appear in ``app/templates/pages/``. JS behavior lives
  in ``app/static/js/htmx-listeners.js`` (event delegation via
  ``htmx:configRequest``, ``htmx:beforeRequest``, ``htmx:afterSwap``).
- **D-04 supplement:** the same restriction extends to
  ``hx-vals='js:...'`` and ``hx-headers='js:...'`` — both run their argument
  through ``Function()`` and would re-introduce the CSP gap.

**Comment-strip step.** Before regex matching, this test strips Jinja
(``{# ... #}``) and HTML (``<!-- ... -->``) comments so a template's
documentation comment can mention ``|safe`` without self-triggering. The
strip is conservative (regex, single-pass, non-greedy) — it is not a Jinja
parser. If a future template embeds the forbidden token inside a more
complex comment shape, the test may need a real parser.

When ``app/templates/pages/`` is empty (or absent), pytest's parametrize
collects zero cases and the test is reported as skipped, not failed. The
test re-engages automatically the moment a real page template lands.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PAGES_DIR = Path("app/templates/pages")

FORBIDDEN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\|\s*safe"),
        "Pipe `|safe` is forbidden in user-facing templates (SEC-05).",
    ),
    (
        re.compile(r"\bhx-on:"),
        "`hx-on:*` is forbidden — use htmx-listeners.js event delegation (D-04).",
    ),
    (
        re.compile(r"hx-vals=['\"]js:"),
        "`hx-vals='js:...'` is forbidden — set via htmx:configRequest listener (D-04).",
    ),
    (
        re.compile(r"hx-headers=['\"]js:"),
        "`hx-headers='js:...'` is forbidden — set via htmx:configRequest listener (D-04).",
    ),
]

_JINJA_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def _strip_comments(source: str) -> str:
    """Remove Jinja and HTML comments so they cannot trigger the FORBIDDEN_PATTERNS scan."""
    source = _JINJA_COMMENT.sub("", source)
    source = _HTML_COMMENT.sub("", source)
    return source


@pytest.mark.parametrize(
    "template_path",
    list(PAGES_DIR.rglob("*.html")) if PAGES_DIR.exists() else [],
)
def test_template_safety(template_path: Path) -> None:
    """Every ``.html`` under ``app/templates/pages/`` is free of forbidden patterns.

    Parametrized over the file tree at collection time. An empty tree yields
    zero collected cases (pytest reports the test as skipped, which is the
    correct "no work to do" state for an unfinished UI phase).
    """
    raw = template_path.read_text(encoding="utf-8")
    scannable = _strip_comments(raw)
    for pattern, message in FORBIDDEN_PATTERNS:
        match = pattern.search(scannable)
        assert not match, (
            f"{template_path}: {message} "
            f"(matched: {match.group(0)!r})"
        )
