---
phase: 5
slug: brew-sessions
status: verified
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-19
validated: 2026-05-20
---

# Phase 5 — Validation Strategy

> Per-phase validation contract. Audited post-execution against the implemented test suite.
> Every automatable requirement has a green automated test; remaining items are documented manual-only / deferred.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 + pytest-asyncio (installed at test time per CLAUDE.md — not baked into prod image) |
| **Config / fixtures** | `tests/conftest.py` — forces a dedicated `<db>_test` database (rewrites `DATABASE_URL`/`POSTGRES_DB`, refuses to run unless "test" is in the DB name), `_provision_test_db` creates+migrates it once/session, autouse `fresh_db` TRUNCATE between tests |
| **Brew subset command** | `docker compose exec coffee-snobbery python -m pytest -q tests/services/test_brew_*.py tests/routers/test_brew_*.py tests/ci/test_no_unsafe_jinja.py` |
| **Full suite command** | `docker compose exec coffee-snobbery python -m pytest -q` |
| **Measured runtime** | brew subset: **72 tests, ~10s** (2026-05-20, in-container against `snobbery_test`) |

> Note: the image has no source bind-mount. To exercise uncommitted/just-changed code, `docker compose cp tests/ app/ coffee-snobbery:/app/...` before running, or rebuild.

---

## Sampling Rate

- **After every task commit:** Run the brew subset (`tests/services/test_brew_*.py tests/routers/test_brew_*.py`)
- **After every plan wave:** Run the full suite
- **Before `/gsd-verify-work`:** Full suite green + `tests/ci/test_no_unsafe_jinja.py` green (no `|safe`, no `hx-on:`, no `hx-vals='js:'` across **all** of `app/templates/`)
- **Max feedback latency:** ~10s for the brew subset

---

## Per-Task Verification Map

> Audited 2026-05-20 against the implemented suite. All rows COVERED + green except the inherently-manual / Phase-12-deferred MOB rows.

| Req | Behavior (proof) | Test Type | Test (file::function) | Status |
|-----|------------------|-----------|------------------------|--------|
| BREW-01 | `extraction_yield_pct` is GENERATED: insert dose/yield/tds → DB read-back returns computed EY; NULL when any input NULL; INSERT cannot set it | integration | `tests/services/test_brew_schema.py::test_extraction_yield_generated`, `::test_extraction_yield_null_when_input_null`, `::test_ey_not_writable` | ✅ green |
| BREW-01 | EY overflow (>100%) rejected at schema + CSV-row + router (200 not 500) | unit/integration | `test_brew_schema.py::test_brew_create_rejects_ey_overflow`, `::test_brew_csv_row_rejects_ey_overflow`, `tests/routers/test_brew_router.py::test_ey_overflow_returns_200_not_500` | ✅ green |
| BREW-01 | `flavor_note_ids_observed` ARRAY round-trips (`list[int]` → `list[int]`) | integration | `tests/services/test_brew_schema.py::test_observed_notes_array` | ✅ green |
| BREW-04 | Rating Decimal validates 0/1.75/2.5/5; rejects 5.5 and non-0.25 steps | unit | `tests/services/test_brew_schema.py::test_rating_decimal_steps` | ✅ green |
| BREW-02, BREW-05 | Form POST valid → insert; invalid → 200 + fragment with field errors (SEC-06) | integration (TestClient) | `tests/routers/test_brew_router.py::test_form_validation_200` | ✅ green |
| BREW-03, BREW-04, BREW-05 | EY/ratio readout NOT submitted/written (EY GENERATED; ratio has no column) | unit/integration | `tests/services/test_brew_schema.py::test_ey_not_writable`, `tests/routers/test_brew_router.py::test_ey_not_writable` | ✅ green |
| BREW-02 | `user_id` server-set on create (mass-assignment defense) | integration | `tests/routers/test_brew_router.py::test_create_sets_user_id` | ✅ green |
| BREW-09 | `/brew/new?from={id}` prefills all-but `rating`/`notes`/`observed` | integration | `tests/services/test_brew_prefill.py::test_brew_again_blanks_per_attempt`, `tests/routers/test_brew_router.py::test_brew_again_blanks_per_attempt` | ✅ green |
| BREW-02 | Prefill source resolution: D-04 last session, D-05 recipe-wins, D-06 newest-open-bag, hybrid + edge cases | integration | `tests/services/test_brew_prefill.py` (test_d04_*, test_d05_*, test_d06_*, hybrid/finished-bag) | ✅ green |
| BREW-02 | Prefill is user-scoped (no cross-user leak); unknown coffee → blank; requires auth | integration | `tests/services/test_brew_prefill.py::test_brew_again_is_user_scoped`, `tests/routers/test_brew_router.py::test_prefill_user_scoped`, `::test_prefill_unknown_coffee_blank`, `::test_prefill_requires_user` | ✅ green |
| BREW-06, BREW-07 | Draft upsert keeps one row / latest payload; get; clear; per-user isolation; server draft surfaced in `/brew/new` | integration | `tests/services/test_brew_drafts.py` (6), `tests/routers/test_brew_router.py::test_draft_upsert_one_row`, `::test_draft_per_user`, `::test_brew_new_includes_server_draft` | ✅ green |
| BREW-07 | Draft autosave + clear are CSRF-enforced (not exempt) | integration | `tests/routers/test_brew_router.py::test_draft_requires_csrf` | ✅ green |
| BREW-11 | CSV import: refused / skipped-duplicate / inserted outcomes; single transaction (no partial commit); observed-note autocreate rolls back on later failure | integration | `tests/services/test_brew_csv.py::test_import_outcomes`, `::test_import_single_transaction`, `::test_import_autocreates_observed_notes`, `::test_import_observed_note_autocreate_rolls_back_on_later_failure`, `tests/routers/test_brew_list_csv.py::test_import_outcomes_http` | ✅ green |
| BREW-11 | Import is CSRF-enforced; oversized upload rejected before buffering (W-01) | integration | `tests/routers/test_brew_list_csv.py::test_import_requires_csrf`, `::test_import_oversized_content_length_rejected` | ✅ green |
| BREW-10 | CSV export resolves ids→names, includes ratio + EY, re-imports cleanly (round-trip); formula-injection prefix (T-05-13) | integration | `tests/services/test_brew_csv.py::test_export_resolves_names`, `::test_export_includes_ratio_and_ey`, `::test_export_roundtrip`, `::test_export_formula_injection_prefix` | ✅ green |
| BREW-10 | Sessions list scoped to current user only (IDOR defense); fragment-vs-page; filters; cross-user edit → 404; export attachment | integration | `tests/services/test_brew_sessions_service.py::test_list_user_scoped`, `::test_list_filters`, `tests/routers/test_brew_list_csv.py::test_list_user_scoped`, `::test_list_fragment_vs_page`, `::test_list_filters`, `::test_export_attachment`, `tests/routers/test_brew_router.py::test_edit_404_cross_user` | ✅ green |
| BREW-01 | `equipment.usage_count`: +1 on create, diff on edit (incl. null↔value), -1 on delete, across 3 FKs | unit/integration | `tests/services/test_brew_sessions_service.py::test_usage_count`, `::test_usage_count_null_to_value_and_value_to_null`, `::test_create_writes_user_scoped_row` | ✅ green |
| CSP | brew templates (pages **and** fragments) have no `\|safe`, no `hx-on:`, no `hx-vals='js:'`/`hx-headers='js:'` | static grep | `tests/ci/test_no_unsafe_jinja.py` (scans all of `app/templates/` after W-02; 43 templates pass) | ✅ green |
| MOB-05, MOB-06 | No brew input font-size <16px; `inputmode`/`type` matrix; no iOS focus-zoom at 375px | static grep + Playwright | Playwright 375px assertion **deferred to Phase 12 (TEST-06)**; interim manual + grep | ⏭ deferred / manual |

