"""Toolchain Engineer agent for selecting and configuring tools."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from langgraph_system_generator.generator.agents._llm import build_chat_llm
from langgraph_system_generator.generator.state import (
    Constraint,
    ToolPlanningFeedback,
    ToolPlanningResult,
    ToolSpec,
)
from langgraph_system_generator.generator.tool_registry import (
    ToolRegistry,
    get_tool_registry,
    normalize_tool_token,
)
from langgraph_system_generator.generator.utils import extract_json_from_llm_response
from langgraph_system_generator.utils.config import ModelConfig


class ToolchainEngineer:
    """Selects and configures tools for the workflow."""

    def __init__(
        self,
        model: str | None = None,
        model_config: ModelConfig | None = None,
        registry: ToolRegistry | None = None,
    ):
        self.llm = build_chat_llm(
            model=model,
            model_config=model_config,
            chat_openai_class=ChatOpenAI,
        )
        self.registry = registry.clone() if registry is not None else get_tool_registry().clone()

    @staticmethod
    def _append_unique(items: List[str], value: str | None) -> None:
        """Append a non-empty string once while preserving order."""

        normalized = str(value or "").strip()
        if normalized and normalized not in items:
            items.append(normalized)

    @staticmethod
    def _string_list(value: Any) -> List[str]:
        """Normalize list-or-scalar input into an ordered string list."""

        if value in (None, ""):
            return []
        if isinstance(value, list):
            raw_items = value
        else:
            raw_items = [value]

        normalized: List[str] = []
        for raw_item in raw_items:
            text = str(raw_item or "").strip()
            if text and text not in normalized:
                normalized.append(text)
        return normalized

    @classmethod
    def _merge_string_lists(cls, *values: Any) -> List[str]:
        """Merge arbitrary string-list inputs into an ordered de-duplicated list."""

        merged: List[str] = []
        for value in values:
            for item in cls._string_list(value):
                if item not in merged:
                    merged.append(item)
        return merged

    @staticmethod
    def _normalize_configuration(value: Any) -> Dict[str, Any]:
        """Return a normalized configuration mapping."""

        if not isinstance(value, Mapping):
            return {}
        return {
            str(key).strip(): item
            for key, item in value.items()
            if str(key or "").strip()
        }

    def _registration_tool_spec(
        self,
        tool_id: str,
        *,
        purpose: str,
        configuration: Mapping[str, Any] | None = None,
        status: str = "ready",
        warnings: List[str] | None = None,
        name: str | None = None,
        packages: Any = None,
        provider_env_vars: Any = None,
    ) -> ToolSpec:
        """Build a ToolSpec from a canonical registry entry."""

        registration = self.registry.get(tool_id)
        tool = registration.build_tool_spec(
            purpose=purpose,
            configuration=configuration,
            status=status,
            warnings=warnings,
            name=name,
        )
        return tool.model_copy(
            update={
                "packages": self._merge_string_lists(tool.packages, packages),
                "provider_env_vars": self._merge_string_lists(
                    tool.provider_env_vars,
                    provider_env_vars,
                ),
            }
        )

    def _unsupported_tool_spec(
        self,
        *,
        raw_name: str,
        raw_category: str,
        purpose: str,
        configuration: Mapping[str, Any] | None,
        warning: str,
    ) -> ToolSpec:
        """Return an unsupported tool spec for unresolved suggestions."""

        fallback_name = raw_name.strip() or "Unsupported Tool"
        tool_token = raw_name or raw_category or "unsupported_tool"
        return ToolSpec(
            tool_id=normalize_tool_token(tool_token),
            name=fallback_name,
            category=(raw_category or "unsupported").strip() or "unsupported",
            purpose=purpose.strip() or f"Unsupported tool suggestion: {fallback_name}",
            configuration=dict(configuration or {}),
            packages=self._string_list((configuration or {}).get("packages")),
            provider_env_vars=self._string_list(
                (configuration or {}).get("provider_env_vars")
            ),
            status="unsupported",
            warnings=[warning],
        )

    def _infer_fallback_tools(
        self,
        workflow_design: Dict[str, Any],
    ) -> List[ToolSpec]:
        """Infer a conservative fallback tool plan from workflow nodes."""

        nodes = list(workflow_design.get("nodes") or [])
        heuristics = [
            ("web_search", ("research", "search", "docs", "documentation")),
            ("file_reader", ("file", "document", "pdf")),
            ("http_client", ("api", "fetch", "http", "request")),
            ("data_processor", ("parse", "transform", "data", "normalize")),
            ("schema_validator", ("validate", "schema", "check", "verify")),
        ]
        heuristic_matches: Dict[str, List[str]] = {
            tool_id: [] for tool_id, _tokens in heuristics
        }

        for node in nodes:
            node_name = str(node.get("name", "")).strip()
            node_purpose = str(node.get("purpose", "")).strip()
            node_text = f"{node_name} {node_purpose}".lower()
            label = node_name or node_purpose or "workflow node"
            for tool_id, tokens in heuristics:
                if any(token in node_text for token in tokens):
                    self._append_unique(heuristic_matches[tool_id], label)

        fallback_tools: List[ToolSpec] = []
        for tool_id, _tokens in heuristics:
            matched_nodes = heuristic_matches[tool_id]
            if not matched_nodes:
                continue
            fallback_tools.append(
                self._registration_tool_spec(
                    tool_id,
                    purpose=(
                        "Heuristically inferred from workflow nodes: "
                        + ", ".join(matched_nodes)
                    ),
                    status="fallback",
                    warnings=[
                        "Heuristic fallback inferred this tool from workflow node intent."
                    ],
                )
            )

        return fallback_tools

    def _normalize_llm_tools(
        self,
        payload: Any,
        feedback: ToolPlanningFeedback,
    ) -> List[ToolSpec]:
        """Normalize an LLM payload into registry-backed tool specs."""

        if not isinstance(payload, list):
            self._append_unique(
                feedback.validation_errors,
                "Tool planning response must be a JSON array of tool objects.",
            )
            return []

        normalized_tools: List[ToolSpec] = []
        for index, item in enumerate(payload):
            if not isinstance(item, Mapping):
                self._append_unique(
                    feedback.validation_errors,
                    f"Tool suggestion at index {index} must be an object.",
                )
                continue

            raw_tool_token = str(item.get("tool_id") or "").strip()
            display_name = str(item.get("name") or "").strip()
            resolution_token = raw_tool_token or display_name
            raw_category = str(item.get("category") or "").strip().lower()
            purpose = str(item.get("purpose") or "").strip()
            configuration = self._normalize_configuration(item.get("configuration"))
            extra_packages = self._merge_string_lists(
                item.get("packages"),
                configuration.get("packages"),
            )
            extra_provider_env_vars = self._merge_string_lists(
                item.get("provider_env_vars"),
                configuration.get("provider_env_vars"),
            )

            if not resolution_token:
                self._append_unique(
                    feedback.validation_errors,
                    f"Tool suggestion at index {index} is missing a tool_id or alias.",
                )
                continue

            resolved_tool_id = self.registry.resolve_tool_id(resolution_token)
            if resolved_tool_id is None:
                warning = (
                    f"Unsupported tool suggestion '{resolution_token}' could not be resolved to a canonical tool."
                )
                self._append_unique(feedback.validation_errors, warning)
                self._append_unique(feedback.unresolved_tools, resolution_token)
                self._append_unique(feedback.warnings, warning)
                normalized_tools.append(
                    self._unsupported_tool_spec(
                        raw_name=display_name or resolution_token,
                        raw_category=raw_category,
                        purpose=purpose,
                        configuration=configuration,
                        warning=warning,
                    )
                )
                continue

            normalized_tools.append(
                self._registration_tool_spec(
                    resolved_tool_id,
                    purpose=purpose or f"Use {resolved_tool_id} for this workflow.",
                    configuration=configuration,
                    status="ready",
                    warnings=self._string_list(item.get("warnings")),
                    name=display_name or None,
                    packages=extra_packages,
                    provider_env_vars=extra_provider_env_vars,
                )
            )

        return normalized_tools

    @staticmethod
    def _has_usable_tools(tools: List[ToolSpec]) -> bool:
        """Return True when the plan contains at least one runnable tool."""

        return any(tool.status != "unsupported" for tool in tools)

    async def plan_tools(
        self, workflow_design: Dict[str, Any], constraints: List[Constraint]
    ) -> ToolPlanningResult:
        """Select tools needed for the workflow.

        Args:
            workflow_design: Workflow design from GraphDesigner
            constraints: Project constraints

        Returns:
            Structured tool-planning output with normalized tool specs and feedback
        """
        nodes = workflow_design.get("nodes", [])
        nodes_text = "\n".join(
            [f"- {node.get('name')}: {node.get('purpose')}" for node in nodes]
        )

        constraints_text = "\n".join([f"- [{c.type}] {c.value}" for c in constraints])
        feedback = ToolPlanningFeedback(
            available_tool_ids=self.registry.supported_tool_ids()
        )
        heuristic_tools = self._infer_fallback_tools(workflow_design)

        tools_prompt = SystemMessage(
            content=f"""You are a toolchain engineer for LangGraph workflows.
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
- tool_id: Canonical tool identifier or supported alias
- name: Human-readable display name for the tool
- category: Tool category
- purpose: Why this tool is needed
- configuration: Any specific configuration

