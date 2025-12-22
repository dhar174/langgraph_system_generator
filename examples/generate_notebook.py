"""
Example: Generate a Jupyter notebook from a prompt.

This example demonstrates how to create a complete Jupyter notebook
containing LangGraph code and documentation.
"""

from langgraph_system_generator import LangGraphGenerator, NotebookGenerator


def main():
    # Initialize generators
    lang_generator = LangGraphGenerator()
    notebook_generator = NotebookGenerator()
    
    # Define a prompt
    prompt = """
    Create a research assistant system with a researcher agent and writer agent.
    The researcher should gather information and the writer should create a summary.
    """
    
    # Generate the LangGraph code
    print("Generating LangGraph code...")
    code = lang_generator.generate_from_prompt(prompt)
    
    # Create a notebook from the code
    print("Creating Jupyter notebook...")
    notebook = notebook_generator.create_notebook_from_prompt(
        prompt=prompt,
        langgraph_code=code,
        title="Research Assistant System"
    )
    
    # Save the notebook
    output_file = "research_assistant.ipynb"
    notebook_generator.save_notebook(notebook, output_file)
    
    print(f"\n✓ Notebook saved to {output_file}")
    print(f"  Open it with: jupyter notebook {output_file}")


if __name__ == "__main__":
    main()
