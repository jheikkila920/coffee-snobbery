---
phase: 4
slug: shared-catalog
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-18
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Derived from `04-RESEARCH.md` §Validation Architecture and Phase 0–3 test patterns.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio + httpx.AsyncClient (FastAPI TestClient for sync paths) |
| **Config file** | `pyproject.toml` (pytest section) — already configured in Phase 0 |
| **Quick run command** | `docker compose exec coffee-snobbery pytest -q tests/phase_04/ -x` |
| **Full suite command** | `docker compose exec coffee-snobbery pytest -q` |
| **Estimated runtime** | ~25–40 seconds (Phase 4 tests add ~15s; full suite ~30s) |

Test layout follows Phase 0–3 convention:

- `tests/phase_04/test_models_catalog.py` — Mapped[...] roundtrip + constraints
- `tests/phase_04/test_routers_<entity>.py` — HTMX fragment shape, CSRF, 200-on-validation-error
- `tests/phase_04/test_services_photos.py` — magic-byte + Pillow re-encode + EXIF strip + sweep_orphans
- `tests/phase_04/test_schemas_form_validation.py` — Pydantic v2 numeric ranges + HttpUrl
- `tests/phase_04/conftest.py` — fixtures: authed_client, csrf_client, photo_volume (tmp_path), synthetic_jpeg, polyglot_jpeg
- `tests/phase_04/test_migration.py` — Alembic upgrade/downgrade round-trip on fresh DB

---

## Sampling Rate

- **After every task commit:** Run `docker compose exec coffee-snobbery pytest -q tests/phase_04/<closest>.py -x`
- **After every plan wave:** Run the quick command (`tests/phase_04/ -x`)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds (quick) / 120 seconds (full)

---

## Per-Task Verification Map

