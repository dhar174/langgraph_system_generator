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
        filtered = {k: v for k, v in config.items() if k in known_fields}
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

        model_kwargs: dict[str, object] = {
            "model": self.model or default_model,
        }
        if self.temperature is not None:
            model_kwargs["temperature"] = self.temperature
        if self.api_base is not None:
            model_kwargs["api_base"] = self.api_base
        if self.max_tokens is not None:
            model_kwargs["max_tokens"] = self.max_tokens
        return ModelConfig(**model_kwargs)


def resolve_model_config(
    *,
    model: str | None = None,
    model_config: ModelConfig | None = None,
    temperature: float = 0.0,
) -> ModelConfig:
    """Return the request-scoped model config or construct a default one."""

    if model_config is not None:
        return model_config
    return ModelConfig(model=model or settings.default_model, temperature=temperature)


def build_chat_openai_kwargs(config: ModelConfig) -> dict[str, object]:
    """Translate a ModelConfig into ChatOpenAI constructor kwargs."""

    llm_kwargs: dict[str, object] = {
        "model": config.model,
        "temperature": config.temperature,
    }
    if config.api_base:
        llm_kwargs["base_url"] = config.api_base
    if config.max_tokens is not None:
        llm_kwargs["max_tokens"] = config.max_tokens
    return llm_kwargs


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


def _test_settings_env_keys() -> tuple[str, ...]:
    """Return the env var names mirrored by Settings fields during pytest loads."""

    env_keys: list[str] = []
    for field_name, field_info in Settings.model_fields.items():
        env_name = field_info.alias or field_name
        env_keys.append(env_name.upper())
    return tuple(env_keys)


_TEST_SETTINGS_ENV_KEYS = _test_settings_env_keys()


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


@lru_cache(maxsize=8)
def _cached_settings(env_file: Optional[str]) -> Settings:
    """Create and cache settings instances by env file path."""

    init_kwargs = {}
    if env_file is not None:
        init_kwargs["_env_file"] = env_file
        init_kwargs["_env_file_encoding"] = "utf-8"

    with _suspend_project_env_for_pytest(env_file):
        return Settings(**init_kwargs)


@contextmanager
def _suspend_project_env_for_pytest(env_file: Optional[str]):
    """Temporarily remove project env vars during default pytest loads."""

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
