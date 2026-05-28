# Phase 18: Self-Host Packaging - Pattern Map

**Mapped:** 2026-05-28
**Files analyzed:** 11 (7 modified + 3 created + 1 modified-app-code)
**Analogs found:** 10 / 11 (CONTRIBUTING.md has no analog — new file type)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `.github/workflows/release.yml` | CI workflow | event-driven | `.github/workflows/ci.yml` | role-match (trigger differs) |
| `docker-compose.yml` | compose config | config transform | `docker-compose.yml` itself (current shape) | self-analog (transform in place) |
| `.gitignore` | config | n/a | `.gitignore` itself | self-analog (append) |
| `.dockerignore` | config | n/a | `.dockerignore` itself | self-analog (append) |
| `Dockerfile` | dockerfile | config | `Dockerfile` itself (current) | self-analog (append labels + ARG) |
| `README.md` | docs | n/a | `README.md` itself (current) | self-analog (restructure) |
| `.env.example` | config | n/a | `.env.example` + `app/config.py` | self-analog (prose polish only) |
| `CLAUDE.md` | docs | n/a | `CLAUDE.md` itself | self-analog (one-line pointer) |
| `app/routers/admin/system.py` | app code | request-response | `app/routers/admin/system.py` itself | self-analog (surgical version patch) |
| `docker-compose.override.yml.example` | compose config | n/a | `docker-compose.yml` (test service block lines 89-120) | exact |
| `CONTRIBUTING.md` | docs | n/a | `README.md` (content carve-out) | content-source |

---

## Pattern Assignments

### `.github/workflows/release.yml` (CI workflow, event-driven)

**Analog:** `.github/workflows/ci.yml`

**Trigger pattern** (ci.yml lines 1-3 — change for release):
```yaml
# ci.yml uses:
on: [push, pull_request]

# release.yml uses:
on:
  push:
    tags:
      - 'v*'
```

**Postgres service container pattern** (ci.yml lines 9-22 — copy verbatim):
```yaml
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
```

**Python setup + Tailwind build + ruff + pytest steps** (ci.yml lines 25-85 — copy entire step block verbatim into the `test` job):
```yaml
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
  env: [same as above]
  run: python -m pytest tests/ -rs --tb=short --ignore=tests/e2e
```

**New `build-push` job** — no analog in ci.yml; use RESEARCH.md skeleton verbatim (lines 301-353 of 18-RESEARCH.md):
```yaml
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

**Landmines:**
- `permissions:` belongs on `build-push` job ONLY, not on `test` job (security principle of least privilege)
- `target: runtime` is mandatory — without it, the final Dockerfile stage `dev` runs pytest on `up -d`
- Tailwind step must use `v3.4.17` (NOT v4) — project memory `tailwind-v3-not-v4`
- Both ruff steps must appear — project memory `executors-skip-ruff-ci-gates-both`
- Both pytest steps (full suite + isolation double-run) must appear — mirrors ci.yml exactly
- `flavor: latest=auto` is the D-11 pre-release filter mechanism; do not replace with a conditional
- `APP_VERSION` env var must NOT be added to `Settings` or `.env.example` — it's a Dockerfile `ENV`, not a runtime secret

---

### `docker-compose.yml` (compose config, transform in place)

**Analog:** Current `docker-compose.yml` (self)

**Current `coffee-snobbery` service block** (lines 55-88 — transform this):
```yaml
# CURRENT (lines 55-88):
coffee-snobbery:
  image: coffee-snobbery:latest
  build:
    context: .
    dockerfile: Dockerfile
    target: runtime
  container_name: coffee-snobbery
  restart: unless-stopped
  ...

# AFTER D-05 transform:
coffee-snobbery:
  image: ghcr.io/jheikkila54/coffee-snobbery:v1.2.0
  # build: block removed — operators pull; devs use docker-compose.override.yml
  container_name: coffee-snobbery
  restart: unless-stopped
  ...
  # All other fields (security_opt, mem_limit, depends_on, env_file,
  # environment, volumes, networks, ports) stay identical
```

**`coffee-snobbery-test` service block** (lines 89-120 — DELETE from this file, move to override example):
```yaml
# DELETE lines 89-120 in full: the entire coffee-snobbery-test service
# including its comment block. This service moves to docker-compose.override.yml.example.
```

**Network block stays** (lines 122-125 — unchanged):
```yaml
networks:
  coffee-snobbery-net:
    driver: bridge
    name: coffee-snobbery-net
