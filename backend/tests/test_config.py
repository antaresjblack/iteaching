import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_have_runnable_defaults_without_env_file() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_name == "AI Teaching Supervision System"
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.database_url == "sqlite:///./data/app.db"
    assert settings.cors_origins == ["http://localhost:3000", "http://localhost:5173"]


def test_settings_parse_cors_origins_from_json_environment(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["https://teaching.example.com"]')

    settings = Settings(_env_file=None)

    assert settings.cors_origins == ["https://teaching.example.com"]


def test_settings_parse_cors_origins_from_comma_separated_environment(monkeypatch) -> None:
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
    for app_env in ("production", " production "):
        with pytest.raises(ValidationError):
            Settings(
                _env_file=None,
                app_env=app_env,
                initial_admin_password="long-enough-password",
            )

    settings = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret_key="a-unique-jwt-secret-with-at-least-32-chars",
        ai_service_token="a-unique-worker-token-with-at-least-32-chars",
        initial_admin_password="long-enough-password",
    )

    assert settings.app_env == "production"
