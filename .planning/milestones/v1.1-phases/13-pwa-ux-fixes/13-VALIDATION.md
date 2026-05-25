---
phase: 13
slug: pwa-ux-fixes
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-24
updated: 2026-05-25
audited: 2026-05-25
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
| 13-01-01 | 01 | 1 | C9 | T-13-03 | SW always renders a valid CACHE_NAME | unit/route | `... tests/test_pwa.py -rs` | ✅ | ✅ green |
| 13-01-02 | 01 | 1 | C9 | T-13-01/02/03 | build_id.txt drives cache key | unit/route | `... tests/test_pwa.py -rs` | ✅ | ✅ green |
| 13-01-03 | 01 | 1 | C9 (GATE) | — | cache key changes per build | manual (two-build) | n/a — human-verify | n/a | ✓ human-approved |
| 13-02-01 | 02 | 1 | C10 / D-07 | T-13-04 | aspect-safe crop / correct icon dims | static (PIL dims) | `... tests/test_pwa_icons.py -rs` (NEW) | ✅ | ✅ green |
| 13-02-02 | 02 | 1 | C10 / D-07 | T-13-05 | manifest icon refs intact | route+PIL | `... tests/test_pwa_icons.py -rs` (NEW) | ✅ | ✅ green |
| 13-02-03 | 02 | 1 | C10 | — | full mascot, undistorted | manual (visual) | n/a — human-verify | n/a | ✓ human-approved |
| 13-03-01 | 03 | 1 | C2 / D-03/D-04 | T-13-06/07 | CSRF + mass-assign preserved | route | `... tests/routers/test_equipment_create_fragment.py -rs` | ✅ | ✅ green |
| 13-03-02 | 03 | 1 | C2, C3 | T-13-06/08 | OOB list update (CR-01 rework) | route + static | `... -k equipment` | ✅ | ✅ green |
| 13-03-03 | 03 | 1 | C2 | T-13-06/08 | OOB list update (CR-01 rework) | route + static | `... -k coffee` | ✅ | ✅ green |
| 13-04-01 | 04 | 1 | C6 | T-13-09 | no eval/x-model; role=switch gone | static (template) | `... tests/templates/test_guided_brew_controls.py -rs` (NEW) | ✅ | ✅ green |
| 13-04-02 | 04 | 1 | C7a | T-13-09 | CSP-safe resync | static (template) | `... tests/templates/test_guided_brew_controls.py -rs` (NEW) | ✅ | ✅ green |
| 13-04-03 | 04 | 1 | C7b | — | tap targets >=44px / flex-nowrap | static (template) | `... tests/templates/test_guided_brew_controls.py -rs` (NEW) | ✅ | ✅ green |
| 13-04-04 | 04 | 1 | C6, C7a, C7b | T-13-09/10 | — | manual (375px) | n/a — human-verify | n/a | ✓ human-approved |
| 13-05-01 | 05 | 1 | C4 / D-01 | T-13-12 | no eval/x-model | static (check_c4_dark.py) | `... tests/test_c4_dark_checker.py -rs` (NEW, gates checker) | ✅ | ✅ green |
| 13-05-02 | 05 | 1 | C4, C1 / D-01/D-02 | T-13-11/12 | nonce'd no-FOUC, no unsafe-inline | static (check_c4_dark.py --templates) | `... tests/test_c4_dark_checker.py -rs` (NEW, gates checker) | ✅ | ✅ green |
| 13-05-03 | 05 | 1 | C1, C4 | T-13-11 | CSP/|safe guards still pass | CI grep | `... tests/ci/ -rs` | ✅ | ✅ green |
| 13-05-04 | 05 | 1 | C4, C1, D-02 | T-13-11/12/13 | Light-on-dark override; login dark; iOS top | manual (375px + on-device) | n/a — human-verify | n/a | ⚠️ approved; C1 iOS on-device UNVERIFIED (see audit) |
| 13-06-01 | 06 | 2 | C5 / D-05 (mandated) | — | real branch assertions | template render | `... tests/templates/test_recipe_row.py -rs` | ✅ | ✅ green |
| 13-06-02 | 06 | 2 | C5 / D-05 | — | guided-brew reach | static (grep) | `python -c "...Guided Brew /recipes..."` | ✅ | ✓ verified structurally (home/sessions links) |
| 13-06-03 | 06 | 2 | C8 / D-06 | T-13-14/15/16 | CSRF + require_user preserved | route | `... tests/routers/test_brew_list_csv.py tests/routers/test_brew_router.py -rs` | ✅ | ✅ green |
| 13-06-04 | 06 | 2 | C5, C8 | T-13-14/15 | — | manual (nav) | n/a — human-verify | n/a | ✓ human-approved |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky · ✓ human-approved (tracked in 13-VERIFICATION.md)*

