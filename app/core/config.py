from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # App
    app_name: str = "Job Service"
    app_env: str = "development"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5434/job_db"

    # Embeddings
    gemini_api_key: str | None = None
    embedding_provider: str = "gemini"  # openai, gemini, ollama, openrouter, deepseek
    embedding_api_key: str | None = None  # defaults to gemini_api_key if not set
    embedding_api_base: str | None = None
    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 1024
    embedding_batch_size: int = 32

    # LLM (for JD parsing)
    llm_provider: str = "gemini"  # openai, anthropic, gemini, deepseek, ollama, openrouter
    llm_model: str = "gemini-2.5-flash-lite"
    llm_api_key: str | None = None  # defaults to gemini_api_key if not set
    llm_api_base: str | None = None

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug_flag(cls, value: object) -> object:
        """Accept common non-boolean environment values like 'release'."""
        if isinstance(value, str) and value.strip().lower() in {"release", "prod", "production"}:
            return False
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
