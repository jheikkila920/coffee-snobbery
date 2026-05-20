---
phase: 05-brew-sessions
reviewed: 2026-05-20T00:00:00Z
depth: standard
files_reviewed: 35
files_reviewed_list:
  - app/events.py
  - app/main.py
  - app/migrations/versions/p5_brew_sessions.py
  - app/models/__init__.py
  - app/models/brew_draft.py
  - app/models/brew_session.py
  - app/routers/brew.py
  - app/schemas/__init__.py
  - app/schemas/brew_csv.py
  - app/schemas/brew_session.py
  - app/services/brew_drafts.py
  - app/services/brew_sessions.py
  - app/services/csv_io.py
  - app/static/css/tailwind.src.css
  - app/static/js/alpine-components/brew-draft.js
  - app/static/js/alpine-components/brew-ratio.js
  - app/static/js/alpine-components/flavor-tag-input.js
  - app/static/js/alpine-components/rating-stars.js
  - app/templates/base.html
  - app/templates/fragments/brew_prefill_fields.html
  - app/templates/fragments/csv_import_results.html
  - app/templates/fragments/session_list.html
  - app/templates/fragments/session_row.html
  - app/templates/pages/brew_form.html
  - app/templates/pages/brew_import.html
  - app/templates/pages/sessions.html
  - tests/conftest.py
  - tests/routers/test_brew_list_csv.py
  - tests/routers/test_brew_router.py
  - tests/services/test_brew_csv.py
  - tests/services/test_brew_drafts.py
  - tests/services/test_brew_prefill.py
  - tests/services/test_brew_schema.py
  - tests/services/test_brew_sessions_service.py
findings:
  critical: 2
  warning: 6
  info: 5
  total: 13
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-05-20
**Depth:** standard
**Files Reviewed:** 35
**Status:** issues_found

## Summary

Phase 5 (brew sessions) is broadly solid on the hard invariants John flagged:
per-user IDOR scoping is consistently applied across every read/write path
(service `where(... user_id == by_user_id)`, router maps the `None` sentinel to
404), CSRF is enforced on every state-changing route (`/brew`, `/brew/{id}`,
`/brew/draft`, `/brew/draft/clear`, `/brew/import` are NOT exempt — verified by
tests), `extraction_yield_pct` is correctly GENERATED + absent from every
writable schema + folded into `_form` via `extra="forbid"`, the templates are
CSP-strict (no `|safe`, no inline `hx-on:`, no `x-model`, no `hx-vals='js:'`),
and CSV export neutralizes formula-injection triggers.

However, two BLOCKERs undermine documented guarantees:

1. The **"single transaction" CSV import (BREW-11, Pitfall 4)** is violated:
   `csv_io._resolve_observed_notes` calls `create_flavor_note`, which runs its
   own `db.flush()` + `db.commit()` mid-batch. Any auto-created observed note
   commits all sessions already added to the pending loop, so a DB failure on a
   later row leaves a partial commit. The "rolls everything back" claim in the
   module docstring is false whenever a row carries a new observed note.

2. The **GENERATED EY expression can overflow `numeric(5,2)`** for input
   combinations the schemas accept (small dose + large yield/tds), producing an
   unhandled 500 on both the create form and CSV import.

The remaining items are robustness, correctness-edge, and quality findings.

## Critical Issues

### CR-01: CSV import auto-create breaks the single-transaction guarantee (partial commit)

**File:** `app/services/csv_io.py:436-449` (batch loop) calling
`app/services/csv_io.py:315-324` → `app/services/flavor_notes.py:71-73`

**Issue:** `import_brews` documents (lines 28-31) that all accepted rows insert
"in ONE transaction with a single `db.commit()`" and "a DB error during the
batch rolls everything back (no partial commit — Pitfall 4)". That guarantee is
broken. Inside the pending-insert loop:

```python
for _row_number, session, notes_raw in pending:
    session.flavor_note_ids_observed = _resolve_observed_notes(db, names_raw=notes_raw, by_user_id=by_user_id)
    db.add(session)
db.commit()
```

