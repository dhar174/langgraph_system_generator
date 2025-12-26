"""Tests for notebook utility functions."""

from langgraph_system_generator.notebook.utils import escape_xml_chars, parse_markdown_heading


def test_escape_xml_chars():
    """Test XML character escaping."""
    assert escape_xml_chars("Hello World") == "Hello World"
    assert escape_xml_chars("x < y") == "x &lt; y"
    assert escape_xml_chars("x > y") == "x &gt; y"
    assert escape_xml_chars("A & B") == "A &amp; B"
    assert escape_xml_chars("x < y & z > w") == "x &lt; y &amp; z &gt; w"


def test_parse_markdown_heading():
    """Test markdown heading parsing."""
    # Valid headings
    assert parse_markdown_heading("# Title") == (1, "Title")
    assert parse_markdown_heading("## Section") == (2, "Section")
    assert parse_markdown_heading("### Subsection") == (3, "Subsection")

    # With extra spaces
    assert parse_markdown_heading("  # Title  ") == (1, "Title")
    assert parse_markdown_heading("  ## Section  ") == (2, "Section")

    # Not headings
    assert parse_markdown_heading("Regular text") is None
    assert parse_markdown_heading("") is None
    assert parse_markdown_heading("   ") is None
    assert parse_markdown_heading("#NoSpace") is None
    assert parse_markdown_heading("##NoSpace") is None
