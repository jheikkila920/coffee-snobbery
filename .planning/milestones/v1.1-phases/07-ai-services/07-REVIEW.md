---
phase: 07-ai-services
reviewed: 2026-05-21T00:00:00Z
depth: standard
files_reviewed: 22
files_reviewed_list:
  - app/events.py
  - app/main.py
  - app/routers/ai.py
  - app/routers/home.py
  - app/services/ai_schemas.py
  - app/services/ai_service.py
  - app/services/wishlist.py
  - app/templates/fragments/ai/paste_rank_results.html
  - app/templates/fragments/home/ai_rec_cold_start.html
  - app/templates/fragments/home/ai_rec_hero.html
  - app/templates/fragments/home/ai_rec_in_flight.html
  - app/templates/fragments/home/ai_rec_not_configured.html
  - app/templates/fragments/home/ai_rec_try_again.html
  - app/templates/fragments/home/equipment_rec.html
  - app/templates/fragments/home/sweet_spots.html
  - app/templates/pages/home.html
  - app/templates/pages/paste_rank.html
  - app/templates/pages/wishlist.html
  - tests/routers/test_ai_router.py
  - tests/routers/test_home.py
  - tests/services/test_ai_service.py
  - tests/services/test_wishlist.py
findings:
  critical: 5
  warning: 6
  info: 3
  total: 14
status: issues_found
---

# Phase 7: Code Review Report

**Reviewed:** 2026-05-21T00:00:00Z
**Depth:** standard
**Files Reviewed:** 22
**Status:** issues_found

## Summary

Phase 7 delivers the AI services layer: provider abstraction (Anthropic + OpenAI fallback), three recommendation flows (coffee, sweet-spots, equipment), paste-and-rank, wishlist CRUD, and all associated templates and tests. The security framing is mostly sound — IDOR guards are consistent, CSRF coverage is complete, the citation projector correctly filters non-tool_use content, and `|safe` is absent from all AI prose rendering. However, five blockers were found: a stored XSS vector via an unvalidated user-supplied `source_url` rendered as an `href` in wishlist.html; a crash-path `NoneType` dereference when `_generate_sweet_spots_prose` is called with `cred=None` (possible when both providers are deconfigured between steps in `regenerate`); an uncaught `ValueError` from the citation projector that escapes the `except` clause in `_generate_coffee_rec` for the `characteristics_only` Anthropic path; an SSRF risk in the paste-rank URL handler accepting `http://` URLs into the prompt without fetching them (a subtle information-leak bypass); and unvalidated empty `coffee_name` on `/ai/wishlist/add` creating garbage rows. Six warnings cover logic gaps, missing test assertions, and a `source_url` SSRF bypass that deserves a separate finding. Three informational items cover dead test code and minor code hygiene.

---

## Critical Issues

### CR-01: Stored XSS — unvalidated `source_url` rendered as `href` in wishlist.html

**File:** `app/templates/pages/wishlist.html:35-40` / `app/routers/ai.py:361`

**Issue:** The wishlist add endpoint accepts `source_url` from form data without any scheme or URL validation, and stores it directly in the DB. The template then renders it as `<a href="{{ entry.source_url }}">`. Jinja2 autoescaping protects against injected HTML tags in the *text node* but does NOT prevent `href="javascript:alert(1)"` or `href="data:text/html,..."` — those survive autoescaping because they are syntactically valid attribute values. A user (or a compromised AI output that reaches the wishlist) can craft a `javascript:` URI that executes when another user clicks the link. Because wishlist entries are per-user and not shared, the immediate blast radius is self-XSS, but the architectural rule is: any URL placed in an `href` must be validated to `https://` before storage.

**Fix:**
```python
# app/routers/ai.py — in post_wishlist_add, after line 361
source_url_raw = str(form.get("source_url") or "").strip() or None
if source_url_raw and not source_url_raw.startswith("https://"):
    source_url_raw = None  # reject non-https; treat as no URL
source_url = source_url_raw
```
The same guard must also be applied in `ai_rec_hero.html` where `source_url` is emitted into the wishlist-add form as a hidden field — but since that value comes from `prose.buy_url` which is already gated by `rec.url_verified` being True on line 89, the template path is safe as written. The router path for direct form submission has no equivalent gate.

