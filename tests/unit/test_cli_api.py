"""Tests for CLI helpers and FastAPI server integration."""

from __future__ import annotations

import asyncio as aio
import importlib
import json
from pathlib import Path

import pytest
import httpx
from fastapi.testclient import TestClient

from langgraph_system_generator.api.server import app
from langgraph_system_generator.cli import GenerationArtifacts, generate_artifacts
from langgraph_system_generator.generator.graph_design_registry import (
    GraphDesignRegistration,
    get_graph_design_registry,
)
from langgraph_system_generator.utils.config import GenerationConfig
from langgraph_system_generator.utils.error_handling import GenerationError
from langgraph_system_generator.utils.optional_deps import OptionalDependencyError


def _reload_server_modules():
    """Reload constants/server modules after environment changes in a test."""
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.api.server as server_module

    importlib.reload(constants_module)
    importlib.reload(server_module)
    return constants_module, server_module


@pytest.mark.asyncio
async def test_generate_artifacts_stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Set a test output base
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_generate_artifacts_stub")

    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)

    # Use path within OUTPUT_BASE
    output_dir = constants_module._BASE_OUTPUT / "test_stub"
    artifacts: GenerationArtifacts = await cli_module.generate_artifacts(
        "Test prompt", output_dir=str(output_dir), mode="stub"
    )

    assert artifacts["manifest"]["prompt"] == "Test prompt"
    assert artifacts["manifest"]["cell_count"] > 0
    assert artifacts["manifest"]["requirements_feedback"]["fallback_used"] is False
    assert artifacts["manifest"]["architecture_feedback"]["fallback_used"] is False
    assert artifacts["manifest"]["architecture_feedback"]["docs_considered"] == []
    assert artifacts["manifest"]["graph_design_feedback"]["fallback_used"] is False
    assert "flowchart TD" in artifacts["manifest"]["graph_exports"]["mermaid"]
    assert artifacts["manifest"]["notebook_composition_feedback"]["fallback_used"] is False
    assert "langgraph" in artifacts["manifest"]["notebook_dependency_plan"]["packages"]
    assert artifacts["result"]["requirements_feedback"]["fallback_used"] is False
    assert artifacts["result"]["architecture_feedback"]["fallback_used"] is False
    assert artifacts["result"]["architecture_feedback"]["docs_considered"] == []
    assert artifacts["result"]["graph_design_feedback"]["fallback_used"] is False
    assert "flowchart TD" in artifacts["result"]["graph_exports"]["mermaid"]
    assert artifacts["result"]["notebook_composition_feedback"]["fallback_used"] is False
    assert "OPENAI_API_KEY" in artifacts["result"]["notebook_dependency_plan"]["provider_env_vars"]
    assert Path(artifacts["manifest_path"]).exists()
    assert artifacts["result"]["generation_complete"] is True


def test_default_state_includes_generation_mode_and_qa_history():
    import langgraph_system_generator.cli as cli_module

    state = cli_module._default_state(
        "Test prompt",
        GenerationConfig(model="gpt-5-mini"),
        generation_mode="live",
    )

    assert state["generation_mode"] == "live"
    assert state["qa_history"] == []
    assert state["requirements_feedback"].fallback_used is False
    assert state["architecture_feedback"].fallback_used is False
    assert state["graph_design_feedback"].fallback_used is False
    assert state["graph_exports"].schema == {}
    assert state["notebook_composition_feedback"].fallback_used is False
    assert state["notebook_dependency_plan"].packages == []
    assert "goal" in state["requirements_feedback"].available_constraint_types


def test_default_and_stub_results_normalize_constraint_type_registry(monkeypatch):
    import langgraph_system_generator.cli as cli_module

    monkeypatch.setattr(
        cli_module,
        "settings",
        cli_module.settings.model_copy(
            update={
                "requirements_constraint_types": [
                    "Custom Type",
                    " runtime ",
                    "custom-type",
                ]
            }
        ),
    )

    expected_registry = [
        "goal",
        "tone",
        "length",
        "structure",
        "runtime",
        "environment",
        "custom_type",
    ]

    state = cli_module._default_state("Test prompt")
    stub_result = cli_module._build_stub_result("Test prompt")

    assert state["requirements_feedback"].available_constraint_types == expected_registry
    assert stub_result["requirements_feedback"].available_constraint_types == expected_registry
    assert (
        stub_result["notebook_composition_feedback"].resolved_model
        == cli_module.settings.default_model
    )
    assert "langgraph" in stub_result["notebook_dependency_plan"].packages


