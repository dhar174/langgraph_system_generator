# Usage Guide

This guide provides detailed instructions on how to use the LangGraph System Generator.

## Table of Contents

1. [Installation](#installation)
2. [Quick Start](#quick-start)
3. [Generating LangGraph Code](#generating-langgraph-code)
4. [Generating Jupyter Notebooks](#generating-jupyter-notebooks)
5. [Advanced Usage](#advanced-usage)
6. [API Reference](#api-reference)

## Installation

### From Source

```bash
git clone https://github.com/dhar174/langgraph_system_generator.git
cd langgraph_system_generator
pip install -e .
```

### Install Dependencies

```bash
pip install langgraph langchain langchain-core nbformat nbconvert
```

## Quick Start

### Generate Code

```python
from langgraph_system_generator import LangGraphGenerator

# Create generator
generator = LangGraphGenerator()

# Generate code from prompt
prompt = "Create a research assistant with a researcher and writer agent"
code = generator.generate_from_prompt(prompt)

# Save to file
with open("my_system.py", "w") as f:
    f.write(code)
```

### Generate Notebook

```python
from langgraph_system_generator import LangGraphGenerator, NotebookGenerator

# Generate code
lang_gen = LangGraphGenerator()
code = lang_gen.generate_from_prompt("Create a multi-agent system")

# Create notebook
nb_gen = NotebookGenerator()
notebook = nb_gen.create_notebook_from_prompt(
    prompt="Create a multi-agent system",
    langgraph_code=code,
    title="My System"
)

# Save notebook
nb_gen.save_notebook(notebook, "my_system.ipynb")
```

## Generating LangGraph Code

### Basic Generation

```python
from langgraph_system_generator import LangGraphGenerator

generator = LangGraphGenerator()
code = generator.generate_from_prompt("Your prompt here")
```

### Workflow Types

The generator supports different workflow patterns:

#### Sequential Workflow

```python
prompt = """
Create a sequential pipeline with:
- Researcher agent to gather data
- Writer agent to create content
- Reviewer agent to validate
"""
code = generator.generate_from_prompt(prompt)
```

#### Parallel Workflow

```python
prompt = """
Create a parallel processing system where multiple agents
work on the same input simultaneously
"""
code = generator.generate_from_prompt(prompt)
```

### Agent Detection

The generator automatically detects agents mentioned in your prompt:

```python
# Automatically creates "researcher" and "writer" agents
prompt = "Build a system with a researcher and writer"
code = generator.generate_from_prompt(prompt)
```

## Generating Jupyter Notebooks

### From Code

```python
from langgraph_system_generator import NotebookGenerator

nb_gen = NotebookGenerator()
notebook = nb_gen.create_notebook_from_code(
    code=generated_code,
    title="My System",
    description="System description"
)
nb_gen.save_notebook(notebook, "output.ipynb")
```

### From Prompt and Code

```python
notebook = nb_gen.create_notebook_from_prompt(
    prompt="Original user prompt",
    langgraph_code=generated_code,
    title="My System"
)
```

### Custom Cells

```python
nb_gen = NotebookGenerator()

# Add markdown
nb_gen.add_markdown_cell("# My Header")

# Add code
nb_gen.add_code_cell("print('Hello, World!')")

# Save
nb_gen.save_notebook(nb_gen.notebook, "custom.ipynb")
```

## Advanced Usage

### Complete Workflow

```python
import os
from langgraph_system_generator import LangGraphGenerator, NotebookGenerator

# Setup
output_dir = "output"
os.makedirs(output_dir, exist_ok=True)

# Define system
prompt = """
Create a content generation system with:
1. Research agent - gathers information
2. Writing agent - creates content
3. Editing agent - refines the output
Sequential workflow.
"""

# Generate code
lang_gen = LangGraphGenerator()
code = lang_gen.generate_from_prompt(prompt)

# Save Python file
python_file = os.path.join(output_dir, "system.py")
with open(python_file, 'w') as f:
    f.write(code)

# Generate notebook
nb_gen = NotebookGenerator()
notebook = nb_gen.create_notebook_from_prompt(
    prompt=prompt,
    langgraph_code=code,
    title="Content Generation System"
)

# Save notebook
notebook_file = os.path.join(output_dir, "system.ipynb")
nb_gen.save_notebook(notebook, notebook_file)

print(f"✓ Generated {python_file}")
print(f"✓ Generated {notebook_file}")
```

### Validation

```python
from langgraph_system_generator.utils import validate_python_code, validate_notebook

# Validate generated code
is_valid, error = validate_python_code(code)
if is_valid:
    print("✓ Code is valid")
else:
    print(f"✗ Error: {error}")

# Validate notebook
is_valid, message = validate_notebook(notebook)
if is_valid:
    print("✓ Notebook is valid")
```

### Code Formatting

```python
from langgraph_system_generator.utils import clean_code, format_code

# Clean up code
cleaned = clean_code(code)

# Format code
formatted = format_code(code, indent=4)
```

## API Reference

### LangGraphGenerator

**Methods:**
- `generate_from_prompt(prompt: str) -> str`: Generate LangGraph code from prompt
- `_extract_agents(prompt: str) -> List[str]`: Extract agent names from prompt
- `_extract_workflow(prompt: str) -> str`: Determine workflow type
- `_generate_code(requirements: Dict) -> str`: Generate the actual code

### NotebookGenerator

**Methods:**
- `create_notebook_from_code(code, title, description) -> NotebookNode`: Create notebook from code
- `create_notebook_from_prompt(prompt, langgraph_code, title) -> NotebookNode`: Create from prompt and code
- `save_notebook(notebook, filename)`: Save notebook to file
- `add_markdown_cell(content)`: Add markdown cell
- `add_code_cell(code)`: Add code cell

### Utility Functions

**code_utils:**
- `validate_python_code(code) -> Tuple[bool, Optional[str]]`: Validate Python syntax
- `format_code(code, indent) -> str`: Format code
- `extract_imports(code) -> List[str]`: Extract import statements
- `clean_code(code) -> str`: Clean up code formatting

**notebook_utils:**
- `validate_notebook(notebook) -> Tuple[bool, str]`: Validate notebook structure
- `count_cells(notebook) -> Dict[str, int]`: Count cells by type
- `extract_code_from_notebook(notebook) -> List[str]`: Extract code cells
- `notebook_to_script(notebook) -> str`: Convert notebook to script

## Examples

See the `examples/` directory for complete working examples:
- `generate_code.py` - Basic code generation
- `generate_notebook.py` - Basic notebook generation
- `complete_workflow.py` - Full workflow with both outputs

Run an example:
```bash
python examples/complete_workflow.py
```

## Troubleshooting

### Import Errors

If you get import errors, ensure all dependencies are installed:
```bash
pip install langgraph langchain langchain-core nbformat nbconvert
```

### Module Not Found

If the module is not found, install in development mode:
```bash
pip install -e .
```

### Notebook Won't Open

Ensure Jupyter is installed:
```bash
pip install jupyter
jupyter notebook output/your_notebook.ipynb
```
