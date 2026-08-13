"""Regression tests for shared platform hardening behaviors."""

from __future__ import annotations

import importlib
import logging
from pathlib import Path

import httpx
import pytest

from langgraph_system_generator.utils import optional_deps


@pytest.mark.asyncio
async def test_generate_artifacts_records_phase_summary_and_export_results(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    """Generation should persist structured phase and export metadata."""
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_phase_summary_manifest")

    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.cli as cli_module
    import langgraph_system_generator.notebook.exporters as exporters_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)

    caplog.set_level(logging.INFO, logger="langgraph_system_generator.cli")

    artifacts = await cli_module.generate_artifacts(
        "Track structured generation phases",
        output_dir=str(constants_module._BASE_OUTPUT / "phase_summary"),
        mode="stub",
        formats=["ipynb"],
    )

    manifest = artifacts["manifest"]

    assert manifest["warnings"] == []
    assert "phase_summary" in manifest
    assert any(
        entry["phase"] == "export_ipynb" and entry["status"] == "completed"
        for entry in manifest["phase_summary"]
    )
    assert manifest["export_results"]["ipynb"]["requested"] is True
    assert manifest["export_results"]["ipynb"]["status"] == "completed"
    assert manifest["export_results"]["ipynb"]["path"] == manifest["notebook_path"]

    phase_records = [record for record in caplog.records if hasattr(record, "phase")]
    assert any(
        getattr(record, "phase", None) == "export_ipynb"
        and getattr(record, "status", None) == "completed"
        for record in phase_records
    )


@pytest.mark.asyncio
async def test_default_export_failures_become_manifest_warnings(
    monkeypatch: pytest.MonkeyPatch,
):
    """Default convenience exports should degrade to warnings instead of failing."""
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_default_export_warning")

    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)

    def fail_html(self, notebook, output_path):
        raise optional_deps.OptionalDependencyError(
            "HTML export dependencies are unavailable.",
        )

    monkeypatch.setattr(exporters_module.NotebookExporter, "export_to_html", fail_html)

    artifacts = await cli_module.generate_artifacts(
        "Allow default export warnings",
        output_dir=str(constants_module._BASE_OUTPUT / "default_warning"),
        mode="stub",
        formats=None,
    )

    manifest = artifacts["manifest"]

    assert manifest["export_results"]["html"]["requested"] is False
    assert manifest["export_results"]["html"]["status"] == "failed"
    assert manifest["warnings"]
    assert any(warning["phase"] == "export_html" for warning in manifest["warnings"])
    assert "html_error" in manifest
    assert "notebook_path" in manifest


@pytest.mark.asyncio
async def test_requested_export_failures_raise_generation_error(
    monkeypatch: pytest.MonkeyPatch,
):
    """Explicitly requested exports should fail the overall request."""
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_requested_export_failure")

    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module
    from langgraph_system_generator.utils.error_handling import GenerationError

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)

    def fail_html(self, notebook, output_path):
        raise optional_deps.OptionalDependencyError(
            'Install the "full" extra with: pip install -e ".[full]"',
        )

    monkeypatch.setattr(exporters_module.NotebookExporter, "export_to_html", fail_html)

    with pytest.raises(GenerationError) as exc_info:
        await cli_module.generate_artifacts(
            "Fail requested export",
            output_dir=str(constants_module._BASE_OUTPUT / "requested_failure"),
            mode="stub",
            formats=["ipynb", "html"],
        )

    assert exc_info.value.phase == "export_html"
    assert exc_info.value.status_code == 503
    assert exc_info.value.code in {
        "dependency_unavailable",
        "requested_export_failed",
    }


@pytest.mark.asyncio
async def test_api_returns_structured_generation_errors(
    monkeypatch: pytest.MonkeyPatch,
):
    """The API should surface phase-aware structured error payloads."""
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_structured_api_errors")

    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.api.server as server_module
    from langgraph_system_generator.utils.error_handling import GenerationError

    importlib.reload(constants_module)
    importlib.reload(server_module)

    async def fail_generation(*_args, **_kwargs):
        raise GenerationError(
            "HTML export could not run because notebook export dependencies are missing.",
            code="dependency_unavailable",
            phase="export_html",
            hint='Install the full extra with: pip install -e ".[full]"',
            status_code=503,
        )

    monkeypatch.setattr(server_module, "generate_artifacts", fail_generation)

    transport = httpx.ASGITransport(app=server_module.app)
    output_dir = constants_module._BASE_OUTPUT / "structured_api_errors"
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/generate",
            json={
                "prompt": "Trigger structured error",
                "mode": "stub",
                "output_dir": str(output_dir),
                "formats": ["ipynb", "html"],
            },
        )

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "dependency_unavailable"
    assert detail["phase"] == "export_html"
    assert "Install the full extra" in detail["hint"]


