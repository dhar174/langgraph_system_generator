# LangGraph System Generator

**Prompt → Full Agentic System**

Generates entire multiagent systems based on user constraints in a simple text prompt. Creates both LangGraph Python code and Jupyter Notebooks ready for execution.

## Features

- 🤖 **LangGraph Code Generation**: Creates production-ready Python code using LangGraph
- 📓 **Jupyter Notebook Support**: Generates interactive notebooks with documentation
- 🔄 **Multiple Workflow Patterns**: Sequential, parallel, and conditional workflows
- 🎯 **Agent-Based Architecture**: Easily define multiple specialized agents
- 📝 **Template System**: Built-in templates for common patterns
- ✅ **Code Validation**: Utilities for validating and formatting generated code

## Installation

```bash
# Clone the repository
git clone https://github.com/dhar174/langgraph_system_generator.git
cd langgraph_system_generator

# Install the package
pip install -e .

# Or install with development dependencies
pip install -e ".[dev]"
```

## Quick Start

### Generate LangGraph Code

```python
from langgraph_system_generator import LangGraphGenerator

# Initialize the generator
generator = LangGraphGenerator()

# Define your system
prompt = """
Create a multiagent system with a researcher agent, writer agent, and reviewer agent.
The system should work sequentially: researcher gathers information, 
writer creates content, and reviewer validates the output.
"""

# Generate the code
code = generator.generate_from_prompt(prompt)
print(code)
```

### Generate Jupyter Notebook

```python
from langgraph_system_generator import LangGraphGenerator, NotebookGenerator

# Generate code
lang_generator = LangGraphGenerator()
code = lang_generator.generate_from_prompt(prompt)

# Create notebook
notebook_generator = NotebookGenerator()
notebook = notebook_generator.create_notebook_from_prompt(
    prompt=prompt,
    langgraph_code=code,
    title="My Multiagent System"
)

# Save notebook
notebook_generator.save_notebook(notebook, "my_system.ipynb")
```

## Examples

The `examples/` directory contains several complete examples:

- `generate_code.py` - Generate LangGraph Python code
- `generate_notebook.py` - Generate Jupyter notebooks
- `complete_workflow.py` - Complete workflow with both code and notebook generation

Run an example:

```bash
python examples/complete_workflow.py
```

## Project Structure

```
langgraph_system_generator/
├── langgraph_system_generator/    # Main package
│   ├── generators/                # Code and notebook generators
│   │   ├── langgraph_generator.py
│   │   └── notebook_generator.py
│   ├── templates/                 # Code templates
│   │   ├── langgraph_templates.py
│   │   └── notebook_templates.py
│   └── utils/                     # Utility functions
│       ├── code_utils.py
│       └── notebook_utils.py
├── examples/                      # Example scripts
├── tests/                         # Test suite
├── pyproject.toml                 # Project configuration
└── README.md                      # This file
```

## Usage

### LangGraphGenerator

The `LangGraphGenerator` class analyzes prompts and generates LangGraph code:

```python
generator = LangGraphGenerator()
code = generator.generate_from_prompt("Create a research pipeline with 3 agents")
```

### NotebookGenerator

The `NotebookGenerator` class creates Jupyter notebooks:

```python
notebook_gen = NotebookGenerator()

# From code
notebook = notebook_gen.create_notebook_from_code(
    code=generated_code,
    title="My System",
    description="System description"
)

# From prompt and code
notebook = notebook_gen.create_notebook_from_prompt(
    prompt="Original prompt",
    langgraph_code=generated_code,
    title="My System"
)

# Save to file
notebook_gen.save_notebook(notebook, "output.ipynb")
```

## Development

### Running Tests

```bash
pytest tests/
```

### Code Formatting

```bash
black langgraph_system_generator/
```

### Linting

```bash
flake8 langgraph_system_generator/
```

## Dependencies

Core dependencies:
- `langgraph` - For LangGraph functionality
- `langchain` - For LangChain integration
- `nbformat` - For Jupyter notebook creation
- `nbconvert` - For notebook conversion

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is open source and available under the MIT License.

## Roadmap

- [ ] Enhanced prompt parsing with LLM integration
- [ ] More workflow patterns (map-reduce, fan-in/fan-out)
- [ ] GUI for visual system design
- [ ] Pre-built agent templates library
- [ ] Export to other formats (Docker, Cloud Functions)
- [ ] Interactive notebook execution and testing

## Support

For issues, questions, or contributions, please visit the [GitHub repository](https://github.com/dhar174/langgraph_system_generator).
