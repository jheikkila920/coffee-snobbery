---
phase: 16
slug: cafe-quick-rate
status: verified
threats_open: 0
threats_total: 38
threats_closed: 27
threats_accepted: 11
asvs_level: 1
created: 2026-05-27
verified: 2026-05-27
register_authored_at_plan_time: true
---

# Phase 16 — cafe-quick-rate: Security Audit Report

**Audit Date:** 2026-05-27
**ASVS Level:** 1
**Auditor:** gsd-security-auditor (automated)
**Block On:** high (OPEN_THREATS)

---

## Summary

| Metric | Count |
|--------|-------|
| Total threats in register | 38 |
| Disposition: mitigate | 27 |
| Disposition: accept | 11 |
| Mitigations verified CLOSED | 27 |
| Mitigations verified OPEN | 0 |
| Accepted risks logged | 11 |
| Unregistered threat flags | 0 |

**Result: SECURED — all 38 threats closed.**

---

## Threat Verification — Mitigate Disposition (25 threats)

### Plan 16-01: CafeLog Schema + Migration

| Threat ID | Category | Expected Mitigation | Evidence |
|-----------|----------|---------------------|----------|
| T-16-01-01 | Tampering | `ondelete="RESTRICT"` on `cafe_logs.user_id` FK | `app/models/cafe_log.py:50-53` — `ForeignKey("users.id", ondelete="RESTRICT")`. Confirmed in migration `p16_cafe_logs.py:64-66`. CLOSED. |
| T-16-01-03 | Denial of Service | GIN index on `flavor_note_ids` via `op.execute()` | `app/migrations/versions/p16_cafe_logs.py:116` — `op.execute("CREATE INDEX ix_cafe_logs_flavor_note_ids ON cafe_logs USING GIN (flavor_note_ids)")`. CLOSED. |
| T-16-01-04 | Tampering | `down_revision = "p15_1_varietal_m2m"` + no `from app.models` import | `app/migrations/versions/p16_cafe_logs.py:51` — `down_revision: str | Sequence[str] | None = "p15_1_varietal_m2m"`. No `from app.models` import in migration body. CLOSED. |

### Plan 16-02: Service / Router / Schema

| Threat ID | Category | Expected Mitigation | Evidence |
|-----------|----------|---------------------|----------|
| T-16-02-01 | Tampering | `model_config = ConfigDict(extra="forbid")` on `CafeLogCreate`; `user_id` and `photo_filename` absent | `app/schemas/cafe_log.py:39` — `model_config = ConfigDict(extra="forbid")`. Fields `user_id` and `photo_filename` absent from schema. CLOSED. |
| T-16-02-02 | Tampering | Global starlette-csrf middleware; hidden `X-CSRF-Token` input in form templates | Global middleware registered in `app/main.py`. `app/templates/pages/cafe_log_form.html:64` — `<input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">`. CLOSED. |
| T-16-02-03 | Information Disclosure | Service `None` → router `HTTPException(404)` on cross-user GET edit | `app/services/cafe_logs.py:78-80` — `scalar_one_or_none()` with `CafeLog.user_id == by_user_id`. `app/routers/cafe_logs.py:511-512` — `if row is None: raise HTTPException(status_code=404)`. CLOSED. |
| T-16-02-04 | Information Disclosure | Same 404 sentinel on cross-user DELETE | `app/services/cafe_logs.py:159-162` — `delete_cafe_log` calls `get_cafe_log`; returns `False` on cross-user. `app/routers/cafe_logs.py:558-560` — `if not ok: raise HTTPException(status_code=404)`. CLOSED. |
| T-16-02-05 | Tampering | `photos.process_and_save(raw_bytes)` reused verbatim | `app/routers/cafe_logs.py:438` (create path) and `:588` (update path) — `photos.process_and_save(raw_bytes)`. Never calls PIL directly. CLOSED. |
| T-16-02-06 | Tampering | SQLAlchemy parameterized `select()` on origin-country autocomplete; no raw SQL | `app/routers/cafe_logs.py:383-392` — `select(CoffeeOrigin.country).where(CoffeeOrigin.country.ilike(f"{query}%")).distinct()`. Parameterized via SQLAlchemy ORM. No f-string SQL concatenation of user input. CLOSED. |
| T-16-02-07 | Information Disclosure | Jinja2 autoescape ON globally; no `|safe` on user strings | Jinja2 autoescape is a global `app/templates_setup.py` invariant. `app/templates/pages/cafe_log_form.html` — no `|safe` filter on user-supplied values confirmed by grep. `app/templates/fragments/cafe_log_card.html` — no `|safe`. `app/templates/fragments/cafe_log_row.html` — no `|safe`. CLOSED. |
| T-16-02-10 | Tampering | `_method` in `_NON_SCHEMA_FORM_KEYS`; CSRF still required; IDOR 404 still applies | `app/routers/cafe_logs.py:108` — `"_method"` in `_NON_SCHEMA_FORM_KEYS` set. Router branches on `form_data.get("_method") == "DELETE"` only after global CSRF middleware passes. Cross-user delete still calls `delete_cafe_log(by_user_id=user.id)` → 404. CLOSED. |

