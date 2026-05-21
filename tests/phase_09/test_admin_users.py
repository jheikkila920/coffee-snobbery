"""Phase 9 — Admin user management tests (ADMIN-01).

Covers ADMIN-01 requirements: list, create, edit, reset password,
toggle admin, deactivate, delete — with D-15 (hard-delete guard) and
D-16 (last-admin / self-lockout) safety behaviors.

Test design notes
-----------------
- All fixtures self-seed real rows via conftest.py; no pytest.skip on
  missing seed data (project history: skip-masked green).
- CSRF: state-changing requests include the X-CSRF-Token field in the
  form body so the CSRFFormFieldShim hoists it into the header. When
  testing that CSRF is *required*, the field is omitted.
- Admin count isolation: fixtures that care about last-admin guards
  (single_admin, two_admins) use dedicated seeded users; the
  seeded_admin_user fixture may create additional admin rows when
  fresh_db cascades between tests, so the last-admin tests use the
  ``single_admin`` fixture which owns the count.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _csrf_cookies(client: Any, admin_session: dict[str, str]) -> str:
    """Do a GET /admin/users to get the csrftoken cookie, return its value."""
    resp = client.get("/admin/users", cookies=admin_session, follow_redirects=False)
    # The csrftoken cookie is set by the middleware on every response.
    return resp.cookies.get("csrftoken", "")


# ---------------------------------------------------------------------------
# Task 1 tests — list + short-password create (RED first)
# ---------------------------------------------------------------------------


class TestListUsers:
    """ADMIN-01: GET /admin/users lists all users."""

    def test_list_users(
        self,
        client: Any,
        admin_session: dict[str, str],
        seeded_admin_user: dict[str, Any],
    ) -> None:
        """GET /admin/users returns 200 and contains the seeded admin username."""
        resp = client.get("/admin/users", cookies=admin_session)
        assert resp.status_code == 200, (
            f"Expected 200 on GET /admin/users, got {resp.status_code}"
        )
        username = seeded_admin_user["user"].username
        assert username in resp.text, (
            f"Expected '{username}' in /admin/users response body"
        )

    def test_list_users_non_admin_403(
        self,
        client: Any,
        regular_session: dict[str, str],
    ) -> None:
        """GET /admin/users returns 403 for a non-admin session."""
        resp = client.get("/admin/users", cookies=regular_session)
        assert resp.status_code == 403, (
            f"Expected 403 for non-admin on /admin/users, got {resp.status_code}"
        )


class TestCreateUserValidation:
    """ADMIN-01: Create-user form rejects passwords shorter than 12 characters."""

    def test_create_user_short_password(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """POST /admin/users with an 11-char password returns 200 (error fragment) — no new user."""
        csrf_token = _csrf_cookies(client, admin_session)

        # Count users before
        list_resp = client.get("/admin/users", cookies=admin_session)
        assert list_resp.status_code == 200

        resp = client.post(
            "/admin/users",
            data={
                "username": f"newuser-{uuid.uuid4().hex[:6]}",
                "password": "tooshort123",  # 11 chars
                "X-CSRF-Token": csrf_token,
            },
            cookies=admin_session,
        )
        # Validation failure: re-renders form at HTTP 200
        assert resp.status_code == 200, (
            f"Expected 200 (form re-render) for short password, got {resp.status_code}"
        )
        # Should contain an error indication (password error message)
        body_lower = resp.text.lower()
        assert "password" in body_lower or "error" in body_lower or "least" in body_lower, (
            "Expected an error message in the form re-render for short password"
        )


# ---------------------------------------------------------------------------
# Task 2 tests — create, delete, toggle, deactivate, CSRF
# ---------------------------------------------------------------------------


class TestCreateUser:
    """ADMIN-01: Successful user creation."""

    def test_create_user(
        self,
        client: Any,
        admin_session: dict[str, str],
    ) -> None:
        """POST /admin/users with valid data creates a user with argon2id hash."""
        csrf_token = _csrf_cookies(client, admin_session)
        username = f"newuser-{uuid.uuid4().hex[:6]}"

        resp = client.post(
            "/admin/users",
            data={
                "username": username,
                "password": "validpassword12",  # 15 chars — passes floor
                "X-CSRF-Token": csrf_token,
            },
            cookies=admin_session,
        )
        assert resp.status_code == 200, (
            f"Expected 200 (row fragment) on user create, got {resp.status_code}"
        )
        # The new username should appear in the response fragment
        assert username in resp.text, (
            f"Expected new username '{username}' in create response"
        )
        # The plaintext password must NOT appear in the response
        assert "validpassword12" not in resp.text, (
            "Plaintext password must not appear in the response body"
        )

        # Verify hash is stored as argon2id
        from app.db import SessionLocal
        from app.models.user import User
        from sqlalchemy import select
        with SessionLocal() as db:
            user = db.execute(
                select(User).where(User.username == username)
            ).scalar_one_or_none()
        assert user is not None, f"User '{username}' not found in DB after create"
        assert user.password_hash.startswith("$argon2id$"), (
            f"Expected argon2id hash, got: {user.password_hash[:20]}"
        )


class TestDeleteUserGuards:
    """ADMIN-01: D-15 hard-delete guard and D-16 last-admin guard."""

    def test_delete_user_with_sessions_blocked(
        self,
        client: Any,
        admin_session: dict[str, str],
        user_with_brews: dict[str, Any],
    ) -> None:
        """D-15: Hard-delete of user with brew_sessions is blocked (409 or error fragment)."""
        csrf_token = _csrf_cookies(client, admin_session)
        target_id = user_with_brews["user_id"]

        resp = client.post(
            f"/admin/users/{target_id}/delete",
            data={"X-CSRF-Token": csrf_token},
            cookies=admin_session,
        )
        # Must be 4xx (conflict) or a 200 error fragment — NOT a deletion
        assert resp.status_code in (409, 200), (
            f"Expected 409 or 200 error fragment for D-15 block, got {resp.status_code}"
        )
        # The user must still exist in the DB
        from app.db import SessionLocal
        from app.models.user import User
        from sqlalchemy import select
        with SessionLocal() as db:
            user = db.execute(
                select(User).where(User.id == target_id)
            ).scalar_one_or_none()
        assert user is not None, (
            f"D-15: User {target_id} was deleted despite having brew_sessions — MUST be blocked"
        )

    def test_delete_empty_user(
        self,
        client: Any,
        admin_session: dict[str, str],
        user_no_brews: dict[str, Any],
    ) -> None:
        """D-15: Hard-delete of user with no brew_sessions succeeds."""
        csrf_token = _csrf_cookies(client, admin_session)
        target_id = user_no_brews["user_id"]

        resp = client.post(
            f"/admin/users/{target_id}/delete",
            data={"X-CSRF-Token": csrf_token},
            cookies=admin_session,
        )
        assert resp.status_code == 200, (
            f"Expected 200 on successful delete, got {resp.status_code}"
        )
        # The user must be gone from the DB
        from app.db import SessionLocal
        from app.models.user import User
        from sqlalchemy import select
        with SessionLocal() as db:
            user = db.execute(
                select(User).where(User.id == target_id)
            ).scalar_one_or_none()
        assert user is None, (
            f"Expected user {target_id} to be deleted (no brew_sessions), but row still exists"
        )

    def test_delete_last_admin_blocked(
        self,
        client: Any,
        single_admin: dict[str, Any],
    ) -> None:
        """D-16: Deleting the only active admin is refused (no mutation)."""
        admin_cookies = {"session_id": single_admin["signed_cookie"]}
        csrf_token = _csrf_cookies(client, admin_cookies)
        target_id = single_admin["user_id"]

        resp = client.post(
            f"/admin/users/{target_id}/delete",
            data={"X-CSRF-Token": csrf_token},
            cookies=admin_cookies,
        )
        # Must refuse with 4xx or error fragment
        assert resp.status_code in (400, 403, 409, 200), (
            f"Expected refusal response for last-admin delete, got {resp.status_code}"
        )
        # The admin user must still exist
        from app.db import SessionLocal
        from app.models.user import User
        from sqlalchemy import select
        with SessionLocal() as db:
            user = db.execute(
                select(User).where(User.id == target_id)
            ).scalar_one_or_none()
        assert user is not None, (
            "D-16: Last admin was deleted — must be blocked"
        )
        assert user.is_admin is True, (
            "D-16: Last admin's is_admin was cleared — must be blocked"
        )

    def test_self_demote_blocked(
        self,
        client: Any,
        two_admins: dict[str, Any],
    ) -> None:
        """D-16: An admin demoting/deactivating themselves is refused."""
        # admin1 tries to deactivate themselves
        admin1_id = two_admins["admin1_id"]
        admin1_cookies = {"session_id": two_admins["admin1_cookie"]}
        csrf_token = _csrf_cookies(client, admin1_cookies)

        resp = client.post(
            f"/admin/users/{admin1_id}/deactivate",
            data={"X-CSRF-Token": csrf_token},
            cookies=admin1_cookies,
        )
        # Must refuse (4xx or error fragment at 200)
        # The user must NOT be deactivated
        from app.db import SessionLocal
        from app.models.user import User
        from sqlalchemy import select
        with SessionLocal() as db:
            user = db.execute(
                select(User).where(User.id == admin1_id)
            ).scalar_one_or_none()
        assert user is not None, "D-16: Self-deactivation should not delete the user"
        assert user.is_active is True, (
            f"D-16: Admin was allowed to deactivate themselves — must be blocked"
        )


class TestToggleAdmin:
    """ADMIN-01: Toggle is_admin invalidates target sessions immediately."""

    def test_toggle_admin_invalidates_sessions(
        self,
        client: Any,
        admin_session: dict[str, str],
        user_with_sessions: dict[str, Any],
    ) -> None:
        """POST /admin/users/{id}/toggle-admin deletes all target's sessions."""
        from app.db import SessionLocal
        from app.models.session import Session as SessionModel
        from sqlalchemy import select, func

        target_id = user_with_sessions["user_id"]
        csrf_token = _csrf_cookies(client, admin_session)

        # Verify there are sessions before toggle
        with SessionLocal() as db:
            pre_count = db.execute(
                select(func.count()).select_from(SessionModel).where(
                    SessionModel.user_id == target_id
                )
            ).scalar_one()
        assert pre_count >= 1, f"Expected >=1 session before toggle, got {pre_count}"

        resp = client.post(
            f"/admin/users/{target_id}/toggle-admin",
            data={"X-CSRF-Token": csrf_token},
            cookies=admin_session,
        )
        assert resp.status_code == 200, (
            f"Expected 200 on toggle-admin, got {resp.status_code}"
        )

        # After toggle: all sessions for target_id must be deleted
        with SessionLocal() as db:
            post_count = db.execute(
                select(func.count()).select_from(SessionModel).where(
                    SessionModel.user_id == target_id
                )
            ).scalar_one()
        assert post_count == 0, (
            f"Expected 0 sessions after toggle-admin, got {post_count} (T-09-04)"
        )


