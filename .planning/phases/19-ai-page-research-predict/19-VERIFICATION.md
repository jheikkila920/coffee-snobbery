# Phase 19 Verification Ledger

**Phase:** 19-ai-page-research-predict
**Populated:** 2026-05-28 (plan 19-07)
**Source:** D-15 (CONTEXT.md) — one-time latency investigation before phase close; operator NPM/SSE smoke

---

## AIX-13 / D-15: Latency Investigation

### Query Used

```sql
SELECT
    recommendation_type,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY duration_ms) AS p50_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_ms,
    COUNT(*) AS sample_count
FROM ai_recommendations
WHERE
    duration_ms IS NOT NULL
    AND error_status IS NULL
    AND generated_at >= NOW() - INTERVAL '30 days'
GROUP BY recommendation_type
ORDER BY recommendation_type;
```

Executed: `docker compose exec coffee-snobbery-db psql -U snobbery -d snobbery` on 2026-05-28.

### Results

| recommendation_type        | sample_count | p50_ms | p95_ms | documented target (D-15) | verdict |
|---------------------------|-------------|--------|--------|--------------------------|---------|
| coffee_research            | 1           | 11046  | 11046  | p95 ≤ 30000ms           | within target |
| equipment                  | 1           | 9210   | 9210   | p95 ≤ 20000ms           | within target |
| coffee (what-to-buy-next)  | 0 duration_ms rows | — | — | p95 ≤ 60000ms | insufficient data — re-measure at Phase 22 |
| brew_improvement           | 0 rows      | —      | —      | p95 ≤ 20000ms           | insufficient data — re-measure at Phase 22 |
| preference_profile_prose   | 0 rows      | —      | —      | p95 ≤ 30000ms           | insufficient data — re-measure at Phase 22 |
| sweet_spots_prose          | 0 rows      | —      | —      | p95 ≤ 30000ms           | insufficient data — re-measure at Phase 22 |
| paste_rank                 | 0 rows      | —      | —      | p95 ≤ 45000ms           | insufficient data — re-measure at Phase 22 |

**Notes:**
- `coffee_research` and `equipment` have exactly one sample each (Phase 19 dev session only). These single-sample results meet their p95 targets but do not constitute statistically meaningful p95 estimates. The percentile equals the single observation.
- Phase 22 verification should re-run this query after production use accumulates sufficient samples (recommended minimum: 20+ per flow for p95 to be meaningful).
- Flows that are fundamental web-search-driven (coffee_research, equipment) are expected to remain 8–15s p50 due to Anthropic web_search_tool round-trip latency. This is architecture-fundamental, not a regression.
- `generate_sweet_spots_prose` writes to `ai_recommendations` with `recommendation_type='sweet_spots_prose'`; no rows present at phase close (nightly job not yet run on this deployment).

### Verdict Summary

No flow exceeds its D-15 target in the available data. Two flows within target on single-sample data; five flows with zero duration_ms samples at phase close. All five deferred to Phase 22 re-measurement.

---

## D-16 / NPM SSE Buffering

**Operator step status:** PENDING — see Task 3 checkpoint (Phase 19 close gate).

The NPM `proxy_buffering off` block requirement is documented in `CONTRIBUTING.md` § "Reverse-Proxy SSE Configuration (NPM)". The operator must apply this config to the Snobbery NPM proxy host and smoke-test end-to-end SSE streaming through NPM before declaring the research flow production-ready.

**Backend defense-in-depth:** `X-Accel-Buffering: no` is already emitted by the SSE route (`EventSourceResponse` headers). This header instructs Nginx (and NPM's underlying nginx) to disable buffering on this connection even without the explicit NPM Advanced config block. The NPM block is belt-and-suspenders and ensures consistent behavior across NPM config resets.

**Operator SSE smoke result:** (To be recorded here after the operator completes Task 3.)

---

## AIX-05 / D-08: Admin-Editable Quota Settings

**Status:** VERIFIED via automated test (test_admin_settings.py::test_quota_settings_*).

Both `ai.research_daily_quota` and `ai.improve_brew_daily_quota` are seeded as `int` type rows by the Phase 19 migration. The generic settings editor (`app/routers/admin/settings_editor.py`) renders all `int` rows as `number_int` inputs automatically — no bespoke template logic was needed. The `get_quota_cap()` function in `ai_quota.py` reads the live DB value via `settings_service.get_int()`, which invalidates its cache on every `set_setting()` call. An admin change to either key is reflected immediately on the next quota check.

---

## Phase-Close Gate — Local (run by orchestrator, 2026-05-29)

**Full suite (`coffee-snobbery-test`, baked image, `snobbery_test` dropped first):**
Run twice (clean DB, then dirty DB) — stable: **1316 passed, 3 skipped (documented), 10 xfailed, 1 failed**.

The 3 skips are documented/benign (async session fixture, FK-cascade orphan-session, live-container cafe log). The 1 failure is pre-existing and environmental:
- `test_admin_system::test_system_info` — asserts pyproject version `1.2.0` appears in `/admin`, but the page renders `get_app_version()` = the `APP_VERSION` build-arg, which the local dev test image does not set (only `release.yml` stamps it from the git tag). Passes in release builds (`1.2.0` ⊂ `v1.2.0`). Not a Phase 19 regression, not a production bug. (Recommend a follow-up to make the test skip when `APP_VERSION` is unset/`dev`.)

**Two gate failures found and fixed (test-only, commit `83d2680`):**
1. `test_ai_router::test_ai_page_above_gate_with_key_shows_hero` asserted the Phase-17 `/ai` layout (deleted flavor-descriptors mount + replaced "Coming in Phase 19" stub). Reconciled to the D-10 / ADR-0004 structure.
2. `test_admin_settings` quota update-persists tests committed caps (5/10) without restoring, polluting `test_p19_quota_settings_seeded` in the full suite. Added an autouse teardown restoring both quota rows to `'20'`. Verified the fix holds on a dirty-DB second run.

**Ruff gates (CI parity):** `ruff format --check .` → 240 files clean; `ruff check .` → all checks passed.

---

## Outstanding UAT (carried from 19-06)

These items were identified in the 19-06 SUMMARY as not confirmed during Phase 19 human verification. They are input to this verification ledger but are NOT fixed in plan 19-07 (out of scope per plan frontmatter). Carry to post-phase UAT.

1. **Cached-badge on identical re-run:** Submit the same research query twice; confirm quota counter does NOT decrement on the second call and the `cached` badge appears.
2. **CSP console violations on trimmed card:** Open DevTools on /ai after rebuild, submit a research query, confirm zero script-src/style-src violations.
3. **CSRF token mechanism for wishlist POST:** `research_result.html` sends `X-CSRF-Token` as a form field read from the `csrftoken` cookie. Verify this matches other working HTMX POST forms (e.g., `research_form.html`, `paste_rank_results.html`).
4. **Admin "Test connection" probe:** The admin test-connection only calls GET /v1/models, not POST /v1/messages. Invalid model names (e.g., period-separated `claude-opus-4.8`) pass the probe but fail at first research invocation. Recommend replacing with a real 1-token `messages.create` probe in a future phase.

---

## 19-06 Deviations Carried Forward (not in scope for 19-07)

- **Cached-re-run quota check:** Not tested end-to-end through the running container in Phase 19.
- **Dark-mode Chart.js DevTools verification:** Initial manual test positive; formal DevTools check at 375px not completed.
- **Improve-brew SSE through NPM:** Pending operator Task 3 smoke test.