Synced with the eleven plan files in this phase. Plan IDs and waves below match the frontmatter in `04-NN-PLAN.md` (wave shifts applied per plan-checker B1/B2 revision).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01-wave-0-photos-service | 1 | SEC-07 | T-04-PHOTO | Magic-byte mismatch raises PhotoRejected before Pillow decode | unit | `pytest -q tests/phase_04/test_services_photos.py::test_magic_byte_reject` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01-wave-0-photos-service | 1 | SEC-07 | T-04-EXIF | EXIF removed after re-encode | unit | `pytest -q tests/phase_04/test_services_photos.py::test_exif_strip` | ❌ W0 | ⬜ pending |
| 04-01-03 | 01-wave-0-photos-service | 1 | SEC-07 | T-04-POLY | Polyglot JPEG trailing bytes stripped after re-encode | unit | `pytest -q tests/phase_04/test_services_photos.py::test_polyglot_strip` | ❌ W0 | ⬜ pending |
| 04-01-04 | 01-wave-0-photos-service | 1 | SEC-07 | T-04-DOS | Oversize rejected (>5MB) before buffer; decompression-bomb cap raises PhotoRejected | unit | `pytest -q tests/phase_04/test_services_photos.py::test_size_reject` | ❌ W0 | ⬜ pending |
| 04-01-05 | 01-wave-0-photos-service | 1 | SEC-07 | — | sweep_orphans() unlinks unreferenced files only (FS-first, DB-second ordering) | unit | `pytest -q tests/phase_04/test_services_photos.py::test_sweep_orphans` | ❌ W0 | ⬜ pending |
| 04-02-NN | 02-form-validation-schemas | 2 | SEC-06 | T-04-MASS | Pydantic ValidationError → 200 + form fragment with field errors; extra='forbid' enforced | integration | `pytest -q tests/phase_04/test_schemas_form_validation.py` | ❌ W0 | ⬜ pending |
| 04-03-NN | 03-models-migration | 2 | CAT-01, CAT-02, CAT-03, CAT-05, CAT-06, CAT-08 | — | Alembic upgrade/downgrade round-trip; CITEXT unique; ARRAY+JSONB round-trip; GIN index on advertised_flavor_note_ids; bag FK RESTRICT | integration | `pytest -q tests/phase_04/test_models_catalog.py tests/phase_04/test_migration.py` | ❌ W0 | ⬜ pending |
| 04-04-NN | 04-roasters-crud | 3 | CAT-01 | T-04-CSRF, T-04-XSS, T-04-MASS | POST → 200 + row fragment; CITEXT case-insensitive dedup; HX-Trigger `roaster-created` on as_modal=true; autocomplete `/roasters/list` | integration | `pytest -q tests/phase_04/test_routers_roasters.py` | ❌ W0 | ⬜ pending |
| 04-05-NN | 05-flavor-notes-crud | 4 | CAT-02 | T-04-CSRF, T-04-XSS, T-04-MASS | POST → 200 + row fragment; 9-value category CHECK + regex; HX-Trigger `flavor-note-created`; `/flavor-notes/datalist` autocomplete reuses shared fragment | integration | `pytest -q tests/phase_04/test_routers_flavor_notes.py` | ❌ W0 | ⬜ pending |
| 04-06-NN | 06-equipment-crud | 5 | CAT-05 | T-04-CSRF, T-04-XSS, T-04-MASS | POST → 200 + row fragment; 6-value type CHECK; list grouped by type; usage_count defaults 0; no autocomplete, no mini-modal | integration | `pytest -q tests/phase_04/test_routers_equipment.py` | ❌ W0 | ⬜ pending |
| 04-07-NN | 07-coffees-crud | 7 | CAT-03, CAT-07 | T-04-CSRF, T-04-XSS, T-04-MASS | List filters by roaster/country/process/archived with `hx-push-url="true"`; ARRAY(BigInteger) advertised_flavor_note_ids round-trip; responsive table↔card markers; HTMX autocomplete attrs locked for plan 04-11 to wire | integration | `pytest -q tests/phase_04/test_routers_coffees.py tests/phase_04/test_coffee_filters.py` | ❌ W0 | ⬜ pending |
| 04-08-NN | 08-recipes-crud | 6 | CAT-06 | T-04-CSRF, T-04-XSS, T-04-MASS | JSONB steps round-trip with order preserved; per-step Pydantic ge/le; HX-Redirect on `/duplicate`; Alpine recipeStepBuilder registered CSP-build | integration | `pytest -q tests/phase_04/test_routers_recipes.py tests/phase_04/test_services_recipes.py` | ❌ W0 | ⬜ pending |
| 04-09-NN | 09-bags-coffee-detail | 9 | CAT-08, SEC-07 | T-04-PHOTO, T-04-EXIF, T-04-POLY, T-04-DOS, T-04-CSRF, T-04-MASS | Bag CRUD nested under coffee; FK RESTRICT enforced; photo upload pipeline integration (5MB pre-check + magic-byte + Pillow re-encode + EXIF strip + polyglot strip + atomic replace); archive == `finished_at IS NOT NULL` | integration | `pytest -q tests/phase_04/test_routers_bags.py` | ❌ W0 | ⬜ pending |
| 04-10-NN | 10-photos-router | 8 | SEC-07 | T-04-AUTH | GET /photos/{uuid}.jpg requires auth; 404 (not 403) for unauthed; explicit `Content-Type: image/jpeg`, `Cache-Control: private, max-age=31536000, immutable`, `X-Content-Type-Options: nosniff`, `Content-Disposition: inline`; path-traversal blocked; Phase 1 D-12 doesn't overwrite | integration | `pytest -q tests/phase_04/test_routers_photos.py` | ❌ W0 | ⬜ pending |
| 04-11-NN | 11-autocomplete-mini-modal | 10 | CAT-01, CAT-02 | T-04-CSRF, T-04-XSS | `hx-trigger="input changed delay:350ms[target.value.length >= 2]"` + `hx-sync="this:replace"` + `focus once from:closest .field` (D-13/D-14/HX-4); HX-Trigger pre-selects parent (D-16); miniModal + autocomplete + flavorNoteChips Alpine components register CSP-build; no `hx-swap-oob` on autocomplete responses | integration | `pytest -q tests/phase_04/test_autocomplete.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky · ❌ W0 = file does not exist yet, Wave 0 must create stubs*

---

## Wave 0 Requirements

Wave 0 is the first wave in each plan; it creates the test stubs the rest of the wave will fill in.

- [ ] `tests/phase_04/__init__.py` — package marker
- [ ] `tests/phase_04/conftest.py` — shared fixtures:
  - `authed_client` — TestClient with valid session cookie + CSRF token preloaded
  - `csrf_client` — TestClient with mismatched CSRF (for negative tests)
  - `photo_volume` — `tmp_path`-backed photo directory monkeypatched into `app.services.photos`
  - `synthetic_jpeg(size_bytes, dimensions)` — generates a clean Pillow JPEG with controlled size
  - `polyglot_jpeg()` — generates a JPEG with appended ZIP/text trailing bytes (SEC-4 fixture)
  - `exif_jpeg(gps_lat, gps_lon)` — generates a JPEG with EXIF GPS metadata for strip verification
  - `bad_magic_jpeg()` — JPEG-extension file with PHP/HTML header
- [ ] `tests/phase_04/test_models_catalog.py` — model creation + CITEXT + ARRAY + JSONB roundtrip stubs
- [ ] `tests/phase_04/test_schemas_form_validation.py` — Pydantic schema stubs for each entity
- [ ] `tests/phase_04/test_services_photos.py` — magic-byte, EXIF, polyglot, DOS, sweep_orphans stubs
- [ ] `tests/phase_04/test_routers_<entity>.py` (one per entity) — HTMX fragment shape + CSRF + auth stubs
- [ ] `tests/phase_04/test_migration.py` — alembic upgrade/downgrade round-trip stub

Wave 0 plan should generate empty test functions with `pytest.fail("Wave 0 stub")` so the sampling-rate "after every commit" command exists and turns green incrementally.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Mobile card-list collapse at 375px viewport | CAT-07 / Success #2 | Visual regression; Playwright in CI is Phase 12 | `docker compose up -d`, open `http://localhost:8000/coffees` in DevTools at 375×667 (iPhone SE), 390×844 (iPhone 14), and 768×1024 (iPad); confirm desktop table at ≥768px, card list at <768px, no horizontal scroll |
| Step-builder reorder UX feel | CAT-06 / Success #3 | Drag-reorder feel is subjective | `docker compose up -d`, open `http://localhost:8000/recipes/new`, add 4 steps, drag the second to position 4, confirm cumulative water + time recompute in real time |
| Pour-timeline vertical bar visual correctness | CAT-06 / Success #3 | Visual; SVG/HTML proportions correlate with `time_seconds` | Open a saved recipe with steps [(15g,30s,'Bloom'), (60g,75s,'Main'), (40g,45s,'Final')]; visually confirm segments are proportional 30:75:45 and labels align |
| Client-side Canvas downscale (D-05) | SEC-07 | Browser-side; pytest can't drive a browser at Phase 4 | Upload a 4000×3000 8MB JPEG from a phone, confirm Network tab shows ~500KB–1MB payload; confirm DevTools EXIF stripped from the response photo |
| Mini-modal ESC/backdrop close | D-15 | Manual click/keyboard testing; Playwright at Phase 12 | Open coffee form, type unknown roaster name, click "+ Create new", verify modal opens; press ESC, verify close without save; reopen, click backdrop, verify close without save |
| HEIC fallback rejection (JS-off) | D-05, deferred-HEIC | Cross-browser; needs real iOS device | On a JS-disabled iOS Safari, upload a HEIC photo, confirm "Please use JPEG/PNG/WebP" friendly error (no server 500) |
| Filter URL state survives reload | D-03 | Browser navigation behavior | Open `/coffees`, filter by roaster=Onyx, archived=true, reload — confirm filters re-applied; use browser back, confirm previous filter state |