`_resolve_observed_notes` calls `create_flavor_note`, which itself does
`db.flush()` then `db.commit()` (`flavor_notes.py:72-73`). That commit flushes
and persists **every session already added** to the loop. Concrete failure:
pending = [row A (carries a brand-new observed note), row B (triggers a DB error
on insert)]. Row A's note creation commits row A; row B then fails the final
`db.commit()`; the `except: db.rollback()` rolls back only the still-open
transaction — row A is already durably committed. Result: a partial import the
code claims is impossible. Additionally, if `create_flavor_note` raises
`DuplicateNameError` it calls `db.rollback()` internally
(`flavor_notes.py:78-79`), silently discarding pending sessions added before it
within the same batch.

The existing test `test_import_single_transaction`
(`tests/services/test_brew_csv.py:284`) does NOT catch this — its CSV rows carry
no `observed_flavor_notes`, so `create_flavor_note` is never reached and no
mid-batch commit fires.

**Fix:** Resolve/auto-create observed notes without committing inside the batch.
Options: (a) add a no-commit variant of `create_flavor_note` (e.g.
`create_flavor_note(..., commit=False)` that only `flush()`es and lets the
caller own the single commit), and call that from `_resolve_observed_notes`; or
(b) resolve all observed-note names in a pre-pass before opening the insert
batch. Then keep exactly one `db.commit()` at the end. Add a regression test
whose CSV includes a new `observed_flavor_notes` value AND forces a later-row DB
error, asserting zero rows persist.

```python
# flavor_notes.py — no-commit path the importer can compose into its txn
def create_flavor_note(db, *, name, category, by_user_id, commit=True):
    flavor_note = FlavorNote(name=name, category=category)
    db.add(flavor_note)
    db.flush()                      # id available; no commit
    if commit:
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise DuplicateNameError from exc
    log.info(CATALOG_FLAVOR_NOTE_CREATED, flavor_note_id=flavor_note.id, category=category, user_id=by_user_id)
    return flavor_note
```

### CR-02: GENERATED extraction_yield_pct can overflow numeric(5,2) → unhandled 500

**File:** `app/models/brew_session.py:62,118-122`,
`app/migrations/versions/p5_brew_sessions.py:60,154-157`,
schema ranges in `app/schemas/brew_session.py:55-59` and
`app/schemas/brew_csv.py:42-46`

**Issue:** `extraction_yield_pct` is `numeric(5,2)` (max 999.99). The stored
expression is `(yield_grams_actual * tds_pct / 100.0) / dose_grams_actual * 100`.
The writable schemas accept `dose_grams_actual` in `(0, 200]`,
`yield_grams_actual` in `[0, 3000]`, and `tds_pct` in `[0, 100]`. These bounds
do not constrain the computed EY. Example values that all pass validation:
`dose=0.01, yield=3000, tds=100` → EY = `(3000*100/100)/0.01*100 = 30,000,000`,
far beyond `numeric(5,2)`. Postgres raises `numeric field overflow` on INSERT.
On the brew create form this surfaces as an unhandled 500 (the router only
catches `ValidationError`, not the DB error from
`brew_sessions.create_brew_session`). On CSV import the same overflow propagates
out of `import_brews`' bare `except Exception: db.rollback(); raise`, returning a
500 to the upload with no per-row reason. A user (or a crafted CSV) can trigger a
server error with otherwise-valid-looking numbers — denial of service / data
entry crash.

**Fix:** Either widen the column (e.g. `numeric(8,2)` or `numeric` unbounded
precision) via a follow-up migration, OR add cross-field validation that bounds
the realistic EY (a refractometer EY is physically ~14–30%; reject values whose
computed EY exceeds, say, 100). A column-precision fix is the most robust since
it also protects the CSV path. If keeping `numeric(5,2)`, add a model/schema
`@model_validator` rejecting input combinations whose EY would exceed 999.99 and
re-render with a friendly field error instead of a 500.

## Warnings

### WR-01: `update_brew_session` adjusts usage_count even when no writable fields change, and the equipment UPDATE runs outside the `if values:` guard

**File:** `app/services/brew_sessions.py:236-256`