@pytest.mark.asyncio
async def test_generate_artifacts_stub_autoagent_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_generate_artifacts_stub_autoagent")

    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)

    output_dir = constants_module._BASE_OUTPUT / "test_stub_autoagent"
    artifacts: GenerationArtifacts = await cli_module.generate_artifacts(
        "Build an autonomous planning workflow",
        output_dir=str(output_dir),
        mode="stub",
        agent_type="autoagent",
    )

    assert artifacts["manifest"]["architecture_type"] == "autoagent"
    assert artifacts["manifest"]["agent_type"] == "autoagent"
    assert artifacts["result"]["architecture_type"] == "autoagent"
    assert artifacts["result"]["generation_complete"] is True


@pytest.mark.asyncio
async def test_generate_artifacts_stub_hybrid_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_generate_artifacts_stub_hybrid")

    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)

    output_dir = constants_module._BASE_OUTPUT / "test_stub_hybrid"
    artifacts: GenerationArtifacts = await cli_module.generate_artifacts(
        "Build a workflow that mixes direct routing with a worker team",
        output_dir=str(output_dir),
        mode="stub",
        agent_type="hybrid",
    )

    graph_cells = [
        cell
        for cell in artifacts["result"]["generated_cells"]
        if cell["section"] == "graph"
    ]
    assert artifacts["manifest"]["architecture_type"] == "hybrid"
    assert artifacts["manifest"]["agent_type"] == "hybrid"
    assert artifacts["result"]["architecture_type"] == "hybrid"
    assert graph_cells
    assert 'workflow.add_node("router", router_node)' in graph_cells[0]["content"]
    assert 'workflow.add_node("supervisor", supervisor_node)' in graph_cells[0]["content"]


@pytest.mark.asyncio
async def test_generate_artifacts_default_formats_include_markdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("BASE_OUTPUT_DIR", str(tmp_path.resolve()))

    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)

    output_dir = tmp_path / "default_formats"
    artifacts: GenerationArtifacts = await cli_module.generate_artifacts(
        "Test prompt", output_dir=str(output_dir), mode="stub"
    )

    assert "markdown_path" in artifacts["manifest"]
    assert Path(artifacts["manifest"]["markdown_path"]).exists()


@pytest.mark.asyncio
async def test_api_generate_stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Set a test output base
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_api_stub")

    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.api.server as server_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(server_module)

    transport = httpx.ASGITransport(app=server_module.app)
    output_dir = constants_module._BASE_OUTPUT / tmp_path.name
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/generate",
            json={
                "prompt": "API prompt",
                "mode": "stub",
                "output_dir": str(output_dir),
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["manifest"]["prompt"] == "API prompt"
    assert "manifest_path" in payload
    # Verify new response fields
    assert payload["mode"] == "stub"
    assert payload["prompt"] == "API prompt"
    assert "output_dir" in payload
    assert payload["output_dir"] == str(output_dir)
    assert payload["manifest"]["requirements_feedback"]["fallback_used"] is False
    assert payload["manifest"]["architecture_feedback"]["fallback_used"] is False
    assert payload["manifest"]["notebook_composition_feedback"]["fallback_used"] is False
    assert "langgraph" in payload["manifest"]["notebook_dependency_plan"]["packages"]


@pytest.mark.asyncio
async def test_generate_artifacts_surfaces_requirements_feedback_as_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_requirements_feedback_warning")

    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)

    original_build_stub_result = cli_module._build_stub_result

    def build_stub_result_with_feedback(prompt: str, agent_type: str | None = None):
        result = original_build_stub_result(prompt, agent_type=agent_type)
        result["requirements_feedback"] = {
            "fallback_used": True,
            "fallback_reason": "Failed to parse requirements payload.",
            "missing_inputs": ["runtime", "environment"],
            "conflicts": ["Conflicting runtime instructions were detected."],
            "suggestions": ["Clarify the target runtime and environment constraints."],
            "available_constraint_types": ["goal", "runtime", "environment"],
        }
        return result

    monkeypatch.setattr(cli_module, "_build_stub_result", build_stub_result_with_feedback)

    output_dir = constants_module._BASE_OUTPUT / tmp_path.name
    artifacts = await cli_module.generate_artifacts(
        "Ambiguous prompt",
        output_dir=str(output_dir),
        mode="stub",
    )

    warning_codes = {warning["code"] for warning in artifacts["manifest"]["warnings"]}
    assert "requirements_fallback" in warning_codes
    assert "requirements_missing_inputs" in warning_codes
    assert "requirements_conflicts" in warning_codes
    assert artifacts["manifest"]["requirements_feedback"]["fallback_used"] is True


