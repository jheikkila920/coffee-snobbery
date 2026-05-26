# Phase 15: v1.1 Debt Cleanup - Context

**Gathered:** 2026-05-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Close all carried v1.1 debt so v1.2 feature work sits on a clean, verified base.
Five requirements, no new capabilities — this is correctness + verification only:

- **DEBT-01 (G-01):** first deploy writes backups/photos with no manual `chown`
- **DEBT-02 (T-INFRA-1):** `pytest tests/` green twice in a row, zero cross-module isolation failures
- **DEBT-03:** persistent nav + user identity + working sign-out on every authenticated page, on-device verified
- **DEBT-04:** outstanding v1.1 human-UAT scenarios executed and recorded
- **DEBT-05:** outstanding `human_needed` verifications resolved or explicitly re-deferred with a reason

Explicitly NOT in this phase: any nav/IA redesign (Phase 17), any mobile visual rework (Phase 21),
any new feature. If a fix tempts a redesign, stop — it belongs to a later phase.
</domain>

<decisions>
## Implementation Decisions

### DEBT-01 — G-01 chown (entrypoint privilege model)
- **D-01:** Fix the root-owned-named-volume problem with a runtime chown in `entrypoint.sh`. The container must **start as root**, chown `/app/data`, then **drop to the `app` user (UID 1000)** to `exec uvicorn`. This changes the current model where the Dockerfile ends on `USER app` (Dockerfile:122) and the entrypoint never drops privileges.
- **D-02:** Use **`gosu`** as the privilege-drop tool (canonical Debian choice; the official Postgres image uses it for this exact pattern; correct SIGTERM forwarding so uvicorn shuts down cleanly). Add the one apt package to the runtime stage.
- **D-03:** Chown must be **idempotent and cheap**: only run `chown -R app:app /app/data` when `/app/data` is **not already app-owned** (check the dir's owner UID first). First boot fixes the root-owned volume; every later boot is near-zero cost even as the photos volume grows.
- **D-04:** The **single-worker invariant is non-negotiable** — `exec uvicorn ... --workers 1 --proxy-headers --forwarded-allow-ips "${TRUSTED_PROXY_IPS:-127.0.0.1}"` must survive the rewrite unchanged. The three-place single-worker warning system (entrypoint.sh, scheduler.py, README) must stay intact.

### DEBT-02 — Test isolation (T-INFRA-1)
- **D-05:** The documented T-INFRA-1 fix (module-scoped catalog TRUNCATE teardown + `app_settings` cache clear) is **already present** in `tests/conftest.py` (`_reset_catalog_tables`, `_svc._cache.clear()`). Treat this requirement as **prove-and-lock**, not rebuild. **Do NOT rewrite the fixtures** — they carry many safety interlocks (test-DB-name guard, Postgres-reachability probe). Minimal code only.
- **D-06:** **Fix `test_setup_concurrent_race` at the root cause** so it passes deterministically inside a full `pytest tests/` run. It is project memory's lone full-suite failure and is a cross-module ordering/cache-residue artifact, not a feature bug. **Do not** xfail/skip/quarantine it — that contradicts the project's "no pass-by-skip" posture.
- **D-07:** "green twice in a row" means: run `pytest tests/` **twice against the SAME test DB** (residue from run 1 would surface on run 2 = real teardown proof). NOT drop+recreate between runs (that hides residue). Add a **CI guard** so the double-run isolation can't silently regress.

### DEBT-03 — Nav / sign-out
- **D-08:** **Correctness-only.** Guarantee persistent nav + visible user identity + a working sign-out on **every authenticated page**, then verify on a physical device. Sign-out forms already exist (`base.html:161`, `config_hub.html`, `index.html`); this is verify-and-fix-if-broken, not a build.
- **D-09:** **No visual redesign and no IA changes** in this phase. Phase 17 (IA Restructure) and Phase 21 (mobile rework) own nav design — polishing it here is throwaway work.

### DEBT-04 / DEBT-05 — Human-gated closure
- **D-10:** Execution model is **live interactive**: the human-UAT scenarios and `human_needed` verifications are closed **together (John + Claude) during phase execution**, not via a pre-built standalone runbook. Plans should structure this as an interactive on-device session Claude drives and John confirms.
- **D-11:** **Record every outcome.** Even though execution is interactive, each item gets a written result (close-with-evidence or re-defer). Produce/update a verification ledger so closure is auditable, not just a verbal "done."
- **D-12:** **Re-defer with a written reason** for any `human_needed` item that genuinely can't be closed with evidence in this phase — include a target phase. Honest ledger, no hollow green.
- **D-13:** **Fold the safe-area on-device verification (commit `982c0e6`) into the same Phase 15 device session.** STATE.md flags it as a gate for Phases 20 and 21; closing it here in the one device sitting (alongside DEBT-03 nav + the Phase 11/14 UAT) unblocks later phases and means John only picks up the phone once.

### Claude's Discretion
- Exact `gosu` install line / layer placement in the Dockerfile runtime stage (researcher/planner pick), as long as D-01..D-04 hold.
- The precise CI-guard shape for the double-run (D-07) — a CI step vs a pytest marker/assertion — planner's call.
- How the verification ledger is represented (a Phase 15 VERIFICATION.md vs updating each archived phase's record) — planner's call, as long as outcomes are auditable (D-11).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` § "Phase 15: v1.1 Debt Cleanup" — goal + 5 success criteria
- `.planning/REQUIREMENTS.md` lines 14-18 (DEBT-01..DEBT-05) — the precise requirement wording
- `.planning/STATE.md` § "Deferred Items" and § "Blockers/Concerns" — the carried-debt ledger Phase 15 closes; also names the safe-area gate
- `.planning/PROJECT.md` § "Known Gaps (deferred at v1.1 close)" — origin of every debt item

### DEBT-01 (chown) — code to change
- `entrypoint.sh` — current entrypoint; never drops privileges today (the file to rewrite)
- `Dockerfile` — base `python:3.12-slim` (line 67), `useradd app UID 1000` (line 92), build-time `chown -R app:app /app/data` (line 120), `USER app` (line 122); the `docker compose run --rm -u root ... chown` workaround note (lines 113-118) is the manual step this requirement eliminates

### DEBT-02 (test isolation) — code to prove/fix
- `tests/conftest.py` — `_reset_catalog_tables` (module teardown, lines ~419-481), `_svc._cache.clear()` (settings cache), `fresh_db` (users/sessions reset), `_provision_test_db`; the test-DB-name safety interlocks live here
- Target test: `test_setup_concurrent_race` (the lone known full-suite failure)

### DEBT-03 (nav/sign-out) — templates to verify
- `app/templates/base.html` (sign-out form ~line 161), `app/templates/admin_base.html`, `app/templates/pages/config_hub.html` (mobile sign-out), `app/templates/pages/index.html`

### DEBT-04 / DEBT-05 (human-gated) — where the open items are recorded
- `.planning/milestones/v1.1-phases/01-middleware/` — human-UAT (3) + `human_needed`
- `.planning/milestones/v1.1-phases/02-auth/` — human-UAT (1) + `human_needed`
- `.planning/milestones/v1.1-phases/07-ai-services/` — human-UAT (2) + `human_needed`
- `.planning/milestones/v1.1-phases/09-admin/` — partial UAT + `human_needed`
- `.planning/milestones/v1.1-phases/10-global-search/` — `human_needed`
- `.planning/milestones/v1.1-phases/11-pwa-mobile-polish/` — human-UAT (3) + `human_needed` + the nav/sign-out gap that DEBT-03 verifies
- Phase 14 375px search-sheet UAT (search full-screen sheet behavior + p95 latency) — recorded in `.planning/milestones/v1.1-phases/14-audit-remediation/`
- Commit `982c0e6` — the iOS bottom-nav safe-area fix to verify on-device (D-13)

No new external specs introduced during discussion — decisions above are the contract.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tests/conftest.py` already contains the full T-INFRA-1 mechanism (catalog TRUNCATE teardown + settings cache clear) — reuse, don't rebuild.
- Sign-out CSRF POST forms already exist in `base.html`, `config_hub.html`, `index.html` — DEBT-03 verifies coverage rather than authoring sign-out.
- Dockerfile already creates `app` (UID 1000) and a build-time app-owned `/app/data` — the entrypoint just needs the runtime root→chown→drop layer on top.

### Established Patterns
- **Single uvicorn worker** is a hard invariant reinforced in three files; the chown rewrite must preserve the exact `exec uvicorn --workers 1 ...` line (D-04).
- **Test-DB safety interlocks** (`"test" in db_name` guard + 0.5s Postgres reachability probe) gate every destructive fixture; any DEBT-02 change must keep them.
- **`gosu` over su-exec** because the base is Debian glibc (`python:3.12-slim`), not Alpine.

### Integration Points
- `entrypoint.sh` is the only runtime privilege boundary; the chown + drop happens there before `exec uvicorn`.
- CI (`.github/workflows`) is where the DEBT-02 double-run guard attaches.
- The interactive human-gated session (D-10) connects discussion → execution: it's a live step in the Phase 15 plans, not an automated task.
</code_context>

<specifics>
## Specific Ideas

- "Green twice in a row" must use the **same** test DB to actually prove teardown (D-07) — explicitly rejected drop-and-recreate as too weak.
- John picks up the phone **once**: nav (DEBT-03), Phase 11/14 UAT, and safe-area (`982c0e6`) all verified in a single on-device session (D-13).
- chown is conditional on current ownership, not unconditional `-R` every boot (D-03).
</specifics>

<deferred>
## Deferred Ideas

- **Phase 11 visual backlog** — logo-on-every-page, login hero image, cold-start meter position (flagged in project memory). Deferred to Phase 17 (IA Restructure) / Phase 21 (mobile rework); not built in Phase 15.
- **Any nav/IA redesign** — owned by Phase 17.
- **Any mobile visual polish beyond on-device correctness** — owned by Phase 21.

None of the above are dropped — they are captured for the phases that own that surface.
</deferred>

---

*Phase: 15-v1-1-debt-cleanup*
*Context gathered: 2026-05-25*
