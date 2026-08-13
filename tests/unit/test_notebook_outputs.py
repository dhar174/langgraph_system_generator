"""Tests for notebook and document output generation."""

from __future__ import annotations

import zipfile
from pathlib import Path

import nbformat
import pytest


@pytest.mark.asyncio
async def test_generate_notebook_ipynb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test that IPYNB notebook is generated."""
    # Set a test output base
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_notebook_ipynb")

    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)

    artifacts = await cli_module.generate_artifacts(
        "Create a test system",
        output_dir=str(constants_module._BASE_OUTPUT / "test_ipynb"),
        mode="stub",
        formats=["ipynb"],
    )

    assert "notebook_path" in artifacts["manifest"]
    notebook_path = constants_module.resolve_under_base(
        Path(artifacts["manifest"]["notebook_path"])
    )
    assert notebook_path.exists()
    assert notebook_path.suffix == ".ipynb"
    assert notebook_path.stat().st_size > 0


@pytest.mark.asyncio
async def test_generate_html_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test that HTML export is generated."""
    # Set a test output base
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_html_export")

    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)

    artifacts = await cli_module.generate_artifacts(
        "Create a test system",
        output_dir=str(constants_module._BASE_OUTPUT / "test_html"),
        mode="stub",
        formats=["ipynb", "html"],
    )

    assert "html_path" in artifacts["manifest"]
    html_path = constants_module._BASE_OUTPUT / artifacts["manifest"]["html_path"]
    assert html_path.exists()
    assert html_path.suffix == ".html"
    assert html_path.stat().st_size > 0

    # Check HTML contains notebook content
    content = html_path.read_text(encoding="utf-8")
    assert "LangGraph" in content or "notebook" in content.lower()


@pytest.mark.asyncio
async def test_generate_docx_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test that DOCX export is generated."""
    # Set a test output base
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_docx_export")

    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)

    artifacts = await cli_module.generate_artifacts(
        "Create a test system",
        output_dir=str(constants_module._BASE_OUTPUT / "test_docx"),
        mode="stub",
        formats=["ipynb", "docx"],
    )

    assert "docx_path" in artifacts["manifest"]
    docx_path = constants_module._BASE_OUTPUT / artifacts["manifest"]["docx_path"]
    assert docx_path.exists()
    assert docx_path.suffix == ".docx"
    assert docx_path.stat().st_size > 0


@pytest.mark.asyncio
async def test_generate_markdown_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test that Markdown export is generated when requested."""
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_markdown_export")

    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)

    artifacts = await cli_module.generate_artifacts(
        "Create a test system",
        output_dir=str(constants_module._BASE_OUTPUT / "test_markdown"),
        mode="stub",
        formats=["ipynb", "markdown"],
    )

    assert "markdown_path" in artifacts["manifest"]
    markdown_path = constants_module.resolve_under_base(
        Path(artifacts["manifest"]["markdown_path"])
    )
    assert markdown_path.exists()
    assert markdown_path.suffix == ".md"
    assert markdown_path.read_text(encoding="utf-8").strip()


@pytest.mark.asyncio
async def test_generate_zip_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test that ZIP bundle is generated with all artifacts."""
    # Set a test output base
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_zip_bundle")

    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)

    artifacts = await cli_module.generate_artifacts(
        "Create a test system",
        output_dir=str(constants_module._BASE_OUTPUT / "test_zip"),
        mode="stub",
        formats=["ipynb", "zip"],
    )

    assert "zip_path" in artifacts["manifest"]
    zip_path = constants_module._BASE_OUTPUT / artifacts["manifest"]["zip_path"]
    assert zip_path.exists()
    assert zip_path.suffix == ".zip"
    assert zip_path.stat().st_size > 0

    # Verify ZIP contents
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        assert "notebook.ipynb" in names
        # Should also include JSON artifacts
        assert any("json" in name for name in names)


@pytest.mark.asyncio
async def test_manifest_cell_count_matches_serialized_notebook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Manifest cell_count should describe the emitted notebook, not raw specs."""
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_manifest_cell_count_truth")

    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)

    artifacts = await cli_module.generate_artifacts(
        "Create a manifest truth test system",
        output_dir=str(constants_module._BASE_OUTPUT / "cell_count_truth"),
        mode="stub",
        formats=["ipynb"],
    )

    manifest = artifacts["manifest"]
    notebook_path = constants_module.resolve_under_base(Path(manifest["notebook_path"]))
    notebook = nbformat.read(notebook_path, as_version=4)

    assert manifest["cell_count"] == len(notebook.cells)
    assert manifest["cell_count_source"] == "serialized_notebook"
    assert manifest["generated_cell_spec_count"] == len(
        artifacts["result"]["generated_cells"]
    )