@pytest.mark.asyncio
async def test_generate_artifacts_surfaces_architecture_feedback_as_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_architecture_feedback_warning")

    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)

    original_build_stub_result = cli_module._build_stub_result

    def build_stub_result_with_feedback(prompt: str, agent_type: str | None = None):
        result = original_build_stub_result(prompt, agent_type=agent_type)
        result["architecture_feedback"] = {
            "confidence": 0.21,
            "fallback_used": True,
            "fallback_reason": "Architecture selection fallback used after validation failed.",
            "validation_errors": ["Unsupported architecture_type 'swarm'."],
            "tradeoffs": ["Router fallback may underfit specialized workflows."],
            "alternatives": [],
            "docs_considered": ["router", "subagents"],
        }
        return result

    monkeypatch.setattr(cli_module, "_build_stub_result", build_stub_result_with_feedback)

    output_dir = constants_module._BASE_OUTPUT / tmp_path.name
    artifacts = await cli_module.generate_artifacts(
        "Ambiguous architecture prompt",
        output_dir=str(output_dir),
        mode="stub",
    )

    warning_codes = {warning["code"] for warning in artifacts["manifest"]["warnings"]}
    assert "architecture_fallback" in warning_codes
    assert "architecture_validation" in warning_codes
    assert artifacts["manifest"]["architecture_feedback"]["fallback_used"] is True


@pytest.mark.asyncio
async def test_generate_artifacts_surfaces_graph_design_feedback_as_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_graph_design_feedback_warning")

    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)

    original_build_stub_result = cli_module._build_stub_result

    def build_stub_result_with_graph_feedback(prompt: str, agent_type: str | None = None):
        result = original_build_stub_result(prompt, agent_type=agent_type)
        result["graph_design_feedback"] = {
            "fallback_used": True,
            "fallback_reason": "Live graph design validation failed.",
            "validation_errors": [
                "Duplicate node id 'router'.",
                "Unknown edge target 'missing_target'.",
            ],
            "warnings": ["Recovered using deterministic fallback."],
            "validation_issues": [
                {
                    "code": "duplicate_node_id",
                    "message": "Duplicate node id 'router'.",
                    "severity": "error",
                    "nodes": ["router"],
                    "details": {},
                }
            ],
        }
        result["graph_exports"] = {
            "mermaid": "flowchart TD\n    router --> finish",
            "schema": {
                "entry_point": "router",
                "terminal_nodes": ["finish"],
                "validation_summary": {
                    "errors": [
                        "Duplicate node id 'router'.",
                        "Unknown edge target 'missing_target'.",
                    ],
                    "warnings": ["Recovered using deterministic fallback."],
                },
            },
        }
        return result

    monkeypatch.setattr(cli_module, "_build_stub_result", build_stub_result_with_graph_feedback)

    output_dir = constants_module._BASE_OUTPUT / "graph_feedback_stub"
    artifacts = await cli_module.generate_artifacts(
        "Graph feedback prompt",
        output_dir=str(output_dir),
        mode="stub",
    )

    warning_codes = {warning["code"] for warning in artifacts["manifest"]["warnings"]}
    assert "graph_design_fallback" in warning_codes
    assert "graph_design_validation" in warning_codes
    assert artifacts["manifest"]["graph_design_feedback"]["fallback_used"] is True
    assert "flowchart TD" in artifacts["manifest"]["graph_exports"]["mermaid"]


