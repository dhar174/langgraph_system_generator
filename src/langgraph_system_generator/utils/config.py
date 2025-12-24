"""Configuration management for LangGraph Notebook Foundry."""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Project settings loaded from environment or a `.env` file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    langsmith_api_key: Optional[str] = None
    langsmith_project: str = "langgraph-notebook-foundry"

    vector_store_type: str = "faiss"
    vector_store_path: str = "./data/vector_store"

    default_model: str = "gpt-4-turbo-preview"
    max_repair_attempts: int = 3
    default_budget_tokens: int = 100000


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()


settings = get_settings()

