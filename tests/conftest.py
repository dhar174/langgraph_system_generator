import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"

if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))


import pytest


@pytest.fixture(autouse=True)
def isolated_unit_provider_credentials(request, monkeypatch):
    """Unit tests use explicit fake provider credentials, never a developer key.

    Tests for missing credentials override these values with monkeypatch.delenv.
    Existing module-local ChatOpenAI mocks still own all model behavior.
    """
    if "unit" in request.node.path.parts:
        monkeypatch.setenv("OPENAI_API_KEY", "unit-test-openai-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "unit-test-anthropic-key")
        monkeypatch.setenv("LANGSMITH_API_KEY", "unit-test-tracing-key")
        monkeypatch.setenv("LANGSMITH_TRACING", "false")
        monkeypatch.setenv("LNF_CUSTOM_LLM_API_KEY", "unit-test-custom-key")
        monkeypatch.setenv("LNF_LLM_ENDPOINT_POLICY", "local")
        monkeypatch.setenv("LNF_TRUSTED_LLM_ENDPOINTS", "{}")
        monkeypatch.setenv("LNF_CUSTOM_LLM_NO_AUTH", "false")
