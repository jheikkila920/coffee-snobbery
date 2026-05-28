---
phase: 18
slug: self-host-packaging
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-28
---

# Phase 18 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Packaging + docs phase: validators are mostly shell asserts on files/configs, plus the existing `.env.example` parity test. Re-uses the test gate from `.github/workflows/ci.yml` for the release-workflow YAML.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (installed in running container via `requirements-dev.txt`) + shell asserts + `docker compose config` |
| **Config file** | `pyproject.toml` → `[tool.pytest.ini_options]` |
| **Quick run command** | `docker compose exec coffee-snobbery python -m pytest tests/test_env_example.py -x` |
| **Full suite command** | `docker compose run --rm coffee-snobbery-test` (post-D-05: invoked via the dev `docker-compose.override.yml`) |
| **Estimated runtime** | ~10s quick / ~3–4 min full |

---

## Sampling Rate

- **After every task commit:** Run the validator(s) referenced by that task's `<verify>` block (V18-NN shell asserts) plus the quick run command if any code under `tests/test_env_example.py` was touched.
- **After every plan wave:** Run all V18-NN validators for files modified in that wave.
- **Before `/gsd-verify-work`:** All V18-NN validators green; full suite (`coffee-snobbery-test`) green; manual DIST-05 smoke (V18-19, V18-20) executed in a clean volume.
- **Max feedback latency:** ~10 seconds for shell asserts; ~3–4 min for full suite.

---

## Per-Task Verification Map

> Filled in by the planner during PLAN.md generation. Each task in each plan references one or more validator IDs from the Validator Table below in its `<verify>`/`<acceptance_criteria>` block. Planner updates this table per task.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _planner fills_ | _planner_ | _planner_ | DIST-NN | T-18-NN / — | _as applicable_ | shell / pytest / manual | V18-NN | ✅ / ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Validator Table (Nyquist invariants for Phase 18)

| Validator ID | What it checks | Type | Automated Command | Notes |
|-------------|----------------|------|-------------------|-------|
| V18-01 | Compose syntax + image pin (no `build:` block on operator-facing service) | shell | `docker compose -f docker-compose.yml config \| python -c "import sys,yaml; cfg=yaml.safe_load(sys.stdin); svc=cfg['services']['coffee-snobbery']; assert 'build' not in svc; assert 'ghcr.io/jheikkila54/coffee-snobbery' in svc.get('image',''); print('V18-01 OK')"` | D-05; image pin is D-04 |
| V18-02 | `.env.example` ↔ `app/config.py` parity test | pytest | `docker compose exec coffee-snobbery python -m pytest tests/test_env_example.py -x` | Existing test; must remain green after D-17 prose polish |
| V18-03 | Single-worker three-place invariant | shell | `[ "$(grep -RIn -E '\-\-workers 1\|single worker' README.md entrypoint.sh app/services/scheduler.py \| wc -l)" -ge 3 ] && echo OK` | Survives README rewrite per CONTEXT.md `code_context` |
| V18-04 | Release workflow YAML structure | shell | `python -c "import yaml; w=yaml.safe_load(open('.github/workflows/release.yml')); jobs=w['jobs']; assert 'test' in jobs; assert 'build-push' in jobs; assert 'test' in jobs['build-push'].get('needs',[]); print('V18-04 OK')"` | D-10 test-then-push chain |
| V18-05 | Release workflow multi-arch platforms string | shell | `grep -q 'linux/amd64,linux/arm64' .github/workflows/release.yml` | D-13 |
| V18-06 | Release workflow GHCR write permission | shell | `grep -A2 'permissions:' .github/workflows/release.yml \| grep -q 'packages: write'` | Standard GHCR auth |
| V18-07 | Release workflow pre-release filter | shell | `grep -q 'latest=auto' .github/workflows/release.yml` | D-11 — pre-release tags publish exact tag only |
| V18-08 | README required headers present | shell | `for h in 'Quickstart' 'Prerequisites' 'Reverse proxy' 'Upgrade' 'Restore' 'Troubleshooting' 'License'; do grep -q "## $h" README.md \|\| { echo "MISSING: $h"; exit 1; }; done; echo OK` | D-14 |
| V18-09 | README references GHCR image path | shell | `grep -q 'ghcr.io/jheikkila54/coffee-snobbery' README.md` | D-04 / D-19 |
| V18-10 | README NPM walkthrough + `TRUSTED_PROXY_IPS=*` callout | shell | `grep -q 'TRUSTED_PROXY_IPS=\*' README.md` | Non-negotiable per project memory `snobbery-vps-npm-reverse-proxy` |
| V18-11 | README upgrade three-line procedure | shell | `grep -q 'docker compose pull' README.md && grep -q 'docker compose up -d' README.md` | D-19 |
| V18-12 | README GHCR pull-fail troubleshooting entry | shell | `grep -q '403 from ghcr.io' README.md \|\| grep -q 'Image pull fails' README.md` | D-20 |
| V18-13 | CONTRIBUTING.md exists with dev content carve-out | shell | `test -f CONTRIBUTING.md && grep -q 'make smoke' CONTRIBUTING.md && grep -q 'ruff' CONTRIBUTING.md && grep -q 'docker compose cp' CONTRIBUTING.md` | D-14 |
| V18-14 | Dockerfile OCI label set present | shell | `[ "$(grep -c 'org.opencontainers.image' Dockerfile)" -ge 4 ] && echo OK` | D-disc image labels |
| V18-15 | Dockerfile consumes ARG APP_VERSION | shell | `grep -q 'ARG APP_VERSION' Dockerfile` | D-12 version stamp |
| V18-16 | Release workflow passes APP_VERSION build-arg | shell | `grep -q 'APP_VERSION=' .github/workflows/release.yml` | D-12 |
| V18-17 | `.gitignore` excludes `docker-compose.override.yml` | shell | `grep -q '^docker-compose.override.yml$' .gitignore` | D-05 |
| V18-18 | Committed dev override example | shell | `test -f docker-compose.override.yml.example` | D-05 / D-06 |
| V18-19 | DIST-05 smoke: `/healthz` returns ok (clean volume) | manual | See § Manual-Only Verifications below | D-18 |
| V18-20 | DIST-05 smoke: GET `/` redirects to `/setup` with zero users (clean volume) | manual | See § Manual-Only Verifications below | D-18 |

