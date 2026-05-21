---
quick_id: 260517-make-smoke-grep-fix
mode: quick
created: 2026-05-17
status: ready
files_modified:
  - Makefile
---

# Fix `make smoke` migration-applied assertion

## Problem

The `smoke:` recipe in `Makefile` asserts the migration ran by grepping `docker compose logs coffee-snobbery | grep -E 'Running upgrade .* -> 0001'`. This grep always returns empty because **the line is never emitted**:

- `entrypoint.sh` runs `alembic upgrade head` *before* uvicorn starts
- Structlog configuration lives in the FastAPI lifespan inside uvicorn
- At migration time, Alembic uses raw stdlib logging at the default `WARNING` level
- `Running upgrade ...` is an `INFO` message, so it is dropped — not just hidden behind a JSON envelope, but never written

Verified empirically: `docker compose down -v && docker compose up -d` produces zero lines matching `upgrade|alembic|0001` in the container logs (only uvicorn's startup banner appears).

## Fix

Replace the log-grep with a `docker compose exec coffee-snobbery alembic current` check. This queries `alembic_version` directly through Alembic's own runtime — the canonical "did the migration apply?" assertion — and is independent of log format or visibility.

Pin the expected revision (`0001_initial`) via `grep` so the smoke test fails loudly if a future migration is the new head but the assertion forgot to update.

## Task

**Edit `Makefile`, `smoke:` recipe only.**

Before:
```
docker compose logs coffee-snobbery | grep -E 'Running upgrade .* -> 0001'
```

After:
```
docker compose exec coffee-snobbery alembic current | grep -E '^0001_initial \(head\)'
```

Keep the rest of the recipe unchanged (`docker compose down -v`, `up -d --build`, `sleep 30`, `curl -fsS /healthz`, the trailing `smoke: OK` echo, the surrounding `@echo` lines).

## Verification

1. From the repo root, run the new check against the currently-running stack:
   ```
   docker compose exec coffee-snobbery alembic current | grep -E '^0001_initial \(head\)'
   ```
   Expected: exit 0, prints `0001_initial (head)`.

2. Smoke gate (cold-start): `make smoke` (on a host with `make` + Docker) — first three steps unchanged, the new grep step replaces the old log-grep, exit code propagation preserved.

3. Negative test (optional): rename the migration head locally and re-run — the grep should fail with exit 1, surfacing the regression. Revert after.

## Done when

- `Makefile` `smoke:` recipe uses `alembic current` instead of `docker compose logs | grep upgrade`
- Manual run of the new line against the live stack returns 0
- One conventional commit on `main`: `fix(makefile): use alembic current for smoke migration check`
- `260517-make-smoke-grep-fix-SUMMARY.md` written in this directory
