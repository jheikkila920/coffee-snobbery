# Phase 18: Self-Host Packaging - Research

**Researched:** 2026-05-28
**Domain:** Docker multi-arch image publishing, GitHub Container Registry, GitHub Actions release CI, Docker Compose override pattern, Nginx Proxy Manager, operator documentation
**Confidence:** HIGH (GitHub Actions action versions verified against release pages; Compose behavior verified against official docs; GHCR behavior verified against GitHub docs)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Registry path, visibility, tags**
- D-01: Publish to `ghcr.io/jheikkila54/coffee-snobbery`. Matches the GitHub repo owner/name exactly.
- D-02: GHCR image visibility is public. `docker pull` works without `docker login ghcr.io`.
- D-03: Stable-release tag scheme: every stable `v*` tag publishes `v1.2.0` (exact) + `1.2` (mutable major.minor) + `1` (mutable major) + `latest` (mutable).
- D-04: Committed `docker-compose.yml` pins `image:` to the current semver (e.g. `:v1.2.0`).

**Compose split**
- D-05: Override-file pattern. Committed `docker-compose.yml` is operator-facing: `image:` only, no `build:` block on the `coffee-snobbery` service. `docker-compose.override.yml` is gitignored and holds the `build:` block. `docker-compose.override.yml.example` is committed.
- D-06: `coffee-snobbery-test` service moves to the dev override.
- D-07: Makefile stays dev-only. README operator quickstart uses raw `docker compose` only.
- D-08: Operator's first-run command is the single line `docker compose up -d`.

**Release CI trigger + scope**
- D-09: Trigger is `on: push: tags: ['v*']` — single trigger, no `workflow_dispatch` fallback.
- D-10: Release workflow re-runs the full test gate before pushing the image.
- D-11: Pre-release tag policy: any tag matching `v*-*` (e.g. `v1.2.0-rc1`) publishes under the exact tag ONLY. The mutable `latest`/`1`/`1.2` tags are NOT touched on pre-release tags.
- D-12: Version source-of-truth is the git tag. Workflow reads `${{ github.ref_name }}` and stamps it into image labels and `app/system.py` path.
- D-13: Multi-arch build approach: `docker/setup-qemu-action` + `docker/setup-buildx-action` + `docker/build-push-action` with `platforms: linux/amd64,linux/arm64`.

**Docs structure + NPM depth**
- D-14: Rewrite README to lead with self-host. Dev content moves to `CONTRIBUTING.md`.
- D-15: NPM walkthrough = field-list + key gotchas, no screenshots.
- D-16: Plain-nginx server-block snippet stays as a secondary section below NPM.
- D-17: `.env.example` is audited for DIST-06 in this phase.
- D-18: DIST-05 fresh-install path is verify-only.
- D-19: Upgrade walkthrough = three lines, explicit-tag-bump pattern.
- D-20: Troubleshooting carries forward + adds "Image pull fails / 403 from ghcr.io" entry.

### Claude's Discretion
- Release workflow file layout: single `release.yml`, two sequential jobs with `needs:`.
- `docker/metadata-action` `tags:` config exact patterns.
- Whether the release workflow also generates a GitHub Release with auto-generated notes.
- `tailwind-builder` stage caching between releases.
- `docker-compose.override.yml.example` exact contents.
- CONTRIBUTING.md final structure.
- Whether to update CLAUDE.md to reference the new operator/dev split.
- GHCR retention policy mention.
- OCI image label values (`title`, `description`, `url`, `source`, `version`, `revision`, `licenses`).

### Deferred Ideas (OUT OF SCOPE)
- Image signing / SBOM / cosign / syft
- CHANGELOG.md / formal release-notes process
- Caddy / Traefik / docker swarm / k8s walkthroughs
- Deploy automation scripts (`upgrade.sh`, `deploy.sh`)
- `workflow_dispatch` manual-rebuild fallback
- Re-running release via GitHub Release publication trigger
- GHCR retention automation
- Removing `/admin` link from top-nav
- VPS-side automation (Ansible / systemd-unit)
- GHCR Docker Hub mirror
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DIST-01 | Operator can deploy with no `docker compose build` step | Compose override pattern (Section 4); operator-facing `docker-compose.yml` with `image:` only |
| DIST-02 | Versioned multi-arch (amd64+arm64) image published to GHCR by release CI on version tag | Release CI architecture (Section 3); metadata-action tag matrix (Section 3) |
| DIST-03 | README gives complete from-zero self-host walkthrough | README rewrite outline (Section 6); env var audit (Section 9) |
| DIST-04 | Deploy doc includes step-by-step NPM setup | NPM walkthrough (Section 7) |
| DIST-05 | Fresh install boots cleanly: migrations auto-run, operator lands on /setup | Verify-only smoke procedure (Section 10); Phase 15 entrypoint already handles this |
| DIST-06 | `.env.example` documents every required env var with generation hints | `.env.example` audit checklist (Section 9) |
</phase_requirements>

---

## Domain Overview

Phase 18 converts Snobbery from a "git clone + build" project into a first-class self-hostable app. The work has three equal parts: (1) a GitHub Actions release pipeline that builds and publishes a multi-arch OCI image to GHCR on a version tag push, (2) a Compose split that removes build-time complexity from the operator experience, and (3) operator-facing documentation that gets a new household operator from zero to running in one sitting.

The app itself is unchanged. No router, model, template, or service code is modified (except a surgical version-stamp in `app/routers/admin/system.py` — currently `pkg_version("coffee-snobbery")` which reads `pyproject.toml` version `"0.1.0"` on the source tree and `importlib.metadata` in the baked image).

The Dockerfile already has full multi-arch wiring (`ARG TARGETARCH`, arch switch in the tailwind-builder stage). The entrypoint already handles fresh-install boot. The primary new artifacts are: `release.yml`, `docker-compose.override.yml.example`, `CONTRIBUTING.md`, and the rewritten `README.md`.

**Primary recommendation:** Implement the release workflow as two sequential jobs in a single `release.yml` file. Use `docker/metadata-action@v6` with `flavor: latest=auto` — this is the idiomatic 2026 pattern; `latest=auto` already withholds `latest` from semver pre-release tags, which satisfies D-11 without a conditional.