@pytest.mark.asyncio
async def test_generate_artifacts_surfaces_notebook_composition_feedback_as_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_notebook_feedback_warning")

    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)

    original_build_stub_result = cli_module._build_stub_result

    def build_stub_result_with_notebook_feedback(
        prompt: str,
        agent_type: str | None = None,
    ):
        result = original_build_stub_result(prompt, agent_type=agent_type)
        result["notebook_composition_feedback"] = {
            "fallback_used": True,
            "warnings": ['Deterministic fallback used for tool "search".'],
            "fallback_events": [
                {
                    "kind": "tool",
                    "item_name": "search",
                    "reason": "LLM tool generation returned placeholder or incomplete code.",
                    "warning": 'Deterministic fallback used for tool "search".',
                }
            ],
            "resolved_model": "gpt-5.2",
            "resolved_api_base": None,
            "resolved_max_iterations": 10,
            "sections_built": [
                "intro",
                "install",
                "config",
                "state",
                "tools",
                "nodes",
                "graph",
                "execution",
            ],
        }
        result["notebook_dependency_plan"] = {
            "packages": ["langgraph", "langchain-openai", "requests"],
            "install_commands": [
                "python -m pip install -q langgraph langchain-openai requests"
            ],
            "runtime_notes": [
                "The install cell checks for missing packages before invoking pip."
            ],
            "conflicts_resolved": [],
            "provider_env_vars": ["OPENAI_API_KEY"],
        }
        return result

    monkeypatch.setattr(
        cli_module,
        "_build_stub_result",
        build_stub_result_with_notebook_feedback,
    )

    output_dir = constants_module._BASE_OUTPUT / "notebook_feedback_stub"
    artifacts = await cli_module.generate_artifacts(
        "Notebook feedback prompt",
        output_dir=str(output_dir),
        mode="stub",
    )

    warning_codes = {warning["code"] for warning in artifacts["manifest"]["warnings"]}
    assert "notebook_composition_fallback" in warning_codes
    assert artifacts["manifest"]["notebook_composition_feedback"]["fallback_used"] is True
    assert "requests" in artifacts["manifest"]["notebook_dependency_plan"]["packages"]


def test_build_stub_result_raises_for_invalid_stub_graph_design(monkeypatch):
    import langgraph_system_generator.cli as cli_module

    registry = get_graph_design_registry().clone()
    router_registration = get_graph_design_registry().get("router")
    registry.register(
        GraphDesignRegistration(
            architecture_id="router",
            supported_entry_shapes=router_registration.supported_entry_shapes,
            supported_exit_shapes=router_registration.supported_exit_shapes,
            cycles_allowed=router_registration.cycles_allowed,
            fallback_builder=lambda *_args, **_kwargs: {
                "state_schema": {},
                "nodes": [{"name": "router", "purpose": "Route requests"}],
                "edges": [{"from": "router", "to": "missing_target"}],
                "conditional_edges": [],
                "entry_point": "router",
                "checkpointing": False,
            },
            normalization_hook=router_registration.normalization_hook,
            validation_hook=router_registration.validation_hook,
            export_label_defaults=router_registration.export_label_defaults,
            composition_strategy=router_registration.composition_strategy,
        )
    )
    monkeypatch.setattr(cli_module, "get_graph_design_registry", lambda: registry)

    with pytest.raises(GenerationError, match="invalid workflow"):
        cli_module._build_stub_result("Build a test workflow")


