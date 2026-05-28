# Contributing to Snobbery

Operator docs live in `README.md`. This file is for working on Snobbery itself — local dev loop, tests, lint, release ritual.

## Development Prerequisites

- Docker + Docker Compose v2
- Git
- `cp docker-compose.override.yml.example docker-compose.override.yml`

Compose auto-merges `docker-compose.override.yml` (gitignored). With the override in place, `docker compose up -d` builds the image locally instead of pulling from GHCR.

## Local Dev Loop

The Makefile is convenience over `docker compose` — raw commands work identically.

| Command | What it does |
|---------|-------------|
| `make up` | `docker compose up -d` — start the two-service stack |
| `make down` | `docker compose down` — stop, keep volumes |
| `make logs` | Tail the web container logs |
| `make logs-db` | Tail the Postgres container logs |
| `make psql` | Open a `psql` shell inside the db container |
| `make migrate` | Run `alembic upgrade head` (migrations also run on container start) |
| `make revision MSG="add foo column"` | Generate a new alembic autogenerate revision |
| `make test` | Run `pytest -x` inside the web container |
| `make smoke` | Cold-start gate: `down -v && up -d --build && /healthz` |
| `make shell` | Open a `bash` shell inside the web container |
| `make build` | Rebuild the web image (`docker compose build coffee-snobbery`) |
| `make fmt` | Run `ruff format .` inside the web container |
| `make lint` | Run `ruff check .` inside the web container |

## Fast Per-File Iteration

The container has no source bind-mount — code changes don't reach the running container until you either rebuild or copy them in. For one-file Python edits during a test loop:

```bash
# CORRECT — file-level copy (no directory-nesting trap).
docker compose cp app/routers/foo.py coffee-snobbery:/app/app/routers/foo.py
docker compose exec coffee-snobbery python -m pytest tests/test_foo.py -x

# WRONG — directory-level copy nests (creates /app/app/routers/app/routers/foo.py).
# docker compose cp app/ coffee-snobbery:/app/app/   # DO NOT DO THIS
```

Template and static-file edits ALSO require either a rebuild or a `docker compose cp` — Jinja caches templates in-process and the image bakes the static directory.

For a full rebuild after broader changes: `docker compose build coffee-snobbery && docker compose up -d coffee-snobbery`.

## Linting and Formatting

CI gates on **both** ruff steps. Run both before pushing:

```bash
ruff format --check .
ruff check .
```

Or fix in place:

```bash
ruff format .
ruff check --fix .
```

Inside the container (matches CI): `make fmt && make lint`.

## Running the Test Suite

Quick targeted run during dev:

```bash
docker compose exec coffee-snobbery python -m pytest tests/test_foo.py -x
```

Full gate (matches CI — requires the dev override active so `coffee-snobbery-test` exists):

```bash
docker compose build coffee-snobbery-test
docker compose run --rm coffee-snobbery-test
# Or: make test (with --build alternative — see Makefile)
```

The test gate runs the baked tree, not your source directory. Rebuild `coffee-snobbery-test` before each run or use `docker compose cp` to push individual files into the live container.

## Committing

