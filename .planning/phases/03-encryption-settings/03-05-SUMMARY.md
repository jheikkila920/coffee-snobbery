---
phase: 03-encryption-settings
plan: 05
subsystem: lifespan
tags: [lifespan, encryption, settings, credentials, startup, sec-08, sec-09]
dependency_graph:
  requires:
    - "app/services/encryption.py:startup_check (Plan 03-02, wave 1)"
    - "app/services/credentials.py:rewrap_if_needed (Plan 03-04, wave 2)"
    - "app/services/settings.py:prewarm_cache (Plan 03-03, wave 1)"
    - "app/db.py:SessionLocal (Phase 0)"
  provides:
    - "Container-startup activation of the encryption + settings substrate (no new module)"
  affects:
    - "Phase 7 AI service: requires the encryption startup_check sentinel to have run before it can decrypt credentials"
    - "Plan 03-06 tests: the test_lifespan rows in Validation Map (rows 22, 26) now have a wired call chain to observe"
tech-stack:
  added: []
  patterns:
    - "Extend an existing FastAPI lifespan async context manager (NOT @app.on_event — deprecated in Starlette 1.0)"
    - "Three sync calls inside an async lifespan body — no await, no asyncio.to_thread"
    - "Single SessionLocal() context manager wrapping both DB-touching calls"
    - "Bare exception propagation — no outer try/except — so uvicorn exits non-zero on startup failure"
key-files:
  created: []
  modified:
    - "app/main.py — lifespan extension + 3 import additions"
decisions:
  - "D-16: locked startup order: encryption_startup_check() → SessionLocal() block { rewrap_if_needed → prewarm_cache }"
  - "T-03-T3 mitigation: encryption_startup_check runs FIRST (before any DB I/O); failure propagates out of lifespan → uvicorn exits non-zero → docker healthcheck flips unhealthy"
  - "T-03-T5 mitigation: rewrap_if_needed runs BEFORE prewarm_cache so the post-rewrap fingerprint is the one cached"
metrics:
  duration_minutes: 12
  tasks_completed: 1
  completed_date: "2026-05-18"
  files_created: 0
  files_modified: 1
---

# Phase 3 Plan 5: Lifespan Wiring Summary

## One-liner

Extends `app/main.py:lifespan` with the three Phase 3 hooks in the
D-16-locked order — `encryption_startup_check()` → `with SessionLocal()
as db: credentials.rewrap_if_needed(db); settings_service.prewarm_cache(db)`
— so every container restart performs the encryption sentinel round-trip,
auto-rewraps ciphertexts if `APP_ENCRYPTION_KEY` changed, and prewarms
the settings cache before any request handler runs.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Extend `app/main.py:lifespan` with the three Phase 3 hooks (D-16 order) | `9530252` | `app/main.py` |

## Exact line ranges of new code

In `app/main.py`:

