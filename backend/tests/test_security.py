"""Tests for app/core/security.py (password hashing and JWT creation)."""
from datetime import datetime, timezone

import jwt
import pytest

from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password


def test_hash_password_does_not_store_plain_text():
    hashed = hash_password("Password@123")
    assert hashed != "Password@123"
    assert hashed.startswith("$argon2")


def test_hash_password_is_salted():
    assert hash_password("same") != hash_password("same")


def test_verify_password_accepts_correct_password():
    hashed = hash_password("Password@123")
    assert verify_password("Password@123", hashed) is True


@pytest.mark.parametrize("attempt", ["password@123", "Password@1234", ""])
def test_verify_password_rejects_wrong_password(attempt):
    hashed = hash_password("Password@123")
    assert verify_password(attempt, hashed) is False


def _decode(token):
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def test_access_token_contains_subject_and_role():
    payload = _decode(create_access_token(42, "clerk"))
    assert payload["sub"] == "42"  # JWT subject must be a string
    assert payload["role"] == "clerk"


def test_access_token_expires_after_configured_minutes():
    before = datetime.now(timezone.utc).timestamp()
    payload = _decode(create_access_token(1, "approver"))
    expected = before + settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    assert abs(payload["exp"] - expected) < 5


def test_access_token_signed_with_other_key_is_rejected():
    token = create_access_token(1, "clerk")
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, "some-other-secret-key-32-bytes-long!!", algorithms=["HS256"])
