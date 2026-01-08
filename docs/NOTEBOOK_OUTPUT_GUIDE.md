# Notebook and Document Output Guide

This guide explains how to use the notebook and document export features of the LangGraph Notebook Foundry.

## Overview

The generator workflow automatically produces complete, production-ready notebooks and documentation in multiple formats. After generating cells based on your prompt, the system:

1. Builds a complete Jupyter notebook using `NotebookComposer`
2. Exports to multiple formats using `NotebookExporter`
3. Updates the manifest with paths to all generated artifacts

## Available Formats

### Jupyter Notebook (.ipynb)

The primary output format. A fully functional Jupyter notebook with:
- Required sections (setup, config, graph, execution, export, troubleshooting)
- Colab-friendly metadata
- Validated nbformat structure
- Ready to run in Jupyter Lab, Jupyter Notebook, or Google Colab

### HTML (.html)

Web-ready export suitable for:
- Viewing in browsers
- Sharing via email or web hosting
- Documentation websites
- Embedding in web applications

Generated using `nbconvert`'s HTML exporter with full styling and syntax highlighting.

### DOCX (.docx)

Microsoft Word document format for:
- Editing and collaboration
- Creating documentation
- Offline review
- Integration with Word workflows

Includes proper heading styles, code formatting, and paragraph structure.

### PDF (.pdf)

Print-ready PDF document (optional, requires additional dependencies):
- Professional manuscripts
- Archival purposes
- Print distribution
- Read-only sharing

PDF export uses either `webpdf` (Chromium-based, more reliable) or `latex` (requires LaTeX installation) methods.

### ZIP Bundle (.zip)

Complete package containing:
- The notebook file (`notebook.ipynb`)
- JSON artifacts (`notebook_plan.json`, `generated_cells.json`)
- Convenient single-file distribution

## Usage

### CLI Usage

#### Generate All Formats (Default)

```bash
lnf generate "Create a chatbot with routing" --output ./output/chatbot
```

This generates:
- `notebook.ipynb`
- `notebook.html`
- `notebook.docx`
- `notebook_bundle.zip`
- `notebook_plan.json`
- `generated_cells.json`
- `manifest.json`

#### Select Specific Formats

```bash
lnf generate "Create a chatbot" --output ./output/chatbot --formats ipynb html
```

Only generates the specified formats plus JSON artifacts.

#### Available Format Options

- `ipynb` - Jupyter notebook
- `html` - HTML export
- `docx` - Word document
- `pdf` - PDF export (may require additional dependencies)
- `zip` - ZIP bundle

### API Usage

#### Request All Formats

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Create a multi-agent system",
    "mode": "stub",
    "output_dir": "./output/my_system"
  }'
```

#### Request Specific Formats

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Create a multi-agent system",
    "mode": "stub",
    "output_dir": "./output/my_system",
    "formats": ["ipynb", "html", "docx"]
  }'
```

#### Response Structure

```json
{
  "success": true,
  "mode": "stub",
  "prompt": "Create a multi-agent system",
  "manifest": {
    "prompt": "Create a multi-agent system",
    "mode": "stub",
    "architecture_type": "router",
    "cell_count": 15,
    "plan_title": "LangGraph Workflow: Create a multi-agent system",
    "notebook_path": "./output/my_system/notebook.ipynb",
    "html_path": "./output/my_system/notebook.html",
    "docx_path": "./output/my_system/notebook.docx",
    "zip_path": "./output/my_system/notebook_bundle.zip",
    "plan_path": "./output/my_system/notebook_plan.json",
    "cells_path": "./output/my_system/generated_cells.json"
  },
  "manifest_path": "./output/my_system/manifest.json",
  "output_dir": "./output/my_system"
}
```

### Programmatic Usage

```python
from langgraph_system_generator.cli import generate_artifacts

# Generate all formats
artifacts = await generate_artifacts(
    "Create a chatbot",
    output_dir="./output/chatbot",
    mode="stub",
    formats=None  # None or empty list generates all formats
)

# Generate specific formats
artifacts = await generate_artifacts(
    "Create a chatbot",
    output_dir="./output/chatbot",
    mode="stub",
    formats=["ipynb", "html", "docx"]
)

# Access generated file paths
notebook_path = artifacts["manifest"]["notebook_path"]
html_path = artifacts["manifest"]["html_path"]
```

## Notebook Structure

