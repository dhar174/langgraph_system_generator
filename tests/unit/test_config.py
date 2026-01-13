from pathlib import Path

from pydantic_settings import SettingsConfigDict

from langgraph_system_generator.utils.config import (
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
                "DEFAULT_MODEL=gpt-5-nano",
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
    assert loaded.default_model == "gpt-5-nano"
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
    assert loaded.default_model == "gpt-5-nano"
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
