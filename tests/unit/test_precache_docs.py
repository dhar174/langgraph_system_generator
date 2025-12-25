"""Test for the precache_docs script utility functions.

Note: These functions are duplicated from the main script rather than imported
to avoid dependency issues. The main script imports DocsIndexer which requires
heavy dependencies (langchain-openai, faiss-cpu, etc.). By duplicating the
utility functions here, we can test the core logic independently without
requiring all those dependencies to be installed.
"""

import re
from pathlib import Path

import pytest
from langchain_core.documents import Document


def sanitize_filename(text: str, max_length: int = 100) -> str:
    """Convert a string to a safe filename (copied from precache_docs)."""
    text = re.sub(r'[<>:"/\\|?*]', '_', text)
    text = text.replace(' ', '_')
    text = re.sub(r'_+', '_', text)
    text = text.strip('_.')
    if len(text) > max_length:
        text = text[:max_length]
    return text or "untitled"


def generate_filename_from_url(url: str) -> str:
    """Generate a filename from a URL (copied from precache_docs)."""
    path_parts = url.rstrip('/').split('/')
    relevant_parts = [p for p in path_parts[-3:] if p and p not in ('https:', 'http:', '')]
    filename_base = '_'.join(relevant_parts)
    return sanitize_filename(filename_base)


def save_document(doc: Document, output_dir: Path) -> Path:
    """Save a document to disk (copied from precache_docs)."""
    source_url = doc.metadata.get('source', '')
    title = doc.metadata.get('title', '')
    heading = doc.metadata.get('heading', '')
    
    if title:
        filename_base = sanitize_filename(title)
    elif heading:
        filename_base = sanitize_filename(heading)
    elif source_url:
        filename_base = generate_filename_from_url(source_url)
    else:
        filename_base = "untitled"
    
    output_path = output_dir / f"{filename_base}.txt"
    counter = 1
    while output_path.exists():
        output_path = output_dir / f"{filename_base}_{counter}.txt"
        counter += 1
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("METADATA\n")
        f.write("=" * 80 + "\n")
        for key, value in doc.metadata.items():
            f.write(f"{key}: {value}\n")
        f.write("=" * 80 + "\n\n")
        f.write(doc.page_content)
    
    return output_path


def test_sanitize_filename():
    """Test filename sanitization."""
    # Test basic sanitization
    assert sanitize_filename("Hello World") == "Hello_World"
    
    # Test removal of unsafe characters
    assert sanitize_filename("file<>:\"/\\|?*name") == "file_name"
    
    # Test multiple underscores
    assert sanitize_filename("too___many___spaces") == "too_many_spaces"
    
    # Test truncation
    long_name = "a" * 150
    result = sanitize_filename(long_name, max_length=100)
    assert len(result) == 100
    
    # Test empty string fallback
    assert sanitize_filename("") == "untitled"
    assert sanitize_filename("___") == "untitled"


def test_generate_filename_from_url():
    """Test URL to filename conversion."""
    # Test standard URL
    url = "https://docs.langchain.com/oss/python/langgraph/use-graph-api"
    result = generate_filename_from_url(url)
    assert result == "python_langgraph_use-graph-api"
    
    # Test URL with trailing slash
    url = "https://example.com/path/to/doc/"
    result = generate_filename_from_url(url)
    assert "doc" in result or "path_to_doc" in result
    
    # Test simple URL
    url = "https://example.com/document"
    result = generate_filename_from_url(url)
    assert "document" in result


def test_save_document(tmp_path):
    """Test saving a document to disk."""
    # Create a test document
    doc = Document(
        page_content="This is test content\nwith multiple lines.",
        metadata={
            "source": "https://example.com/test",
            "title": "Test Document",
            "heading": "Test Heading"
        }
    )
    
    # Save the document
    output_path = save_document(doc, tmp_path)
    
    # Verify the file was created
    assert output_path.exists()
    assert output_path.suffix == ".txt"
    
    # Verify content
    content = output_path.read_text(encoding='utf-8')
    assert "Test Document" in content  # Title in metadata
    assert "This is test content" in content  # Page content
    assert "source: https://example.com/test" in content
    
    # Test duplicate filename handling
    doc2 = Document(
        page_content="Another document",
        metadata={"title": "Test Document"}  # Same title
    )
    output_path2 = save_document(doc2, tmp_path)
    
    # Should create a different file
    assert output_path2 != output_path
    assert output_path2.exists()
    assert "_1" in output_path2.name


def test_save_document_with_no_title(tmp_path):
    """Test saving a document without a title."""
    doc = Document(
        page_content="Content without title",
        metadata={"source": "https://example.com/path/to/page"}
    )
    
    output_path = save_document(doc, tmp_path)
    
    assert output_path.exists()
    # Should use URL-based filename
    assert "example" in output_path.name or "path" in output_path.name
