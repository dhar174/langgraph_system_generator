"""Configuration management for LangGraph Notebook Foundry."""

from functools import lru_cache
from typing import Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelConfig(BaseModel):
    """Configuration for LLM model parameters used in code generation.
    
    This class encapsulates all model-related configuration to make it easy
    to inject different models, temperatures, and API settings into pattern
    generators without modifying the generator source code.
    """

    model: str = Field(
        default="gpt-5-mini",
        description="LLM model identifier (e.g., gpt-5-mini, gpt-4, claude-3-opus)",
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Temperature for LLM sampling (0.0-2.0)",
    )
    api_base: Optional[str] = Field(
        default=None,
        description="Custom API base URL for self-hosted or alternative providers",
    )
    max_tokens: Optional[int] = Field(
        default=None,
        description="Maximum tokens for LLM response",
    )

    @classmethod
    def from_dict(cls, config: dict) -> "ModelConfig":
        """Create ModelConfig from a dictionary, filtering unknown keys."""
        known_fields = cls.model_fields.keys()
        filtered = {k: v for k, v in config.items() if k in known_fields}
        return cls(**filtered)


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