Generated notebooks include these required sections:

1. **Setup**: Package installation and imports
2. **Config**: Environment configuration and API keys
3. **Graph**: LangGraph state and node definitions
4. **Execution**: Graph building and invocation
5. **Export**: Results export and visualization
6. **Troubleshooting**: Common issues and solutions

The `NotebookComposer` automatically adds these sections if not present, ensuring every generated notebook is complete and runnable.

## Error Handling

Export errors are handled gracefully:

```json
{
  "notebook_path": "./output/notebook.ipynb",
  "html_path": "./output/notebook.html",
  "pdf_error": "webpdf export failed: jupyter command not found..."
}
```

If an export fails:
- The error is captured in the manifest (e.g., `pdf_error`)
- Other exports continue normally
- The main notebook generation always succeeds

## Dependencies

Required packages (included in `requirements.txt`):

- `nbformat>=5.9.0` - Notebook format
- `nbconvert>=7.14.0` - Notebook conversion
- `python-docx>=1.1.0` - DOCX generation
- `reportlab>=4.0.0` - PDF generation (for manuscripts)

Optional for PDF export:
- Jupyter (for `webpdf` method)
- Chromium/Chrome (for `webpdf` method)
- LaTeX (for `latex` method)

## Advanced: Custom Notebook Composition

For advanced use cases, you can use the notebook modules directly:

```python
from langgraph_system_generator.generator.state import CellSpec
from langgraph_system_generator.notebook import (
    NotebookComposer,
    NotebookExporter,
)

# Create cells
cells = [
    CellSpec(cell_type="markdown", content="# My Notebook", section="intro"),
    CellSpec(cell_type="code", content="print('Hello!')", section="code"),
]

# Build notebook
composer = NotebookComposer(colab_friendly=True)
notebook = composer.build_notebook(cells, ensure_minimum_sections=True)

# Export to formats
exporter = NotebookExporter()
exporter.export_ipynb(notebook, "output.ipynb")
exporter.export_to_html(notebook, "output.html")
exporter.export_notebook_to_docx(notebook, "output.docx", title="My Notebook")
exporter.export_zip(notebook, "bundle.zip", extra_files=["data.json"])
```

## Professional Manuscripts

For high-quality documentation, use the manuscript generators:

```python
from langgraph_system_generator.notebook import (
    ManuscriptDOCXGenerator,
    ManuscriptPDFGenerator,
)

# DOCX manuscript
docx_gen = ManuscriptDOCXGenerator(
    font_name="Times New Roman",
    font_size=12,
    line_spacing=2.0
)

chapters = [
    {
        "title": "Chapter 1: Introduction",
        "content": ["First paragraph.", "Second paragraph."]
    }
]

docx_gen.create_manuscript(
    title="My Documentation",
    author="Author Name",
    chapters=chapters,
    output_path="manuscript.docx"
)

# PDF manuscript
pdf_gen = ManuscriptPDFGenerator()
pdf_gen.create_manuscript(
    title="My Documentation",
    chapters=chapters,
    output_path="manuscript.pdf"
)
```

## Testing

Run tests for notebook outputs:

```bash
# Test notebook generation
pytest tests/unit/test_notebook_outputs.py -v

# Test CLI and API
pytest tests/unit/test_cli_api.py -v

# Test notebook composition and export
pytest tests/unit/test_notebook.py -v
```

## Troubleshooting

### PDF Export Fails

If PDF export fails:
1. Ensure Jupyter is installed and in PATH: `jupyter --version`
2. For webpdf: Install Chromium/Chrome
3. For latex: Install LaTeX distribution (TeX Live, MiKTeX)
4. Consider using only ipynb, html, and docx formats

### Large Notebooks

For notebooks with many cells:
- HTML export may be large (compression recommended)
- PDF export may take longer
- Consider splitting into multiple notebooks

### Custom Styling

To customize exported document appearance:
- Edit the notebook metadata before export
- Use ManuscriptDOCXGenerator/ManuscriptPDFGenerator for full control
- Modify CSS for HTML exports

## See Also

- [Notebook Module README](../src/langgraph_system_generator/notebook/README.md) - Detailed API reference
- [PHASE5_COMPLETE.md](PHASE5_COMPLETE.md) - Export and QA features
- [CLI Documentation](../README.md#cli) - Command-line interface guide
- [API Documentation](../README.md#api) - REST API reference