@pytest.mark.asyncio
async def test_manifest_artifact_contract_marks_standalone_files_and_zip_members(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Manifest artifact metadata should match files and bundle contents."""
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_manifest_artifact_contract")

    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)

    artifacts = await cli_module.generate_artifacts(
        "Create an artifact contract test system",
        output_dir=str(constants_module._BASE_OUTPUT / "artifact_contract"),
        mode="stub",
        formats=["ipynb", "html", "zip"],
    )

    manifest = artifacts["manifest"]
    contract = manifest["artifact_contract"]
    standalone_by_key = {
        entry["manifest_key"]: entry for entry in contract["standalone_files"]
    }

    for manifest_key in [
        "plan_path",
        "cells_path",
        "notebook_path",
        "html_path",
        "zip_path",
    ]:
        entry = standalone_by_key[manifest_key]
        assert entry["availability"] == "standalone"
        assert entry["path_type"] == "server_local"
        assert entry["exists"] is True
        assert constants_module.resolve_under_base(Path(entry["path"])).is_file()
        assert entry["relative_path"]

    zip_path = constants_module.resolve_under_base(Path(manifest["zip_path"]))
    with zipfile.ZipFile(zip_path, "r") as zf:
        actual_members = set(zf.namelist())

    manifest_members = {entry["name"]: entry for entry in contract["zip_members"]}
    assert set(manifest_members).issubset(actual_members)
    assert manifest_members["notebook.ipynb"]["availability"] in {
        "standalone_and_bundle",
        "bundle_only",
    }
    assert manifest_members["notebook_plan.json"]["source_manifest_key"] == "plan_path"
    assert (
        manifest_members["generated_cells.json"]["source_manifest_key"] == "cells_path"
    )


def test_artifact_contract_does_not_inspect_nonstandard_manifest_zip(tmp_path: Path):
    """Only the generator-owned bundle name is inspected for ZIP members."""
    import langgraph_system_generator.cli as cli_module

    output_dir = tmp_path / "artifact_contract"
    output_dir.mkdir()
    alternate_zip = output_dir / "user_named_bundle.zip"
    with zipfile.ZipFile(alternate_zip, "w") as zf:
        zf.writestr("unexpected.txt", "not a generated bundle member")

    contract = cli_module._build_artifact_contract(
        {"zip_path": str(alternate_zip)},
        output_dir,
    )

    assert contract["standalone_files"][0]["exists"] is True
    assert contract["zip_members"] == []


@pytest.mark.asyncio
async def test_generate_all_formats(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test that all formats are generated when formats=None."""
    # Set a test output base
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_all_formats")

    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)

    artifacts = await cli_module.generate_artifacts(
        "Create a test system",
        output_dir=str(constants_module._BASE_OUTPUT / "test_all"),
        mode="stub",
        formats=None,  # Should generate all formats
    )

    # Check all expected formats are in manifest
    assert "notebook_path" in artifacts["manifest"]
    assert "html_path" in artifacts["manifest"]
    assert "docx_path" in artifacts["manifest"]
    assert "zip_path" in artifacts["manifest"]

    # Verify all files exist
    assert constants_module.resolve_under_base(
        Path(artifacts["manifest"]["notebook_path"])
    ).exists()
    assert constants_module.resolve_under_base(
        Path(artifacts["manifest"]["html_path"])
    ).exists()
    assert constants_module.resolve_under_base(
        Path(artifacts["manifest"]["docx_path"])
    ).exists()
    assert constants_module.resolve_under_base(
        Path(artifacts["manifest"]["zip_path"])
    ).exists()