*Status: ✅ green · ⏭ deferred · 🖐 manual-only*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| No iOS Safari focus-zoom on any brew input | MOB-06 | Real-device / Playwright-at-375px behavior; formal Playwright suite is Phase 12 (TEST-06) | At 375px, focus each input; confirm no viewport zoom. |
| Tap-on-stars quarter/half/full feel + hit-slop | BREW-04 | Touch ergonomics not unit-testable; ~28px half-zones are a recorded deviation from 44px (D-03), human-approved at the Task-3 checkpoint | On a phone, tap each star's left/right half; confirm 0.5 increments register reliably. |
| <30s log of session N+1 (core-value gate) | BREW-02 | End-to-end human timing | Open `/brew/new` with one prior session; confirm prefill; fill only rating + notes; submit; time it. |
| Client-side draft reconciliation (localStorage primary, server backstop) | BREW-07 | Browser localStorage + Alpine behavior; server-side upsert/get/clear is automated above | On two devices, start a draft on one; confirm restore-notice logic and that submit/Discard clears both stores. |

---

## Validation Audit 2026-05-20

| Metric | Count |
|--------|-------|
| Requirements audited | 17 rows (13 BREW + CSP + MOB) |
| Automatable gaps found | 0 |
| Resolved (tests filled) | 0 (all pre-existing) |
| Escalated to manual-only | 0 |
| Brew test subset result | **72 passed** (~10s, in-container vs `snobbery_test`) |

No automatable gaps: every BREW/CSP requirement maps to a green automated test. MOB-05/06 Playwright is deferred to Phase 12 (TEST-06) per the original plan; touch-ergonomics, human-timing, and client-side draft reconciliation are inherently manual and documented above. Auditor spawn skipped (no gaps to fill).

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify (or documented manual-only / Phase-12 deferral)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 complete — full brew test suite exists and runs green
- [x] No watch-mode flags
- [x] Feedback latency < 60s (measured ~10s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-05-20 — 72/72 brew tests green; manual-only items documented.
