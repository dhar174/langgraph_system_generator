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
from langgraph_system_generator.generator.graph_design_registry import (
    normalize_graph_schema_payload,
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
from langgraph_system_generator.patterns.utils import render_additional_fields
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
    _PATTERN_TERMINAL_NAMES = {"finish", "__end__"}
    _PATTERN_TERMINAL_ROLES = {
        "synthesizer",
        "terminal",
        "finalizer",
        "finish",
        "final",
    }
    _CHATBOT_STATE_FIELDS: dict[str, str] = {
        "draft_response": "Draft chatbot response awaiting verification.",
        "safety_passed": "Whether safety and realism checks passed.",
        "needs_revision": "Whether the draft requires a bounded revision.",
        "historical_risk_notes": "Historical anachronism or realism findings.",
        "realism_notes": "Persona realism notes from verifier nodes.",
        "revision_instructions": "Concrete instructions for the reviser node.",
        "revision_count": "Number of revision attempts for the current turn.",
        "revision_history": "Attempt-by-attempt revision notes.",
        "verification_passed": "Whether verifier checks accepted the draft.",
        "final_response": "Accepted final chatbot response.",
        "turn_count": "Number of completed chat turns for the thread.",
        "memory_summary": "Short running conversation memory summary.",
        "conversation_memory": "Thread-scoped multi-turn conversation memory.",
        "persona_profile": "Selected persona profile for the active character.",
        "persona": "Selected 18th-century commoner persona.",
        "persona_choice": "Selected persona choice for the active character.",
        "selected_gender": "Selected male or female character gender.",
        "gender_pending": "Whether character selection is still pending.",
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

    @classmethod
    def _safe_node_identifier(cls, value: Any, fallback: str) -> str:
        """Return the lowercase function identifier used for generated graph nodes."""

        return cls._safe_identifier(value, fallback).lower()

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

    def _augment_chatbot_state_schema(
        self,
        workflow_design: Dict[str, Any],
        notebook_plan: NotebookPlan | None = None,
    ) -> Dict[str, Any]:
        """Return state schema plus canonical chatbot/verifier memory fields."""

        state_schema = dict(workflow_design.get("state_schema") or {})
        if not self._is_chatbot_workflow(workflow_design, notebook_plan):
            return state_schema
        for field_name, description in self._CHATBOT_STATE_FIELDS.items():
            state_schema.setdefault(field_name, description)
        return state_schema

    def _workflow_state_fields(
        self,
        workflow_design: Dict[str, Any],
        notebook_plan: NotebookPlan | None = None,
    ) -> set[str]:
        """Return sanitized state field names expected by generated code."""

        state_schema = self._augment_chatbot_state_schema(
            workflow_design,
            notebook_plan,
        )
        return {
            self._safe_identifier(field_name, "field").lower()
            for field_name in state_schema
        }

    def _nodes_for_generated_node_cells(
        self,
        workflow_design: Dict[str, Any],
        nodes: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Return nodes that need explicit node-cell implementations."""

        canonical_schema = self._canonical_graph_schema(workflow_design)
        if not canonical_schema:
            return nodes
        architecture_type = str(
            canonical_schema.get("architecture_type")
            or workflow_design.get("architecture_type")
            or ""
        ).lower()
        if architecture_type not in {"subagents", "autoagent", "hybrid"}:
            return nodes
        node_names = {
            str(node.get("name") or "") for node in canonical_schema.get("nodes", [])
        }
        if "finish" not in node_names:
            return nodes
        return [node for node in nodes if str(node.get("name") or "") != "finish"]

    def _with_required_pattern_scaffold_nodes(
        self,
        nodes: List[Dict[str, Any]],
        workflow_design: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Ensure fallback node cells define handlers referenced by pattern graphs."""

        architecture_type = str(workflow_design.get("architecture_type") or "").lower()
        required_by_architecture = {
            "router": [
                ("router", "Route the chat turn to the next workflow handler."),
            ],
            "subagents": [
                ("supervisor", "Coordinate the generated chatbot subagents."),
            ],
            "hybrid": [
                ("router", "Route direct chatbot turns or delegate to the team."),
                ("supervisor", "Coordinate the generated chatbot worker team."),
            ],
            "autoagent": [
                ("coordinator", "Coordinate generated chatbot worker agents."),
            ],
        }
        required_nodes = required_by_architecture.get(architecture_type, [])
        if not required_nodes:
            return nodes

        existing_names = {
            str(node.get("name") or "").strip().lower()
            for node in nodes
            if isinstance(node, dict)
        }
        prepended_nodes: list[Dict[str, Any]] = []
        for name, purpose in required_nodes:
            if name not in existing_names:
                prepended_nodes.append({"name": name, "purpose": purpose})
                existing_names.add(name)
        return [*prepended_nodes, *nodes]

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
        if self._is_chatbot_workflow(workflow_design, notebook_plan):
            workflow_design["state_schema"] = self._augment_chatbot_state_schema(
                workflow_design,
                notebook_plan,
            )
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
            "from langchain_openai import ChatOpenAI",
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
            'THREAD_ID = "lnf-demo-thread"',
            "SHOW_UPDATES = False",
            "RUN_INTERACTIVE_LOOP = False",
            "RUN_DEMO_TURNS = False",
            "CHARACTER_GENDER = None  # Set to 'male' or 'female' to skip the first-turn prompt.",
            "ANACHRONISM_TERMS = (",
            '    "smartphone",',
            '    "internet",',
            '    "television",',
            '    "movie",',
            '    "star wars",',
            '    "computer",',
            '    "airplane",',
            '    "radio",',
            '    "electricity",',
            ")",
            "",
            "# Credentials",
            "# Prefer environment variables over hardcoded secrets in notebooks.",
            "def _load_env_var(name: str) -> str:",
            '    """Load a credential from env, Colab secrets, or an interactive prompt."""',
            "    value = os.environ.get(name, '')",
            "    if value:",
            "        return value",
            "    try:",
            "        from google.colab import userdata  # type: ignore",
            "        value = userdata.get(name) or ''",
            "    except Exception:",
            "        value = ''",
            "    if value:",
            "        os.environ[name] = value",
            "        return value",
            "    try:",
            "        from getpass import getpass",
            "        value = getpass(f'Enter {name}: ')",
            "    except (EOFError, KeyboardInterrupt):",
            "        value = ''",
            "    if value:",
            "        os.environ[name] = value",
            "    return value",
            "",
        ]
        for env_var in dependency_plan.provider_env_vars:
            safe_env_var = self._normalize_provider_env_var(env_var)
            if not safe_env_var:
                continue
            config_lines.extend(
                [
                    f'{safe_env_var} = _load_env_var("{safe_env_var}")',
                    f"if not {safe_env_var}:",
                    f'    print("{safe_env_var} is not set. Configure it before running live model cells.")',
                    "",
                ]
            )
        if not dependency_plan.provider_env_vars:
            config_lines.append(
                "# No provider-specific credential environment variables were required for this notebook."
            )
        config_lines.extend(
            [
                "",
                "def make_llm(",
                "    *,",
                "    model: str = MODEL,",
                "    temperature: float = TEMPERATURE,",
                "    max_tokens: int | None = MAX_TOKENS,",
                "):",
                '    """Construct a ChatOpenAI client from notebook-level settings."""',
                "    kwargs: dict[str, object] = {",
                '        "model": model,',
                '        "temperature": temperature,',
                "    }",
                "    if API_BASE:",
                '        kwargs["base_url"] = API_BASE',
                "    if max_tokens is not None:",
                '        kwargs["max_tokens"] = max_tokens',
                "    return ChatOpenAI(**kwargs)",
            ]
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
        augmented_state_schema = self._augment_chatbot_state_schema(workflow_design)
        state_schema = self._state_schema_extensions(
            architecture_type,
            augmented_state_schema,
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
            fields = render_additional_fields(
                {
                    name: str(desc)
                    for name, desc in state_schema.items()
                    if self._safe_identifier(name, "field").lower() != "messages"
                }
            )
            state_content = f"""import operator
from typing import Annotated, Dict, List

from langchain_core.messages import BaseMessage
from langgraph.graph import MessagesState
from langgraph.graph.message import add_messages


class WorkflowState(MessagesState):
    \"\"\"Custom workflow state schema.

    Inherits from MessagesState to maintain conversation history.
    \"\"\"
{fields if fields else "    pass"}"""

        return [
            CellSpec(
                cell_type="markdown",
                content="## State Schema\n\nDefine the workflow state:",
                section="state",
            ),
            CellSpec(cell_type="code", content=state_content, section="state"),
        ]

    @classmethod
    def _tool_contract_ids(cls, tool: Dict[str, Any]) -> set[str]:
        """Return normalized identifiers that may link a tool to graph reachability."""

        identifiers = {
            str(tool.get("tool_id") or "").strip(),
            str(tool.get("name") or "").strip(),
            cls._safe_identifier(tool.get("name") or "", "tool"),
        }
        return {identifier for identifier in identifiers if identifier}

    @staticmethod
    def _executable_tool_ids(workflow_design: Dict[str, Any] | None) -> set[str]:
        """Return tool IDs whose graph contract claims executable tool wiring."""

        executable_paths = {
            "tool_node",
            "manual_loop",
            "create_agent",
            "create_react_agent",
        }
        executable_ids: set[str] = set()
        for entry in NotebookComposer._tool_reachability_entries(workflow_design):
            if not isinstance(entry, dict):
                continue
            execution_path = str(entry.get("execution_path") or "").strip()
            if execution_path not in executable_paths:
                continue
            tool_id = str(
                entry.get("tool_id")
                or entry.get("name")
                or entry.get("tool_name")
                or ""
            ).strip()
            if tool_id:
                executable_ids.add(tool_id)
        return executable_ids

    @staticmethod
    def _tool_reachability_entries(
        workflow_design: Dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Return graph tool reachability entries when a workflow declares them."""

        if not workflow_design:
            return []
        graph_exports = workflow_design.get("graph_exports") or {}
        schema = graph_exports.get("schema") if isinstance(graph_exports, dict) else {}
        if not isinstance(schema, dict):
            schema = {}
        entries = schema.get("tool_reachability") or workflow_design.get(
            "tool_reachability",
            [],
        )
        return [entry for entry in entries or [] if isinstance(entry, dict)]

    @staticmethod
    def _as_utility_helper_code(tool_code: str) -> str:
        """Render generated helper code without claiming LangChain tool reachability."""

        utility_notice = [
            "# Utility helper only: this function is not registered as a LangChain tool.",
            "# The graph contract did not declare an executable tool path for it.",
        ]
        source_lines = NotebookComposer._strip_tool_import_scaffold(
            tool_code.splitlines()
        )
        lines: list[str] = []
        if source_lines and source_lines[0].startswith("# WARNING:"):
            lines.append(source_lines[0])
            lines.extend(utility_notice)
            source_lines = source_lines[1:]
        else:
            lines.extend(utility_notice)
        for line in source_lines:
            if line.strip() == "@tool":
                continue
            if line.strip() == "from langchain_core.tools import tool":
                continue
            lines.append(line)
        return "\n".join(lines).strip() + "\n"

    @staticmethod
    def _strip_tool_import_scaffold(source_lines: list[str]) -> list[str]:
        """Remove local @tool import guards when a generated tool becomes a helper."""

        source = "\n".join(source_lines)
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return source_lines

        remove_lines: set[int] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            meaningful_body = [
                statement
                for statement in node.body
                if not (
                    isinstance(statement, ast.Expr)
                    and isinstance(statement.value, ast.Constant)
                    and isinstance(statement.value.value, str)
                )
            ]
            imports_tool = any(
                isinstance(statement, ast.ImportFrom)
                and statement.module == "langchain_core.tools"
                and any(alias.name == "tool" for alias in statement.names)
                for statement in meaningful_body
            )
            if not imports_tool:
                continue
            handlers_are_noop = bool(node.handlers) and all(
                NotebookComposer._handler_only_suppresses_tool_import(handler)
                for handler in node.handlers
            )
            if not handlers_are_noop:
                continue
            end_lineno = getattr(node, "end_lineno", node.lineno)
            remove_lines.update(range(node.lineno, end_lineno + 1))

        if remove_lines:
            return [
                line
                for lineno, line in enumerate(source_lines, start=1)
                if lineno not in remove_lines
            ]
        return source_lines

    @staticmethod
    def _handler_only_suppresses_tool_import(handler: ast.ExceptHandler) -> bool:
        """Return True for except handlers that only neutralize a missing tool import."""

        meaningful_body = [
            statement
            for statement in handler.body
            if not (
                isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Constant)
                and isinstance(statement.value.value, str)
            )
        ]
        if not meaningful_body:
            return False
        for statement in meaningful_body:
            if isinstance(statement, ast.Pass):
                continue
            if isinstance(statement, ast.Assign):
                targets = [
                    target.id
                    for target in statement.targets
                    if isinstance(target, ast.Name)
                ]
                if targets == ["tool"] and isinstance(statement.value, ast.Constant):
                    continue
            if (
                isinstance(statement, ast.AnnAssign)
                and isinstance(statement.target, ast.Name)
                and statement.target.id == "tool"
                and isinstance(statement.value, ast.Constant)
            ):
                continue
            return False
        return True

    async def _create_tool_cells(
        self,
        tools: List[Dict[str, Any]],
        feedback: NotebookCompositionFeedback,
        workflow_design: Dict[str, Any] | None = None,
    ) -> List[CellSpec]:
        """Create tool implementation cells with tracked fallback behavior."""
        cells = [
            CellSpec(
                cell_type="markdown",
                content="## Tools\n\nDefine tools used in the workflow:",
                section="tools",
            )
        ]
        split_by_contract = bool(self._tool_reachability_entries(workflow_design))
        executable_tool_ids = (
            self._executable_tool_ids(workflow_design) if split_by_contract else set()
        )
        executable_tools: list[Dict[str, Any]] = []
        utility_tools: list[Dict[str, Any]] = []
        for tool in tools:
            tool_ids = self._tool_contract_ids(tool)
            if not split_by_contract or tool_ids & executable_tool_ids:
                executable_tools.append(tool)
            else:
                utility_tools.append(tool)

        async def build_tool_code(
            tool: Dict[str, Any],
            *,
            executable: bool,
        ) -> tuple[str, NotebookCompositionFeedback]:
            tool_feedback = NotebookCompositionFeedback()
            tool_code = await self._generate_tool_implementation(
                tool,
                feedback=tool_feedback,
            )
            if not executable:
                tool_code = self._as_utility_helper_code(tool_code)
            return tool_code, tool_feedback

        tool_results = await self._execute_llm_tasks_in_order(
            executable_tools,
            lambda tool: build_tool_code(tool, executable=True),
        )
        utility_results = await self._execute_llm_tasks_in_order(
            utility_tools,
            lambda tool: build_tool_code(tool, executable=False),
        )
        tool_function_names: list[str] = []
        for tool_code, tool_feedback in tool_results:
            self._merge_feedback(feedback, tool_feedback)
            cells.append(CellSpec(cell_type="code", content=tool_code, section="tools"))
            tool_function_names.append(
                self._tool_function_name(tool_code, "unknown_tool")
            )
        for tool_code, tool_feedback in utility_results:
            self._merge_feedback(feedback, tool_feedback)
            cells.append(CellSpec(cell_type="code", content=tool_code, section="tools"))

        tool_function_names = [
            name for name in dict.fromkeys(tool_function_names) if name
        ]
        if tool_function_names:
            tools_list = ", ".join(tool_function_names)
            registry_code = f"""from langgraph.prebuilt import ToolNode

TOOLS = [{tools_list}]
TOOLS_BY_NAME = {{tool.name: tool for tool in TOOLS}}
tool_node = ToolNode(TOOLS, handle_tool_errors=True)"""
            cells.append(
                CellSpec(cell_type="code", content=registry_code, section="tools")
            )

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
- Decorate runnable LangChain tools with @tool from langchain_core.tools
- Include proper error handling
- Add helpful docstrings
- Import necessary libraries at the function level
- Use best practices for the tool's category
- Make it immediately runnable
- In custom StateGraph workflows, execute tools through ToolNode or an explicit ToolMessage loop.
- For a standard prebuilt agent loop, prefer langchain.agents.create_agent over deprecated langgraph.prebuilt.create_react_agent.

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

            generated_code = self._ensure_langchain_tool_code(generated_code)

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

        return (
            header + "from langchain_core.tools import tool\n\n@tool\n" + implementation
        )

    async def _create_node_cells(
        self,
        workflow_design: Dict[str, Any],
        feedback: NotebookCompositionFeedback,
        tools: Optional[List[Dict[str, Any]]] = None,
        notebook_plan: NotebookPlan | None = None,
    ) -> List[CellSpec]:
        """Create node implementation cells with tracked fallback behavior."""
        cells = [
            CellSpec(
                cell_type="markdown",
                content="## Nodes\n\nImplement workflow nodes:",
                section="nodes",
            )
        ]

        nodes = self._nodes_for_generated_node_cells(
            workflow_design,
            list(workflow_design.get("nodes", [])),
        )
        architecture_type = workflow_design.get("architecture_type", "router")
        is_chatbot_workflow = self._is_chatbot_workflow(
            workflow_design,
            notebook_plan,
        )
        if is_chatbot_workflow:
            nodes = self._with_required_pattern_scaffold_nodes(
                nodes,
                workflow_design,
            )
        use_pattern_nodes = (
            architecture_type
            in [
                "router",
                "subagents",
                "hybrid",
                "autoagent",
                "deepagents",
                "critique_loop",
            ]
            and not is_chatbot_workflow
        )

        # Check if we should use pattern-based generation
        if use_pattern_nodes:
            # Use pattern library for architecture-specific nodes
            pattern_cells = self._create_pattern_node_cells(
                nodes, architecture_type, workflow_design, tools=tools
            )
            cells.extend(pattern_cells)
        elif is_chatbot_workflow:
            for node in nodes:
                cells.append(
                    CellSpec(
                        cell_type="code",
                        content=self._generate_node_fallback(
                            node,
                            workflow_design,
                            reason="Chatbot workflows use deterministic contract nodes for memory, verifier, and revision semantics.",
                            feedback=feedback,
                        ),
                        section="nodes",
                    )
                )
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
        safe_node_identifier = self._safe_node_identifier(node_name, "unknown")
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
- Use the notebook-level make_llm(...) helper for LLM initialization if needed
- Use MessagesState pattern with proper message handling
- Import necessary libraries at the function level
- Add comprehensive docstring
- Implement actual logic based on the purpose (no 'pass' statements)
- Handle state fields appropriately
- For verifier/checker nodes, write structured pass/fail and revision fields such as needs_revision, historical_risk_notes, realism_notes, and revision_instructions
- For reviser nodes, consume revision_instructions and clear needs_revision when the response has been revised

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
        safe_node_identifier = self._safe_node_identifier(node_name, "unknown")
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
        lowered_node_context = f"{safe_node_name} {node_purpose}".lower()
        state_fields = self._workflow_state_fields(workflow_design)

        update_lines = [
            "    updates: dict[str, object] = {}",
            '    messages = list(state.get("messages", []))',
            '    last_content = messages[-1].content if messages else ""',
            f'    node_summary = {node_name_literal} + " completed: " + (last_content or {node_purpose_literal})',
            '    updates["messages"] = messages + [HumanMessage(content=node_summary)]',
        ]
        written_state_fields: set[str] = {"messages"}

        def add_if_state_field(field_name: str, *lines: str) -> None:
            if field_name in state_fields and field_name not in written_state_fields:
                update_lines.extend(lines)
                written_state_fields.add(field_name)

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
        elif any(
            marker in lowered_node_context
            for marker in {"verify", "verifier", "verification", "check", "realism"}
        ):
            update_lines.extend(
                [
                    '    draft = str(state.get("draft_response") or state.get("final_response") or last_content)',
                    "    lowered_draft = draft.lower()",
                    '    configured_terms = globals().get("ANACHRONISM_TERMS", (',
                    '        "smartphone", "internet", "television", "movie", "star wars", "computer", "airplane"',
                    "    ))",
                    "    anachronism_terms = tuple(str(term).lower() for term in configured_terms if str(term).strip())",
                    "    findings = [term for term in anachronism_terms if term in lowered_draft]",
                    '    revision_count = int(state.get("revision_count", 0))',
                    "    max_revisions = int(globals().get('MAX_ITERATIONS', 3) or 3)",
                    "    needs_revision = bool(findings) and revision_count < max_revisions",
                    "    safety_passed = not findings",
                    "    historical_risk_notes = (",
                    '        "Potential anachronisms detected: " + ", ".join(findings)',
                    "        if findings",
                    '        else "No obvious anachronisms detected."',
                    "    )",
                    '    realism_notes = "Checked response against persona and historical-realism constraints."',
                    "    revision_instructions = (",
                    '        "Revise the draft to avoid future knowledge or out-of-period references: " + ", ".join(findings)',
                    "        if needs_revision",
                    '        else ""',
                    "    )",
                    '    updates["safety_passed"] = safety_passed',
                    '    updates["needs_revision"] = needs_revision',
                    '    updates["historical_risk_notes"] = historical_risk_notes',
                    '    updates["realism_notes"] = realism_notes',
                    '    updates["revision_instructions"] = revision_instructions',
                    '    updates["verification_passed"] = safety_passed',
                    '    updates["route"] = "revise" if needs_revision else "accept"',
                    "    if not needs_revision:",
                    '        updates["final_response"] = draft',
                ]
            )
        elif any(marker in lowered_node_context for marker in {"revise", "revision"}):
            update_lines.extend(
                [
                    '    revision_history = list(state.get("revision_history", []))',
                    '    instructions = state.get("revision_instructions", "")',
                    '    draft = str(state.get("draft_response") or state.get("final_response") or last_content)',
                    '    revision_count = int(state.get("revision_count", 0)) + 1',
                    "    revised_draft = (",
                    '        draft + "\\n\\nRevision note: " + str(instructions or "Keep the answer in-period and in persona.")',
                    "    )",
                    '    revision_history.append(instructions or "No revision required.")',
                    '    updates["draft_response"] = revised_draft',
                    '    updates["revision_count"] = revision_count',
                    '    updates["revision_history"] = revision_history',
                    '    updates["needs_revision"] = False',
                    '    updates["revision_instructions"] = ""',
                    '    updates["route"] = "verify"',
                ]
            )
        elif any(
            marker in lowered_node_context
            for marker in {
                "persona",
                "character",
                "chat",
                "draft",
                "response",
                "commoner",
                "memory",
            }
        ):
            update_lines.extend(
                [
                    '    selected_gender = str(state.get("selected_gender") or state.get("character_sex") or "female").lower()',
                    '    if selected_gender not in {"male", "female"}:',
                    '        selected_gender = "female"',
                    "    persona_profile = {",
                    '        "gender": selected_gender,',
                    '        "role": "18th-century conversational character",',
                    '        "style": "period-appropriate, plainspoken, and historically grounded",',
                    "    }",
                    "    draft = node_summary",
                ]
            )
            add_if_state_field(
                "selected_gender", '    updates["selected_gender"] = selected_gender'
            )
            add_if_state_field(
                "character_sex", '    updates["character_sex"] = selected_gender'
            )
            add_if_state_field(
                "character_gender",
                '    updates["character_gender"] = selected_gender',
            )
            add_if_state_field(
                "persona_choice",
                '    updates["persona_choice"] = f"{selected_gender}_commoner"',
            )
            add_if_state_field(
                "persona",
                '    updates["persona"] = f"{selected_gender}_commoner"',
            )
            add_if_state_field(
                "persona_id",
                '    updates["persona_id"] = f"{selected_gender}_commoner"',
            )
            add_if_state_field(
                "gender_pending", '    updates["gender_pending"] = False'
            )
            add_if_state_field(
                "persona_profile", '    updates["persona_profile"] = persona_profile'
            )
            add_if_state_field(
                "character_profile",
                '    updates["character_profile"] = persona_profile',
            )
            add_if_state_field(
                "draft_response", '    updates["draft_response"] = draft'
            )
            add_if_state_field(
                "final_response", '    updates["final_response"] = draft'
            )
            add_if_state_field(
                "turn_count",
                '    updates["turn_count"] = int(state.get("turn_count", 0)) + 1',
            )
            add_if_state_field(
                "memory_summary",
                '    updates["memory_summary"] = (',
                '        str(state.get("memory_summary") or "").strip()',
                '        + ("\\n" if state.get("memory_summary") else "")',
                "        + node_summary",
                "    )[-1200:]",
            )
            add_if_state_field(
                "persona_memory",
                '    updates["persona_memory"] = (',
                '        str(state.get("persona_memory") or "").strip()',
                '        + ("\\n" if state.get("persona_memory") else "")',
                "        + node_summary",
                "    )[-1200:]",
            )
            add_if_state_field(
                "conversation_summary",
                '    updates["conversation_summary"] = (',
                '        str(state.get("conversation_summary") or "").strip()',
                '        + ("\\n" if state.get("conversation_summary") else "")',
                "        + node_summary",
                "    )[-1200:]",
            )
            add_if_state_field(
                "conversation_memory",
                '    updates["conversation_memory"] = (',
                '        str(state.get("conversation_memory") or "").strip()',
                '        + ("\\n" if state.get("conversation_memory") else "")',
                "        + node_summary",
                "    )[-1200:]",
            )
            for field_name in sorted(state_fields - written_state_fields):
                lowered_field = field_name.lower()
                field_literal = json.dumps(field_name)
                if "profile" in lowered_field:
                    update_lines.append(
                        f"    updates[{field_literal}] = persona_profile"
                    )
                    written_state_fields.add(field_name)
                elif (
                    "memories" in lowered_field
                    or "conversation_history" in lowered_field
                ):
                    update_lines.append(
                        f"    updates[{field_literal}] = [node_summary]"
                    )
                    written_state_fields.add(field_name)
                elif "memory" in lowered_field:
                    update_lines.extend(
                        [
                            f"    updates[{field_literal}] = (",
                            f"        str(state.get({field_literal}) or '').strip()",
                            f"        + ('\\n' if state.get({field_literal}) else '')",
                            "        + node_summary",
                            "    )[-1200:]",
                        ]
                    )
                    written_state_fields.add(field_name)
                elif "persona" in lowered_field:
                    update_lines.append(
                        f'    updates[{field_literal}] = f"{{selected_gender}}_commoner"'
                    )
                    written_state_fields.add(field_name)
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
    def _is_pattern_terminal_node(
        node: Dict[str, Any],
        workflow_design: Dict[str, Any] | None = None,
    ) -> bool:
        """Return whether a graph node is a terminal handled by pattern templates."""

        name = str(node.get("name", "")).strip()
        normalized_name = name.lower()
        role = str(node.get("role", "")).strip().lower()
        terminal_names = {
            str(value).strip().lower()
            for value in (workflow_design or {}).get("terminal_nodes") or []
            if str(value).strip()
        }
        if normalized_name in terminal_names:
            return True
        if normalized_name in NotebookComposer._PATTERN_TERMINAL_NAMES:
            return True
        return bool(role and role in NotebookComposer._PATTERN_TERMINAL_ROLES)

    @classmethod
    def _router_route_specs(
        cls,
        nodes: List[Dict[str, Any]],
        workflow_design: Dict[str, Any] | None = None,
    ) -> list[tuple[str, str]]:
        """Return route labels and descriptions for router pattern cells."""

        specs: list[tuple[str, str]] = []
        seen: set[str] = set()
        for node in nodes:
            name = str(node.get("name") or "").strip()
            if not name or name == "router":
                continue
            if cls._is_pattern_terminal_node(node, workflow_design):
                continue
            if name in seen:
                continue
            seen.add(name)
            purpose = str(node.get("purpose") or f"Handle {name} requests").strip()
            specs.append((name, purpose or f"Handle {name} requests"))

        if specs:
            return specs
        return [("default", "Handle the default routed request.")]

    @classmethod
    def _subagent_specs(
        cls,
        nodes: List[Dict[str, Any]],
        workflow_design: Dict[str, Any] | None = None,
    ) -> list[tuple[str, str]]:
        """Return subagent labels and descriptions for supervisor pattern cells."""

        specs: list[tuple[str, str]] = []
        seen: set[str] = set()
        for node in nodes:
            name = str(node.get("name") or "").strip()
            if not name or name == "supervisor":
                continue
            if cls._is_pattern_terminal_node(node, workflow_design):
                continue
            if name in seen:
                continue
            seen.add(name)
            purpose = str(node.get("purpose") or f"{name} specialist").strip()
            specs.append((name, purpose or f"{name} specialist"))

        if specs:
            return specs
        return [("worker", "General worker specialist.")]

    @classmethod
    def _autoagent_worker_specs(
        cls,
        nodes: List[Dict[str, Any]],
        workflow_design: Dict[str, Any] | None = None,
    ) -> list[tuple[str, str]]:
        """Return worker labels and descriptions for autoagent pattern cells."""

        specs: list[tuple[str, str]] = []
        seen: set[str] = set()
        for node in nodes:
            name = str(node.get("name") or "").strip()
            if not name or name in {"coordinator", "supervisor"}:
                continue
            if cls._is_pattern_terminal_node(node, workflow_design):
                continue
            if name in seen:
                continue
            seen.add(name)
            purpose = str(node.get("purpose") or f"{name} worker").strip()
            specs.append((name, purpose or f"{name} worker"))

        if specs:
            return specs
        return [("worker", "General worker specialist.")]

    @staticmethod
    def _split_hybrid_nodes(
        nodes: List[Dict[str, Any]],
        workflow_design: Dict[str, Any] | None = None,
    ) -> tuple[List[str], Dict[str, str], List[str], Dict[str, str]]:
        """Split hybrid nodes into direct-specialist and team-worker groups."""

        non_router_nodes = [
            node
            for node in nodes
            if node.get("name") not in {"router", "supervisor"}
            and not NotebookComposer._is_pattern_terminal_node(node, workflow_design)
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
        if not team_workers and "worker" not in direct_specialists:
            team_workers.append("worker")

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
            route_specs = self._router_route_specs(nodes, workflow_design)
            routes = [name for name, _ in route_specs]

            # Generate router node
            router_code = RouterPattern.generate_router_node_code(
                routes,
                model_config=model_config,
                use_notebook_helper=True,
            )
            cells.append(
                CellSpec(cell_type="code", content=router_code, section="nodes")
            )

            # Generate route handler nodes
            for route_name, route_purpose in route_specs:
                route_code = RouterPattern.generate_route_node_code(
                    route_name,
                    route_purpose,
                    model_config=model_config,
                    use_notebook_helper=True,
                )
                cells.append(
                    CellSpec(cell_type="code", content=route_code, section="nodes")
                )

        elif architecture_type == "subagents":
            subagent_specs = self._subagent_specs(nodes, workflow_design)
            subagents = [name for name, _ in subagent_specs]
            subagent_descriptions = dict(subagent_specs)

            # Generate supervisor node
            supervisor_code = SubagentsPattern.generate_supervisor_code(
                subagents,
                subagent_descriptions,
                model_config=model_config,
                use_notebook_helper=True,
            )
            cells.append(
                CellSpec(cell_type="code", content=supervisor_code, section="nodes")
            )

            # Generate subagent nodes
            for subagent_name, subagent_purpose in subagent_specs:
                subagent_code = SubagentsPattern.generate_subagent_code(
                    subagent_name,
                    subagent_purpose,
                    model_config=model_config,
                    use_notebook_helper=True,
                )
                cells.append(
                    CellSpec(cell_type="code", content=subagent_code, section="nodes")
                )
        elif architecture_type == "hybrid":
            (
                direct_specialists,
                direct_descriptions,
                team_workers,
                worker_descriptions,
            ) = self._split_hybrid_nodes(nodes, workflow_design)

            router_code = HybridPattern.generate_router_node_code(
                direct_specialists,
                model_config=model_config,
                use_notebook_helper=True,
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
                    use_notebook_helper=True,
                )
                cells.append(
                    CellSpec(cell_type="code", content=specialist_code, section="nodes")
                )

            supervisor_code = HybridPattern.generate_supervisor_code(
                team_workers,
                worker_descriptions,
                model_config=model_config,
                use_notebook_helper=True,
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
                    use_notebook_helper=True,
                )
                cells.append(
                    CellSpec(cell_type="code", content=worker_code, section="nodes")
                )
        elif architecture_type == "autoagent":
            worker_specs = self._autoagent_worker_specs(nodes, workflow_design)
            workers = [name for name, _ in worker_specs]
            worker_descriptions = dict(worker_specs)

            coordinator_code = AutoAgentPattern.generate_coordinator_code(
                workers,
                worker_descriptions,
                model_config=model_config,
                use_notebook_helper=True,
            )
            cells.append(
                CellSpec(cell_type="code", content=coordinator_code, section="nodes")
            )

            for worker_name, worker_purpose in worker_specs:
                worker_code = AutoAgentPattern.generate_worker_code(
                    worker_name,
                    worker_purpose,
                    model_config=model_config,
                    use_notebook_helper=True,
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
                model_config=model_config,
                use_notebook_helper=True,
            )
            cells.append(
                CellSpec(cell_type="code", content=generate_code, section="nodes")
            )

            critique_code = CritiqueLoopPattern.generate_critique_node_code(
                model_config=model_config,
                use_notebook_helper=True,
            )
            cells.append(
                CellSpec(cell_type="code", content=critique_code, section="nodes")
            )

            revise_code = CritiqueLoopPattern.generate_revise_node_code(
                model_config=model_config,
                use_notebook_helper=True,
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
        canonical_schema = self._canonical_graph_schema(workflow_design)
        if canonical_schema:
            return self._wrap_graph_cells(
                self._generate_canonical_graph_code(workflow_design, canonical_schema),
                canonical_schema=canonical_schema,
            )

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
                name for name, _ in self._router_route_specs(nodes, workflow_design)
            ]
            graph_code = RouterPattern.generate_graph_code(routes)
        elif architecture_type == "subagents":
            subagents = [
                name for name, _ in self._subagent_specs(nodes, workflow_design)
            ]
            graph_code = SubagentsPattern.generate_graph_code(
                subagents,
                max_iterations=max_iterations,
            )
        elif architecture_type == "hybrid":
            direct_specialists, _, team_workers, _ = self._split_hybrid_nodes(
                nodes, workflow_design
            )
            graph_code = HybridPattern.generate_graph_code(
                direct_specialists,
                team_workers,
                max_iterations=max_iterations,
            )
        elif architecture_type == "autoagent":
            workers = [
                name for name, _ in self._autoagent_worker_specs(nodes, workflow_design)
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
    def _wrap_graph_cells(
        graph_code: str,
        *,
        canonical_schema: Dict[str, Any] | None = None,
    ) -> List[CellSpec]:
        """Wrap graph code with the standard notebook graph section cells."""

        code_metadata: Dict[str, Any] = {}
        if canonical_schema:
            code_metadata["canonical_graph_schema"] = canonical_schema

        return [
            CellSpec(
                cell_type="markdown",
                content="## Build Graph\n\nDefine the LangGraph workflow structure.",
                section="graph",
            ),
            CellSpec(
                cell_type="code",
                content=graph_code,
                metadata=code_metadata,
                section="graph",
            ),
        ]

    @staticmethod
    def _canonical_graph_schema(workflow_design: Dict[str, Any]) -> Dict[str, Any]:
        """Return the canonical graph schema when topology is explicit enough."""

        graph_exports = workflow_design.get("graph_exports")
        if hasattr(graph_exports, "model_dump"):
            graph_exports = graph_exports.model_dump(by_alias=True)

        schema: Dict[str, Any] = {}
        if isinstance(graph_exports, dict) and isinstance(
            graph_exports.get("schema"), dict
        ):
            schema = dict(graph_exports["schema"])
        elif any(
            workflow_design.get(key)
            for key in ("edges", "conditional_edges", "command_routes")
        ):
            schema = {
                "architecture_type": workflow_design.get("architecture_type"),
                "state_schema": workflow_design.get("state_schema", {}),
                "nodes": workflow_design.get("nodes", []),
                "edges": workflow_design.get("edges", []),
                "conditional_edges": workflow_design.get("conditional_edges", []),
                "command_routes": workflow_design.get("command_routes", []),
                "tool_reachability": workflow_design.get("tool_reachability", []),
                "domain_terms": workflow_design.get("domain_terms", []),
                "compiled_graph_variable": workflow_design.get(
                    "compiled_graph_variable", "graph"
                ),
                "entry_point": workflow_design.get("entry_point"),
                "checkpointing": workflow_design.get("checkpointing", True),
                "terminal_nodes": workflow_design.get("terminal_nodes", []),
            }

        nodes = schema.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            return {}

        schema.setdefault("architecture_type", workflow_design.get("architecture_type"))
        schema.setdefault("state_schema", workflow_design.get("state_schema", {}))
        schema.setdefault("edges", workflow_design.get("edges", []))
        schema.setdefault(
            "conditional_edges", workflow_design.get("conditional_edges", [])
        )
        schema.setdefault("command_routes", workflow_design.get("command_routes", []))
        schema.setdefault(
            "tool_reachability", workflow_design.get("tool_reachability", [])
        )
        schema.setdefault("domain_terms", workflow_design.get("domain_terms", []))
        schema.setdefault(
            "compiled_graph_variable",
            workflow_design.get("compiled_graph_variable", "graph"),
        )
        schema.setdefault("entry_point", workflow_design.get("entry_point"))
        schema.setdefault("checkpointing", workflow_design.get("checkpointing", True))
        schema.setdefault("terminal_nodes", workflow_design.get("terminal_nodes", []))
        return normalize_graph_schema_payload(schema)

    def _generate_canonical_graph_code(
        self, workflow_design: Dict[str, Any], schema: Dict[str, Any]
    ) -> str:
        """Render executable graph wiring from canonical graph schema."""

        nodes = [node for node in schema.get("nodes", []) if isinstance(node, dict)]
        node_names = [
            str(node.get("name") or "").strip()
            for node in nodes
            if str(node.get("name") or "").strip()
        ]
        entry_point = str(
            schema.get("entry_point")
            or workflow_design.get("entry_point")
            or (node_names[0] if node_names else "router")
        )
        compiled_graph_variable = str(
            schema.get("compiled_graph_variable")
            or workflow_design.get("compiled_graph_variable")
            or "graph"
        )
        if not compiled_graph_variable.isidentifier() or keyword.iskeyword(
            compiled_graph_variable
        ):
            compiled_graph_variable = "graph"

        def _target_expr(value: Any) -> str:
            normalized = str(value or "").strip()
            if normalized in {"START", "__start__"}:
                return "START"
            if normalized in {"END", "__end__"}:
                return "END"
            return json.dumps(normalized)

        def _branch_key(value: Any) -> str:
            normalized = str(value or "").strip()
            return "END" if normalized in {"END", "__end__"} else normalized

        def _branch_target(value: Any) -> str:
            normalized = str(value or "").strip()
            return "END" if normalized in {"END", "__end__"} else json.dumps(normalized)

        node_additions = "\n".join(
            f"workflow.add_node({json.dumps(node_name)}, {self._safe_node_identifier(node_name, 'node')}_node)"
            for node_name in node_names
        )
        architecture_type = str(
            schema.get("architecture_type")
            or workflow_design.get("architecture_type")
            or ""
        ).strip()
        structural_node_definitions = self._canonical_finish_node_definition(
            architecture_type,
            node_names,
        )

        direct_edge_pairs: list[tuple[str, str]] = []
        for edge in schema.get("edges", []) or []:
            if not isinstance(edge, dict):
                continue
            source = str(edge.get("from") or edge.get("source") or "").strip()
            target = str(edge.get("to") or edge.get("target") or "").strip()
            if source and target:
                direct_edge_pairs.append((source, target))

        route_specs: dict[str, dict[str, Any]] = {}
        route_sources_with_end: set[str] = set()

        def _route_spec(source: str) -> dict[str, Any]:
            return route_specs.setdefault(
                source,
                {
                    "path_entries": [],
                    "route_keys": [],
                    "target_values": set(),
                    "field_names": ["next_agent", "route", "decision", "status"],
                },
            )

        def _add_route_entry(
            source: str,
            label: Any,
            target: Any,
            *,
            dedupe_target: bool = False,
        ) -> None:
            spec = _route_spec(source)
            key = _branch_key(label)
            target_value = _branch_target(target)
            if dedupe_target and target_value in spec["target_values"]:
                return
            if target_value == "END":
                route_sources_with_end.add(source)
            spec["path_entries"].append((key, target_value))
            spec["route_keys"].append(key)
            spec["target_values"].add(target_value)

        for conditional_edge in schema.get("conditional_edges", []) or []:
            if not isinstance(conditional_edge, dict):
                continue
            source = str(
                conditional_edge.get("from") or conditional_edge.get("source") or ""
            ).strip()
            branches = conditional_edge.get("branches")
            if not source or not isinstance(branches, dict) or not branches:
                continue
            for label, target in branches.items():
                _add_route_entry(source, label, target)

        for command_route in schema.get("command_routes", []) or []:
            if not isinstance(command_route, dict):
                continue
            source = str(
                command_route.get("source") or command_route.get("from") or ""
            ).strip()
            destinations = command_route.get("destinations")
            if isinstance(destinations, str):
                destinations = [destinations]
            if not source or not destinations:
                continue
            for destination in destinations:
                _add_route_entry(
                    source,
                    destination,
                    destination,
                    dedupe_target=True,
                )
            update_fields = command_route.get("update_fields")
            if isinstance(update_fields, str):
                update_fields = [update_fields]
            spec = _route_spec(source)
            for field_name in [
                str(field).strip()
                for field in (update_fields or [])
                if str(field).strip()
            ]:
                if field_name not in spec["field_names"]:
                    spec["field_names"].append(field_name)
            if "goto" not in spec["field_names"]:
                spec["field_names"].append("goto")

        route_blocks: list[str] = []
        for index, (source, spec) in enumerate(route_specs.items()):
            path_entries = [
                f"{json.dumps(key)}: {target_value}"
                for key, target_value in spec["path_entries"]
            ]
            if not path_entries:
                continue
            route_name = (
                f"_route_from_{self._safe_node_identifier(source, 'node')}_{index}"
            )
            path_map = "{" + ", ".join(path_entries) + "}"
            field_names = spec["field_names"]
            field_tuple = ", ".join(json.dumps(field) for field in field_names)
            if len(field_names) == 1:
                field_tuple += ","
            default_key = json.dumps(spec["route_keys"][0])
            route_blocks.append(
                f"""def {route_name}(state: WorkflowState) -> str:
    path_map = {path_map}
    for field_name in ({field_tuple}):
        value = state.get(field_name)
        if value in path_map:
            return value
    return {default_key}

workflow.add_conditional_edges({json.dumps(source)}, {route_name}, {path_map})"""
            )

        direct_edge_set = set(direct_edge_pairs)
        terminal_nodes = [
            str(node).strip()
            for node in (schema.get("terminal_nodes") or [])
            if str(node).strip()
        ]
        terminal_nodes_without_explicit_end = [
            node
            for node in terminal_nodes
            if (node, "END") not in direct_edge_set
            and (node, "__end__") not in direct_edge_set
            and node not in route_sources_with_end
        ]
        direct_edge_pairs.extend(
            (node, "END") for node in terminal_nodes_without_explicit_end
        )

        edge_additions = "\n".join(
            f"workflow.add_edge({_target_expr(source)}, {_target_expr(target)})"
            for source, target in direct_edge_pairs
        )
        start_edge = (
            ""
            if ("START", entry_point) in direct_edge_set
            or ("__start__", entry_point) in direct_edge_set
            else f"workflow.add_edge(START, {json.dumps(entry_point)})"
        )
        route_code = "\n\n".join(route_blocks)
        schema_literal = repr(schema)
        checkpointing_enabled = bool(schema.get("checkpointing", True))
        checkpoint_import = (
            "from langgraph.checkpoint.memory import InMemorySaver\n"
            if checkpointing_enabled
            else ""
        )
        checkpoint_setup = (
            "checkpointer = InMemorySaver()\n" if checkpointing_enabled else ""
        )
        compile_statement = (
            f"{compiled_graph_variable} = workflow.compile(checkpointer=checkpointer)"
            if checkpointing_enabled
            else f"{compiled_graph_variable} = workflow.compile()"
        )

        return f"""from langgraph.graph import END, START, StateGraph
{checkpoint_import}

CANONICAL_GRAPH_SPEC = {schema_literal}
{structural_node_definitions}

# Create graph from canonical graph/spec metadata.
workflow = StateGraph(WorkflowState)
{checkpoint_setup}

# Add nodes.
{node_additions if node_additions else "# No canonical nodes were provided."}

# Connect entry point and canonical direct edges.
{start_edge}
{edge_additions if edge_additions else "# No direct graph edges were provided."}

# Add canonical conditional and Command-route destinations.
{route_code if route_code else "# No conditional or Command routes were provided."}

# Compile graph with the canonical variable name.
{compile_statement}"""

    @staticmethod
    def _canonical_finish_node_definition(
        architecture_type: str,
        node_names: list[str],
    ) -> str:
        """Return architecture-owned finish node logic for canonical graph cells."""

        if "finish" not in node_names:
            return ""
        if architecture_type in {"subagents", "autoagent"}:
            return '''

def finish_node(state: WorkflowState) -> dict:
    """Synthesize a final answer from the accumulated specialist outputs."""
    results = state.get("task_results", {})
    if results:
        final_output = "\\n\\n".join(
            f"## {agent}\\n{output}" for agent, output in results.items()
        )
    else:
        final_output = "No specialist results were produced."
    return {
        "final_output": final_output,
        "messages": [],
    }
'''
        if architecture_type == "hybrid":
            return '''

def finish_node(state: WorkflowState) -> dict:
    """Merge direct specialist and worker-team outputs into a final answer."""
    direct_results = state.get("results", {})
    team_results = state.get("task_results", {})
    sections = []
    for agent, output in direct_results.items():
        sections.append(f"## {agent}\\n{output}")
    for agent, output in team_results.items():
        sections.append(f"## {agent}\\n{output}")
    final_output = "\\n\\n".join(sections) if sections else "No workflow results were produced."
    return {
        "final_output": final_output,
        "messages": [],
    }
'''
        return ""

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
                self._safe_node_identifier(node.get("name", "unknown"), "unknown"),
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
                source_slug = self._safe_node_identifier(source, "node")
                function_name = f"_route_from_{source_slug}"
                # Serialize source safely for use inside a string literal in the
                # generated code (handles quotes, backslashes, newlines, etc.).
                safe_source = json.dumps(source)
                conditional_blocks.append(
                    f"""def {function_name}(state: WorkflowState) -> str:
    return "END"

workflow.add_conditional_edges({safe_source}, {function_name}, {{"END": END}})"""
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
                        route_key = "END"
                        path_items.append('"END": END')
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
                source_slug = self._safe_node_identifier(source, "node")
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

    @staticmethod
    def _workflow_search_text(
        workflow_design: Dict[str, Any],
        notebook_plan: NotebookPlan | None = None,
    ) -> str:
        """Return lower-cased text used to infer notebook execution affordances."""

        parts: list[str] = []
        if notebook_plan is not None:
            parts.append(notebook_plan.title)
            parts.extend(notebook_plan.sections)
            parts.extend(notebook_plan.patterns_used)
        parts.extend(str(value) for value in workflow_design.values() if value)
        for node in workflow_design.get("nodes", []) or []:
            if isinstance(node, dict):
                parts.extend(
                    str(node.get(key, "")) for key in ("name", "purpose", "role")
                )
        state_schema = workflow_design.get("state_schema", {})
        if isinstance(state_schema, dict):
            for key, value in state_schema.items():
                parts.append(str(key))
                parts.append(str(value))
        return " ".join(parts).lower()

    @classmethod
    def _is_chatbot_workflow(
        cls,
        workflow_design: Dict[str, Any],
        notebook_plan: NotebookPlan | None = None,
    ) -> bool:
        """Return whether the workflow should render an interactive chat loop."""

        text = cls._workflow_search_text(workflow_design, notebook_plan)
        state_schema = workflow_design.get("state_schema", {})
        state_fields = set(state_schema) if isinstance(state_schema, dict) else set()
        high_signal_terms = {
            "chatbot",
            "chat bot",
            "turn-taking",
            "conversation loop",
            "interactive chat",
            "chat loop",
        }
        if any(term in text for term in high_signal_terms):
            return True
        if {"user_message", "selected_gender", "persona_profile"} & state_fields:
            return True
        return "chat" in text and any(
            term in text for term in {"user input", "conversation", "message"}
        )

    @classmethod
    def _requires_character_selection(
        cls,
        workflow_design: Dict[str, Any],
        notebook_plan: NotebookPlan | None = None,
    ) -> bool:
        """Return whether generated execution should prompt for character gender."""

        text = cls._workflow_search_text(workflow_design, notebook_plan)
        state_schema = workflow_design.get("state_schema", {})
        state_fields = set(state_schema) if isinstance(state_schema, dict) else set()
        if {"selected_gender", "gender_pending"} & state_fields:
            return True
        return ("male" in text and "female" in text) or "gender" in text

    def _create_chat_execution_content(
        self,
        workflow_design: Dict[str, Any],
        notebook_plan: NotebookPlan | None,
    ) -> str:
        """Create a reusable chat-loop execution cell."""

        requires_character = self._requires_character_selection(
            workflow_design,
            notebook_plan,
        )
        state_fields_literal = repr(
            sorted(self._workflow_state_fields(workflow_design, notebook_plan))
        )
        first_turn_gender = (
            "    selected_gender = select_character_gender(CHARACTER_GENDER)\n"
            "    if first_message:\n"
            "        chat_once(first_message, thread_id=thread_id, character_gender=selected_gender, show_updates=show_updates)"
            if requires_character
            else "    if first_message:\n"
            "        chat_once(first_message, thread_id=thread_id, show_updates=show_updates)"
        )

        next_turn_gender = (
            "        chat_once(user_input, thread_id=thread_id, character_gender=selected_gender, show_updates=show_updates)"
            if requires_character
            else "        chat_once(user_input, thread_id=thread_id, show_updates=show_updates)"
        )

        return f'''from langchain_core.messages import BaseMessage, HumanMessage


_MISSING = object()
WORKFLOW_STATE_FIELDS = set({state_fields_literal})


def _find_nested_key(value, target_key: str, default=_MISSING):
    """Find a key in nested dict/list values without treating falsey values as absent."""
    if isinstance(value, dict):
        if target_key in value:
            return value[target_key]
        for nested_value in value.values():
            found = _find_nested_key(nested_value, target_key, default)
            if found is not _MISSING:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_nested_key(item, target_key, default)
            if found is not _MISSING:
                return found
    return default


def _message_content(value) -> str:
    if isinstance(value, BaseMessage):
        return str(value.content)
    if isinstance(value, dict) and "content" in value:
        return str(value["content"])
    return str(value)


def _extract_final_output(state: dict) -> str:
    for key in ("final_output", "final_response", "revised_response", "draft_response"):
        value = _find_nested_key(state, key, "")
        if isinstance(value, str) and value.strip():
            return value
    task_results = _find_nested_key(state, "task_results", {{}})
    if isinstance(task_results, dict) and task_results:
        return str(next(reversed(task_results.values())))
    messages = _find_nested_key(state, "messages", [])
    if isinstance(messages, list) and messages:
        return _message_content(messages[-1])
    return ""


def _set_state_field(payload: dict, field_name: str, value) -> None:
    if field_name in WORKFLOW_STATE_FIELDS:
        payload[field_name] = value


def select_character_gender(value: str | None = CHARACTER_GENDER) -> str:
    """Resolve the requested character gender before the first chat turn."""
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {{"male", "female"}}:
            return normalized
    while True:
        selected = input("Choose character gender ('male' or 'female'): ").strip().lower()
        if selected in {{"male", "female"}}:
            return selected
        print("Please enter 'male' or 'female'.")


def _chat_input(user_text: str, character_gender: str | None = None) -> dict:
    payload: dict[str, object] = {{"messages": [HumanMessage(content=user_text)]}}
    _set_state_field(payload, "user_message", user_text)
    _set_state_field(payload, "user_request", user_text)
    if character_gender:
        persona_profile = {{
            "gender": character_gender,
            "role": "18th-century conversational character",
            "style": "period-appropriate, plainspoken, and historically grounded",
        }}
        if "selected_gender" in WORKFLOW_STATE_FIELDS:
            payload["selected_gender"] = character_gender
        if "character_sex" in WORKFLOW_STATE_FIELDS:
            payload["character_sex"] = character_gender
        if "character_gender" in WORKFLOW_STATE_FIELDS:
            payload["character_gender"] = character_gender
        if "persona_choice" in WORKFLOW_STATE_FIELDS:
            payload["persona_choice"] = f"{{character_gender}}_commoner"
        if "persona" in WORKFLOW_STATE_FIELDS:
            payload["persona"] = f"{{character_gender}}_commoner"
        if "persona_id" in WORKFLOW_STATE_FIELDS:
            payload["persona_id"] = f"{{character_gender}}_commoner"
        if "gender_pending" in WORKFLOW_STATE_FIELDS:
            payload["gender_pending"] = False
        if "needs_character_selection" in WORKFLOW_STATE_FIELDS:
            payload["needs_character_selection"] = False
        if "persona_profile" in WORKFLOW_STATE_FIELDS:
            payload["persona_profile"] = persona_profile
        if "character_profile" in WORKFLOW_STATE_FIELDS:
            payload["character_profile"] = persona_profile
    return payload


def chat_once(
    user_text: str,
    *,
    thread_id: str = THREAD_ID,
    character_gender: str | None = None,
    show_updates: bool = SHOW_UPDATES,
) -> dict:
    """Run one chat turn while preserving thread-scoped graph memory."""
    config = {{"configurable": {{"thread_id": thread_id}}, "recursion_limit": 25}}
    inputs = _chat_input(user_text, character_gender=character_gender)
    stream_mode = "updates" if show_updates else "values"
    latest_state: dict = {{}}
    for step in graph.stream(inputs, config, stream_mode=stream_mode):
        if show_updates:
            print(step)
        elif isinstance(step, dict):
            latest_state = step
    final_state = graph.get_state(config).values
    response_text = _extract_final_output(final_state or latest_state)
    if response_text:
        print(response_text)
    return final_state or latest_state


def run_chat_loop(
    *,
    first_message: str = "Hello! How do we start?",
    thread_id: str = THREAD_ID,
    show_updates: bool = SHOW_UPDATES,
) -> None:
{first_turn_gender}
    while True:
        user_input = input("\\nEnter next message (or type 'quit' to exit): ").strip()
        if user_input.lower() in {{"quit", "exit", "q"}}:
            break
{next_turn_gender}


def run_demo_turns(
    turns: list[str] | None = None,
    *,
    thread_id: str = THREAD_ID,
    character_gender: str | None = None,
    show_updates: bool = SHOW_UPDATES,
) -> list[dict]:
    """Run repeatable same-thread turns without blocking for input."""
    selected_gender = (
        select_character_gender(character_gender or CHARACTER_GENDER)
        if {requires_character!r}
        else None
    )
    states: list[dict] = []
    for user_text in turns or [
        "Good day. Who are you?",
        "What would you think of a smartphone?",
    ]:
        states.append(
            chat_once(
                user_text,
                thread_id=thread_id,
                character_gender=selected_gender,
                show_updates=show_updates,
            )
        )
    return states


if RUN_INTERACTIVE_LOOP:
    run_chat_loop()
elif RUN_DEMO_TURNS:
    run_demo_turns()
else:
    print("Chat helpers ready. Call chat_once(...) or run_chat_loop() when ready.")'''

    def _create_execution_cells(
        self,
        workflow_design: Dict[str, Any],
        notebook_plan: NotebookPlan | None = None,
    ) -> List[CellSpec]:
        """Create execution cells aligned with the generated workflow state."""
        architecture_type = workflow_design.get("architecture_type", "router")

        if self._is_chatbot_workflow(workflow_design, notebook_plan):
            exec_content = self._create_chat_execution_content(
                workflow_design,
                notebook_plan,
            )
            return [
                CellSpec(
                    cell_type="markdown",
                    content="## Execution\n\nRun the interactive chat loop:",
                    section="execution",
                ),
                CellSpec(cell_type="code", content=exec_content, section="execution"),
            ]

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

print("Streaming workflow state:")
for step in graph.stream(initial_state, config, stream_mode="values"):
    print(step)

final_state = graph.get_state(config).values
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
            location = (
                f"line {exc.lineno}" if exc.lineno is not None else "unknown line"
            )
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
    def _tool_function_name(content: str, fallback: str) -> str:
        """Return the first top-level tool function name from generated code."""

        try:
            parsed = ast.parse(content)
        except SyntaxError:
            return fallback
        for node in parsed.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return node.name
        return fallback

    @staticmethod
    def _ensure_langchain_tool_code(content: str) -> str:
        """Ensure generated tool code is decorated as a LangChain tool."""

        normalized = content.strip()
        try:
            parsed = ast.parse(normalized)
        except SyntaxError:
            return normalized

        first_function = next(
            (
                node
                for node in parsed.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            ),
            None,
        )
        if first_function is None:
            return normalized

        has_tool_import = (
            "from langchain_core.tools import tool" in normalized
            or "from langchain.tools import tool" in normalized
        )
        decorators = set()
        for decorator in first_function.decorator_list:
            if isinstance(decorator, ast.Name):
                decorators.add(decorator.id)
            elif isinstance(decorator, ast.Call) and isinstance(
                decorator.func, ast.Name
            ):
                decorators.add(decorator.func.id)
        has_tool_decorator = "tool" in decorators

        lines = normalized.splitlines()
        if not has_tool_decorator:
            insert_at = max(first_function.lineno - 1, 0)
            lines.insert(insert_at, "@tool")
        if not has_tool_import:
            lines.insert(0, "from langchain_core.tools import tool")
        return "\n".join(lines)

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