@pytest.mark.asyncio
async def test_generate_selective_formats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test that only selected formats are generated."""
    # Set a test output base
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_selective_formats")

    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)

    artifacts = await cli_module.generate_artifacts(
        "Create a test system",
        output_dir=str(constants_module._BASE_OUTPUT / "test_selective"),
        mode="stub",
        formats=["ipynb", "html"],
    )

    # Should have selected formats
    assert "notebook_path" in artifacts["manifest"]
    assert constants_module.resolve_under_base(
        Path(artifacts["manifest"]["notebook_path"])
    ).exists()
    assert constants_module.resolve_under_base(
        Path(artifacts["manifest"]["html_path"])
    ).exists()
    assert "html_path" in artifacts["manifest"]

    # Should NOT have other formats
    assert "docx_path" not in artifacts["manifest"]
    assert "zip_path" not in artifacts["manifest"]
    assert "pdf_path" not in artifacts["manifest"]


@pytest.mark.asyncio
async def test_notebook_has_required_sections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test that generated notebook has required sections."""
    # Set a test output base
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_required_sections")

    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)

    artifacts = await cli_module.generate_artifacts(
        "Create a test system",
        output_dir=str(constants_module._BASE_OUTPUT / "test_sections"),
        mode="stub",
        formats=["ipynb"],
    )

    import nbformat

    notebook_path = (
        constants_module._BASE_OUTPUT / artifacts["manifest"]["notebook_path"]
    )
    with open(notebook_path, "r", encoding="utf-8") as f:
        nb = nbformat.read(f, as_version=4)

    # Check for required sections in cell metadata
    sections = {cell.metadata.get("section") for cell in nb.cells}
    required_sections = {
        "setup",
        "config",
        "graph",
        "execution",
        "export",
        "troubleshooting",
    }

    # The composer adds these required sections
    assert required_sections.issubset(
        sections
    ), f"Missing sections: {required_sections - sections}"


@pytest.mark.asyncio
async def test_manifest_includes_all_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test that manifest includes paths to all generated artifacts."""
    # Set a test output base
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_manifest_paths")

    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)

    artifacts = await cli_module.generate_artifacts(
        "Create a test system",
        output_dir=str(constants_module._BASE_OUTPUT / "test_manifest"),
        mode="stub",
        formats=["ipynb", "html", "docx", "zip"],
    )

    manifest = artifacts["manifest"]

    # Check basic metadata
    assert manifest["prompt"] == "Create a test system"
    assert manifest["mode"] == "stub"
    assert manifest["architecture_type"] in ["router", "subagents", "hybrid"]
    assert manifest["cell_count"] > 0

    # Check paths to artifacts are in manifest
    assert "plan_path" in manifest
    assert "cells_path" in manifest
    assert "notebook_path" in manifest
    assert "html_path" in manifest
    assert "docx_path" in manifest
    assert "zip_path" in manifest

    # Verify generated output files exist. Note: plan_path and cells_path are
    # referenced in manifest but may not be saved as files; we only verify the
    # actual exported artifact files (notebook, html, docx, zip)
    for key in [
        "notebook_path",
        "html_path",
        "docx_path",
        "zip_path",
    ]:
        path = constants_module._BASE_OUTPUT / manifest[key]
        assert path.exists(), f"{key} file not found: {path}"


@pytest.mark.asyncio
async def test_error_handling_pdf_missing_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test that PDF export errors are handled gracefully."""
    # Set a test output base
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_pdf_errors")

    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)

    artifacts = await cli_module.generate_artifacts(
        "Create a test system",
        output_dir=str(constants_module._BASE_OUTPUT / "test_pdf"),
        mode="stub",
        formats=["ipynb", "pdf"],
    )

    # PDF may fail if dependencies are missing, but should be captured in manifest
    if "pdf_path" not in artifacts["manifest"]:
        # If PDF failed, error should be in manifest
        assert "pdf_error" in artifacts["manifest"]
    else:
        # If PDF succeeded, verify it exists
        assert (
            constants_module._BASE_OUTPUT / artifacts["manifest"]["pdf_path"]
        ).exists()