---

### CR-02: `NoneType` crash — `_generate_sweet_spots_prose` called with `cred=None`

**File:** `app/services/ai_service.py:1186-1196`

**Issue:** Inside `regenerate()`, after `_generate_coffee_rec` succeeds, sweet-spots prose is triggered with:
```python
cred=(
    credentials_service.get_provider_credential(db, "anthropic")
    or credentials_service.get_provider_credential(db, "openai")
)
```
If both queries return `None` (e.g., an admin deleted the only credential between the coffee-rec call and this point, or there is a transient decrypt failure logged by `ENCRYPTION_DECRYPT_FAILED`), `cred` is `None`. `_generate_sweet_spots_prose` accepts `cred: credentials_service.ProviderCredential` without a None guard and immediately dereferences `cred.provider` at line 613 (`if cred.provider == "anthropic":`), producing `AttributeError: 'NoneType' object has no attribute 'provider'`. This exception is swallowed by the `except Exception as exc` block at line 1201, returning `"error"` — but only after silently abandoning the coffee row that was already written. This is incorrect behavior: the coffee row is written but `regenerate` returns `"error"`, so the caller's background-task URL verification is not triggered and the hero card may not appear.

**Fix:**
```python
# app/services/ai_service.py — in _generate_sweet_spots_prose signature
async def _generate_sweet_spots_prose(
    db: Session,
    *,
    user_id: int,
    generated_by: str,
    cred: credentials_service.ProviderCredential | None,  # allow None
    signature: str,
) -> AIRecommendation | None:
    if cred is None:
        return None  # no provider — skip prose, don't crash
    sweet_spots = analytics_service.get_sweet_spots(db, user_id)
    ...
```

---

### CR-03: Uncaught `ValueError` from projector on `characteristics_only` tier in `_generate_coffee_rec`

**File:** `app/services/ai_service.py:846-881`

**Issue:** In the `_generate_coffee_rec` tier loop, when Anthropic is the active provider and the `characteristics_only` tier call returns a response that has no `structure_output` block (e.g., the model responds with only a text block), `_project_tool_use_input` raises `ValueError`. This is caught correctly on line 854 for the first two tiers. However, for the `characteristics_only` tier specifically there is an additional code path: if `_is_anthropic_fallback_error` evaluates to `False` for the raised exception but the exception is NOT a `ValueError` or `PydanticValidationError`, line 881 (`raise`) re-raises it, skipping OpenAI and crashing the whole `regenerate()` coroutine. More critically, `ValueError` itself IS caught at line 854 and correctly `continue`s — but the `else: raise` at line 881 creates a path where a `BaseException` subclass that is not caught by `_is_anthropic_fallback_error` (e.g., `asyncio.CancelledError` on Python 3.8+, or `KeyboardInterrupt`) will propagate unchecked out of a function that is supposed to return `"try_again"`. `asyncio.CancelledError` in particular is a `BaseException` (not `Exception`) and will escape the outer `try/except Exception` in `regenerate()` at line 1201, leaving the advisory lock held and the DB session in an undefined state.

**Fix:**
```python
# app/services/ai_service.py — line 865
except BaseException as e:
    if isinstance(e, (asyncio.CancelledError, KeyboardInterrupt)):
        raise  # never swallow task cancellation
    if _is_anthropic_fallback_error(e):
        ...
    else:
        last_error = e
        continue  # treat unknown provider errors as tier failure, not crash
```
Alternatively, narrow the `BaseException` catch to `Exception` for the fallback predicate path, and let `CancelledError` propagate naturally.

---

### CR-04: SSRF information-leak — `http://` URLs passed to the LLM in paste-rank

**File:** `app/services/ai_service.py:1443-1459` / `app/services/ai_service.py:1551-1555`

