"""Tests for notebook composer and exporters."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import nbformat
import pytest
from jupyter_client.kernelspec import NoSuchKernel
from nbclient.client import NotebookClient

from langgraph_system_generator.generator.state import CellSpec
from langgraph_system_generator.notebook.composer import NotebookComposer
from langgraph_system_generator.notebook.exporters import NotebookExporter


def test_composer_adds_required_sections():
    composer = NotebookComposer()
    custom_cell = CellSpec(cell_type="markdown", content="### Custom", section="custom")

    nb = composer.build_notebook([custom_cell], ensure_minimum_sections=True)

    sections = {cell.metadata.get("section") for cell in nb.cells}
    assert {"setup", "config", "graph", "execution", "export", "troubleshooting"}.issubset(
        sections
    )
    assert "custom" in sections
    nbformat.validate(nb)


def test_exporters_write_files(tmp_path: Path):
    composer = NotebookComposer()
    exporter = NotebookExporter()

    nb = composer.build_notebook(
        [CellSpec(cell_type="code", content="x = 1\nprint(x)", section="execution")],
        ensure_minimum_sections=False,
    )

    ipynb_path = tmp_path / "test.ipynb"
    zip_path = tmp_path / "bundle.zip"
    extra_file = tmp_path / "extra.json"
    extra_file.write_text(json.dumps({"ok": True}), encoding="utf-8")

    written = exporter.export_ipynb(nb, ipynb_path)
    assert Path(written).exists()

    bundle = exporter.export_zip(nb, zip_path, extra_files=[extra_file])
    assert Path(bundle).exists()
    with zipfile.ZipFile(bundle, "r") as zf:
        assert "notebook.ipynb" in zf.namelist()
        assert "extra.json" in zf.namelist()


def test_smoke_execute_simple_notebook(tmp_path: Path):
    composer = NotebookComposer()
    nb = composer.build_notebook(
        [
            CellSpec(cell_type="code", content="value = 2 + 2\nprint(value)", section="execution")
        ],
        ensure_minimum_sections=False,
    )

    client = NotebookClient(nb, timeout=60, kernel_name="python3")
    try:
        executed = client.execute()
    except NoSuchKernel:
        pytest.skip("python3 kernel is not available in this environment")

    # Ensure execution added outputs
    output_cells = [cell for cell in executed.cells if cell.cell_type == "code"]
    assert any(cell.get("outputs") for cell in output_cells)
