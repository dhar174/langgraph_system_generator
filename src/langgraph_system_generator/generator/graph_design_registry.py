"""Registry, normalization, validation, and exports for graph design."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import importlib
import re
from typing import Any, Callable, Iterable, Mapping

from langgraph_system_generator.generator.state import (
    GraphConditionalEdgeSpec,
    GraphDesignResult,
    GraphEdgeSpec,
    GraphExportBundle,
    GraphNodeSpec,
    GraphValidationIssue,
)
from langgraph_system_generator.utils.config import settings

END_TARGETS = {"END", "__end__"}
PluginHook = Callable[["GraphDesignRegistry"], None]
FallbackBuilder = Callable[..., dict[str, Any]]
NormalizationHook = Callable[[GraphDesignResult], GraphDesignResult]
ValidationHook = Callable[[GraphDesignResult], list[GraphValidationIssue]]


def _normalize_architecture_id(value: str) -> str:
    """Return a normalized architecture identifier."""

    normalized = str(value or "").strip().lower()
    if not normalized:
        raise ValueError(
            "Graph design registrations must include a non-empty architecture_id."
        )
    return normalized


def _normalize_string_list(values: Iterable[str] | None) -> list[str]:
    """Return an ordered, de-duplicated list of non-empty strings."""

    normalized_values: list[str] = []
    for raw_value in values or []:
        normalized = str(raw_value or "").strip()
        if normalized and normalized not in normalized_values:
            normalized_values.append(normalized)
    return normalized_values


def _normalize_mapping(values: Mapping[str, Any] | None) -> dict[str, str]:
    """Return a stringified mapping with trimmed keys and values."""

    normalized: dict[str, str] = {}
    for raw_key, raw_value in (values or {}).items():
        key = str(raw_key or "").strip()
        value = str(raw_value or "").strip()
        if key:
            normalized[key] = value
    return normalized


def _mermaid_id(value: str) -> str:
    """Return a Mermaid-safe identifier derived from a node id."""

    slug = re.sub(r"[^a-zA-Z0-9_]", "_", str(value or "").strip())
    slug = re.sub(r"_+", "_", slug).strip("_")
    if not slug:
        slug = "node"
    if slug[0].isdigit():
        slug = f"n_{slug}"
    return slug


def _issue(
    code: str,
    message: str,
    *,
    severity: str = "error",
    nodes: Iterable[str] | None = None,
) -> GraphValidationIssue:
    """Create a normalized validation issue."""

    return GraphValidationIssue(
        code=code,
        message=message,
        severity="warning" if severity == "warning" else "error",
        nodes=[str(node) for node in nodes or [] if str(node or "").strip()],
    )


def _build_router_fallback(*_args, **_kwargs) -> dict[str, Any]:
    """Return the deterministic fallback router design."""

    return {
        "state_schema": {
            "messages": "List of messages",
            "route": "Selected route",
            "results": "Outputs grouped by direct specialist",
            "final_output": "Final synthesized answer",
        },
        "nodes": [
            {"name": "router", "purpose": "Route the request to the best specialist"},
            {
                "name": "specialist_1",
                "purpose": "Handle the first specialist pathway directly",
            },
            {
                "name": "specialist_2",
                "purpose": "Handle the second specialist pathway directly",
            },
        ],
        "edges": [],
        "conditional_edges": [
            {
                "from": "router",
                "condition": "Dispatch by selected route",
                "branches": {
                    "specialist_1": "specialist_1",
                    "specialist_2": "specialist_2",
                },
            }
        ],
        "entry_point": "router",
        "checkpointing": False,
    }


def _build_supervisor_fallback(
    *,
    coordinator_name: str,
    worker_names: list[str],
    state_schema: Mapping[str, str],
) -> dict[str, Any]:
    """Return a deterministic coordinator-plus-workers design."""

    return {
        "state_schema": dict(state_schema),
        "nodes": [
            {
                "name": coordinator_name,
                "purpose": "Coordinate worker delegation and synthesis",
            },
            *[
                {
                    "name": worker_name,
                    "purpose": f"{worker_name.title()} specialist worker",
                }
                for worker_name in worker_names
            ],
        ],
        "edges": [],
        "conditional_edges": [
            {
                "from": coordinator_name,
                "condition": "Route to the next worker or finish once synthesis is complete",
                "branches": {
                    **{worker_name: worker_name for worker_name in worker_names},
                    "FINISH": "END",
                },
            }
        ],
        "entry_point": coordinator_name,
        "checkpointing": True,
    }


def _build_subagents_fallback(*_args, **_kwargs) -> dict[str, Any]:
    """Return the deterministic fallback subagents design."""

    return _build_supervisor_fallback(
        coordinator_name="supervisor",
        worker_names=["planner", "executor", "critic"],
        state_schema={
            "messages": "List of messages",
            "next_agent": "Next worker to call",
            "instructions": "Supervisor guidance for the selected worker",
            "task_results": "Merged worker outputs",
            "dispatch_log": "History of dispatched workers",
            "iterations": "Current supervisor iteration count",
        },
    )


def _build_autoagent_fallback(*_args, **_kwargs) -> dict[str, Any]:
    """Return the deterministic fallback autoagent design."""

    return _build_supervisor_fallback(
        coordinator_name="coordinator",
        worker_names=["planner", "executor", "critic"],
        state_schema={
            "messages": "List of messages",
            "next_agent": "Next worker to call",
            "instructions": "Coordinator guidance for the selected worker",
            "task_results": "Merged worker outputs",
            "dispatch_log": "History of dispatched workers",
            "iterations": "Current coordinator iteration count",
        },
    )


def _build_hybrid_fallback(*_args, **_kwargs) -> dict[str, Any]:
    """Return the deterministic fallback hybrid design."""

    return {
        "state_schema": {
            "messages": "List of messages",
            "route": "Selected router branch",
            "results": "Outputs grouped by direct specialist",
            "next_agent": "Next worker to call when the team path is chosen",
            "instructions": "Supervisor guidance for the selected worker",
            "task_results": "Worker-team outputs",
            "dispatch_log": "History of direct and team path routing",
            "iterations": "Current supervisor iteration count",
            "final_output": "Final synthesized answer",
        },
        "nodes": [
            {
                "name": "router",
                "purpose": "Route to a direct specialist or the supervisor-led team path",
            },
            {
                "name": "specialist_1",
                "purpose": "Handle direct specialist work without team coordination",
            },
            {
                "name": "supervisor",
                "purpose": "Coordinate the worker team when deeper collaboration is needed",
            },
            {
                "name": "researcher",
                "purpose": "Gather supporting facts and intermediate context",
            },
            {
                "name": "reviewer",
                "purpose": "Review worker output before the final synthesis",
            },
            {
                "name": "finish",
                "purpose": "Synthesize final results from both direct and team branches",
            },
        ],
        "edges": [
            {"from": "specialist_1", "to": "finish"},
            {"from": "researcher", "to": "supervisor"},
            {"from": "reviewer", "to": "supervisor"},
        ],
        "conditional_edges": [
            {
                "from": "router",
                "condition": "Route to a direct specialist or the worker team",
                "branches": {
                    "specialist_1": "specialist_1",
                    "team_path": "supervisor",
                },
            },
            {
                "from": "supervisor",
                "condition": "Route to the next worker or finish after synthesis",
                "branches": {
                    "researcher": "researcher",
                    "reviewer": "reviewer",
                    "FINISH": "finish",
                },
            },
        ],
        "entry_point": "router",
        "checkpointing": True,
    }


@dataclass(frozen=True)
class GraphDesignRegistration:
    """Metadata describing a supported graph design architecture."""

    architecture_id: str
    supported_entry_shapes: list[str] = field(default_factory=list)
    supported_exit_shapes: list[str] = field(default_factory=list)
    cycles_allowed: bool = False
    fallback_builder: FallbackBuilder = _build_router_fallback
    normalization_hook: NormalizationHook | None = None
    validation_hook: ValidationHook | None = None
    export_label_defaults: dict[str, str] = field(default_factory=dict)
    composition_strategy: str = "deterministic"

    def normalized(self) -> "GraphDesignRegistration":
        """Return a normalized copy suitable for registry storage."""

        architecture_id = _normalize_architecture_id(self.architecture_id)
        if not callable(self.fallback_builder):
            raise ValueError(
                f"Graph design registration '{architecture_id}' must include a callable fallback_builder."
            )
        composition_strategy = str(self.composition_strategy or "").strip()
        if not composition_strategy:
            raise ValueError(
                f"Graph design registration '{architecture_id}' must include a composition_strategy."
            )
        return GraphDesignRegistration(
            architecture_id=architecture_id,
            supported_entry_shapes=_normalize_string_list(self.supported_entry_shapes),
            supported_exit_shapes=_normalize_string_list(self.supported_exit_shapes),
            cycles_allowed=bool(self.cycles_allowed),
            fallback_builder=self.fallback_builder,
            normalization_hook=self.normalization_hook,
            validation_hook=self.validation_hook,
            export_label_defaults={
                str(key).strip(): str(value).strip()
                for key, value in (self.export_label_defaults or {}).items()
                if str(key).strip()
            },
            composition_strategy=composition_strategy,
        )


class GraphDesignRegistry:
    """Mutable in-memory registry for graph design architectures."""

    def __init__(self, registrations: Iterable[GraphDesignRegistration] | None = None):
        self._registrations: dict[str, GraphDesignRegistration] = {}
        for registration in registrations or []:
            self.register(registration)

    def clone(self) -> "GraphDesignRegistry":
        """Return a shallow copy of the registry."""

        return GraphDesignRegistry(self._registrations.values())

    def register(self, registration: GraphDesignRegistration) -> GraphDesignRegistration:
        """Register or replace a graph design entry."""

        normalized = registration.normalized()
        self._registrations[normalized.architecture_id] = normalized
        return normalized

    def get(self, architecture_id: str) -> GraphDesignRegistration:
        """Return a registered graph design entry."""

        return self._registrations[_normalize_architecture_id(architecture_id)]

    def supported_architecture_types(self) -> list[str]:
        """Return registered architecture identifiers in insertion order."""

        return list(self._registrations.keys())


def normalize_graph_design(
    payload: Mapping[str, Any] | GraphDesignResult,
    architecture_type: str,
    registration: GraphDesignRegistration,
) -> GraphDesignResult:
    """Normalize arbitrary graph-design payloads into typed output."""

    if isinstance(payload, GraphDesignResult):
        result = payload.model_copy(
            update={"architecture_type": _normalize_architecture_id(architecture_type)}
        )
    else:
        state_schema = _normalize_mapping(payload.get("state_schema"))
        nodes = [
            GraphNodeSpec(
                name=str(node.get("name", "")).strip(),
                purpose=str(
                    node.get("purpose", "")
                    or f"Handle {str(node.get('name', '')).strip()} work."
                ).strip(),
            )
            for node in list(payload.get("nodes") or [])
            if str(node.get("name", "")).strip()
        ]
        edges = [
            GraphEdgeSpec.model_validate(edge)
            for edge in list(payload.get("edges") or [])
        ]
        conditional_edges = [
            GraphConditionalEdgeSpec.model_validate(edge)
            for edge in list(payload.get("conditional_edges") or [])
        ]
        result = GraphDesignResult(
            architecture_type=_normalize_architecture_id(architecture_type),
            state_schema=state_schema,
            nodes=nodes,
            edges=edges,
            conditional_edges=conditional_edges,
            entry_point=str(payload.get("entry_point", "")).strip(),
            checkpointing=bool(payload.get("checkpointing", False)),
        )

    if registration.normalization_hook:
        result = registration.normalization_hook(result)

    return result.model_copy(
        update={"architecture_type": _normalize_architecture_id(result.architecture_type)}
    )


def _adjacency_map(result: GraphDesignResult) -> dict[str, set[str]]:
    """Return adjacency among real node ids, excluding END targets."""

    adjacency: dict[str, set[str]] = {node.name: set() for node in result.nodes}
    for edge in result.edges:
        if edge.source in adjacency and edge.target in adjacency:
            adjacency[edge.source].add(edge.target)
    for conditional_edge in result.conditional_edges:
        if conditional_edge.source not in adjacency:
            continue
        for target in conditional_edge.branches.values():
            if target not in END_TARGETS and target in adjacency:
                adjacency[conditional_edge.source].add(target)
    return adjacency


def _reachable_nodes(result: GraphDesignResult) -> set[str]:
    """Return node ids reachable from the entry point."""

    if not result.entry_point:
        return set()

    adjacency = _adjacency_map(result)
    if result.entry_point not in adjacency:
        return set()

    seen: set[str] = set()
    queue = [result.entry_point]
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        queue.extend(
            target for target in adjacency.get(current, set()) if target not in seen
        )
    return seen


def terminal_nodes_for(result: GraphDesignResult) -> list[str]:
    """Return normalized terminal node ids for the workflow."""

    adjacency = _adjacency_map(result)
    conditional_end_sources = {
        conditional_edge.source
        for conditional_edge in result.conditional_edges
        if any(target in END_TARGETS for target in conditional_edge.branches.values())
    }
    terminal_nodes: list[str] = []
    for node in result.nodes:
        if not adjacency.get(node.name) or node.name in conditional_end_sources:
            if node.name not in terminal_nodes:
                terminal_nodes.append(node.name)
    return terminal_nodes


def _detect_cycle(adjacency: Mapping[str, set[str]]) -> bool:
    """Return True when the graph contains a cycle."""

    visiting: set[str] = set()
    visited: set[str] = set()

    def _visit(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        for target in adjacency.get(node_id, set()):
            if _visit(target):
                return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    return any(_visit(node_id) for node_id in adjacency)


def validate_graph_design(
    result: GraphDesignResult,
    registration: GraphDesignRegistration,
) -> list[GraphValidationIssue]:
    """Validate a normalized graph design and return structured issues."""

    issues: list[GraphValidationIssue] = []
    node_names = [node.name for node in result.nodes]
    node_id_set = set(node_names)

    if not result.entry_point:
        issues.append(
            _issue(
                "missing_entry_point",
                "Graph design must include a non-empty entry_point.",
            )
        )
    elif result.entry_point not in node_id_set:
        issues.append(
            _issue(
                "missing_entry_point",
                f"Entry point '{result.entry_point}' does not match any declared node.",
                nodes=[result.entry_point],
            )
        )

    duplicate_node_ids = sorted(
        {node_name for node_name in node_names if node_names.count(node_name) > 1}
    )
    for node_id in duplicate_node_ids:
        issues.append(
            _issue(
                "duplicate_node_id",
                f"Duplicate node id '{node_id}'.",
                nodes=[node_id],
            )
        )

    incoming_counts = {node_id: 0 for node_id in node_id_set}
    for edge in result.edges:
        if edge.source not in node_id_set:
            issues.append(
                _issue(
                    "unknown_edge_source",
                    f"Unknown edge source '{edge.source}'.",
                    nodes=[edge.source],
                )
            )
        if edge.target not in node_id_set:
            issues.append(
                _issue(
                    "unknown_edge_target",
                    f"Unknown edge target '{edge.target}'.",
                    nodes=[edge.target],
                )
            )
        if edge.target in incoming_counts:
            incoming_counts[edge.target] += 1

    for conditional_edge in result.conditional_edges:
        if conditional_edge.source not in node_id_set:
            issues.append(
                _issue(
                    "unknown_branch_source",
                    f"Unknown conditional edge source '{conditional_edge.source}'.",
                    nodes=[conditional_edge.source],
                )
            )
        for branch_label, target in conditional_edge.branches.items():
            if target in END_TARGETS:
                continue
            if target not in node_id_set:
                issues.append(
                    _issue(
                        "unknown_branch_target",
                        f"Unknown edge target '{target}' for branch '{branch_label}'.",
                        nodes=[target],
                    )
                )
            elif target in incoming_counts:
                incoming_counts[target] += 1

    adjacency = _adjacency_map(result)
    reachable = _reachable_nodes(result)
    for node in result.nodes:
        if node.name == result.entry_point:
            continue
        if incoming_counts.get(node.name, 0) == 0:
            issues.append(
                _issue(
                    "orphan_node",
                    f"Node '{node.name}' has no inbound edges or branches.",
                    severity="warning",
                    nodes=[node.name],
                )
            )
        if node.name not in reachable:
            issues.append(
                _issue(
                    "unreachable_node",
                    f"Node '{node.name}' is unreachable from entry point '{result.entry_point}'.",
                    severity="warning",
                    nodes=[node.name],
                )
            )

    reachable_terminals = [
        node_id for node_id in terminal_nodes_for(result) if node_id in reachable
    ]
    if not reachable_terminals:
        issues.append(
            _issue(
                "missing_terminal_path",
                "Graph design does not contain a reachable terminal path.",
            )
        )

    if not registration.cycles_allowed and _detect_cycle(adjacency):
        issues.append(
            _issue(
                "cycle_detected",
                (
                    f"Graph design for architecture '{registration.architecture_id}' "
                    "contains a cycle, but this architecture does not allow cycles."
                ),
            )
        )

    if registration.validation_hook:
        issues.extend(registration.validation_hook(result))

    return issues


def build_graph_exports(
    result: GraphDesignResult,
    registration: GraphDesignRegistration,
    issues: Iterable[GraphValidationIssue] | None = None,
    warnings: Iterable[str] | None = None,
) -> GraphExportBundle:
    """Build Mermaid and JSON-schema exports for a graph design."""

    issue_list = list(issues or [])
    warning_messages = list(warnings or [])
    error_messages = [
        issue.message for issue in issue_list if issue.severity == "error"
    ]
    warning_messages.extend(
        issue.message
        for issue in issue_list
        if issue.severity == "warning" and issue.message not in warning_messages
    )

    mermaid_lines = ["flowchart TD", f"    START([START]) --> {_mermaid_id(result.entry_point)}"]
    for node in result.nodes:
        mermaid_lines.append(
            f'    {_mermaid_id(node.name)}["{node.name}: {node.purpose}"]'
        )
    for edge in result.edges:
        mermaid_lines.append(
            f"    {_mermaid_id(edge.source)} --> {_mermaid_id(edge.target)}"
        )
    for conditional_edge in result.conditional_edges:
        for branch_label, target in conditional_edge.branches.items():
            target_id = "END" if target in END_TARGETS else _mermaid_id(target)
            mermaid_lines.append(
                f'    {_mermaid_id(conditional_edge.source)} -- "{branch_label}" --> {target_id}'
            )
    mermaid_lines.append("    END([END])")

    schema = {
        "architecture_type": result.architecture_type,
        "composition_strategy": registration.composition_strategy,
        "labels": dict(registration.export_label_defaults),
        "state_schema": dict(result.state_schema),
        "nodes": [node.model_dump() for node in result.nodes],
        "edges": [edge.model_dump(by_alias=True) for edge in result.edges],
        "conditional_edges": [
            edge.model_dump(by_alias=True) for edge in result.conditional_edges
        ],
        "entry_point": result.entry_point,
        "checkpointing": result.checkpointing,
        "terminal_nodes": terminal_nodes_for(result),
        "validation_summary": {
            "errors": error_messages,
            "warnings": warning_messages,
        },
    }

    return GraphExportBundle(mermaid="\n".join(mermaid_lines), schema=schema)


def _default_registrations() -> list[GraphDesignRegistration]:
    """Return the built-in graph design catalog."""

    return [
        GraphDesignRegistration(
            architecture_id="router",
            supported_entry_shapes=["router"],
            supported_exit_shapes=["terminal"],
            cycles_allowed=False,
            fallback_builder=_build_router_fallback,
            export_label_defaults={"title": "Router Workflow"},
            composition_strategy="router_direct",
        ),
        GraphDesignRegistration(
            architecture_id="subagents",
            supported_entry_shapes=["supervisor"],
            supported_exit_shapes=["supervisor_end"],
            cycles_allowed=False,
            fallback_builder=_build_subagents_fallback,
            export_label_defaults={"title": "Supervisor Team Workflow"},
            composition_strategy="supervisor_team",
        ),
        GraphDesignRegistration(
            architecture_id="hybrid",
            supported_entry_shapes=["router"],
            supported_exit_shapes=["finish"],
            cycles_allowed=False,
            fallback_builder=_build_hybrid_fallback,
            export_label_defaults={"title": "Hybrid Workflow"},
            composition_strategy="router_plus_team",
        ),
        GraphDesignRegistration(
            architecture_id="autoagent",
            supported_entry_shapes=["coordinator"],
            supported_exit_shapes=["coordinator_end"],
            cycles_allowed=False,
            fallback_builder=_build_autoagent_fallback,
            export_label_defaults={"title": "AutoAgent Workflow"},
            composition_strategy="coordinator_team",
        ),
    ]


def _normalize_plugin_modules(plugin_modules: Iterable[str] | None) -> tuple[str, ...]:
    """Return normalized plugin module paths for cache keys and loading."""

    normalized: list[str] = []
    for raw_value in plugin_modules or []:
        module_name = str(raw_value or "").strip()
        if module_name and module_name not in normalized:
            normalized.append(module_name)
    return tuple(normalized)


def _load_plugin_modules(
    registry: GraphDesignRegistry,
    plugin_modules: tuple[str, ...],
) -> GraphDesignRegistry:
    """Load plugin registrations into a cloned registry."""

    for module_name in plugin_modules:
        module = importlib.import_module(module_name)
        register = getattr(module, "register_graph_designers", None)
        if not callable(register):
            raise ValueError(
                f"Graph design plugin module '{module_name}' must define register_graph_designers(registry)."
            )
        hook: PluginHook = register
        hook(registry)
    return registry


@lru_cache(maxsize=16)
def get_graph_design_registry(
    plugin_modules: tuple[str, ...] | None = None,
) -> GraphDesignRegistry:
    """Return the built-in graph design registry with optional plugin extensions."""

    normalized_modules = _normalize_plugin_modules(
        settings.graph_designer_plugin_modules
        if plugin_modules is None
        else plugin_modules
    )
    registry = GraphDesignRegistry(_default_registrations())
    if normalized_modules:
        registry = _load_plugin_modules(registry, normalized_modules)
    return registry


def graph_design_issue_messages(
    issues: Iterable[GraphValidationIssue],
    *,
    severity: str | None = None,
) -> list[str]:
    """Return validation issue messages filtered by severity when requested."""

    normalized_severity = severity if severity in {"error", "warning"} else None
    messages: list[str] = []
    for issue in issues:
        if normalized_severity and issue.severity != normalized_severity:
            continue
        if issue.message not in messages:
            messages.append(issue.message)
    return messages