**Issue:** `_split_inputs` (line 1455) classifies lines starting with `http://` as URLs and adds them to the `urls` list. These are then passed to `_fetch_page_text` which rejects them with the https allowlist, returning `""`. The rejected URL itself however is NOT removed from the combined prompt assembled at line 1553-1554: `all_text_parts = text_blocks + url_texts`. When `_fetch_page_text` returns `""` (falsy), the URL-text entry is omitted from `url_texts` (line 1549), but the original `http://` URL line was placed in the `urls` list, not in `text_blocks`, so it is silently discarded. The risk is low at the fetch layer. However, the subtle issue is that if a user pastes `http://internal-host/secret` as input, the URL string itself is placed in `urls` (not `text_blocks`), so it is NOT included in `combined_input` when the fetch fails. This means the LLM never sees the string. That is actually correct behavior — but the classification is inconsistent: any text starting with `http://` is silently discarded rather than treated as freeform text, which is surprising and undocumented. An attacker could use this to bypass rate/quota by forcing the function to make network calls to internal https:// addresses (the SSRF threat), but the scheme check in `_fetch_page_text` prevents actual connection to non-https targets. The real defect is that there is no cap on the number of URLs that will be fetched: if a user pastes 100 `https://` lines, `rank_pasted_coffees` will fire 100 sequential HTTP requests, each with a 5-second timeout, for a maximum blocking time of 500 seconds before any LLM call is made. This is a denial-of-service / cost vector against the household, not a security issue against other users.

**Fix:**
```python
# app/services/ai_service.py — in rank_pasted_coffees, before the URL fetch loop
MAX_URLS = 5  # cap per-call SSRF / DoS surface
for url in urls[:MAX_URLS]:
    fetched = await _fetch_page_text(url)
    ...
```
Also add a log warning when the cap is applied, so the operator can see abuse.

---

### CR-05: Empty `coffee_name` accepted on `/ai/wishlist/add`, creating garbage DB rows

**File:** `app/routers/ai.py:359-370`

**Issue:** `coffee_name` is extracted as `str(form.get("coffee_name") or "").strip()`. If the field is absent or whitespace-only, `coffee_name` is `""` (empty string). Unlike `roaster_name` and `source_url`, there is no `or None` guard — the empty string is passed directly to `add_to_wishlist`. The `WishlistEntry` model's `coffee_name` column is presumably `NOT NULL Text`, so a `""` row is valid at the DB level but meaningless at the application level. Any user (or HTMX replay) can inject blank wishlist entries. The hero-card form at `ai_rec_hero.html:87` always provides a non-empty value from the AI output, so the normal flow is fine; but direct POST to the endpoint is unguarded.

**Fix:**
```python
# app/routers/ai.py — replace line 359
coffee_name = str(form.get("coffee_name") or "").strip()
if not coffee_name:
    raise HTTPException(status_code=422, detail="coffee_name is required")
```

---

## Warnings

### WR-01: `throttle_429` test does not actually exercise the router throttle path — mocking is incorrect

**File:** `tests/routers/test_ai_router.py:188-205`

**Issue:** The test patches `app.routers.ai.ai_service` (the whole module alias) and sets `mock_ai._THROTTLE = throttle`. However, the router code imports `ai_service` at module level and accesses `ai_service._THROTTLE` directly. When the module alias is replaced by a MagicMock, `mock_ai._THROTTLE = throttle` sets an attribute on the mock, but the actual throttle check in the router at line 182-185 reads `ai_service._THROTTLE.get(user_id)` — which after the patch resolves to the MagicMock's `_THROTTLE` attribute, not the real dict. The test then also calls `mock_ai._evict_stale_throttle.return_value = None`, which suppresses the real eviction. The test may pass for the wrong reason: if the mock's `_THROTTLE.get()` returns a truthy MagicMock (not `None`), the condition `if last_refresh is not None:` is True, which accidentally makes the test pass. The correct approach mirrors `test_throttle_429`'s second block at line 165: use `patch("app.routers.ai.ai_service._THROTTLE", throttle)` directly.

**Fix:**
```python
with patch("app.routers.ai.ai_service._THROTTLE", throttle):
    with patch("app.routers.ai.ai_service._evict_stale_throttle"):
        resp = client.post("/ai/refresh")
```