@pytest.mark.asyncio
async def test_api_rejects_removed_advanced_options_as_unknown_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_api_unsupported_options")

    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.api.server as server_module

    importlib.reload(constants_module)
    importlib.reload(server_module)

    transport = httpx.ASGITransport(app=server_module.app)
    output_dir = constants_module._BASE_OUTPUT / tmp_path.name
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/generate",
            json={
                "prompt": "API prompt",
                "mode": "stub",
                "output_dir": str(output_dir),
                "memory_config": "short",
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "extra_forbidden"


def test_generation_request_formats_description_mentions_markdown():
    description = app.openapi()["components"]["schemas"]["GenerationRequest"]["properties"][
        "formats"
    ]["description"]

    assert "markdown" in description.lower()
    assert "ipynb, html, markdown, docx, zip" in description


@pytest.mark.asyncio
async def test_api_rejects_invalid_custom_endpoint():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/generate",
            json={
                "prompt": "Invalid endpoint",
                "mode": "stub",
                "output_dir": "./output/api",
                "model": "gpt-5-mini",
                "custom_endpoint": "ftp://example.test/v1",
            },
        )

    assert response.status_code == 400
    assert "http or https URL" in response.json()["detail"]


@pytest.mark.asyncio
async def test_api_rejects_unsupported_agent_type():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/generate",
            json={
                "prompt": "Unsupported agent type",
                "mode": "stub",
                "output_dir": "./output/api",
                "agent_type": " swarm ",
            },
        )

    assert response.status_code == 400
    assert "Unsupported agent_type" in response.json()["detail"]


@pytest.mark.asyncio
async def test_api_generate_surfaces_optional_dependency_errors(
    monkeypatch: pytest.MonkeyPatch,
):
    error_message = "optional dependency unavailable"

    async def fake_generate_artifacts(*_args, **_kwargs):
        raise OptionalDependencyError(error_message)

    monkeypatch.setattr(
        "langgraph_system_generator.api.server.generate_artifacts",
        fake_generate_artifacts,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/generate",
            json={
                "prompt": "Missing optional dependencies",
                "mode": "stub",
                "output_dir": "./output/api",
            },
        )

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "dependency_unavailable"
    assert detail["message"] == error_message
    assert detail["status_code"] == 503


@pytest.mark.asyncio
async def test_api_accepts_arbitrary_openai_compatible_model_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Built-in provider should accept explicit model identifiers without an allowlist."""
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_api_arbitrary_model")

    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.api.server as server_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(server_module)

    transport = httpx.ASGITransport(app=server_module.app)
    output_dir = constants_module._BASE_OUTPUT / tmp_path.name
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/generate",
            json={
                "prompt": "API prompt",
                "mode": "stub",
                "output_dir": str(output_dir),
                "model": "gpt-5-future-release",
            },
        )

    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.asyncio
async def test_api_rejects_custom_endpoint_without_explicit_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Custom endpoints must include a non-placeholder model identifier."""
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_api_custom_endpoint_requires_model")

    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.api.server as server_module

    importlib.reload(constants_module)
    importlib.reload(server_module)

    transport = httpx.ASGITransport(app=server_module.app)
    output_dir = constants_module._BASE_OUTPUT / tmp_path.name
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/generate",
            json={
                "prompt": "API prompt",
                "mode": "stub",
                "output_dir": str(output_dir),
                "custom_endpoint": "https://example.test/v1",
            },
        )

    assert response.status_code == 400
    assert (
        "custom_endpoint requires an explicit OpenAI-compatible model identifier"
        in response.json()["detail"]
    )


@pytest.mark.asyncio
async def test_api_generate_with_formats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test API with format selection."""
    # Set a test output base
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_api_formats")

    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.api.server as server_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(server_module)

    transport = httpx.ASGITransport(app=server_module.app)
    output_dir = constants_module._BASE_OUTPUT / tmp_path.name
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/generate",
            json={
                "prompt": "Test with formats",
                "mode": "stub",
                "output_dir": str(output_dir),
                "formats": ["ipynb", "html"],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["manifest"]["prompt"] == "Test with formats"

    # Verify selected formats are in manifest
    assert "notebook_path" in payload["manifest"]
    assert "html_path" in payload["manifest"]

    # Verify unselected formats are NOT in manifest
    assert "docx_path" not in payload["manifest"]
    assert "pdf_path" not in payload["manifest"]


@pytest.mark.asyncio
async def test_api_download_artifact_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test downloading a generated artifact through the API."""
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_api_artifact_download")

    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module
    import langgraph_system_generator.api.server as server_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)
    importlib.reload(server_module)

    artifacts = await cli_module.generate_artifacts(
        "Artifact download prompt",
        output_dir=str(constants_module._BASE_OUTPUT / tmp_path.name),
        mode="stub",
        formats=["ipynb"],
    )

    transport = httpx.ASGITransport(app=server_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/artifacts",
            params={"path": artifacts["manifest"]["notebook_path"]},
        )

    assert response.status_code == 200
    assert "notebook.ipynb" in response.headers.get("content-disposition", "")
    assert response.content


