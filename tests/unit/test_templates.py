"""Tests for notebook cell templates."""

from __future__ import annotations

from langgraph_system_generator.notebook import templates


def test_installation_and_imports_returns_cells_with_imports():
    """Ensure installation/imports returns markdown + code cells with imports."""
    cells = templates.installation_and_imports()

    assert [cell.cell_type for cell in cells] == ["markdown", "code"]

    code = cells[1].content
    assert "from langgraph.graph import END, START, MessagesState, StateGraph" in code
    assert "from langchain_openai import ChatOpenAI" in code


def test_installation_and_imports_respects_custom_packages():
    """Ensure installation/imports uses custom package list."""
    packages = ["langgraph", "custom-lib"]
    cells = templates.installation_and_imports(packages=packages)

    code = cells[1].content
    assert f"for _pkg in {packages!r}" in code


def test_configuration_cell_includes_keys_and_model():
    """Ensure configuration cell includes key handling and model parameter."""
    cells = templates.configuration_cell(model="gpt-test")

    assert [cell.cell_type for cell in cells] == ["markdown", "code"]

    code = cells[1].content
    assert "OPENAI_API_KEY" in code
    assert "ANTHROPIC_API_KEY" in code
    assert "getpass" in code
    assert "MODEL = os.getenv(\"MODEL\", \"gpt-test\")" in code
