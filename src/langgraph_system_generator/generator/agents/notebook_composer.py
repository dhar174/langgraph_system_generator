"""Notebook Composer agent for generating notebook cell specifications."""

from __future__ import annotations

import json
import keyword
import re
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from langgraph_system_generator.generator.state import CellSpec, NotebookPlan
from langgraph_system_generator.patterns import (
    CritiqueLoopPattern,
    RouterPattern,
    SubagentsPattern,
)
from langgraph_system_generator.utils.config import ModelConfig, settings


class NotebookComposer:
    """Generate notebook cell specifications with pattern-first code synthesis.

    The composer prefers deterministic pattern-library implementations for
    supported architectures. When LLM synthesis is used for tools or custom
    nodes, weak or placeholder output is rejected in favor of runnable,
    deterministic fallback templates so generated notebooks remain useful in
    stub and offline workflows.
    """

    def __init__(self, model: str | None = None):
        self.llm = ChatOpenAI(model=model or settings.default_model, temperature=0)

    @staticmethod
    def _safe_identifier(value: Any, fallback: str) -> str:
        """Return a strict Python identifier derived from arbitrary input."""

        text = str(value or "").strip()
        slug = re.sub(r"[^a-zA-Z0-9]", "_", text)
        slug = re.sub(r"_+", "_", slug).strip("_")
        if not slug:
            slug = fallback
        if slug and slug[0].isdigit():
            slug = f"_{slug}"
        # Ensure the result is a valid, non-keyword Python identifier
        if not slug or not slug.isidentifier() or keyword.iskeyword(slug):
            slug = f"_{slug}" if slug else "_identifier"
            if not slug.isidentifier() or keyword.iskeyword(slug):
                slug = "_identifier"
        return slug

    @staticmethod
    def _normalize_docstring_text(text: Any) -> str:
        """Normalize arbitrary text for safe inclusion in a Python docstring."""

        # Coerce to string and collapse excessive whitespace/newlines
        normalized = re.sub(r"\s+", " ", str(text or "")).strip()
        # Avoid accidentally closing triple-quoted strings
        normalized = normalized.replace('"""', '\\"""')
        return normalized

    @staticmethod
    def _normalize_inline_text(value: Any, fallback: str) -> str:
        """Normalize arbitrary text for safe single-line comments/messages."""

        text = str(value or fallback).replace("\r\n", "\n").replace("\r", "\n")
        text = " ".join(part.strip() for part in text.split("\n") if part.strip())
        return text or fallback

    @staticmethod
    def _normalize_docstring_text(value: Any, fallback: str) -> str:
        """Normalize arbitrary text for safe inclusion inside generated docstrings."""

        text = str(value or fallback).replace("\r\n", "\n").replace("\r", "\n")
        text = text.replace('"""', '\\"\\"\\"')
        lines = [line.rstrip() for line in text.split("\n")]
        normalized = "\n    ".join(lines).strip()
        return normalized or fallback

    async def compose_notebook(
        self,
        notebook_plan: NotebookPlan,
        workflow_design: Dict[str, Any],
        tools: List[Dict[str, Any]],
        architecture: Dict[str, Any],
    ) -> List[CellSpec]:
        """Generate complete list of notebook cells.

        Args:
            notebook_plan: Notebook structure plan
            workflow_design: Workflow graph design
            tools: Tools specification
            architecture: Architecture selection

        Returns:
            List of CellSpec objects defining all notebook cells
        """
        # Ensure architecture_type is in workflow_design for pattern selection
        if (
            "architecture_type" not in workflow_design
            and "architecture_type" in architecture
        ):
            workflow_design["architecture_type"] = architecture["architecture_type"]

        cells = []

        # Title and intro cells
        cells.extend(
            self._create_intro_cells(notebook_plan, architecture.get("justification"))
        )

        # Installation cells
        cells.extend(self._create_install_cells(tools))

        # Configuration cells
        cells.extend(self._create_config_cells())

        # State definition
        cells.extend(self._create_state_cells(workflow_design))

        # Tool implementations
        if tools:
            cells.extend(self._create_tool_cells(tools))

        # Node implementations
        cells.extend(self._create_node_cells(workflow_design))

        # Graph construction
        cells.extend(self._create_graph_cells(workflow_design))

        # Execution cells
        cells.extend(self._create_execution_cells(workflow_design))

        return cells

    def _create_intro_cells(
        self, plan: NotebookPlan, justification: str | None
    ) -> List[CellSpec]:
        """Create title and introduction cells."""
        title_cell = CellSpec(
            cell_type="markdown",
            content=f"""# {plan.title}

Generated by LangGraph Notebook Foundry

**Architecture**: {plan.architecture_type}  
**Patterns Used**: {', '.join(plan.patterns_used)}
""",
            section="intro",
        )

        overview_cell = CellSpec(
            cell_type="markdown",
            content=f"""## Overview

This notebook implements a LangGraph workflow using the **{plan.architecture_type}** pattern.

### Architecture Justification

{justification or 'Architecture selected based on requirements analysis.'}

### Sections

{chr(10).join([f"1. {section}" for section in plan.sections])}
""",
            section="intro",
        )

        return [title_cell, overview_cell]

    def _create_install_cells(self, tools: List[Dict[str, Any]]) -> List[CellSpec]:
        """Create installation cells."""
        packages = [
            "langgraph",
            "langchain-core",
            "langchain-community",
            "langchain-openai",
        ]

        # Add tool-specific packages
        for tool in tools:
            category = tool.get("category", "")
            if "search" in category.lower():
                packages.append("langchain-community")
            elif "file" in category.lower() or "document" in category.lower():
                packages.append("pypdf")

        install_content = f"""# Install required packages
!pip install -q {' '.join(packages)}"""

        return [
            CellSpec(
                cell_type="markdown",
                content="## Installation\n\nInstall the required packages:",
                section="setup",
            ),
            CellSpec(cell_type="code", content=install_content, section="setup"),
        ]

    def _create_config_cells(self) -> List[CellSpec]:
        """Create configuration cells."""
        config_content = """import os
from getpass import getpass

# Configuration
MODEL = "gpt-5-mini"
MAX_ITERATIONS = 10

# API Keys
if not os.environ.get("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = getpass("Enter OpenAI API Key: ")

if not os.environ.get("ANTHROPIC_API_KEY"):
    os.environ["ANTHROPIC_API_KEY"] = getpass("Enter Anthropic API Key (optional): ")"""

        return [
            CellSpec(
                cell_type="markdown",
                content="## Configuration\n\nSet up API keys and configuration:",
                section="setup",
            ),
            CellSpec(cell_type="code", content=config_content, section="setup"),
        ]

    def _create_state_cells(self, workflow_design: Dict[str, Any]) -> List[CellSpec]:
        """Create state definition cells using pattern library or custom generation."""
        architecture_type = workflow_design.get("architecture_type", "router")
        state_schema = workflow_design.get("state_schema", {})

        # Use pattern library for known architectures
        if architecture_type == "router":
            state_content = RouterPattern.generate_state_code(state_schema)
        elif architecture_type == "subagents":
            state_content = SubagentsPattern.generate_state_code(state_schema)
        elif architecture_type == "critique_loop":
            state_content = CritiqueLoopPattern.generate_state_code(state_schema)
        else:
            # Fallback to custom state generation
            fields = "\n    ".join(
                [f"{name}: str  # {desc}" for name, desc in state_schema.items()]
            )
            state_content = f"""from langgraph.graph import MessagesState


class WorkflowState(MessagesState):
    \"\"\"Custom workflow state schema.
    
    Inherits from MessagesState to maintain conversation history.
    \"\"\"
    {fields if fields else "pass"}"""

        return [
            CellSpec(
                cell_type="markdown",
                content="## State Schema\n\nDefine the workflow state:",
                section="state",
            ),
            CellSpec(cell_type="code", content=state_content, section="state"),
        ]

    def _create_tool_cells(self, tools: List[Dict[str, Any]]) -> List[CellSpec]:
        """Create tool implementation cells with LLM-generated code."""
        cells = [
            CellSpec(
                cell_type="markdown",
                content="## Tools\n\nDefine tools used in the workflow:",
                section="tools",
            )
        ]

        for tool in tools:
            # Try to generate real implementation with LLM
            tool_code = self._generate_tool_implementation(tool)

            cells.append(CellSpec(cell_type="code", content=tool_code, section="tools"))

        return cells

    def _generate_tool_implementation(self, tool: Dict[str, Any]) -> str:
        """Generate tool implementation using LLM.

        Args:
            tool: Tool specification with name, purpose, category, etc.

        Returns:
            Python code string implementing the tool
        """
        tool_name = tool.get("name", "unknown_tool")
        tool_purpose = tool.get("purpose", "")
        tool_category = tool.get("category", "")
        tool_config = tool.get("configuration", {})

        try:
            # Build prompt for LLM
            system_prompt = SystemMessage(
                content="""You are an expert Python developer specializing in LangGraph workflows and tool implementations.

Generate a complete, production-ready Python function implementation for the specified tool.

Requirements:
- The function should be fully implemented (no 'pass' statements)
- Include proper error handling
- Add helpful docstrings
- Import necessary libraries at the function level
- Use best practices for the tool's category
- Make it immediately runnable

Common tool categories and approaches:
- **search**: Use DuckDuckGoSearchRun or similar
- **file I/O**: Use pathlib, open(), json, csv libraries
- **data processing**: Use pandas, json, or built-in Python
- **API calls**: Use requests or httpx
- **validation**: Use pydantic or custom validation logic

Return ONLY the Python function code, nothing else."""
            )

            user_prompt = HumanMessage(
                content=f"""Tool Name: {tool_name}
Purpose: {tool_purpose}
Category: {tool_category}
Configuration: {tool_config}

Generate the complete Python function implementation."""
            )

            # Get LLM response (synchronous)
            response = self.llm.invoke([system_prompt, user_prompt])
            generated_code = self._strip_code_fences(response.content)
            if not self._is_meaningful_tool_code(generated_code):
                return self._generate_tool_fallback(tool)

            # Add header comment
            header = f"""# Tool: {tool_name}
# Purpose: {tool_purpose}
# Category: {tool_category}

"""
            return header + generated_code

        except (ValueError, KeyError, AttributeError):
            # Fallback to template with better implementation hints
            return self._generate_tool_fallback(tool)
        except Exception:
            # Unexpected error - still fallback but this is unusual
            return self._generate_tool_fallback(tool)

    def _generate_tool_fallback(self, tool: Dict[str, Any]) -> str:
        """Generate a deterministic fallback tool implementation.

        Args:
            tool: Tool specification

        Returns:
            Python code with implementation hints
        """
        tool_name = tool.get("name", "unknown_tool")
        tool_purpose = tool.get("purpose", "")
        tool_category = tool.get("category", "").lower()
        safe_tool_name = self._normalize_inline_text(tool_name, "unknown_tool")
        safe_tool_purpose = self._normalize_docstring_text(
            tool_purpose, "Fallback tool implementation."
        )
        safe_tool_purpose_comment = self._normalize_inline_text(
            tool_purpose, "Fallback tool implementation."
        )
        safe_tool_category = self._normalize_inline_text(tool_category, "general")
        func_name = self._safe_identifier(tool_name, "unknown_tool")

        header = f"""# Tool: {tool_name}
# Purpose: {tool_purpose}
# Category: {tool_category}

"""

        if "search" in tool_category:
            implementation = f'''def {func_name}(query: str) -> str:
    """{tool_purpose or "Search for relevant information using DuckDuckGo."}"""
    from langchain_community.tools import DuckDuckGoSearchRun

    search = DuckDuckGoSearchRun()
    results = search.run(query)
    return results if isinstance(results, str) else str(results)'''
        elif "file" in tool_category or "document" in tool_category:
            implementation = f'''def {func_name}(filename: str, encoding: str = "utf-8") -> str:
    """{tool_purpose or "Read a text document from disk."}"""
    from pathlib import Path

    file_path = Path(filename).expanduser().resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {{file_path}}")

    return file_path.read_text(encoding=encoding)'''
        elif "data" in tool_category or "process" in tool_category:
            implementation = f'''def {func_name}(data: object) -> dict[str, object]:
    """{tool_purpose or "Normalize data into a simple summary structure."}"""
    if isinstance(data, dict):
        return {{
            "record_count": len(data),
            "keys": sorted(data.keys()),
            "preview": data,
        }}
    if isinstance(data, list):
        preview = data[:3]
        return {{
            "record_count": len(data),
            "item_types": sorted({{type(item).__name__ for item in data}}),
            "preview": preview,
        }}
    return {{
        "record_count": 1,
        "item_types": [type(data).__name__],
        "preview": data,
    }}'''
        elif "api" in safe_tool_category:
            api_docstring = NotebookComposer._normalize_docstring_text(
                tool_purpose or "Fetch data from an HTTP API endpoint."
            )
            implementation = f'''def {func_name}(url: str, params: dict[str, object] | None = None, timeout: int = 10) -> object:
    """{api_docstring}"""
    import requests

    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        return response.json()
    return response.text'''
        else:
            fallback_docstring = NotebookComposer._normalize_docstring_text(
                tool_purpose or "Capture tool inputs in a structured result."
            )
            implementation = f'''def {func_name}(*args: object, **kwargs: object) -> dict[str, object]:
    """{fallback_docstring}"""
    return {{
        "tool_name": {json.dumps(safe_tool_name)},
        "purpose": {json.dumps(tool_purpose or "")},
        "args": list(args),
        "kwargs": kwargs,
    }}'''

        return header + implementation

    def _create_node_cells(self, workflow_design: Dict[str, Any]) -> List[CellSpec]:
        """Create node implementation cells with LLM-generated or pattern-based code."""
        cells = [
            CellSpec(
                cell_type="markdown",
                content="## Nodes\n\nImplement workflow nodes:",
                section="nodes",
            )
        ]

        nodes = workflow_design.get("nodes", [])
        architecture_type = workflow_design.get("architecture_type", "router")

        # Check if we should use pattern-based generation
        if architecture_type in ["router", "subagents", "critique_loop"]:
            # Use pattern library for architecture-specific nodes
            pattern_cells = self._generate_nodes_from_pattern(
                nodes, architecture_type, workflow_design
            )
            cells.extend(pattern_cells)
        else:
            # Use LLM for custom node generation
            for node in nodes:
                node_code = self._generate_node_implementation(node, workflow_design)
                cells.append(
                    CellSpec(cell_type="code", content=node_code, section="nodes")
                )

        return cells

    def _generate_node_implementation(
        self, node: Dict[str, Any], workflow_design: Dict[str, Any]
    ) -> str:
        """Generate node implementation using LLM.

        Args:
            node: Node specification with name, purpose, etc.
            workflow_design: Complete workflow design for context

        Returns:
            Python code string implementing the node
        """
        node_name = node.get("name", "unknown")
        node_purpose = node.get("purpose", "")
        safe_node_identifier = self._safe_identifier(node_name, "unknown")
        state_schema = workflow_design.get("state_schema", {})
        function_signature = (
            f"def {safe_node_identifier}_node(state: WorkflowState) -> WorkflowState"
        )

        try:
            # Build prompt for LLM
            system_prompt = SystemMessage(
                content=f"""You are an expert Python developer specializing in LangGraph node implementations.

Generate a complete, production-ready Python function for a LangGraph node.

Requirements:
- Function signature: {function_signature}
- The function MUST return an updated state dictionary (not just 'return state')
- Include proper LLM initialization and invocation if needed
- Use MessagesState pattern with proper message handling
- Import necessary libraries at the function level
- Add comprehensive docstring
- Implement actual logic based on the purpose (no 'pass' statements)
- Handle state fields appropriately

Return ONLY the Python function code, nothing else."""
            )

            state_info = "\n".join(
                [f"- {field}: {desc}" for field, desc in state_schema.items()]
            )

            user_prompt = HumanMessage(
                content=f"""Node Name: {node_name}
Purpose: {node_purpose}

State Schema:
{state_info}

Generate the complete Python function implementation."""
            )

            # Get LLM response
            response = self.llm.invoke([system_prompt, user_prompt])
            generated_code = self._strip_code_fences(response.content)
            if not self._is_meaningful_node_code(generated_code):
                return self._generate_node_fallback(node, workflow_design)

            return generated_code

        except (ValueError, KeyError, AttributeError):
            # Fallback to improved template
            return self._generate_node_fallback(node, workflow_design)
        except Exception:
            # Unexpected error - still fallback
            return self._generate_node_fallback(node, workflow_design)

    def _generate_node_fallback(
        self, node: Dict[str, Any], workflow_design: Dict[str, Any]
    ) -> str:
        """Generate deterministic fallback node implementation.

        Args:
            node: Node specification
            workflow_design: Workflow design for context

        Returns:
            Python code with implementation hints
        """
        node_name = node.get("name", "unknown")
        node_purpose = node.get("purpose", "")
        architecture_type = workflow_design.get("architecture_type", "")
        routes = [
            candidate.get("name")
            for candidate in workflow_design.get("nodes", [])
            if candidate.get("name") not in {node_name, "router", "supervisor"}
        ]
        default_route = routes[0] if routes else "complete"
        supervisor_target = default_route if routes else "FINISH"

        update_lines = [
            "    updates: dict[str, object] = dict(state)",
            "    messages = list(state.get(\"messages\", []))",
            "    last_content = messages[-1].content if messages else \"\"",
            f'    node_summary = f"{node_name} completed: {{last_content or {node_purpose!r}}}"',
            "    updates[\"messages\"] = messages + [HumanMessage(content=node_summary)]",
        ]

        if architecture_type == "router" and node_name == "router":
            update_lines.extend(
                [
                    f'    updates["route"] = "{default_route}"',
                    '    results = dict(state.get("results", {}))',
                    '    results["routing_decision"] = updates["route"]',
                    '    updates["results"] = results',
                ]
            )
        elif architecture_type == "subagents" and node_name == "supervisor":
            update_lines.extend(
                [
                    f'    updates["next"] = "{supervisor_target}"',
                    f'    updates["instructions"] = "Continue with the delegated task for {default_route}."',
                ]
            )
        elif architecture_type == "critique_loop" and "critique" in node_name:
            update_lines.extend(
                [
                    '    updates["critique_feedback"] = "The draft is coherent but should add more detail and evidence."',
                    '    updates["quality_score"] = 0.75',
                    '    updates["approved"] = False',
                ]
            )
        elif architecture_type == "critique_loop" and "revise" in node_name:
            update_lines.extend(
                [
                    '    revision_count = int(state.get("revision_count", 0)) + 1',
                    '    updates["revision_count"] = revision_count',
                    '    feedback = state.get("critique_feedback", "")',
                    '    updates["current_draft"] = f"{state.get(\'current_draft\', \'\')}\\n\\nRevision {revision_count}: {feedback}"',
                ]
            )
        elif architecture_type == "critique_loop":
            update_lines.extend(
                [
                    '    updates["current_draft"] = last_content or "Generated initial draft based on the task request."',
                    '    updates["revision_count"] = int(state.get("revision_count", 0))',
                    '    updates["approved"] = bool(state.get("approved", False))',
                ]
            )
        else:
            update_lines.extend(
                [
                    '    if "results" in state:',
                    '        results = dict(state.get("results", {}))',
                    f'        results["{node_name}"] = node_summary',
                    '        updates["results"] = results',
                    '    if "task_results" in state:',
                    '        task_results = dict(state.get("task_results", {}))',
                    f'        task_results["{node_name}"] = node_summary',
                    '        updates["task_results"] = task_results',
                    '    if "final_output" in state:',
                    '        updates["final_output"] = node_summary',
                ]
            )

        update_lines.append("    return updates")

        safe_content = repr(
            f"{node_name} completed a fallback step for: {node_purpose or node_name}"
        )

        return f"""def {safe_node_identifier}_node(state: WorkflowState) -> WorkflowState:
    \"\"\"
    {node_purpose or f"Process workflow state in the {node_name} node."}
    \"\"\"
    from langchain_core.messages import HumanMessage
{chr(10).join(update_lines)}"""

    def _generate_nodes_from_pattern(
        self,
        nodes: List[Dict[str, Any]],
        architecture_type: str,
        workflow_design: Dict[str, Any],
    ) -> List[CellSpec]:
        """Generate nodes using pattern library templates.

        Args:
            nodes: List of node specifications
            architecture_type: Architecture pattern type
            workflow_design: Complete workflow design

        Returns:
            List of CellSpec objects with pattern-based node implementations
        """
        cells = []
        
        # Create model config from settings
        model_config = ModelConfig(model=settings.default_model)

        if architecture_type == "router":
            # Extract routes from nodes
            routes = [
                node.get("name") for node in nodes if node.get("name") != "router"
            ]

            # Generate router node
            router_code = RouterPattern.generate_router_node_code(routes, model_config=model_config)
            cells.append(
                CellSpec(cell_type="code", content=router_code, section="nodes")
            )

            # Generate route handler nodes
            for node in nodes:
                if node.get("name") != "router":
                    route_code = RouterPattern.generate_route_node_code(
                        node.get("name"),
                        node.get("purpose", f"Handle {node.get('name')} requests"),
                        model_config=model_config,
                    )
                    cells.append(
                        CellSpec(cell_type="code", content=route_code, section="nodes")
                    )

        elif architecture_type == "subagents":
            # Extract subagents (excluding supervisor)
            subagents = [
                node.get("name") for node in nodes if node.get("name") != "supervisor"
            ]
            subagent_descriptions = {
                node.get("name"): node.get("purpose", "")
                for node in nodes
                if node.get("name") != "supervisor"
            }

            # Generate supervisor node
            supervisor_code = SubagentsPattern.generate_supervisor_code(
                subagents, subagent_descriptions, model_config=model_config
            )
            cells.append(
                CellSpec(cell_type="code", content=supervisor_code, section="nodes")
            )

            # Generate subagent nodes
            for node in nodes:
                if node.get("name") != "supervisor":
                    subagent_code = SubagentsPattern.generate_subagent_code(
                        node.get("name"),
                        node.get("purpose", f"{node.get('name')} specialist"),
                        model_config=model_config,
                    )
                    cells.append(
                        CellSpec(
                            cell_type="code", content=subagent_code, section="nodes"
                        )
                    )

        elif architecture_type == "critique_loop":
            # Generate critique loop nodes
            generate_code = CritiqueLoopPattern.generate_generation_node_code(model_config=model_config)
            cells.append(
                CellSpec(cell_type="code", content=generate_code, section="nodes")
            )

            critique_code = CritiqueLoopPattern.generate_critique_node_code(model_config=model_config)
            cells.append(
                CellSpec(cell_type="code", content=critique_code, section="nodes")
            )

            revise_code = CritiqueLoopPattern.generate_revise_node_code(model_config=model_config)
            cells.append(
                CellSpec(cell_type="code", content=revise_code, section="nodes")
            )

        return cells

    def _create_graph_cells(self, workflow_design: Dict[str, Any]) -> List[CellSpec]:
        """Create graph construction cells using pattern library or custom generation."""
        architecture_type = workflow_design.get("architecture_type", "router")
        nodes = workflow_design.get("nodes", [])

        # Use pattern library for known architectures
        if architecture_type == "router":
            routes = [
                node.get("name") for node in nodes if node.get("name") != "router"
            ]
            graph_code = RouterPattern.generate_graph_code(routes)
        elif architecture_type == "subagents":
            subagents = [
                node.get("name") for node in nodes if node.get("name") != "supervisor"
            ]
            graph_code = SubagentsPattern.generate_graph_code(subagents)
        elif architecture_type == "critique_loop":
            graph_code = CritiqueLoopPattern.generate_graph_code(
                max_revisions=3, min_quality_score=0.8
            )
        else:
            # Fallback to enhanced template-based generation
            graph_code = self._generate_graph_fallback(workflow_design)

        return [
            CellSpec(
                cell_type="markdown",
                content="## Graph Construction\n\nBuild the LangGraph workflow:",
                section="graph",
            ),
            CellSpec(cell_type="code", content=graph_code, section="graph"),
        ]

    def _generate_graph_fallback(self, workflow_design: Dict[str, Any]) -> str:
        """Generate fallback graph construction code.

        Args:
            workflow_design: Complete workflow design

        Returns:
            Python code for graph construction
        """
        entry_point = workflow_design.get("entry_point", "start")
        nodes = workflow_design.get("nodes", [])
        edges = workflow_design.get("edges", [])
        conditional_edges = workflow_design.get("conditional_edges", [])

        # Generate node additions
        node_bindings = [
            (
                json.dumps(str(node.get("name", "unknown"))),
                self._safe_identifier(node.get("name", "unknown"), "unknown"),
            )
            for node in nodes
        ]
        node_additions = "\n".join(
            [
                f"workflow.add_node({display_name}, {function_name}_node)"
                for display_name, function_name in node_bindings
            ]
        )

        # Generate regular edges
        edge_additions = "\n".join(
            [
                f'workflow.add_edge("{edge.get("from")}", "{edge.get("to")}")'
                for edge in edges
            ]
        )

        # Generate conditional edges if present
        conditional_code = ""
        if conditional_edges:
            conditional_blocks = []
            for ce in conditional_edges:
                source = ce.get("from", "node")
                # Produce a valid Python identifier: replace every non-alphanumeric
                # character with '_' and ensure the result doesn't start with a digit.
                source_slug = re.sub(r"[^a-zA-Z0-9]", "_", source)
                if source_slug and source_slug[0].isdigit():
                    source_slug = "_" + source_slug
                source_slug = source_slug or "node"
                function_name = f"_route_from_{source_slug}"
                # Serialize source safely for use inside a string literal in the
                # generated code (handles quotes, backslashes, newlines, etc.).
                safe_source = json.dumps(source)
                conditional_blocks.append(
                    f"""def {function_name}(state: WorkflowState) -> str:
    return "__end__"

workflow.add_conditional_edges({safe_source}, {function_name}, {{"__end__": END}})"""
                )
            conditional_code = "\n\n# Add conditional edges\n" + "\n\n".join(conditional_blocks)

        return f"""from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver

# Create graph
workflow = StateGraph(WorkflowState)
memory = MemorySaver()

# Add nodes
{node_additions if node_additions else "# Add your nodes here"}

# Connect start to entry point
workflow.add_edge(START, "{entry_point}")

# Add edges
{edge_additions if edge_additions else "# Add your edges here"}
{conditional_code}

# Compile graph
graph = workflow.compile(checkpointer=memory)"""

    def _create_execution_cells(self, workflow_design: Dict[str, Any]) -> List[CellSpec]:
        """Create execution cells aligned with the generated workflow state."""
        architecture_type = workflow_design.get("architecture_type", "router")

        if architecture_type == "router":
            initial_state_block = """initial_state: WorkflowState = {
    "messages": [HumanMessage(content="Route this request to the best specialist and produce a concise answer.")],
    "route": "",
    "results": {},
    "final_output": "",
}"""
        elif architecture_type == "subagents":
            initial_state_block = """initial_state: WorkflowState = {
    "messages": [HumanMessage(content="Research the topic, draft a response, and review it before finishing.")],
    "next": "supervisor",
    "instructions": "",
    "task_results": {},
}"""
        elif architecture_type == "critique_loop":
            initial_state_block = """initial_state: WorkflowState = {
    "messages": [HumanMessage(content="Draft a polished explanation of how this workflow should solve the task.")],
    "current_draft": "",
    "critique_feedback": "",
    "revision_count": 0,
    "quality_score": 0.0,
    "approved": False,
    "criteria": [
        "Accuracy and correctness",
        "Clarity and readability",
        "Completeness",
    ],
}"""
        else:
            initial_state_block = """initial_state: WorkflowState = {
    "messages": [HumanMessage(content="Run the workflow with this sample request.")],
    # Add additional workflow state fields here if your custom schema requires them.
}"""

        exec_content = f"""from langchain_core.messages import HumanMessage

# Execute the workflow with a durable thread
config = {{"configurable": {{"thread_id": "lnf-demo-thread"}}}}
{initial_state_block}

print("Streaming state updates:")
for step in graph.stream(initial_state, config, stream_mode="updates"):
    print(step)

final_state = graph.invoke(initial_state, config)
print(final_state)"""

        return [
            CellSpec(
                cell_type="markdown",
                content="## Execution\n\nRun the workflow:",
                section="execution",
            ),
            CellSpec(cell_type="code", content=exec_content, section="execution"),
        ]

    @staticmethod
    def _strip_code_fences(content: str) -> str:
        """Normalize LLM-generated code content by removing markdown fences."""
        normalized = content.strip()
        if normalized.startswith("```python"):
            normalized = normalized[9:]
        if normalized.startswith("```"):
            normalized = normalized[3:]
        if normalized.endswith("```"):
            normalized = normalized[:-3]
        return normalized.strip()

    @staticmethod
    def _is_meaningful_tool_code(content: str) -> bool:
        """Return True when generated tool code looks runnable and non-placeholder."""
        lowered = content.lower()
        if not content or "def " not in content:
            return False
        placeholder_markers = ["\npass", "todo", "implement your", "placeholder"]
        return not any(marker in lowered for marker in placeholder_markers)

    @staticmethod
    def _is_meaningful_node_code(content: str) -> bool:
        """Return True when generated node code contains non-placeholder logic."""
        lowered = content.lower()
        if not content or "def " not in content:
            return False
        placeholder_markers = [
            "\npass",
            "todo",
            "implement the actual node logic",
            "return state",
        ]
        return not any(marker in lowered for marker in placeholder_markers)