Use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:`, `fix:`, `chore:`, `refactor:`, `docs:`, `style:`
- Short, imperative, present tense ("add backup retention config")

Branches: small changes go straight to `main`; anything touching schema, auth, encryption, AI scheduling, or deployment topology goes on a feature branch with a PR.

## Deploying a Change to the VPS

From the repo root on the VPS:

```bash
git pull
docker compose build coffee-snobbery
docker compose up -d coffee-snobbery
docker compose logs -f coffee-snobbery
# Confirm: alembic upgrade completes, then `Application startup complete.`
```

Note: this is the **dev → VPS direct-deploy** path. The **release** path goes through CI and a tag push (see below) and produces a versioned multi-arch image on GHCR that any operator can pull.

### One-time: fix root-owned volumes on an existing VPS deployment (G-01)

Volumes created before the Phase 15 entrypoint fix are owned by `root`, which blocks the `app` user (UID 1000) from writing backups and photo uploads. Fresh deploys do NOT need this step — the Phase 15 entrypoint runs `chown -R app:app /app/data` at startup as root, then drops privileges via `gosu`.

If you deployed before Phase 15 and backups or photo uploads fail with permission errors:

```bash
docker compose run --rm -u root coffee-snobbery chown -R app:app /app/data
```

## Releasing

The release ritual is a single tag push:

```bash
git tag v1.2.0
git push --tags
```

This fires `.github/workflows/release.yml`:

1. `test` job — verbatim CI gate (Tailwind v3.4.17 build → `ruff format --check .` → `ruff check .` → `pytest tests/ -rs --ignore=tests/e2e` → isolation double-run).
2. `build-push` job (gated on `needs: test`) — QEMU + Buildx, multi-arch (`linux/amd64,linux/arm64`), pushes to `ghcr.io/jheikkila54/coffee-snobbery` with the following tag matrix:
   - `:v1.2.0` (exact)
   - `:1.2` (mutable major.minor — stable tags only)
   - `:1` (mutable major — stable tags only, disabled on v0.x)
   - `:latest` (mutable — stable tags only, pre-releases skip this via `flavor: latest=auto`)

Pre-release tags (`v1.2.0-rc1`, `v1.2.0-beta1`) publish under the exact tag only — they do NOT bump `:latest`, `:1.2`, or `:1`, so production operators floating on those tags are safe.

The image is stamped with the git tag via `APP_VERSION=${{ github.ref_name }}` build-arg → `Dockerfile ARG APP_VERSION` → `ENV APP_VERSION=` → `app/routers/admin/system.py` displays it on `/admin`. `org.opencontainers.image.version` label also carries the tag.

### Re-running a failed release

The workflow may fail mid-push (e.g., one arch built, the other failed). To re-run, delete and re-push the tag:

```bash
git tag -d v1.2.0
git push origin :refs/tags/v1.2.0
git tag v1.2.0
git push --tags
```

GHCR overwrites matching tags on push — no manual cleanup required.

## After First Release — One-Time GHCR Public Visibility Flip

GHCR publishes packages as **private by default**. After the first `v*` tag push, the package will exist at `https://github.com/users/jheikkila54/packages/container/coffee-snobbery` but `docker pull` will fail with 403 without `docker login ghcr.io`.

To make the image public (DIST-02 requires it):

1. Visit `https://github.com/users/jheikkila54/packages/container/coffee-snobbery/settings`.
2. Scroll to "Danger Zone" → "Change visibility" → select **Public** → confirm.
3. Verify: `docker pull ghcr.io/jheikkila54/coffee-snobbery:v1.2.0` (without `docker login`).

This is a **one-way** operation — public → private is not supported by GitHub once any download has occurred. Subsequent pushes to the same package keep the public visibility.

## GHCR Package Maintenance

Untagged image versions accumulate over time (each release creates and orphans the previous untagged platform manifests). Clean up periodically via the GitHub UI:

> GitHub → Profile → Packages → coffee-snobbery → Manage versions → delete untagged

Automation via `actions/delete-package-versions` is possible but deferred — manual periodic cleanup is sufficient at household release cadence.

## Adding a New Env Var

Four steps:

1. Add the key to `.env.example` with a generation hint comment.
2. Add the key to the `environment:` section of `docker-compose.yml` (and the override example if dev-only).
3. Add the field to the `Settings` class in `app/config.py` (pydantic-settings) — never read `os.environ` directly elsewhere.
4. Document in `README.md` → "Environment variables" table if operator-facing.

`tests/test_env_example.py` enforces step 1 ↔ step 3 parity — it will fail if you miss either side.

## Files Worth Knowing

See `CLAUDE.md` § "Files worth knowing" for the per-file role table.
