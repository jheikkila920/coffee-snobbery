# ADR 0002: All Custom Middleware Is Pure ASGI

- Status: Accepted
- Date: 2026-05-16
- Phase: 1 (Middleware)
- Requirements: AUTH-10
- Supersedes: (none)

## Context

Starlette historically offered `starlette.middleware.base.BaseHTTPMiddleware` as an ergonomic way to write middleware as a class with a `dispatch(request, call_next)` method. The class wraps the downstream app in a Starlette `Request`/`Response` round-trip, which is convenient when the middleware needs to read the parsed body or build a typed response.

The convenience has a load-bearing cost: `BaseHTTPMiddleware` runs the downstream app inside a separate `asyncio.Task`. Python's `contextvars.ContextVar` mutations do not propagate across task boundaries by default. Any contextvar set inside an inner middleware or route handler is invisible to outer middlewares on the response path.

This breaks two things we depend on:

1. **`structlog.contextvars.bind_contextvars(request_id=..., csp_nonce=...)`** — set by `RequestContextMiddleware` at request entry. AUTH-10 requires every structured log line to carry the `request_id` for correlation. If a `BaseHTTPMiddleware` were inserted anywhere in the stack, log lines emitted by inner middlewares or route handlers would silently lose `request_id` — and worse, the loss is non-obvious because no exception is raised.

2. **`scope["state"]` mutations** — used by Plan 03 (`SecurityHeadersMiddleware` reads `csp_nonce`), Plan 04 (`SessionMiddleware` sets `user` + `session`), and Plan 08 (`csp_nonce(request)` Jinja global reads from `request.state.csp_nonce`). Some of these write to `scope["state"]` and some to `Request(scope).state` — both are aliases for the same dict. `BaseHTTPMiddleware` constructs a new `Request` inside its task, so writes by inner middleware can be invisible to outer middlewares depending on the exact code path.

The defect is silent. There is no error, no warning, no test failure that catches it. Diagnosis requires noticing that `request_id` is missing from a log line and tracing back through three middlewares.

## Decision

Every custom middleware in `app/middleware/` MUST be a **pure ASGI middleware** — a class with this exact shape:

```python
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class M:
    def __init__(self, app: ASGIApp, **opts) -> None:
        self.app = app
        # opts validation here

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Pre-request work: mutate scope["state"], bind contextvars, etc.

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                # Mutate message["headers"] here to add headers on the response path.
                ...
            await send(message)

        await self.app(scope, receive, send_wrapper)
```

`BaseHTTPMiddleware` and `starlette.middleware.base.BaseHTTPMiddleware` are **forbidden**.

Third-party middleware is permitted only when verified pure ASGI. As of Phase 1:

- `starlette_csrf.CSRFMiddleware` — VERIFIED pure ASGI (3.0.0)
- `slowapi` — registers an exception handler, not a middleware; pure ASGI is moot

## Consequences

- All five Phase 1 middlewares (`RequestContextMiddleware`, `SecurityHeadersMiddleware`, `FragmentCacheHeadersMiddleware`, `SessionMiddleware`, `CSRFMiddleware`) follow this rule.
- Future contributors writing new middleware in `app/middleware/` MUST follow the pure ASGI template from RESEARCH §4. The template handles non-HTTP scope (lifespan, WebSocket) by passing through unchanged.
- When wrapping outgoing responses, use the `send_wrapper(message)` pattern shown above. Intercept `http.response.start` to mutate `message["headers"]`; pass other message types (`http.response.body`, etc.) through unchanged.
- When reading cookies or headers from the incoming request, parse `scope["headers"]` directly rather than constructing a `starlette.requests.Request` — see `app/middleware/session.py:_parse_cookies` for the canonical strict parser.
- Performance benefit (incidental): pure ASGI middlewares show 20–30% lower per-request overhead than `BaseHTTPMiddleware` equivalents because there's no second `Task` construction per request.

## Alternatives Considered

- **Allow `BaseHTTPMiddleware`** with documented contextvars limitations — rejected. The limitation is silent (no exception, no warning, no test failure). Future contributors would inevitably hit it; we'd lose hours per incident chasing missing `request_id` correlation.
- **Adopt `asgi-correlation-id`** for `request_id`, accepting `BaseHTTPMiddleware` everywhere else — rejected. Pure ASGI is ~30 LOC per middleware; adding a third-party dependency to work around a known limitation is the wrong trade-off.
- **Document and ignore** — rejected. The mental tax on every future code review is not worth the convenience.

## Enforcement

- `app/middleware/__init__.py` opens with a docstring citing this ADR and the BaseHTTPMiddleware ban.
- Each Phase 1 middleware's module docstring restates the rule + the pitfall ID (RESEARCH §13.1) for in-context discoverability.
- Phase 12 may add a CI grep: `grep -rE 'BaseHTTPMiddleware' app/middleware/` MUST return zero hits. Until then, this ADR is enforced at PR review.

## References

- AUTH-10 (`.planning/REQUIREMENTS.md`)
- RESEARCH.md §4 (lifespan + middleware patterns), §13.1 (the contextvars pitfall)
- `app/middleware/__init__.py` (package docstring citing this ADR)
- `app/middleware/request_context.py` (the canonical pure-ASGI example)
- https://www.starlette.io/middleware/
- https://github.com/Kludex/starlette/discussions/2160
- https://www.encode.io/articles/working-with-http-requests-in-asgi