@pytest.mark.asyncio
async def test_api_download_artifact_rejects_invalid_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test artifact download rejects paths outside the trusted base."""
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_api_artifact_reject")

    import importlib
    import langgraph_system_generator.api.server as server_module

    importlib.reload(server_module)

    transport = httpx.ASGITransport(app=server_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/artifacts", params={"path": str(tmp_path / ".." / "escape.txt")}
        )

    assert response.status_code == 400
    assert "allowed base directory" in response.json()["detail"]


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_chrome_devtools_endpoint():
    """Test that Chrome DevTools endpoint returns 204 No Content."""
    client = TestClient(app)
    response = client.get("/.well-known/appspecific/com.chrome.devtools.json")
    assert response.status_code == 204
    # 204 responses should have no content
    assert response.content == b""


def test_root_endpoint_with_static_files():
    """Test that root endpoint serves the web interface when static files exist."""
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    # Should return HTML content
    assert "text/html" in response.headers.get("content-type", "")
    # Check for key elements from index.html with expected casing
    content = response.text
    assert "LangGraph" in content and "System Generator" in content


@pytest.mark.asyncio
async def test_live_mode_requires_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # Set BASE_OUTPUT_DIR to allow test output in tmp_path
    monkeypatch.setenv("BASE_OUTPUT_DIR", str(tmp_path.resolve()))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        await generate_artifacts("Live prompt", output_dir=tmp_path, mode="live")


@pytest.mark.asyncio
async def test_api_rejects_disallowed_output_dir(tmp_path: Path):
    outside = tmp_path.parent
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/generate",
            json={
                "prompt": "Traversal attempt",
                "mode": "stub",
                "output_dir": str(outside),
            },
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_api_generate_respects_concurrency_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test that /generate respects the shared concurrency limit."""
    monkeypatch.setenv("LNF_MAX_CONCURRENT_GENERATIONS", "1")
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_sync_concurrency")

    constants_module, server_module = _reload_server_modules()

    gate = aio.Event()

    async def slow_generate_artifacts(*_args, **_kwargs):
        await gate.wait()
        return {
            "mode": "stub",
            "prompt": "slow",
            "manifest": {},
            "manifest_path": str(constants_module._BASE_OUTPUT / "manifest.json"),
            "output_dir": str(constants_module._BASE_OUTPUT / tmp_path.name / "gen1"),
        }

    monkeypatch.setattr(server_module, "generate_artifacts", slow_generate_artifacts)

    transport = httpx.ASGITransport(app=server_module.app)
    output_dir = constants_module._BASE_OUTPUT / tmp_path.name

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        request_one = aio.create_task(
            client.post(
                "/generate",
                json={
                    "prompt": "Test concurrent sync generation 1",
                    "mode": "stub",
                    "output_dir": str(output_dir / "gen1"),
                },
            )
        )
        await aio.sleep(0.05)

        response2 = await client.post(
            "/generate",
            json={
                "prompt": "Test concurrent sync generation 2",
                "mode": "stub",
                "output_dir": str(output_dir / "gen2"),
            },
        )

        assert response2.status_code == 503

        gate.set()
        response1 = await request_one

    assert response1.status_code == 200


