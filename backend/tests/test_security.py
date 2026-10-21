"""安全组件测试：密码哈希与 JWT 访问令牌。

覆盖要点：
- 密码哈希不可逆、可校验、能区分错误密码；
- 超过 bcrypt 72 字节限制的密码不被静默截断（避免"前缀相同即通过"的安全隐患）；
- 含中文等 Unicode 字符的长密码可正常哈希与校验；
- JWT 令牌签发/解码往返一致，非法令牌被明确拒绝。
"""

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
    """正确密码校验通过、错误密码被拒绝，且哈希结果不明文保存密码。"""
    encoded = hash_password("correct horse battery staple")

    assert encoded != "correct horse battery staple"
    assert verify_password("correct horse battery staple", encoded) is True
    assert verify_password("wrong password", encoded) is False


def test_password_hash_does_not_silently_truncate_after_72_bytes() -> None:
    """超过 72 字节的密码不被静默截断：前缀相同、尾部不同的密码必须校验失败。"""
    encoded = hash_password("a" * 72 + "x")

    assert verify_password("a" * 72 + "y", encoded) is False


def test_password_hash_supports_unicode_passwords_longer_than_72_bytes() -> None:
    """多字节 Unicode 密码（UTF-8 编码后超 72 字节）可以完整哈希并通过校验。"""
    password = "教学督导" * 20

    encoded = hash_password(password)

    assert verify_password(password, encoded) is True


def test_access_token_round_trip() -> None:
    """签发的访问令牌可解码出主体（sub）与过期时间（exp）。"""
    token = create_access_token("user-42", expires_delta=timedelta(minutes=5))

    payload = decode_access_token(token)

    assert payload["sub"] == "user-42"
    assert "exp" in payload


def test_invalid_access_token_is_rejected() -> None:
    """伪造/损坏的令牌解码时抛出 InvalidTokenError，而不是静默通过。"""
    with pytest.raises(InvalidTokenError):
        decode_access_token("not-a-valid-token")
