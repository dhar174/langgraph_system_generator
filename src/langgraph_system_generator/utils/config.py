"""Configuration management for LangGraph Notebook Foundry."""

from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
import os
from pathlib import Path
import sys
from typing import Optional, Union

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelConfig(BaseModel):
    """Configuration for LLM model parameters used in code generation."""

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
    summary_model: Optional[str] = Field(
        default=None,
        description=(
            "Optional model identifier for lightweight summarization steps. "
            "When omitted, uses 'gpt-4o-mini' with the default API base, or "
            "the primary model when a custom api_base is configured."
        ),
    )

    @classmethod
    def from_dict(cls, config: dict) -> "ModelConfig":
        """Create ModelConfig from a dictionary, filtering unknown keys."""
        known_fields = cls.model_fields.keys()
        filtered = {key: value for key, value in config.items() if key in known_fields}
        return cls(**filtered)


class GenerationConfig(BaseModel):
    """Request-scoped live generation settings."""

    model: Optional[str] = Field(default=None, description="Optional model override")
    temperature: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="Optional temperature override",
    )
    max_tokens: Optional[int] = Field(
        default=None,
        ge=1,
        description="Optional max_tokens override",
    )
    api_base: Optional[str] = Field(
        default=None,
        description="Optional OpenAI-compatible base URL override",
    )
    agent_type: Optional[str] = Field(
        default=None,
        description="Optional architecture override",
    )

    def to_model_config(self, default_model: str) -> ModelConfig:
        """Resolve a per-request model configuration for live agents."""
        return ModelConfig(
            model=self.model or default_model,
            temperature=0.0 if self.temperature is None else self.temperature,
            api_base=self.api_base,
            max_tokens=self.max_tokens,
        )


class Settings(BaseSettings):
    """Project settings loaded from environment or a `.env` file."""

    model_config = SettingsConfigDict(
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


_DEFAULT_ENV_FILE = object()
_TEST_SETTINGS_ENV_KEYS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "LANGSMITH_API_KEY",
    "LANGSMITH_PROJECT",
    "VECTOR_STORE_TYPE",
    "VECTOR_STORE_PATH",
    "DEFAULT_MODEL",
    "MAX_REPAIR_ATTEMPTS",
    "DEFAULT_BUDGET_TOKENS",
)


def _pytest_is_active() -> bool:
    """Return True when running under pytest collection or execution."""
    return "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ


def _resolve_default_env_file() -> Optional[str]:
    """Resolve the default dotenv path for application usage."""
    if _pytest_is_active():
        return None

    configured_env_file = os.environ.get("LNF_ENV_FILE")
    if configured_env_file is not None:
        return configured_env_file or None

    if os.environ.get("LNF_DISABLE_DOTENV", "").lower() in {"1", "true", "yes", "on"}:
        return None

    candidate = Path(".env")
    if candidate.exists():
        return str(candidate)

    return None


@contextmanager
def _suspend_project_env_for_pytest(env_file: Optional[str]):
    """Temporarily remove project settings env vars during default pytest loads."""
    if not (_pytest_is_active() and env_file is None):
        yield
        return

    removed_values = {
        key: os.environ.pop(key)
        for key in _TEST_SETTINGS_ENV_KEYS
        if key in os.environ
    }
    try:
        yield
    finally:
        os.environ.update(removed_values)


@lru_cache(maxsize=8)
def _cached_settings(env_file: Optional[str]) -> Settings:
    """Create and cache settings instances by env file path."""
    init_kwargs = {}
    if env_file is not None:
        init_kwargs["_env_file"] = env_file
        init_kwargs["_env_file_encoding"] = "utf-8"

    with _suspend_project_env_for_pytest(env_file):
        return Settings(**init_kwargs)


def get_settings(env_file: Union[str, Path, None, object] = _DEFAULT_ENV_FILE) -> Settings:
    """Return a cached settings instance."""
    if env_file is _DEFAULT_ENV_FILE:
        resolved_env_file = None if _pytest_is_active() else _resolve_default_env_file()
    elif env_file is None:
        resolved_env_file = None
    else:
        resolved_env_file = str(Path(env_file))

    return _cached_settings(resolved_env_file)


def reset_settings_cache(
    env_file: Union[str, Path, None, object] = _DEFAULT_ENV_FILE,
) -> Settings:
    """Clear and refresh the cached settings instance."""
    _cached_settings.cache_clear()
    refreshed = get_settings(env_file)
    globals()["settings"] = refreshed
    return refreshed


settings = get_settings()
