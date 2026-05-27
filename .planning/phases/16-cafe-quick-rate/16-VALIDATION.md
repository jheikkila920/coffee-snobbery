---
phase: 16
slug: cafe-quick-rate
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-27
---

# Phase 16 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Generated from RESEARCH.md § "Validation Architecture" (see lines 1467-1525 of `16-RESEARCH.md`).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio + respx (HTTP mock; unused this phase) |
| **Config file** | `pyproject.toml` (no separate `pytest.ini`) |
| **Quick run command** | `docker compose exec coffee-snobbery python -m pytest tests/services/test_cafe_logs.py tests/routers/test_cafe_logs.py -q -x` |
| **Full suite command** | `docker compose exec coffee-snobbery python -m pytest tests/ -q -rs` (drop `snobbery_test` DB before full run per project memory `full-suite-test-isolation-gaps`; `-rs` makes skips visible per `tests-pass-by-skip-mask-green`) |
| **Phase gate** | Run gate against BAKED image — `docker compose build coffee-snobbery && docker compose up -d coffee-snobbery && docker compose exec coffee-snobbery python -m pytest tests/ -q -rs` |
| **Estimated runtime** | Quick: <5s · Per-wave: 10-20s · Full suite: ~3-5 min |

---

## Sampling Rate

- **After every task commit:** Run quick command above.
- **After every plan wave:** Run wave command — `pytest tests/services/test_cafe_logs.py tests/routers/test_cafe_logs.py tests/services/test_analytics.py tests/services/test_photos.py::test_sweep_keeps_cafe_photos -q`
- **Before `/gsd-verify-work`:** Full suite must be green against BAKED image.
- **Max feedback latency:** ~5s (quick) · ~20s (wave) · ~5 min (full).

---

## Per-Task Verification Map

