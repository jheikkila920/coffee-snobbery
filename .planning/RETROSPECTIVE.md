# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.1 — Initial Release

**Shipped:** 2026-05-25
**Phases:** 15 (0–14) | **Plans:** 93 | **Commits:** 576 | **Span:** 9 days

### What Was Built
- The complete self-hosted household coffee log: hardened two-container stack (Postgres 16 + FastAPI behind NGINX), full auth + security posture (argon2id, nonce-CSP, CSRF, MultiFernet-encrypted keys), shared catalog + per-user brew logging.
- The AI differentiator: provider-agnostic service with three-tier web-search coffee recommendation, verified buy URLs, SSRF-hardened fetchers, and signature-based nightly regeneration for cost control.
- Admin + scheduler + search + an installable PWA (Guided Brew Mode, dark mode), backed by ~25.8k LOC of tests, Playwright responsive smoke, and CI — plus a post-launch UX-fix pass (Phase 13) and a Codex audit-remediation pass (Phase 14).

### What Worked
- **Schema bets up front paid off.** `bags`, `wishlist_entries`, refractometer columns, and AI cost-observability columns landed in the first migration set, so later phases never needed a painful retrofit.
- **Rigid horizontal-layer ordering held.** Middleware → auth → encryption → catalog → sessions → analytics → AI was a clean dependency chain; each phase had what it needed.
- **Load-bearing cost-control design survived to ship.** Signature-based regen + single-worker + advisory locks stayed intact through 15 phases.
- **A second AI did real work.** The Codex audit (Phase 14) surfaced a genuine CRITICAL (last-admin `FOR UPDATE`-on-aggregate crash, proven live) and a real SSRF gap — independently verified before fixing, with overstated findings correctly rejected.

### What Was Inefficient
- **Human verification debt accumulated silently.** Several phases shipped with `human_needed` verification and partial UAT (Phases 01/02/07/09/10/11) that never got worked down — the milestone closed with acknowledged debt rather than clean gates. Running a solo build, the manual gates were the easiest thing to skip.
- **"Green" sometimes wasn't.** Executor SUMMARYs called suites green when tests `pytest.skip`ped on missing seed data, and executors committed without running ruff (CI gates both `format --check` and `check`) — repeated cleanup before pushes.
- **Doc/runtime drift cost debugging time.** Service-worker SWR caching made rebuilds invisible in the browser during UI checks; project docs implied Tailwind v4 when the build is v3. Both burned investigation cycles.
- **Windows + GSD worktrees fought each other.** Stale `.git/index.lock` and locked worktrees needed manual clearing before merges.

### Patterns Established
- `commit_docs: false` means `gsd-sdk query commit` refuses all doc commits — planning docs (STATE/ROADMAP/VERIFICATION/etc.) are staged and committed manually.
- Baked image, no source bind-mount: any template/CSS/JS change needs a rebuild or `docker compose cp` before it's exercised in-container; Jinja caches templates in-process.
- Run the full suite with `-rs` and treat skips as gaps, not passes. Drop `snobbery_test` before a full run to dodge cross-module isolation pollution (T-INFRA-1).
- Run both `ruff format --check` and `ruff check` and commit a `style()` pass before pushing a phase — CI gates both.
- SW cache name is content-deterministic (bumps on template/CSS/JS change); for live UI verification have the user "Clear site data," not just "Bypass."

### Key Lessons
1. **Make human gates first-class, not optional.** On a solo build, UAT and `human_needed` verification are the first things to slip and the last to get caught. Schedule them into the phase, or accept up front that the milestone ships with debt — but decide consciously, don't drift into it.
2. **Trust the code over the SUMMARY for "green."** Skips, un-run linters, and stale browser caches all produce false-green. Verify at the level that actually runs.
3. **A second auditor (Codex) earns its keep — if findings are independently verified.** It found a real live CRITICAL; it also overstated several items. The discipline that made it valuable was confirming each finding against code + live DB + tests before acting.

### Cost Observations
- Model mix: not tracked this milestone.
- Sessions: not tracked precisely; build spanned 9 days (2026-05-16 → 2026-05-25).
- Notable: zero-dependency choices held (hand-rolled session store, tag input, PWA service worker, backup via `pg_dump` subprocess) — kept the frontend/runtime footprint small and npm-free as specified.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.1 | 15 | 93 | Baseline — GSD plan→execute→verify→ship→complete loop established |

### Cumulative Quality

| Milestone | Tests (LOC) | Verification gates clean | Zero-Dep Additions |
|-----------|-------------|--------------------------|--------------------|
| v1.1 | ~25,800 | No — 6 phases `human_needed`, UAT partial on 4 (deferred) | session store, tag input, SW/manifest, backup, rating control |

### Top Lessons (Verified Across Milestones)

1. *(v1.1)* Human verification gates slip silently on solo builds — make them explicit or acknowledge the debt deliberately. (Re-test this trend next milestone.)