Only recommend tools from this canonical registry:
{self.registry.render_planning_prompt_catalog()}

Return a JSON array:
[
  {{
    "tool_id": "canonical_tool_id_or_alias",
    "name": "display_name",
    "category": "category",
    "purpose": "description",
    "configuration": {{}}
  }},
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
            payload = extract_json_from_llm_response(response.content)
        except (ValueError, KeyError, TypeError) as exc:
            feedback.fallback_used = True
            feedback.fallback_reason = (
                f"Tool planning fell back to heuristic inference after payload parsing failed: {exc}"
            )
            self._append_unique(feedback.warnings, feedback.fallback_reason)
            return ToolPlanningResult(tools=heuristic_tools, feedback=feedback)

        normalized_tools = self._normalize_llm_tools(payload, feedback)
        if self._has_usable_tools(normalized_tools):
            return ToolPlanningResult(tools=normalized_tools, feedback=feedback)

        feedback.fallback_used = True
        feedback.fallback_reason = (
            "Tool planning fell back to heuristic inference because the model returned no usable canonical tools."
        )
        self._append_unique(feedback.warnings, feedback.fallback_reason)

        combined_tools: List[ToolSpec] = list(heuristic_tools)
        combined_tools.extend(
            tool for tool in normalized_tools if tool.status == "unsupported"
        )
        return ToolPlanningResult(tools=combined_tools, feedback=feedback)
