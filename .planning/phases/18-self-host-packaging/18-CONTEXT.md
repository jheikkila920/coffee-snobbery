# Phase 18: Self-Host Packaging - Context

**Gathered:** 2026-05-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Turn Snobbery from a "git clone + `docker compose build`" experience into a "pull a prebuilt multi-arch image and run" experience for new operators on their own VPS. Six locked requirements:

- **DIST-01:** Deploy with no `docker compose build` step (compose references a published `image:`)
- **DIST-02:** Versioned multi-arch (amd64 + arm64) image published to GHCR by a release CI workflow triggered on a version tag
- **DIST-03:** README contains a complete from-zero self-host walkthrough (prereqs, env vars, first run, upgrade)
- **DIST-04:** Deploy doc includes step-by-step Nginx Proxy Manager setup (proxy host to `coffee-snobbery:8000`, `TRUSTED_PROXY_IPS`, shared docker network)
- **DIST-05:** Fresh install boots cleanly — migrations auto-run, operator lands at `/setup` to create first admin
- **DIST-06:** `.env.example` documents every required env var with generation hints for `APP_SECRET_KEY` and `APP_ENCRYPTION_KEY`

Explicitly NOT in this phase:
- **Image signing / SBOM / cosign / syft** — overkill for a household-scale self-hostable app; revisit only if a downstream operator asks.
- **CHANGELOG.md / formal release-notes process** — GitHub Releases UI is sufficient; let release notes accumulate there at tag time.
- **Caddy / Traefik / docker swarm / k8s walkthroughs** — out of scope. NPM is primary, plain nginx is secondary.
- **Deploy automation scripts** (`upgrade.sh`, `deploy.sh`) — KISS, three-line operator workflow stays raw.
- **DIST-07** (post-`/setup` API key prompt) — closed in Phase 17 (banner pattern, see Phase 17 D-19).
- **Stack changes** (Python/FastAPI/Postgres versions, single-worker rule) — locked, untouched.
- **App-level features** — no router, model, template, or analytics changes. This phase is packaging + docs only.

</domain>

<decisions>
## Implementation Decisions

### Registry path, visibility, tags

- **D-01:** Publish to **`ghcr.io/jheikkila54/coffee-snobbery`**. Matches the GitHub repo owner/name exactly so the link from image to source is obvious. No separate org.
- **D-02:** GHCR image visibility is **public**. Matches the v1.2 "self-hostable by others" goal. `docker pull` works without `docker login ghcr.io`.
- **D-03:** **Stable-release tag scheme:** every stable `v*` tag publishes four tags simultaneously — `v1.2.0` (exact), `1.2` (mutable major.minor), `1` (mutable major), `latest` (mutable). Operators can pin tight or float on whichever cadence they want. Standard pattern for self-hostable apps (docker/metadata-action handles this directly).
- **D-04:** Committed `docker-compose.yml` **pins `image:` to the current semver** (e.g., `:v1.2.0`). Phase 22 (Verification & Release) is the one that bumps the pin when v1.2.0 ships. Operators who `git clone` get a known-good combination; operators who pin tighter than `latest` get reproducibility. Floating-on-latest is documented as an option but not the default in the committed file.

### Compose split (image-only vs build-aware)

- **D-05:** **Override-file pattern.** Committed `docker-compose.yml` is operator-facing: `image: ghcr.io/jheikkila54/coffee-snobbery:vX.Y.Z` only, no `build:` block on the `coffee-snobbery` service. A `docker-compose.override.yml` is **gitignored** and adds the `build:` block back for the dev loop (compose auto-merges `override.yml` by default, zero ceremony). `.gitignore` gains a `docker-compose.override.yml` entry; an example `docker-compose.override.yml.example` is committed showing the dev block.
- **D-06:** **`coffee-snobbery-test` service moves to the dev override** — it requires the `dev` Dockerfile stage which requires a build, and operators never run the gate. Operator-facing compose stays lean; test workflow stays exactly the same for the developer.
- **D-07:** **Makefile stays dev-only.** README operator quickstart uses raw `docker compose` commands only — no `make` prereq on the host. Makefile + `make smoke`/`make test`/`make build` migrate to CONTRIBUTING.md.
- **D-08:** **Operator's first-run command is the single line `docker compose up -d`.** Compose pulls referenced images on `up` if absent; no explicit `pull` step in the quickstart. README shows the explicit `pull` only in the upgrade flow (D-19).