---

## Threat Refs (Phase 4 photo-pipeline threat model)

The planner's `<threat_model>` block must reference these IDs (the SECURITY_ENFORCEMENT gate is enabled).

| ID | Threat | Mitigation Wave | Test |
|----|--------|-----------------|------|
| T-04-PHOTO | Path traversal / arbitrary file write via filename | Wave 1 (photos service) | Filenames are server-generated UUIDs; no user input touches the path |
| T-04-EXIF | GPS metadata leak via uploaded photo | Wave 1 (photos service) | EXIF cleared + Pillow re-save before storage; serve route reads only stripped file |
| T-04-POLY | Polyglot upload (JPEG+ZIP / JPEG+PHP) executes if mis-served | Wave 1 (photos service) | Re-encode via `img.save(format=img.format)` strips trailing bytes; serve with `Content-Type: image/jpeg` explicit + `X-Content-Type-Options: nosniff` |
| T-04-DOS | Decompression bomb (large dimensions, small file size) | Wave 1 (photos service) | `Image.MAX_IMAGE_PIXELS` cap set + Content-Length pre-check + magic-byte before decode |
| T-04-AUTH | Unauthenticated photo enumeration | Wave 3 (photos router) | Auth-gated `/photos/{uuid}.jpg` returns **404** (not 403) for unauthed; opaque UUID filenames prevent enumeration |
| T-04-CSRF | State-changing form bypasses CSRF (catalog mutations) | Wave 2 (routers) | Every form template includes the hidden `X-CSRF-Token` input; CSRFMiddleware (Phase 1 D-09) enforces |
| T-04-XSS | User-supplied roaster/coffee/recipe text rendered unescaped | All waves | Jinja autoescape ON globally; grep test asserts no `\|safe` in `templates/` |
| T-04-MASS | Mass-assignment via extra form fields (e.g., `is_admin=True` posted to coffee create) | Wave 2 (schemas) | Pydantic schemas declare exact fields; `model_config = ConfigDict(extra='forbid')` rejects extras |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (test files listed in Wave 0 Requirements)
- [ ] No watch-mode flags (pytest runs one-shot)
- [ ] Feedback latency < 60s (quick) / 120s (full)
- [ ] Manual-only verifications scoped to genuinely-non-automatable behaviors (Playwright lands Phase 12)
- [ ] `nyquist_compliant: true` set in frontmatter after Wave 0 complete

**Approval:** pending