@pytest.mark.asyncio
async def test_api_generate_async_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test /generate-async endpoint returns job_id and stream_url."""
    # Set a test output base
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_api_async")

    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.api.server as server_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(server_module)

    transport = httpx.ASGITransport(app=server_module.app)
    output_dir = constants_module._BASE_OUTPUT / tmp_path.name
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/generate-async",
            json={
                "prompt": "Test async generation",
                "mode": "stub",
                "output_dir": str(output_dir),
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert "job_id" in payload
    assert "stream_url" in payload
    assert payload["status"] == "started"
    assert payload["stream_url"].startswith("/stream/")


@pytest.mark.asyncio
async def test_api_stream_endpoint_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test /stream/{job_id} endpoint returns error for non-existent job."""
    # Set a test output base
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_stream_notfound")

    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.api.server as server_module

    importlib.reload(server_module)

    transport = httpx.ASGITransport(app=server_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Try to stream a non-existent job
        async with client.stream("GET", "/stream/nonexistent-job-id") as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")

            # Read first event which should be an error
            events = []
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    event_type = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data = line.split(":", 1)[1].strip()
                    events.append({"event": event_type, "data": json.loads(data)})
                    break

            assert len(events) > 0
            assert events[0]["event"] == "error"
            assert "not found" in events[0]["data"]["error"].lower()


@pytest.mark.asyncio
async def test_api_generate_async_with_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test full async generation flow with SSE stream consumption."""
    # Set a test output base
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_async_stream")

    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.api.server as server_module
    import langgraph_system_generator.api.progress_streaming as progress_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(progress_module)
    importlib.reload(server_module)

    transport = httpx.ASGITransport(app=server_module.app)
    output_dir = constants_module._BASE_OUTPUT / tmp_path.name

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Start async generation
        response = await client.post(
            "/generate-async",
            json={
                "prompt": "Test streaming generation",
                "mode": "stub",
                "output_dir": str(output_dir),
                "formats": ["ipynb"],
            },
        )

        assert response.status_code == 200
        payload = response.json()
        stream_url = payload["stream_url"]

        # Connect to SSE stream
        events = []
        async with client.stream("GET", stream_url, timeout=30.0) as stream_response:
            assert stream_response.status_code == 200

            # Parse SSE events
            event_type = None
            async for line in stream_response.aiter_lines():
                line = line.strip()
                if not line:
                    continue

                if line.startswith("event:"):
                    event_type = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data = line.split(":", 1)[1].strip()
                    events.append({"event": event_type, "data": json.loads(data)})

                    # Stop after complete or error
                    if event_type in ("complete", "error"):
                        break

        # Verify we got events
        assert len(events) > 0, "Should receive at least one event"

        # Check for progress events
        progress_events = [e for e in events if e["event"] == "progress"]
        assert len(progress_events) > 0, "Should receive progress events"

        # Check for completion
        complete_events = [e for e in events if e["event"] == "complete"]
        assert len(complete_events) == 1, "Should have exactly one complete event"

        # Verify completion data
        final_result = complete_events[0]["data"]
        assert final_result.get("success") is True
        assert final_result.get("mode") == "stub"
        assert "manifest" in final_result


@pytest.mark.asyncio
async def test_api_generate_async_concurrency_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test that /generate-async respects concurrency limits."""
    monkeypatch.setenv("LNF_MAX_CONCURRENT_GENERATIONS", "1")
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_concurrency")

    import importlib
    import asyncio as aio
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.api.server as server_module

    importlib.reload(constants_module)
    importlib.reload(server_module)

    gate = aio.Event()

    async def slow_generate_artifacts(*_args, **_kwargs):
        await gate.wait()
        return {
            "mode": "stub",
            "prompt": "slow",
            "manifest": {},
            "manifest_path": str(constants_module._BASE_OUTPUT / "manifest.json"),
            "output_dir": str(constants_module._BASE_OUTPUT / tmp_path.name / "gen1"),
        }

    monkeypatch.setattr(server_module, "generate_artifacts", slow_generate_artifacts)
    server_module._active_generation_count = 0

    transport = httpx.ASGITransport(app=server_module.app)
    output_dir = constants_module._BASE_OUTPUT / tmp_path.name

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response1 = await client.post(
            "/generate-async",
            json={
                "prompt": "Test concurrent generation 1",
                "mode": "stub",
                "output_dir": str(output_dir / "gen1"),
            },
        )
        assert response1.status_code == 200

        response2 = await client.post(
            "/generate-async",
            json={
                "prompt": "Test concurrent generation 2",
                "mode": "stub",
                "output_dir": str(output_dir / "gen2"),
            },
        )

        assert response2.status_code == 503
        gate.set()
        await aio.sleep(0.05)
