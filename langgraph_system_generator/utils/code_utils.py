"""Utility functions for code formatting and validation."""

import ast
from typing import Optional


def validate_python_code(code: str) -> tuple[bool, Optional[str]]:
    """
    Validate that a string contains valid Python code.
    
    Args:
        code: Python code string to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        ast.parse(code)
        return True, None
    except SyntaxError as e:
        return False, f"Syntax error at line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)


def format_code(code: str, indent: int = 4) -> str:
    """
    Format Python code with consistent indentation.
    
    Args:
        code: Python code to format
        indent: Number of spaces for indentation
        
    Returns:
        Formatted code
    """
    # Basic formatting - can be enhanced with black or autopep8
    lines = code.split('\n')
    formatted_lines = []
    
    for line in lines:
        # Remove trailing whitespace
        line = line.rstrip()
        formatted_lines.append(line)
    
    return '\n'.join(formatted_lines)


def extract_imports(code: str) -> list[str]:
    """
    Extract import statements from Python code.
    
    Args:
        code: Python code
        
    Returns:
        List of import statements
    """
    imports = []
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(f"import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                names = ', '.join(alias.name for alias in node.names)
                imports.append(f"from {module} import {names}")
    except:
        pass
    
    return imports


def clean_code(code: str) -> str:
    """
    Clean up generated code by removing extra blank lines and trailing spaces.
    
    Args:
        code: Python code to clean
        
    Returns:
        Cleaned code
    """
    lines = code.split('\n')
    cleaned = []
    prev_blank = False
    
    for line in lines:
        # Remove trailing whitespace
        line = line.rstrip()
        
        # Skip multiple consecutive blank lines
        if line == '':
            if not prev_blank:
                cleaned.append(line)
                prev_blank = True
        else:
            cleaned.append(line)
            prev_blank = False
    
    # Remove leading/trailing blank lines
    while cleaned and cleaned[0] == '':
        cleaned.pop(0)
    while cleaned and cleaned[-1] == '':
        cleaned.pop()
    
    return '\n'.join(cleaned)