| Range | Content |
|-------|---------|
| line 75 | `from app.db import SessionLocal, dispose_engine, engine` — `SessionLocal` added alphabetically (was `from app.db import dispose_engine, engine`) |
| lines 88–90 | Three new import lines:<br>`from app.services import credentials`<br>`from app.services import settings as settings_service`<br>`from app.services.encryption import startup_check as encryption_startup_check` |
| lines 138–151 | Updated lifespan docstring documenting D-16 order and the T-03-T3 / T-03-T5 mitigations |
| line 154 | `encryption_startup_check()  # raises EncryptionStartupError -> uvicorn exits non-zero` |
| lines 155–157 | The DB-touching block:<br>`with SessionLocal() as db:`<br>`    credentials.rewrap_if_needed(db)`<br>`    settings_service.prewarm_cache(db)` |
| line 158 | Existing `log.info("app.startup", version=app.version)` — preserved, but now runs AFTER the three hooks (per the plan's "Why this exact placement" rationale) |

## D-16 order — structural confirmation

Lifespan body statement layout (verified by AST — see "Verification" below):

```
0: docstring
1: with engine.connect() as conn:        # Phase 0 SELECT 1 smoke (preserved)
       conn.execute(text("SELECT 1"))
2: encryption_startup_check()            # Phase 3 hook 1 (D-16: FIRST, no DB)
3: with SessionLocal() as db:            # Phase 3 single DB block
       credentials.rewrap_if_needed(db)  # Phase 3 hook 2 (D-16: BEFORE prewarm)
       settings_service.prewarm_cache(db) # Phase 3 hook 3 (D-16: LAST)
4: log.info("app.startup", ...)          # emits AFTER all 3 hooks succeed
5: yield
6: log.info("app.shutdown")
7: dispose_engine()
8: await _async_engine.dispose()
```

Key invariants confirmed:

1. `encryption_startup_check()` is a bare call, NOT inside any `with` block — it does not need a DB session and runs OUTSIDE the `SessionLocal()` context. This is the D-16 fail-fast-before-DB-I/O guarantee.
2. `rewrap_if_needed(db)` and `prewarm_cache(db)` share a single `with SessionLocal() as db:` block — the plan explicitly forbade splitting them across two contexts.
3. No `await` precedes any of the three new calls. All three are sync (D-07 + D-11).
4. No `try/except` wraps any of the three new calls. Failures propagate to uvicorn (T-03-T3 mitigation).
5. The existing Phase 0 `SELECT 1` smoke is preserved before the three new calls — DB reachability is still validated before encryption startup runs.
6. The existing `log.info("app.startup", ...)` is preserved, but now emits AFTER the three hooks. A startup-time encryption failure therefore does NOT emit `app.startup` — the operator-facing log stream shows the chained `EncryptionStartupError` instead.

## Decisions implemented

| ID | Decision | How it lives in `app/main.py` |
|----|----------|-------------------------------|
| D-16 | Locked startup order | `encryption_startup_check()` at line 154 outside any `with`; `with SessionLocal() as db:` at line 155 wrapping `rewrap_if_needed(db)` (line 156) then `prewarm_cache(db)` (line 157) in that exact order |

## Threat Model Disposition

| Threat | Disposition | Implementation |
|--------|-------------|----------------|
| T-03-T3 (silent ciphertext from bad `APP_ENCRYPTION_KEY`) | mitigate | `encryption_startup_check()` is the first new statement after the SELECT-1 smoke. On `EncryptionStartupError`, no `try/except` catches it → propagates out of the async lifespan context manager → uvicorn exits non-zero → docker-compose healthcheck flips the container unhealthy. No DB I/O happens before this point. |
| T-03-T5 (cache holds pre-rewrap fingerprint after rotation) | mitigate | `rewrap_if_needed(db)` is called BEFORE `prewarm_cache(db)` inside the same `SessionLocal()` block — `rewrap_if_needed` commits the new fingerprint to `app_settings.encryption_key_primary_fingerprint`, then `prewarm_cache`'s single `SELECT * FROM app_settings` reads the just-committed value into `_cache`. |

## Verification — automated checks run

1. **AST hook-ordering check** (the exact `<verify><automated>` block from the plan): PASS.
   ```
   OK ordering: startup_check@0 -> rewrap_if_needed@7 -> prewarm_cache@8
   ```
   The indices 0/7/8 are byte-offsets within `ast.walk(lifespan)`'s call list; the relative order (startup < rewrap < prewarm) is what the assertion requires, and it holds.

2. **AST lifespan-body structural check** (statement layout): PASS — the 9-statement structure documented above matches the plan's required placement.

3. **`python -m py_compile app/main.py`** → exit 0 (clean syntax).

4. **`ruff check app/main.py`** → `All checks passed!` — no F-401 unused imports, no E-501 line-length, no I001 isort violations.

5. **`ruff check --select I app/main.py`** → `All checks passed!` — the import additions are alphabetized within the `from app.X import Y` block (alphabetical position: `from app.routers ...` → `from app.services import credentials` → `from app.services import settings as settings_service` → `from app.services.encryption import ...` → `from app.templates_setup import templates`).

6. **`grep -n "await " app/main.py | grep -E "encryption_startup_check|rewrap_if_needed|prewarm_cache"`** → empty. No `await` precedes any of the three new calls.

7. **`grep -n "try:" app/main.py`** between line 138 and line 162 → only the existing `try:` inside `/healthz` (which is OUTSIDE the lifespan body and unrelated). No `try/except` wraps the three new calls.

8. **Post-commit deletion check** — `git diff --diff-filter=D --name-only HEAD~1 HEAD` → empty (no files deleted by the commit).

## Acceptance criteria — verification status

| Plan acceptance row | Status | Evidence |
|---------------------|--------|----------|
| Validation Map row 26: three calls run in D-16 order | PASS (AST) | AST ordering check above: startup@0 → rewrap@7 → prewarm@8 |
| `encryption_startup_check()` is the FIRST line after the existing `SELECT 1` smoke | PASS | Line 154 immediately follows lines 152–153 (the `with engine.connect() as conn: conn.execute(text("SELECT 1"))` block); no other statement intervenes |
| The three calls are inside the SAME `with SessionLocal() as db` block (except `startup_check` which doesn't need a session) | PASS | Single `With` AST node at body[3]; its body contains exactly two `Expr` statements (`rewrap_if_needed(db)` then `prewarm_cache(db)`) |
| No `try/except` wraps the three new calls | PASS | grep confirms no `try:` between line 138 and line 162 |
| No `await` precedes any of the three new calls | PASS | grep confirms no `await ` token on lines 154, 156, or 157 |
| `ruff check app/main.py` clean | PASS | `All checks passed!` |
| Import additions are alphabetized within the existing `from app.X import Y` block | PASS | `ruff check --select I app/main.py` → no I001 violations |
| Docker-compose health — bad `APP_ENCRYPTION_KEY` causes container to exit non-zero | DEFERRED (manual) | Per the plan's acceptance text: "this acceptance can be confirmed manually per Validation Map's Manual-Only Verifications section; the AST + ordering check above is the automated proof." The AST proof is in place; the live container check is the responsibility of Validation Map / Plan 03-06. |

## Why ruff format check was not run as a gate

`ruff format --check app/main.py` reports `1 file would be reformatted`, but the reformat target is the **pre-existing** `compute_tailwind_css_path` function (lines 119–122), not any line touched by this plan. Stashing the change confirms the format diff is present at base commit `a5b7906` independent of any Plan 03-05 edit. Per the executor `<SCOPE BOUNDARY>` rule ("Only auto-fix issues DIRECTLY caused by the current task's changes"), this is out of scope. Applying `ruff format` here would silently reformat unrelated lines outside the plan's `files_modified` declaration — left for a future opportunistic cleanup or a dedicated `chore(format)` plan. `ruff check app/main.py` (the gate the plan actually specifies) is clean.

## Deviations from plan

**None.** Plan executed exactly as written.

The only mechanical adjustment was ruff I001 splitting the combined import `from app.services import credentials, settings as settings_service` into two adjacent lines:

```python
from app.services import credentials
from app.services import settings as settings_service
```

Identical resolution; no semantic change. The 03-04 SUMMARY documents the same split for the same reason ("ruff's I001 isort enforcement splits combined imports when one member uses `import X` syntax and another uses `import X as Y`").

The lifespan docstring was extended (rather than left as-is) to document the D-16 ordering and the two threat mitigations. The plan's `<action>` did not forbid this; the analog patterns (PATTERNS.md, SUMMARY of 03-02) all keep the docstring synchronized with the body it documents.

## Authentication gates

None. Plan was fully autonomous.

## Known stubs

None. Every wired call points at a fully-implemented function from Plans 03-02 / 03-03 / 03-04.

## Threat flags

None. The wiring activates already-mitigated surfaces (the three service modules); it does not introduce new endpoints, auth paths, file access, or schema changes.

## Worktree setup note

This worktree's HEAD started on the stale Phase 1 commit `56d3091` (the worktree was provisioned before Phase 2 + Phase 3 waves 1/2 completed on base). The merge-base check (`git merge-base --is-ancestor 56d3091 a5b79060`) returned ancestor, so the worktree was fast-forwarded with `git merge --ff-only a5b79060ce7c6688fde64454f00aeda45edb5613` — the expected base committed by Phase 3 Wave 2 (Plans 03-02 + 03-03 + 03-04, plus the post-wave tracking-doc update). No code modifications were needed; the fast-forward brought the entire Phase 2 + Wave 1 + Wave 2 history into the worktree cleanly. From base `a5b7906`, this plan adds exactly one commit (`9530252`).

## Self-Check: PASSED

- File `app/main.py` modified (lifespan extension + 3 imports): FOUND.
- Commit `9530252` on branch `worktree-agent-a17bc54c7bdde315d`: FOUND (`git log --oneline -3` shows it as HEAD, parent `a5b7906`).
- AST hook-ordering check (from the plan's `<verify><automated>` block): PASS — `OK ordering: startup_check@0 -> rewrap_if_needed@7 -> prewarm_cache@8`.
- Lifespan body structural layout (3 hooks correctly placed): PASS — statement types `Expr-With-Expr-With-Expr-Expr-Expr-Expr-Expr` with `encryption_startup_check` outside any `With` and the two DB calls inside the single `SessionLocal()` `With`.
- `python -m py_compile app/main.py`: exit 0.
- `ruff check app/main.py`: `All checks passed!`.
- `git diff --diff-filter=D --name-only HEAD~1 HEAD` (post-commit deletion check): empty.