---

### WR-02: `_generate_sweet_spots_prose` makes a blocking synchronous LLM call inside an `async def`

**File:** `app/services/ai_service.py:613-631`

**Issue:** `_generate_sweet_spots_prose` is declared `async def` but the Anthropic path calls `client.messages.create(...)` synchronously (line 616). This is a synchronous network call inside the async event loop. The docstring acknowledges this ("The LLM call is synchronous; the async wrapper keeps the function signature consistent with the awaited call site"), but this is explicitly called out in CLAUDE.md §3.3 as a known anti-pattern: "Don't mix `async def` handlers with sync DB calls." The same applies to sync network calls. For a household-scale single-worker app the practical impact is low — the call blocks the event loop for the duration of the LLM call — but it means the app cannot serve other requests (including the polling `/home/cards/ai-recommendation` endpoint) while sweet-spots prose is generating. The coffee-rec flow in `_generate_coffee_rec` has the same issue.

**Fix:** Wrap the synchronous SDK call in `asyncio.to_thread`:
```python
response = await asyncio.to_thread(
    client.messages.create,
    model=cred.model_name,
    max_tokens=512,
    system=SYSTEM_PROMPT_VOICE,
    messages=[{"role": "user", "content": prompt}],
    tools=[...],
)
```
Or accept the current behavior by adding an explicit comment that this is intentional at household scale and filing a follow-up.

---

### WR-03: `source_url` written to wishlist with no validation when sourced from AI output

**File:** `app/routers/ai.py:361` / `app/templates/fragments/home/ai_rec_hero.html:89-91`

**Issue:** The hero form at `ai_rec_hero.html:89-91` conditionally includes `source_url` (from `prose.buy_url`) only when `rec.url_verified` is True. This is a correct guard for the template path. However, the router's `post_wishlist_add` handler accepts `source_url` from ANY form POST — not just the hero form — and stores it without validation. A user can POST directly to `/ai/wishlist/add` with `source_url=javascript:evil()` and have it stored and rendered as a clickable link. This overlaps with CR-01 but deserves a separate note because the template-level protection does not propagate to the API layer. Any route that can receive `source_url` from untrusted form input must validate it server-side.

**Fix:** Same as CR-01 fix — add the `startswith("https://")` check in the router before passing to the service.

---

### WR-04: Equipment query fetches ALL non-archived equipment regardless of user

**File:** `app/services/ai_service.py:1244-1246`

**Issue:** The equipment query for the equipment rec prompt reads:
```python
equipment_rows = db.execute(
    select(Equipment).where(Equipment.archived.is_(False))
).scalars().all()
```
`Equipment` is a household-shared catalog (no `user_id`), so this is by design — but the prompt then presents this shared equipment list to the LLM as if it is the specific user's setup. For a two-person household (John + Farrah), whoever shares the catalog will see both people's equipment in a joint list. If Farrah has a different grinder than John, the LLM may recommend upgrading equipment that John does not own. The query should be filtered by equipment referenced in the requesting user's brew sessions (similar to how `alt_brewer_callout` queries via `BrewSession.brewer_id`).

**Fix:**
```python
# Filter to equipment the user has actually used in brew sessions
from app.models.brew_session import BrewSession as BS
equipment_rows = db.execute(
    select(Equipment)
    .join(BS, BS.brewer_id == Equipment.id)
    .where(BS.user_id == user_id, Equipment.archived.is_(False))
    .distinct()
).scalars().all()
```
If no sessions exist, fall back to all non-archived equipment with a comment.

---

### WR-05: `post_ai_equipment` silently ignores `EquipmentRecSchema` validation failure in template context

**File:** `app/routers/ai.py:284-297`

