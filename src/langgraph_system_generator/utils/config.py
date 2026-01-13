"""Configuration management for LangGraph Notebook Foundry."""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Project settings loaded from environment or a `.env` file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: Optional[str] = Field(
        default=None,
        description="OpenAI API key used for language model access.",
    )
    anthropic_api_key: Optional[str] = Field(
        default=None,
        description="Anthropic API key for Claude models (optional).",
    )
    langsmith_api_key: Optional[str] = Field(
        default=None,
        description="LangSmith API key for tracing and monitoring (optional).",
    )
    langsmith_project: str = Field(
        default="langgraph-notebook-foundry",
        description="LangSmith project name for tracing runs.",
    )

    vector_store_type: str = Field(
        default="faiss",
        description="Vector store backend to use (e.g., faiss or chromadb).",
    )
    vector_store_path: str = Field(
        default="./data/vector_store",
        description="Filesystem path for storing vector index data.",
    )

    default_model: str = Field(
        default="gpt-5-mini",
        description="Primary model identifier used for generation.",
    )
    max_repair_attempts: int = Field(
        default=3,
        description="Maximum number of automated repair attempts during QA.",
    )
    default_budget_tokens: int = Field(
        default=100000,
        description="Default token budget allocated for a generation run.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()


def reset_settings_cache() -> Settings:
    """Clear and refresh the cached settings instance."""

    get_settings.cache_clear()
    refreshed = get_settings()
    globals()["settings"] = refreshed
    return refreshed


settings = get_settings()