```

**Landmines:**
- Keep `127.0.0.1:8080:8000` port binding — required for plain-nginx path (D-16); NPM operators are told they can comment it out
- Keep the `DATABASE_URL` inline override in `environment:` (lines 76-80) — keeps hostname correct regardless of what's in `.env`
- Keep all security hardening fields (`security_opt`, `mem_limit`, `pids_limit`, `cap_drop`, `cap_add`) on the db service
- The `name: coffee-snobbery` at the top (line 20) stays — it's the compose project name

---

### `docker-compose.override.yml.example` (compose config, new file)

**Analog:** `docker-compose.yml` lines 89-120 (the test service block being removed)

**Source block to copy** (docker-compose.yml lines 94-120):
```yaml
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

**Full override example file structure** (from RESEARCH.md):
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

**Landmines:**
- No `container_name:` on `coffee-snobbery-test` (existing file omits it — allows parallel `run` invocations)
- No `restart:`, no `ports:`, no `photo/backup volumes` on test service (matches existing pattern)
- The override's `coffee-snobbery` build block uses `target: runtime` (not `dev`)

---

### `Dockerfile` (dockerfile, append only)

**Analog:** `Dockerfile` itself (current)

**Existing `runtime` stage ENV block** (lines 69-73 — insert after this):
```dockerfile
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
```

**Add ARG + ENV for version stamp (after existing ENV block):**
```dockerfile
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}
```

**Add OCI labels (before EXPOSE line 122):**
```dockerfile
LABEL org.opencontainers.image.title="Snobbery" \
      org.opencontainers.image.description="Self-hosted household coffee log for pour-over enthusiasts" \
      org.opencontainers.image.url="https://github.com/jheikkila54/coffee-snobbery" \
      org.opencontainers.image.source="https://github.com/jheikkila54/coffee-snobbery" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.licenses="Proprietary"
```

**Existing EXPOSE + HEALTHCHECK + ENTRYPOINT** (lines 122-130 — DO NOT TOUCH):
```dockerfile
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1
ENTRYPOINT ["./entrypoint.sh"]
```

**Existing `dev` stage** (lines 132-166 — DO NOT TOUCH):
The entire `FROM runtime AS dev` block is unchanged; executor must not edit it.

**Landmines:**
- `ARG APP_VERSION=dev` must be in the `runtime` stage (after `FROM python:3.12-slim AS runtime`), NOT in the `tailwind-builder` stage — ARGs do not cross stage boundaries without re-declaration
- `ENTRYPOINT ["./entrypoint.sh"]` is sacrosanct (Phase 15 D-01..D-04) — do not modify
- The chown+gosu pattern in `entrypoint.sh` is already complete — Dockerfile changes are labels + ARG only
- `org.opencontainers.image.created` and `org.opencontainers.image.revision` are auto-set by `docker/metadata-action` at build time via `--label` flags — do not hardcode them in the Dockerfile

---

### `app/routers/admin/system.py` (app code, surgical patch)

**Analog:** `app/routers/admin/system.py` itself (current)

**Current version-reading block** (lines 133-144 — replace with env-var-first pattern):
```python
# CURRENT:
try:
    app_version = pkg_version("coffee-snobbery")
except PackageNotFoundError:
    _pyproject = Path(__file__).resolve().parents[3] / "pyproject.toml"
    if _pyproject.exists():
        with _pyproject.open("rb") as _f:
            app_version = tomllib.load(_f).get("project", {}).get("version", "unknown")
    else:
        app_version = "unknown"
```

**D-12 replacement pattern (env var first, then existing fallback chain):**
```python
import os

# REPLACE the try/except block with:
app_version = os.environ.get("APP_VERSION") or _read_version_fallback()

# Extract the fallback into a helper (or inline the check):
def _read_version_fallback() -> str:
    try:
        return pkg_version("coffee-snobbery")
    except PackageNotFoundError:
        _pyproject = Path(__file__).resolve().parents[3] / "pyproject.toml"
        if _pyproject.exists():
            with _pyproject.open("rb") as _f:
                return tomllib.load(_f).get("project", {}).get("version", "unknown")
        return "unknown"
```