**Issue:** The function computes `new_equipment` from `values.get(...)` defaults
to the existing column values, so when an edit passes only non-equipment fields
the deltas are empty and `_adjust_usage_counts` is a no-op — correct. But the
ordering is fragile: `_adjust_usage_counts(db, deltas=deltas)` executes its
`UPDATE equipment` (line 247) BEFORE the `if values:` guard (line 249). If a
future caller passes equipment FK keys that are NOT in `_WRITABLE_FIELDS`-applied
`values` (they are filtered at line 239), the deltas could be computed against
values that never get written, double-counting. Today it is consistent because
both `new_equipment` and `values` derive from the same filtered dict, but the
two derivations are independent and easy to desync on edit. There is also no test
covering "update with empty writable set" (e.g. a POST that only changes a
non-writable field) to lock the no-op behavior.

**Fix:** Derive `new_equipment` from the same `values` dict already filtered to
writable fields and compute deltas only after establishing the final applied
values; or short-circuit when `not values`. Add a test asserting `usage_count`
is unchanged when an update touches no equipment FK.

### WR-02: `tds_pct` accepts 0 but a zero TDS yields EY = 0 silently; ranges admit physically impossible refractometer values

**File:** `app/schemas/brew_session.py:58`, `app/schemas/brew_csv.py:45`

**Issue:** `tds_pct: Decimal | None = Field(None, ge=0, le=100)` permits `0`
(EY computes to 0) and values up to 100% TDS, which is physically impossible for
coffee (real TDS is ~1–2%). Combined with CR-02, the loose upper bound is the
root enabler of the overflow. Even without overflow, accepting 100% TDS lets a
typo store a meaningless EY that Phase 6 analytics will treat as real data.

**Fix:** Tighten to a realistic range (e.g. `gt=0, le=10` for `tds_pct`) or at
minimum document why 0–100 is intentional. Coordinate with CR-02's bound.

### WR-03: `_parse_form_payload` collapses repeated scalar keys to the first value, dropping later submissions silently

**File:** `app/routers/brew.py:165-169`

**Issue:** The dedup guard `if key in seen_keys: continue` means that for any
repeated non-list field name, only the FIRST occurrence is read; subsequent ones
are dropped without error. For `flavor_note_ids_observed` this is handled
correctly via `getlist`. But for a scalar field submitted twice (e.g. a stray
duplicate hidden input, or an attacker crafting `rating=5&rating=2.5` to confuse
validation vs. what the template echoes), the router validates the first value
while the user/template may believe the second applied. Last-wins or explicit
rejection is the safer contract; first-wins is surprising and untested.

**Fix:** For scalar fields use `form_data.get(key)` (Starlette returns the last
value) consistently, or reject duplicate scalar keys. Keep the `getlist` path for
the array field. Add a test for duplicate scalar keys.

### WR-04: `_read_draft_payload` stores fully arbitrary, unbounded JSON keyed per user with no size limit

**File:** `app/routers/brew.py:933-943`, `app/services/brew_drafts.py:34-55`

**Issue:** `POST /brew/draft` accepts either JSON or form-encoded input and
stores it verbatim into `brew_drafts.payload` (JSONB) with no schema, no key
allow-list, and no size cap. While the row is per-user (T-05-08 holds) and never
rendered as HTML through an unsafe path, an authenticated user can write an
arbitrarily large JSON blob (megabytes) on every blur autosave, and the payload
is later serialized into the create page via `json.dumps(server_draft)`
(`brew.py:346`) and dropped into a `data-server-draft` attribute. A large or
deeply nested draft bloats the DB and every `/brew/new` render. The autosave is
also unthrottled server-side (the JS blurs frequently).

**Fix:** Cap the accepted payload size (reject > N KB), and optionally restrict
top-level keys to the known brew-form field names. Document the intended ceiling.

### WR-05: CSV import buffers the whole upload into memory before the size check on `UploadFile.read()`

**File:** `app/routers/brew.py:566-581`

