# Phase 18: Self-Host Packaging - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-28
**Phase:** 18-self-host-packaging
**Areas discussed:** Registry path/visibility/tags, Compose split, Release CI trigger + scope, Docs structure + NPM depth

---

## Registry path, visibility, tags

### What GHCR path?

| Option | Description | Selected |
|--------|-------------|----------|
| `ghcr.io/jheikkila54/coffee-snobbery` | Matches repo owner exactly; cleanest mental model. | ✓ |
| `ghcr.io/jheikkila54/snobbery` | Shorter image name; diverges from repo name. | |
| `ghcr.io/<other-org>/coffee-snobbery` | Publish under a different GitHub org (e.g., nightingalesupperclub). | |

**User's choice:** `ghcr.io/jheikkila54/coffee-snobbery`
**Notes:** Standard repo-owner/repo-name pattern.

### Visibility?

| Option | Description | Selected |
|--------|-------------|----------|
| Public | Anyone can `docker pull` without auth; matches "self-hostable by others." | ✓ |
| Private | Operators must `docker login ghcr.io` with a PAT. | |

**User's choice:** Public

### Tag scheme on stable release?

| Option | Description | Selected |
|--------|-------------|----------|
| Full semver + `latest` + mutable `1.2` + `1` | v1.2.0 release publishes v1.2.0, 1.2, 1, latest. | ✓ |
| Semver + `latest` only | No mutable major/minor tags. | |
| Semver only — no `latest` | Forces explicit pinning. | |

**User's choice:** Full semver + `latest` + mutable `1.2` + `1`
**Notes:** Operators can pin tight or float on whatever cadence they want.

### Compose `image:` pin?

| Option | Description | Selected |
|--------|-------------|----------|
| Pin to current semver (e.g. `:v1.2.0`) | Bumped at release time; clones get a known-good combo. | ✓ |
| Float on `:latest` | `docker compose pull && up -d` always grabs newest. | |
| Float on `:1` / `:1.2` | Major / major.minor pin. | |

**User's choice:** Pin to current semver
**Notes:** Phase 22 (Verification & Release) bumps the pin to `v1.2.0` when v1.2.0 ships.

---

## Compose split: image-only vs build-aware

### Structure?

| Option | Description | Selected |
|--------|-------------|----------|
| Override file: `docker-compose.yml` (image-only) + gitignored `docker-compose.override.yml` (build) | Compose auto-merges override.yml; zero ceremony for dev, zero footgun for operators. | ✓ |
| Two files: `docker-compose.yml` (operator) + `compose.dev.yml` (`-f` overlay) | Both committed; no gitignored magic. | |
| Single file + `pull_policy: missing` | Brittle; compose-version dependent. | |

**User's choice:** Override-file pattern
**Notes:** `docker-compose.override.yml.example` (committed) documents the dev pattern without enabling it.

### Test service?

| Option | Description | Selected |
|--------|-------------|----------|
| Move `coffee-snobbery-test` to the dev override | Operators never run it; depends on `dev` Dockerfile stage. | ✓ |
| Keep in operator compose under `profiles: [test]` | Profiles already gate it from `up -d`. | |

**User's choice:** Move to dev override

### Makefile?

| Option | Description | Selected |
|--------|-------------|----------|
| Keep Makefile dev-only; operators use raw `docker compose` | Operators on minimal VPSes don't need a Make install. | ✓ |
| Add operator-facing `make` targets | Convenience; extra maintenance surface. | |
| Drop Makefile entirely | KISS; loses `make smoke` as a one-word phase gate. | |

**User's choice:** Keep dev-only; migrate to CONTRIBUTING.md

### Operator's first-run command?

| Option | Description | Selected |
|--------|-------------|----------|
| `docker compose up -d` is the one command (pulls implicitly) | Simplest possible flow. | ✓ |
| Require explicit `docker compose pull` then `up -d` | Two-step; marginally more transparent. | |

**User's choice:** Single `docker compose up -d`

---

## Release CI trigger + scope

### Trigger?

| Option | Description | Selected |
|--------|-------------|----------|
| Git tag `v*` push | Tag IS version source. Simple, scriptable. | ✓ |
| GitHub Release publication | Forces release notes ceremony before publish. | |
| Both tag-push and `workflow_dispatch` | Manual rebuild safety net. | |

**User's choice:** Tag-push only
**Notes:** No GitHub Release ceremony, no workflow_dispatch fallback.

### Test gate?

| Option | Description | Selected |
|--------|-------------|----------|
| Re-run the full test gate inside the release workflow | Defense in depth; ~5–10 min extra. | ✓ |
| Require existing CI green, don't re-run | Faster; trusts the tagged SHA's prior CI run. | |
| Just build + push | Fastest; highest risk of shipping a broken image. | |

