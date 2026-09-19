from datetime import timedelta

import pytest
from jwt import InvalidTokenError

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_round_trip_and_wrong_password_rejection() -> None:
    encoded = hash_password("correct horse battery staple")

    assert encoded != "correct horse battery staple"
    assert verify_password("correct horse battery staple", encoded) is True
    assert verify_password("wrong password", encoded) is False


def test_password_hash_does_not_silently_truncate_after_72_bytes() -> None:
    encoded = hash_password("a" * 72 + "x")

    assert verify_password("a" * 72 + "y", encoded) is False


def test_password_hash_supports_unicode_passwords_longer_than_72_bytes() -> None:
    password = "教学督导" * 20

    encoded = hash_password(password)

    assert verify_password(password, encoded) is True


def test_access_token_round_trip() -> None:
    token = create_access_token("user-42", expires_delta=timedelta(minutes=5))

    payload = decode_access_token(token)

    assert payload["sub"] == "user-42"
    assert "exp" in payload


def test_invalid_access_token_is_rejected() -> None:
    with pytest.raises(InvalidTokenError):
        decode_access_token("not-a-valid-token")