@pytest.mark.asyncio
async def test_api_optional_dependency_errors_include_feature_metadata(
    monkeypatch: pytest.MonkeyPatch,
):
    """Structured API dependency errors should keep the OptionalDependencyError feature field."""
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_structured_api_dependency_feature")

    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.api.server as server_module

    importlib.reload(constants_module)
    importlib.reload(server_module)

    async def fail_generation(*_args, **_kwargs):
        raise optional_deps.OptionalDependencyError(
            "HTML export requires nbconvert.",
            hint='Install the full extra with: pip install -e ".[full]"',
            dependency="nbconvert",
            extra="full",
            feature="HTML export",
        )

    monkeypatch.setattr(server_module, "generate_artifacts", fail_generation)

    transport = httpx.ASGITransport(app=server_module.app)
    output_dir = constants_module._BASE_OUTPUT / "structured_api_dependency_feature"
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/generate",
            json={
                "prompt": "Trigger structured dependency error",
                "mode": "stub",
                "output_dir": str(output_dir),
            },
        )

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["details"]["dependency"] == "nbconvert"
    assert detail["details"]["extra"] == "full"
    assert detail["details"]["feature"] == "HTML export"


@pytest.mark.asyncio
async def test_pdf_only_generation_records_implicit_notebook_export_result(
    monkeypatch: pytest.MonkeyPatch,
):
    """Implicit prerequisite notebook exports should appear in export_results."""
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_pdf_implicit_notebook_export")

    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)

    def fake_pdf(self, notebook_path, output_path, method="webpdf"):
        output_path = Path(output_path)
        output_path.write_bytes(b"%PDF-1.4\n%stub")
        return str(output_path)

    monkeypatch.setattr(exporters_module.NotebookExporter, "export_to_pdf", fake_pdf)

    artifacts = await cli_module.generate_artifacts(
        "Generate only a PDF artifact",
        output_dir=str(constants_module._BASE_OUTPUT / "pdf_only"),
        mode="stub",
        formats=["pdf"],
    )

    manifest = artifacts["manifest"]
    assert manifest["notebook_path"].endswith("notebook.ipynb")
    assert manifest["export_results"]["ipynb"]["requested"] is False
    assert manifest["export_results"]["ipynb"]["status"] == "completed"
    assert manifest["export_results"]["ipynb"]["path"] == manifest["notebook_path"]
    assert manifest["export_results"]["pdf"]["status"] == "completed"


def test_web_ui_uses_async_generation_and_eventsource():
    """The web UI should use SSE-backed async generation instead of fake sync progress."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    app_js = (repo_root / "src/langgraph_system_generator/api/static/app.js").read_text(
        encoding="utf-8"
    )

    assert "/generate-async" in app_js
    assert "new EventSource(" in app_js
    assert "fetch('/generate'" not in app_js


def test_web_ui_avoids_innerhtml_for_manifest_values():
    """Manifest-derived values should be rendered via DOM APIs instead of innerHTML."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    app_js = (repo_root / "src/langgraph_system_generator/api/static/app.js").read_text(
        encoding="utf-8"
    )

    forbidden_patterns = [
        'innerHTML = `<strong>Architecture:</strong>',
        'innerHTML = `<strong>Plan Title:</strong>',
        'innerHTML = `<strong>Notebook Cells:</strong>',
        'innerHTML = `<strong>Output Directory:</strong>',
    ]
    for pattern in forbidden_patterns:
        assert pattern not in app_js


def test_web_ui_renders_qa_summary_details():
    """Successful web results should expose non-blocking QA advisory details."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    app_js = (repo_root / "src/langgraph_system_generator/api/static/app.js").read_text(
        encoding="utf-8"
    )

    assert "manifest.qa_summary" in app_js
    assert "Generation Completed With Advisories" in app_js
    assert "appendQaSummary(resultWrapper, qaSummary)" in app_js
    assert "finding.check_name" in app_js
    assert "finding.suggestions" in app_js


def test_web_ui_only_treats_server_sent_sse_errors_as_terminal():
    """Transport-level EventSource errors should be allowed to reconnect."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    app_js = (repo_root / "src/langgraph_system_generator/api/static/app.js").read_text(
        encoding="utf-8"
    )

    assert "eventSource.addEventListener('error'" in app_js
    assert "if (event.data)" in app_js
    assert "'reconnecting'" in app_js


def test_web_ui_rejects_when_sse_reconnect_is_no_longer_possible():
    """Permanent EventSource closure should surface as a terminal UI error."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    app_js = (repo_root / "src/langgraph_system_generator/api/static/app.js").read_text(
        encoding="utf-8"
    )

    marker = "eventSource.onerror = () => {"
    assert marker in app_js
    onerror_block = app_js.split(marker, 1)[1].split("});", 1)[0]
    assert "eventSource.readyState === EventSource.CLOSED" in onerror_block
    assert "rejectStream(" in onerror_block
