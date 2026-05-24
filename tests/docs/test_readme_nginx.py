"""SEC-04 + D-16: README documents the production NGINX server block.

Source of truth: ``.planning/phases/01-middleware/01-RESEARCH.md`` §10
(NGINX Reverse-Proxy Example) — the README is the authoritative artifact a
sysadmin copies when configuring NGINX in front of the ``coffee-snobbery``
container.

Required README content (each test asserts a literal substring):

- ``Strict-Transport-Security`` header line with ``max-age=63072000`` — HSTS
  enforces HTTPS for two years. Per RESEARCH §10 this is the recommended
  minimum for production.
- ``proxy_set_header X-Forwarded-Proto $scheme`` — uvicorn's
  ``--proxy-headers`` rewrites ``request.url.scheme`` from this header. Drop
  the line and cookies marked ``Secure`` silently break.
- ``proxy_buffering off`` — staged now even though Phase 1 doesn't use SSE;
  Phase 7 may switch from polling to SSE in v1.1. Pre-baking the directive
  avoids retroactive NGINX edits.

When ``README.md`` does not yet exist (Plan 08 lands the README + NGINX
block), the tests ``pytest.skip`` rather than fail. The test re-engages
automatically once the README appears.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_README_PATH = Path("README.md")


def _readme_text() -> str:
    """Return the README contents, or skip the calling test if missing."""
    if not _README_PATH.exists():
        pytest.skip("README.md not yet created — Plan 08 lands the NGINX block")
    return _README_PATH.read_text(encoding="utf-8")


def test_readme_has_hsts() -> None:
    """README documents the HSTS header line at the recommended max-age."""
    text = _readme_text()
    assert "Strict-Transport-Security" in text, (
        "README missing literal `Strict-Transport-Security` header line"
    )
    assert "max-age=63072000" in text, (
        "README missing recommended HSTS `max-age=63072000` (two years)"
    )


def test_readme_has_proxy_proto_header() -> None:
    """README documents the X-Forwarded-Proto $scheme directive."""
    text = _readme_text()
    assert "proxy_set_header X-Forwarded-Proto $scheme" in text, (
        "README missing literal `proxy_set_header X-Forwarded-Proto $scheme` "
        "(uvicorn --proxy-headers depends on it)"
    )


def test_readme_has_proxy_buffering_off() -> None:
    """README documents `proxy_buffering off` (Phase 7 SSE pre-bake per RESEARCH §10)."""
    text = _readme_text()
    assert "proxy_buffering off" in text, "README missing literal `proxy_buffering off` directive"