**Issue:** The docstring claims the size ceiling is enforced "BEFORE buffering the
full body (T-05-27 DoS guard)", but the code calls `raw_bytes = await
upload.read()` (line 577) which reads the ENTIRE uploaded file into memory, and
only THEN checks `len(raw_bytes) > MAX_CSV_BYTES`. The content-type allow-list
runs first, but content-type is attacker-controlled and trivially set to
`text/csv`. A client can stream a multi-GB body labeled `text/csv` and the server
buffers all of it before rejecting. The `MAX_CSV_BYTES` check is post-hoc, not a
true pre-buffer guard.

**Fix:** Read in bounded chunks and abort once the cumulative size exceeds
`MAX_CSV_BYTES`, or check `request.headers["content-length"]` against the ceiling
before reading (defense-in-depth; content-length is also spoofable but cheap).
Reword the docstring to match actual behavior.

### WR-06: `_resolve_coffee` does not exclude archived coffees while `_resolve_recipe_id`/`_resolve_equipment_id` do

**File:** `app/services/csv_io.py:226-236` vs. `csv_io.py:475-495`

**Issue:** Inconsistent archival handling on import. `_resolve_equipment_id`
filters `Equipment.archived.is_(False)` and `_resolve_recipe_id` filters
`Recipe.archived.is_(False)`, but `_resolve_coffee` matches `Coffee.name == name`
with no `archived` filter. An import row can therefore link a brew session to an
archived coffee, which the UI hides — producing a session whose coffee is
invisible in the catalog. Either the coffee filter is missing or the
equipment/recipe filters are over-restrictive; the three should agree on a
documented policy.

**Fix:** Decide the policy (most likely: refuse archived coffees on import, or
intentionally allow all three) and apply it consistently across the three
resolvers. Document the choice.

## Info

### IN-01: Bare `except Exception` around the import commit loses the failure class for diagnostics

**File:** `app/services/csv_io.py:444-446`

**Issue:** `except Exception: db.rollback(); raise` re-raises but emits no log
line, so an operator sees only the generic 500 with no `BREW_CSV_IMPORTED`
telemetry for the failed run. Given CR-01/CR-02 can land here, a structured log
(error class only, no payload) would speed triage.

**Fix:** Log `error_class=type(exc).__name__` before `raise`, mirroring the
`/healthz` handler in `main.py:244-245`.

### IN-02: `_date_or_none` end-of-day widening only fires when time is exactly midnight

**File:** `app/routers/brew.py:396-397`

**Issue:** A `date_to` supplied as a full datetime at, e.g., `2026-05-10T00:00:01`
is NOT widened to end-of-day, so the inclusive upper bound silently excludes most
of that day. Only a bare date (or an explicit midnight) is widened. This is an
edge case for the date filter but could surprise anyone passing a datetime
`date_to` via the query string.

**Fix:** Either widen any `date_to` whose time component the caller did not
intend, or document that `date_to` is treated as a date boundary only.

### IN-03: Duplicate `_brew_ratio` helper across two modules

**File:** `app/routers/brew.py:438-445` and `app/services/csv_io.py:521-528`

**Issue:** Near-identical `_brew_ratio` implementations (one returns `"—"` for
empty, the other `""`). DRY violation; a future ratio-format change must be made
in two places.

**Fix:** Extract a single shared helper (e.g. in a small `app/services` util)
parameterized on the empty placeholder.

### IN-04: Repeated `_require_postgres` / `_require_p5_migration_applied` / `_authed_client` / `_prime_csrf` copies across test modules

**File:** `tests/routers/test_brew_router.py:56-86,148-174`,
`tests/routers/test_brew_list_csv.py:45-75,122-140`, and the three service test
modules

**Issue:** The skip-gate and authed-client helpers are copy-pasted verbatim
across five Phase-5 test files. Drift risk if one is updated. Not a correctness
issue, but a maintenance smell.

**Fix:** Promote the shared probes/helpers into `tests/conftest.py` (or a
`tests/_brew_helpers.py`) and import them.

### IN-05: `BrewSessionUpdate` is an empty subclass with no behavioral divergence

**File:** `app/schemas/brew_session.py:80-86`

**Issue:** `BrewSessionUpdate(BrewSessionCreate)` adds nothing today. The
docstring justifies the split as future-proofing, which is reasonable, but the
update path requiring `coffee_id`/`dose`/`water` (inherited as required) means an
edit must always re-send those fields — fine for the current full-form edit, but
a latent constraint if a partial PATCH is ever wanted. Noted for awareness, not a
defect.

**Fix:** None required; revisit when/if a partial-update path is introduced.

---

_Reviewed: 2026-05-20_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