---

## Phase Boundary Statement

**In scope (packaging + docs only):**
- `.github/workflows/release.yml` (new)
- `docker-compose.yml` (modify: replace `build:` block with `image: ghcr.io/...`, remove `coffee-snobbery-test` service)
- `.gitignore` (add `docker-compose.override.yml`)
- `docker-compose.override.yml.example` (new)
- `README.md` (full restructure to operator-first)
- `CONTRIBUTING.md` (new — dev content carved from README)
- `.env.example` (prose polish only; no new vars)
- `CLAUDE.md` (optional one-line pointer to the split)
- `Dockerfile` (add OCI labels + `ARG APP_VERSION` for version stamp)
- `pyproject.toml` (bump version from `"0.1.0"` to `"1.2.0"` — the version displayed in admin/system; see Section 5)

**NOT in scope:**
- `app/routers/`, `app/templates/`, `app/models/`, `app/services/` (except reading version from env/label in admin/system — see Section 5)
- `app/services/scheduler.py`, `app/services/encryption.py`, `app/services/ai_service.py`, `app/services/search.py` — untouched
- `entrypoint.sh` — do NOT modify (Phase 15 D-01..D-04)
- `app/routers/auth.py` — /setup route already works; DIST-05 is verify-only
- Any feature routes, cafe logs, AI surfaces, brew sessions, guided brew

**Verify-only (DIST-05):** The fresh-install boot path (`entrypoint.sh` → `alembic upgrade head` → `/setup` redirect for unauthenticated user with zero users) is already shipped and tested. Phase 18 asserts it works with the published image via a local smoke procedure.

---

## Release CI Architecture

### Action Versions (verified against GitHub release pages, 2026-05-28)

| Action | Verified Version | Notes |
|--------|-----------------|-------|
| `docker/metadata-action` | `v6` (v6.1.0, May 22 2026) | [VERIFIED: github.com/docker/metadata-action/releases] |
| `docker/build-push-action` | `v7` (v7.2.0, May 21 2025; v7 GA March 2025) | [VERIFIED: github.com/docker/build-push-action/releases] |
| `docker/setup-qemu-action` | `v4` | [CITED: docs.docker.com/build/ci/github-actions/multi-platform/] |
| `docker/setup-buildx-action` | `v4` | [CITED: docs.docker.com/build/ci/github-actions/multi-platform/] |
| `docker/login-action` | `v4` (v4.2.0, May 22 2026) | [VERIFIED: github.com/docker/login-action/releases] |
| `actions/checkout` | `v4` | [ASSUMED: standard; widely current] |
| `actions/setup-python` | `v5` | [CITED: existing ci.yml] |

### Job-Chain Design

Two jobs in a single `release.yml`:

```
test job  →  build-push job (needs: test)
```

The `test` job is a verbatim copy of the CI test gate. The `build-push` job only runs if `test` passes. This eliminates the "tagged a flaky commit and shipped it" failure mode (D-10).

### Metadata-Action Tag Matrix (D-03 + D-11)

**Key behavior of `flavor: latest=auto` (verified from docker/metadata-action README):**
- For a stable tag like `v1.2.0` (no pre-release suffix): generates `v1.2.0`, `1.2`, `1`, AND implicitly adds `latest`.
- For a pre-release tag like `v1.2.0-rc1` (has pre-release suffix per semver): generates `1.2.0-rc1` ONLY. `latest`, `1.2`, `1` are NOT generated.

This is the idiomatic way to implement D-11. No conditional expression needed.

**Note on `v` prefix stripping:** By default, `type=semver,pattern={{version}}` strips the leading `v` from the git tag (produces `1.2.0`, not `v1.2.0`). D-03 requires the exact-tag form `v1.2.0` in addition to `1.2` and `1`. Use `type=semver,pattern={{raw}}` for the exact verbatim tag, and `type=semver,pattern={{version}}` for the stripped form only if needed for Docker Hub conventions. Since D-04 pins `image: ghcr.io/.../coffee-snobbery:v1.2.0`, the `v`-prefixed form must be one of the published tags.

**Recommended tags block:**

```yaml
tags: |
  # Exact verbatim git tag (v1.2.0 or v1.2.0-rc1)
  type=semver,pattern={{raw}}
  # Mutable major.minor (1.2) — only on stable releases (auto-skipped on pre-release)
  type=semver,pattern={{major}}.{{minor}}
  # Mutable major (1) — disabled on v0.x to avoid false "stable" signal
  type=semver,pattern={{major}},enable=${{ !startsWith(github.ref, 'refs/tags/v0.') }}
flavor: |
  latest=auto
```

With `flavor: latest=auto`:
- Stable `v1.2.0` → tags: `ghcr.io/.../coffee-snobbery:v1.2.0`, `:1.2`, `:1`, `:latest`
- Pre-release `v1.2.0-rc1` → tags: `ghcr.io/.../coffee-snobbery:v1.2.0-rc1` (only)

[VERIFIED: github.com/docker/metadata-action README — "Pre-release (rc, beta, alpha) will only extend `{{version}}` (or `{{raw}}`) as tag"]

### OCI Labels (auto-generated + custom)

`docker/metadata-action@v6` automatically generates from repo context:

```json
{
  "org.opencontainers.image.title": "<from repo name>",
  "org.opencontainers.image.description": "<from repo description>",
  "org.opencontainers.image.url": "https://github.com/jheikkila54/coffee-snobbery",
  "org.opencontainers.image.source": "https://github.com/jheikkila54/coffee-snobbery",
  "org.opencontainers.image.version": "<from git tag>",
  "org.opencontainers.image.created": "<build timestamp ISO 8601>",
  "org.opencontainers.image.revision": "<full git SHA>",
  "org.opencontainers.image.licenses": "<from repo license field>"
}
```

To override or add custom values, use the `labels:` input:

```yaml
- name: Docker meta
  id: meta
  uses: docker/metadata-action@v6
  with:
    images: ghcr.io/jheikkila54/coffee-snobbery
    labels: |
      org.opencontainers.image.title=Snobbery
      org.opencontainers.image.description=Self-hosted household coffee log for pour-over enthusiasts
      org.opencontainers.image.licenses=Proprietary
```

