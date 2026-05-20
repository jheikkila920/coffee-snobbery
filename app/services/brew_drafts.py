"""One-draft-per-user store — the brew-form localStorage server backstop.

BREW-06/07 + MX-5: the brew form autosaves to ``localStorage`` as the primary
draft store, but iOS Safari ITP evicts ``localStorage`` after 7 days of
non-installed inactivity. This service is the server backstop: exactly one row
per user (``brew_drafts.user_id`` UNIQUE), an upsert-on-blur write, and a
clear-on-submit / clear-on-logout delete.

Sync :class:`Session` + single commit + structlog audit, mirroring
:mod:`app.services.equipment` and the single-key write idea in
:mod:`app.services.settings`. The ``payload`` is opaque JSON form state (per-
field values, per-field touched-state, the D-02 advanced-disclosure open flag);
this service NEVER interprets it — the form schema gates the values when the
draft is reconciled and submitted (the router enforces that drafts apply to
``/brew/new`` only; the edit form is not draft-backed).

Per-user keying is the security property (T-05-08): every operation is keyed by
the server-derived ``by_user_id``, so a draft can never leak across users.
"""

from __future__ import annotations

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.events import BREW_DRAFT_CLEARED, BREW_DRAFT_SAVED
from app.models.brew_draft import BrewDraft

log = structlog.get_logger(__name__)


def upsert_draft(db: Session, *, by_user_id: int, payload: dict) -> BrewDraft:
    """Insert or update the single draft row for *by_user_id*.

    Atomic ``INSERT ... ON CONFLICT (user_id) DO UPDATE`` against the UNIQUE
    ``user_id`` — one round trip, no read-then-write race. ``updated_at`` is
    stamped on the update branch. Commits, emits ``brew.draft.saved``, and
    returns the live row.
    """
    stmt = (
        pg_insert(BrewDraft)
        .values(user_id=by_user_id, payload=payload)
        .on_conflict_do_update(
            index_elements=[BrewDraft.user_id],
            set_={"payload": payload, "updated_at": func.now()},
        )
        .returning(BrewDraft.id)
    )
    db.execute(stmt)
    db.commit()
    row = db.execute(select(BrewDraft).where(BrewDraft.user_id == by_user_id)).scalar_one()
    log.info(BREW_DRAFT_SAVED, user_id=by_user_id)
    return row


def get_draft(db: Session, *, by_user_id: int) -> dict | None:
    """Return the user's stored draft payload, or ``None`` when no draft exists."""
    return db.execute(
        select(BrewDraft.payload).where(BrewDraft.user_id == by_user_id)
    ).scalar_one_or_none()


def clear_draft(db: Session, *, by_user_id: int) -> None:
    """Delete the user's draft row; safe no-op when none exists.

    Called by the router on successful submit and on logout (MX-5 server side).
    Always commits and emits ``brew.draft.cleared`` (the event records the
    clear intent even when the DELETE affected zero rows).
    """
    db.execute(delete(BrewDraft).where(BrewDraft.user_id == by_user_id))
    db.commit()
    log.info(BREW_DRAFT_CLEARED, user_id=by_user_id)


__all__ = ["clear_draft", "get_draft", "upsert_draft"]