The planner populates the Task ID + Plan + Wave columns below as plans are written. Requirement, test type, and command columns are pre-filled from RESEARCH.md § "Phase Requirements → Test Map".

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | 16-03 | TBD | CAFE-01 | V13/V5 | CSRF token enforced; rejects unknown fields | router unit | `pytest tests/routers/test_cafe_logs.py::test_new_form_renders -x` | ❌ W0 | ⬜ pending |
| TBD | 16-02 | TBD | CAFE-01 | V5 | extra=forbid; minimal payload accepted | router unit | `pytest tests/routers/test_cafe_logs.py::test_create_minimal_payload -x` | ❌ W0 | ⬜ pending |
| TBD | 16-02 | TBD | CAFE-02 | V5 | All enrichment fields validated | router unit | `pytest tests/routers/test_cafe_logs.py::test_create_full_enrichment -x` | ❌ W0 | ⬜ pending |
| TBD | 16-03 | TBD | CAFE-02 | V12 | Bad magic/oversize/bomb → PhotoRejected | router unit | `pytest tests/routers/test_cafe_logs.py::test_photo_rejection_paths -x` | ❌ W0 | ⬜ pending |
| TBD | 16-04 | TBD | CAFE-03 | V4 | tab=cafe fragment renders; visual class present | router unit | `pytest tests/routers/test_cafe_logs.py::test_tab_cafe_renders_list -x` | ❌ W0 | ⬜ pending |
| TBD | 16-04 | TBD | CAFE-03 | — | Blank empty state (D-08) | router unit | `pytest tests/routers/test_cafe_logs.py::test_empty_state_is_blank -x` | ❌ W0 | ⬜ pending |
| TBD | 16-02 | TBD | CAFE-03 | V4 | Cross-user → 404 (non-leak) | router IDOR | `pytest tests/routers/test_cafe_logs.py::test_cross_user_returns_404 -x` | ❌ W0 | ⬜ pending |
| TBD | 16-05 | TBD | CAFE-04 | — | Signature mutates on rated cafe insert | service unit | `pytest tests/services/test_analytics.py::test_signature_includes_cafe_logs -x` | ❌ W0 | ⬜ pending |
| TBD | 16-05 | TBD | CAFE-04 | — | Unrated cafe excluded from signature | service unit | `pytest tests/services/test_analytics.py::test_signature_excludes_unrated_cafe -x` | ❌ W0 | ⬜ pending |
| TBD | 16-05 | TBD | CAFE-04 | — | Origin dim UNIONs brew+cafe | service unit | `pytest tests/services/test_analytics.py::test_preference_profile_origin_unions_cafe -x` | ❌ W0 | ⬜ pending |
| TBD | 16-05 | TBD | CAFE-04 | — | Roaster dim UNIONs brew+cafe | service unit | `pytest tests/services/test_analytics.py::test_preference_profile_roaster_unions_cafe -x` | ❌ W0 | ⬜ pending |
| TBD | 16-05 | TBD | CAFE-04 | — | Process + roast_level stay brew-only | service unit | `pytest tests/services/test_analytics.py::test_preference_profile_process_brew_only -x` | ❌ W0 | ⬜ pending |
| TBD | 16-05 | TBD | CAFE-04 | — | Flavor descriptors UNIONs rated-4+ | service unit | `pytest tests/services/test_analytics.py::test_flavor_descriptors_unions_cafe -x` | ❌ W0 | ⬜ pending |
| TBD | 16-05 | TBD | CAFE-04 | — | Cold-start brew-only threshold | service unit | `pytest tests/services/test_analytics.py::test_cold_start_brew_only -x` | ❌ W0 | ⬜ pending |
| TBD | 16-05 | TBD | CAFE-04 | — | Cold-start cafe-only threshold | service unit | `pytest tests/services/test_analytics.py::test_cold_start_cafe_only -x` | ❌ W0 | ⬜ pending |
| TBD | 16-05 | TBD | CAFE-04 | — | Cold-start mixed brew+cafe | service unit | `pytest tests/services/test_analytics.py::test_cold_start_mixed -x` | ❌ W0 | ⬜ pending |
| TBD | 16-05 | TBD | CAFE-05 | — | get_sweet_spots excludes cafe | service unit | `pytest tests/services/test_analytics.py::test_sweet_spots_excludes_cafe -x` | ❌ W0 | ⬜ pending |
| TBD | 16-05 | TBD | CAFE-05 | — | get_top_coffees excludes cafe | service unit | `pytest tests/services/test_analytics.py::test_top_coffees_excludes_cafe -x` | ❌ W0 | ⬜ pending |
| TBD | 16-02 | TBD | CAFE-06 | V4 | DELETE own log succeeds | router unit | `pytest tests/routers/test_cafe_logs.py::test_delete_own_succeeds -x` | ❌ W0 | ⬜ pending |
| TBD | 16-02 | TBD | CAFE-06 | V4 | DELETE cross-user → 404 (IDOR) | router IDOR | `pytest tests/routers/test_cafe_logs.py::test_delete_cross_user_404 -x` | ❌ W0 | ⬜ pending |
| TBD | 16-03 | TBD | CAFE-06 | — | Edit form renders with stored values | router unit | `pytest tests/routers/test_cafe_logs.py::test_edit_form_renders -x` | ❌ W0 | ⬜ pending |
| TBD | 16-03 | TBD | CAFE-06 | — | layout=desktop renders desktop variant (D-21) | router unit | `pytest tests/routers/test_cafe_logs.py::test_edit_form_desktop_layout -x` | ❌ W0 | ⬜ pending |
| TBD | 16-02 | TBD | CAFE-06 | V4 | Update own log succeeds | router unit | `pytest tests/routers/test_cafe_logs.py::test_update_own_succeeds -x` | ❌ W0 | ⬜ pending |
| TBD | 16-05 | TBD | All | V12 | sweep_orphans keeps cafe photos | service unit | `pytest tests/services/test_photos.py::test_sweep_keeps_cafe_photos -x` | ❌ W0 | ⬜ pending |
| TBD | 16-01 | TBD | All | — | Migration applies on top of p15_1_varietal_m2m | migration smoke | `pytest tests/migrations/test_cafe_logs_migration.py -x` | ❌ W0 | ⬜ pending |
| TBD | 16-04 | TBD | All | — | UAT @ 375px: Quick rate button + tab + form fit viewport | manual UAT | Documented in `16-VERIFICATION.md` | n/a (human) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/services/test_cafe_logs.py` — net-new; covers CAFE-01..06 service-layer (CRUD + photo orchestration)
- [ ] `tests/routers/test_cafe_logs.py` — net-new; covers CAFE-01..03, CAFE-06 router-level (CSRF, IDOR, multipart, layout query param)
- [ ] `tests/services/test_analytics.py` — extend `_seed_analytics_scenario` to include cafe fixtures + add cafe-specific test functions (signature, preference profile, flavor descriptors, cold-start, sweet-spots / top-coffees exclusion)
- [ ] `tests/services/test_photos.py::test_sweep_keeps_cafe_photos` — new test verifying `sweep_orphans` keeps files referenced by `cafe_logs.photo_filename`
- [ ] `tests/migrations/test_cafe_logs_migration.py` — net-new; smoke test the upgrade + downgrade chain on top of `p15_1_varietal_m2m`
- [ ] `_require_cafe_logs_table()` skip-gate helper in `tests/conftest.py` (or local to the new test files) — mirror `_require_analytics_tables()`

*All gaps net-new — no existing test infrastructure covers cafe_logs because the table doesn't exist yet.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Quick rate button visible in /brew header at 375px | CAFE-01 / CAFE-03 | Visual + responsive @ phone viewport | Open `/brew` on a 375px viewport; confirm "Quick rate" button visible in same flex row as Log session + Guided Brew; no horizontal scroll |
| Cafe tastings tab switches lists without page reload | CAFE-03 | Visual + HTMX swap behavior | Click "Cafe tastings" tab; URL updates to `?tab=cafe`; list region swaps; back-button returns to "Sessions" tab |
| Cafe card border-l-2 amber accent + cup icon visible | CAFE-03 / D-07 | Visual differentiation | Compare a cafe card and a brew card on same screen; cafe shows amber left border + cup icon; brew shows espresso accent + kettle icon |
| Empty Cafe tastings tab renders blank (D-08) | CAFE-03 | Deliberate divergence from app's empty-state pattern | Fresh user with zero cafe logs sees blank list, no hint copy, no sample entry |
| Cafe form first viewport: name + rating + Save without scrolling at 375px | CAFE-01 / D-11 | Visual + mobile keyboard | Open `/cafe-logs/new` at 375px; coffee_name autofocuses (keyboard pops); rating + Save visible in first viewport without scrolling |
| Photo upload works on iPhone PWA standalone mode | CAFE-02 | Safe-area + camera capture | Open installed PWA, navigate to /cafe-logs/new, tap photo input, capture photo, verify upload + thumbnail render |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s per wave
- [ ] `nyquist_compliant: true` set in frontmatter (after Wave 0 lands and per-task map is populated by planner)
- [ ] Full suite green twice in a row against BAKED image with `snobbery_test` DB dropped between runs (T-INFRA-1 invariant)

**Approval:** pending (auto-generated 2026-05-27 — planner / verifier promote to approved as plans land)