The `${{ steps.meta.outputs.labels }}` output is passed to `build-push-action`'s `labels:` input.

### GHA Cache Configuration

The GitHub Actions cache backend (`type=gha`) requires Buildx >= v0.21.0 and the Cache API v2 (enforced as of April 2025). The ubuntu-latest runner ships with compliant versions.

```yaml
cache-from: type=gha
cache-to: type=gha,mode=max
```

`mode=max` saves all intermediate layers, not just the final image — critical for caching the Tailwind builder stage and the pip install layer separately from the COPY app step.

**10 GB limit per repo.** For a household-scale app this is ample. The Tailwind builder stage and pip layer are the expensive layers; they are content-addressed and reused across runs unless `TAILWIND_VERSION` or `requirements.txt` changes.

[VERIFIED: docs.docker.com/build/ci/github-actions/cache/]

### Complete `release.yml` Skeleton

```yaml
name: Release

on:
  push:
    tags:
      - 'v*'

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: snobbery
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-timeout 3s
          --health-retries 10
        ports:
          - 5432:5432

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install deps
        run: pip install -r requirements-dev.txt

      - name: Build Tailwind CSS
        run: |
          set -euo pipefail
          curl -fsSL \
            "https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.17/tailwindcss-linux-x64" \
            -o /usr/local/bin/tailwindcss
          chmod +x /usr/local/bin/tailwindcss
          HASH="$(sha256sum app/static/css/tailwind.src.css | cut -c1-8)"
          tailwindcss \
            -i app/static/css/tailwind.src.css \
            -o "app/static/css/tailwind.${HASH}.css" \
            --minify

      - name: Ruff format check
        run: ruff format --check .

      - name: Ruff lint
        run: ruff check .

      - name: Pytest full suite
        env:
          DATABASE_URL: postgresql+psycopg://test:test@localhost:5432/snobbery
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: snobbery
          APP_SECRET_KEY: ${{ secrets.APP_SECRET_KEY || 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' }}
          APP_ENCRYPTION_KEY: ${{ secrets.APP_ENCRYPTION_KEY || '0123456789abcdef0123456789abcdef0123456789a=' }}
          SNOB_CI: "1"
        run: python -m pytest tests/ -rs --tb=short --ignore=tests/e2e

      - name: Pytest isolation double-run
        env:
          DATABASE_URL: postgresql+psycopg://test:test@localhost:5432/snobbery
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: snobbery
          APP_SECRET_KEY: ${{ secrets.APP_SECRET_KEY || 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' }}
          APP_ENCRYPTION_KEY: ${{ secrets.APP_ENCRYPTION_KEY || '0123456789abcdef0123456789abcdef0123456789a=' }}
          SNOB_CI: "1"
        run: python -m pytest tests/ -rs --tb=short --ignore=tests/e2e

  build-push:
    needs: test
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4

      - name: Set up QEMU
        uses: docker/setup-qemu-action@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v4

      - name: Log in to GHCR
        uses: docker/login-action@v4
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Docker metadata
        id: meta
        uses: docker/metadata-action@v6
        with:
          images: ghcr.io/jheikkila54/coffee-snobbery
          tags: |
            type=semver,pattern={{raw}}
            type=semver,pattern={{major}}.{{minor}}
            type=semver,pattern={{major}},enable=${{ !startsWith(github.ref, 'refs/tags/v0.') }}
          flavor: |
            latest=auto
          labels: |
            org.opencontainers.image.title=Snobbery
            org.opencontainers.image.description=Self-hosted household coffee log for pour-over enthusiasts
            org.opencontainers.image.licenses=Proprietary

      - name: Build and push
        uses: docker/build-push-action@v7
        with:
          context: .
          target: runtime
          platforms: linux/amd64,linux/arm64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          build-args: |
            APP_VERSION=${{ github.ref_name }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

**Notes for the planner:**
- `permissions:` block belongs on the `build-push` job, NOT on the `test` job. The `test` job does not write to packages.
- The `test` job does NOT need `permissions:` (defaults are fine for a checkout + test run).
- `target: runtime` is required — same reason as the current `docker-compose.yml`: without it, the last Dockerfile stage (`dev`) is built, whose ENTRYPOINT is pytest.
- `build-args: APP_VERSION=${{ github.ref_name }}` passes e.g. `v1.2.0` into the Dockerfile (see Section 5).

### Tag-Retag Edge Case (D-09 deferred)

The deferred "re-tag if release fails" flow: `git tag -d v1.2.0 && git push origin :refs/tags/v1.2.0 && git tag v1.2.0 && git push --tags`. Force-retag (`git push --tags -f`) works but requires the remote to allow force-push on tags.

**Mid-run failure behavior:** If the `build-push` job fails after partial pushes (e.g., amd64 manifest pushed but arm64 failed), GHCR does not auto-clean the partial state. Re-running the workflow by force-retagging will overwrite the partial state — GHCR overwrites matching tags on push. This is safe; there is no deduplication risk for a household-scale image.

[MEDIUM confidence — based on training knowledge of GHCR's tag-overwrite behavior; the core behavior is standard OCI registry behavior]

---

## Compose Split Pattern

### How Docker Compose v2 Override Merging Works

Compose v2 automatically reads `docker-compose.yml` and (if present) `docker-compose.override.yml` — no flags needed. The override file is merged into the base file according to these rules:

- **Scalar fields** (`image`, `command`, `mem_limit`): override value replaces base value.
- **List fields** (`volumes`, `ports`, `environment`): values are concatenated (append, not replace).
- **Map fields** (`build`): override value replaces base value.

**Critical interaction for D-05:** The operator-facing `docker-compose.yml` will have `image: ghcr.io/...` and NO `build:` block on `coffee-snobbery`. The `docker-compose.override.yml` will ADD a `build:` block. Compose will merge these, producing a service that has BOTH `image:` and `build:`. 

When both `image:` and `build:` are present, Compose follows `pull_policy` (default: `missing`): it tries to pull the image from the registry first; if not found, it builds from source. For the dev loop (where the local override adds `build:`), this is the correct behavior — the dev loop builds locally. For the operator (no override file), only `image:` is present and no build step runs.

[CITED: docs.docker.com/compose/how-tos/multiple-compose-files/merge/]

### Operator-Facing `docker-compose.yml` (after D-05)

The `coffee-snobbery` service loses its `build:` block and gains `image: ghcr.io/jheikkila54/coffee-snobbery:v1.2.0`. The `coffee-snobbery-test` service is removed entirely.

The port binding for the NPM topology (D-15): operators behind NPM do NOT use `127.0.0.1:8080:8000` — NPM routes by container name on a shared Docker network. The current port binding `127.0.0.1:8080:8000` is for the plain-nginx topology (host nginx → localhost:8080). For NPM, the port mapping can be removed or changed to the container network approach. See Section 7.

**Planner decision needed:** Whether to keep the `127.0.0.1:8080:8000` binding in the operator-facing Compose (so it works for both plain-nginx and NPM) or remove it (cleaner for NPM operators). The plain-nginx path (D-16) requires the localhost bind. Recommended: keep it — operators who use NPM on the same Docker network bypass the host port entirely, and the localhost bind is harmless.

### Committed `docker-compose.override.yml.example`

```yaml
# docker-compose.override.yml.example
#
# Copy this file to docker-compose.override.yml (gitignored) for the dev loop.
# Compose auto-merges override.yml — no flags needed.

