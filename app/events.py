"""Canonical structured-log event names — owned by Phase 1.

CONTEXT D-14 establishes a single event taxonomy: every structured log line
emitted by application code uses a constant from this module rather than a
free-form string. This gives us three properties:

1. **Greppable enforcement** — CI / reviewers can grep ``app/`` for the literal
   string ``"csp.violation"`` and any hit outside this file is a violation of
   the convention.
2. **Stable schema** — log shipping / alerting downstream (any future ELK /
   Loki / Vector pipeline) can pin alerts to a known set of event names that
   only change in one place.
3. **Refactor safety** — renaming an event (e.g. ``csp.violation`` ->
   ``security.csp.violation``) touches one constant; every emit site picks up
   the new value automatically.

Adding a new event: add the constant here with a short docstring; do NOT
import this module from anywhere outside the emit site (avoids a knock-on
import graph that complicates Phase 0 boot ordering).

This module is owned by Phase 1 collectively — Plan 02 (request_context),
Plan 03 (csp_report), Plan 04 (sessions / csrf), Plan 06 (fragment cache),
Plan 07 (rate-limit), Plan 08 (debug proxy) each contribute constants here.
Plan 03 ships the file with ``CSP_VIOLATION`` so the ``/csp-report`` handler
can land without waiting for the other Wave 1 plans.
"""

from __future__ import annotations

# CSP violation report — emitted by ``app.routers.csp_report`` on every POST
# to ``/csp-report`` (one log line per report; the dual-content-type handler
# emits one event per item in the ``application/reports+json`` array).
# Event fields (per D-06): ``blocked_uri``, ``violated_directive``, ``line``,
# ``source_file``, ``ip``. Other fields in the browser-supplied payload are
# stripped before emission to limit PII surface (threat T-03-07).
CSP_VIOLATION: str = "csp.violation"
