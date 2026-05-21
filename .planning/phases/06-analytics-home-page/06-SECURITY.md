---
phase: 6
slug: analytics-home-page
status: secured
threats_total: 12
threats_closed: 12
threats_open: 0
asvs_level: 1
created: 2026-05-20
---

# Phase 6 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Verified by gsd-security-auditor (register authored at plan time; mitigations verified against implementation).

**Audit date:** 2026-05-20 · **ASVS Level:** 1 · **Verdict:** SECURED · **Threats:** 12/12 closed, 0 open

---

## Threat Verification

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-06-01 | Information Disclosure / IDOR | mitigate | CLOSED | `BrewSession.user_id == user_id` is the first WHERE clause on all nine query functions (`analytics.py:62,96,116,208,247,282,302,331,397`). `user_id` is a typed function arg — no global or request-param path. |
| T-06-02 | Tampering (signature integrity) | mitigate | CLOSED | `compute_input_signature` (`analytics.py:370–419`) reads only this user's rated sessions (`BrewSession.rating.is_not(None)`), never shared catalog counts. Serializes six per-session fields (coffee_id, float(rating), sorted flavor_note_ids_observed, recipe_id, brewer_id, roast_date) via `json.dumps(sort_keys=True, separators=(",",":"))` + `hashlib.sha256`. `_EMPTY_SIGNATURE` at `analytics.py:39`; `ORDER BY BrewSession.id` for determinism. Tests: determinism, order-independent, excludes-free-text, zero-rated-sentinel — all pass. |
| T-06-03 | Tampering (SQLi) | mitigate | CLOSED | All nine functions use SQLAlchemy Core constructs. The two `text()` unnest fallbacks (`analytics.py:148–162`, `343–353`) bind `:user_id` via `db.execute(stmt, {"user_id": user_id})` — no user-controlled input interpolated into SQL. |
| T-06-04 | Information Disclosure (unauthed access) | mitigate | CLOSED | `Depends(require_user)` on all 8 handlers (`home.py:43,72,98,136,157,178,197,216`); `require_user` raises HTTP 401 (`auth.py:33–45`). Tests `test_home_unauthenticated_returns_401`, `test_unrated_coffees_fragment_requires_auth` pass. |
| T-06-05 | Elevation of Privilege (IDOR) | mitigate | CLOSED | All analytics calls use `user.id` from `request.state.user` (set by SessionMiddleware), never a query param. No `user_id`/`query_params` in any `home.py` handler. |
| T-06-06 | Tampering (XSS) | mitigate | CLOSED | Zero matches for `\|safe`, `hx-on:`, `hx-vals='js:'` across `home.html` + `fragments/home/*.html`. Jinja2 autoescape global; all user-derived strings render through autoescaped variables. |
| T-06-07 | DoS (connection pool exhaustion) | mitigate | CLOSED | Staggered `hx-trigger="load delay:Nms"` (100–500ms + 150ms unrated) at `home.html:32,54,67,80,93,106`; pool `pool_size=10, max_overflow=5` (`db.py:42–43`). Stagger spreads requests across 500ms. |
| T-06-08 | Information Disclosure (aggregate fragments) | mitigate | CLOSED | `Depends(require_user)` on all five aggregate handlers (`home.py:136,157,178,197,216`). Tests `test_top_coffees_requires_auth`, `test_sweet_spots_requires_auth` assert 401. |
| T-06-09 | Elevation of Privilege (IDOR, aggregate) | mitigate | CLOSED | Five aggregate handlers call `analytics.get_*(db, user.id)` with `user` from `Depends(require_user)`; no `user_id` param accepted; service enforces per-user WHERE (T-06-01). |
| T-06-10 | Tampering (XSS, card templates) | mitigate | CLOSED | Zero matches for `\|safe`, `hx-on:`, `hx-vals='js:'` across all six card templates (incl. `_card_sparse.html`). All values autoescaped. |
| T-06-11 | Scope leak (HOME-06 AI prose in Phase 6) | accept→guard | CLOSED | `sweet_spots.html` ends after the SQL list — no AI prose / "coming soon" placeholder. Test `test_sweet_spots_no_ai_placeholder` asserts "coming soon"/"ai insight"/"recommendation" absent from the response body. |
| T-06-12 | Reliability (broken Phase 7 cross-phase trigger) | mitigate | CLOSED | Phase 7 AI slot is a Jinja2 comment (`home.html:115`), stripped at render. Test `test_ai_slot_placeholder_present` asserts no live `hx-trigger="revealed"` in rendered HTML and the comment exists in source. |

---

## Unregistered Flags

None. The `## Threat Surface Scan` sections of all three SUMMARY.md files declare no new attack surface beyond the planned register.

---

## Accepted Risks Log

| ID | Risk | Rationale |
|----|------|-----------|
| T-06-11 | No AI prose rendered in Phase 6 sweet-spots card | Phase 6 scope explicitly excludes AI prose (HOME-06 deferred to Phase 7). Guard test enforces absence. Accepted by design — not a residual risk. |

---

## Notes

- The `text()` unnest fallback in `get_flavor_descriptors` and `get_cold_start_counts` uses bound parameters, not interpolation — T-06-03 closed despite the ORM detour (SQLAlchemy 2.0.49 `column_valued()` limitation).
- `compute_input_signature` excludes `brewed_at` timestamps and free-text `notes` per D-08 (confirmed by `test_signature_excludes_free_text`).
- `get_unrated_coffees` enforces `Coffee.archived == False` (`analytics.py:310`), proven by `test_unrated_coffees`.
- All eight derivations + `compute_input_signature` confirmed <50ms against a 1000-session seed (`tests/services/test_analytics_perf.py`); no new Alembic migration added.

---

## Audit Trail

### Security Audit 2026-05-20
| Metric | Count |
|--------|-------|
| Threats found | 12 |
| Closed | 12 |
| Open | 0 |

Register authored at plan time across plans 06-01/06-02/06-03; mitigations verified against the implemented code by gsd-security-auditor (ASVS L1, block-on: high).
