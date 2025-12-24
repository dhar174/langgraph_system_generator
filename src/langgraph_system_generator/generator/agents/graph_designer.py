"""Graph Designer agent for designing the inner workflow structure."""

from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from langgraph_system_generator.generator.state import Constraint
from langgraph_system_generator.generator.utils import extract_json_from_llm_response
from langgraph_system_generator.utils.config import settings


class GraphDesigner:
    """Designs the inner workflow state, nodes, and edges."""

    def __init__(self, model: str | None = None):
        self.llm = ChatOpenAI(model=model or settings.default_model, temperature=0)

    async def design_workflow(
        self, architecture: Dict[str, Any], constraints: List[Constraint]
    ) -> Dict[str, Any]:
        """Create complete graph specification.

        Args:
            architecture: Selected architecture from ArchitectureSelector
            constraints: Project constraints

        Returns:
            Dictionary with state_schema, nodes, edges, conditional_logic, etc.
        """
        architecture_type = architecture.get("architecture_type", "router")
        justification = architecture.get("justification", "")

        constraints_text = "\n".join(
            [f"- [{c.type}] {c.value} (priority: {c.priority})" for c in constraints]
        )

        design_prompt = SystemMessage(
            content="""You are a LangGraph workflow designer.
Design a complete graph specification for the given architecture type.

For the workflow, specify:
1. **state_schema**: TypedDict fields needed for the workflow
2. **nodes**: List of node names and their purposes
3. **edges**: Direct edges between nodes
4. **conditional_edges**: Conditional routing logic with conditions
5. **entry_point**: Starting node
6. **checkpointing**: Whether to enable checkpointing

Return a JSON object with this structure:
{
  "state_schema": {
    "field_name": "description",
    ...
  },
  "nodes": [
    {"name": "node_name", "purpose": "description"},
    ...
  ],
  "edges": [
    {"from": "node_a", "to": "node_b"},
    ...
  ],
  "conditional_edges": [
    {
      "from": "node_name",
      "condition": "condition_description",
      "branches": {"branch_name": "target_node", ...}
    },
    ...
  ],
  "entry_point": "start_node",
  "checkpointing": true
}"""
        )

        user_message = HumanMessage(
            content=f"""Architecture Type: {architecture_type}
Architecture Justification: {justification}

Requirements:
{constraints_text}

Design the workflow graph."""
        )

        response = await self.llm.ainvoke([design_prompt, user_message])

        try:
            result = extract_json_from_llm_response(response.content)
            return result
        except (ValueError, KeyError, TypeError):
            # Fallback to a basic workflow
            return self._fallback_design(architecture_type)

    def _fallback_design(self, architecture_type: str) -> Dict[str, Any]:
        """Provide a fallback design if LLM parsing fails."""
        if architecture_type == "subagents":
            return {
                "state_schema": {
                    "messages": "List of messages",
                    "next": "Next agent to call",
                },
                "nodes": [
                    {"name": "supervisor", "purpose": "Coordinate subagents"},
                    {"name": "agent_1", "purpose": "Specialized agent 1"},
                    {"name": "agent_2", "purpose": "Specialized agent 2"},
                ],
                "edges": [],
                "conditional_edges": [
                    {
                        "from": "supervisor",
                        "condition": "Route to next agent",
                        "branches": {
                            "agent_1": "agent_1",
                            "agent_2": "agent_2",
                            "FINISH": "END",
                        },
                    }
                ],
                "entry_point": "supervisor",
                "checkpointing": True,
            }
        else:
            # Router fallback
            return {
                "state_schema": {
                    "messages": "List of messages",
                    "route": "Selected route",
                },
                "nodes": [
                    {"name": "router", "purpose": "Route to specialist"},
                    {"name": "specialist_1", "purpose": "Specialist function 1"},
                    {"name": "specialist_2", "purpose": "Specialist function 2"},
                ],
                "edges": [],
                "conditional_edges": [
                    {
                        "from": "router",
                        "condition": "Route based on input",
                        "branches": {
                            "specialist_1": "specialist_1",
                            "specialist_2": "specialist_2",
                        },
                    }
                ],
                "entry_point": "router",
                "checkpointing": False,
            }
