from pathlib import Path

from langgraph_system_generator.utils.config import Settings, get_settings, settings


def test_settings_loads_from_env_file(tmp_path):
    env_path = Path(tmp_path) / ".env"
    env_path.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=test-key",
                "LANGSMITH_PROJECT=custom-project",
                "VECTOR_STORE_TYPE=chromadb",
                "DEFAULT_MODEL=gpt-4o-mini",
                "MAX_REPAIR_ATTEMPTS=2",
                "DEFAULT_BUDGET_TOKENS=2048",
            ]
        ),
        encoding="utf-8",
    )

    loaded = Settings(_env_file=env_path)

    assert loaded.openai_api_key == "test-key"
    assert loaded.langsmith_project == "custom-project"
    assert loaded.vector_store_type == "chromadb"
    assert loaded.default_model == "gpt-4o-mini"
    assert loaded.max_repair_attempts == 2
    assert loaded.default_budget_tokens == 2048


def test_settings_cached_instance_is_reused():
    first = get_settings()
    second = settings

    assert first is second