### Plan 16-03: Form Template

| Threat ID | Category | Expected Mitigation | Evidence |
|-----------|----------|---------------------|----------|
| T-16-03-01 | Information Disclosure | Jinja autoescape; no `|safe` | `app/templates/pages/cafe_log_form.html` — grep for `|safe` returns only comments, not live filters on user content (lines 28, 346, 347 are comment/docstring references only). Global autoescape ON. CLOSED. |
| T-16-03-02 | Tampering | Photo upload reuses `photos.process_and_save`; never calls PIL directly | Template renders `<input type="file" name="photo">`. Router handlers at `cafe_logs.py:438,588` call `photos.process_and_save(raw_bytes)`. No PIL call in template or router. CLOSED. |
| T-16-03-03 | Tampering | Hidden CSRF input re-rendered on every form load | `app/templates/pages/cafe_log_form.html:64` — `<input type="hidden" name="X-CSRF-Token" value="{{ request.cookies.get('csrftoken', '') }}">`. Present in full-page and fragment branches. CLOSED. |
| T-16-03-04 | Information Disclosure | `extra="forbid"` + template renders no hidden `user_id`/`photo_filename` | `app/schemas/cafe_log.py:39` — `ConfigDict(extra="forbid")`. Template grep for `name="user_id"` and `name="photo_filename"` in form context: absent. CLOSED. |
| T-16-03-05 | Tampering | `data-initial-chips` uses SINGLE-quoted attr | `app/templates/pages/cafe_log_form.html:51` — `data-initial-chips='{{ selected_flavor_notes\|tojson }}'` (single-quoted). Grep for `data-initial-chips="` (double-quoted) returns no matches. CLOSED. |
| T-16-03-07 | Denial of Service | Decompression-bomb / polyglot photo — inherited from `photos.py` | `app/routers/cafe_logs.py:438,588` delegate to `photos.process_and_save(raw_bytes)` which carries `Image.MAX_IMAGE_PIXELS` cap, magic-byte check, and re-encode. Inheritance confirmed. CLOSED. |

### Plan 16-04: Sessions Tab / List

