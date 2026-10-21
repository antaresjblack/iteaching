import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "AI Teaching Supervision System"
    app_version: str = "0.1.0"
    app_env: str = "development"
    debug: bool = False

    api_v1_prefix: str = "/api/v1"

    host: str = "127.0.0.1"
    port: int = 8000

    database_url: str = "sqlite:///./data/app.db"

    jwt_secret_key: str = "development-only-secret-change-me-1234567890"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    upload_dir: Path = Path("uploads")
    max_upload_size_mb: int = Field(default=500, gt=0)
    ai_service_token: str = "development-ai-service-token-change-me"
    audio_public_base_url: str = ""
    audio_signing_key: str = ""
    audio_url_ttl_seconds: int = Field(default=7200, ge=300, le=86400)
    task_lease_seconds: int = Field(default=300, ge=30, le=3600)
    task_max_attempts: int = Field(default=3, ge=1, le=10)
    initial_admin_username: str = "admin"
    initial_admin_password: str = ""
    consent_version: str = "2026-01"

    log_level: str = "INFO"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value

        raw_value = value.strip()
        if raw_value.startswith("["):
            decoded = json.loads(raw_value)
            if not isinstance(decoded, list):
                raise ValueError("CORS_ORIGINS JSON value must be an array")
            return decoded

        return [origin.strip() for origin in raw_value.split(",") if origin.strip()]

    @field_validator("initial_admin_password")
    @classmethod
    def validate_initial_admin_password(cls, value: str) -> str:
        if value and len(value) < 12:
            raise ValueError("INITIAL_ADMIN_PASSWORD must contain at least 12 characters")
        return value

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.app_env.strip().lower() not in {"prod", "production"}:
            return self

        if (
            len(self.jwt_secret_key) < 32
            or self.jwt_secret_key == "development-only-secret-change-me-1234567890"
        ):
            raise ValueError(
                "Production requires a unique JWT_SECRET_KEY of at least 32 characters"
            )
        if (
            len(self.ai_service_token) < 32
            or self.ai_service_token == "development-ai-service-token-change-me"
        ):
            raise ValueError(
                "Production requires a unique AI_SERVICE_TOKEN of at least 32 characters"
            )
        if not self.initial_admin_password:
            raise ValueError("Production requires INITIAL_ADMIN_PASSWORD for first-admin setup")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