### Release CI trigger + scope

- **D-09:** **Trigger is `on: push: tags: ['v*']`** — single trigger, no GitHub Release ceremony, no `workflow_dispatch` fallback. `git tag v1.2.0 && git push --tags` is the entire release ritual.
- **D-10:** **The release workflow re-runs the full test gate before pushing the image.** Steps: `ruff format --check .` → `ruff check .` → `pytest tests/ -rs --tb=short --ignore=tests/e2e` against a Postgres-16 service container (mirroring `ci.yml`'s posture), then `docker buildx` + push. ~5–10 min slower than push-only; eliminates "tagged a flaky commit and shipped it."
- **D-11:** **Pre-release tag policy:** any tag matching `v*-*` (e.g., `v1.2.0-rc1`, `v1.2.0-beta1`) publishes to GHCR under the **exact tag only**. The mutable `latest` / `1` / `1.2` tags are NOT touched on pre-release tags. Production operators floating on `:latest` or `:1.2` never accidentally pull a pre-release. The planner implements this as a docker/metadata-action `flavor: latest=false` + filtered tag list, or as a conditional in the release job.
- **D-12:** **Version source-of-truth is the git tag.** Workflow reads `${{ github.ref_name }}` (e.g., `v1.2.0`) and stamps it into image labels (`org.opencontainers.image.version`) and into the in-app version path (`app/system.py` — already aware per project memory `ci-source-tree-vs-baked-image-divergence`; planner reconciles the importlib.metadata fallback with the tag-stamp). No `VERSION` file in the repo. Tag IS version.
- **D-13:** **Multi-arch build approach** — `docker/setup-qemu-action` + `docker/setup-buildx-action` + `docker/build-push-action` with `platforms: linux/amd64,linux/arm64`. One Ubuntu runner, QEMU emulation for arm64. Well-trodden; no matrix complexity needed at household release cadence.

### Docs structure + NPM depth

- **D-14:** **Rewrite README to lead with self-host.** New section order: What this is → Quickstart (operator) → Prerequisites → Environment variables → Reverse proxy (NPM primary, plain nginx secondary) → Upgrade → Restore from backup → Troubleshooting → License. Dev content (Makefile, `make smoke`, ruff/mypy invocations, local-dev rebuild loop, `docker compose cp` fast-iteration trick, test-suite invocations) moves to a new **`CONTRIBUTING.md`**. CLAUDE.md and the existing CLAUDE.md `make/` references are unaffected.
- **D-15:** **NPM walkthrough = field-list + key gotchas, no screenshots.** Lists exact NPM fields (Domain Names, Forward Hostname/IP `coffee-snobbery`, Forward Port `8000`, scheme `http`, Block Common Exploits on, Websockets Support — leave off unless future SSE work needs it, SSL tab with Let's Encrypt, Advanced tab custom Nginx Configuration for `/sw.js` Cache-Control passthrough), then enumerates load-bearing gotchas: shared docker network attach, `TRUSTED_PROXY_IPS=*` for NPM (per project memory `snobbery-vps-npm-reverse-proxy`), the X-Forwarded-Proto requirement, and the `/sw.js` no-cache passthrough (PWA-7 invariant from current README). No screenshots — they rot with NPM UI changes.
- **D-16:** **Plain-nginx server-block snippet stays as a secondary section** below NPM. The existing snippet (README lines 86–135) already works; it's preserved verbatim or only lightly polished. Operators not running NPM (the minority) have a clear copy-paste path. Caddy/Traefik out of scope.
- **D-17:** **`.env.example` is audited for DIST-06 in this phase.** The file already documents 10 vars with generation hints; the planner cross-checks against `app/config.py` `Settings` (test_env_example.py already enforces parity, so this is verify-and-tighten-prose, not rebuild). Each var gets: purpose (one line), generation hint (if a secret), default (if optional). The four secrets (`POSTGRES_PASSWORD`, `APP_SECRET_KEY`, `APP_ENCRYPTION_KEY`, `DATABASE_URL` password patch) are called out at the top of the operator quickstart.
- **D-18:** **DIST-05 fresh-install path is verify-only.** Auto-migrations + `/setup`-first-admin are already shipped (`entrypoint.sh` + `auth.py:209`). The Phase 18 plan adds an explicit smoke test: spin up the published image in a clean VPS-ish environment (or a local `docker compose down -v && pull && up -d` simulation), confirm `/healthz` returns ok, confirm GET `/` redirects an unauthenticated user to `/setup`. Document the expected first-run sequence (logs show alembic upgrade then uvicorn startup, then operator visits `https://<host>` and is on `/setup`).
- **D-19:** **Upgrade walkthrough = three lines, explicit-tag-bump pattern.** Operator: (1) edit `image:` line in `docker-compose.yml` to the new semver, (2) `docker compose pull`, (3) `docker compose up -d`. Migrations auto-run on container start. Documented as a labelled `## Upgrade` section, copy-paste-ready. `:latest`/mutable-tag float is mentioned as an alternative but explicit-pin is the recommended path (matches D-04).
- **D-20:** **Troubleshooting carries forward** the existing README troubleshooting block (healthcheck failing, cookies dropping, migrations didn't run, pg_dump version mismatch). Add one new entry: **"Image pull fails / 403 from ghcr.io"** — covers public-image verification and docker login fallback. Operational smoke check (`/debug/proxy`) stays as-is.

### Claude's Discretion (planner picks)

- **Release workflow file layout** — single `release.yml` vs splitting "test" + "build-push" into two jobs in the same file (recommended: single file, two sequential jobs with `needs:` so push won't run if tests fail).
- **`docker/metadata-action` `tags:` config exact patterns** — there are a couple of idiomatic ways to express the D-03 tag scheme (raw `type=semver` lines vs `flavor: latest=true` + filters). Planner picks the cleanest.
- **Whether the release workflow also generates a GitHub Release with auto-generated notes** — nice-to-have; if it's a 5-line add, do it. If it pulls in extra actions, skip.
- **`tailwind-builder` stage caching** between releases — docker/build-push-action's GHA cache backend (`cache-from: type=gha`, `cache-to: type=gha,mode=max`) is the default; planner enables.
- **`docker-compose.override.yml.example` exact contents** — should mirror the dev `build:` block + the test service. Planner copies the current `docker-compose.yml` block.
- **CONTRIBUTING.md final structure** — Makefile reference, test/lint commands, local rebuild loop, `docker compose cp` fast-iteration recipe, conventional commits note, PR conventions. Planner organizes.
- **Whether to update CLAUDE.md** to reference the new operator/dev split — likely yes (one-line pointer); planner's call.
- **GHCR retention policy** — not a workflow step, GHCR setting. Mention in CONTRIBUTING/release-runbook section that untagged images can be cleaned periodically via UI or `actions/delete-package-versions` step; not load-bearing.
- **Image labels** — `org.opencontainers.image.{title,description,url,source,version,revision,licenses}` standard set; planner picks values.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` § "Phase 18: Self-Host Packaging" — goal + 6 success criteria + dependency on Phase 15
- `.planning/REQUIREMENTS.md` § "Self-Host Distribution (DIST)" — DIST-01..DIST-06 precise wording (DIST-07 is Phase 17 / closed)
- `.planning/PROJECT.md` § "Active" → "Self-host packaging" — milestone framing; § "Deployment shape" — the NPM topology; § "Key Decisions" → "Deploy behind Nginx Proxy Manager on the shared n8n box"
- `.planning/STATE.md` § "Current Position" — Phase 17 just closed; Phase 18 ready to plan
- `.planning/phases/15-v1-1-debt-cleanup/15-CONTEXT.md` — D-01..D-04 entrypoint root→chown→gosu pattern (already shipped; Phase 18 does NOT change it); D-09 nav redesign deferral (no IA work in Phase 18)
- `.planning/phases/17-ia-restructure/17-CONTEXT.md` — D-19 DIST-07 banner pattern (already shipped); Phase 18 does NOT touch the post-setup banner

### Code surfaces this phase modifies

**Existing files MUST be modified:**
- `docker-compose.yml` — pin `image:` to `ghcr.io/jheikkila54/coffee-snobbery:vX.Y.Z`, remove the `build:` block from the `coffee-snobbery` service, remove the `coffee-snobbery-test` service entirely (it moves to override). Keep the `image: coffee-snobbery:latest` fallback name OR remove — planner's call (D-05).
- `.gitignore` — add `docker-compose.override.yml`
- `README.md` — full restructure per D-14: self-host quickstart first, dev content moves out, NPM walkthrough added, upgrade section added, troubleshooting carries forward + GHCR pull entry (D-15/D-16/D-19/D-20).
- `.env.example` — verify-and-tighten prose per D-17; cross-check against `app/config.py` `Settings`
- `CLAUDE.md` — minor pointer to the new operator/dev split (planner's call, D-discretion)
- `app/system.py` — version path reconciliation with `github.ref_name` build-arg/label (D-12; project memory `ci-source-tree-vs-baked-image-divergence`)
- `Dockerfile` — add OCI image labels (`org.opencontainers.image.*`) and optionally `ARG APP_VERSION` consumed at build time; runtime stage otherwise unchanged. Entrypoint/chown/gosu (Phase 15) untouched.

**New files (planner creates):**
- `.github/workflows/release.yml` — tag-push triggered, test→build-push job chain (D-09/D-10/D-11/D-13)
- `docker-compose.override.yml.example` — committed example showing the dev `build:` block + the `coffee-snobbery-test` service (D-05/D-06)
- `CONTRIBUTING.md` — dev content carved out of README (D-14)
- (optional) `.github/workflows/release.yml` may delegate test setup to a reusable workflow; planner's call.

**Pattern files to read before implementing:**
- `Dockerfile` (full file, all three stages) — multi-arch `TARGETARCH` switch already wired (lines 25–42); planner re-uses
- `.github/workflows/ci.yml` (full file) — test gate that release.yml mirrors (Tailwind build step on lines 41–52, pytest invocation lines 60–69 + 71–85 double-run)
- `docker-compose.yml` (full file) — current shape; D-05 transforms it
- `entrypoint.sh` — chown+migrate+gosu sequence already shipped; do NOT modify
- `README.md` (current full file) — the dev/operator mix that gets split
- `.env.example` — current 10-var inventory; cross-checked against `app/config.py`
- `app/config.py` `Settings` class — source of truth for env vars; `test_env_example.py` enforces parity
- `Makefile` — referenced from CONTRIBUTING.md; not modified by Phase 18

### Architectural patterns to follow

- **Single-worker invariant** — `entrypoint.sh` line that runs `exec uvicorn ... --workers 1 --proxy-headers --forwarded-allow-ips="${TRUSTED_PROXY_IPS:-127.0.0.1}"` is sacrosanct. Three-place warning system (entrypoint.sh + scheduler.py + README) survives the README rewrite — keep the audit grep `grep -RIn -E '\-\-workers 1|single worker' README.md entrypoint.sh app/services/scheduler.py` returning ≥3 hits.
- **Tailwind v3 invariant** — builder stage on `v3.4.17`; project memory `tailwind-v3-not-v4`. Release workflow's mirrored Tailwind step uses the same version.
- **CI source-tree vs baked-image divergence** — project memory: `system.py` version path differs between baked image (importlib.metadata works) and CI source tree (importlib.metadata fails). Tag-derived label/build-arg gives a robust fallback (D-12).
- **No `docker compose build` in operator path** — DIST-01 hard rule. The operator-facing `docker-compose.yml` ships with `image:` only after D-05.
- **NPM topology constraints** — `TRUSTED_PROXY_IPS=*` is non-negotiable (project memory `snobbery-vps-npm-reverse-proxy`); shared docker network attach is mandatory; `/sw.js` Cache-Control passthrough is PWA-7 invariant.
- **DIST-06 parity** — `tests/test_env_example.py` enforces `.env.example` ↔ `app/config.py` parity; do not break this test when polishing prose.
- **`.dockerignore` audit** — `.git/`, `.planning/`, `.claude/`, `docs/` already excluded; `docker-compose.override.yml` should also be excluded so the override never leaks into a baked image (planner adds).
- **GHCR auth in release workflow** — `permissions: { contents: read, packages: write }` + `docker/login-action` with `GITHUB_TOKEN` is the standard pattern; no PAT needed.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`Dockerfile` multi-arch wiring** (lines 25–42) — `ARG TARGETARCH` + arch switch (`amd64`/`arm64`) already in the tailwind-builder stage; the runtime stage is pure Python so it's arch-portable. Multi-arch buildx works out of the box; the release workflow just sets `platforms: linux/amd64,linux/arm64`.
- **`.github/workflows/ci.yml`** (full) — the exact test sequence (Tailwind build, ruff format check, ruff lint, pytest with SNOB_CI=1) the release workflow re-runs verbatim. Copy-pasta + adapt.
- **`docker-compose.yml`** `coffee-snobbery-test` profile (lines 89–120) — moves to `docker-compose.override.yml.example` near-verbatim.
- **`entrypoint.sh`** chown+migrate+gosu sequence (Phase 15) — already handles fresh-install boot correctly; DIST-05 is verify-only.
- **`/setup` route** (`app/routers/auth.py:209`) — already redirects authenticated users away from setup and unauthenticated users to it when zero users exist. DIST-05 is verify-only.
- **`/healthz` endpoint** (referenced by HEALTHCHECK in Dockerfile line 127–128) — operator smoke check.
- **README NGINX server-block snippet** (lines 86–135) — preserved verbatim as the plain-nginx secondary path (D-16).
- **README single-worker warning block** (lines 63–84) — preserved through the rewrite; surviving location #3 of the three-place warning system.
- **Makefile targets** (`make up`, `make smoke`, `make logs`, `make test`, etc.) — migrate to CONTRIBUTING.md.

### Established Patterns

- **Three-place single-worker warning system** (entrypoint.sh + scheduler.py + README) — survives the README restructure; audit grep is the verification step.
- **`.env.example` ↔ `app/config.py` parity** enforced by `tests/test_env_example.py` — DIST-06 prose polish must NOT break this test.
- **OCI image labels** — currently absent from Dockerfile. Phase 18 adds the standard set (`org.opencontainers.image.{title,description,url,source,version,revision,licenses}`).
- **`docker/metadata-action` for tag matrix** — the standard pattern for D-03's `v1.2.0 + 1.2 + 1 + latest`. Pre-release filter (D-11) implemented via `flavor: latest=false` on pre-release tags or via a job conditional.
- **`docker/build-push-action` with GHA cache** (`cache-from: type=gha`, `cache-to: type=gha,mode=max`) — speeds up release builds by ~50% on subsequent runs.

### Integration Points

- **`docker-compose.yml`** — the single file that operators interact with. D-05 transformation is the load-bearing change.
- **`.github/workflows/`** — adds `release.yml`; `ci.yml` untouched.
- **README.md / CONTRIBUTING.md** — content carve-out; README becomes operator-facing, CONTRIBUTING.md becomes dev-facing.
- **`app/system.py`** — version display. D-12 reconciles the tag-derived label with the existing importlib.metadata fallback (project memory).
- **`Dockerfile` runtime stage** — adds OCI labels and (optionally) `ARG APP_VERSION`; no functional change.
- **No app router / model / template / analytics changes** — Phase 18 is packaging + docs, not features. Stay out of `app/routers/`, `app/templates/`, `app/services/` (except the version path in `system.py`).
- **No scheduler / encryption / search / brew / cafe / AI changes** — APScheduler untouched, encryption untouched, AI surfaces untouched.

</code_context>

<specifics>
## Specific Ideas

- **GHCR path is `ghcr.io/jheikkila54/coffee-snobbery`** (D-01) — repo-owner-matches-image-name; not a separate org.
- **Public visibility** (D-02) — `docker pull` works without auth; matches "self-hostable by others."
- **`v1.2.0 + 1.2 + 1 + latest` tag scheme on stable** (D-03) — full menu, operators choose pin tightness.
- **Pre-release tags publish under exact tag only** (D-11) — `latest`/`1.2`/`1` never updated on `-rc1`/`-beta1`. Production floating-on-latest is safe by construction.
- **`docker-compose.override.yml` (gitignored) holds the dev `build:` block** (D-05) — compose auto-merges; zero ceremony for John, zero footgun for operators.
- **`docker-compose.override.yml.example` is committed** — visible documentation of the dev pattern without enabling it by default.
- **Operator's first-run command is the single line `docker compose up -d`** (D-08) — compose pulls implicitly; README quickstart is exactly two steps (cp + edit .env, then up -d).
- **Tag-push `v*` is the only release trigger** (D-09) — no GitHub Release UI, no workflow_dispatch fallback. Single-step release: `git tag v1.2.0 && git push --tags`.
- **Release workflow re-runs the full test gate** (D-10) — eliminates "tagged a flaky commit and shipped it."
- **Version source is `github.ref_name`, stamped into image labels and `app/system.py`** (D-12) — no VERSION file; tag IS version.
- **README rewrite: self-host first, dev moves to CONTRIBUTING.md** (D-14) — operator-facing README opens with the quickstart.
- **NPM walkthrough = field-list + gotchas, no screenshots** (D-15) — maintainable; UI-shift-resilient.
- **Plain-nginx kept as secondary; Caddy/Traefik out of scope** (D-16) — focus on the deployment shape John actually uses.
- **Upgrade = `edit tag → pull → up -d`** (D-19) — explicit three-line copy-paste, matches the pin-to-semver default in D-04.
- **DIST-05 is verify-only** (D-18) — fresh-install path already works post-Phase 15; the phase asserts it with a smoke test, doesn't rebuild it.

</specifics>

<deferred>
## Deferred Ideas

- **Image signing with cosign / Sigstore** — overkill for household scale; revisit if a downstream operator requests verification or if a supply-chain incident in the Python ecosystem changes the calculus.
- **SBOM generation (syft / Anchore)** — same reasoning. Add if a future audit requires it.
- **CHANGELOG.md / formal release-notes process** — GitHub Releases UI is sufficient at current cadence. Revisit if release frequency picks up.
- **`upgrade.sh` / `deploy.sh` wrapper scripts** — KISS; three-line `docker compose` workflow stays raw. Add only if operator feedback shows the three lines are a real stumbling block.
- **`workflow_dispatch` manual-rebuild fallback** — if a release build flakes, re-tag is cheap (`git tag -d v1.2.0 && git tag v1.2.0 && git push --tags -f`). Revisit if force-retagging becomes a frequent need.
- **Re-running release workflow via GitHub Release publication trigger** — adds ceremony; rejected. Tag-push is the only canonical path.
- **Caddy / Traefik reverse-proxy walkthroughs** — out of scope for v1.2; add if a self-hoster opens an issue.
- **Docker swarm / k8s deployment topology** — anti-scope; explicitly out per single-worker invariant.
- **GHCR retention automation (auto-deleting old untagged images)** — call out as a manual periodic task in CONTRIBUTING.md; full automation deferred.
- **Removing the `/admin` link from top-nav (≥768px)** — Phase 17 D-18 punt; not Phase 18 scope.
- **VPS-side automation (Ansible / systemd-unit pattern / unattended-upgrades)** — operator's choice; out of scope for the repo.
- **GHCR Docker Hub mirror** — single-registry is fine; mirror to Docker Hub only if a downstream operator's network blocks ghcr.io.

None of the above are dropped — each is captured for a future iteration if/when triggered.

</deferred>

---

*Phase: 18-self-host-packaging*
*Context gathered: 2026-05-28*
