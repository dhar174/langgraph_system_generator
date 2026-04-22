"""Toolchain Engineer agent for selecting and configuring tools."""

from __future__ import annotations

from dataclasses import dataclass
import json
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
from langgraph_system_generator.generator.tool_dependency_utils import (
    DependencyAccumulator,
    accumulate_tool_dependencies,
    merge_string_lists,
)
from langgraph_system_generator.generator.tool_registry import (
    ToolRegistry,
    get_tool_registry,
    normalize_tool_token,
)
from langgraph_system_generator.generator.utils import extract_json_from_llm_response
from langgraph_system_generator.utils.config import ModelConfig


@dataclass(frozen=True)
class _RuntimeEnvironmentProfile:
    """Normalized runtime/environment constraints relevant to tool planning."""

    offline_evidence: tuple[str, ...] = ()
    firewalled_evidence: tuple[str, ...] = ()
    notebook_evidence: tuple[str, ...] = ()

    @property
    def offline(self) -> bool:
        return bool(self.offline_evidence)

    @property
    def firewalled(self) -> bool:
        return bool(self.firewalled_evidence)

    @property
    def notebook_runtime(self) -> bool:
        return bool(self.notebook_evidence)


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

        return merge_string_lists(*values)

    @staticmethod
    def _is_empty_configuration_value(value: Any) -> bool:
        """Return True when a normalized configuration value is empty."""

        return value is None or value == "" or value == [] or value == {}

    @classmethod
    def _canonicalize_configuration_value(cls, value: Any) -> Any:
        """Recursively normalize configuration values for comparison and storage."""

        if isinstance(value, Mapping):
            normalized_items: Dict[str, Any] = {}
            for raw_key, raw_item in value.items():
                key = str(raw_key or "").strip()
                if not key:
                    continue
                normalized_item = cls._canonicalize_configuration_value(raw_item)
                if cls._is_empty_configuration_value(normalized_item):
                    continue
                normalized_items[key] = normalized_item
            return {
                key: normalized_items[key]
                for key in sorted(normalized_items.keys())
            }

        if isinstance(value, list):
            normalized_list: List[Any] = []
            for raw_item in value:
                normalized_item = cls._canonicalize_configuration_value(raw_item)
                if cls._is_empty_configuration_value(normalized_item):
                    continue
                if normalized_item not in normalized_list:
                    normalized_list.append(normalized_item)
            return normalized_list

        if isinstance(value, str):
            return value.strip()

        return value

    @staticmethod
    def _configuration_signature(configuration: Mapping[str, Any]) -> str:
        """Return a stable signature for a normalized configuration mapping."""

        return json.dumps(configuration, sort_keys=True, separators=(",", ":"))

    @classmethod
    def _normalize_configuration(cls, value: Any) -> Dict[str, Any]:
        """Return a normalized configuration mapping."""

        if not isinstance(value, Mapping):
            return {}
        normalized = cls._canonicalize_configuration_value(value)
        return normalized if isinstance(normalized, dict) else {}

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

        normalized_configuration = self._normalize_configuration(configuration)
        registration = self.registry.get(tool_id)
        tool = registration.build_tool_spec(
            purpose=purpose,
            configuration=normalized_configuration,
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
            configuration=self._normalize_configuration(configuration),
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

    @staticmethod
    def _status_rank(status: str) -> int:
        """Return merge precedence for tool statuses."""

        return {
            "unsupported": 0,
            "fallback": 1,
            "ready": 2,
        }.get(str(status or "").strip().lower(), 0)

    @staticmethod
    def _constraint_label(constraint: Constraint) -> str:
        """Return a human-readable label for one constraint."""

        constraint_type = str(constraint.type or "").strip() or "constraint"
        constraint_value = str(constraint.value or "").strip()
        return f"[{constraint_type}] {constraint_value}".strip()

    def _parse_runtime_environment(
        self, constraints: List[Constraint]
    ) -> _RuntimeEnvironmentProfile:
        """Extract runtime/environment hints that affect tool compatibility."""

        offline_evidence: List[str] = []
        firewalled_evidence: List[str] = []
        notebook_evidence: List[str] = []

        for constraint in constraints:
            haystack = (
                f"{str(constraint.type or '').strip()} "
                f"{str(constraint.value or '').strip()}"
            ).lower()
            label = self._constraint_label(constraint)
            if any(
                token in haystack
                for token in (
                    "offline",
                    "no network",
                    "no-network",
                    "without network",
                    "no external api",
                    "no external apis",
                    "no external api calls",
                )
            ):
                self._append_unique(offline_evidence, label)
            if any(
                token in haystack
                for token in (
                    "firewalled",
                    "internal only",
                    "internal-only",
                    "private network only",
                )
            ):
                self._append_unique(firewalled_evidence, label)
            if any(
                token in haystack
                for token in (
                    "google colab",
                    "colab",
                    "jupyter",
                    "notebook runtime",
                )
            ):
                self._append_unique(notebook_evidence, label)

        return _RuntimeEnvironmentProfile(
            offline_evidence=tuple(offline_evidence),
            firewalled_evidence=tuple(firewalled_evidence),
            notebook_evidence=tuple(notebook_evidence),
        )

    def _apply_environment_constraints(
        self,
        tools: List[ToolSpec],
        constraints: List[Constraint],
        feedback: ToolPlanningFeedback,
    ) -> List[ToolSpec]:
        """Downgrade incompatible tools based on runtime/environment constraints."""

        profile = self._parse_runtime_environment(constraints)
        if not (profile.offline or profile.firewalled or profile.notebook_runtime):
            return tools

        filtered_tools: List[ToolSpec] = []
        for tool in tools:
            if tool.status == "unsupported":
                filtered_tools.append(tool)
                continue

            compatibility = self.registry.get(tool.tool_id).environment_compatibility
            reasons: List[str] = []
            label = tool.name.strip() or tool.tool_id

            if profile.offline and compatibility.get("requires_network") is True:
                evidence = ", ".join(profile.offline_evidence)
                reasons.append(
                    f"Blocked tool '{label}' because offline/no-network constraints "
                    f"disallow network-dependent tools ({evidence})."
                )
            if profile.firewalled and compatibility.get("public_web") is True:
                evidence = ", ".join(profile.firewalled_evidence)
                reasons.append(
                    f"Blocked tool '{label}' because firewalled/internal-only constraints "
                    f"disallow public-web tools ({evidence})."
                )
            if (
                profile.notebook_runtime
                and compatibility.get("notebook_safe") is False
            ):
                evidence = ", ".join(profile.notebook_evidence)
                reasons.append(
                    f"Blocked tool '{label}' because the target notebook runtime requires "
                    f"notebook-safe tools ({evidence})."
                )

            if reasons:
                for reason in reasons:
                    self._append_unique(feedback.environment_notes, reason)
                self._append_unique(feedback.unresolved_tools, label)
                filtered_tools.append(
                    tool.model_copy(
                        update={
                            "status": "unsupported",
                            "warnings": self._merge_string_lists(tool.warnings, reasons),
                        }
                    )
                )
                continue

            filtered_tools.append(tool)

        return filtered_tools

    def _deduplicate_tools(
        self,
        tools: List[ToolSpec],
        feedback: ToolPlanningFeedback,
    ) -> List[ToolSpec]:
        """Merge duplicate tool suggestions deterministically and keep conflicts visible."""

        merged: Dict[tuple[str, str], ToolSpec] = {}
        ordered_keys: List[tuple[str, str]] = []
        configurations_by_tool_id: Dict[str, List[str]] = {}

        for tool in tools:
            normalized_configuration = self._normalize_configuration(tool.configuration)
            signature = self._configuration_signature(normalized_configuration)
            key = (tool.tool_id, signature)

            configs_for_tool = configurations_by_tool_id.setdefault(tool.tool_id, [])
            if signature not in configs_for_tool:
                configs_for_tool.append(signature)

            if key not in merged:
                merged[key] = tool.model_copy(update={"configuration": normalized_configuration})
                ordered_keys.append(key)
                continue

            existing = merged[key]
            preferred = (
                tool
                if self._status_rank(tool.status) > self._status_rank(existing.status)
                else existing
            )
            merged[key] = preferred.model_copy(
                update={
                    "configuration": normalized_configuration,
                    "name": existing.name or preferred.name,
                    "purpose": existing.purpose or preferred.purpose,
                    "packages": self._merge_string_lists(existing.packages, tool.packages),
                    "provider_env_vars": self._merge_string_lists(
                        existing.provider_env_vars,
                        tool.provider_env_vars,
                    ),
                    "warnings": self._merge_string_lists(existing.warnings, tool.warnings),
                }
            )

        for tool_id, configurations in configurations_by_tool_id.items():
            if len(configurations) > 1:
                self._append_unique(
                    feedback.dependency_conflicts,
                    f"Tool '{tool_id}' was suggested with multiple configurations; keeping separate entries.",
                )

        return [merged[key] for key in ordered_keys]

    def _validate_dependencies(
        self,
        tools: List[ToolSpec],
        feedback: ToolPlanningFeedback,
    ) -> None:
        """Validate deduplicated tool dependencies with shared normalization helpers."""

        combined_dependencies = DependencyAccumulator()
        for tool in tools:
            if tool.status == "unsupported":
                continue

            tool_mapping = tool.model_dump()
            raw_configuration = tool.configuration if isinstance(tool.configuration, Mapping) else {}
            declared_env_vars = self._merge_string_lists(
                tool.provider_env_vars,
                raw_configuration.get("provider_env_vars"),
            )

            per_tool_dependencies = DependencyAccumulator()
            accumulate_tool_dependencies(per_tool_dependencies, tool_mapping)
            accumulate_tool_dependencies(combined_dependencies, tool_mapping)

            if declared_env_vars and not per_tool_dependencies.provider_env_vars:
                self._append_unique(
                    feedback.dependency_conflicts,
                    f"Tool '{tool.name or tool.tool_id}' declared provider env vars but none normalized into a usable notebook-safe key.",
                )

        for detail in combined_dependencies.conflicts_resolved:
            self._append_unique(feedback.dependency_conflicts, detail)

    def _finalize_tools(
        self,
        tools: List[ToolSpec],
        constraints: List[Constraint],
        feedback: ToolPlanningFeedback,
    ) -> List[ToolSpec]:
        """Apply environment filtering, dedupe, and dependency validation."""

        constrained_tools = self._apply_environment_constraints(
            tools,
            constraints,
            feedback,
        )
        deduplicated_tools = self._deduplicate_tools(constrained_tools, feedback)
        self._validate_dependencies(deduplicated_tools, feedback)
        return deduplicated_tools

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
            return ToolPlanningResult(
                tools=self._finalize_tools(heuristic_tools, constraints, feedback),
                feedback=feedback,
            )

        normalized_tools = self._normalize_llm_tools(payload, feedback)
        if self._has_usable_tools(normalized_tools):
            return ToolPlanningResult(
                tools=self._finalize_tools(normalized_tools, constraints, feedback),
                feedback=feedback,
            )

        feedback.fallback_used = True
        feedback.fallback_reason = (
            "Tool planning fell back to heuristic inference because the model returned no usable canonical tools."
        )
        self._append_unique(feedback.warnings, feedback.fallback_reason)

        combined_tools: List[ToolSpec] = list(heuristic_tools)
        combined_tools.extend(
            tool for tool in normalized_tools if tool.status == "unsupported"
        )
        return ToolPlanningResult(
            tools=self._finalize_tools(combined_tools, constraints, feedback),
            feedback=feedback,
        )
