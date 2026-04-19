"""Notebook composition, export, and manuscript generation."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "NotebookComposer",
    "NotebookExporter",
    "ManuscriptDOCXGenerator",
    "ManuscriptPDFGenerator",
]


def __getattr__(name: str):
    """Lazily expose notebook helpers to avoid circular imports during cold loads."""

    if name == "NotebookComposer":
        return import_module("langgraph_system_generator.notebook.composer").NotebookComposer
    if name == "NotebookExporter":
        return import_module("langgraph_system_generator.notebook.exporters").NotebookExporter
    if name == "ManuscriptDOCXGenerator":
        return import_module(
            "langgraph_system_generator.notebook.manuscript_docx"
        ).ManuscriptDOCXGenerator
    if name == "ManuscriptPDFGenerator":
        return import_module(
            "langgraph_system_generator.notebook.manuscript_pdf"
        ).ManuscriptPDFGenerator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
