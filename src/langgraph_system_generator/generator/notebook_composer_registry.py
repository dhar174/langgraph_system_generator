"""Internal registry for NotebookComposer section builders and plugins."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import importlib
from typing import Any, Awaitable, Callable, Mapping, Sequence

from langgraph_system_generator.generator.state import (
    CellSpec,
    NotebookCompositionFeedback,
    NotebookDependencyPlan,
    NotebookPlan,
    ToolPlanningFeedback,
)
from langgraph_system_generator.utils.config import settings

NotebookSectionResult = list[CellSpec] | Awaitable[list[CellSpec]]
NotebookSectionBuilder = Callable[[Any, "NotebookComposerContext"], NotebookSectionResult]
PluginHook = Callable[["NotebookComposerRegistry"], None]


def _normalize_architecture_id(value: str) -> str:
    """Return a normalized architecture identifier."""

    normalized = str(value or "").strip().lower()
    if not normalized:
        raise ValueError(
            "Notebook composer registrations must include a non-empty architecture_id."
        )
    return normalized


def _normalize_builder_name(value: str, *, field_name: str) -> str:
    """Return a normalized builder or hook name."""

    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} must reference a non-empty builder name.")
    return normalized


def _normalize_string_list(values: Sequence[str] | None) -> list[str]:
    """Return an ordered, de-duplicated list of non-empty strings."""

    normalized_values: list[str] = []
    for raw_value in values or []:
        normalized = str(raw_value or "").strip()
        if normalized and normalized not in normalized_values:
            normalized_values.append(normalized)
    return normalized_values


def _normalize_hook_mapping(values: Mapping[str, Sequence[str]] | None) -> dict[str, list[str]]:
    """Return normalized per-section hook mappings."""

    normalized: dict[str, list[str]] = {}
    for raw_section, raw_builders in (values or {}).items():
        section = str(raw_section or "").strip()
        if not section:
            continue
        builder_names = _normalize_string_list(raw_builders)
        if builder_names:
            normalized[section] = builder_names
    return normalized


@dataclass
class NotebookComposerContext:
    """Internal notebook composition context shared across section builders."""

    notebook_plan: NotebookPlan
    workflow_design: dict[str, Any]
    tools: list[dict[str, Any]]
    architecture: dict[str, Any]
    dependency_plan: NotebookDependencyPlan
    feedback: NotebookCompositionFeedback
    tool_planning_feedback: ToolPlanningFeedback


@dataclass
class NotebookComposerArchitectureRegistration:
    """Registration for architecture-specific notebook-composer behavior."""

    architecture_id: str
    section_order: list[str] = field(default_factory=list)
    section_overrides: dict[str, str] = field(default_factory=dict)
    pre_section_hooks: dict[str, list[str]] = field(default_factory=dict)
    post_section_hooks: dict[str, list[str]] = field(default_factory=dict)

    def normalized(
        self,
        *,
        default_section_order: Sequence[str],
    ) -> "NotebookComposerArchitectureRegistration":
        """Return a normalized copy of this registration."""

        section_order = _normalize_string_list(self.section_order) or list(
            default_section_order
        )

        normalized_overrides = {
            str(section or "").strip(): _normalize_builder_name(
                builder_name,
                field_name=f"section_overrides[{section}]",
            )
            for section, builder_name in (self.section_overrides or {}).items()
            if str(section or "").strip()
        }
        return NotebookComposerArchitectureRegistration(
            architecture_id=_normalize_architecture_id(self.architecture_id),
            section_order=section_order,
            section_overrides=normalized_overrides,
            pre_section_hooks=_normalize_hook_mapping(self.pre_section_hooks),
            post_section_hooks=_normalize_hook_mapping(self.post_section_hooks),
        )


class NotebookComposerRegistry:
    """Registry for notebook-composer section builders and architecture hooks."""

    def __init__(self, *, default_section_order: Sequence[str] | None = None):
        self.default_section_order = _normalize_string_list(
            default_section_order
            or ["intro", "install", "config", "state", "tools", "nodes", "graph", "execution"]
        )
        self._builders: dict[str, NotebookSectionBuilder] = {}
        self._architectures: dict[str, NotebookComposerArchitectureRegistration] = {}

    def clone(self) -> "NotebookComposerRegistry":
        """Return a shallow clone suitable for per-composer customization."""

        cloned = NotebookComposerRegistry(default_section_order=self.default_section_order)
        cloned._builders = dict(self._builders)
        cloned._architectures = {
            architecture_id: NotebookComposerArchitectureRegistration(
                architecture_id=registration.architecture_id,
                section_order=list(registration.section_order),
                section_overrides=dict(registration.section_overrides),
                pre_section_hooks={
                    section: list(builder_names)
                    for section, builder_names in registration.pre_section_hooks.items()
                },
                post_section_hooks={
                    section: list(builder_names)
                    for section, builder_names in registration.post_section_hooks.items()
                },
            )
            for architecture_id, registration in self._architectures.items()
        }
        return cloned

    def register_builder(
        self,
        builder_name: str,
        builder: NotebookSectionBuilder,
    ) -> None:
        """Register or replace a named section builder."""

        normalized_name = _normalize_builder_name(builder_name, field_name="builder_name")
        self._builders[normalized_name] = builder

    def register(
        self,
        registration: NotebookComposerArchitectureRegistration,
    ) -> None:
        """Register architecture-specific section overrides and hooks."""

        normalized = registration.normalized(
            default_section_order=self.default_section_order
        )
        referenced_builders = list(normalized.section_overrides.values())
        referenced_builders.extend(
            builder_name
            for builder_names in normalized.pre_section_hooks.values()
            for builder_name in builder_names
        )
        referenced_builders.extend(
            builder_name
            for builder_names in normalized.post_section_hooks.values()
            for builder_name in builder_names
        )
        missing_builders = sorted(
            {
                builder_name
                for builder_name in referenced_builders
                if builder_name not in self._builders
            }
        )
        if missing_builders:
            raise ValueError(
                "Notebook composer registration "
                f"'{normalized.architecture_id}' references unknown builders: "
                + ", ".join(missing_builders)
            )
        self._architectures[normalized.architecture_id] = normalized

    def get(self, architecture_id: str) -> NotebookComposerArchitectureRegistration:
        """Return a registered architecture definition."""

        normalized_id = _normalize_architecture_id(architecture_id)
        try:
            return self._architectures[normalized_id]
        except KeyError as exc:
            raise KeyError(
                f"No notebook composer registration found for '{normalized_id}'."
            ) from exc

    def resolve(
        self,
        architecture_id: str,
    ) -> NotebookComposerArchitectureRegistration:
        """Return the matching registration or a generic default registration."""

        normalized_id = str(architecture_id or "").strip().lower()
        if normalized_id in self._architectures:
            return self._architectures[normalized_id]
        return NotebookComposerArchitectureRegistration(
            architecture_id=normalized_id or "custom",
            section_order=list(self.default_section_order),
        ).normalized(default_section_order=self.default_section_order)

    def builder_names(self) -> set[str]:
        """Return the set of registered section builder names."""

        return set(self._builders)

    def resolve_builder(
        self,
        architecture_id: str,
        section_name: str,
    ) -> NotebookSectionBuilder:
        """Resolve the main builder for a section."""

        registration = self.resolve(architecture_id)
        builder_name = registration.section_overrides.get(section_name, section_name)
        try:
            return self._builders[builder_name]
        except KeyError as exc:
            raise KeyError(
                f"No notebook composer builder named '{builder_name}' is registered for section '{section_name}'."
            ) from exc

    def resolve_hooks(
        self,
        architecture_id: str,
        section_name: str,
        *,
        when: str,
    ) -> list[NotebookSectionBuilder]:
        """Resolve pre- or post-section hook builders."""

        registration = self.resolve(architecture_id)
        hook_mapping = (
            registration.pre_section_hooks
            if when == "pre"
            else registration.post_section_hooks
        )
        builders: list[NotebookSectionBuilder] = []
        for builder_name in hook_mapping.get(section_name, []):
            try:
                builders.append(self._builders[builder_name])
            except KeyError as exc:
                raise KeyError(
                    f"No notebook composer hook builder named '{builder_name}' is registered for section '{section_name}'."
                ) from exc
        return builders


def _build_intro_section(composer: Any, context: NotebookComposerContext) -> list[CellSpec]:
    return composer._create_intro_cells(
        context.notebook_plan,
        context.architecture.get("justification"),
        context.workflow_design.get("graph_exports"),
    )


def _build_install_section(
    composer: Any, context: NotebookComposerContext
) -> list[CellSpec]:
    return composer._create_install_cells(context.dependency_plan)


def _build_config_section(
    composer: Any, context: NotebookComposerContext
) -> list[CellSpec]:
    return composer._create_config_cells(context.dependency_plan, context.feedback)


def _build_state_section(composer: Any, context: NotebookComposerContext) -> list[CellSpec]:
    return composer._create_state_cells(context.workflow_design)


async def _build_tools_section(
    composer: Any,
    context: NotebookComposerContext,
) -> list[CellSpec]:
    warning_cells = composer._create_tool_planning_warning_cells(
        context.tool_planning_feedback
    )
    runnable_tools = [
        tool
        for tool in context.tools
        if str(tool.get("status", "ready")).strip().lower() != "unsupported"
    ]
    if not runnable_tools:
        return warning_cells
    tool_cells = await composer._create_tool_cells(runnable_tools, context.feedback)
    return [*warning_cells, *tool_cells]


async def _build_nodes_section(
    composer: Any,
    context: NotebookComposerContext,
) -> list[CellSpec]:
    return await composer._create_node_cells(
        context.workflow_design,
        context.feedback,
        tools=context.tools,
    )


async def _build_router_nodes_section(
    composer: Any,
    context: NotebookComposerContext,
) -> list[CellSpec]:
    return composer._create_pattern_node_cells(
        context.workflow_design.get("nodes", []),
        "router",
        context.workflow_design,
        tools=context.tools,
    )


async def _build_subagents_nodes_section(
    composer: Any,
    context: NotebookComposerContext,
) -> list[CellSpec]:
    return composer._create_pattern_node_cells(
        context.workflow_design.get("nodes", []),
        "subagents",
        context.workflow_design,
        tools=context.tools,
    )


async def _build_hybrid_nodes_section(
    composer: Any,
    context: NotebookComposerContext,
) -> list[CellSpec]:
    return composer._create_pattern_node_cells(
        context.workflow_design.get("nodes", []),
        "hybrid",
        context.workflow_design,
        tools=context.tools,
    )


async def _build_autoagent_nodes_section(
    composer: Any,
    context: NotebookComposerContext,
) -> list[CellSpec]:
    return composer._create_pattern_node_cells(
        context.workflow_design.get("nodes", []),
        "autoagent",
        context.workflow_design,
        tools=context.tools,
    )


async def _build_deepagents_nodes_section(
    composer: Any,
    context: NotebookComposerContext,
) -> list[CellSpec]:
    return composer._create_pattern_node_cells(
        context.workflow_design.get("nodes", []),
        "deepagents",
        context.workflow_design,
        tools=context.tools,
    )


async def _build_critique_loop_nodes_section(
    composer: Any,
    context: NotebookComposerContext,
) -> list[CellSpec]:
    return composer._create_pattern_node_cells(
        context.workflow_design.get("nodes", []),
        "critique_loop",
        context.workflow_design,
        tools=context.tools,
    )


def _build_graph_section(composer: Any, context: NotebookComposerContext) -> list[CellSpec]:
    return composer._create_graph_cells(
        context.workflow_design,
        context.feedback.resolved_max_iterations or 1,
    )


def _build_router_graph_section(
    composer: Any,
    context: NotebookComposerContext,
) -> list[CellSpec]:
    return composer._create_graph_cells(
        context.workflow_design,
        context.feedback.resolved_max_iterations or 1,
    )


def _build_subagents_graph_section(
    composer: Any,
    context: NotebookComposerContext,
) -> list[CellSpec]:
    return composer._create_graph_cells(
        context.workflow_design,
        context.feedback.resolved_max_iterations or 1,
    )


def _build_hybrid_graph_section(
    composer: Any,
    context: NotebookComposerContext,
) -> list[CellSpec]:
    return composer._create_graph_cells(
        context.workflow_design,
        context.feedback.resolved_max_iterations or 1,
    )


def _build_autoagent_graph_section(
    composer: Any,
    context: NotebookComposerContext,
) -> list[CellSpec]:
    return composer._create_graph_cells(
        context.workflow_design,
        context.feedback.resolved_max_iterations or 1,
    )


def _build_deepagents_graph_section(
    composer: Any,
    context: NotebookComposerContext,
) -> list[CellSpec]:
    return composer._create_graph_cells(
        context.workflow_design,
        context.feedback.resolved_max_iterations or 1,
    )


def _build_critique_loop_graph_section(
    composer: Any,
    context: NotebookComposerContext,
) -> list[CellSpec]:
    return composer._create_graph_cells(
        context.workflow_design,
        context.feedback.resolved_max_iterations or 1,
    )


def _build_execution_section(
    composer: Any,
    context: NotebookComposerContext,
) -> list[CellSpec]:
    return composer._create_execution_cells(
        context.workflow_design,
        notebook_plan=context.notebook_plan,
    )


def _load_plugin_modules(registry: NotebookComposerRegistry) -> None:
    """Load configured notebook-composer plugin modules."""

    for module_name in settings.notebook_composer_plugin_modules:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            raise ValueError(
                f"Failed to import notebook composer plugin module '{module_name}': "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        hook = getattr(module, "register_notebook_composer_builders", None)
        if not callable(hook):
            raise ValueError(
                f"Notebook composer plugin module '{module_name}' must define a callable "
                "'register_notebook_composer_builders(registry)'."
            )
        hook(registry)


@lru_cache(maxsize=1)
def get_notebook_composer_registry() -> NotebookComposerRegistry:
    """Return the shared notebook-composer registry with built-ins and plugins."""

    registry = NotebookComposerRegistry()
    registry.register_builder("intro", _build_intro_section)
    registry.register_builder("install", _build_install_section)
    registry.register_builder("config", _build_config_section)
    registry.register_builder("state", _build_state_section)
    registry.register_builder("tools", _build_tools_section)
    registry.register_builder("nodes", _build_nodes_section)
    registry.register_builder("graph", _build_graph_section)
    registry.register_builder("execution", _build_execution_section)

    registry.register_builder("router_nodes", _build_router_nodes_section)
    registry.register_builder("subagents_nodes", _build_subagents_nodes_section)
    registry.register_builder("hybrid_nodes", _build_hybrid_nodes_section)
    registry.register_builder("autoagent_nodes", _build_autoagent_nodes_section)
    registry.register_builder("deepagents_nodes", _build_deepagents_nodes_section)
    registry.register_builder("critique_loop_nodes", _build_critique_loop_nodes_section)

    registry.register_builder("router_graph", _build_router_graph_section)
    registry.register_builder("subagents_graph", _build_subagents_graph_section)
    registry.register_builder("hybrid_graph", _build_hybrid_graph_section)
    registry.register_builder("autoagent_graph", _build_autoagent_graph_section)
    registry.register_builder("deepagents_graph", _build_deepagents_graph_section)
    registry.register_builder(
        "critique_loop_graph",
        _build_critique_loop_graph_section,
    )

    for architecture_id, node_builder, graph_builder in [
        ("router", "router_nodes", "router_graph"),
        ("subagents", "subagents_nodes", "subagents_graph"),
        ("hybrid", "hybrid_nodes", "hybrid_graph"),
        ("autoagent", "autoagent_nodes", "autoagent_graph"),
        ("deepagents", "deepagents_nodes", "deepagents_graph"),
        ("critique_loop", "critique_loop_nodes", "critique_loop_graph"),
    ]:
        registry.register(
            NotebookComposerArchitectureRegistration(
                architecture_id=architecture_id,
                section_overrides={
                    "nodes": node_builder,
                    "graph": graph_builder,
                },
            )
        )

    _load_plugin_modules(registry)
    return registry
