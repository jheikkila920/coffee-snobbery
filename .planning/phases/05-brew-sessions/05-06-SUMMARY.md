---
phase: 05-brew-sessions
plan: 06
subsystem: ui
tags: [htmx, jinja2, tailwind, csv, fastapi, brew-sessions, mobile-first, filters]

# Dependency graph
requires:
  - phase: 05-brew-sessions (plan 02)
    provides: list_brew_sessions(db, *, by_user_id, coffee_id, brewer_id, rating_min, rating_max, date_from, date_to) ordered brewed_at DESC
  - phase: 05-brew-sessions (plan 03)
    provides: csv_io.export_brews (name-resolved, ratio + EY, formula-prefix, round-trip headers) + csv_io.import_brews (resolve/dedup/single-transaction RowOutcomes)
  - phase: 05-brew-sessions (plan 04)
    provides: brew router (require_user gating, GET new/edit + POST create/update + brew-again /brew/new?from={id}), draft routes; route-order convention
  - phase: 05-brew-sessions (plan 05)
    provides: base.html, the brew add/edit form, brew-draft.js Discard affordance (now retargeted to /brew)
  - phase: 04-shared-catalog
    provides: list/fragment HX-Request branch + filter-bar + hx-push-url + responsive table->card conventions (coffees.py / coffee_list/coffee_row/coffee_filters_panel), FragmentCacheHeadersMiddleware
  - phase: 01-middleware
    provides: double-submit CSRF, CSP nonce + |safe ban, Tailwind base layer (tailwind.src.css), FragmentCacheHeadersMiddleware (no-store + Vary: HX-Request)
provides:
  - "GET /brew — per-user sessions list (BREW-10 IDOR-scoped), six filters parsed into parameterized service kwargs, HX-Request -> #session-list fragment vs full page"
  - "GET /brew/export — filtered, name-resolved CSV attachment via csv_io.export_brews (same _parse_list_filters helper as the list, so export == the currently-filtered view)"
  - "GET /brew/import — upload page (before-upload empty state); POST /brew/import — content-type + size guard, single-transaction csv_io.import_brews, per-row result fragment, CSRF-enforced"
  - "pages/sessions.html — filter bar (coffee/brewer native <select>, rating min/max, two date inputs MOB-05), collapsed-by-default native <details> filter panel (both breakpoints), persistent Export CSV + Import + Log CTAs"
  - "fragments/session_list.html — #session-list HTMX target, desktop table -> mobile card collapse at md, zero/filtered-zero empty states, is_fragment-gated hx-swap-oob export-link sync"
  - "fragments/session_row.html — row/card via mode flag; Edit (/brew/{id}/edit) + accent Brew again (/brew/new?from={id}, D-08), locked aria-labels"
  - "fragments/csv_import_results.html — per-row outcome summary (Imported/Skipped/Refused), inserted=neutral+check, skipped=muted, refused=red-700 reason, all autoescaped (no |safe)"
  - "App-wide readable anchor color in tailwind.src.css @layer base (espresso-700 light / espresso-100 dark) — fixes low-contrast bare links app-wide"
