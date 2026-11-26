"""Tests for app/routers/auth.py: login, token validation and role checks."""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.routers.auth import get_current_user, login, require_role

MODULE = "app.routers.auth"
PASSWORD = "Password@123"
HASHED = hash_password(PASSWORD)


class LoginForm:
    def __init__(self, username, password):
        self.username = username
        self.password = password


def _user_row(user_id=1, active=True):
    return (user_id, "Anita Sharma", "anita.clerk@example.com", HASHED, active)


# ---------------------------------------------------------------- login

def test_login_clerk_returns_bearer_token_with_clerk_role(fake_db):
    conn = fake_db(MODULE, results=[_user_row(user_id=3)])

    response = login(LoginForm("anita.clerk@example.com", PASSWORD))

    assert response["token_type"] == "bearer"
    payload = jwt.decode(response["access_token"], settings.JWT_SECRET_KEY, algorithms=["HS256"])
    assert payload == {**payload, "sub": "3", "role": "clerk"}
    assert conn.closed


def test_login_falls_through_to_approvers_table(fake_db):
    # clerks: no match, approvers: match
    fake_db(MODULE, results=[None, _user_row(user_id=7)])

    response = login(LoginForm("rahul.approver@example.com", PASSWORD))

    payload = jwt.decode(response["access_token"], settings.JWT_SECRET_KEY, algorithms=["HS256"])
    assert payload["role"] == "approver"
    assert payload["sub"] == "7"


def test_login_falls_through_to_auditors_table(fake_db):
    fake_db(MODULE, results=[None, None, _user_row(user_id=9)])

    response = login(LoginForm("meera.auditor@example.com", PASSWORD))

    payload = jwt.decode(response["access_token"], settings.JWT_SECRET_KEY, algorithms=["HS256"])
    assert payload["role"] == "auditor"


def test_login_unknown_email_returns_401(fake_db):
    conn = fake_db(MODULE, results=[None, None, None])

    with pytest.raises(HTTPException) as exc:
        login(LoginForm("nobody@example.com", PASSWORD))

    assert exc.value.status_code == 401
    assert conn.closed


def test_login_wrong_password_returns_401(fake_db):
    fake_db(MODULE, results=[_user_row()])

    with pytest.raises(HTTPException) as exc:
        login(LoginForm("anita.clerk@example.com", "wrong"))

    assert exc.value.status_code == 401


def test_login_inactive_user_returns_403(fake_db):
    fake_db(MODULE, results=[_user_row(active=False)])

    with pytest.raises(HTTPException) as exc:
        login(LoginForm("anita.clerk@example.com", PASSWORD))

    assert exc.value.status_code == 403


# ---------------------------------------------------------------- get_current_user

def test_get_current_user_returns_profile_for_valid_token(fake_db):
    conn = fake_db(MODULE, results=[(3, "Anita Sharma", "anita.clerk@example.com")])

    user = get_current_user(create_access_token(3, "clerk"))

    assert user == {"id": 3, "name": "Anita Sharma", "email": "anita.clerk@example.com", "role": "clerk"}
    sql, params = conn.executed[0]
    assert "from clerks" in sql.lower()
    assert params == (3,)


@pytest.mark.parametrize(
    "role, table",
    [("approver", "approvers"), ("auditor", "auditors")],
)
def test_get_current_user_queries_table_for_role(fake_db, role, table):
    conn = fake_db(MODULE, results=[(5, "Name", "x@example.com")])

    user = get_current_user(create_access_token(5, role))

    assert user["role"] == role
    assert f"from {table}" in conn.executed[0][0].lower()


def test_get_current_user_rejects_garbage_token(fake_db):
    fake_db(MODULE)
    with pytest.raises(HTTPException) as exc:
        get_current_user("not-a-jwt")
    assert exc.value.status_code == 401


def test_get_current_user_rejects_expired_token(fake_db):
    fake_db(MODULE)
    expired = jwt.encode(
        {"sub": "1", "role": "clerk", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.JWT_SECRET_KEY,
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as exc:
        get_current_user(expired)
    assert exc.value.status_code == 401


def test_get_current_user_rejects_unknown_role(fake_db):
    conn = fake_db(MODULE)
    with pytest.raises(HTTPException) as exc:
        get_current_user(create_access_token(1, "admin"))
    assert exc.value.status_code == 401
    assert conn.executed == []  # rejected before touching the DB


def test_get_current_user_rejects_non_numeric_subject(fake_db):
    fake_db(MODULE)
    token = jwt.encode(
        {"sub": "abc", "role": "clerk", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        settings.JWT_SECRET_KEY,
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as exc:
        get_current_user(token)
    assert exc.value.status_code == 401


def test_get_current_user_rejects_deleted_user(fake_db):
    conn = fake_db(MODULE, results=[None])
    with pytest.raises(HTTPException) as exc:
        get_current_user(create_access_token(99, "clerk"))
    assert exc.value.status_code == 401
    assert conn.closed


# ---------------------------------------------------------------- require_role

def test_require_role_allows_matching_role():
    checker = require_role("clerk")
    user = {"id": 1, "role": "clerk"}
    assert checker(current_user=user) is user


@pytest.mark.parametrize("role", ["approver", "auditor"])
def test_require_role_blocks_other_roles(role):
    checker = require_role("clerk")
    with pytest.raises(HTTPException) as exc:
        checker(current_user={"id": 1, "role": role})
    assert exc.value.status_code == 403
