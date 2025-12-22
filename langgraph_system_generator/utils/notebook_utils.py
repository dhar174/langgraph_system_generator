"""Utility functions for working with notebooks."""

import nbformat
from typing import Dict, Any, List


def validate_notebook(notebook: nbformat.NotebookNode) -> tuple[bool, str]:
    """
    Validate a notebook structure.
    
    Args:
        notebook: NotebookNode to validate
        
    Returns:
        Tuple of (is_valid, message)
    """
    try:
        nbformat.validate(notebook)
        return True, "Notebook is valid"
    except nbformat.ValidationError as e:
        return False, f"Validation error: {str(e)}"


def count_cells(notebook: nbformat.NotebookNode) -> Dict[str, int]:
    """
    Count the number of cells by type in a notebook.
    
    Args:
        notebook: NotebookNode to analyze
        
    Returns:
        Dictionary with cell type counts
    """
    counts = {"code": 0, "markdown": 0, "raw": 0}
    
    for cell in notebook.cells:
        cell_type = cell.get("cell_type", "unknown")
        if cell_type in counts:
            counts[cell_type] += 1
    
    return counts


def extract_code_from_notebook(notebook: nbformat.NotebookNode) -> List[str]:
    """
    Extract all code cells from a notebook.
    
    Args:
        notebook: NotebookNode to extract from
        
    Returns:
        List of code strings
    """
    code_cells = []
    
    for cell in notebook.cells:
        if cell.get("cell_type") == "code":
            code_cells.append(cell.get("source", ""))
    
    return code_cells


def notebook_to_script(notebook: nbformat.NotebookNode) -> str:
    """
    Convert a notebook to a Python script.
    
    Args:
        notebook: NotebookNode to convert
        
    Returns:
        Python script as string
    """
    script_parts = []
    
    for cell in notebook.cells:
        if cell.get("cell_type") == "code":
            source = cell.get("source", "")
            if source.strip():
                script_parts.append(source)
        elif cell.get("cell_type") == "markdown":
            # Add markdown as comments
            source = cell.get("source", "")
            if source.strip():
                commented = '\n'.join(f"# {line}" for line in source.split('\n'))
                script_parts.append(commented)
    
    return '\n\n'.join(script_parts)
