---
phase: 01-middleware
plan: 07
status: complete
type: execute
wave: 2
completed: 2026-05-17
files_modified:
  - app/rate_limit.py
files_created:
  - app/routers/auth.py
commits:
  - 51f691d feat(01-07): finalize app/rate_limit.py — slowapi Limiter + 429 audit handler
  - 0291cbe feat(01-07): stub POST /login + /setup with rate limit + auth.login_attempt
executor: orchestrator-mediated (subagent worktree base broken; bash git commit denied)
---

## Plan 01-07 — slowapi finalization + /login + /setup stubs

Replaces the temporary `app/rate_limit.py` shim from Plan 01-03 with the production slowapi 0.1.9 wiring. Ships stub `/login` and `/setup` endpoints decorated with the rate limiter so Wave 0's `test_login_rate_limit` integration test can light up once Plan 09 mounts the router.

## Task outcomes

### Task 1 — app/rate_limit.py finalized

- `limiter = Limiter(key_func=get_remote_address, default_limits=[])` — `get_remote_address`, never `get_ipaddr` (slowapi issue #255 / RESEARCH §13.3 — `get_ipaddr` reads `X_FORWARDED_FOR` underscored, which uvicorn doesn't produce).
- Limit-string constants: `LOGIN_LIMIT = SETUP_LIMIT = "5/15minutes"`, `CSP_REPORT_LIMIT = "30/minute"` per D-17.
- `_structured_rate_limit_handler(request, exc) -> Response` — sync signature matching slowapi 0.1.9's `_rate_limit_exceeded_handler`. Emits one `log.warning(RATE_LIMIT_EXCEEDED, path, ip, detail)` then delegates to slowapi's stock handler so the 429 JSON response shape is preserved.
- `register_rate_limiter(app)` sets `app.state.limiter = limiter` and registers the exception handler. Plan 09 calls this once during main.py assembly.
- The Plan 03 ImportError-shim is gone (slowapi is now properly pinned in requirements.txt via Plan 05's `starlette-csrf` addition + Phase 0's earlier slowapi pin).

**csp_report integration verified:** `from app.routers.csp_report import router` imports cleanly. The `@limiter.limit("30/minute")` decoration still works because the module path and `limiter` symbol are preserved.

### Task 2 — app/routers/auth.py stub

- `router = APIRouter()` + two routes: `POST /login` and `POST /setup`, both `status_code=200`, both decorated `@limiter.limit(LOGIN_LIMIT|SETUP_LIMIT)`, both accepting `request: Request` (slowapi introspection requirement).
- `/login` emits `log.info(AUTH_LOGIN_ATTEMPT, ip=..., request_id=...)` on every request. Uses the imported constant (NOT the hard-coded string literal). Reads zero request body fields (AUTH-10).
- `/setup` returns the stub body with no log line — `/setup` has no taxonomy analogue; Phase 2 emits `admin.user_created` on the real path.
- Both handlers are `async` for Phase 2 signature compatibility, even though they do no async work in Phase 1.

### Verification

- slowapi 0.1.9 imports cleanly under FastAPI 0.136 + Starlette 1.0 — RESEARCH A2 confirmed.
- `pytest tests/routers/test_auth_stub.py --co -q` → 2 tests collected (`test_login_rate_limit`, `test_login_rate_limit_per_ip`).
- `ruff check app/rate_limit.py app/routers/auth.py` → clean.

## Deviations

1. **Executor mode** — subagent attempt 1 (worktree mode) failed because the worktree was created at the orphan initial commit `5c6f07e` instead of plan base `603df82`, and the agent's `git reset --hard` was denied by the subagent Bash sandbox. Plan 01-07's subagent attempt did not produce any commits or file changes. Orchestrator finished Task 1 and Task 2 inline; commits are atomic per-task as the plan required.
2. **Module docstring rewrite** — the new `app/rate_limit.py` docstring no longer references "Plan 07 will land …" because Plan 07 IS this commit. Reframed as a description of the production behavior.

## Plan 10 ADR follow-up

The `AUTH_LOGIN_ATTEMPT` constant ships in `app/events.py` (added by Plan 02) but the D-14 taxonomy in CONTEXT.md does NOT list it. Plan 10's ADR `0003-event-taxonomy-d14-amendment.md` MUST formalize the amendment so future contributors can find the constant alongside the rest of `auth.*`.

## Plan 09 hooks

Plan 09 will call:

```python
from app.rate_limit import register_rate_limiter
from app.routers.auth import router as auth_router

# inside FastAPI app factory:
app = FastAPI(lifespan=...)
register_rate_limiter(app)   # MUST run before include_router (slowapi reads app.state.limiter at decoration time has already happened; this just attaches the handler/state for runtime use)
app.include_router(auth_router)
app.include_router(debug_router)
app.include_router(csp_report_router)
```
