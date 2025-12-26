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
from langgraph_system_generator.notebook.manuscript_docx import ManuscriptDOCXGenerator
from langgraph_system_generator.notebook.manuscript_pdf import ManuscriptPDFGenerator


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


def test_export_to_html(tmp_path: Path):
    """Test HTML export functionality."""
    composer = NotebookComposer()
    exporter = NotebookExporter()

    nb = composer.build_notebook(
        [
            CellSpec(cell_type="markdown", content="# Test Notebook", section="intro"),
            CellSpec(cell_type="code", content="print('hello')", section="code"),
        ],
        ensure_minimum_sections=False,
    )

    html_path = tmp_path / "test.html"
    result = exporter.export_to_html(nb, html_path)

    assert Path(result).exists()
    content = Path(result).read_text(encoding="utf-8")
    assert "Test Notebook" in content
    assert "hello" in content


def test_export_notebook_to_docx(tmp_path: Path):
    """Test basic DOCX export functionality."""
    composer = NotebookComposer()
    exporter = NotebookExporter()

    nb = composer.build_notebook(
        [
            CellSpec(cell_type="markdown", content="# Introduction\nThis is a test.", section="intro"),
            CellSpec(cell_type="code", content="x = 42", section="code"),
        ],
        ensure_minimum_sections=False,
    )

    docx_path = tmp_path / "test.docx"
    result = exporter.export_notebook_to_docx(nb, docx_path, title="Test Document")

    assert Path(result).exists()
    assert Path(result).stat().st_size > 0


def test_manuscript_docx_creation(tmp_path: Path):
    """Test ManuscriptDOCXGenerator for professional DOCX output."""
    generator = ManuscriptDOCXGenerator(font_name="Arial", font_size=11)

    chapters = [
        {
            "title": "Chapter 1: Introduction",
            "content": ["This is the first paragraph.", "This is the second paragraph."],
        },
        {
            "title": "Chapter 2: Methods",
            "content": "This is a single string content with multiple sentences. It should be formatted nicely.",
        },
    ]

    output_path = tmp_path / "manuscript.docx"
    result = generator.create_manuscript(
        title="Test Manuscript",
        author="Test Author",
        chapters=chapters,
        output_path=output_path,
    )

    assert Path(result).exists()
    assert Path(result).stat().st_size > 0


def test_manuscript_docx_from_notebook_cells(tmp_path: Path):
    """Test creating DOCX manuscript from notebook cells."""
    generator = ManuscriptDOCXGenerator()

    cells = [
        {"cell_type": "markdown", "content": "# Setup\nInitial setup instructions.", "section": "setup"},
        {"cell_type": "code", "content": "import os\nprint('ready')", "section": "setup"},
        {"cell_type": "markdown", "content": "## Configuration", "section": "config"},
        {"cell_type": "code", "content": "config = {'key': 'value'}", "section": "config"},
    ]

    output_path = tmp_path / "notebook_manuscript.docx"
    result = generator.create_notebook_manuscript(
        notebook_cells=cells,
        output_path=output_path,
        title="Notebook as Manuscript",
    )

    assert Path(result).exists()
    assert Path(result).stat().st_size > 0


def test_manuscript_pdf_creation(tmp_path: Path):
    """Test ManuscriptPDFGenerator for professional PDF output."""
    generator = ManuscriptPDFGenerator(font_name="Helvetica", font_size=11)

    chapters = [
        {
            "title": "Chapter 1: Getting Started",
            "content": ["First paragraph of chapter 1.", "Second paragraph of chapter 1."],
        },
        {
            "title": "Chapter 2: Advanced Topics",
            "content": [
                {"heading": "Section 2.1", "text": "This is section 2.1 content."},
                {"heading": "Section 2.2", "text": "This is section 2.2 content."},
            ],
        },
    ]

    output_path = tmp_path / "manuscript.pdf"
    result = generator.create_manuscript(
        title="Test PDF Manuscript",
        chapters=chapters,
        output_path=output_path,
        author="Test Author",
    )

    assert Path(result).exists()
    assert Path(result).stat().st_size > 0


def test_manuscript_pdf_from_notebook_cells(tmp_path: Path):
    """Test creating PDF manuscript from notebook cells."""
    generator = ManuscriptPDFGenerator()

    cells = [
        {"cell_type": "markdown", "content": "# Introduction\nWelcome to the notebook.", "section": "intro"},
        {"cell_type": "code", "content": "def hello():\n    print('Hello, World!')", "section": "code"},
        {"cell_type": "markdown", "content": "## Execution\nRun the code.", "section": "execution"},
        {"cell_type": "code", "content": "hello()", "section": "execution"},
    ]

    output_path = tmp_path / "notebook_manuscript.pdf"
    result = generator.create_notebook_manuscript(
        notebook_cells=cells,
        output_path=output_path,
        title="Notebook PDF",
        author="Generator",
    )

    assert Path(result).exists()
    assert Path(result).stat().st_size > 0


def test_manuscript_docx_without_title_page(tmp_path: Path):
    """Test DOCX generation without title page."""
    generator = ManuscriptDOCXGenerator()

    chapters = [{"title": "Only Chapter", "content": "Simple content."}]

    output_path = tmp_path / "no_title.docx"
    result = generator.create_manuscript(
        title="Test",
        chapters=chapters,
        output_path=output_path,
        include_title_page=False,
    )

    assert Path(result).exists()


def test_manuscript_pdf_without_title_page(tmp_path: Path):
    """Test PDF generation without title page."""
    generator = ManuscriptPDFGenerator()

    chapters = [{"title": "Only Chapter", "content": "Simple content."}]

    output_path = tmp_path / "no_title.pdf"
    result = generator.create_manuscript(
        title="Test",
        chapters=chapters,
        output_path=output_path,
        include_title_page=False,
    )

    assert Path(result).exists()

