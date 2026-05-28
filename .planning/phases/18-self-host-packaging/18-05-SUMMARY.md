---
phase: 18-self-host-packaging
plan: "05"
subsystem: docs
tags: [docs, readme, contributing, self-host, npm, operator-ux]
dependency_graph:
  requires: [18-01, 18-02, 18-03, 18-04]
  provides: [DIST-03, DIST-04, DIST-05-documented]
  affects: [README.md, CONTRIBUTING.md, CLAUDE.md]
tech_stack:
  added: []
  patterns: [operator-first-docs, dev-contributing-split, ghcr-public-visibility-ritual]
key_files:
  created:
    - CONTRIBUTING.md
  modified:
    - README.md
    - CLAUDE.md
decisions:
  - "D-14: README leads with operator content; dev content moved to CONTRIBUTING.md"
  - "D-15: NPM walkthrough as field-list + gotchas (no screenshots)"
  - "D-16: Plain-NGINX server-block preserved verbatim"
  - "D-19: Upgrade is exactly three lines: edit tag, pull, up -d"
  - "D-20: GHCR 403 troubleshooting entry added"
  - "D-18: DIST-05 fresh-install smoke documented in Quickstart"
  - "D-07: Operator quickstart uses raw docker compose only — no make prereq"
metrics:
  duration: "~25 minutes"
  completed: "2026-05-28"
  tasks_completed: 3
  tasks_total: 3
  files_modified: 3
---

# Phase 18 Plan 05: Operator-First Docs Rewrite Summary

Rewrote README.md to lead with operator content, created CONTRIBUTING.md to hold dev content carved from README, and appended three pointer rows to CLAUDE.md's "Files worth knowing" table. Satisfies DIST-03 (complete from-zero operator walkthrough), DIST-04 (NPM step-by-step with field tables), and DIST-05 (fresh-install smoke procedure documented).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Operator-first README rewrite | 0e132c6 | README.md (rewrite: 147 insertions, 105 deletions) |
| 2 | CONTRIBUTING.md dev guide | 3eb5a93 | CONTRIBUTING.md (new: 187 lines) |
| 3 | CLAUDE.md files table pointers | d223c4b | CLAUDE.md (3 rows appended) |

## What Changed

### README.md — Operator-First Rewrite

Restructured from developer-first to operator-first. New section order:

1. What this is / Stack
2. **Prerequisites** (new: explicit Docker Compose v2 requirement, no Python/Node on host)
3. **Quickstart** (new: `git clone` → `cp .env.example .env` → `docker compose up -d` → `/healthz` → `/setup`) — DIST-05 smoke documented inline
4. **Environment variables** (existing table preserved; `TRUSTED_PROXY_IPS` row updated with NPM callout)
5. **Reverse proxy** (new: NPM primary walkthrough with Details/SSL/Advanced field tables + three gotchas; plain NGINX verbatim secondary)
6. **Single uvicorn worker — DO NOT change** (preserved verbatim — location #3 of three-place system)
7. **Upgrade** (new: three-line procedure per D-19)
8. **Restore from backup** (preserved verbatim)
9. **Troubleshooting** (existing four entries preserved; new: GHCR 403 entry per D-20)
10. Known caveats / iOS Wake Lock (preserved verbatim)
11. Project history / License

Removed from README: make-target table, "Deploying a change" dev/VPS flow, root-owned volumes one-time fix.

### CONTRIBUTING.md — New File

Dev-facing content carved from README plus new release and GHCR content:

- Make-target table (13 targets with descriptions)
- Fast Per-File Iteration with **file-level vs directory-level `docker compose cp` caveat** (memory: docker-cp-into-container-nesting)
- Both ruff steps: `ruff format --check .` and `ruff check .`
- Full test gate procedure (`coffee-snobbery-test` service)
- Conventional Commits guidance
- Deploy-to-VPS direct path + root-owned volumes one-time fix (Phase 15 context updated)
- Release ritual: `git tag v1.2.0 && git push --tags` → `release.yml` fires
- After First Release: GHCR private→public visibility flip (DIST-02)
- GHCR package maintenance
- Add-new-env-var 4-step procedure
- Pointer to CLAUDE.md for full file-role table

### CLAUDE.md — Three Table Rows

Appended to "Files worth knowing" table:
- `CONTRIBUTING.md` — dev guide pointer
- `docker-compose.override.yml.example` — dev override template pointer
- `.github/workflows/release.yml` — release CI pointer

## Validators

| Validator | Check | Result |
|-----------|-------|--------|
| V18-03 | `grep -RIn -E '\-\-workers 1\|single worker' README.md entrypoint.sh app/services/scheduler.py \| wc -l` ≥ 3 | 4 hits — PASS |
| V18-08 | All 8 required H2 headers in README | PASS |
| V18-09 | `ghcr.io/jheikkila54/coffee-snobbery` in README | PASS |
| V18-10 | `TRUSTED_PROXY_IPS=*` in README | PASS |
| V18-11 | `docker compose pull` + `docker compose up -d` in README | PASS |
| V18-12 | `Image pull fails` / `403 from ghcr.io` in README | PASS |
| V18-13 | CONTRIBUTING.md: `make smoke` + `ruff` + `docker compose cp` | PASS |
| LF endings | All three files LF-only | PASS |
| ruff format | `ruff format --check .` | 224 files already formatted — PASS |
| ruff check | `ruff check .` | All checks passed — PASS |
| DIST-05 docs | `{"status":"ok"}` and `/setup` referenced in README | PASS |
| make-target carve-out | `` `make smoke` `` count in README = 0 | PASS |

## Deviations from Plan

**1. [Rule 1 - Minor] Rephrased `make smoke` in pg_dump troubleshooting**
- **Found during:** Task 1 acceptance verification
- **Issue:** The plan's acceptance criteria requires `` grep -c '`make smoke`' README.md `` returns 0 (proving the make-target table was removed). The original pg_dump troubleshooting text contained `` `make smoke` `` in prose (not the table). This would have failed the criterion.
- **Fix:** Replaced `` `make smoke` `` prose reference with an equivalent description of the same check: `the smoke gate (docker compose down -v && docker compose up -d --build)`. The meaning is preserved; the backtick-make reference is gone.
- **Files modified:** README.md
- **Commit:** 0e132c6 (inline with Task 1)

## Known Stubs

None — all content is wired to actual infrastructure decisions, not placeholders.

## DIST-05 Status

Documented in README Quickstart (steps 4–5: `/healthz` returns `{"status":"ok"}`, fresh install lands on `/setup`). **MANUAL VERIFICATION PENDING** — V18-19 and V18-20 require a clean-volume run against the published GHCR image (`ghcr.io/jheikkila54/coffee-snobbery:v1.2.0`) which requires the first `v*` tag push + GHCR public-visibility flip.

Phase 22 (Verification & Release) owns the v1.2.0 tag push and will execute V18-19, V18-20, V18-22 as its first checkpoint.

## Carry-Forward

- **Phase 22 / Verification & Release:** First `v*` tag push exercises V18-19 (healthz ok), V18-20 (/setup reachable), V18-22 (GHCR public-visibility flip per CONTRIBUTING.md "After First Release"). The smoke procedure in README Quickstart is the canonical reference.

## Self-Check: PASSED

- [x] README.md exists and has all 8 required H2 sections
- [x] CONTRIBUTING.md exists at repo root
- [x] CLAUDE.md has 3 new rows in Files worth knowing table
- [x] Commits 0e132c6, 3eb5a93, d223c4b all exist
- [x] V18-03 through V18-13 all pass
- [x] ruff format + ruff check both exit 0
