"""Tests for notebook and document output generation."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from langgraph_system_generator.cli import generate_artifacts


@pytest.mark.asyncio
async def test_generate_notebook_ipynb(tmp_path: Path):
    """Test that IPYNB notebook is generated."""
    artifacts = await generate_artifacts(
        "Create a test system",
        output_dir=tmp_path,
        mode="stub",
        formats=["ipynb"],
    )

    assert "notebook_path" in artifacts["manifest"]
    notebook_path = Path(artifacts["manifest"]["notebook_path"])
    assert notebook_path.exists()
    assert notebook_path.suffix == ".ipynb"
    assert notebook_path.stat().st_size > 0


@pytest.mark.asyncio
async def test_generate_html_export(tmp_path: Path):
    """Test that HTML export is generated."""
    artifacts = await generate_artifacts(
        "Create a test system",
        output_dir=tmp_path,
        mode="stub",
        formats=["ipynb", "html"],
    )

    assert "html_path" in artifacts["manifest"]
    html_path = Path(artifacts["manifest"]["html_path"])
    assert html_path.exists()
    assert html_path.suffix == ".html"
    assert html_path.stat().st_size > 0

    # Check HTML contains notebook content
    content = html_path.read_text(encoding="utf-8")
    assert "LangGraph" in content or "notebook" in content.lower()


@pytest.mark.asyncio
async def test_generate_docx_export(tmp_path: Path):
    """Test that DOCX export is generated."""
    artifacts = await generate_artifacts(
        "Create a test system",
        output_dir=tmp_path,
        mode="stub",
        formats=["ipynb", "docx"],
    )

    assert "docx_path" in artifacts["manifest"]
    docx_path = Path(artifacts["manifest"]["docx_path"])
    assert docx_path.exists()
    assert docx_path.suffix == ".docx"
    assert docx_path.stat().st_size > 0


@pytest.mark.asyncio
async def test_generate_zip_bundle(tmp_path: Path):
    """Test that ZIP bundle is generated with all artifacts."""
    artifacts = await generate_artifacts(
        "Create a test system",
        output_dir=tmp_path,
        mode="stub",
        formats=["ipynb", "zip"],
    )

    assert "zip_path" in artifacts["manifest"]
    zip_path = Path(artifacts["manifest"]["zip_path"])
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
async def test_generate_all_formats(tmp_path: Path):
    """Test that all formats are generated when formats=None."""
    artifacts = await generate_artifacts(
        "Create a test system",
        output_dir=tmp_path,
        mode="stub",
        formats=None,  # Should generate all formats
    )

    # Check all expected formats are in manifest
    assert "notebook_path" in artifacts["manifest"]
    assert "html_path" in artifacts["manifest"]
    assert "docx_path" in artifacts["manifest"]
    assert "zip_path" in artifacts["manifest"]

    # Verify all files exist
    assert Path(artifacts["manifest"]["notebook_path"]).exists()
    assert Path(artifacts["manifest"]["html_path"]).exists()
    assert Path(artifacts["manifest"]["docx_path"]).exists()
    assert Path(artifacts["manifest"]["zip_path"]).exists()


@pytest.mark.asyncio
async def test_generate_selective_formats(tmp_path: Path):
    """Test that only selected formats are generated."""
    artifacts = await generate_artifacts(
        "Create a test system",
        output_dir=tmp_path,
        mode="stub",
        formats=["ipynb", "html"],
    )

    # Should have selected formats
    assert "notebook_path" in artifacts["manifest"]
    assert "html_path" in artifacts["manifest"]

    # Should NOT have other formats
    assert "docx_path" not in artifacts["manifest"]
    assert "zip_path" not in artifacts["manifest"]
    assert "pdf_path" not in artifacts["manifest"]


@pytest.mark.asyncio
async def test_notebook_has_required_sections(tmp_path: Path):
    """Test that generated notebook has required sections."""
    artifacts = await generate_artifacts(
        "Create a test system",
        output_dir=tmp_path,
        mode="stub",
        formats=["ipynb"],
    )

    import nbformat

    notebook_path = Path(artifacts["manifest"]["notebook_path"])
    with open(notebook_path, "r", encoding="utf-8") as f:
        nb = nbformat.read(f, as_version=4)

    # Check for required sections in cell metadata
    sections = {cell.metadata.get("section") for cell in nb.cells}
    required_sections = {"setup", "config", "graph", "execution", "export", "troubleshooting"}

    # The composer adds these required sections
    assert required_sections.issubset(sections), f"Missing sections: {required_sections - sections}"


@pytest.mark.asyncio
async def test_manifest_includes_all_paths(tmp_path: Path):
    """Test that manifest includes paths to all generated artifacts."""
    artifacts = await generate_artifacts(
        "Create a test system",
        output_dir=tmp_path,
        mode="stub",
        formats=["ipynb", "html", "docx", "zip"],
    )

    manifest = artifacts["manifest"]

    # Check basic metadata
    assert manifest["prompt"] == "Create a test system"
    assert manifest["mode"] == "stub"
    assert manifest["architecture_type"] in ["router", "subagents", "hybrid"]
    assert manifest["cell_count"] > 0

    # Check paths to artifacts
    assert "plan_path" in manifest
    assert "cells_path" in manifest
    assert "notebook_path" in manifest
    assert "html_path" in manifest
    assert "docx_path" in manifest
    assert "zip_path" in manifest

    # Verify all paths exist
    for key in ["plan_path", "cells_path", "notebook_path", "html_path", "docx_path", "zip_path"]:
        path = Path(manifest[key])
        assert path.exists(), f"{key} file not found: {path}"


@pytest.mark.asyncio
async def test_error_handling_pdf_missing_dependencies(tmp_path: Path):
    """Test that PDF export errors are handled gracefully."""
    artifacts = await generate_artifacts(
        "Create a test system",
        output_dir=tmp_path,
        mode="stub",
        formats=["ipynb", "pdf"],
    )

    # PDF may fail if dependencies are missing, but should be captured in manifest
    if "pdf_path" not in artifacts["manifest"]:
        # If PDF failed, error should be in manifest
        assert "pdf_error" in artifacts["manifest"]
    else:
        # If PDF succeeded, verify it exists
        assert Path(artifacts["manifest"]["pdf_path"]).exists()
