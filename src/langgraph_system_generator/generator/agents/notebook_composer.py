"""Notebook Composer agent for generating notebook cell specifications."""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import keyword
import logging
import re
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from langgraph_system_generator.generator.agents._llm import build_chat_llm
from langgraph_system_generator.generator.notebook_composer_registry import (
    NotebookComposerContext,
    NotebookComposerRegistry,
    get_notebook_composer_registry,
)
from langgraph_system_generator.generator.tool_dependency_utils import (
    DependencyAccumulator,
    accumulate_tool_dependencies,
    merge_string_lists,
    normalize_provider_env_var,
    package_import_probe,
)
from langgraph_system_generator.generator.state import (
    CellSpec,
    NotebookCompositionFeedback,
    NotebookCompositionResult,
    NotebookDependencyPlan,
    NotebookFallbackEvent,
    NotebookPlan,
    ToolPlanningFeedback,
)
from langgraph_system_generator.patterns import (
    AutoAgentPattern,
    CritiqueLoopPattern,
    DeepAgentsPattern,
    HybridPattern,
    RouterPattern,
    SubagentsPattern,
)
from langgraph_system_generator.utils.config import ModelConfig, settings


_T = TypeVar("_T")
logger = logging.getLogger(__name__)


class NotebookComposer:
    """Generate notebook cell specifications with pattern-first code synthesis.

    The composer prefers deterministic pattern-library implementations for
    supported architectures. When LLM synthesis is used for tools or custom
    nodes, weak or placeholder output is rejected in favor of runnable,
    deterministic fallback templates so generated notebooks remain useful in
    stub and offline workflows.
    """

    _PATTERN_STATE_FIELDS: dict[str, set[str]] = {
        "router": {
            "messages",
            "route",
            "route_reasoning",
            "route_history",
            "results",
            "final_output",
        },
        "subagents": {
            "messages",
            "next_agent",
            "instructions",
            "iterations",
            "dispatch_log",
            "task_results",
            "final_output",
        },
        "autoagent": {
            "messages",
            "next_agent",
            "instructions",
            "iterations",
            "dispatch_log",
            "task_results",
            "final_output",
        },
        "hybrid": {
            "messages",
            "route",
            "route_reasoning",
            "route_history",
            "next_agent",
            "instructions",
            "iterations",
            "dispatch_log",
            "results",
            "task_results",
            "final_output",
        },
        "deepagents": {
            "messages",
            "task_plan",
            "artifacts",
            "subagent_results",
            "final_output",
            "deepagents_available",
        },
        "critique_loop": {
            "messages",
            "current_draft",
            "critique_feedback",
            "revision_count",
            "quality_score",
            "approved",
            "criteria",
            "draft_history",
            "revision_history",
            "final_output",
            "human_feedback_handler",
            "previous_quality_score",
        },
    }

    def __init__(
        self,
        model: str | None = None,
        model_config: ModelConfig | None = None,
        registry: NotebookComposerRegistry | None = None,
    ):
        self.model_config = model_config or ModelConfig(
            model=model or settings.default_model,
            temperature=0.0,
        )
        self.llm = build_chat_llm(
            model=model,
            model_config=self.model_config,
            chat_openai_class=ChatOpenAI,
        )
        self.registry = (
            registry.clone()
            if registry is not None
            else get_notebook_composer_registry().clone()
        )

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

    def _state_schema_extensions(
        self,
        architecture_type: str,
        state_schema: Dict[str, Any],
    ) -> Dict[str, str]:
        """Return graph-spec fields not already declared by the pattern state."""

        reserved = self._PATTERN_STATE_FIELDS.get(architecture_type, {"messages"})
        extensions: Dict[str, str] = {}
        if not isinstance(state_schema, dict):
            return extensions

        for field_name, description in state_schema.items():
            safe_field = self._safe_identifier(field_name, "field").lower()
            if safe_field in reserved:
                continue
            extensions[str(field_name)] = str(description)
        return extensions

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

    @staticmethod
    def _merge_string_lists(*values: Any) -> List[str]:
        """Merge list-or-scalar string inputs into an ordered unique list."""

        return merge_string_lists(*values)

    @classmethod
    def _normalize_provider_env_var(cls, value: Any) -> str:
        """Normalize arbitrary env-var suggestions into notebook-safe keys."""

        return normalize_provider_env_var(value)

    @staticmethod
    def _package_import_probe(package_name: str) -> str:
        """Return the import probe used to detect whether a package is installed."""

        return package_import_probe(package_name)

    def _resolve_max_iterations(self, workflow_design: Dict[str, Any]) -> int:
        """Resolve the iteration limit embedded into notebook cells."""

        for key in ("max_iterations", "max_revisions"):
            raw_value = workflow_design.get(key)
            if isinstance(raw_value, int) and raw_value > 0:
                return raw_value
        return settings.notebook_composer_default_max_iterations

    @staticmethod
    def _record_fallback(
        feedback: NotebookCompositionFeedback | None,
        *,
        kind: str,
        item_name: str | None,
        reason: str,
        warning: str,
    ) -> None:
        """Record a structured fallback event when feedback tracking is enabled."""

        if feedback is None:
            return
        feedback.fallback_used = True
        if warning not in feedback.warnings:
            feedback.warnings.append(warning)
        feedback.fallback_events.append(
            NotebookFallbackEvent(
                kind=kind,
                item_name=item_name,
                reason=reason,
                warning=warning,
            )
        )

    @staticmethod
    def _merge_feedback(
        target: NotebookCompositionFeedback,
        source: NotebookCompositionFeedback | None,
    ) -> None:
        """Merge per-task feedback into the main composition feedback in order."""

        if source is None:
            return
        if source.fallback_used:
            target.fallback_used = True
        for warning in source.warnings:
            if warning not in target.warnings:
                target.warnings.append(warning)
        target.fallback_events.extend(source.fallback_events)

    def _fallback_banner(self, label: str, reason: str) -> str:
        """Return a visible notebook-facing warning comment for fallback code."""

        safe_label = self._normalize_inline_text(label, "generated component")
        safe_reason = self._normalize_inline_text(
            reason,
            "Primary generation was unavailable or returned placeholder code.",
        )
        return (
            f"# WARNING: Deterministic fallback generated for {safe_label}.\n"
            f"# Reason: {safe_reason}\n\n"
        )

    def _plan_dependencies(
        self,
        tools: List[Dict[str, Any]],
        workflow_design: Dict[str, Any],
    ) -> NotebookDependencyPlan:
        """Build a normalized dependency plan for the generated notebook."""

        plan = NotebookDependencyPlan(
            runtime_notes=[
                "The install cell checks for missing packages before invoking pip.",
                "Generated notebooks assume a Jupyter or Colab-style environment with pip available.",
            ]
        )
        accumulator = DependencyAccumulator(runtime_notes=list(plan.runtime_notes))

        for package_name in ["langgraph", "langchain-core", "langchain-openai"]:
            accumulator.packages.append(package_name)

        architecture_type = self._normalize_inline_text(
            workflow_design.get("architecture_type", ""),
            "",
        ).lower()
        if architecture_type == "deepagents":
            note = (
                "Deep Agents cells are experimental and run in deterministic fallback "
                "mode when the optional `deepagents` SDK is unavailable. Install it "
                "manually with `python -m pip install deepagents` only if your "
                "environment allows package installation and provider credentials are "
                "configured."
            )
            if note not in accumulator.runtime_notes:
                accumulator.runtime_notes.append(note)

        for tool in tools:
            tool_status = self._normalize_inline_text(
                tool.get("status", ""), ""
            ).lower()
            if tool_status == "unsupported":
                continue
            accumulate_tool_dependencies(accumulator, tool)

        if (
            "langchain-openai" in accumulator.packages
            and "OPENAI_API_KEY" not in accumulator.provider_env_vars
        ):
            accumulator.provider_env_vars.append("OPENAI_API_KEY")

        plan.packages = accumulator.packages
        plan.runtime_notes = accumulator.runtime_notes
        plan.conflicts_resolved = accumulator.conflicts_resolved
        plan.provider_env_vars = accumulator.provider_env_vars
        if accumulator.packages:
            plan.install_commands = [
                "python -m pip install -q " + " ".join(accumulator.packages)
            ]
        return plan

    async def _resolve_builder_output(self, builder_output: Any) -> List[CellSpec]:
        """Normalize sync or async section-builder output into a cell list."""

        if inspect.isawaitable(builder_output):
            builder_output = await builder_output
        if builder_output is None:
            return []
        return list(builder_output)

    async def _execute_llm_tasks_in_order(
        self,
        items: List[Any],
        worker: Callable[[Any], Awaitable[_T]],
    ) -> List[_T]:
        """Execute async LLM-backed generation while preserving input order."""

        if not items:
            return []
        if (
            settings.notebook_composer_parallelism_mode == "sequential"
            or len(items) == 1
        ):
            results: List[str] = []
            for item in items:
                results.append(await worker(item))
            return results

        max_concurrency = settings.notebook_composer_max_concurrency
        if max_concurrency <= 0:
            logger.warning(
                "Invalid notebook_composer_max_concurrency=%s; using 1 instead.",
                max_concurrency,
            )
        semaphore = asyncio.Semaphore(max(1, max_concurrency))

        async def run(item: Any) -> _T:
            async with semaphore:
                return await worker(item)

        return await asyncio.gather(*(run(item) for item in items))

    async def _invoke_llm(self, messages: List[Any]) -> Any:
        """Invoke the configured LLM using the async path when available."""

        if hasattr(self.llm, "ainvoke"):
            result = self.llm.ainvoke(messages)
            if inspect.isawaitable(result):
                return await result
            return result
        return await asyncio.to_thread(self.llm.invoke, messages)

    async def compose_notebook(
        self,
        notebook_plan: NotebookPlan,
        workflow_design: Dict[str, Any],
        tools: List[Dict[str, Any]],
        architecture: Dict[str, Any],
        tool_planning_feedback: ToolPlanningFeedback | None = None,
    ) -> NotebookCompositionResult:
        """Generate complete notebook cells plus composition metadata.

        Args:
            notebook_plan: Notebook structure plan
            workflow_design: Workflow graph design
            tools: Tools specification
            architecture: Architecture selection

        Returns:
            Structured notebook composition output
        """
        # Ensure architecture_type is in workflow_design for pattern selection
        if (
            "architecture_type" not in workflow_design
            and "architecture_type" in architecture
        ):
            workflow_design["architecture_type"] = architecture["architecture_type"]

        feedback = NotebookCompositionFeedback(
            resolved_model=self.model_config.model,
            resolved_api_base=self.model_config.api_base,
            resolved_max_iterations=self._resolve_max_iterations(workflow_design),
        )
        dependency_plan = self._plan_dependencies(tools, workflow_design)
        context = NotebookComposerContext(
            notebook_plan=notebook_plan,
            workflow_design=workflow_design,
            tools=tools,
            architecture=architecture,
            dependency_plan=dependency_plan,
            feedback=feedback,
            tool_planning_feedback=(
                tool_planning_feedback or ToolPlanningFeedback(available_tool_ids=[])
            ),
        )

        architecture_type = (
            str(
                workflow_design.get("architecture_type")
                or architecture.get("architecture_type")
                or notebook_plan.architecture_type
                or "router"
            )
            .strip()
            .lower()
        )
        workflow_design["architecture_type"] = architecture_type
        registration = self.registry.resolve(architecture_type)
        cells: List[CellSpec] = []
        for section_name in registration.section_order:
            section_cells: List[CellSpec] = []
            for hook in self.registry.resolve_hooks(
                architecture_type,
                section_name,
                when="pre",
            ):
                section_cells.extend(
                    await self._resolve_builder_output(hook(self, context))
                )

            builder = self.registry.resolve_builder(architecture_type, section_name)
            section_cells.extend(
                await self._resolve_builder_output(builder(self, context))
            )

            for hook in self.registry.resolve_hooks(
                architecture_type,
                section_name,
                when="post",
            ):
                section_cells.extend(
                    await self._resolve_builder_output(hook(self, context))
                )

            if section_cells:
                feedback.sections_built.append(section_name)
                cells.extend(section_cells)

        return NotebookCompositionResult(
            cells=cells,
            dependency_plan=dependency_plan,
            feedback=feedback,
        )

    def _create_tool_planning_warning_cells(
        self,
        tool_planning_feedback: ToolPlanningFeedback | None,
    ) -> List[CellSpec]:
        """Create notebook-visible warnings for degraded tool planning."""

        feedback = tool_planning_feedback
        if feedback is None:
            return []

        has_advisories = any(
            [
                feedback.fallback_used,
                feedback.validation_errors,
                feedback.unresolved_tools,
                feedback.environment_notes,
                feedback.dependency_conflicts,
                feedback.warnings,
            ]
        )
        if not has_advisories:
            return []

        lines = [
            "## Tool Planning Notes",
            "",
            "Review these advisories before relying on the generated tool plan as-is.",
        ]
        if feedback.fallback_used:
            lines.extend(
                [
                    "",
                    f"- Fallback used: {feedback.fallback_reason or 'Heuristic inference was used for tool planning.'}",
                ]
            )
        if feedback.unresolved_tools:
            lines.extend(
                [
                    "",
                    "- Unresolved tools:",
                    *[f"  - {tool_name}" for tool_name in feedback.unresolved_tools],
                ]
            )
        if feedback.validation_errors:
            lines.extend(
                [
                    "",
                    "- Validation issues:",
                    *[f"  - {message}" for message in feedback.validation_errors],
                ]
            )
        if feedback.environment_notes:
            lines.extend(
                [
                    "",
                    "- Environment notes:",
                    *[f"  - {message}" for message in feedback.environment_notes],
                ]
            )
        if feedback.dependency_conflicts:
            lines.extend(
                [
                    "",
                    "- Dependency conflicts:",
                    *[f"  - {message}" for message in feedback.dependency_conflicts],
                ]
            )
        if feedback.warnings:
            lines.extend(
                [
                    "",
                    "- Additional warnings:",
                    *[f"  - {message}" for message in feedback.warnings],
                ]
            )

        return [
            CellSpec(
                cell_type="markdown",
                content="\n".join(lines),
                section="tools",
            )
        ]

    def _create_intro_cells(
        self,
        plan: NotebookPlan,
        justification: str | None,
        graph_exports: Dict[str, Any] | None = None,
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

        cells = [title_cell, overview_cell]

        if isinstance(graph_exports, dict):
            mermaid = str(graph_exports.get("mermaid", "")).strip()
            schema = graph_exports.get("schema", {})
            if mermaid or schema:
                graph_overview_lines = ["## Graph Overview", ""]
                if mermaid:
                    graph_overview_lines.extend(
                        [
                            "```mermaid",
                            mermaid,
                            "```",
                            "",
                        ]
                    )
                if schema:
                    graph_overview_lines.extend(
                        [
                            "### Workflow Schema",
                            "",
                            "```json",
                            json.dumps(schema, indent=2),
                            "```",
                        ]
                    )
                cells.append(
                    CellSpec(
                        cell_type="markdown",
                        content="\n".join(graph_overview_lines),
                        section="intro",
                    )
                )

        return cells

    def _create_install_cells(
        self,
        dependency_plan: NotebookDependencyPlan,
    ) -> List[CellSpec]:
        """Create normalized installation cells from the dependency plan."""

        package_imports = {
            package: self._package_import_probe(package)
            for package in dependency_plan.packages
        }
        install_content = f"""# Install missing notebook dependencies
from importlib.util import find_spec
import subprocess
import sys

PACKAGE_IMPORTS = {json.dumps(package_imports, indent=4)}
REQUIRED_PACKAGES = {json.dumps(dependency_plan.packages, indent=4)}

missing_packages = [
    package
    for package in REQUIRED_PACKAGES
    if find_spec(PACKAGE_IMPORTS[package]) is None
]

if missing_packages:
    print("Installing missing packages:", ", ".join(missing_packages))
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *missing_packages])
else:
    print("All required packages are already available.")"""

        markdown_lines = [
            "## Installation",
            "",
            "Install any missing packages needed by this notebook.",
        ]
        if dependency_plan.runtime_notes:
            markdown_lines.extend(["", "### Environment Notes", ""])
            markdown_lines.extend(f"- {note}" for note in dependency_plan.runtime_notes)
        if dependency_plan.conflicts_resolved:
            markdown_lines.extend(["", "### Dependency Conflict Resolution", ""])
            markdown_lines.extend(
                f"- {detail}" for detail in dependency_plan.conflicts_resolved
            )

        return [
            CellSpec(
                cell_type="markdown",
                content="\n".join(markdown_lines),
                section="setup",
            ),
            CellSpec(cell_type="code", content=install_content, section="setup"),
        ]

    def _create_config_cells(
        self,
        dependency_plan: NotebookDependencyPlan,
        feedback: NotebookCompositionFeedback,
    ) -> List[CellSpec]:
        """Create configuration cells using resolved request-scoped settings."""

        config_lines = [
            "import os",
            "",
            "# Configuration",
            f"MODEL = {json.dumps(self.model_config.model)}",
            f"TEMPERATURE = {self.model_config.temperature}",
            f"MAX_ITERATIONS = {feedback.resolved_max_iterations}",
            (
                f"MAX_TOKENS = {self.model_config.max_tokens}"
                if self.model_config.max_tokens is not None
                else "MAX_TOKENS = None"
            ),
            (
                f"API_BASE = {json.dumps(self.model_config.api_base)}"
                if self.model_config.api_base
                else "API_BASE = None"
            ),
            "",
            "# Credentials",
            "# Prefer environment variables over hardcoded secrets in notebooks.",
        ]
        for env_var in dependency_plan.provider_env_vars:
            safe_env_var = self._normalize_provider_env_var(env_var)
            if not safe_env_var:
                continue
            config_lines.extend(
                [
                    f'{safe_env_var} = os.environ.get("{safe_env_var}", "")',
                    f"if not {safe_env_var}:",
                    f'    print("{safe_env_var} is not set. Configure it in your environment before running live model cells.")',
                    "    # Optional interactive fallback for local notebook sessions:",
                    "    # from getpass import getpass",
                    f'    # os.environ["{safe_env_var}"] = getpass("Enter {safe_env_var}: ")',
                    "",
                ]
            )
        if not dependency_plan.provider_env_vars:
            config_lines.append(
                "# No provider-specific credential environment variables were required for this notebook."
            )
        config_content = "\n".join(config_lines)

        return [
            CellSpec(
                cell_type="markdown",
                content="## Configuration\n\nSet up API keys and configuration:",
                section="config",
            ),
            CellSpec(cell_type="code", content=config_content, section="config"),
        ]

    def _create_state_cells(self, workflow_design: Dict[str, Any]) -> List[CellSpec]:
        """Create state definition cells using pattern library or custom generation."""
        architecture_type = str(
            workflow_design.get("architecture_type", "router")
        ).lower()
        state_schema = self._state_schema_extensions(
            architecture_type,
            workflow_design.get("state_schema", {}),
        )

        # Use pattern library for known architectures
        if architecture_type == "router":
            state_content = RouterPattern.generate_state_code(state_schema)
        elif architecture_type == "subagents":
            state_content = SubagentsPattern.generate_state_code(state_schema)
        elif architecture_type == "hybrid":
            state_content = HybridPattern.generate_state_code(state_schema)
        elif architecture_type == "autoagent":
            state_content = AutoAgentPattern.generate_state_code(state_schema)
        elif architecture_type == "deepagents":
            state_content = DeepAgentsPattern.generate_state_code(state_schema)
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

    async def _create_tool_cells(
        self,
        tools: List[Dict[str, Any]],
        feedback: NotebookCompositionFeedback,
    ) -> List[CellSpec]:
        """Create tool implementation cells with tracked fallback behavior."""
        cells = [
            CellSpec(
                cell_type="markdown",
                content="## Tools\n\nDefine tools used in the workflow:",
                section="tools",
            )
        ]

        async def build_tool_code(
            tool: Dict[str, Any],
        ) -> tuple[str, NotebookCompositionFeedback]:
            tool_feedback = NotebookCompositionFeedback()
            tool_code = await self._generate_tool_implementation(
                tool,
                feedback=tool_feedback,
            )
            return tool_code, tool_feedback

        tool_results = await self._execute_llm_tasks_in_order(
            tools,
            build_tool_code,
        )
        for tool_code, tool_feedback in tool_results:
            self._merge_feedback(feedback, tool_feedback)
            cells.append(CellSpec(cell_type="code", content=tool_code, section="tools"))

        return cells

    async def _generate_tool_implementation(
        self,
        tool: Dict[str, Any],
        *,
        feedback: NotebookCompositionFeedback | None = None,
    ) -> str:
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

            # Use the async LLM path so multiple tool implementations can run concurrently.
            response = await self._invoke_llm([system_prompt, user_prompt])
            generated_code = self._strip_code_fences(response.content)
            if not self._is_meaningful_tool_code(generated_code):
                return self._generate_tool_fallback(
                    tool,
                    reason=(
                        "LLM tool generation returned placeholder or incomplete code."
                    ),
                    feedback=feedback,
                )
            syntax_error = self._python_syntax_error(generated_code)
            if syntax_error is not None:
                return self._generate_tool_fallback(
                    tool,
                    reason=f"LLM tool generation returned invalid Python: {syntax_error}.",
                    feedback=feedback,
                )

            # Add header comment
            header = f"""# Tool: {tool_name}
# Purpose: {tool_purpose}
# Category: {tool_category}

"""
            return header + generated_code

        except (ValueError, KeyError, AttributeError) as exc:
            # Fallback to template with better implementation hints
            return self._generate_tool_fallback(
                tool,
                reason=f"Tool generation could not parse the tool specification: {exc}",
                feedback=feedback,
            )
        except Exception as exc:
            # Unexpected error - still fallback but this is unusual
            return self._generate_tool_fallback(
                tool,
                reason=f"Tool generation failed unexpectedly: {type(exc).__name__}: {exc}",
                feedback=feedback,
            )

    def _generate_tool_fallback(
        self,
        tool: Dict[str, Any],
        *,
        reason: str | None = None,
        feedback: NotebookCompositionFeedback | None = None,
    ) -> str:
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
        warning = f'Deterministic fallback used for tool "{safe_tool_name}".'
        self._record_fallback(
            feedback,
            kind="tool",
            item_name=safe_tool_name,
            reason=reason or "Primary tool generation was unavailable.",
            warning=warning,
        )

        header = f"""{self._fallback_banner(f'tool "{safe_tool_name}"', reason or "Primary tool generation was unavailable.")}
# Tool: {safe_tool_name}
# Purpose: {safe_tool_purpose_comment}
# Category: {safe_tool_category}

"""

        if "search" in tool_category:
            implementation = f'''def {func_name}(query: str) -> str:
    """{safe_tool_purpose or "Search for relevant information using DuckDuckGo."}"""
    from langchain_community.tools import DuckDuckGoSearchRun

    search = DuckDuckGoSearchRun()
    results = search.run(query)
    return results if isinstance(results, str) else str(results)'''
        elif "file" in tool_category or "document" in tool_category:
            implementation = f'''def {func_name}(filename: str, encoding: str = "utf-8") -> str:
    """{safe_tool_purpose or "Read a text document from disk."}"""
    from pathlib import Path

    file_path = Path(filename).expanduser().resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {{file_path}}")

    return file_path.read_text(encoding=encoding)'''
        elif "data" in tool_category or "process" in tool_category:
            implementation = f'''def {func_name}(data: object) -> dict[str, object]:
    """{safe_tool_purpose or "Normalize data into a simple summary structure."}"""
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
                tool_purpose or "Fetch data from an HTTP API endpoint.",
                "Fetch data from an HTTP API endpoint.",
            )
            implementation = f'''def {func_name}(
    url: str,
    params: dict[str, object] = None,
    timeout: int = 10,
) -> dict[str, object]:
    """{api_docstring}"""
    import requests

    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = response.json()
    else:
        payload = response.text
    return {{
        "category": {json.dumps(safe_tool_category)},
        "payload": payload,
    }}'''
        else:
            fallback_docstring = NotebookComposer._normalize_docstring_text(
                tool_purpose or "Capture tool inputs in a structured result.",
                "Capture tool inputs in a structured result.",
            )
            implementation = f'''def {func_name}(*args: object, **kwargs: object) -> dict[str, object]:
    """{fallback_docstring}"""
    return {{
        "tool_name": {json.dumps(safe_tool_name)},
        "purpose": {json.dumps(safe_tool_purpose_comment)},
        "category": {json.dumps(safe_tool_category)},
        "args": list(args),
        "kwargs": kwargs,
    }}'''

        return header + implementation

    async def _create_node_cells(
        self,
        workflow_design: Dict[str, Any],
        feedback: NotebookCompositionFeedback,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> List[CellSpec]:
        """Create node implementation cells with tracked fallback behavior."""
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
        if architecture_type in [
            "router",
            "subagents",
            "hybrid",
            "autoagent",
            "deepagents",
            "critique_loop",
        ]:
            # Use pattern library for architecture-specific nodes
            pattern_cells = self._create_pattern_node_cells(
                nodes, architecture_type, workflow_design, tools=tools
            )
            cells.extend(pattern_cells)
        else:
            # Use LLM for custom node generation
            async def build_node_code(
                node: Dict[str, Any],
            ) -> tuple[str, NotebookCompositionFeedback]:
                node_feedback = NotebookCompositionFeedback()
                node_code = await self._generate_node_implementation(
                    node,
                    workflow_design,
                    feedback=node_feedback,
                )
                return node_code, node_feedback

            node_results = await self._execute_llm_tasks_in_order(
                nodes,
                build_node_code,
            )
            for node_code, node_feedback in node_results:
                self._merge_feedback(feedback, node_feedback)
                cells.append(
                    CellSpec(cell_type="code", content=node_code, section="nodes")
                )

        return cells

    async def _generate_node_implementation(
        self,
        node: Dict[str, Any],
        workflow_design: Dict[str, Any],
        *,
        feedback: NotebookCompositionFeedback | None = None,
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
- The function MUST return a partial state update dictionary (not a full state copy or 'return state')
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

            # Use the async LLM path so custom nodes can run concurrently.
            response = await self._invoke_llm([system_prompt, user_prompt])
            generated_code = self._strip_code_fences(response.content)
            if not self._is_meaningful_node_code(generated_code):
                return self._generate_node_fallback(
                    node,
                    workflow_design,
                    reason=(
                        "LLM node generation returned placeholder or incomplete code."
                    ),
                    feedback=feedback,
                )
            syntax_error = self._python_syntax_error(generated_code)
            if syntax_error is not None:
                return self._generate_node_fallback(
                    node,
                    workflow_design,
                    reason=f"LLM node generation returned invalid Python: {syntax_error}.",
                    feedback=feedback,
                )

            return generated_code

        except (ValueError, KeyError, AttributeError) as exc:
            # Fallback to improved template
            return self._generate_node_fallback(
                node,
                workflow_design,
                reason=f"Node generation could not parse the node specification: {exc}",
                feedback=feedback,
            )
        except Exception as exc:
            # Unexpected error - still fallback
            return self._generate_node_fallback(
                node,
                workflow_design,
                reason=f"Node generation failed unexpectedly: {type(exc).__name__}: {exc}",
                feedback=feedback,
            )

    def _generate_node_fallback(
        self,
        node: Dict[str, Any],
        workflow_design: Dict[str, Any],
        *,
        reason: str | None = None,
        feedback: NotebookCompositionFeedback | None = None,
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
        safe_node_identifier = self._safe_identifier(node_name, "unknown")
        safe_node_name = self._normalize_inline_text(node_name, "unknown node")
        safe_node_purpose = self._normalize_docstring_text(
            node_purpose,
            f"Process workflow state in the {safe_node_name} node.",
        )
        warning = f'Deterministic fallback used for node "{safe_node_name}".'
        self._record_fallback(
            feedback,
            kind="node",
            item_name=safe_node_name,
            reason=reason or "Primary node generation was unavailable.",
            warning=warning,
        )
        routes = [
            candidate.get("name")
            for candidate in workflow_design.get("nodes", [])
            if candidate.get("name") not in {node_name, "router", "supervisor"}
        ]
        default_route = routes[0] if routes else "complete"
        next_worker = routes[0] if routes else "FINISH"

        # Serialize values as safe Python string literals for generated code.
        node_name_literal = json.dumps(safe_node_name)
        node_purpose_literal = json.dumps(
            self._normalize_inline_text(node_purpose, safe_node_name)
        )

        update_lines = [
            "    updates: dict[str, object] = {}",
            '    messages = list(state.get("messages", []))',
            '    last_content = messages[-1].content if messages else ""',
            f'    node_summary = {node_name_literal} + " completed: " + (last_content or {node_purpose_literal})',
            '    updates["messages"] = messages + [HumanMessage(content=node_summary)]',
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
        elif architecture_type in {"subagents", "autoagent"} and node_name in {
            "supervisor",
            "coordinator",
        }:
            update_lines.extend(
                [
                    f'    updates["next_agent"] = "{next_worker}"',
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
                    '    updates["current_draft"] = (',
                    "        f\"{state.get('current_draft', '')}\\n\\n\""
                    '        f"Revision {revision_count}: {feedback}"',
                    "    )",
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
                    f"        results[{node_name_literal}] = node_summary",
                    '        updates["results"] = results',
                    '    if "task_results" in state:',
                    '        task_results = dict(state.get("task_results", {}))',
                    f"        task_results[{node_name_literal}] = node_summary",
                    '        updates["task_results"] = task_results',
                    '    if "final_output" in state:',
                    '        updates["final_output"] = node_summary',
                ]
            )

        update_lines.append("    return updates")

        return f"""{self._fallback_banner(f'node "{safe_node_name}"', reason or "Primary node generation was unavailable.")}
def {safe_node_identifier}_node(state: WorkflowState) -> WorkflowState:
    \"\"\"
    {safe_node_purpose}
    \"\"\"
    from langchain_core.messages import HumanMessage
{chr(10).join(update_lines)}"""

    @staticmethod
    def _split_hybrid_nodes(
        nodes: List[Dict[str, Any]],
    ) -> tuple[List[str], Dict[str, str], List[str], Dict[str, str]]:
        """Split hybrid nodes into direct-specialist and team-worker groups."""

        non_router_nodes = [
            node for node in nodes if node.get("name") not in {"router", "supervisor"}
        ]
        direct_role_names = {"direct", "direct_specialist", "specialist"}
        worker_role_names = {
            "worker",
            "team_worker",
            "subagent",
            "reviewer",
            "planner",
            "critic",
            "qa",
            "quality_assurance",
        }
        worker_name_tokens = {
            "research",
            "review",
            "worker",
            "planner",
            "critic",
            "qa",
        }
        direct_specialists: list[str] = []
        team_workers: list[str] = []
        for node in non_router_nodes:
            node_name = str(node.get("name"))
            role_name = str(node.get("role", "")).strip().lower()
            if role_name in direct_role_names:
                direct_specialists.append(node_name)
            elif role_name in worker_role_names or any(
                token in node_name.lower() for token in worker_name_tokens
            ):
                team_workers.append(node_name)
            else:
                direct_specialists.append(node_name)
        if not direct_specialists:
            if non_router_nodes:
                direct_specialists = [str(non_router_nodes[0].get("name"))]
            else:
                direct_specialists = ["specialist_1"]

        team_workers = [
            worker for worker in team_workers if worker not in direct_specialists
        ]
        if len(team_workers) < 2:
            fallback_workers = [
                name
                for name in ["researcher", "reviewer"]
                if name not in direct_specialists and name not in team_workers
            ]
            team_workers.extend(fallback_workers[: 2 - len(team_workers)])

        direct_descriptions = {
            str(node.get("name")): str(node.get("purpose", ""))
            for node in non_router_nodes
            if str(node.get("name")) in direct_specialists
        }
        worker_descriptions = {
            str(node.get("name")): str(node.get("purpose", ""))
            for node in non_router_nodes
            if str(node.get("name")) in team_workers
        }
        for specialist in direct_specialists:
            direct_descriptions.setdefault(
                specialist,
                f"Handle {specialist} requests directly.",
            )
        for worker in team_workers:
            worker_descriptions.setdefault(
                worker,
                f"{worker} specialist for the worker team.",
            )
        return (
            direct_specialists,
            direct_descriptions,
            team_workers,
            worker_descriptions,
        )

    def _create_pattern_node_cells(
        self,
        nodes: List[Dict[str, Any]],
        architecture_type: str,
        workflow_design: Dict[str, Any],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
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

        model_config = self.model_config

        if architecture_type == "router":
            # Extract routes from nodes
            routes = [
                node.get("name") for node in nodes if node.get("name") != "router"
            ]

            # Generate router node
            router_code = RouterPattern.generate_router_node_code(
                routes, model_config=model_config
            )
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
        elif architecture_type == "hybrid":
            (
                direct_specialists,
                direct_descriptions,
                team_workers,
                worker_descriptions,
            ) = self._split_hybrid_nodes(nodes)

            router_code = HybridPattern.generate_router_node_code(
                direct_specialists,
                model_config=model_config,
            )
            cells.append(
                CellSpec(cell_type="code", content=router_code, section="nodes")
            )

            for specialist in direct_specialists:
                specialist_code = HybridPattern.generate_direct_specialist_code(
                    specialist,
                    direct_descriptions.get(
                        specialist,
                        f"Handle {specialist} requests directly.",
                    ),
                    model_config=model_config,
                )
                cells.append(
                    CellSpec(cell_type="code", content=specialist_code, section="nodes")
                )

            supervisor_code = HybridPattern.generate_supervisor_code(
                team_workers,
                worker_descriptions,
                model_config=model_config,
            )
            cells.append(
                CellSpec(cell_type="code", content=supervisor_code, section="nodes")
            )

            for worker in team_workers:
                worker_code = HybridPattern.generate_worker_code(
                    worker,
                    worker_descriptions.get(
                        worker,
                        f"{worker} specialist for the worker team.",
                    ),
                    model_config=model_config,
                )
                cells.append(
                    CellSpec(cell_type="code", content=worker_code, section="nodes")
                )
        elif architecture_type == "autoagent":
            workers = [
                node.get("name")
                for node in nodes
                if node.get("name") not in {"coordinator", "supervisor"}
            ]
            worker_descriptions = {
                node.get("name"): node.get("purpose", "")
                for node in nodes
                if node.get("name") not in {"coordinator", "supervisor"}
            }

            coordinator_code = AutoAgentPattern.generate_coordinator_code(
                workers, worker_descriptions, model_config=model_config
            )
            cells.append(
                CellSpec(cell_type="code", content=coordinator_code, section="nodes")
            )

            for node in nodes:
                if node.get("name") not in {"coordinator", "supervisor"}:
                    worker_code = AutoAgentPattern.generate_worker_code(
                        node.get("name"),
                        node.get("purpose", f"{node.get('name')} worker"),
                        model_config=model_config,
                    )
                    cells.append(
                        CellSpec(cell_type="code", content=worker_code, section="nodes")
                    )

        elif architecture_type == "deepagents":
            subagents = [
                node.get("name")
                for node in nodes
                if node.get("name") not in {"deep_agent", "deepagents"}
            ]
            tool_identifiers: List[str] = []
            for tool in tools or []:
                tool_status = self._normalize_inline_text(
                    tool.get("status", ""),
                    "ready",
                ).lower()
                if tool_status == "unsupported":
                    continue
                identifier = self._safe_identifier(
                    tool.get("name") or tool.get("tool_id") or "",
                    "tool",
                )
                if identifier not in tool_identifiers:
                    tool_identifiers.append(identifier)
            cells.append(
                CellSpec(
                    cell_type="markdown",
                    content=DeepAgentsPattern.generate_overview_markdown(),
                    section="nodes",
                )
            )
            cells.append(
                CellSpec(
                    cell_type="code",
                    content=DeepAgentsPattern.generate_agent_node_code(
                        subagents,
                        tools=tool_identifiers,
                        model_config=model_config,
                    ),
                    section="nodes",
                )
            )

        elif architecture_type == "critique_loop":
            # Generate critique loop nodes
            generate_code = CritiqueLoopPattern.generate_generation_node_code(
                model_config=model_config
            )
            cells.append(
                CellSpec(cell_type="code", content=generate_code, section="nodes")
            )

            critique_code = CritiqueLoopPattern.generate_critique_node_code(
                model_config=model_config
            )
            cells.append(
                CellSpec(cell_type="code", content=critique_code, section="nodes")
            )

            revise_code = CritiqueLoopPattern.generate_revise_node_code(
                model_config=model_config
            )
            cells.append(
                CellSpec(cell_type="code", content=revise_code, section="nodes")
            )

        return cells

    def _create_graph_cells(
        self,
        workflow_design: Dict[str, Any],
        max_iterations: int,
    ) -> List[CellSpec]:
        """Create graph construction cells using pattern library or custom generation."""
        architecture_type = workflow_design.get("architecture_type", "router")
        if architecture_type in {
            "router",
            "subagents",
            "hybrid",
            "autoagent",
            "deepagents",
            "critique_loop",
        }:
            return self._create_pattern_graph_cells(
                workflow_design,
                architecture_type,
                max_iterations,
            )

        return self._wrap_graph_cells(self._generate_graph_fallback(workflow_design))

    def _create_pattern_graph_cells(
        self,
        workflow_design: Dict[str, Any],
        architecture_type: str,
        max_iterations: int,
    ) -> List[CellSpec]:
        """Create graph construction cells for a known architecture pattern."""

        nodes = workflow_design.get("nodes", [])
        if architecture_type == "router":
            routes = [
                node.get("name") for node in nodes if node.get("name") != "router"
            ]
            graph_code = RouterPattern.generate_graph_code(routes)
        elif architecture_type == "subagents":
            subagents = [
                node.get("name") for node in nodes if node.get("name") != "supervisor"
            ]
            graph_code = SubagentsPattern.generate_graph_code(
                subagents,
                max_iterations=max_iterations,
            )
        elif architecture_type == "hybrid":
            direct_specialists, _, team_workers, _ = self._split_hybrid_nodes(nodes)
            graph_code = HybridPattern.generate_graph_code(
                direct_specialists,
                team_workers,
                max_iterations=max_iterations,
            )
        elif architecture_type == "autoagent":
            workers = [
                node.get("name")
                for node in nodes
                if node.get("name") not in {"coordinator", "supervisor"}
            ]
            graph_code = AutoAgentPattern.generate_graph_code(
                workers,
                max_iterations=max_iterations,
            )
        elif architecture_type == "deepagents":
            graph_code = DeepAgentsPattern.generate_graph_code()
        else:
            graph_code = CritiqueLoopPattern.generate_graph_code(
                max_revisions=max_iterations,
                min_quality_score=0.8,
            )

        return self._wrap_graph_cells(graph_code)

    @staticmethod
    def _wrap_graph_cells(graph_code: str) -> List[CellSpec]:
        """Wrap graph code with the standard notebook graph section cells."""

        return [
            CellSpec(
                cell_type="markdown",
                content="## Build Graph\n\nDefine the LangGraph workflow structure.",
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
        command_routes = workflow_design.get("command_routes", [])

        def _as_string_list(values: Any) -> list[str]:
            if values is None:
                raw_values: list[Any] = []
            elif isinstance(values, str):
                raw_values = [values]
            else:
                try:
                    raw_values = list(values)
                except TypeError:
                    raw_values = [values]
            normalized_values: list[str] = []
            for raw_value in raw_values:
                normalized_value = str(raw_value or "").strip()
                if normalized_value and normalized_value not in normalized_values:
                    normalized_values.append(normalized_value)
            return normalized_values

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
            conditional_code = "\n\n# Add conditional edges\n" + "\n\n".join(
                conditional_blocks
            )

        command_route_code = ""
        if command_routes:
            command_blocks = []
            for index, route in enumerate(command_routes):
                if not isinstance(route, dict):
                    continue
                source = str(route.get("source") or route.get("from") or "").strip()
                if not source:
                    continue
                destinations = _as_string_list(route.get("destinations"))
                update_fields = _as_string_list(route.get("update_fields"))
                path_items: list[str] = []
                route_keys: list[str] = []
                for destination in destinations:
                    if destination in {"END", "__end__"}:
                        route_key = "__end__"
                        path_items.append('"__end__": END')
                    else:
                        route_key = destination
                        path_items.append(
                            f"{json.dumps(route_key)}: {json.dumps(destination)}"
                        )
                    route_keys.append(route_key)
                if not path_items:
                    continue
                path_map_literal = "{" + ", ".join(path_items) + "}"
                default_route = json.dumps(route_keys[0])
                source_slug = self._safe_identifier(source, "node")
                function_name = f"_command_route_from_{source_slug}_{index}"
                path_map_name = f"{function_name}_path_map"
                field_checks = "\n".join(
                    [
                        f"""    value = state.get({json.dumps(field_name)})
    if value in path_map:
        return value"""
                        for field_name in update_fields
                    ]
                )
                if not field_checks:
                    field_checks = f"    return {default_route}"
                else:
                    field_checks = f"{field_checks}\n    return {default_route}"
                command_blocks.append(
                    f"""{path_map_name} = {path_map_literal}

def {function_name}(state: WorkflowState) -> str:
    path_map = {path_map_name}
{field_checks}

workflow.add_conditional_edges({json.dumps(source)}, {function_name}, {path_map_name})"""
                )
            if command_blocks:
                command_route_code = (
                    "\n\n# Add Command route metadata as executable conditional wiring\n"
                    + "\n\n".join(command_blocks)
                )

        return f"""from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import InMemorySaver

# Create graph
workflow = StateGraph(WorkflowState)
memory = InMemorySaver()

# Add nodes
{node_additions if node_additions else "# Add your nodes here"}

# Connect start to entry point
workflow.add_edge(START, "{entry_point}")

# Add edges
{edge_additions if edge_additions else "# Add your edges here"}
{conditional_code}
{command_route_code}

# Compile graph
graph = workflow.compile(checkpointer=memory)"""

    def _create_execution_cells(
        self, workflow_design: Dict[str, Any]
    ) -> List[CellSpec]:
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
    "next_agent": "supervisor",
    "instructions": "",
    "task_results": {},
    "dispatch_log": [],
    "iterations": 0,
}"""
        elif architecture_type == "autoagent":
            initial_state_block = """initial_state: WorkflowState = {
    "messages": [HumanMessage(content="Plan the task, execute it, and critique the output until it is ready.")],
    "next_agent": "coordinator",
    "instructions": "",
    "task_results": {},
    "dispatch_log": [],
    "iterations": 0,
}"""
        elif architecture_type == "hybrid":
            initial_state_block = """initial_state: WorkflowState = {
    "messages": [HumanMessage(content="Route simple work directly, or send deeper requests to the supervisor team.")],
    "route": "",
    "results": {},
    "next_agent": "supervisor",
    "instructions": "",
    "task_results": {},
    "dispatch_log": [],
    "iterations": 0,
    "final_output": "",
}"""
        elif architecture_type == "deepagents":
            initial_state_block = """initial_state: WorkflowState = {
    "messages": [HumanMessage(content="Plan and summarize a small research task.")],
    "task_plan": [],
    "artifacts": {},
    "subagent_results": {},
    "final_output": "",
    "deepagents_available": False,
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

# Execute the workflow with a durable thread and bounded graph recursion.
config = {{"configurable": {{"thread_id": "lnf-demo-thread"}}, "recursion_limit": 25}}
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
    def _python_syntax_error(content: str) -> str | None:
        """Return a compact syntax error for generated Python, if parsing fails."""

        try:
            ast.parse(content)
        except SyntaxError as exc:
            location = f"line {exc.lineno}" if exc.lineno is not None else "unknown line"
            return f"{exc.msg} at {location}"
        return None

    @staticmethod
    def _is_meaningful_tool_code(content: str) -> bool:
        """Return True when generated tool code looks runnable and non-placeholder."""
        normalized = content.strip()
        lowered = normalized.lower()
        # Require at least one function definition.
        if not normalized or "def " not in normalized:
            return False
        # Treat any standalone `pass` statement (including indented variants and
        # trailing comments) as a placeholder.
        if re.search(r"^\s*pass\s*(#.*)?$", normalized, re.MULTILINE):
            return False
        placeholder_markers = ["todo", "implement your", "placeholder"]
        return not any(marker in lowered for marker in placeholder_markers)

    @staticmethod
    def _is_meaningful_node_code(content: str) -> bool:
        """Return True when generated node code contains non-placeholder logic."""
        normalized = content.strip()
        lowered = normalized.lower()
        # Require at least one function definition.
        if not normalized or "def " not in normalized:
            return False
        # Treat any standalone `pass` statement (including indented variants and
        # trailing comments) as a placeholder.
        if re.search(r"^\s*pass\s*(#.*)?$", normalized, re.MULTILINE):
            return False
        placeholder_markers = [
            "todo",
            "implement the actual node logic",
        ]
        if any(marker in lowered for marker in placeholder_markers):
            return False
        return re.search(r"return\s+state\b", lowered) is None
