from pathlib import Path

from pydantic_settings import SettingsConfigDict

from langgraph_system_generator.utils.config import (
    ModelConfig,
    Settings,
    get_settings,
    reset_settings_cache,
    settings,
)


def test_settings_loads_from_env_file(tmp_path):
    env_path = Path(tmp_path) / ".env"
    env_path.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=test-key",
                "LANGSMITH_PROJECT=custom-project",
                "VECTOR_STORE_TYPE=chromadb",
                "DEFAULT_MODEL=gpt-5-mini",
                "MAX_REPAIR_ATTEMPTS=2",
                "DEFAULT_BUDGET_TOKENS=2048",
            ]
        ),
        encoding="utf-8",
    )

    class FileSettings(Settings):
        model_config = SettingsConfigDict(
            env_file=env_path, env_file_encoding="utf-8", extra="ignore"
        )

    reset_settings_cache()
    loaded = FileSettings()

    assert loaded.openai_api_key == "test-key"
    assert loaded.langsmith_project == "custom-project"
    assert loaded.vector_store_type == "chromadb"
    assert loaded.default_model == "gpt-5-mini"
    assert loaded.max_repair_attempts == 2
    assert loaded.default_budget_tokens == 2048


def test_settings_defaults(monkeypatch):
    for key in [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "LANGSMITH_API_KEY",
        "LANGSMITH_PROJECT",
        "VECTOR_STORE_TYPE",
        "VECTOR_STORE_PATH",
        "DEFAULT_MODEL",
        "MAX_REPAIR_ATTEMPTS",
        "DEFAULT_BUDGET_TOKENS",
    ]:
        monkeypatch.delenv(key, raising=False)

    reset_settings_cache()
    loaded = get_settings()

    assert loaded.openai_api_key is None
    assert loaded.anthropic_api_key is None
    assert loaded.langsmith_api_key is None
    assert loaded.langsmith_project == "langgraph-notebook-foundry"
    assert loaded.vector_store_type == "faiss"
    assert loaded.vector_store_path == "./data/vector_store"
    assert loaded.default_model == "gpt-5-mini"
    assert loaded.max_repair_attempts == 3
    assert loaded.default_budget_tokens == 100000


def test_settings_cached_instance_is_reused(monkeypatch):
    for key in [
        "OPENAI_API_KEY",
        "LANGSMITH_PROJECT",
    ]:
        monkeypatch.delenv(key, raising=False)

    reset_settings_cache()
    first = get_settings()
    second = get_settings()

    assert first is second

    third = reset_settings_cache()
    assert third is not first
    assert get_settings() is third


def test_model_config_defaults():
    """Test ModelConfig uses correct defaults."""
    config = ModelConfig()

    assert config.model == "gpt-5-mini"
    assert config.temperature == 0.7
    assert config.api_base is None
    assert config.max_tokens is None


def test_model_config_custom_values():
    """Test ModelConfig accepts custom values."""
    config = ModelConfig(
        model="gpt-5-mini",
        temperature=0.5,
        api_base="https://custom.api.com",
        max_tokens=4096,
    )

    assert config.model == "gpt-5-mini"
    assert config.temperature == 0.5
    assert config.api_base == "https://custom.api.com"
    assert config.max_tokens == 4096


def test_model_config_from_dict():
    """Test ModelConfig.from_dict filters unknown keys."""
    config_dict = {
        "model": "gpt-5-mini",
        "temperature": 0.8,
        "unknown_key": "should be ignored",
        "another_unknown": 123,
    }

    config = ModelConfig.from_dict(config_dict)

    assert config.model == "gpt-5-mini"
    assert config.temperature == 0.8
    # Unknown keys should be ignored, not cause errors
    assert not hasattr(config, "unknown_key")


def test_model_config_temperature_validation():
    """Test ModelConfig validates temperature range."""
    import pytest
    from pydantic import ValidationError

    # Valid temperatures
    ModelConfig(temperature=0.0)
    ModelConfig(temperature=1.0)
    ModelConfig(temperature=2.0)

    # Invalid temperatures should raise
    with pytest.raises(ValidationError):
        ModelConfig(temperature=-0.1)

    with pytest.raises(ValidationError):
        ModelConfig(temperature=2.1)


def test_model_config_preserves_gpt_5_mini():
    """Test ModelConfig preserves gpt-5-mini as default."""
    config = ModelConfig()
    assert config.model == "gpt-5-mini"

    # Should also work when explicitly set
    config2 = ModelConfig(model="gpt-5-mini")
    assert config2.model == "gpt-5-mini"
