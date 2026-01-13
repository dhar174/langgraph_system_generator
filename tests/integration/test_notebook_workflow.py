"""Integration test for complete notebook generation workflow."""

from __future__ import annotations

import zipfile
from pathlib import Path

import nbformat
import pytest

from langgraph_system_generator.cli import generate_artifacts


@pytest.mark.asyncio
async def test_end_to_end_notebook_generation(tmp_path: Path):
    """Test complete workflow from prompt to multiple output formats."""

    # Generate with all formats
    artifacts = await generate_artifacts(
        prompt="Create a customer support chatbot with routing",
        output_dir=tmp_path,
        mode="stub",
        formats=None,  # All formats
    )

    # Verify basic metadata
    assert artifacts["mode"] == "stub"
    assert artifacts["prompt"] == "Create a customer support chatbot with routing"
    assert Path(artifacts["output_dir"]) == tmp_path

    manifest = artifacts["manifest"]

    # Verify all required paths exist in manifest
    required_paths = [
        "notebook_path",
        "html_path",
        "docx_path",
        "zip_path",
        "plan_path",
        "cells_path",
        "manifest_path",
    ]

    for path_key in required_paths:
        assert (
            path_key in manifest or path_key == "manifest_path"
        ), f"Missing {path_key}"
        if path_key in manifest:
            file_path = Path(manifest[path_key])
            assert file_path.exists(), f"File not found: {file_path}"
            assert file_path.stat().st_size > 0, f"Empty file: {file_path}"

    # Verify notebook structure
    notebook_path = Path(manifest["notebook_path"])
    with open(notebook_path, "r", encoding="utf-8") as f:
        nb = nbformat.read(f, as_version=4)

    # Check notebook has cells
    assert len(nb.cells) > 0, "Notebook has no cells"

    # Check notebook has required sections
    sections = {cell.metadata.get("section") for cell in nb.cells}
    required_sections = {
        "setup",
        "config",
        "graph",
        "execution",
        "export",
        "troubleshooting",
    }
    assert required_sections.issubset(
        sections
    ), f"Missing sections: {required_sections - sections}"

    # Check notebook has both markdown and code cells
    cell_types = {cell.cell_type for cell in nb.cells}
    assert "markdown" in cell_types, "No markdown cells"
    assert "code" in cell_types, "No code cells"

    # Verify HTML content
    html_path = Path(manifest["html_path"])
    html_content = html_path.read_text(encoding="utf-8")
    assert len(html_content) > 1000, "HTML content too short"
    assert (
        "<!DOCTYPE" in html_content or "<html" in html_content.lower()
    ), "Not valid HTML"

    # Verify DOCX exists and is not empty
    docx_path = Path(manifest["docx_path"])
    assert docx_path.stat().st_size > 10000, "DOCX file too small"

    # Verify ZIP bundle
    zip_path = Path(manifest["zip_path"])
    with zipfile.ZipFile(zip_path, "r") as zf:
        zip_contents = zf.namelist()
        assert "notebook.ipynb" in zip_contents, "ZIP missing notebook"
        # Should include JSON artifacts
        json_files = [f for f in zip_contents if f.endswith(".json")]
        assert len(json_files) > 0, "ZIP missing JSON artifacts"

    # Verify JSON artifacts have valid content
    import json

    plan_path = Path(manifest["plan_path"])
    plan_data = json.loads(plan_path.read_text())
    assert "title" in plan_data
    assert "sections" in plan_data
    assert "architecture_type" in plan_data

    cells_path = Path(manifest["cells_path"])
    cells_data = json.loads(cells_path.read_text())
    assert isinstance(cells_data, list)
    assert len(cells_data) > 0
    assert "cell_type" in cells_data[0]
    assert "content" in cells_data[0]


@pytest.mark.asyncio
async def test_workflow_with_selective_formats(tmp_path: Path):
    """Test workflow with only specific formats selected."""

    artifacts = await generate_artifacts(
        prompt="Create a simple chatbot",
        output_dir=tmp_path,
        mode="stub",
        formats=["ipynb", "html"],  # Only notebook and HTML
    )

    manifest = artifacts["manifest"]

    # Should have selected formats
    assert "notebook_path" in manifest
    assert "html_path" in manifest
    assert Path(manifest["notebook_path"]).exists()
    assert Path(manifest["html_path"]).exists()

    # Should NOT have other formats
    assert "docx_path" not in manifest
    assert "zip_path" not in manifest
    assert "pdf_path" not in manifest

    # JSON artifacts should always be present
    assert "plan_path" in manifest
    assert "cells_path" in manifest


@pytest.mark.asyncio
async def test_workflow_robustness_with_errors(tmp_path: Path):
    """Test that workflow continues even if some formats fail."""

    # This tests error handling - even if PDF fails, other formats should work
    artifacts = await generate_artifacts(
        prompt="Create a test system",
        output_dir=tmp_path,
        mode="stub",
        formats=["ipynb", "html", "pdf"],  # PDF may fail without deps
    )

    manifest = artifacts["manifest"]

    # Core formats should always succeed
    assert "notebook_path" in manifest
    assert "html_path" in manifest

    # PDF might have an error
    if "pdf_path" not in manifest:
        # Error should be captured
        assert "pdf_error" in manifest

    # Verify the successful exports are valid
    assert Path(manifest["notebook_path"]).exists()
    assert Path(manifest["html_path"]).exists()


@pytest.mark.asyncio
async def test_manifest_completeness(tmp_path: Path):
    """Test that manifest contains all expected metadata."""

    test_prompt = "Build an AI assistant"

    artifacts = await generate_artifacts(
        prompt=test_prompt,
        output_dir=tmp_path,
        mode="stub",
        formats=["ipynb", "html", "docx"],
    )

    manifest = artifacts["manifest"]

    # Verify basic metadata
    assert manifest["prompt"] == test_prompt
    assert manifest["mode"] == "stub"
    assert "architecture_type" in manifest
    assert manifest["architecture_type"] in ["router", "subagents", "hybrid"]
    assert "cell_count" in manifest
    assert manifest["cell_count"] > 0
    assert "plan_title" in manifest
    assert len(manifest["plan_title"]) > 0

    # Verify file paths are absolute or relative to output_dir
    for key in manifest:
        if key.endswith("_path"):
            path = Path(manifest[key])
            # Path should either be absolute or resolvable
            assert path.exists() or path.is_absolute(), f"Invalid path: {path}"