services:
  coffee-snobbery:
    build:
      context: .
      dockerfile: Dockerfile
      target: runtime

  coffee-snobbery-test:
    build:
      context: .
      dockerfile: Dockerfile
      target: dev
    profiles: [test]
    depends_on:
      coffee-snobbery-db:
        condition: service_healthy
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@coffee-snobbery-db:5432/${POSTGRES_DB}
      SNOB_CI: "1"
    networks:
      - coffee-snobbery-net
```

### `.gitignore` Addition

```
docker-compose.override.yml
```

`.dockerignore` should also exclude `docker-compose.override.yml` so the file never leaks into a baked image even if present on disk. The existing `.dockerignore` likely covers it (it excludes `.planning/`, `.claude/`, etc.) — the planner should verify and add the entry if absent.

---

## Image Version Stamp Flow

### Current Version Path (verified by reading `app/routers/admin/system.py`)

The version is read at `admin_system()` handler via:

```python
from importlib.metadata import version as pkg_version, PackageNotFoundError

try:
    app_version = pkg_version("coffee-snobbery")
except PackageNotFoundError:
    # Fallback: read pyproject.toml directly
    _pyproject = Path(__file__).resolve().parents[3] / "pyproject.toml"
    if _pyproject.exists():
        app_version = tomllib.load(_f).get("project", {}).get("version", "unknown")
    else:
        app_version = "unknown"
```

**In the baked image:** `pip install .` or `pip install -e .` installs the package, making `importlib.metadata.version("coffee-snobbery")` work. The current `pyproject.toml` `version = "0.1.0"` is what shows up. This will be wrong after the real release tags start at `v1.2.0`.

**On CI source tree (without pip install):** The `PackageNotFoundError` path fires and reads `pyproject.toml`, returning `"0.1.0"`.

**Project memory `ci-source-tree-vs-baked-image-divergence`:** This divergence is known and acceptable for tests. The issue only matters for the in-app version display.

### D-12: Tag-Stamp Approach

The plan should add a Dockerfile `ARG APP_VERSION` that defaults to `"dev"` and is passed as `${{ github.ref_name }}` in the release workflow. The runtime image sets an ENV from it so `app/routers/admin/system.py` can read it from the environment.

**Recommended approach for the planner:**

**Option A (ENV in Dockerfile — no code change to admin/system.py required):**

```dockerfile
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}
```

Then `app/routers/admin/system.py` adds an env-var fallback BEFORE the `importlib.metadata` call:

```python
import os
app_version = os.environ.get("APP_VERSION") or _read_from_metadata_or_pyproject()
```

This requires a small, surgical change to `app/routers/admin/system.py`.

**Option B (OCI label only — no in-app display change):**
Stamp `org.opencontainers.image.version` via metadata-action (done automatically). The admin panel still shows the `pyproject.toml` version. To fix the display, `pyproject.toml` version must be bumped to match the tag.

**Recommended:** Option A + bump `pyproject.toml` version to `"1.2.0"`. This gives correct in-app display for baked images AND the CI fallback reads the correct `pyproject.toml` version. The `APP_VERSION` env var is the authoritative runtime source for baked images; `pyproject.toml` is the fallback for dev/CI.

**pyproject.toml version should be bumped from `"0.1.0"` to `"1.2.0"` in this phase.** The CONTEXT.md says "git tag IS the version" (D-12), and `pyproject.toml` should reflect the milestone. This is a one-line edit, not a stack change.

**Dockerfile additions:**

```dockerfile
ARG APP_VERSION=dev

# ... (existing FROM runtime AS runtime line stays) ...
# After the existing ENV block:
ENV APP_VERSION=${APP_VERSION}

# OCI labels — add before EXPOSE:
LABEL org.opencontainers.image.title="Snobbery" \
      org.opencontainers.image.description="Self-hosted household coffee log for pour-over enthusiasts" \
      org.opencontainers.image.url="https://github.com/jheikkila54/coffee-snobbery" \
      org.opencontainers.image.source="https://github.com/jheikkila54/coffee-snobbery" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.licenses="Proprietary"
```

Note: `org.opencontainers.image.created`, `org.opencontainers.image.revision` are set dynamically by `docker/metadata-action` via `--label` flags at build time — they override the Dockerfile `LABEL` values. The static `LABEL` in the Dockerfile provides fallback values for local builds outside CI.

[CITED: github.com/docker/metadata-action — labels output description]

---

## README Operator-First Rewrite

### New Section Order (D-14)

```
# Snobbery
[tagline]

## What is this
[2-3 sentences, self-host framing]

## Prerequisites
[Docker + Docker Compose v2; no Python/Node on host]

