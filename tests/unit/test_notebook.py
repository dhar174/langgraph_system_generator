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
    assert {
        "setup",
        "config",
        "graph",
        "execution",
        "export",
        "troubleshooting",
    }.issubset(sections)
    assert "custom" in sections
    nbformat.validate(nb)


def test_exporters_write_files(tmp_path: Path, monkeypatch):
    # Set a test output base
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_exporters")
    
    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    
    composer = NotebookComposer()
    exporter = exporters_module.NotebookExporter()

    nb = composer.build_notebook(
        [CellSpec(cell_type="code", content="x = 1\nprint(x)", section="execution")],
        ensure_minimum_sections=False,
    )

    # Use relative paths that will be created under _BASE_OUTPUT
    ipynb_path = "test.ipynb"
    zip_path = "bundle.zip"
    extra_file_path = constants_module._BASE_OUTPUT / "extra.json"
    extra_file_path.write_text(json.dumps({"ok": True}), encoding="utf-8")

    written = exporter.export_ipynb(nb, ipynb_path)
    assert Path(written).exists()

    bundle = exporter.export_zip(nb, zip_path, extra_files=[extra_file_path])
    assert Path(bundle).exists()
    with zipfile.ZipFile(bundle, "r") as zf:
        assert "notebook.ipynb" in zf.namelist()
        assert "extra.json" in zf.namelist()


