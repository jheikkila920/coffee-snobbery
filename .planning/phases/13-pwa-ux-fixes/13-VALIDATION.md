---
phase: 13
slug: pwa-ux-fixes
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-24
updated: 2026-05-25
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. UAT-sourced; the contract is criteria C1-C10 + decisions D-01..D-07 (no formal REQ-IDs).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (run inside the baked dev/test image — Dockerfile stage 3 `dev`) |
| **Config file** | `pyproject.toml` (pytest section) |
| **Quick run command** | `docker compose run --rm coffee-snobbery-test tests/test_pwa.py tests/routers/test_equipment_create_fragment.py tests/templates/test_recipe_row.py -rs --tb=short` |
| **Full suite command** | `docker compose run --rm coffee-snobbery-test tests/ -rs --tb=short` (e2e ignored by default CMD) |
| **Estimated runtime** | ~60-120 seconds (full suite ~939 pass per memory snobbery-test-gate-runtime) |

Note: production image is pytest-free (CLAUDE.md). Use the `coffee-snobbery-test` dev stage. BAKED tree — no bind-mount; rebuild or `docker compose cp` before exercising changes.

---

## Sampling Rate

- **After every code task commit:** Run the quick command (the plan's own `<verify><automated>`).
- **After every plan wave:** Run the full suite — no new failures vs the pre-phase baseline.
- **Before `/gsd-verify-work`:** Full suite green + the C9 two-build manual gate confirmed.
- **Max feedback latency:** ~120 seconds.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Criterion / Decision | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|----------------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 13-01-01 | 01 | 1 | C9 | T-13-03 | SW always renders a valid CACHE_NAME | unit/route | `... tests/test_pwa.py -rs` | ❌ W0 (extend) | ⬜ pending |
| 13-01-02 | 01 | 1 | C9 | T-13-01/02/03 | build_id.txt drives cache key | unit/route | `... tests/test_pwa.py -rs` | ✅ after 01-01 | ⬜ pending |
| 13-01-03 | 01 | 1 | C9 (GATE) | — | cache key changes per build | manual (two-build) | n/a — human-verify | n/a | ⬜ pending |
| 13-02-01 | 02 | 1 | C10 / D-07 | T-13-04 | aspect-safe crop | static (ast+grep) | `python -c "...crop check..."` | ✅ | ⬜ pending |
| 13-02-02 | 02 | 1 | C10 / D-07 | T-13-05 | manifest icon refs intact | static (PIL dims) | `python -c "...PIL size..."` | ✅ | ⬜ pending |
| 13-02-03 | 02 | 1 | C10 | — | full mascot, undistorted | manual (visual) | n/a — human-verify | n/a | ⬜ pending |
| 13-03-01 | 03 | 1 | C2 / D-03/D-04 | T-13-06/07 | CSRF + mass-assign preserved | route | `... tests/routers/test_equipment_create_fragment.py -rs` | ❌ W0 (new) | ⬜ pending |
| 13-03-02 | 03 | 1 | C2, C3 | T-13-06/08 | list fragment, not row | route + static | `... -k equipment` | ✅ after 03-01 | ⬜ pending |
| 13-03-03 | 03 | 1 | C2 | T-13-06/08 | list fragment, not row | route + static | `... -k coffee` | ✅ after 03-01 | ⬜ pending |
| 13-04-01 | 04 | 1 | C6 | T-13-09 | no eval/x-model; role=switch gone | static (grep) | `python -c "...role=switch check..."` | ✅ | ⬜ pending |
| 13-04-02 | 04 | 1 | C7a | T-13-09 | CSP-safe resync | static (grep) | `python -c "...setDose/setWater..."` | ✅ | ⬜ pending |
| 13-04-03 | 04 | 1 | C7b | — | tap targets >=44px | static (regex) | `python -c "...flex-nowrap..."` | ✅ | ⬜ pending |
| 13-04-04 | 04 | 1 | C6, C7a, C7b | T-13-09/10 | — | manual (375px) | n/a — human-verify | n/a | ⬜ pending |
| 13-05-01 | 05 | 1 | C4 / D-01 | T-13-12 | no eval/x-model | static (check_c4_dark.py) | `python scripts/check_c4_dark.py` | ❌ W0 (executor creates checker) | ⬜ pending |
| 13-05-02 | 05 | 1 | C4, C1 / D-01/D-02 | T-13-11/12 | nonce'd no-FOUC, no unsafe-inline | static (check_c4_dark.py --templates) | `python scripts/check_c4_dark.py --templates` | ✅ after 05-01 | ⬜ pending |
| 13-05-03 | 05 | 1 | C1, C4 | T-13-11 | CSP/|safe guards still pass | CI grep | `... tests/ci/ -rs` | ✅ (exists) | ⬜ pending |
| 13-05-04 | 05 | 1 | C4, C1, D-02 | T-13-11/12/13 | Light-on-dark override; login dark; iOS top | manual (375px + on-device) | n/a — human-verify | n/a | ⬜ pending |
| 13-06-01 | 06 | 2 | C5 / D-05 (mandated) | — | real branch assertions | template render | `... tests/templates/test_recipe_row.py -rs` | ❌ W0 (new) | ⬜ pending |
| 13-06-02 | 06 | 2 | C5 / D-05 | — | guided-brew reach | static (grep) | `python -c "...Guided Brew /recipes..."` | ✅ | ⬜ pending |
| 13-06-03 | 06 | 2 | C8 / D-06 | T-13-14/15/16 | CSRF + require_user preserved | route | `... tests/routers/test_brew_list_csv.py tests/routers/test_brew_router.py -rs` | ✅ (exists, routes unchanged) | ⬜ pending |
| 13-06-04 | 06 | 2 | C5, C8 | T-13-14/15 | — | manual (nav) | n/a — human-verify | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

Sampling continuity: no run of 3 consecutive automation-feasible tasks lacks an `<automated>` verify. The manual checkpoints (13-01-03, 13-02-03, 13-04-04, 13-05-04, 13-06-04) are genuinely non-automatable (two-build cache gate, image content, 375px layout/Alpine reactivity, no-FOUC timing, iOS on-device) and each is bracketed by automated tasks.

---

## Wave 0 Requirements

- [ ] `tests/test_pwa.py` — EXTEND: `test_sw_cache_name_is_versioned` + `test_build_hash_prefers_build_id_txt` (C9, Plan 01).
- [ ] `tests/routers/test_equipment_create_fragment.py` — NEW: equipment + coffee create return the list fragment, not a `<tr>` (C2, Plan 03).
- [ ] `tests/templates/test_recipe_row.py` — NEW: recipe_row enabled-vs-no-steps for mode card+row (C5 mandated, Plan 06).
- [ ] `scripts/check_c4_dark.py` — NEW: structural checker for the C4/C1 string-level acceptance criteria (Plan 05, created in 05-01; reusable + CI-friendly).

Framework already installed (Dockerfile dev stage 3, Phase 12). No new framework install.

---

## Manual-Only Verifications

| Behavior | Criterion | Why Manual | Test Instructions |
|----------|-----------|------------|-------------------|
| SW cache key changes between two real builds | C9 (GATE) | build_id.txt only exists in a baked image; pytest source-tree run sees "dev" | Plan 01 Task 3: two `docker compose build` runs; assert build_id.txt + snobbery-v cache name differ |
| Icon shows full mascot, undistorted, maskable padding | C10 | image content is a visual judgment | Plan 02 Task 3: open logo-badge.png / icon-512.png / icon-512-maskable.png |
| Dark toggle switches with no FOUC; Light wins on dark system; login stays dark | C4 / D-01/D-02 | theme timing + matchMedia + standalone | Plan 05 Task 4: DevTools 375px theme/reload/system-toggle sequence |
| iOS standalone top strip clear of status bar | C1 | env(safe-area-inset-top) = 0 off-device; technique UNVERIFIED (982c0e6) | Plan 05 Task 4: real iPhone installed PWA; if it fails, revise both top + bottom |
| Cue controls read clearly; ratio recalcs on prefill; stars single-line | C6, C7 | Alpine reactivity + 375px layout | Plan 04 Task 4: /brew/guided + /brew/new at 375px |
| Guided Brew reach + Export/Import relocation | C5, C8 | navigation/placement | Plan 06 Task 4 |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or are genuine manual checkpoints (no automatable task lacks automation).
- [x] Sampling continuity: no 3 consecutive automatable tasks without automated verify.
- [x] Wave 0 covers all MISSING references (test_pwa extension, test_equipment_create_fragment, test_recipe_row, check_c4_dark.py).
- [x] No watch-mode flags.
- [x] Feedback latency < 120s.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** approved 2026-05-25