**CR-01 rework note (C2/13-03):** The shipped C2 fix differs from the 13-03-SUMMARY. After code-review finding CR-01 (a validation-error regression in the original "return list fragment + retarget form to `#…-list`" approach), the implementation was reworked to keep `form_target="#…-form-mount"` and update the list via `equipment_create_success.html` / `coffee_create_success.html` with `hx-swap-oob="innerHTML"`. `test_equipment_create_fragment.py` now has **4** tests (success + invalid-input for both entities). 13-VERIFICATION.md reflects the final code; the SUMMARY is stale.

Sampling continuity: no run of 3 consecutive automation-feasible tasks lacks an `<automated>` verify. The manual checkpoints (13-01-03, 13-02-03, 13-04-04, 13-05-04, 13-06-04) are genuinely non-automatable (two-build cache gate, image content, 375px layout/Alpine reactivity, no-FOUC timing, iOS on-device) and each is bracketed by automated tasks.

---

## Wave 0 Requirements

Planned-at-design (all delivered during execution):

- [x] `tests/test_pwa.py` — EXTEND: `test_sw_cache_name_is_versioned` + `test_build_hash_prefers_build_id_txt` (C9, Plan 01).
- [x] `tests/routers/test_equipment_create_fragment.py` — NEW: equipment + coffee create render the list (OOB after CR-01 rework); 4 tests incl. invalid-input path (C2, Plan 03).
- [x] `tests/templates/test_recipe_row.py` — NEW: recipe_row enabled-vs-no-steps for mode card+row (C5 mandated, Plan 06).
- [x] `scripts/check_c4_dark.py` — NEW: structural checker for the C4/C1 string-level acceptance criteria (Plan 05, created in 05-01; reusable + CI-friendly).

Added during validation audit (2026-05-25) — converted one-shot inline checks into persistent regression tests:

- [x] `tests/test_pwa_icons.py` — NEW: 5 committed icon PNG dimensions (Pillow) + manifest icon-ref integrity via TestClient (C10, Plan 02). 6 tests green.
- [x] `tests/templates/test_guided_brew_controls.py` — NEW: no role=switch + toggleChime/toggleVibrate + no x-model (C6); setDose/setWater + x-init + no x-model (C7a); flex-nowrap star row (C7b). 10 tests green.
- [x] `tests/test_c4_dark_checker.py` — NEW: subprocess-wraps `check_c4_dark.py` default + `--templates`, asserts exit 0 — wires the previously-ungated checker into the suite (C4/C1, Plan 05). 2 tests green.

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

## Validation Audit 2026-05-25

State A audit of the as-shipped phase against this contract (phase complete; 13-VERIFICATION.md = 9/9 structural, full suite 965 pass / 0 fail).

| Metric | Count |
|--------|-------|
| Gaps found | 3 |
| Resolved | 3 |
| Escalated | 0 |

**Gaps closed (automatable behaviors that had only one-shot inline verification, no persistent regression test):**

1. **C10** (Plan 02) — icon dims + manifest icon-ref integrity were verified by an inline `python -c` PIL check that left no test. → `tests/test_pwa_icons.py` (6 tests).
2. **C6/C7** (Plan 04) — cue controls / ratio re-sync / star-row nowrap were verified by inline grep. → `tests/templates/test_guided_brew_controls.py` (10 tests).
3. **C4/C1** (Plan 05) — `check_c4_dark.py` passed but nothing invoked it (ungated; latent skip-as-green). → `tests/test_c4_dark_checker.py` (2 tests) wires both modes into the suite.

18 new tests, all green in the baked `coffee-snobbery-test` image (`docker compose run --build --rm coffee-snobbery-test ... -rs --tb=short` → 18 passed, 0 skipped, 0 failed). New files ruff format + check clean.

**Residual manual items (genuinely non-automatable; tracked + approved in 13-VERIFICATION.md):** C9 two-build runtime gate, C10 mascot visual, C4 dark visual/no-FOUC/system-override, C4 login always-dark, C6 clarity, C7 375px render, C5/C8 nav flow.

**One honest caveat — C1 iOS top safe-area (13-05-04):** `env(safe-area-inset-top)` evaluates to 0 off-device, so it is structurally present but UNVERIFIED on a real iPhone in standalone mode. It reuses the same unproven technique as the bottom-nav fix (commit 982c0e6). No automated test can close this; it requires on-device confirmation before being trusted.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or are genuine manual checkpoints (no automatable task lacks automation).
- [x] Sampling continuity: no 3 consecutive automatable tasks without automated verify.
- [x] Wave 0 covers all MISSING references (test_pwa extension, test_equipment_create_fragment, test_recipe_row, check_c4_dark.py).
- [x] No watch-mode flags.
- [x] Feedback latency < 120s.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** approved 2026-05-25
