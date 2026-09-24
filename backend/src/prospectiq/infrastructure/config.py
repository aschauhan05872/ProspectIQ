"""Environment-based configuration. Secrets never belong in source."""

from __future__ import annotations

from functools import lru_cache
from uuid import UUID

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PROSPECTIQ_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "development"
    log_level: str = "INFO"
    secret_key: SecretStr = Field(default=SecretStr("replace-with-a-long-random-string"))
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    internal_tenant_id: UUID = UUID("00000000-0000-0000-0000-000000000001")
    internal_workspace_id: UUID = UUID("00000000-0000-0000-0000-000000000002")
    internal_user_id: UUID = UUID("00000000-0000-0000-0000-000000000003")

    database_url: str = "postgresql+asyncpg://prospectiq:prospectiq@localhost:5432/prospectiq"
    redis_url: str = "redis://localhost:6379/0"

    ai_provider: str = "none"
    ai_api_key: SecretStr = Field(default=SecretStr(""))
    ai_model: str = ""

    official_linkedin_enabled: bool = False
    official_linkedin_client_id: str = ""
    official_linkedin_client_secret: SecretStr = Field(default=SecretStr(""))

    fetch_connect_timeout_seconds: float = 5.0
    fetch_read_timeout_seconds: float = 10.0
    fetch_total_timeout_seconds: float = 15.0
    fetch_max_response_bytes: int = 1_048_576
    fetch_max_redirects: int = 3
    fetch_user_agent: str = "ProspectIQ/0.1 (+internal-company-research)"

    discovery_provider: str = "none"
    serpapi_api_key: SecretStr = Field(default=SecretStr(""))
    discovery_max_candidates: int = 20
    discovery_page_size: int = 10
    discovery_max_pages: int = 2
    discovery_timeout_seconds: float = 15.0

    news_provider: str = "none"
    news_max_results: int = 10

    research_max_pages_per_company: int = 10
    research_max_time_seconds: float = 120.0

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
