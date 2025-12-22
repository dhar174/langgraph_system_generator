"""
Example: Generate both code and notebook.

This example demonstrates the complete workflow of generating both
Python code and a Jupyter notebook from a single prompt.
"""

from langgraph_system_generator import LangGraphGenerator, NotebookGenerator
import os


def main():
    # Create output directory if it doesn't exist
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    
    # Initialize generators
    lang_generator = LangGraphGenerator()
    notebook_generator = NotebookGenerator()
    
    # Define your prompt
    prompt = """
    Build a content creation pipeline with three agents:
    1. A researcher agent that gathers information
    2. A writer agent that creates content based on research
    3. A reviewer agent that validates and improves the content
    
    The workflow should be sequential.
    """
    
    print("="*80)
    print("LANGGRAPH SYSTEM GENERATOR")
    print("="*80)
    print(f"\nPrompt: {prompt}\n")
    
    # Generate LangGraph code
    print("Step 1: Generating LangGraph code...")
    code = lang_generator.generate_from_prompt(prompt)
    
    # Save Python file
    python_file = os.path.join(output_dir, "content_pipeline.py")
    with open(python_file, 'w') as f:
        f.write(code)
    print(f"✓ Python code saved to {python_file}")
    
    # Generate Jupyter notebook
    print("\nStep 2: Generating Jupyter notebook...")
    notebook = notebook_generator.create_notebook_from_prompt(
        prompt=prompt,
        langgraph_code=code,
        title="Content Creation Pipeline"
    )
    
    # Save notebook
    notebook_file = os.path.join(output_dir, "content_pipeline.ipynb")
    notebook_generator.save_notebook(notebook, notebook_file)
    print(f"✓ Notebook saved to {notebook_file}")
    
    # Summary
    print("\n" + "="*80)
    print("GENERATION COMPLETE!")
    print("="*80)
    print(f"\nGenerated files in '{output_dir}' directory:")
    print(f"  - {os.path.basename(python_file)} (Python script)")
    print(f"  - {os.path.basename(notebook_file)} (Jupyter notebook)")
    print(f"\nTo use the notebook:")
    print(f"  jupyter notebook {notebook_file}")


if __name__ == "__main__":
    main()