**User's choice:** Re-run full gate

### Pre-release tags?

| Option | Description | Selected |
|--------|-------------|----------|
| Publish with exact tag, skip mutable tags | `v1.2.0-rc1` publishes as `:v1.2.0-rc1` only; `latest`/`1`/`1.2` never bumped. | ✓ |
| Skip pre-release tags entirely | Only stable semver triggers publish. | |
| Treat pre-release same as stable | (Rejected — would push pre-release to `:latest`.) | |

**User's choice:** Exact tag only

### Version source?

| Option | Description | Selected |
|--------|-------------|----------|
| Git tag is the only source; workflow uses `github.ref_name` | Single source of truth; no drift. | ✓ |
| VERSION file in repo + tag must match (CI checks) | Extra step; prevents file/tag drift. | |
| Build-arg only, no file/tag dependence | Decouples in-app version from importlib.metadata. | |

**User's choice:** Git tag is the only source
**Notes:** Stamped into image labels + reconciles `app/system.py` version path per project memory `ci-source-tree-vs-baked-image-divergence`.

---

## Docs structure + NPM depth

### Where does the from-zero walkthrough live?

| Option | Description | Selected |
|--------|-------------|----------|
| Rewrite README to lead with self-host; demote dev to CONTRIBUTING.md | Cleanest split; matches what self-hostable apps do. | ✓ |
| Keep README; add a separate DEPLOY.md | Less disruption; README still mixes audiences. | |
| Restructure README only — quickstart on top, dev below | Single file; README gets long. | |

**User's choice:** Rewrite README; dev to CONTRIBUTING.md

### NPM walkthrough depth?

| Option | Description | Selected |
|--------|-------------|----------|
| Field-list + key gotchas, no screenshots | UI-shift-resilient; concise + maintainable. | ✓ |
| Field-list + screenshots | More foolproof initially; rot-prone. | |
| Walkthrough video / GIF | Most visual; highest production cost. | |

**User's choice:** Field-list + gotchas

### Non-NPM reverse proxies?

| Option | Description | Selected |
|--------|-------------|----------|
| NPM primary; plain-nginx snippet secondary; Caddy/Traefik out of scope | DIST-04 explicitly NPM; plain-nginx already in README and works. | ✓ |
| Plain nginx primary; NPM as a tagged-on section | Conflicts with John's actual deployment. | |
| Cover NPM, plain nginx, Caddy, Traefik — full menu | Highest maintenance cost. | |

**User's choice:** NPM primary + plain-nginx secondary; Caddy/Traefik out

### Upgrade walkthrough?

| Option | Description | Selected |
|--------|-------------|----------|
| Edit `image:` tag → `docker compose pull` → `up -d` | Explicit, transparent; matches semver-pin default. | ✓ |
| Float on `:latest` → `pull` → `up -d` | Auto-upgrades; surprise upgrades possible. | |
| Provide an `upgrade.sh` script | Hides what's happening; KISS rejection. | |

**User's choice:** Explicit-tag-bump pattern

---

## Claude's Discretion (planner picks)

- Release workflow file layout (single file with two sequential jobs vs split; recommended: single file)
- `docker/metadata-action` `tags:` exact patterns for the D-03 tag scheme
- Whether to also generate a GitHub Release with auto-generated notes (nice-to-have, if cheap)
- `tailwind-builder` stage GHA cache (`cache-from/to: type=gha`)
- `docker-compose.override.yml.example` exact contents
- CONTRIBUTING.md final structure (Makefile reference, test/lint, fast-iteration tricks, conventional-commits note)
- CLAUDE.md update to reference operator/dev split
- GHCR retention policy (manual periodic cleanup note vs automated step)
- Image label values (`org.opencontainers.image.{title,description,url,source,version,revision,licenses}`)

---

## Deferred Ideas

- Image signing with cosign / Sigstore
- SBOM generation (syft / Anchore)
- CHANGELOG.md / formal release-notes process
- `upgrade.sh` / `deploy.sh` wrapper scripts
- `workflow_dispatch` manual-rebuild fallback
- Re-running release workflow via GitHub Release publication trigger
- Caddy / Traefik reverse-proxy walkthroughs
- Docker swarm / k8s deployment topology
- GHCR retention automation (auto-deleting old untagged images)
- Removing `/admin` link from top-nav (Phase 17 punt, not Phase 18 scope)
- VPS-side automation (Ansible / systemd-unit / unattended-upgrades)
- GHCR Docker Hub mirror

None dropped — each captured for a future iteration if/when triggered.