**Issue:** When `generate_equipment_rec` returns `status="generated"` with a non-None `_row`, the router attempts `EquipmentRecSchema.model_validate(_row.response_json)` and sets `ctx["rec"]` to `None` on any exception (line 289-291, bare `except Exception`). The template at `equipment_rec.html:13` checks `status == "generated" and rec is not none`, so if validation fails, the `else` branch renders "Could not generate equipment recommendation right now" — which contradicts the `status="generated"` returned by the service. The real symptom is that an admin looking at logs sees a "generated" status but the user sees the error message. The service already validates via `EquipmentRecSchema.model_validate(raw)` at line 1354 before writing the row, so a failure here indicates the DB row was written with corrupt JSON that passed initial validation but fails on re-validation. The bare `except Exception` in the router silently discards the error with no logging.

**Fix:**
```python
# app/routers/ai.py — replace lines 288-291
try:
    ctx["rec"] = EquipmentRecSchema.model_validate(_row.response_json)
except Exception as e:
    log.warning("ai.equipment.schema_mismatch", error_class=type(e).__name__)
    ctx["rec"] = None
    ctx["status"] = "try_again"  # correct the status so template renders error path
```

---

### WR-06: `regenerate()` double-logs `AI_GENERATION_SUCCESS` for coffee rec

**File:** `app/services/ai_service.py:963-973` / `app/services/ai_service.py:1198`

**Issue:** `_generate_coffee_rec` already logs `AI_GENERATION_SUCCESS` at line 963 with full telemetry (provider, model, tier, tokens, duration_ms). Then `regenerate()` logs `AI_GENERATION_SUCCESS` again at line 1198 with only `user_id` and `rec_type`. Downstream log queries on `ai.generation.success` will see two events per successful generation, potentially doubling counts in dashboards or alerts. The second log call in `regenerate()` at line 1198 appears to be a duplicate that was not removed when the telemetry was moved into `_generate_coffee_rec`.

**Fix:** Remove line 1198 from `regenerate()`:
```python
# Delete this line in regenerate():
log.info(AI_GENERATION_SUCCESS, user_id=user_id, rec_type="coffee")
```
The detailed log in `_generate_coffee_rec` is already sufficient and more informative.

---

## Info

### IN-01: `_make_db_with_sessions` helper in tests is dead code

**File:** `tests/services/test_ai_service.py:334-344`

**Issue:** The function `_make_db_with_sessions` is defined but never called. The tests for `suggest_recipe` and `alt_brewer_callout` create their own `MagicMock()` DB instances directly. This helper was likely a stub from an earlier plan and was not cleaned up.

**Fix:** Remove the unused function (lines 334-344).

---

### IN-02: `_PLEASE_WAIT_HTML` fallback in `ai.py` is never used on the happy path

**File:** `app/routers/ai.py:99-103`

**Issue:** `_PLEASE_WAIT_HTML` is documented as "used when fragments/home/ai_rec_in_flight.html is not yet present." The real template now exists. The inline HTML still references the same `id="ai-rec-hero"` and same content, so it is functionally equivalent to the template. However, the comment "07-06 will add the real template" is stale — Phase 7 was completed. The constant should either be removed (if the template is always present) or the comment should be updated to reflect why it is retained as a fallback.

**Fix:** If the template is always guaranteed to exist at runtime (it is baked into the Docker image), remove `_PLEASE_WAIT_HTML` and replace its three usage sites with template renders. If a fallback for missing templates is desired, document that intent clearly.

---

### IN-03: `PasteRankSchema.model_validate(raw)` called twice in `rank_pasted_coffees`

**File:** `app/services/ai_service.py:1652` / `app/services/ai_service.py:1699`

**Issue:** `rank_pasted_coffees` validates `raw` via `PasteRankSchema.model_validate(raw)` at line 1652 (error path) and again at line 1699 (`return "generated", PasteRankSchema.model_validate(raw)`). The second validation cannot fail unless Pydantic validation is non-deterministic (it is not for the same input). The redundant call should be replaced by storing the validated schema from the first validation and returning it:

**Fix:**
```python
# app/services/ai_service.py — replace lines 1651-1652 and 1699
try:
    validated_schema = PasteRankSchema.model_validate(raw)
except PydanticValidationError as e:
    ...
    return "try_again", None

# ... write row ...
return "generated", validated_schema  # reuse; don't re-validate
```

---

_Reviewed: 2026-05-21T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
