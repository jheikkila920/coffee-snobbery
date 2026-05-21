---
quick_id: 260517-make-smoke-grep-fix
status: complete
completed: 2026-05-17
commits:
  - "3f98959: fix(makefile): use alembic current for smoke migration check"
---

# Summary: Fix `make smoke` migration-applied assertion

## What changed

`Makefile`, `smoke:` recipe only — replaced the never-matching log grep with a direct query through `alembic current`. Also updated the comment block above the recipe to record *why* the grep approach was structurally broken (so the next reader doesn't reintroduce it).

```diff
-	docker compose logs coffee-snobbery | grep -E 'Running upgrade .* -> 0001'
+	docker compose exec coffee-snobbery alembic current | grep -E '^0001_initial \(head\)'
```

## Root cause (preserved here for future reference)

The original recipe asserted that the Alembic migration ran by grepping `docker compose logs` for the literal `Running upgrade <prev> -> 0001` line. Verified empirically against a fresh `docker compose down -v && up -d`: **that line is never emitted**.

- `entrypoint.sh` (Phase 0 / Plan 00-04) runs `alembic upgrade head` *before* uvicorn launches
- Structlog config (`app/logging.py`, Plan 00-02) is loaded in the FastAPI lifespan — i.e., inside the uvicorn process
- At migration time, the Alembic process uses raw stdlib logging at the default `WARNING` level
- `alembic.runtime.migration: Running upgrade ...` is an `INFO`-level message, so it is filtered out before reaching stdout

This means the original grep was a structurally impossible assertion, not just a regex mismatch. Adjusting the regex would not have fixed it; the line simply doesn't exist in the log stream.

## Why `alembic current` is the right replacement

- It queries `alembic_version` in Postgres directly — the canonical "did the migration apply?" check that Alembic itself uses for `--sql` planning
- It is independent of how logging is configured (now or in the future)
- Pinning the head revision (`0001_initial`) makes the assertion concrete: a future migration that lands a new head without updating this grep will fail loudly, which is the correct behavior
- When Phase 1+ introduces additional migrations, the maintainer updates this one regex line to track the new head — a 10-second edit, surfaces in PR diff

## Verification

| Probe | Command | Expected | Actual |
|---|---|---|---|
| Positive | `docker compose exec coffee-snobbery alembic current \| grep -E '^0001_initial \(head\)'` | exit 0, prints `0001_initial (head)` | exit 0, `0001_initial (head)` ✓ |
| Negative | same pipe, but `grep -E '^9999_nonexistent \(head\)'` | exit 1 | exit 1 ✓ |

Both ran against the live container at `coffee-snobbery` immediately after the Makefile edit.

## What didn't change

- `entrypoint.sh` — Alembic still runs at WARN-level stdlib logging at boot; this is fine, because we no longer depend on its log output for verification. The structlog integration inside uvicorn is intentional (FOUND-11) and untouched.
- `app/logging.py` — untouched.
- `docker-compose.yml`, `Dockerfile`, app code — untouched.

## Downstream effects

- `make smoke` on a Docker-equipped host (Linux / Mac / Windows via Git Bash or WSL) will now correctly assert the migration applied
- VPS deploys that invoke `make smoke` as a phase gate will surface real migration failures instead of always-passing silently
- The `coffee-snobbery` container must already be running when `make smoke`'s final assertion line executes — the recipe ensures that via the preceding `up -d --build` + `sleep 30` (no change to that sequencing)

## Deviations from plan

None. Plan executed exactly as written.

## Follow-ups (not in scope)

- The 30-second fixed `sleep` is OS-portable but not optimal — a `until curl /healthz` polling loop would finish faster on a warm cache and time out cleanly on a stuck container. Out of scope for this quick task; flag for a future Makefile portability pass.
- The `sleep` recipe step still breaks Windows-native `make` (cmd.exe has no `sleep`). Out of scope; the recipe targets Linux/Mac developer hosts and the VPS. Windows users can run via Git Bash, WSL, or replicate the steps in PowerShell. Documented in this conversation but not in repo until a portability pass is justified.
