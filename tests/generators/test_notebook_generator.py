"""Tests for NotebookGenerator."""

import pytest
import nbformat
from langgraph_system_generator.generators.notebook_generator import NotebookGenerator


class TestNotebookGenerator:
    """Test suite for NotebookGenerator."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.generator = NotebookGenerator()
        self.sample_code = '''
from langgraph.graph import StateGraph

class AgentState(TypedDict):
    messages: List[BaseMessage]

def agent_node(state):
    return state

workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_node)
app = workflow.compile()
'''
    
    def test_initialization(self):
        """Test that generator initializes correctly."""
        assert self.generator is not None
        assert self.generator.notebook is None
    
    def test_create_notebook_from_code(self):
        """Test notebook creation from code."""
        notebook = self.generator.create_notebook_from_code(
            code=self.sample_code,
            title="Test System",
            description="Test description"
        )
        
        assert isinstance(notebook, nbformat.NotebookNode)
        assert len(notebook.cells) > 0
    
    def test_create_notebook_has_title(self):
        """Test that notebook includes title."""
        title = "My Test System"
        notebook = self.generator.create_notebook_from_code(
            code=self.sample_code,
            title=title
        )
        
        # First cell should be markdown with title
        assert notebook.cells[0].cell_type == "markdown"
        assert title in notebook.cells[0].source
    
    def test_create_notebook_has_installation(self):
        """Test that notebook includes installation cell."""
        notebook = self.generator.create_notebook_from_code(
            code=self.sample_code,
            title="Test"
        )
        
        # Should have a code cell with pip install
        code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
        installation_cells = [
            cell for cell in code_cells 
            if "pip install" in cell.source
        ]
        assert len(installation_cells) > 0
    
    def test_create_notebook_from_prompt(self):
        """Test notebook creation from prompt and code."""
        prompt = "Create a test system"
        notebook = self.generator.create_notebook_from_prompt(
            prompt=prompt,
            langgraph_code=self.sample_code,
            title="Test System"
        )
        
        assert isinstance(notebook, nbformat.NotebookNode)
        assert len(notebook.cells) > 0
        
        # Check that prompt is included
        markdown_cells = [
            cell for cell in notebook.cells 
            if cell.cell_type == "markdown"
        ]
        prompt_mentioned = any(prompt in cell.source for cell in markdown_cells)
        assert prompt_mentioned
    
    def test_split_code_into_sections(self):
        """Test code splitting into sections."""
        sections = self.generator._split_code_into_sections(self.sample_code)
        
        assert isinstance(sections, list)
        assert len(sections) > 0
        
        # Each section should be a tuple of (title, code)
        for section in sections:
            assert isinstance(section, tuple)
            assert len(section) == 2
    
    def test_add_markdown_cell(self):
        """Test adding markdown cell."""
        self.generator.add_markdown_cell("# Test Header")
        
        assert self.generator.notebook is not None
        assert len(self.generator.notebook.cells) == 1
        assert self.generator.notebook.cells[0].cell_type == "markdown"
        assert "Test Header" in self.generator.notebook.cells[0].source
    
    def test_add_code_cell(self):
        """Test adding code cell."""
        test_code = "print('hello')"
        self.generator.add_code_cell(test_code)
        
        assert self.generator.notebook is not None
        assert len(self.generator.notebook.cells) == 1
        assert self.generator.notebook.cells[0].cell_type == "code"
        assert test_code in self.generator.notebook.cells[0].source
    
    def test_create_installation_cell(self):
        """Test installation cell creation."""
        cell = self.generator._create_installation_cell()
        
        assert cell.cell_type == "code"
        assert "pip install" in cell.source
        assert "langgraph" in cell.source
    
    def test_create_usage_cell(self):
        """Test usage cell creation."""
        cell = self.generator._create_usage_cell()
        
        assert cell.cell_type == "code"
        assert "initial_state" in cell.source
        assert "app.invoke" in cell.source
    
    def test_notebook_structure(self):
        """Test overall notebook structure."""
        notebook = self.generator.create_notebook_from_prompt(
            prompt="Test prompt",
            langgraph_code=self.sample_code,
            title="Test"
        )
        
        # Should have mix of markdown and code cells
        markdown_count = sum(
            1 for cell in notebook.cells 
            if cell.cell_type == "markdown"
        )
        code_count = sum(
            1 for cell in notebook.cells 
            if cell.cell_type == "code"
        )
        
        assert markdown_count > 0
        assert code_count > 0
    
    def test_save_notebook(self, tmp_path):
        """Test saving notebook to file."""
        notebook = self.generator.create_notebook_from_code(
            code=self.sample_code,
            title="Test"
        )
        
        output_file = tmp_path / "test.ipynb"
        self.generator.save_notebook(notebook, str(output_file))
        
        assert output_file.exists()
        
        # Verify it's valid notebook
        with open(output_file, 'r') as f:
            loaded_nb = nbformat.read(f, as_version=4)
        assert isinstance(loaded_nb, nbformat.NotebookNode)
    
    def test_save_notebook_adds_extension(self, tmp_path):
        """Test that .ipynb extension is added if missing."""
        notebook = self.generator.create_notebook_from_code(
            code=self.sample_code,
            title="Test"
        )
        
        output_file = tmp_path / "test"
        self.generator.save_notebook(notebook, str(output_file))
        
        expected_file = tmp_path / "test.ipynb"
        assert expected_file.exists()
