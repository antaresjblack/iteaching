"""应用配置（Settings）测试。

覆盖要点：
- 无 .env 文件时各配置项具备可运行的开发默认值；
- CORS_ORIGINS 支持 JSON 数组与逗号分隔两种环境变量写法；
- 生产环境（APP_ENV=production）强制要求显式的密钥与初始管理员密码，
  防止带着开发默认密钥上线。
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_have_runnable_defaults_without_env_file() -> None:
    """不读取 .env 时，核心配置项回退到可运行的开发默认值。"""
    settings = Settings(_env_file=None)

    assert settings.app_name == "AI Teaching Supervision System"
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.database_url == "sqlite:///./data/app.db"
    assert settings.cors_origins == ["http://localhost:3000", "http://localhost:5173"]


def test_settings_parse_cors_origins_from_json_environment(
    monkeypatch,
) -> None:
    """CORS_ORIGINS 环境变量为 JSON 数组字符串时可正确解析为列表。"""
    monkeypatch.setenv("CORS_ORIGINS", '["https://teaching.example.com"]')

    settings = Settings(_env_file=None)

    assert settings.cors_origins == ["https://teaching.example.com"]


def test_settings_parse_cors_origins_from_comma_separated_environment(monkeypatch) -> None:
    """CORS_ORIGINS 环境变量为逗号分隔字符串时也可解析（空白被去除）。"""
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "https://supervision.example.com, https://teacher.example.com",
    )

    settings = Settings(_env_file=None)

    assert settings.cors_origins == [
        "https://supervision.example.com",
        "https://teacher.example.com",
    ]


def test_production_settings_require_explicit_secrets_and_admin_password() -> None:
    """生产模式下缺失显式密钥即校验失败（含首尾带空格的 env 值），补全后可通过。"""
    # app_env 首尾带空格时也应被识别为生产环境
    for app_env in ("production", " production "):
        with pytest.raises(ValidationError):
            Settings(
                _env_file=None,
                app_env=app_env,
                initial_admin_password="long-enough-password",
            )

    # 三项密钥/密码全部显式给出后，生产配置可正常构建
    settings = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret_key="a-unique-jwt-secret-with-at-least-32-chars",
        ai_service_token="a-unique-worker-token-with-at-least-32-chars",
        initial_admin_password="long-enough-password",
    )

    assert settings.app_env == "production"
