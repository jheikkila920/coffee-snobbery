---
phase: 18-self-host-packaging
plan: 01
subsystem: infra
tags: [docker-compose, packaging, self-host, ghcr, compose-override]

requires:
  - phase: 17-ia-restructure
    provides: "Final app surface; no compose changes in Phase 17"

provides:
  - "Operator-facing docker-compose.yml: GHCR image pin, no build: block, no test service"
  - "docker-compose.override.yml.example: committed dev build block + test service template"
  - ".gitignore and .dockerignore exclude docker-compose.override.yml"

affects:
  - 18-02-plan (Dockerfile labels — no compose changes needed)
  - 18-03-plan (release workflow — references operator compose file)
  - 18-05-plan (README — references v1.2.0 tag and upgrade path)

tech-stack:
  added: []
  patterns:
    - "Compose override-file pattern: operator-facing compose pins image:, dev override adds build:"
    - "Dev loop: cp docker-compose.override.yml.example docker-compose.override.yml; Compose auto-merges"

key-files:
  created:
    - docker-compose.override.yml.example
  modified:
    - docker-compose.yml
    - .gitignore
    - .dockerignore

key-decisions:
  - "D-04: operator compose pins image to ghcr.io/jheikkila54/coffee-snobbery:v1.2.0"
  - "D-05: override-file pattern; docker-compose.override.yml is gitignored; example committed"
  - "D-06: coffee-snobbery-test service removed from operator compose, lives only in override.example"

requirements-completed: [DIST-01]

duration: 15min
completed: 2026-05-28
---

# Phase 18 Plan 01: Compose Split Summary

**docker-compose.yml transformed to operator-facing GHCR image-pull-only stack; dev build block and test service moved to committed docker-compose.override.yml.example**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-05-28
- **Completed:** 2026-05-28
- **Tasks:** 3
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments

- docker-compose.yml now satisfies DIST-01: `docker compose up -d` pulls ghcr.io/jheikkila54/coffee-snobbery:v1.2.0 without invoking any build step
- docker-compose.override.yml.example committed at repo root with dev `build: target: runtime` block for coffee-snobbery and the full test service (target: dev, profiles [test], SNOB_CI)
- Both .gitignore and .dockerignore exclude docker-compose.override.yml so the dev override can never accidentally land in VCS or a built image

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite docker-compose.yml** - `7a6934b` (feat)
2. **Task 2: Create docker-compose.override.yml.example** - `6260dbb` (feat)
3. **Task 3: Add override to .gitignore and .dockerignore** - `d6840ea` (chore)

**Plan metadata:** committed with SUMMARY in same chore commit

## Files Created/Modified

- `docker-compose.yml` - Removed build: block, changed image to GHCR pin, deleted coffee-snobbery-test service, updated header comment; db service/networks/volumes blocks unchanged
- `docker-compose.override.yml.example` - New file: dev build block (target: runtime) + test service (target: dev, profiles [test], SNOB_CI, no container_name, no volumes, BAKED tree)
- `.gitignore` - Appended docker-compose.override.yml entry with explanation comment
- `.dockerignore` - Appended docker-compose.override.yml entry with explanation comment

## Decisions Made

Preserved `127.0.0.1:8080:8000` port binding unchanged per D-16 (plain-nginx path requirement). Operators running NPM who want to skip the host bind are instructed in README (Plan 05) — this plan makes no change to the port binding.

The `docker compose config` merge test in the plan's acceptance criteria required `--profile test` to show the profiled test service — expected Compose behavior, not a bug. The merge validates correctly with the flag.

## Deviations from Plan

None — plan executed exactly as written. The merge sanity check in the plan's acceptance criteria omitted `--profile test`; verified with the flag and documented for Plan 05 README completeness.

## Validation Results

| Validator | Command | Result |
|-----------|---------|--------|
| V18-01 | `docker compose -f docker-compose.yml config \| python -c "...assert no build, assert GHCR pin, assert no test service..."` | PASS |
| V18-17 | `grep -q '^docker-compose.override.yml$' .gitignore && .dockerignore` | PASS |
| V18-18 | `test -f docker-compose.override.yml.example && yaml parses && target checks && LF endings` | PASS |

## Issues Encountered

None.

## Next Phase Readiness

- Plan 02 (Dockerfile OCI labels + APP_VERSION ARG) is independent — no compose changes needed
- Plan 03 (release workflow) can reference the operator compose file and GHCR path established here
- Plan 05 (README) will document the v1.2.0 tag, override copy pattern, and upgrade path

## Self-Check

- [x] docker-compose.yml at `C:\Claude\Coffee-Snobbery\docker-compose.yml` — verified
- [x] docker-compose.override.yml.example at `C:\Claude\Coffee-Snobbery\docker-compose.override.yml.example` — verified
- [x] Commits 7a6934b, 6260dbb, d6840ea exist in git log — verified
- [x] V18-01, V18-17, V18-18 all pass
- [x] ruff format --check + ruff check both exit 0

## Self-Check: PASSED

---
*Phase: 18-self-host-packaging*
*Completed: 2026-05-28*
