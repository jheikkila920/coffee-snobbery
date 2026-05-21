# Deferred Items — quick task 260519-ql9

Out-of-scope discoveries logged during execution. NOT fixed (per executor scope boundary:
only auto-fix issues directly caused by the current task's changes).

| Category | Item | File | Detail |
|----------|------|------|--------|
| Lint (pre-existing) | `S110` `try`-`except`-`pass` | `tests/phase_04/test_routers_flavor_notes.py` (`test_name_unique_citext_returns_validation_error`) | Pre-existing on the committed file (verified via `git stash` + `ruff check`). The block has `# noqa: BLE001` but not `# noqa: S110`. Outside this task's scope — the test was neither authored nor modified here. Phase 12 (the "tighten ruff" seat per pyproject.toml comment) or a future cleanup should add `# noqa: S110` or restructure the block. |
