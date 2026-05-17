"""Wave 0 stub for AUTH-05 session helpers (regenerate_session).

Covers the per-task verification map row for AUTH-05 from
``.planning/phases/01-middleware/01-VALIDATION.md``:

- ``test_regenerate`` — regenerate_session(db, old_id, user_id) deletes the
                        old row, mints a new UUID, inserts a fresh row.

Plan 04 lands ``app.services.sessions.regenerate_session``. Until then the
test skips on ImportError; once the helper exists, the test uses the
``db_session`` fixture (which itself skips until the async session factory
exists — see ``tests/conftest.py``).
"""

from __future__ import annotations

import uuid

import pytest


def test_regenerate(db_session) -> None:
    """AUTH-05 / D-10: regenerate_session deletes old row + mints new UUID."""
    try:
        from app.services.sessions import regenerate_session
    except ImportError:
        pytest.skip(
            "Wave 1 dependency: app.services.sessions.regenerate_session (Plan 04)"
        )
    # Pre-populate an "old" session row keyed by a known UUID; Wave 1
    # implementation will define the model. We cannot inspect the row shape
    # here without the model, so we exercise the helper end-to-end against
    # whatever fixture-managed DB session the conftest yields.
    old_id = uuid.uuid4()
    user_id = uuid.uuid4()
    # Helper is expected to: (a) DELETE the row keyed by old_id, (b) INSERT
    # a fresh row with same user_id + a freshly minted UUID, (c) return the
    # new UUID string-or-uuid.
    new_id = regenerate_session(db_session, str(old_id), str(user_id))
    assert new_id is not None
    assert str(new_id) != str(old_id), (
        f"regenerate_session must mint a different UUID, got same: {new_id}"
    )