## Quickstart
[1. git clone or download docker-compose.yml + .env.example]
[2. cp .env.example .env, fill in 4 secrets with generation hints]
[3. docker compose up -d]
[4. visit https://<your-domain> — land on /setup to create first admin]

## Environment variables
[table: all 11 vars, purpose + generation hint]

## Reverse proxy
### Nginx Proxy Manager (recommended)
[field-list walkthrough — see Section 7]
### Plain NGINX
[existing server-block snippet, verbatim — D-16]

## Single uvicorn worker — DO NOT change
[existing warning block, preserved verbatim — 3-place warning system location #3]

## Upgrade
[three-line procedure — D-19]

## Restore from backup
[existing backup restore block]

## Troubleshooting
[existing block + new GHCR pull fails entry — D-20]

## License
```

### Content Carve-out to CONTRIBUTING.md

Move to CONTRIBUTING.md:
- "Working with the code" table (all `make` targets)
- "Deploying a change" section (git pull + build + up -d — dev flow)
- Local rebuild loop
- `docker compose cp` fast-iteration trick
- Test suite invocations (pytest, make smoke, make test)
- ruff/mypy invocations

**README retains:**
- All operator-facing content above
- The NGINX server-block snippet (D-16) — operators using plain NGINX need it
- The single-worker warning block — it must stay in README per the three-place system (audit grep covers README.md)
- The `/debug/proxy` smoke check (operator operational tool)

---

## NPM Walkthrough Reference

### Current NPM UI Fields (verified from nginxproxymanager.com, current version via Docker `jc21/nginx-proxy-manager:latest`)

**Details Tab:**

| Field | Value | Notes |
|-------|-------|-------|
| Domain Names | `snobbery.example.com` | Operator's FQDN; must have DNS A record pointing to the VPS |
| Scheme | `http` | Snobbery listens on plain HTTP inside Docker; NPM terminates TLS |
| Forward Hostname / IP | `coffee-snobbery` | Container name on the shared Docker network |
| Forward Port | `8000` | The in-container uvicorn port (NOT 8080) |
| Cache Assets | Off | Snobbery sets its own cache headers; leave NPM caching off |
| Block Common Exploits | On | Recommended; blocks common web attack patterns |
| Websockets Support | Off | Not needed for v1.2 (SSE planned for AIX-07 in Phase 19) |

**SSL Tab:**

| Field | Value |
|-------|-------|
| SSL Certificate | Let's Encrypt — Request new certificate |
| Force SSL | On |
| HTTP/2 Support | On |
| HSTS Enabled | On |
| HSTS Subdomains | Off (unless operator controls subdomains) |

**Advanced Tab — Custom Nginx Configuration:**

The Advanced tab text area is injected inside the nginx `server {}` block for this proxy host. Location blocks ARE supported — this is confirmed by the Authelia integration guide which pastes full `location { }` blocks into this field.

Paste the following for the `/sw.js` Cache-Control passthrough (PWA-7 invariant):

```nginx
location = /sw.js {
    proxy_pass http://$server:$port;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    add_header Service-Worker-Allowed "/" always;
    # Do NOT add Cache-Control here. The app already sends
    # Cache-Control: no-cache on /sw.js (PWA-7 invariant).
    # Overriding it would cause deployed service workers to be cached
    # by the browser and prevent users from receiving SW updates on deploy.
}
```

**Note on NPM variable syntax:** NPM uses `$server` and `$port` as nginx variables that are set by NPM to the forwarded host and port. Do NOT hardcode `coffee-snobbery:8000` in the `proxy_pass` URL — NPM may not resolve container names correctly in `proxy_pass` directives written by hand inside the Advanced tab. The `$server` and `$port` variables are safer (they use NPM's resolved upstream). Alternatively, if NPM's `$server`/`$port` are not set in the Advanced tab context, use `http://coffee-snobbery:8000` directly — this is what NPM-generated configs do. The planner should use the direct form as the safer option:

```nginx
location = /sw.js {
    proxy_pass http://coffee-snobbery:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    add_header Service-Worker-Allowed "/" always;
}
```

[MEDIUM confidence on `proxy_pass` variable choice — NPM's internal variable names in the Advanced tab context are not officially documented; direct container:port is the safest form]

### Load-Bearing Gotchas (D-15)

1. **Shared Docker network** — The NPM container and the `coffee-snobbery` container must be on the same Docker network. The `coffee-snobbery-net` bridge network must be set to `external: true` in the Snobbery Compose file (or NPM must join it). Without this, `coffee-snobbery` is not resolvable from NPM. The README must include the `docker network connect` or external network step.

   **Planner note:** Current `docker-compose.yml` defines `coffee-snobbery-net` as a local bridge. For NPM to reach it, either: (a) NPM joins the `coffee-snobbery-net` network via NPM's own compose file, or (b) Snobbery's compose is edited to mark the network `external: true` and the operator creates it manually. Option (a) is cleaner for NPM users. The README must explain this.

2. **`TRUSTED_PROXY_IPS=*`** — When NPM is the proxy, it proxies from a Docker network IP (not 127.0.0.1). The exact IP depends on the network configuration and may change. Setting `TRUSTED_PROXY_IPS=*` tells uvicorn to trust X-Forwarded-* headers from any upstream, which is safe when the container is not directly internet-accessible. This is non-negotiable per project memory `snobbery-vps-npm-reverse-proxy`.

3. **Port mapping in the operator Compose** — With NPM, Snobbery does NOT need to expose port 8080 on the host at all. The NPM container reaches `coffee-snobbery:8000` directly on the Docker network. The `ports:` block can be removed from the operator-facing Compose entirely for a cleaner security posture. However, removing it breaks the plain-nginx path (D-16). **Planner decision:** Keep the port binding and document that NPM users can optionally comment it out.

4. **X-Forwarded-Proto requirement** — NPM does send `X-Forwarded-Proto: https` when SSL is active. Combined with `TRUSTED_PROXY_IPS=*`, uvicorn rewrites `request.url.scheme` to `https`, which makes `Secure` session cookies work.

### GHCR Pull Fails / 403 Troubleshooting Entry (D-20)

```
**Image pull fails / 403 from ghcr.io.**
Snobbery images are public — `docker pull ghcr.io/jheikkila54/coffee-snobbery:v1.2.0`
should work without authentication. If you see a 403:
1. Verify the image is public: visit https://github.com/jheikkila54/coffee-snobbery/pkgs/container/coffee-snobbery
2. If the image was just published, wait 1–2 minutes for GHCR's CDN to propagate.
3. If you have stale credentials in Docker's credential store:
   docker logout ghcr.io && docker pull ghcr.io/jheikkila54/coffee-snobbery:v1.2.0
```

---

## CONTRIBUTING.md Outline

```markdown
# Contributing to Snobbery

## Development Prerequisites

- Docker + Docker Compose v2
- Git
- `cp docker-compose.override.yml.example docker-compose.override.yml`
  (enables the dev `build:` block; gitignored)

## Local Dev Loop

| Command | What it does |
|---------|-------------|
| `make up` | docker compose up -d |
| `make build` | Rebuild the web image |
| `make logs` | Tail web container logs |
| `make smoke` | Cold-start end-to-end check (down -v, build, up, /healthz) |
| `make test` | Run pytest inside the web container |
| `make shell` | bash shell inside the web container |
| `make fmt` | ruff format . |
| `make lint` | ruff check . |

## Fast Per-File Iteration (no full rebuild)

```bash
docker compose cp tests/ coffee-snobbery:/app/tests/
docker compose exec coffee-snobbery python -m pytest tests/test_foo.py -x
```

Source changes (Python, templates, static) require a rebuild before they take
effect in the container — there is no bind-mount.

## Linting and Formatting

CI gates on both. Run before pushing:

```bash
ruff format --check .
ruff check .
```

Or fix in place:

```bash
ruff format .
ruff check --fix .
```

## Running the Test Suite

```bash
make test
# or directly:
docker compose exec coffee-snobbery python -m pytest tests/ -rs --tb=short --ignore=tests/e2e
```

For the full gate (includes isolation double-run, matches CI):
```bash
docker compose run --rm coffee-snobbery-test
```
(Requires `docker-compose.override.yml` with the `coffee-snobbery-test` service.)

## Committing

Use [Conventional Commits](https://www.conventionalcommits.org/):
- `feat:`, `fix:`, `chore:`, `refactor:`, `docs:`, `style:`
- Short, imperative, present tense: "add backup retention config"

## Deploying a Change (dev machine → VPS)

```bash
# On the VPS, from repo root
git pull
docker compose build coffee-snobbery
docker compose up -d coffee-snobbery
docker compose logs -f coffee-snobbery   # confirm healthy startup + migrations
```

## Releasing

```bash
git tag v1.2.0
git push --tags
```

The release workflow runs automatically: tests → multi-arch build → push to GHCR.
After the first release, make the image public in GHCR settings (one-time, see below).

## GHCR Package Maintenance

Untagged images accumulate over time. Clean up periodically via:
GitHub → Profile → Packages → coffee-snobbery → Manage versions → delete untagged
```

---

## `.env.example` Audit Checklist

### Current Inventory (verified against `app/config.py` Settings class)

| `.env.example` var | `Settings` field | Match | Generation hint present |
|-------------------|-----------------|-------|------------------------|
| `POSTGRES_USER` | `POSTGRES_USER: str` | Yes | No (user-chosen, default "snobbery") |
| `POSTGRES_PASSWORD` | `POSTGRES_PASSWORD: str` | Yes | Yes (`openssl rand -hex 32`) |
| `POSTGRES_DB` | `POSTGRES_DB: str` | Yes | No (user-chosen, default "snobbery") |
| `DATABASE_URL` | `DATABASE_URL: str` | Yes | Yes (composed from above) |
| `APP_SECRET_KEY` | `APP_SECRET_KEY: str` (min_length=32) | Yes | Yes (`secrets.token_urlsafe(64)`) |
| `APP_ENCRYPTION_KEY` | `APP_ENCRYPTION_KEY: str` | Yes | Yes (`Fernet.generate_key()`) |
| `TRUSTED_PROXY_IPS` | `TRUSTED_PROXY_IPS: str` (default `"127.0.0.1"`) | Yes | Yes (explanation present) |
| `APP_TIMEZONE` | `APP_TIMEZONE: str` (default `"America/Chicago"`) | Yes | No (IANA name note) |
| `BACKUP_RETENTION_DAYS` | `BACKUP_RETENTION_DAYS: int` (default `14`) | Yes | No (integer note) |
| `LOG_LEVEL` | `LOG_LEVEL: Literal[...]` (default `"INFO"`) | Yes | Yes (enum values) |
| `LOG_FORMAT` | `LOG_FORMAT: Literal[...]` (default `"json"`) | Yes | Yes (json|console) |

**Result:** All 11 fields match. `test_env_example.py` would pass today with the current file.

**D-17 prose-polish checklist:**
- `POSTGRES_USER` and `POSTGRES_DB`: add a note "default: snobbery" inline.
- `APP_SECRET_KEY`: verify the generation hint is prominent (it is — line 19).
- `APP_ENCRYPTION_KEY`: verify the note about comma-separated list for key rotation is present (it is — line 24).
- `TRUSTED_PROXY_IPS`: update prose to note "set to * when using Nginx Proxy Manager" (currently says `127.0.0.1` is for the recommended NGINX-on-same-VPS shape, which is now the secondary path).
- `APP_VERSION` if added per Section 5: this env var must NOT be added to `Settings` (it is not a pydantic-settings field) and must NOT appear in `.env.example`. It is a Dockerfile `ENV` / `ARG`, not a runtime secret. The parity test only checks `Settings` fields.

**DIST-06 parity invariant:** `tests/test_env_example.py` enforces strict equality between `.env.example` keys and `Settings.model_fields`. Adding `APP_VERSION` to `.env.example` would FAIL the parity test. Do not add it.

---

## DIST-05 Fresh-Install Smoke Procedure

This is verify-only (D-18). The procedure confirms the published image boots correctly; it does not require code changes.

### Procedure

```bash
# 1. Ensure no existing volumes (simulate fresh install)
docker compose down -v

# 2. Edit docker-compose.yml: ensure it references the published image
#    image: ghcr.io/jheikkila54/coffee-snobbery:v1.2.0
#    (no build: block on coffee-snobbery service)

# 3. Pull the published image explicitly
docker compose pull

# 4. Start the stack
docker compose up -d

# 5. Tail logs until startup is complete (~20 seconds)
docker compose logs -f coffee-snobbery
# Expect to see:
#   INFO  alembic.runtime.migration - Running upgrade ... -> ..., ...
#   INFO  uvicorn.main - Application startup complete.

# 6. Healthcheck
curl -fsS http://127.0.0.1:8080/healthz
# Expect: {"status":"ok"}

# 7. Unauthenticated root redirect
curl -s -o /dev/null -w "%{http_code} %{redirect_url}" http://127.0.0.1:8080/
# Expect: 302 or 303 redirect to /login or /setup
# With zero users, /login redirects to /setup

# 8. Hit /setup directly
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/setup
# Expect: 200 (the setup page renders when zero users exist)
```

### Expected Log Sequence

```
coffee-snobbery  | [entrypoint] chown /app/data → app:app (if needed)
coffee-snobbery  | INFO  [alembic.runtime.migration] Running upgrade  -> 0001_initial, p1_sessions_table, ...
coffee-snobbery  | INFO  [uvicorn.main] Started server process [1]
coffee-snobbery  | INFO  [uvicorn.main] Application startup complete.
```

(Alembic log lines appear before uvicorn because `entrypoint.sh` runs `alembic upgrade head` before `exec gosu app uvicorn ...`.)

---

## GHCR Public Visibility Flow

### First-Push Behavior

When the release workflow first pushes `ghcr.io/jheikkila54/coffee-snobbery` to GHCR, the package is created as **private** by default. This is a one-time state; subsequent pushes to the same package do not change visibility.

[VERIFIED: docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry]

### Steps to Make Public (one-time, after first release tag)

1. Go to `https://github.com/jheikkila54?tab=packages` (Profile → Packages tab)
2. Click `coffee-snobbery`
3. Click "Package settings" (right sidebar)
4. Scroll to "Danger Zone" → "Change visibility" → select "Public" → confirm
5. Verify: `docker pull ghcr.io/jheikkila54/coffee-snobbery:v1.2.0` (no docker login)

**One-way operation:** Making a package public cannot be reversed. [VERIFIED: GitHub docs]

**Repository linking:** GHCR packages are automatically linked to the source repo if the image is built from the same repo's Actions workflow using `GITHUB_TOKEN`. This enables the "Source repository" link on the package page.

### Document in CONTRIBUTING.md

Add a "After first release" section explaining the one-time public-visibility step. This is a human action that cannot be automated in the workflow (GITHUB_TOKEN cannot change package visibility).

---

## Validation Architecture

The `workflow.nyquist_validation` key is absent from `.planning/config.json` (not found in the repo). Treat as enabled.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.x (installed in running container via `requirements-dev.txt`) |
| Config file | `pyproject.toml` → `[tool.pytest.ini_options]` |
| Quick run command | `docker compose exec coffee-snobbery python -m pytest tests/test_env_example.py -x` |
| Full suite command | `docker compose run --rm coffee-snobbery-test` |

### Validator Table (planner lifts into VALIDATION.md)

| Validator ID | What it checks | Type | Automated Command | Notes |
|-------------|----------------|------|-------------------|-------|
| V18-01 | Compose syntax + image pin | shell | `docker compose -f docker-compose.yml config \| grep 'image: ghcr.io/jheikkila54/coffee-snobbery'` | Also assert no `build:` block for `coffee-snobbery` service |
| V18-02 | `.env.example` parity test | pytest | `docker compose exec coffee-snobbery python -m pytest tests/test_env_example.py -x` | Existing test; must remain green |
| V18-03 | Single-worker three-place invariant | shell | `grep -RIn -E '--workers 1\|single worker' README.md entrypoint.sh app/services/scheduler.py \| wc -l` | Assert output >= 3 |
| V18-04 | Release workflow shape | shell/python | `python -c "import yaml; w=yaml.safe_load(open('.github/workflows/release.yml')); jobs=w['jobs']; assert 'test' in jobs; assert 'build-push' in jobs; assert 'test' in jobs['build-push'].get('needs', []); print('OK')"` | Also grep for `platforms:`, `docker/metadata-action`, `permissions` |
| V18-05 | Release workflow platforms string | shell | `grep 'linux/amd64,linux/arm64' .github/workflows/release.yml` | Assert exits 0 |
| V18-06 | Release workflow permissions block | shell | `grep -A2 'permissions:' .github/workflows/release.yml \| grep 'packages: write'` | On build-push job |
| V18-07 | Release workflow pre-release filter | shell | `grep 'latest=auto' .github/workflows/release.yml` | Confirms D-11 mechanism |
| V18-08 | README required headers | shell | `for h in "Quickstart" "Prerequisites" "Reverse proxy" "Upgrade" "Restore" "Troubleshooting" "License"; do grep -q "## $h" README.md && echo "OK: $h" \|\| echo "MISSING: $h"; done` | All must print OK |
| V18-09 | README docker-compose image snippet | shell | `grep 'ghcr.io/jheikkila54/coffee-snobbery' README.md` | Operator knows the image path |
| V18-10 | README NPM walkthrough + TRUSTED_PROXY_IPS callout | shell | `grep -q 'TRUSTED_PROXY_IPS=\*' README.md` | Non-negotiable per project memory |
| V18-11 | README upgrade three-line procedure | shell | `grep -q 'docker compose pull' README.md && grep -q 'docker compose up -d' README.md` | Both lines present |
| V18-12 | README GHCR troubleshooting entry | shell | `grep -q '403 from ghcr' README.md \|\| grep -q 'Image pull fails' README.md` | D-20 |
| V18-13 | CONTRIBUTING.md existence + content | shell | `test -f CONTRIBUTING.md && grep -q 'make smoke' CONTRIBUTING.md && grep -q 'ruff' CONTRIBUTING.md && grep -q 'docker compose cp' CONTRIBUTING.md` | D-14 |
| V18-14 | Dockerfile OCI label set | shell | `grep 'org.opencontainers.image' Dockerfile \| wc -l` | Assert >= 4 labels |
| V18-15 | Dockerfile ARG APP_VERSION | shell | `grep 'ARG APP_VERSION' Dockerfile` | D-12 version stamp |
| V18-16 | Release workflow APP_VERSION build-arg | shell | `grep 'APP_VERSION=' .github/workflows/release.yml` | D-12 |
| V18-17 | .gitignore override entry | shell | `grep 'docker-compose.override.yml' .gitignore` | D-05 |
| V18-18 | docker-compose.override.yml.example exists | shell | `test -f docker-compose.override.yml.example` | D-05 |
| V18-19 | DIST-05 smoke: /healthz returns ok | shell | See Section 10 — full smoke procedure | Manual; assert `{"status":"ok"}` |
| V18-20 | DIST-05 smoke: /setup returns 200 with zero users | shell | See Section 10 | Manual; requires clean volume |

**Note on V18-01 `build:` absence check:**
```bash
docker compose -f docker-compose.yml config | python -c "
import sys, yaml
cfg = yaml.safe_load(sys.stdin)
svc = cfg['services']['coffee-snobbery']
assert 'build' not in svc, 'build: block found — violates D-05'
assert 'ghcr.io/jheikkila54/coffee-snobbery' in svc.get('image', ''), 'GHCR image pin missing'
print('V18-01: OK')
"
```

---

## Open Questions for Planner

1. **Port binding in operator-facing Compose.** The current `127.0.0.1:8080:8000` binding is for the host-NGINX topology. For NPM, the container is reachable on the Docker network without a host port. Should the operator-facing Compose keep the port mapping (compatible with both paths) or remove it (cleaner for NPM-only operators)? Recommendation: keep it and note in the README that NPM operators can comment it out.

2. **`coffee-snobbery-net` as external network.** For NPM to reach `coffee-snobbery` by container name, NPM must join the `coffee-snobbery-net` network. The current Compose defines it as a local `bridge`. The operator README must explain how to attach NPM to this network. Two approaches: (a) tell operators to add the Snobbery network to NPM's compose file as an external network, or (b) mark `coffee-snobbery-net` as `external: true` in the Snobbery Compose and tell operators to `docker network create coffee-snobbery-net` first. Approach (a) is more operator-friendly (NPM's compose is separate). The README should show the specific `docker network connect` command.

3. **`docker-compose.override.yml` in `.dockerignore`.** The existing `.dockerignore` likely excludes this file pattern already (it excludes `docker-compose.*` or similar). The planner should check and add the entry if needed.

4. **`pyproject.toml` version bump.** CONTEXT.md D-12 says "git tag IS version". `pyproject.toml` currently says `"0.1.0"`. Should it be bumped to `"1.2.0"` in Phase 18 (when the first `v1.2.0` tag ships)? Recommendation: yes — bump to `"1.2.0"` in the Phase 18 plan and keep it in sync with the git tag for each release. The executor should bump this as part of the release-prep wave.

5. **GitHub Release auto-notes.** CONTEXT.md (Claude's Discretion) says: "if it's a 5-line add, do it." Adding a GitHub Release via `actions/create-release@v1` or `gh release create` in the `build-push` job is straightforward. Planner should add it as a low-priority task in the last wave.

6. **`APP_VERSION` env var NOT in `.env.example`.** Confirmed in Section 9: do not add it. It is a Dockerfile `ENV` injected at build time, not an operator-controlled runtime variable. The parity test would fail if it were added.

---

## Sources

### Primary (HIGH confidence)
- `github.com/docker/metadata-action/releases` — verified v6.1.0 is current (May 22 2026)
- `github.com/docker/build-push-action/releases` — verified v7.2.0 is current (v7 GA March 2025)
- `github.com/docker/login-action/releases` — verified v4.2.0 is current (May 22 2026)
- `docs.docker.com/build/ci/github-actions/multi-platform/` — multi-arch YAML, action versions
- `docs.docker.com/build/ci/github-actions/cache/` — GHA cache backend, API v2 requirement (April 2025)
- `docs.docker.com/compose/how-tos/multiple-compose-files/merge/` — override file merge rules
- `docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry` — GHCR default private visibility, public change steps
- `github.com/docker/metadata-action` (README) — flavor latest=auto pre-release behavior, OCI labels, tag pattern examples

### Secondary (MEDIUM confidence)
- `authelia.com/integration/proxies/nginx-proxy-manager/` — confirms NPM Advanced tab accepts location blocks (inside server block)
- `deepwiki.com/NginxProxyManager/nginx-proxy-manager/6.2-custom-nginx-configurations` — confirms Advanced tab is injected via `{{ advanced_config }}` Liquid variable inside server block
- `oneuptime.com/blog/post/2025-12-20-multi-platform-docker-builds-github-actions/view` — QEMU vs native runner performance note

### Tertiary (LOW confidence / training knowledge)
- GHCR mid-run push failure / tag-overwrite behavior — standard OCI registry behavior, verified behavior against training knowledge
- NPM `$server`/`$port` variable availability inside Advanced tab — not officially documented; direct `coffee-snobbery:8000` recommended instead

---

## Metadata

**Confidence breakdown:**
- Release CI architecture: HIGH — action versions verified against release pages; YAML patterns verified against official Docker docs
- Compose override pattern: HIGH — verified against official Docker Compose docs
- Metadata-action tag matrix: HIGH — verified against metadata-action README (latest=auto pre-release behavior explicitly documented)
- GHCR visibility flow: HIGH — verified against GitHub official docs
- NPM Advanced tab location block support: MEDIUM — confirmed via Authelia integration guide (third-party, authoritative in practice)
- Version stamp approach: MEDIUM — based on reading actual `app/routers/admin/system.py` code; env-var fallback pattern is standard

**Research date:** 2026-05-28
**Valid until:** 2026-08-28 (action major versions are stable; Docker Compose behavior is stable; GHCR behavior unlikely to change)