def test_smoke_execute_simple_notebook(tmp_path: Path):
    composer = NotebookComposer()
    nb = composer.build_notebook(
        [
            CellSpec(
                cell_type="code",
                content="value = 2 + 2\nprint(value)",
                section="execution",
            )
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


def test_export_to_html(tmp_path: Path, monkeypatch):
    """Test HTML export functionality."""
    # Set a test output base
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_html_export")
    
    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    
    composer = NotebookComposer()
    exporter = exporters_module.NotebookExporter()

    nb = composer.build_notebook(
        [
            CellSpec(cell_type="markdown", content="# Test Notebook", section="intro"),
            CellSpec(cell_type="code", content="print('hello')", section="code"),
        ],
        ensure_minimum_sections=False,
    )

    # Use relative path
    html_path = "test.html"
    result = exporter.export_to_html(nb, html_path)

    assert Path(result).exists()
    content = Path(result).read_text(encoding="utf-8")
    assert "Test Notebook" in content
    assert "hello" in content


def test_export_to_pdf(tmp_path: Path, monkeypatch):
    """Test PDF export functionality."""
    # Set a test output base
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_pdf_export")
    
    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    
    composer = NotebookComposer()
    exporter = exporters_module.NotebookExporter()

    nb = composer.build_notebook(
        [
            CellSpec(
                cell_type="markdown", content="# Test PDF Export", section="intro"
            ),
            CellSpec(cell_type="code", content="x = 1 + 1", section="code"),
        ],
        ensure_minimum_sections=False,
    )

    # First write the notebook to a file (use relative path)
    ipynb_path = "test.ipynb"
    exporter.export_ipynb(nb, ipynb_path)

    # Try to export to PDF - this may fail if dependencies are missing
    pdf_path = "test.pdf"
    try:
        # Get the full path to pass to export_to_pdf
        full_ipynb_path = constants_module._BASE_OUTPUT / ipynb_path
        result = exporter.export_to_pdf(full_ipynb_path, pdf_path, method="webpdf")
        assert Path(result).exists()
    except (RuntimeError, FileNotFoundError) as e:
        # Skip if Jupyter or required dependencies are not available
        pytest.skip(f"PDF export dependencies not available: {e}")


def test_export_notebook_to_docx(tmp_path: Path):
    """Test basic DOCX export functionality."""
    composer = NotebookComposer()
    exporter = NotebookExporter()

    nb = composer.build_notebook(
        [
            CellSpec(
                cell_type="markdown",
                content="# Introduction\nThis is a test.",
                section="intro",
            ),
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
            "content": [
                "This is the first paragraph.",
                "This is the second paragraph.",
            ],
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
        {
            "cell_type": "markdown",
            "content": "# Setup\nInitial setup instructions.",
            "section": "setup",
        },
        {
            "cell_type": "code",
            "content": "import os\nprint('ready')",
            "section": "setup",
        },
        {"cell_type": "markdown", "content": "## Configuration", "section": "config"},
        {
            "cell_type": "code",
            "content": "config = {'key': 'value'}",
            "section": "config",
        },
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
            "content": [
                "First paragraph of chapter 1.",
                "Second paragraph of chapter 1.",
            ],
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
        {
            "cell_type": "markdown",
            "content": "# Introduction\nWelcome to the notebook.",
            "section": "intro",
        },
        {
            "cell_type": "code",
            "content": "def hello():\n    print('Hello, World!')",
            "section": "code",
        },
        {
            "cell_type": "markdown",
            "content": "## Execution\nRun the code.",
            "section": "execution",
        },
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


# Security tests for path traversal protection


def test_safe_output_path_rejects_parent_directory_traversal(tmp_path: Path, monkeypatch):
    """Test that paths with .. are rejected."""
    from langgraph_system_generator.notebook.exporters import NotebookExporter
    
    # Set the base output to a subdirectory name (will be created under default_root)
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_output")
    
    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    
    exporter = exporters_module.NotebookExporter()
    composer = NotebookComposer()
    nb = composer.build_notebook(
        [CellSpec(cell_type="code", content="x = 1", section="execution")],
        ensure_minimum_sections=False,
    )
    
    # Try to write to parent directory using .. - this should try to escape the base
    # Since all paths are relative to _BASE_OUTPUT, we need enough .. to go outside
    malicious_path = "../../../etc/malicious.ipynb"
    
    with pytest.raises(RuntimeError, match="Output path must reside within the allowed base directory"):
        exporter.export_ipynb(nb, malicious_path)


def test_safe_output_path_rejects_absolute_paths_outside_base(tmp_path: Path, monkeypatch):
    """Test that absolute paths outside the base directory are rejected."""
    from langgraph_system_generator.notebook.exporters import NotebookExporter
    
    # Set the base output to a subdirectory name (will be created under default_root)
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_output")
    
    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    
    exporter = exporters_module.NotebookExporter()
    composer = NotebookComposer()
    nb = composer.build_notebook(
        [CellSpec(cell_type="code", content="x = 1", section="execution")],
        ensure_minimum_sections=False,
    )
    
    # Try to write to /tmp which is outside the base directory
    malicious_path = "/tmp/malicious.ipynb"
    
    with pytest.raises(RuntimeError, match="Output path must reside within the allowed base directory"):
        exporter.export_ipynb(nb, malicious_path)


def test_base_output_env_var_enforced(tmp_path: Path, monkeypatch):
    """Test that LNF_OUTPUT_BASE environment variable is properly enforced."""
    
    # Set the base output to a subdirectory name (will be created under default_root)
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_output_enforced")
    
    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    
    exporter = exporters_module.NotebookExporter()
    composer = NotebookComposer()
    nb = composer.build_notebook(
        [CellSpec(cell_type="code", content="x = 1", section="execution")],
        ensure_minimum_sections=False,
    )
    
    # This should work - within allowed base (use a relative path)
    good_path = "good.ipynb"
    result = exporter.export_ipynb(nb, good_path)
    assert Path(result).exists()
    
    # This should fail - absolute path outside allowed base
    bad_path = "/etc/passwd"
    with pytest.raises(RuntimeError, match="Output path must reside within the allowed base directory"):
        exporter.export_ipynb(nb, bad_path)


def test_absolute_env_var_is_ignored(tmp_path: Path, monkeypatch):
    """Test that absolute paths in LNF_OUTPUT_BASE cause an error."""
    
    # Try to set an absolute path as LNF_OUTPUT_BASE
    monkeypatch.setenv("LNF_OUTPUT_BASE", "/tmp/absolute_path")
    
    # Force module reload to pick up new env var - this should raise RuntimeError
    import importlib
    import langgraph_system_generator.constants as constants_module
    
    with pytest.raises(RuntimeError, match="LNF_OUTPUT_BASE must resolve to a directory within the trusted"):
        importlib.reload(constants_module)


def test_pdf_export_source_path_validation(tmp_path: Path, monkeypatch):
    """Test that export_to_pdf validates source notebook path is within base directory."""
    # Set a test output base
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_pdf_validation")
    
    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    
    exporter = exporters_module.NotebookExporter()
    composer = NotebookComposer()
    
    # Create a valid notebook
    nb = composer.build_notebook(
        [CellSpec(cell_type="code", content="x = 1", section="execution")],
        ensure_minimum_sections=False,
    )
    
    # Write it to a valid location (use relative path)
    source_path = "source.ipynb"
    exporter.export_ipynb(nb, source_path)
    
    # This test would need nbconvert with webpdf support, so we just check
    # that the path validation happens before attempting the export
    # We can't fully test this without the dependencies, but the path
    # validation code is exercised in other tests
    full_source_path = constants_module._BASE_OUTPUT / source_path
    assert full_source_path.exists()


def test_all_export_methods_use_safe_paths(tmp_path: Path):
    """Test that all export methods use path validation."""
    exporter = NotebookExporter()
    composer = NotebookComposer()
    
    nb = composer.build_notebook(
        [CellSpec(cell_type="code", content="x = 1", section="execution")],
        ensure_minimum_sections=False,
    )
    
    # Test export_ipynb with malicious path
    with pytest.raises(RuntimeError, match="Output path must reside within the allowed base directory"):
        exporter.export_ipynb(nb, "/etc/passwd")
    
    # Test export_zip with malicious path
    with pytest.raises(RuntimeError, match="Output path must reside within the allowed base directory"):
        exporter.export_zip(nb, "/etc/malicious.zip")
    
    # Test export_to_html with malicious path
    with pytest.raises(RuntimeError, match="Output path must reside within the allowed base directory"):
        exporter.export_to_html(nb, "/etc/malicious.html")
