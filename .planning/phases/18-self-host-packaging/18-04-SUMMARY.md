---
phase: 18-self-host-packaging
plan: "04"
subsystem: ci
tags: [ci, release, ghcr, multi-arch, packaging]

requires:
  - phase: 18-self-host-packaging/18-02
    provides: Dockerfile ARG APP_VERSION=dev + ENV APP_VERSION handshake

provides:
  - .github/workflows/release.yml — tag-triggered two-job workflow: test gate + multi-arch GHCR publish
  - DIST-02 unblocked: git tag v1.2.0 && git push --tags fires the full workflow

affects:
  - 18-05 (CONTRIBUTING.md will document the one-time GHCR public-visibility flip)
  - future release ops (re-tag recovery procedure documented in file header comment)

tech-stack:
  added: []
  patterns:
    - "D-09: tag-push-only trigger; no workflow_dispatch"
    - "D-10: test job gates build-push via needs: test"
    - "D-11: flavor: latest=auto skips latest/major/minor on pre-release tags"
    - "D-12: APP_VERSION=${{ github.ref_name }} build-arg flows into Dockerfile ARG"
    - "D-13: QEMU@v4 + Buildx@v4 + build-push@v7 for linux/amd64,linux/arm64"
    - "D-03: {{raw}} + {{major}}.{{minor}} + {{major}} tag matrix with v0.x guard"

key-files:
  created:
    - .github/workflows/release.yml
  modified: []

key-decisions:
  - "permissions: packages:write on build-push job only (least privilege; test job has no permissions block)"
  - "target: runtime mandatory — without it the dev stage's pytest ENTRYPOINT runs on operator up -d"
  - "actionlint not installed on host — skip noted; YAML parse confirmed clean via python yaml.safe_load"
  - "No GitHub Release auto-notes step added — actions/create-release@v1 is deprecated; gh release create deferred per CONTEXT.md discretion"
  - "No workflow_dispatch trigger — explicit D-09 deferral; re-tag is the re-run mechanism"

metrics:
  duration: 10min
  completed: 2026-05-28
  tasks: 2
  files_created: 1
  files_modified: 0
---

# Phase 18 Plan 04: Tag-Triggered Multi-Arch GHCR Release Workflow Summary

**Single `.github/workflows/release.yml` with two jobs — test gate mirrors `ci.yml` verbatim, build-push publishes `linux/amd64,linux/arm64` to `ghcr.io/jheikkila54/coffee-snobbery` with the D-03 tag matrix on every `v*` push.**

## Performance

- **Duration:** ~10 min
- **Completed:** 2026-05-28
- **Tasks:** 2
- **Files created:** 1

## Accomplishments

- Created `.github/workflows/release.yml` (~168 lines) as a two-job workflow triggered only on `push: tags: ['v*']`
- `test` job: exact mirror of `ci.yml` — Tailwind v3.4.17 binary, `ruff format --check`, `ruff check`, pytest full suite + isolation double-run with `SNOB_CI: "1"` against a postgres:16-alpine service container
- `build-push` job (gated `needs: test`): QEMU@v4 + Buildx@v4 + login@v4 + metadata@v6 + build-push@v7
- Multi-arch: `platforms: linux/amd64,linux/arm64`; `target: runtime` (mandatory — prevents dev-stage pytest ENTRYPOINT from running on operator `up -d`)
- `flavor: latest=auto` implements D-11: pre-release tags (`v1.2.0-rc1`) publish the exact tag only; `latest`/`1.2`/`1` are untouched
- D-03 tag matrix: `{{raw}}` (v1.2.0), `{{major}}.{{minor}}` (1.2), `{{major}}` (1, with v0.x guard), plus `latest` via flavor=auto
- `APP_VERSION=${{ github.ref_name }}` build-arg wired to Plan 02's `ARG APP_VERSION=dev` in the Dockerfile runtime stage
- `permissions: { contents: read, packages: write }` on `build-push` only; `test` job has no permissions block (least privilege)
- GHA cache (`type=gha, mode=max`) enabled for Tailwind builder stage + pip layer reuse across release runs

## Task Commits

1. **Task 1+2: Create release.yml + run all validators** — `bc44477` (ci)

## Validator Results

All five V18 validators passed inline before commit:

| Validator | Command | Result |
|-----------|---------|--------|
| V18-04 | structural shape (2 jobs, needs: test, permissions placement) | OK |
| V18-05 | `grep -q 'linux/amd64,linux/arm64'` | OK |
| V18-06 | `grep -A2 'permissions:' \| grep -q 'packages: write'` | OK |
| V18-07 | `grep -q 'latest=auto'` | OK |
| V18-16 | `grep -q 'APP_VERSION='` | OK |

Additional assertions:
- LF-only line endings: `b'\r\n' not in b` — OK
- ARG handshake: `grep -q 'ARG APP_VERSION' Dockerfile && grep -q 'APP_VERSION=' release.yml` — OK
- Tailwind v3.4.17 pin: OK
- Both ruff steps: OK
- Two pytest runs: count=2 — OK
- `target: runtime`: OK
- All 5 action version pins (metadata@v6, build-push@v7, qemu@v4, buildx@v4, login@v4): OK
- Tag trigger `- 'v*'`: OK
- `actionlint`: not installed on host — skipped (noted)

## Plan 02 ARG Handshake

Confirmed: `ARG APP_VERSION=dev` is present in the Dockerfile runtime stage (line 77, commit `e3b0cd2` from Plan 02). The `build-args: APP_VERSION=${{ github.ref_name }}` in `release.yml` passes the git tag (e.g., `v1.2.0`) end-to-end into the runtime ENV and the `org.opencontainers.image.version` OCI label.

## Deferrals

- **No `workflow_dispatch` trigger** — explicitly deferred per D-09; re-tag is the release re-run mechanism
- **No GitHub Release auto-notes** — `actions/create-release@v1` is deprecated; `gh release create` is the modern path but not load-bearing for DIST-02; deferred per CONTEXT.md discretion
- **No GHCR retention automation** — documented as a periodic manual task (Plan 05 CONTRIBUTING.md)
- **actionlint not installed** — YAML validated via `python yaml.safe_load` instead; no errors

## Remaining Human Step

First `v*` tag push will publish to GHCR as **private** by default. After the first push, one-time action:
visit `https://github.com/users/jheikkila54/packages/container/coffee-snobbery/settings`, set visibility = Public.
This will be documented in Plan 05's CONTRIBUTING.md.

## Deviations from Plan

None — plan executed exactly as written.

## Threat Flags

None — this plan adds no network endpoints, auth paths, file access patterns, or schema changes. The workflow file itself is a GitHub Actions YAML that writes to GHCR (package registry) using the built-in `GITHUB_TOKEN` with `packages: write` scope, which is the standard GitHub-documented pattern for GHCR publishing.

## Self-Check: PASSED

- `.github/workflows/release.yml` exists: CONFIRMED
- Commit `bc44477` exists: CONFIRMED
- All validators V18-04 through V18-07 and V18-16: PASSED
