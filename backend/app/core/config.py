import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, field_validator
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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