affects: [analytics (Phase 6 — home page consumes the sessions list + brew-again entry), global-search (Phase 10 — per-user session-note scoping), pwa-mobile-polish (Phase 11 — bottom nav + card collapse), hardening-tests (Phase 12 — Playwright 375px + |safe grep)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "List/fragment HX-Request branch extended to the brew router: GET /brew returns fragments/session_list.html when request.headers.get('HX-Request')=='true', else pages/sessions.html — same idiom as coffees.py; FragmentCacheHeadersMiddleware applies no-store + Vary for free"
    - "Single shared filter parser (_parse_list_filters) feeds BOTH the list query and the export query so 'Export CSV' is always exactly the currently-filtered view (D-15) — no filter-logic drift between the two routes"
    - "Native collapsed <details> as the filter panel on ALL breakpoints (CSP-safe, zero JS) — replaces the Phase-4 always-visible bar / Alpine toggle; collapsed by default, ~44px summary on every viewport"
    - "is_fragment context flag, set only on the HX-Request branch, gates the hx-swap-oob export-link anchor so the OOB swap fires during HTMX swaps but never renders a visible duplicate on a full-page {% include %} render"
    - "starlette.datastructures.UploadFile (NOT fastapi.UploadFile) is the runtime type returned by request.form() — the isinstance guard must use the Starlette type or valid uploads are wrongly refused"
    - "Literal /brew/export and /brew/import routes declared BEFORE /brew/{session_id}/* so the path-param route never shadows them"

key-files:
  created:
    - app/templates/pages/sessions.html
    - app/templates/pages/brew_import.html
    - app/templates/fragments/session_list.html
    - app/templates/fragments/session_row.html
    - app/templates/fragments/csv_import_results.html
    - tests/routers/test_brew_list_csv.py
  modified:
    - app/routers/brew.py
    - app/static/css/tailwind.src.css
    - app/static/js/alpine-components/brew-draft.js
    - app/templates/pages/brew_form.html

key-decisions:
  - "Filter panel is a native collapsed <details> available on BOTH desktop and mobile (collapsed by default), per explicit user preference — not the Phase-4 always-visible bar nor an Alpine toggle. CSP-safe, zero JS."
  - "Export-link sync uses an hx-swap-oob anchor gated by an is_fragment flag emitted only on the HX-Request branch — avoids a visible duplicate Export button on full-page load while keeping the swap-time href in sync with live filters."
  - "App-wide readable anchor color lives in tailwind.src.css @layer base and intentionally affects every page (a cross-cutting contrast fix broader than this plan's files)."
  - "Discard-changes target moved from / (home) to /brew (sessions list) — a deliberate cross-plan touch of 05-05-owned files (brew-draft.js, brew_form.html) now that GET /brew exists."
  - "Import isinstance guard uses starlette.datastructures.UploadFile (FastAPI's UploadFile is a subclass; request.form() returns the Starlette type) — caught under TDD before GREEN (Rule-1 bug)."

patterns-established:
  - "Filtered-export-equals-filtered-view: one _parse_list_filters helper shared by GET /brew and GET /brew/export"
  - "is_fragment-gated OOB sync: emit hx-swap-oob targets only when serving the HTMX fragment branch, never on the full-page include"
  - "Collapsed <details> filter panel as the CSP-safe responsive filter affordance"

requirements-completed: [BREW-10, BREW-11, MOB-05]

# Metrics
duration: 2 rounds (initial build + 1 post-checkpoint fix round)
completed: 2026-05-20
---

# Phase 5 Plan 06: Sessions List + CSV Import/Export UI Summary

**The Phase 5 surface closes out: a per-user sessions list at GET /brew (six filters AND-ing through one parameterized service helper, HTMX fragment swaps with hx-push-url, desktop-table/mobile-card collapse), a filter-aware CSV export that downloads exactly the currently-filtered view, a CSV import page with a per-row inserted/skipped/refused outcome summary committed in one transaction, and Edit + "Brew again" on every row — human-verified by John at 375px after two fix rounds, including a collapsed-by-default <details> filter panel on both breakpoints, a filter-tracking export link, an app-wide anchor-contrast fix, and a Discard-returns-to-/brew change.**

## Performance

- **Duration:** 2 rounds (initial build through Task 2, then one post-checkpoint fix round)
- **Completed:** 2026-05-20
- **Tasks:** 3 of 3 (Task 3 = blocking human-verify checkpoint, PASSED — John approved)
- **Files modified:** 10 (6 created, 4 modified)

## Accomplishments

- **List + export + import routes (Task 1, TDD)** in `app/routers/brew.py`, all `require_user`-gated and scoped by `user.id`, with the literal `/brew/export` and `/brew/import` declared before `/brew/{session_id}/*`:
  - `GET /brew` parses the six filters (`coffee_id`, `brewer_id`, `rating_min`, `rating_max`, `date_from`, `date_to`) via `_parse_list_filters`, calls `list_brew_sessions(...)`, and returns `fragments/session_list.html` when `HX-Request == "true"` else `pages/sessions.html` (BREW-10 / T-05-24 IDOR — a second user's sessions never appear).
  - `GET /brew/export` reuses the **same** `_parse_list_filters` helper, calls `csv_io.export_brews(db, by_user_id=user.id, **filters)`, and returns `text/csv` with `Content-Disposition: attachment` — so the download is exactly the currently-filtered view (D-15).
  - `GET /brew/import` renders the upload page; `POST /brew/import` enforces content-type + a size ceiling before buffering, runs `csv_io.import_brews` in one transaction, and renders `fragments/csv_import_results.html` (BREW-11). CSRF-enforced (not exempt).
- **Five templates (Task 2)** per the locked UI-SPEC, reusing Phase-4 catalog conventions: `pages/sessions.html`, `pages/brew_import.html`, `fragments/session_list.html`, `fragments/session_row.html`, `fragments/csv_import_results.html` — CSP-clean (no `|safe`, no inline `hx-on:`, no `x-model`).
- **Human-verify checkpoint (Task 3) PASSED** — John walked all seven checks at a 375px viewport (list scoping, HTMX filter swaps + back-button replay, mobile filter panel, filtered export download, re-import skip-duplicate, refused-unknown-coffee + inserted-new-row, Brew-again-blank + Edit-stored-values) and approved after two fix rounds.

## Task Commits

1. **Task 1: List + export + import routes (TDD)** — `f74246f` (test, RED) → `8e1b77e` (feat, GREEN)
2. **Task 2: sessions list + import templates + result fragment** — `2700699` (feat)
3. **Task 3: human-verify checkpoint** — PASSED (John approved); no code commit (verification gate)

**Post-checkpoint fix round (after the first checkpoint feedback):**
- `c7a9e4d` (fix, 05-06) — app-wide readable anchor color in `tailwind.src.css @layer base` (espresso-700 light / espresso-100 dark) + explicit `dark:` variants + `font-semibold` on the desktop session-row Edit / "Brew again" links (they read near-black on the dark surface before).
- `c925d94` (fix, 05-05) — "Discard changes" now returns to `/brew` (was `/`): `brew-draft.js discardAndLeave()` → `/brew` and the edit-mode discard link `href` → `/brew`.
- `e2da491` (fix, 05-06) — single collapsed-by-default native `<details>` filter panel serving BOTH desktop and mobile (round-1 panel was always-open on md+ with an `md:hidden` toggle, so desktop had no control and the panel never started collapsed); export link now carries the current params so it tracks live filters.
- `a26e7cb` (fix, 05-06) — guard the `hx-swap-oob` export anchor behind a new `is_fragment` flag set only on the HX-Request branch, so the full-page `{% include %}` render keeps the single persistent Export CSV button (the OOB anchor was rendering as a visible duplicate on full-page load).

**Plan metadata:** committed with this SUMMARY + tracking.

## Files Created/Modified

- `app/routers/brew.py` — added `GET /brew` (list + HX-Request fragment branch, six filters), `GET /brew/export` (filter-aware CSV attachment), `GET /brew/import` (upload page), `POST /brew/import` (guarded single-transaction import → result fragment); helpers `_parse_list_filters`, `_raw_filters`, `_session_view_rows`, `_local_dt`, `_brew_ratio`, `_render_import_results`; `from starlette.datastructures import UploadFile`
- `app/templates/pages/sessions.html` — h1 "Sessions"; collapsed `<details>` filter panel (coffee/brewer `<select>`, rating min/max, two `type="date"` inputs — MOB-05) with `hx-get`/`hx-target=#session-list`/`hx-push-url`/`hx-include`; persistent Export CSV `<a>`, Import link, Log primary CTA; mounts `#session-list`
- `app/templates/pages/brew_import.html` — native `<input type="file" accept=".csv,text/csv">` + Import accent button (`hx-post` to `/brew/import`, CSRF hidden field), before-upload empty state, helper copy
- `app/templates/fragments/session_list.html` — `#session-list` target; desktop table (Date/Coffee/Brewer/Recipe/Ratio/Rating/Actions) → mobile card collapse at md; zero / filtered-zero empty states; `is_fragment`-gated `hx-swap-oob` export-link sync
- `app/templates/fragments/session_row.html` — row/card via `mode` flag; Edit `/brew/{id}/edit` + accent "Brew again" `/brew/new?from={id}` (D-08); locked aria-labels; explicit `dark:` link variants
- `app/templates/fragments/csv_import_results.html` — summary line "Imported {N} · Skipped {M} (duplicate) · Refused {K}"; per row inserted=neutral+check, skipped=muted espresso-600, refused=`text-red-700` reason; all reasons autoescaped (no `|safe`)
- `app/static/css/tailwind.src.css` — `@layer base` readable anchor color (light + `prefers-color-scheme: dark`); the existing input-contrast + 16px floor rules stay
- `app/static/js/alpine-components/brew-draft.js` — `discardAndLeave()` navigates to `/brew` (was `/`) (cross-plan, 05-05-owned)
- `app/templates/pages/brew_form.html` — edit-mode "Discard changes" link `href` → `/brew` (was `/`) (cross-plan, 05-05-owned)
- `tests/routers/test_brew_list_csv.py` — `test_list_user_scoped` (BREW-10 IDOR), `test_list_fragment_vs_page`, `test_list_filters`, `test_export_attachment`, `test_import_outcomes_http`, `test_import_requires_csrf`

## Decisions Made

- **Filter panel = native collapsed `<details>` on both breakpoints, per John's explicit preference.** The plan referenced the Phase-4 "mobile-collapse / desktop-always-visible" bar; John wanted filters available AND collapsed by default on both desktop and mobile. A single `<details>` (no `open`, no `md:hidden`) delivers that with zero JS and CSP safety, and the `<summary>` toggle is ~44px on every viewport. The HTMX swap + `hx-push-url` are unchanged.
- **Export link gated by `is_fragment`.** The export `<a>` must update its `href` after each filter swap (so the download always equals the filtered view), but `hx-swap-oob` only acts during an HTMX swap — emitted unconditionally it rendered as a visible duplicate inside the list on full-page loads. Gating the OOB anchor on a new `is_fragment` context flag (set only on the HX-Request branch) keeps one persistent Export button in the page header while still syncing its href on every swap.
- **App-wide anchor-contrast fix in `tailwind.src.css @layer base`.** Tailwind Preflight strips the UA anchor color, leaving bare `<a>` on body inheritance — muted on the light cream surface and near-black (unreadable) on the dark surface. Pinning the accent palette token for both schemes in the base layer fixes every plain anchor app-wide without per-link utilities (utility classes still win by specificity). Cross-cutting by design.
- **Discard returns to `/brew`, not `/`.** With the sessions list now shipped at `GET /brew`, both create- and edit-mode "Discard changes" land there (a fixed target, not `document.referrer`). This touched the 05-05-owned `brew-draft.js` and `brew_form.html` — documented below as a cross-plan touch.
- **Import isinstance guard against `starlette.datastructures.UploadFile`.** `request.form()` returns the Starlette `UploadFile`; FastAPI's `UploadFile` is a subclass, so `isinstance(upload, fastapi.UploadFile)` over the form value wrongly rejected valid uploads. Switched the import to the Starlette type. Caught under TDD before GREEN.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Import wrongly refused valid uploads (wrong UploadFile type)**
- **Found during:** Task 1 (TDD — failing import test before GREEN)
- **Issue:** The import route guarded the uploaded value with `fastapi.UploadFile`, but `request.form()` yields `starlette.datastructures.UploadFile`; FastAPI's class is a subclass, so the `isinstance` check against the FastAPI type failed for genuine uploads and refused them.
- **Fix:** `from starlette.datastructures import UploadFile` and `isinstance(upload, UploadFile)` against the Starlette type.
- **Files modified:** app/routers/brew.py
- **Verification:** `test_import_outcomes_http` / `test_import_requires_csrf` pass; import accepts a real CSV and returns per-row outcomes.
- **Committed in:** `8e1b77e` (Task 1 GREEN)

**2. [Plan-intent deviation] Filter panel as a collapsed `<details>` on both breakpoints**
- **Found during:** Round 2 (post-checkpoint)
- **Issue:** The round-1 panel mirrored the Phase-4 "always-visible on md+, `md:hidden` toggle on mobile" pattern, so desktop had no filter control and the panel never started collapsed — not what John wanted.
- **Fix:** A single native `<details>` (no `open`, no `md:hidden`) serves both desktop and mobile, collapsed by default, CSP-safe, zero JS.
- **Files modified:** app/templates/pages/sessions.html
- **Verification:** Human-verified at the checkpoint (filters available + collapsed by default on both desktop and 375px; HTMX swap + push-url intact).
- **Committed in:** `e2da491`

**3. [Rule 1 - Bug] Export link did not track live filters / OOB anchor rendered as a duplicate**
- **Found during:** Round 2 (post-checkpoint)
- **Issue:** (a) The export link did not carry the active filter params, so a download could include rows outside the filtered view (D-15 violation). (b) After wiring an `hx-swap-oob` anchor to sync the href, it rendered as a visible duplicate Export button on full-page loads because the fragment is `{% include %}`'d and OOB only takes effect during an HTMX swap.
- **Fix:** Export link carries the current query string; the OOB sync anchor is gated by a new `is_fragment` flag emitted only on the HX-Request branch, so the page header keeps one persistent Export CSV button and swaps still update its href.
- **Files modified:** app/routers/brew.py, app/templates/fragments/session_list.html
- **Verification:** Human-verified at the checkpoint (Export downloads exactly the filtered rows; single Export button on the page, href updates after each filter change).
- **Committed in:** `e2da491` (filter tracking), `a26e7cb` (is_fragment gate)

**4. [Rule 1 - Bug] Low-contrast bare anchors app-wide + near-black session-row action links**
- **Found during:** Round 2 (post-checkpoint)
- **Issue:** Tailwind Preflight strips the UA anchor color; bare `<a>` read muted on the light surface and near-black (unreadable) on the dark surface — visibly affecting the session-row Edit / "Brew again" links.
- **Fix:** `@layer base` `a { color: espresso-700 }` (+ hover) with a `prefers-color-scheme: dark` override to espresso-100 in `tailwind.src.css`; explicit `dark:` variants + `font-semibold` on the desktop session-row action links. Cross-cutting by design — repairs bare links on every page.
- **Files modified:** app/static/css/tailwind.src.css, app/templates/fragments/session_row.html
- **Verification:** Human-verified at the checkpoint (Edit / "Brew again" legible in both color schemes).
- **Committed in:** `c7a9e4d`

**5. [Rule 3 - Blocking, cross-plan] Discard target → /brew now that the list exists**
- **Found during:** Round 2 (post-checkpoint)
- **Issue:** "Discard changes" navigated to `/` (home); with the sessions list now shipped at `GET /brew`, John wanted Discard to land on the list, not home.
- **Fix:** `brew-draft.js discardAndLeave()` → `/brew`; edit-mode discard link `href` → `/brew`.
- **Files modified:** app/static/js/alpine-components/brew-draft.js, app/templates/pages/brew_form.html
- **Cross-plan note:** Both files are owned by Plan 05-05 (`files_modified`). This plan touched them because Plan 06 is what makes `/brew` exist as a real destination — a justified cross-plan retarget, not a rewrite. Committed under a `fix(05-05)` scope to reflect the owning plan.
- **Committed in:** `c925d94`

---

**Total deviations:** 5 (1 TDD-caught bug, 1 contrast bug, 1 export/OOB bug, 1 plan-intent UI choice, 1 blocking cross-plan retarget)
**Impact on plan:** All necessary for correctness, the D-15 "export == filtered view" contract, mobile usability, and app-wide legibility. The anchor-contrast fix is intentionally cross-cutting; one cross-plan retarget of 05-05 files (Discard → /brew), documented. No scope creep beyond the planned surface.

## Issues Encountered

- **Two checkpoint rounds.** The first human-verify surfaced four issues: the filter panel had no desktop control and wasn't collapsed by default, the export link didn't track live filters (and the OOB sync anchor duplicated the button on full-page load), bare anchors / session-row action links were low-contrast, and Discard still went home instead of to the new list. Round 2 fixed all four; John approved.
- **REQUIREMENTS bookkeeping note (no action needed).** BREW-10 and BREW-11 were already checked off in `44aeb86` (docs(05-03)) because the ROADMAP attributes them to both the csv_io service plan (05-03) and this UI plan (05-06); MOB-05 was checked in 05-01. The `requirements mark-complete` call here is idempotent.

## Known Stubs

None — the list, filters, export, and import are all wired to real services and verified end-to-end at the checkpoint. No hardcoded empty data sources, no placeholder copy.

## Threat Flags

None — no security surface outside the plan's `<threat_model>`. All six registered threats are mitigated as designed: T-05-24 (list/export scoped by `user.id`; `test_list_user_scoped`), T-05-25 (filters bound through `select()`, never string-formatted), T-05-26 (CSRF enforced on `POST /brew/import`; `test_import_requires_csrf`), T-05-27 (content-type + size guard before buffering), T-05-28 (refused reasons + names autoescaped, no `|safe`), T-05-29 (formula-prefix inherited from the Plan-03 export service).

## Known Follow-ups / Out of Scope (not implemented)

- **TEST-ISOLATION DEFECT (high value, being fixed separately right after this finalization).** `tests/conftest.py` uses `os.environ.setdefault("POSTGRES_DB", "test")`, but the app container already sets `POSTGRES_DB=snobbery`, so `setdefault` is a no-op and the suite runs against the **live app DB**. Its `TRUNCATE users CASCADE` fixture then wipes the admin + `brew_sessions` on every in-container test run. This is why pytest must NOT be run during this finalization. Fix tracked as the immediate next task.
- **Verification test data not committed.** The admin (john) + 2 brew sessions used for the checkpoint were seeded at runtime, not committed as code.
- **Inline "add new coffee" from the brew-form coffee select** remains an out-of-scope enhancement (catalog CRUD is Phase 4 scope) — already captured in the 05-05 follow-ups and STATE.md Accumulated Context.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- **Phase 5 is complete (6/6 plans).** The full brew surface ships: data foundation (P01), services (P02), CSV I/O (P03), form router (P04), form UI (P05), and the sessions list + CSV UI (P06).
- **Phase 6 (Analytics / home page)** can now consume the per-user sessions list, the "Brew again" / "Edit" deep links, and the post-save `GET /brew` redirect target that the create/update success path expects.
- **Recommended immediate follow-up before any further in-container testing:** fix the conftest `POSTGRES_DB` test-isolation defect so the suite stops running against (and wiping) the live DB.

## Self-Check: PASSED

All 10 files exist on disk (6 created: `pages/sessions.html`, `pages/brew_import.html`, `fragments/session_list.html`, `fragments/session_row.html`, `fragments/csv_import_results.html`, `tests/routers/test_brew_list_csv.py`; 4 modified: `app/routers/brew.py`, `app/static/css/tailwind.src.css`, `app/static/js/alpine-components/brew-draft.js`, `app/templates/pages/brew_form.html`). All 7 implementation commits are present in `git log` (`f74246f`, `8e1b77e`, `2700699`, `c7a9e4d`, `c925d94`, `e2da491`, `a26e7cb`). Verified in code: `/brew/export` and `/brew/import` declared before `/brew/{session_id}/*` (route order correct); `_parse_list_filters` shared by GET /brew (line 487) and GET /brew/export (line 531); `from starlette.datastructures import UploadFile` + `isinstance(upload, UploadFile)`; `is_fragment` set on the HX-Request branch and gating the `hx-swap-oob` export anchor in `session_list.html`; `@layer base` anchor-color rule (espresso-700 light / espresso-100 dark) in `tailwind.src.css`; `discardAndLeave()` → `/brew` in `brew-draft.js`; csv_import_results.html refused=`text-red-700` / inserted=neutral / skipped=muted with no `|safe`; all six tests present in `test_brew_list_csv.py`; Task 3 human-verify PASSED (John approved after 2 rounds).

---
*Phase: 05-brew-sessions*
*Completed: 2026-05-20*
