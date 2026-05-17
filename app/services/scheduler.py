"""APScheduler integration — owned by Phase 8."""

# IMPORTANT: This module — and the uvicorn process hosting it — MUST run as a
#   single worker (uvicorn flag: --workers 1). APScheduler is in-process;
#   module-level AI locks live in this process. A future `--workers 4` would
#   fire every nightly job 4x and bill 4x the AI cost
#   (PROJECT.md row 16; CONTEXT.md <specifics>).
#
# This file is location #2 of three places that loudly state the single-worker
# rule. The other two are:
#   (1) entrypoint.sh — comment block above the uvicorn invocation
#   (3) README.md     — deployment section
#
# Anyone trying to add `--workers 4` trips over this note three times before
# they succeed. If you remove or weaken this comment, restore one of the other
# two locations to compensate so the count of warnings stays at three.

# Phase 8 will replace this file's body with the actual APScheduler wiring:
# SQLAlchemyJobStore, misfire_grace_time=3600, coalesce=True (PITFALLS §AI/Cost),
# and lifespan hooks in app/main.py that call scheduler.start() / shutdown().
