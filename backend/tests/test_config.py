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
