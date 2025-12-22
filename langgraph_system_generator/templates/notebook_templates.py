"""
Notebook templates for common patterns.
"""

NOTEBOOK_HEADER_TEMPLATE = """# {title}

{description}

This notebook contains a LangGraph-based multiagent system.
"""

INSTALLATION_TEMPLATE = """## Installation

Install the required dependencies:"""

INSTALLATION_CODE = """!pip install langgraph langchain langchain-core langchain-openai"""

USAGE_TEMPLATE = """## Usage

Run the multiagent system with your input:"""

USAGE_CODE_TEMPLATE = """# Initialize the system
initial_state = {{
    "messages": [HumanMessage(content="{default_input}")],
    "context": "{default_context}"
}}

# Run the workflow
result = app.invoke(initial_state)

# Display results
print("Result:", result)
"""

SECTION_HEADERS = {
    "imports": "## Imports",
    "state": "## State Definition",
    "agents": "## Agent Nodes",
    "graph": "## Graph Construction",
    "usage": "## Example Usage"
}
