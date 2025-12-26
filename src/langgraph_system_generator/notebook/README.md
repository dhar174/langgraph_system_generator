# Notebook Generation Module

The notebook generation module provides comprehensive tools for creating, exporting, and formatting Jupyter notebooks and professional manuscripts.

## Features

### 1. Notebook Composition (`composer.py`)
- Build notebooks from `CellSpec` objects
- Automatic addition of required sections (setup, config, execution, etc.)
- Colab-friendly formatting
- Validation and metadata handling

### 2. Export Capabilities (`exporters.py`)
- **IPYNB**: Standard Jupyter notebook format
- **HTML**: Web-ready notebook export
- **PDF**: Print-ready notebook export (webpdf or LaTeX)
- **DOCX**: Microsoft Word document export
- **ZIP**: Bundled notebook with additional files

### 3. Professional DOCX Manuscripts (`manuscript_docx.py`)
- Print-ready DOCX with professional formatting
- Configurable typography and spacing
- Title page support
- Chapter-based structure
- Convert notebook cells to manuscript format

### 4. Professional PDF Manuscripts (`manuscript_pdf.py`)
- Print-ready PDF with professional formatting
- ReportLab-based generation
- Custom styles and layouts
- Chapter-based structure
- Convert notebook cells to manuscript format

## Quick Start

```python
from langgraph_system_generator.generator.state import CellSpec
from langgraph_system_generator.notebook import (
    NotebookComposer,
    NotebookExporter,
    ManuscriptDOCXGenerator,
    ManuscriptPDFGenerator,
)

# Create a notebook
composer = NotebookComposer()
cells = [
    CellSpec(cell_type="markdown", content="# My Notebook", section="intro"),
    CellSpec(cell_type="code", content="print('Hello!')", section="code"),
]
notebook = composer.build_notebook(cells)

# Export to various formats
exporter = NotebookExporter()
exporter.export_ipynb(notebook, "output.ipynb")
exporter.export_to_html(notebook, "output.html")
exporter.export_notebook_to_docx(notebook, "output.docx", title="My Notebook")

# Create professional manuscripts
docx_gen = ManuscriptDOCXGenerator()
chapters = [
    {"title": "Chapter 1", "content": ["First paragraph.", "Second paragraph."]}
]
docx_gen.create_manuscript(
    title="My Book",
    author="Author Name",
    chapters=chapters,
    output_path="manuscript.docx"
)

pdf_gen = ManuscriptPDFGenerator()
pdf_gen.create_manuscript(
    title="My Report",
    chapters=chapters,
    output_path="manuscript.pdf"
)
```

## API Reference

### NotebookComposer

```python
composer = NotebookComposer(colab_friendly=True)
notebook = composer.build_notebook(cells, ensure_minimum_sections=True)
path = composer.write(notebook, "output.ipynb")
```

### NotebookExporter

```python
exporter = NotebookExporter()

# Export methods
exporter.export_ipynb(notebook, "output.ipynb")
exporter.export_to_html(notebook, "output.html")
exporter.export_to_pdf("notebook.ipynb", "output.pdf", method="webpdf")
exporter.export_notebook_to_docx(notebook, "output.docx", title="My Notebook")
exporter.export_zip(notebook, "bundle.zip", extra_files=["data.json"])
```

### ManuscriptDOCXGenerator

```python
generator = ManuscriptDOCXGenerator(
    font_name="Times New Roman",
    font_size=12,
    line_spacing=2.0
)

# From chapters
generator.create_manuscript(
    title="Title",
    author="Author",
    chapters=[...],
    output_path="manuscript.docx",
    include_title_page=True
)

# From notebook cells
generator.create_notebook_manuscript(
    notebook_cells=[...],
    output_path="manuscript.docx",
    title="Title",
    author="Author"
)
```

### ManuscriptPDFGenerator

```python
generator = ManuscriptPDFGenerator(
    page_size=letter,
    font_name="Times-Roman",
    font_size=12
)

# From chapters
generator.create_manuscript(
    title="Title",
    chapters=[...],
    output_path="manuscript.pdf",
    author="Author",
    include_title_page=True
)

# From notebook cells
generator.create_notebook_manuscript(
    notebook_cells=[...],
    output_path="manuscript.pdf",
    title="Title",
    author="Author"
)
```

## Chapter Format

Chapters for manuscript generation follow this structure:

```python
chapters = [
    {
        "title": "Chapter 1: Introduction",
        "content": [
            "First paragraph text.",
            "Second paragraph text.",
        ]
    },
    {
        "title": "Chapter 2: Advanced Topics",
        "content": [
            {"heading": "Section 2.1", "text": "Content for section 2.1"},
            {"heading": "Section 2.2", "text": "Content for section 2.2"},
        ]
    },
    {
        "title": "Chapter 3: Conclusion",
        "content": "Single string content can also be used."
    }
]
```

## Requirements

All dependencies are in `requirements.txt`:
- `nbformat>=5.9.0` - Notebook format
- `nbconvert>=7.14.0` - Notebook conversion
- `python-docx>=1.1.0` - DOCX generation
- `reportlab>=4.0.0` - PDF generation

## Testing

Run tests with:
```bash
pytest tests/unit/test_notebook.py -v
```

## Documentation

See `docs/PHASE5_COMPLETE.md` for detailed implementation documentation.