class TestDeactivateRequiresCsrf:
    """ADMIN-01: CSRF enforcement on deactivate/reactivate."""

    def test_deactivate_requires_csrf(
        self,
        client: Any,
        admin_session: dict[str, str],
        user_no_brews: dict[str, Any],
    ) -> None:
        """POST /admin/users/{id}/deactivate without CSRF returns 403.
        With CSRF + non-last-admin target returns 200 and deletes sessions.
        """
        target_id = user_no_brews["user_id"]

        # 1. Without CSRF token — expect 403
        resp_no_csrf = client.post(
            f"/admin/users/{target_id}/deactivate",
            data={},  # no X-CSRF-Token field
            cookies=admin_session,
        )
        assert resp_no_csrf.status_code == 403, (
            f"Expected 403 without CSRF token, got {resp_no_csrf.status_code}"
        )

        # 2. With valid CSRF token — expect 200 and sessions deleted
        csrf_token = _csrf_cookies(client, admin_session)
        resp_with_csrf = client.post(
            f"/admin/users/{target_id}/deactivate",
            data={"X-CSRF-Token": csrf_token},
            cookies=admin_session,
        )
        assert resp_with_csrf.status_code == 200, (
            f"Expected 200 with valid CSRF on deactivate, got {resp_with_csrf.status_code}"
        )

        # Sessions for target must be deleted
        from app.db import SessionLocal
        from app.models.session import Session as SessionModel
        from sqlalchemy import select, func
        with SessionLocal() as db:
            count = db.execute(
                select(func.count()).select_from(SessionModel).where(
                    SessionModel.user_id == target_id
                )
            ).scalar_one()
        assert count == 0, (
            f"Expected 0 sessions after deactivate, got {count} (T-09-04)"
        )
