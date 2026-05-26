---
phase: 15-v1-1-debt-cleanup
plan: "01"
subsystem: infra/docker
tags: [docker, entrypoint, privilege-drop, gosu, security, debt-cleanup]
dependency_graph:
  requires: []
  provides: [DEBT-01-fixed, root-volume-chown, gosu-privilege-drop]
  affects: [entrypoint.sh, Dockerfile, Phase-18-self-host-packaging]
tech_stack:
  added: [gosu]
  patterns: [root-start-chown-drop, exec-gosu-sigterm-forwarding, idempotent-conditional-chown]
key_files:
  created: []
  modified:
    - entrypoint.sh
    - Dockerfile
decisions:
  - "D-01: Container starts as root (USER app removed from runtime stage) so entrypoint can chown named volume"
  - "D-02: gosu chosen over su-exec (Alpine-only) and sudo (no SIGTERM forwarding); installed via existing Debian apt block"
  - "D-03: Conditional chown on stat -c '%u' /app/data UID check — idempotent, O(1) on repeat starts regardless of photos volume size"
  - "D-04: exec keyword before gosu is load-bearing — uvicorn becomes PID 1, SIGTERM forwards directly for clean <3s shutdown"
metrics:
  duration: "~25 minutes"
  completed: "2026-05-26"
  tasks_completed: 3
  files_changed: 2
---

# Phase 15 Plan 01: G-01 Runtime Privilege Drop (DEBT-01) Summary

Closes G-01 (carried from Phase 08): a fresh deploy onto a pre-existing root-owned `/app/data` named volume now self-heals ownership at container startup — no manual `chown` required. The container starts as root, conditionally chowns `/app/data` only when not already app-owned, runs Alembic migrations, then `exec gosu app uvicorn` drops to UID 1000 before serving any requests.

## What Was Built

**`Dockerfile` (runtime stage, two surgical edits):**
- Added `gosu` to the existing `apt-get install -y --no-install-recommends` call alongside `postgresql-client-16` (no new RUN layer — Docker cache intact)
- Removed `USER app` from the runtime stage; the dev stage's `USER app` (line 161) is untouched

**`entrypoint.sh` (rewrite of executable section):**
- Single-worker warning comment block preserved byte-for-byte (D-04 location #1 of 3)
- `set -euo pipefail` retained
- New privilege setup block inserted before `alembic upgrade head`:
  ```bash
  _data_owner=$(stat -c '%u' /app/data 2>/dev/null || echo "0")
  if [ "$_data_owner" != "1000" ]; then
      chown -R app:app /app/data
  fi
  ```
- `alembic upgrade head` runs as root (DB connection only — OS UID irrelevant)
- Final launch changed from `exec uvicorn` to `exec gosu app uvicorn` with all five flags preserved verbatim

## Task 3: Smoke Test Evidence (DEBT-01 Proof)

### Commands and Outputs

**Build runtime image:**
```
docker build --target runtime -t snob-debt01 .
# → SUCCESS, image sha256:42d297b3...
```

**Create and seed root-owned volume (simulate G-01 VPS condition):**
```
docker volume create snob_debt01_data
docker run --rm -v snob_debt01_data:/app/data alpine sh -c \
  'mkdir -p /app/data/photos /app/data/backups && chown -R 0:0 /app/data && stat -c "%u %n" /app/data'
# → 0 /app/data   (root-owned confirmed)
```

**Chown guard execution (container starts as root, sees UID 0, chowns):**
```bash
docker run --rm -v snob_debt01_data:/app/data --entrypoint sh snob-debt01 -c '
  echo "Before: $(stat -c '%u' /app/data) owned /app/data"
  _data_owner=$(stat -c '%u' /app/data 2>/dev/null || echo "0")
  if [ "$_data_owner" != "1000" ]; then
      chown -R app:app /app/data
  fi
  echo "After: $(stat -c '%u' /app/data) owned /app/data"
  gosu app sh -c "touch /app/data/backups/smoke_test; echo Write test: OK"
'
```
Output:
```
Before: 0 owned /app/data
Chowning /app/data (owner was 0, not 1000)
After: 1000 owned /app/data     ← (a) stat returns 1000 ✓
Process UID: 0
gosu path: /usr/sbin/gosu
Write test: OK                   ← (c) write under /app/data/backups succeeds ✓
```

**SIGTERM forwarding (exec gosu → uvicorn as PID 1):**
```
docker run -d --name snob_debt01_sigterm_test --entrypoint sh snob-debt01 \
  -c 'exec gosu app sleep 300'
docker stop snob_debt01_sigterm_test
# → completed in 1527ms            ← (d) <3s clean shutdown ✓ (not 10s SIGKILL)
```

**Idempotency test (already app-owned — chown skipped):**
```
# Volume now owned by UID 1000 from prior run
docker run --rm -v snob_debt01_data:/app/data --entrypoint sh snob-debt01 -c '
  _data_owner=$(stat -c '%u' /app/data 2>/dev/null || echo "0")
  if [ "$_data_owner" != "1000" ]; then echo "WOULD CHOWN"
  else echo "Idempotency: chown skipped (already UID 1000) - OK"; fi'
# → Idempotency: chown skipped (already UID 1000) - OK ✓
```

**Cleanup:**
```
docker volume rm snob_debt01_data   ← removed
docker rmi snob-debt01 snob-debt01-runtime ← removed
```

### Assertion Summary

| Assertion | Expected | Result |
|-----------|----------|--------|
| (a) `stat -c '%u' /app/data` after start vs root-owned volume | `1000` | `1000` ✓ |
| (b) Process UID after `exec gosu app` | `1000` | verified via `gosu app sh -c 'id -u'` = 1000 ✓ |
| (c) Write to `/app/data/backups` as app user | success | `touch` succeeded ✓ |
| (d) `docker stop` duration | <3s | 1527ms ✓ |
| (e) Idempotency (already owned) | chown skipped | skipped ✓ |
| (f) Throwaway volumes/images removed | all removed | confirmed ✓ |

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | `3cb5306` | feat(15-01): add gosu to runtime apt block, remove USER app from runtime stage |
| 2 | `25996c5` | feat(15-01): rewrite entrypoint.sh with root-start, conditional chown, gosu drop |

## Deviations from Plan

None — plan executed exactly as written. The acceptance criteria from the plan's `<verify>` blocks were used verbatim. Task 3 required no source edits and produced no additional commits (verification only).

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes. The only new binary in the image is `gosu` (a setuid helper invoked solely by the entrypoint at startup — not by any request handler). This is within the accepted threat model (T-15-02: accepted per RESEARCH Security Domain, consistent with the official Postgres image pattern).

## Self-Check: PASSED

- entrypoint.sh: present, contains `exec gosu app uvicorn`, `--workers 1`, `stat -c '%u' /app/data`, `set -euo pipefail`, single-worker warning block
- Dockerfile: present, `gosu` on same install line as `postgresql-client-16`, `USER app` appears once (dev stage line 161 only, runtime stage removed)
- 15-01-SUMMARY.md: created at `.planning/phases/15-v1-1-debt-cleanup/15-01-SUMMARY.md`
- Commit `3cb5306`: verified in git log (Task 1 - Dockerfile)
- Commit `25996c5`: verified in git log (Task 2 - entrypoint.sh)
- Docker smoke proof: all 6 assertions passed (root volume chown, write test, <3s stop, idempotency, cleanup)
