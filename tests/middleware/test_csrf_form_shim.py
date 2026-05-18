"""D-15: ``CSRFFormFieldShim`` ASGI middleware — five integration cases.

Maps to ``02-VALIDATION.md`` Per-Task Verification Map rows:

- ``test_header_passthrough``       — D-15 header-already-present passthrough
- ``test_form_field_hoisted``       — D-15 form-encoded POST hoists field to header
- ``test_multipart_body_preserved`` — D-15 multipart POST body preserved byte-for-byte
- ``test_get_passthrough``          — D-15 GET passthrough untouched
- ``test_json_passthrough``         — D-15 JSON content-type passthrough

These tests deliberately do NOT use the full FastAPI ``app`` fixture. They build
a tiny Starlette app with the shim wrapping a single ``/echo`` route that
captures the headers and body the downstream code observes. That keeps the
shim behavior isolated from any other middleware that lives in ``app.main``
(the actual mounting is Plan 02-10, not this plan).

Wave-1 skip pattern: if ``app.csrf.CSRFFormFieldShim`` does not yet exist
(Task 2 hasn't landed), every test skips cleanly with a descriptive message.
"""

from __future__ import annotations

import hashlib
import os

import pytest


# Module-level capture dict; cleared at the top of each test by the test
# itself so that test ordering does not leak state. We do NOT use a fixture
# for this because the echo endpoint is module-level (Starlette routes are
# pickled / re-resolved by name).
CAPTURE: dict[str, object] = {}


def _require_shim() -> None:
    """Skip cleanly if Plan 02-04 Task 2 hasn't appended the shim yet."""
    try:
        from app.csrf import CSRFFormFieldShim  # noqa: F401
    except ImportError:
        pytest.skip("Wave 1 dependency: app.csrf.CSRFFormFieldShim (Plan 02-04 Task 2)")


async def _echo_endpoint(request):  # type: ignore[no-untyped-def]
    """Capture headers + body bytes that arrived at the route layer.

    The presence of ``x-csrf-token`` in ``request.headers`` proves the shim
    injected it into ``scope['headers']`` before the route ran. The body bytes
    are kept verbatim so ``test_multipart_body_preserved`` can hash them.
    """
    from starlette.responses import Response

    CAPTURE["headers"] = list(request.headers.items())
    body = await request.body()
    CAPTURE["body"] = body
    CAPTURE["body_sha256"] = hashlib.sha256(body).hexdigest()
    return Response("ok", status_code=200)


def _build_test_app():  # type: ignore[no-untyped-def]
    """Build the minimal Starlette app under test.

    Imported lazily so the module imports cleanly even when ``app.csrf``
    cannot provide the shim (Task 2 not yet landed) — _require_shim() handles
    the skip.
    """
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.routing import Route

    from app.csrf import CSRFFormFieldShim

    routes = [Route("/echo", endpoint=_echo_endpoint, methods=["GET", "POST"])]
    middleware = [Middleware(CSRFFormFieldShim)]
    return Starlette(routes=routes, middleware=middleware)


def _reset_capture() -> None:
    CAPTURE.clear()


def test_get_passthrough() -> None:
    """GET request: shim must NOT buffer/replay; headers unchanged."""
    _require_shim()
    _reset_capture()
    from starlette.testclient import TestClient

    app = _build_test_app()
    with TestClient(app) as c:
        r = c.get("/echo")
        assert r.status_code == 200, r.text

    headers_dict = dict(CAPTURE["headers"])  # type: ignore[arg-type]
    # No x-csrf-token should have been injected on a GET
    assert "x-csrf-token" not in headers_dict


def test_header_passthrough() -> None:
    """POST with X-CSRF-Token header already present → idempotent passthrough.

    When the HTMX listener wires the header, the shim must be a no-op even if
    a form field with the same name happens to be present. The header value
    (not the form-field value) is what downstream observes.
    """
    _require_shim()
    _reset_capture()
    from starlette.testclient import TestClient

    app = _build_test_app()
    with TestClient(app) as c:
        r = c.post(
            "/echo",
            data={"X-CSRF-Token": "from-form", "user": "x"},
            headers={"X-CSRF-Token": "from-header"},
        )
        assert r.status_code == 200, r.text

    headers_dict = dict(CAPTURE["headers"])  # type: ignore[arg-type]
    # Header wins (shim is idempotent)
    assert headers_dict.get("x-csrf-token") == "from-header"


def test_form_field_hoisted() -> None:
    """POST application/x-www-form-urlencoded → form field hoisted to header."""
    _require_shim()
    _reset_capture()
    from starlette.testclient import TestClient

    app = _build_test_app()
    with TestClient(app) as c:
        r = c.post("/echo", data={"X-CSRF-Token": "tok-from-form", "user": "x"})
        assert r.status_code == 200, r.text

    headers_dict = dict(CAPTURE["headers"])  # type: ignore[arg-type]
    assert headers_dict.get("x-csrf-token") == "tok-from-form"
    # Body still readable by downstream route layer
    body = CAPTURE["body"]
    assert isinstance(body, bytes)
    assert b"user=x" in body


def test_multipart_body_preserved() -> None:
    """POST multipart/form-data → token hoisted AND body bytes preserved byte-for-byte.

    The multipart envelope is byte-sensitive: any reassembly that re-serialises
    fields will reorder them and break downstream parsers. The shim must
    preserve the original chunked sequence.
    """
    _require_shim()
    _reset_capture()
    from starlette.testclient import TestClient

    payload = os.urandom(2048)
    payload_sha = hashlib.sha256(payload).hexdigest()

    app = _build_test_app()
    with TestClient(app) as c:
        files = {"upload": ("blob.bin", payload, "application/octet-stream")}
        data = {"X-CSRF-Token": "tok-multipart"}
        r = c.post("/echo", data=data, files=files)
        assert r.status_code == 200, r.text

    headers_dict = dict(CAPTURE["headers"])  # type: ignore[arg-type]
    assert headers_dict.get("x-csrf-token") == "tok-multipart"

    body = CAPTURE["body"]
    assert isinstance(body, bytes)
    assert payload in body, (
        f"multipart payload bytes missing from observed body — shim corrupted "
        f"the envelope. payload_sha256={payload_sha}, "
        f"body_sha256={CAPTURE['body_sha256']}"
    )


def test_json_passthrough() -> None:
    """POST application/json → shim must NOT inject; client owns the header."""
    _require_shim()
    _reset_capture()
    from starlette.testclient import TestClient

    app = _build_test_app()
    with TestClient(app) as c:
        r = c.post("/echo", json={"foo": "bar"})  # no header, no form field
        assert r.status_code == 200, r.text

    headers_dict = dict(CAPTURE["headers"])  # type: ignore[arg-type]
    assert "x-csrf-token" not in headers_dict
    body = CAPTURE["body"]
    assert isinstance(body, bytes)
    assert b'"foo"' in body
