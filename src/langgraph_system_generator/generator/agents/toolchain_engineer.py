"""Toolchain Engineer agent for selecting and configuring tools."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from langgraph_system_generator.generator.state import Constraint
from langgraph_system_generator.utils.config import settings


class ToolchainEngineer:
    """Selects and configures tools for the workflow."""

    def __init__(self, model: str | None = None):
        self.llm = ChatOpenAI(model=model or settings.default_model, temperature=0)

    async def plan_tools(
        self, workflow_design: Dict[str, Any], constraints: List[Constraint]
    ) -> List[Dict[str, Any]]:
        """Select tools needed for the workflow.

        Args:
            workflow_design: Workflow design from GraphDesigner
            constraints: Project constraints

        Returns:
            List of tool specifications with name, purpose, and configuration
        """
        nodes = workflow_design.get("nodes", [])
        nodes_text = "\n".join(
            [f"- {node.get('name')}: {node.get('purpose')}" for node in nodes]
        )

        constraints_text = "\n".join(
            [f"- [{c.type}] {c.value}" for c in constraints]
        )

        tools_prompt = SystemMessage(
            content="""You are a toolchain engineer for LangGraph workflows.
Analyze the workflow nodes and determine what tools are needed.

Common tool categories:
- **Search tools**: Web search, documentation search
- **File I/O**: Read/write files, upload/download
- **Data processing**: Parse JSON, CSV, transform data
- **External APIs**: Google Drive, Slack, email
- **Document generation**: PDF, DOCX, reports
- **Code execution**: Python REPL, sandbox
- **Validation**: Schema validation, content moderation

For each tool, specify:
- name: Tool identifier
- category: Tool category
- purpose: Why this tool is needed
- configuration: Any specific configuration

Return a JSON array:
[
  {
    "name": "tool_name",
    "category": "category",
    "purpose": "description",
    "configuration": {}
  },
  ...
]"""
        )

        user_message = HumanMessage(
            content=f"""Workflow Nodes:
{nodes_text}

Requirements:
{constraints_text}

Identify needed tools."""
        )

        response = await self.llm.ainvoke([tools_prompt, user_message])

        try:
            content = response.content
            if isinstance(content, str):
                # Try to extract JSON from markdown code blocks
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()

                tools = json.loads(content)
                return tools
        except (json.JSONDecodeError, KeyError, TypeError):
            # Fallback: no tools needed
            return []

        return []
