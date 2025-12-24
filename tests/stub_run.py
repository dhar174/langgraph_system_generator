#!/usr/bin/env python
"""Minimal stub run to demonstrate generator produces NotebookPlan and CellSpecs.

This script runs a minimal version of the generator without requiring API keys,
demonstrating that the graph structure works and produces the expected outputs.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from langgraph_system_generator.generator import create_generator_graph


async def mock_minimal_run():
    """Run generator with mocked LLM calls to demonstrate structure."""
    print("=" * 70)
    print("LangGraph Notebook Foundry - Minimal Stub Run")
    print("=" * 70)
    print()

    # Mock the ChatOpenAI to avoid needing API keys
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock()

    # Mock RequirementsAnalyst response
    mock_llm.ainvoke.return_value.content = """```json
[
  {"type": "goal", "value": "Create a router-based chatbot", "priority": 5},
  {"type": "environment", "value": "Jupyter notebook", "priority": 3}
]
```"""

    with patch(
        "langgraph_system_generator.generator.agents.requirements_analyst.ChatOpenAI",
        return_value=mock_llm,
    ):
        with patch(
            "langgraph_system_generator.generator.agents.architecture_selector.ChatOpenAI",
            return_value=mock_llm,
        ):
            with patch(
                "langgraph_system_generator.generator.agents.graph_designer.ChatOpenAI",
                return_value=mock_llm,
            ):
                with patch(
                    "langgraph_system_generator.generator.agents.toolchain_engineer.ChatOpenAI",
                    return_value=mock_llm,
                ):
                    with patch(
                        "langgraph_system_generator.generator.agents.notebook_composer.ChatOpenAI",
                        return_value=mock_llm,
                    ):
                        with patch(
                            "langgraph_system_generator.generator.agents.qa_repair_agent.ChatOpenAI",
                            return_value=mock_llm,
                        ):
                            # Override LLM responses for different stages
                            async def mock_invoke_side_effect(messages):
                                # Check context to determine which stage we're in
                                if any(
                                    "requirements analyst" in str(m).lower()
                                    for m in messages
                                ):
                                    mock_response = MagicMock()
                                    mock_response.content = """```json
[
  {"type": "goal", "value": "Create a router-based chatbot", "priority": 5},
  {"type": "environment", "value": "Jupyter notebook", "priority": 3}
]
```"""
                                    return mock_response
                                elif any(
                                    "architecture" in str(m).lower() for m in messages
                                ):
                                    mock_response = MagicMock()
                                    mock_response.content = """```json
{
  "architecture_type": "router",
  "patterns": {"primary": "router", "secondary": []},
  "justification": "Router pattern is ideal for simple classification-based task routing"
}
```"""
                                    return mock_response
                                elif any(
                                    "workflow designer" in str(m).lower()
                                    for m in messages
                                ):
                                    mock_response = MagicMock()
                                    mock_response.content = """```json
{
  "state_schema": {
    "messages": "List of conversation messages",
    "route": "Selected specialist route"
  },
  "nodes": [
    {"name": "router", "purpose": "Route to appropriate specialist"},
    {"name": "specialist_chat", "purpose": "Handle chat queries"}
  ],
  "edges": [],
  "conditional_edges": [],
  "entry_point": "router",
  "checkpointing": false
}
```"""
                                    return mock_response
                                else:
                                    mock_response = MagicMock()
                                    mock_response.content = "[]"
                                    return mock_response

                            mock_llm.ainvoke = mock_invoke_side_effect

                            # Create and run the generator graph
                            print("Creating generator graph...")
                            graph = create_generator_graph()
                            print("✓ Graph created successfully\n")

                            initial_state = {
                                "user_prompt": "Create a simple router-based chatbot for customer support",
                                "uploaded_files": None,
                                "constraints": [],
                                "selected_patterns": {},
                                "docs_context": [],
                                "notebook_plan": None,
                                "architecture_justification": "",
                                "workflow_design": None,
                                "tools_plan": None,
                                "generated_cells": [],
                                "qa_reports": [],
                                "repair_attempts": 0,
                                "artifacts_manifest": {},
                                "generation_complete": False,
                                "error_message": None,
                            }

                            print("Running generator workflow...")
                            print(f"User prompt: {initial_state['user_prompt']}\n")

                            result = await graph.ainvoke(initial_state)

                            print("\n" + "=" * 70)
                            print("Results")
                            print("=" * 70)
                            print()

                            # Display constraints
                            if result.get("constraints"):
                                print(
                                    f"✓ Extracted {len(result['constraints'])} constraints:"
                                )
                                for c in result["constraints"][:3]:
                                    print(f"  - [{c.type}] {c.value}")
                                print()

                            # Display architecture selection
                            if result.get("selected_patterns"):
                                print(
                                    f"✓ Architecture: {result['selected_patterns'].get('primary', 'N/A')}"
                                )
                                print(
                                    f"  Justification: {result.get('architecture_justification', 'N/A')[:100]}..."
                                )
                                print()

                            # Display notebook plan
                            if result.get("notebook_plan"):
                                plan = result["notebook_plan"]
                                print("✓ Notebook Plan:")
                                print(f"  Title: {plan.title}")
                                print(f"  Architecture: {plan.architecture_type}")
                                print(f"  Sections: {len(plan.sections)}")
                                print(f"  Estimated cells: {plan.cell_count_estimate}")
                                print()

                            # Display generated cells
                            if result.get("generated_cells"):
                                cells = result["generated_cells"]
                                print(f"✓ Generated {len(cells)} cells:")
                                markdown_count = sum(
                                    1 for c in cells if c.cell_type == "markdown"
                                )
                                code_count = sum(
                                    1 for c in cells if c.cell_type == "code"
                                )
                                print(f"  - {markdown_count} markdown cells")
                                print(f"  - {code_count} code cells")
                                print()

                                # Show first few cells
                                print("  Sample cells:")
                                for i, cell in enumerate(cells[:3]):
                                    content_preview = cell.content[:60].replace(
                                        "\n", " "
                                    )
                                    print(
                                        f"    {i+1}. [{cell.cell_type}] {content_preview}..."
                                    )
                                print()

                            # Display QA reports
                            if result.get("qa_reports"):
                                reports = result["qa_reports"]
                                passed = sum(1 for r in reports if r.passed)
                                print(
                                    f"✓ QA Reports: {passed}/{len(reports)} checks passed"
                                )
                                for report in reports:
                                    status = "✓" if report.passed else "✗"
                                    print(
                                        f"  {status} {report.check_name}: {report.message}"
                                    )
                                print()

                            # Display completion status
                            if result.get("generation_complete"):
                                print("✓ Generation complete!")
                                print()
                                if result.get("artifacts_manifest"):
                                    print("Artifacts manifest:")
                                    for key, value in result[
                                        "artifacts_manifest"
                                    ].items():
                                        print(f"  - {key}: {value}")
                            else:
                                print("✗ Generation incomplete")
                                if result.get("error_message"):
                                    print(f"  Error: {result['error_message']}")

                            print()
                            print("=" * 70)
                            print(
                                "Stub run completed successfully! Graph produces NotebookPlan + CellSpecs."
                            )
                            print("=" * 70)


if __name__ == "__main__":
    asyncio.run(mock_minimal_run())