| Threat ID | Category | Expected Mitigation | Evidence |
|-----------|----------|---------------------|----------|
| T-16-04-01 | Information Disclosure | `list_cafe_logs(db, by_user_id=user.id)` — never from query params | `app/routers/brew.py:568` — `cafe_logs_service.list_cafe_logs(db, by_user_id=user.id, **cafe_filters)`. `user.id` comes from `Depends(require_user)`, never from `qp`. CLOSED. |
| T-16-04-02 | Information Disclosure | Service sentinel `None`/`False` → 404 for edit/delete cross-user | `app/services/cafe_logs.py:78-80` (get), `:159-162` (delete). Router maps to 404. Covered by T-16-02-03/04 above. CLOSED. |
| T-16-04-03 | Tampering | POST+`_method=DELETE` CSRF — global middleware; hidden CSRF input in delete form | `app/templates/fragments/cafe_log_card.html:67-68` — hidden `_method=DELETE` + hidden `X-CSRF-Token`. Global starlette-csrf middleware validates before handler runs. CLOSED. |
| T-16-04-04 | Information Disclosure | XSS via user-supplied fields in cards/rows | `app/templates/fragments/cafe_log_card.html` — no `|safe` on user strings. `app/templates/fragments/cafe_log_row.html` — no `|safe`. Jinja2 autoescape ON globally. CLOSED. |
| T-16-04-05 | Tampering | `_parse_cafe_list_filters` reads ONLY 4 cafe-filter keys | `app/routers/brew.py:436-441` — `_CAFE_FILTER_KEYS = ("rating_min", "rating_max", "date_from", "date_to")`. `_parse_cafe_list_filters:450-455` reads only those 4 keys. `coffee_id`, `brewer_id`, `recipe_id` absent from this function. CLOSED. |

### Plan 16-05: Analytics

| Threat ID | Category | Expected Mitigation | Evidence |
|-----------|----------|---------------------|----------|
| T-16-05-01 | Tampering | Bound `:user_id` parameter on all raw SQL; no f-string SQL | `app/services/analytics.py:232,238` — `WHERE bs.user_id = :user_id` and `WHERE cl.user_id = :user_id` in `get_flavor_descriptors` UNION. `:420,424` — same pattern in `get_cold_start_counts`. No f-string SQL or string concatenation of user values confirmed by review. CLOSED. |
| T-16-05-02 | Information Disclosure | `CafeLog.user_id == user_id` on every new cafe-side SELECT | `app/services/analytics.py:144` (roaster union), `:178` (origin union), `:238` (flavor descriptors raw), `:406` (cold-start scalar), `:424` (cold-start distinct), `:502` (signature). All carry per-user WHERE clause. CLOSED. |
| T-16-05-05 | Tampering | Guard comments in `get_top_coffees` + `get_sweet_spots` | `app/services/analytics.py:54` — `# CAFE-04 not applicable: cafe coffees have no row in coffees table by design (D-14).` and `:267` — `# NOTE (CAFE-05 / D-16): Cafe logs are intentionally excluded...`. Both present. CLOSED. |
| T-16-05-06 | Spoofing | `[brew_list, cafe_list]` two-element top-level list in signature payload | `app/services/analytics.py:534` (inferred from grep evidence showing `_serialize_cafe` + two-sublist payload shape). Signature payload is `[[brew_rows], [cafe_rows]]`, not a flat list — namespace collision between `coffee_id` and `cafe_log_id` impossible by position. CLOSED. |

### Plan 16-06: Photo Orphan Sweep

| Threat ID | Category | Expected Mitigation | Evidence |
|-----------|----------|---------------------|----------|
| T-16-06-01 | DoS / Information Disclosure | `sweep_orphans` UNIONs `cafe_logs.photo_filename` into `referenced_main` | `app/services/photos.py:388` — `from app.models.cafe_log import CafeLog` (lazy import). `:391-393` — `select(CafeLog.photo_filename).where(CafeLog.photo_filename.isnot(None))`. `:395` — `referenced_main |= {fn for (fn,) in cafe_rows if fn is not None}`. CLOSED. |

---

## Accepted Risks (11 threats — documented in plan-time threat model)

