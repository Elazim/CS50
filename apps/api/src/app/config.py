from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ATC_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "staging", "production"] = "dev"

    database_url: str = "postgresql+psycopg://atc:atc@localhost:5432/atc"
    redis_url: str = "redis://localhost:6379/0"
    celery_task_always_eager: bool = False

    # Object storage (MinIO in dev, S3-compatible in prod)
    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "atc-documents"
    s3_region: str = "us-east-1"

    # Auth. "dev" enables password-less email login for local development only;
    # startup fails closed if auth_mode=dev in a production environment.
    auth_mode: Literal["dev", "workos"] = "dev"
    session_secret: str = "dev-only-secret-change-me"
    session_max_age_seconds: int = 60 * 60 * 8
    workos_api_key: str | None = None
    workos_client_id: str | None = None

    web_origin: str = "http://localhost:3000"

    # AI providers (docs/03 §8). "local" implementations are deterministic
    # stand-ins for dev/test; production requires real providers.
    embedding_provider: Literal["local", "voyage"] = "local"
    embedding_model: str = "voyage-3"
    voyage_api_key: str | None = None
    anthropic_api_key: str | None = None
    llm_model: str = "claude-sonnet-5"

    sentry_dsn: str | None = None

    max_upload_bytes: int = 200 * 1024 * 1024

    @field_validator("s3_endpoint_url", mode="before")
    @classmethod
    def _empty_endpoint_is_none(cls, v: str | None) -> str | None:
        # ATC_S3_ENDPOINT_URL="" means "use real AWS endpoints" (tests/prod).
        return v or None

    def validate_for_environment(self) -> None:
        if self.env == "production":
            if self.auth_mode == "dev":
                raise RuntimeError("auth_mode=dev is not allowed in production")
            if self.session_secret == "dev-only-secret-change-me":
                raise RuntimeError("session_secret must be set in production")
            if self.embedding_provider == "local":
                raise RuntimeError("embedding_provider=local is not allowed in production")


@lru_cache
def get_settings() -> Settings:
    return Settings()