---

## Wave 0 Requirements

- [ ] No new test framework install — pytest already in `requirements-dev.txt`.
- [ ] No new test scaffolding files. Existing `tests/test_env_example.py` covers V18-02 directly.
- [ ] Wave 0 produces nothing for this phase — packaging+docs has no new code paths under test.

*Existing infrastructure covers all phase requirements except the two manual smoke checks (V18-19, V18-20) — see below.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Fresh install `/healthz` returns ok (V18-19) | DIST-05 | Requires clean Postgres volume + container restart to exercise the alembic-on-boot path | `docker compose down -v && docker compose pull && docker compose up -d && sleep 20 && curl -fsS http://localhost:8000/healthz \| grep '"status":"ok"'` |
| Fresh install lands operator at `/setup` (V18-20) | DIST-05 | Requires zero-users state — destructive on a real DB; only safe in a clean volume | After V18-19 sequence above, `curl -fsS -o /dev/null -w '%{http_code} %{redirect_url}\n' http://localhost:8000/` — expect a 302/303 to `/setup` (when zero users) OR fetch `/setup` directly and expect 200 |
| Manual NPM walkthrough end-to-end | DIST-04 | NPM UI is GUI-only; can't be asserted from CI. Operator's "first VPS deploy" is the proof. | Spin up NPM in a sandbox VPS (or staging), follow README NPM section verbatim, confirm cookies are Secure, confirm `/sw.js` cache-control passthrough survives the proxy |
| GHCR first-push public-visibility flip | DIST-02 | One-time package-settings UI action after the first release tag; not automatable from CI | After first `v*` tag push: visit `https://github.com/users/jheikkila54/packages/container/coffee-snobbery/settings`, set visibility = Public, confirm `docker pull ghcr.io/jheikkila54/coffee-snobbery:vX.Y.Z` works without `docker login` |

---

## Validation Sign-Off

- [ ] All tasks have `<verify>` referencing at least one V18-NN validator OR a Wave 0 dependency
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (none expected — existing infra covers)
- [ ] No watch-mode flags in validator commands
- [ ] Feedback latency < 30s for shell asserts; < 5 min for full suite
- [ ] `nyquist_compliant: true` set in frontmatter after the planner wires every task

**Approval:** approved 2026-05-28 (all 11 tasks across 5 plans wire ≥1 V18-NN validator; Wave 0 not required — existing test infra covers)