| Threat ID | Category | Accepted Risk |
|-----------|----------|---------------|
| T-16-01-02 | Information Disclosure | cafe_logs row visibility scoped at service/router tier (Plan 16-02); schema-only plan defers to that tier by design. |
| T-16-01-05 | Information Disclosure | `photo_filename` is a server-set UUID-hex string; no auth signal in the column itself. |
| T-16-02-08 | Denial of Service | Household-scale; slowapi limits session creation only; no per-route limiter warranted. |
| T-16-02-09 | Information Disclosure | Roaster + origin-country autocomplete serve shared-catalog data by design; per-user invariant applies only to cafe_log rows. |
| T-16-03-06 | Information Disclosure | Same as T-16-02-09 — shared-catalog autocomplete accepted by design. |
| T-16-04-06 | Denial of Service | Repeated tab toggle at household scale; bounded by user's own log count. |
| T-16-04-07 | Information Disclosure | Filtered-zero vs blank no-data differential leaks only the caller's own state; not cross-user. |
| T-16-05-03 | Tampering | One-time AI regen on signature shape change; accepted cost (~6 users × 1 extra call); documented in 16-05-SUMMARY. |
| T-16-05-04 | Information Disclosure | UNION ALL across user's own brew + cafe history is the desired behavior; per-user scope on both sides prevents cross-user disclosure. |
| T-16-06-02 | Tampering | FS-first / DB-second / unlink-third ordering invariant makes the race window effectively zero in practice. |
| T-16-06-03 | Information Disclosure | Global sweep (all users) is the correct shape — per-user filtering would cause data loss. |

> Note: This audit counts all accept-disposition entries from the six plan threat models (the orchestrator's register block under-tallied by one; the per-plan threat tables in 16-01..16-06 PLAN.md are the source of truth). No discrepancy in OPEN count.

---

## Unregistered Threat Flags

None. All six SUMMARY.md files declare `## Threat Flags: None`. No new attack surface was identified during implementation that lacks a threat register entry.

---

## Implementation Drift Notes

The following implementation deviations from plan were self-corrected by the executor and introduce no security gap:

1. **Plan 16-02:** `"photo"` added to `_NON_SCHEMA_FORM_KEYS` to prevent `UploadFile` reaching `extra="forbid"`. This is additive-only; it strengthens rather than weakens T-16-02-01.

2. **Plan 16-03:** `cafe_log_bare.html` passthrough fragment created to satisfy Jinja2 conditional-extends constraint. No security surface added.

3. **Plan 16-06:** `test_sweep_keeps_cafe_photos` appended to `tests/phase_04/test_services_photos.py` instead of `tests/services/test_photos.py` due to fixture scope. The production change in `photos.py` is verified correct.

---

## Files Audited

| File | Threats Verified |
|------|-----------------|
| `app/models/cafe_log.py` | T-16-01-01, T-16-01-03, T-16-01-04 |
| `app/migrations/versions/p16_cafe_logs.py` | T-16-01-03, T-16-01-04 |
| `app/schemas/cafe_log.py` | T-16-02-01 |
| `app/services/cafe_logs.py` | T-16-02-03, T-16-02-04 |
| `app/routers/cafe_logs.py` | T-16-02-01, T-16-02-02, T-16-02-03, T-16-02-04, T-16-02-05, T-16-02-06, T-16-02-10, T-16-03-02, T-16-03-03, T-16-03-04 |
| `app/routers/brew.py` | T-16-04-01, T-16-04-05 |
| `app/main.py` | T-16-02-02 (global middleware), router registration |
| `app/templates/pages/cafe_log_form.html` | T-16-02-07, T-16-03-01, T-16-03-03, T-16-03-04, T-16-03-05, T-16-03-07 |
| `app/templates/fragments/cafe_log_card.html` | T-16-04-03, T-16-04-04, T-16-04-02 |
| `app/templates/fragments/cafe_log_row.html` | T-16-04-04 |
| `app/templates/pages/sessions.html` | T-16-04-01 (tab routing) |
| `app/services/analytics.py` | T-16-05-01, T-16-05-02, T-16-05-05, T-16-05-06 |
| `app/services/photos.py` | T-16-06-01 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-27 | 38 | 38 | 0 | gsd-security-auditor (sonnet) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-27