**pyproject.toml version bump** (line 6 — one-line change):
```toml
# CURRENT:
version = "0.1.0"

# AFTER:
version = "1.2.0"
```

**Landmines:**
- `APP_VERSION` env var must NOT appear in `app/config.py` `Settings` — it is a Dockerfile `ENV`/`ARG`, not a pydantic-settings field. Adding it would cause `extra="forbid"` to crash at startup if the var is not set in `.env`
- `APP_VERSION` must NOT appear in `.env.example` — `tests/test_env_example.py` enforces strict equality between `.env.example` keys and `Settings.model_fields`; adding it would break the parity test
- The `os` import is already absent from `system.py` — add it; do not break the existing import block structure
- Project memory `ci-source-tree-vs-baked-image-divergence`: CI runs source tree without pip install; the env-var-first pattern means CI shows `APP_VERSION` env if set, or falls through to `pyproject.toml`

---

### `.gitignore` (config, append)

**Analog:** `.gitignore` itself (current, 31 lines)

**Current file structure** (for placement context):
```
# Secrets
.env

# GSD config
.planning/config.json

# Python build / cache
__pycache__/
...

# Tailwind
app/static/css/tailwind.*.css
!app/static/css/tailwind.src.css

# Build artifact
app/static/build_id.txt
```

**Append to end of file:**
```
# Dev compose override — gitignored so operator-facing docker-compose.yml
# stays clean; devs copy docker-compose.override.yml.example.
docker-compose.override.yml
```

---

### `.dockerignore` (config, append)

**Analog:** `.dockerignore` itself (current, 41 lines)

**Current file ends at line 41** (no existing docker-compose.* exclusion). The file already excludes `.env` (line 25) and `.env.*` (line 26) but does NOT exclude `docker-compose.override.yml`.

**Append to end of file:**
```
# Dev compose override — never bake into the image
docker-compose.override.yml
```

---

### `.env.example` (config, prose polish)

**Analog:** `.env.example` itself (current) + `app/config.py` Settings (source of truth)

