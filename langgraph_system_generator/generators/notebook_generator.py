"""
Jupyter Notebook generator module.

Generates Jupyter notebooks containing LangGraph code and documentation.
"""

from typing import List, Dict, Optional, Any
import nbformat
from nbformat.v4 import new_notebook, new_code_cell, new_markdown_cell


class NotebookGenerator:
    """
    Generates Jupyter notebooks for multiagent systems.
    
    This class creates .ipynb files with properly formatted cells containing
    LangGraph code, documentation, and examples.
    """
    
    def __init__(self):
        """Initialize the notebook generator."""
        self.notebook = None
    
    def create_notebook_from_code(
        self,
        code: str,
        title: str = "LangGraph Multiagent System",
        description: str = ""
    ) -> nbformat.NotebookNode:
        """
        Create a Jupyter notebook from generated code.
        
        Args:
            code: Generated Python code
            title: Title for the notebook
            description: Description of the system
            
        Returns:
            NotebookNode object
        """
        nb = new_notebook()
        
        # Add title cell
        nb.cells.append(new_markdown_cell(f"# {title}\n\n{description}"))
        
        # Add installation cell
        nb.cells.append(self._create_installation_cell())
        
        # Add imports and code
        code_sections = self._split_code_into_sections(code)
        
        for section_title, section_code in code_sections:
            if section_title:
                nb.cells.append(new_markdown_cell(f"## {section_title}"))
            nb.cells.append(new_code_cell(section_code))
        
        # Add usage example cell
        nb.cells.append(self._create_usage_cell())
        
        self.notebook = nb
        return nb
    
    def create_notebook_from_prompt(
        self,
        prompt: str,
        langgraph_code: str,
        title: Optional[str] = None
    ) -> nbformat.NotebookNode:
        """
        Create a notebook from a user prompt and generated code.
        
        Args:
            prompt: Original user prompt
            langgraph_code: Generated LangGraph code
            title: Optional custom title
            
        Returns:
            NotebookNode object
        """
        if title is None:
            title = "Generated Multiagent System"
        
        nb = new_notebook()
        
        # Add title and description
        nb.cells.append(new_markdown_cell(
            f"# {title}\n\n"
            f"This notebook was generated based on the following prompt:\n\n"
            f"> {prompt}"
        ))
        
        # Add installation instructions
        nb.cells.append(new_markdown_cell("## Installation\n\n"
            "Install the required dependencies:"))
        nb.cells.append(self._create_installation_cell())
        
        # Add the generated code
        nb.cells.append(new_markdown_cell("## System Implementation"))
        
        code_sections = self._split_code_into_sections(langgraph_code)
        for section_title, section_code in code_sections:
            if section_title:
                nb.cells.append(new_markdown_cell(f"### {section_title}"))
            nb.cells.append(new_code_cell(section_code))
        
        # Add usage section
        nb.cells.append(new_markdown_cell("## Usage\n\n"
            "Run the system with your own input:"))
        nb.cells.append(self._create_usage_cell())
        
        self.notebook = nb
        return nb
    
    def save_notebook(self, notebook: nbformat.NotebookNode, filename: str):
        """
        Save a notebook to a file.
        
        Args:
            notebook: NotebookNode to save
            filename: Output filename (should end with .ipynb)
        """
        if not filename.endswith('.ipynb'):
            filename += '.ipynb'
        
        with open(filename, 'w', encoding='utf-8') as f:
            nbformat.write(notebook, f)
    
    def generate_and_save(
        self,
        code: str,
        filename: str,
        title: str = "LangGraph Multiagent System",
        description: str = ""
    ):
        """
        Generate a notebook from code and save it to a file.
        
        Args:
            code: Generated Python code
            filename: Output filename
            title: Notebook title
            description: System description
        """
        notebook = self.create_notebook_from_code(code, title, description)
        self.save_notebook(notebook, filename)
    
    def _create_installation_cell(self) -> nbformat.NotebookNode:
        """Create a cell with installation instructions."""
        code = """!pip install langgraph langchain langchain-core langchain-openai"""
        return new_code_cell(code)
    
    def _create_usage_cell(self) -> nbformat.NotebookNode:
        """Create a cell with usage example."""
        code = """# Run the multiagent system
initial_state = {
    "messages": [HumanMessage(content="Your input here")],
    "context": "Your context here"
}

result = app.invoke(initial_state)
print("Result:", result)"""
        return new_code_cell(code)
    
    def _split_code_into_sections(self, code: str) -> List[tuple]:
        """
        Split code into logical sections for better notebook organization.
        
        Args:
            code: Python code to split
            
        Returns:
            List of (section_title, code) tuples
        """
        sections = []
        current_section = []
        current_title = None
        
        lines = code.split('\n')
        
        for line in lines:
            # Check for major section markers
            if line.startswith('from ') or line.startswith('import '):
                if current_section and current_title != "Imports":
                    sections.append((current_title, '\n'.join(current_section)))
                    current_section = []
                current_title = "Imports"
                current_section.append(line)
            elif line.startswith('class AgentState'):
                if current_section:
                    sections.append((current_title, '\n'.join(current_section)))
                    current_section = []
                current_title = "State Definition"
                current_section.append(line)
            elif line.startswith('def ') and '_node(' in line:
                if current_section and current_title == "Agent Nodes":
                    current_section.append(line)
                else:
                    if current_section:
                        sections.append((current_title, '\n'.join(current_section)))
                    current_section = [line]
                    current_title = "Agent Nodes"
            elif line.startswith('# Create the graph') or line.startswith('workflow = StateGraph'):
                if current_section:
                    sections.append((current_title, '\n'.join(current_section)))
                    current_section = []
                current_title = "Graph Construction"
                current_section.append(line)
            elif line.startswith('if __name__'):
                if current_section:
                    sections.append((current_title, '\n'.join(current_section)))
                    current_section = []
                current_title = "Example Usage"
                current_section.append(line)
            else:
                current_section.append(line)
        
        # Add the last section
        if current_section:
            sections.append((current_title, '\n'.join(current_section)))
        
        # Clean up sections - remove empty ones and trim whitespace
        cleaned_sections = []
        for title, code in sections:
            code = code.strip()
            if code:
                cleaned_sections.append((title, code))
        
        return cleaned_sections
    
    def add_markdown_cell(self, content: str):
        """
        Add a markdown cell to the current notebook.
        
        Args:
            content: Markdown content
        """
        if self.notebook is None:
            self.notebook = new_notebook()
        self.notebook.cells.append(new_markdown_cell(content))
    
    def add_code_cell(self, code: str):
        """
        Add a code cell to the current notebook.
        
        Args:
            code: Python code
        """
        if self.notebook is None:
            self.notebook = new_notebook()
        self.notebook.cells.append(new_code_cell(code))
