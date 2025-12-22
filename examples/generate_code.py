"""
Example: Generate LangGraph code from a prompt.

This example demonstrates how to use the LangGraphGenerator to create
multiagent system code from a text prompt.
"""

from langgraph_system_generator import LangGraphGenerator


def main():
    # Initialize the generator
    generator = LangGraphGenerator()
    
    # Define a prompt
    prompt = """
    Create a multiagent system with a researcher agent, writer agent, and reviewer agent.
    The system should work sequentially: researcher gathers information, 
    writer creates content, and reviewer validates the output.
    """
    
    # Generate the code
    print("Generating LangGraph code from prompt...")
    code = generator.generate_from_prompt(prompt)
    
    # Display the generated code
    print("\n" + "="*80)
    print("GENERATED CODE:")
    print("="*80 + "\n")
    print(code)
    
    # Optionally save to a file
    output_file = "generated_system.py"
    with open(output_file, 'w') as f:
        f.write(code)
    print(f"\n✓ Code saved to {output_file}")


if __name__ == "__main__":
    main()