**Current file** (all 11 vars, lines 1-37 — parity already confirmed, no structural changes):
The 11 vars (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL`, `APP_SECRET_KEY`, `APP_ENCRYPTION_KEY`, `TRUSTED_PROXY_IPS`, `APP_TIMEZONE`, `BACKUP_RETENTION_DAYS`, `LOG_LEVEL`, `LOG_FORMAT`) exactly match `Settings` fields. `tests/test_env_example.py` enforces this.

**Specific prose changes only (D-17):**
- `TRUSTED_PROXY_IPS=127.0.0.1` comment: update to note "set to `*` when using Nginx Proxy Manager" (currently says `127.0.0.1` is for the NGINX-on-same-VPS shape)
- `POSTGRES_USER` and `POSTGRES_DB`: add inline "(default: snobbery)" note if not already present
- Verify `APP_SECRET_KEY` generation hint is prominent (line 19 — it is)
- Verify `APP_ENCRYPTION_KEY` comma-separated rotation note is present (line 23 — it is)

**Hard rule:** Do NOT add `APP_VERSION` to this file. The parity test (`tests/test_env_example.py`) would fail.

---

### `README.md` (docs, restructure)

**Analog:** `README.md` itself (current 200+ lines)

**Content to PRESERVE verbatim (do not rewrite these blocks):**

Single-worker warning block (lines 65-84 — location #3 of three-place system):
```
### Single uvicorn worker — DO NOT change
...
grep -RIn -E '\-\-workers 1|single worker' README.md entrypoint.sh app/services/scheduler.py
must return at least three hits.
```

NGINX server-block snippet (lines 86-135 — plain nginx secondary path, D-16):
```nginx
server { ... }  # full block verbatim
```

**Content to MOVE to CONTRIBUTING.md (carve-out, D-14):**
- "Working with the code" make-target table (lines 42-59)
- "Deploying a change" section (lines 139-150)
- Root-owned volumes one-time fix (lines 152-159)

**New section order (D-14 target structure):**
```
# Snobbery
[tagline]

## What is this

## Prerequisites

## Quickstart
[operator: git clone or download compose + .env.example; cp + edit; docker compose up -d; visit https://<host>]

## Environment variables
[table: all 11 vars with purpose + generation hint]

## Reverse proxy
### Nginx Proxy Manager (recommended)
[D-15 field-list + gotchas: shared network, TRUSTED_PROXY_IPS=*, X-Forwarded-Proto, /sw.js passthrough]
### Plain NGINX
[verbatim snippet from current README lines 86-135]

## Single uvicorn worker — DO NOT change
[verbatim from current README lines 65-84 — three-place system location #3]

## Upgrade
[three-line procedure: edit image: tag → docker compose pull → docker compose up -d]

## Restore from backup

## Troubleshooting
[existing block + new GHCR pull fails / 403 entry]

## License
```

**Key new content blocks (from RESEARCH.md):**

NPM walkthrough gotchas — these MUST appear (D-15, project memory `snobbery-vps-npm-reverse-proxy`):
- Shared Docker network: `docker network connect coffee-snobbery-net <npm-container-name>` step
- `TRUSTED_PROXY_IPS=*` is non-negotiable for NPM topology
- `/sw.js` Advanced tab passthrough snippet (RESEARCH.md lines 628-635)

Upgrade section (D-19):
```bash
# 1. Edit image: line in docker-compose.yml to the new version
#    image: ghcr.io/jheikkila54/coffee-snobbery:v1.3.0
docker compose pull
docker compose up -d
# Migrations run automatically on container start.
```

GHCR troubleshooting entry (D-20, from RESEARCH.md lines 655-662):
```
**Image pull fails / 403 from ghcr.io.**
Snobbery images are public — docker pull ghcr.io/jheikkila54/coffee-snobbery:v1.2.0
should work without authentication...
```

**Audit check (MUST pass after rewrite):**
```bash
grep -RIn -E '\-\-workers 1|single worker' README.md entrypoint.sh app/services/scheduler.py | wc -l
# Must return >= 3
```

---

### `CONTRIBUTING.md` (docs, new file)

**No direct analog** — content is carved from README + Makefile.

**Content sources:**
- README.md lines 42-59 (make-target table)
- README.md lines 139-159 (deploying a change, root-owned volume fix)
- `Makefile` targets (lines 36-98 — reference for command correctness)
- RESEARCH.md lines 667-761 (CONTRIBUTING.md outline — use as the structural template)

**Makefile targets to reference** (lines 36-98 of Makefile):
```makefile
make up, make down, make logs, make logs-db, make psql, make migrate,
make revision, make test, make smoke, make shell, make build, make fmt, make lint
```

**Key sections to include (from RESEARCH.md CONTRIBUTING.md outline):**
- Development Prerequisites (Docker + Compose v2 + Git + `cp override.yml.example`)
- Local Dev Loop (make-target table)
- Fast Per-File Iteration (`docker compose cp` trick — project memory `docker-cp-into-container-nesting` caveat: use file-level cp)
- Linting and Formatting (`ruff format --check .` + `ruff check .`)
- Running the Test Suite (make test + direct pytest + docker compose run gate)
- Committing (conventional commits reference)
- Deploying a Change (git pull + build + up -d — the dev/VPS flow)
- Releasing (`git tag v1.2.0 && git push --tags`)
- GHCR Package Maintenance (one-time public visibility step + manual untagged cleanup)

**Landmines:**
- The `docker compose cp` fast-iteration section must include the project memory caveat (`docker-cp-into-container-nesting`): use file-level cp (`docker compose cp tests/test_foo.py ...:/app/tests/test_foo.py`), NOT directory-level cp which nests
- The "Releasing" section must include the one-time GHCR public visibility step (from RESEARCH.md lines 856-870) — this is a human action, not automatable

---

### `CLAUDE.md` (docs, optional pointer)

**Analog:** `CLAUDE.md` itself (current)

**Change:** One-line pointer in the "Files worth knowing" table or a new `## Operator / Dev Split` note:
```markdown
# In CLAUDE.md "Files worth knowing" table — add row:
| `CONTRIBUTING.md` | Dev content (local loop, test, lint, release ritual) carved from README in Phase 18 |
| `docker-compose.override.yml.example` | Dev override template; copy to `docker-compose.override.yml` (gitignored) for the build-loop |
```

**Also update** the `docker-compose.yml` command blocks if they reference `make up` — the README quickstart now uses `docker compose up -d` directly (D-07/D-08).

---

## Shared Patterns

### Three-Place Single-Worker Warning System
**Source:** `README.md` lines 65-84 + `entrypoint.sh` (top-of-file comment) + `app/services/scheduler.py` (top-of-file comment)
**Apply to:** README rewrite must preserve the warning block verbatim at location #3
**Audit grep:**
```bash
grep -RIn -E '\-\-workers 1|single worker' README.md entrypoint.sh app/services/scheduler.py
# Must return >= 3 hits after the README rewrite
```

### `.env.example` Parity Invariant
**Source:** `tests/test_env_example.py` (enforces strict key equality between `.env.example` and `app/config.py Settings.model_fields`)
**Apply to:** `.env.example` prose polish AND `app/routers/admin/system.py` version patch
**Rule:** Do not add `APP_VERSION` to `.env.example`. Do not add it to `Settings`. The parity test runs against the 11-field count — adding anything breaks it.
**Verify:**
```bash
docker compose exec coffee-snobbery python -m pytest tests/test_env_example.py -x
```

### Tailwind v3.4.17 Invariant
**Source:** `Dockerfile` lines 25, 41-42 + `ci.yml` lines 45-51
**Apply to:** `release.yml` Tailwind build step
**Rule:** Binary URL must use `v3.4.17`, NOT v4. Project memory `tailwind-v3-not-v4`. The release workflow mirrors ci.yml exactly for this step.

### `target: runtime` Invariant
**Source:** `docker-compose.yml` lines 60-62 (comment) + `Dockerfile` lines 132-166
**Apply to:** `release.yml` build-push step, `docker-compose.override.yml.example`
**Rule:** Always `target: runtime` for production builds. Without it, the last stage (`dev`) is built, whose `ENTRYPOINT` is pytest.

### GHCR Auth Pattern
**Source:** RESEARCH.md (D-13 / build-push job)
**Apply to:** `release.yml` build-push job
```yaml
permissions:
  contents: read
  packages: write
# Login step:
uses: docker/login-action@v4
with:
  registry: ghcr.io
  username: ${{ github.actor }}
  password: ${{ secrets.GITHUB_TOKEN }}
```
No PAT required. `permissions:` on the `build-push` job only.

### NPM Topology Constraints
**Source:** Project memory `snobbery-vps-npm-reverse-proxy`
**Apply to:** README.md NPM walkthrough section
**Non-negotiable:** `TRUSTED_PROXY_IPS=*` for NPM topology. Must appear in README with explanation.
**Docker network:** `docker network connect coffee-snobbery-net <npm-container-name>` must be in the NPM setup steps.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `CONTRIBUTING.md` | docs | n/a | No existing contributor guide in this repo; content is carved from README + Makefile |

---

## Metadata

**Analog search scope:** `.github/workflows/`, `Dockerfile`, `docker-compose.yml`, `.gitignore`, `.dockerignore`, `.env.example`, `app/config.py`, `app/routers/admin/system.py`, `Makefile`, `README.md`, `pyproject.toml`
**Files scanned:** 12
**Pattern extraction date:** 2026-05-28

### Cross-Reference: Project Memory Anchors

| Memory Key | File Affected | What It Means |
|---|---|---|
| `ci-source-tree-vs-baked-image-divergence` | `app/routers/admin/system.py` | `importlib.metadata` fails on CI source tree; env-var-first patch is the fix |
| `snobbery-vps-npm-reverse-proxy` | `README.md` | `TRUSTED_PROXY_IPS=*` non-negotiable; shared docker network mandatory |
| `tailwind-v3-not-v4` | `release.yml` | Tailwind build step must use v3.4.17 binary, not v4 |
| `executors-skip-ruff-ci-gates-both` | `release.yml` | Both `ruff format --check .` AND `ruff check .` steps required |
| `docker-cp-into-container-nesting` | `CONTRIBUTING.md` | Fast-iteration section must warn: file-level cp only, not directory-level |
| `strict-csp-blocks-htmx-indicator` | No change | Out of scope; referenced only if UI changes appear |
| `snobbery-test-gate-runtime` | `docker-compose.override.yml.example` | Test gate requires baked tree (no bind-mount); override example must not add volumes: mount |
