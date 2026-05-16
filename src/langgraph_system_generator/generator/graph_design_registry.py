"""Registry, normalization, validation, and exports for graph design."""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from functools import lru_cache
import importlib
import re
from typing import Any, Callable, Iterable, Mapping

from langgraph_system_generator.generator.state import (
    Constraint,
    GraphCommandRouteSpec,
    GraphConditionalEdgeSpec,
    GraphDesignResult,
    GraphEdgeSpec,
    GraphExportBundle,
    GraphNodeSpec,
    GraphToolReachabilitySpec,
    GraphValidationIssue,
)
from langgraph_system_generator.utils.config import settings

END_TARGETS = {"END", "__end__"}
_DOMAIN_STOPWORDS = {
    "a",
    "about",
    "agent",
    "agents",
    "ai",
    "and",
    "app",
    "build",
    "create",
    "for",
    "from",
    "generate",
    "graph",
    "help",
    "into",
    "langgraph",
    "make",
    "notebook",
    "of",
    "or",
    "please",
    "system",
    "task",
    "that",
    "the",
    "to",
    "tool",
    "tools",
    "turn",
    "use",
    "user",
    "with",
    "workflow",
}
_DOMAIN_ROLE_PRESETS: tuple[tuple[set[str], list[str], list[str]], ...] = (
    (
        {"museum", "artifact", "artifacts", "catalog", "cataloging", "archive"},
        ["artifact_cataloger", "metadata_validator"],
        ["provenance_researcher", "collection_reviewer"],
    ),
    (
        {"incident", "sre", "outage", "alert", "alerts", "remediation"},
        ["incident_triage", "impact_assessor"],
        ["remediation_planner", "postmortem_reviewer"],
    ),
    (
        {"support", "customer", "ticket", "escalation", "case"},
        ["support_triage", "account_researcher"],
        ["resolution_specialist", "quality_reviewer"],
    ),
    (
        {"research", "report", "synthesis", "sources", "literature"},
        ["source_researcher", "evidence_synthesizer"],
        ["outline_planner", "citation_reviewer"],
    ),
    (
        {"data", "validation", "catalog", "dataset", "schema"},
        ["data_validator", "catalog_reconciler"],
        ["schema_reviewer", "quality_auditor"],
    ),
)
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


def _constraint_text(constraints: Iterable[Constraint] | None) -> str:
    """Return joined user-facing constraint text for deterministic fallbacks."""

    return " ".join(str(getattr(constraint, "value", constraint) or "") for constraint in constraints or [])


def _slug_token(value: str) -> str:
    """Return a short snake-case token suitable for node ids."""

    token = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return re.sub(r"_+", "_", token)


def _domain_terms_from_constraints(constraints: Iterable[Constraint] | None) -> list[str]:
    """Extract compact request-domain terms without live model calls."""

    text = _constraint_text(constraints)
    terms: list[str] = []
    for raw_token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text):
        token = _slug_token(raw_token)
        if (
            not token
            or token in _DOMAIN_STOPWORDS
            or token.isdigit()
            or token in terms
        ):
            continue
        terms.append(token)
        if len(terms) >= 6:
            break
    return terms


def _domain_roles_from_terms(domain_terms: list[str]) -> tuple[list[str], list[str]]:
    """Return direct and team role node ids for a request domain."""

    term_set = set(domain_terms)
    for preset_terms, direct_roles, team_roles in _DOMAIN_ROLE_PRESETS:
        if term_set & preset_terms:
            return list(direct_roles), list(team_roles)

    if not domain_terms:
        return [], []

    primary = domain_terms[0]
    secondary = domain_terms[1] if len(domain_terms) > 1 else primary
    return [f"{primary}_analyst", f"{secondary}_reviewer"], [
        f"{primary}_planner",
        f"{secondary}_qa",
    ]


def _domain_profile(
    constraints: Iterable[Constraint] | None,
) -> tuple[list[str], list[str], list[str]]:
    """Return domain terms plus direct/team roles for deterministic fallbacks."""

    domain_terms = _domain_terms_from_constraints(constraints)
    direct_roles, team_roles = _domain_roles_from_terms(domain_terms)
    return domain_terms, direct_roles, team_roles


def domain_terms_for_constraints(constraints: Iterable[Constraint] | None) -> list[str]:
    """Return deterministic request-domain terms for graph metadata."""

    return _domain_terms_from_constraints(constraints)


def _node(
    name: str,
    purpose: str,
    *,
    role: str | None = None,
    domain_terms: list[str] | None = None,
    required_tools: list[str] | None = None,
) -> dict[str, Any]:
    """Build a normalized node payload with optional graph-spec metadata."""

    payload: dict[str, Any] = {"name": name, "purpose": purpose}
    if role:
        payload["role"] = role
    if domain_terms:
        payload["domain_terms"] = domain_terms
    if required_tools:
        payload["required_tools"] = required_tools
    return payload


def _mermaid_id(value: str) -> str:
    """Return a Mermaid-safe identifier derived from a node id."""

    slug = re.sub(r"[^a-zA-Z0-9_]", "_", str(value or "").strip())
    slug = re.sub(r"_+", "_", slug).strip("_")
    if not slug:
        slug = "node"
    if slug[0].isdigit():
        slug = f"n_{slug}"
    return slug


def _mermaid_label(value: str) -> str:
    """Return Mermaid-safe label text for node and edge annotations."""

    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("[", "&#91;")
        .replace("]", "&#93;")
        .replace("{", "&#123;")
        .replace("}", "&#125;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )


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


def _build_router_fallback(*_args, **kwargs) -> dict[str, Any]:
    """Return the deterministic fallback router design."""

    domain_terms, direct_roles, _team_roles = _domain_profile(kwargs.get("constraints"))
    specialist_roles = direct_roles or ["specialist_1", "specialist_2"]
    branch_map = {role: role for role in specialist_roles}
    return {
        "state_schema": {
            "messages": "List of messages",
            "route": "Selected route",
            "route_reasoning": "Reason for the selected route",
            "route_history": "Ordered route decisions made by the router",
            "results": "Outputs grouped by direct specialist",
            "final_output": "Final synthesized answer",
        },
        "nodes": [
            _node(
                "router",
                "Route the request to the best domain specialist",
                role="router",
                domain_terms=domain_terms,
            ),
            *[
                _node(
                    role,
                    f"Handle {role.replace('_', ' ')} work directly",
                    role="direct_specialist",
                    domain_terms=domain_terms,
                )
                for role in specialist_roles
            ],
        ],
        "edges": [],
        "conditional_edges": [
            {
                "from": "router",
                "condition": "Dispatch by selected route",
                "branches": branch_map,
                "routing_mechanism": "conditional_edge",
            }
        ],
        "domain_terms": domain_terms,
        "entry_point": "router",
        "compiled_graph_variable": "graph",
        "checkpointing": False,
    }


def _build_supervisor_fallback(
    *,
    coordinator_name: str,
    worker_names: list[str],
    state_schema: Mapping[str, str],
    domain_terms: list[str] | None = None,
) -> dict[str, Any]:
    """Return a deterministic coordinator-plus-workers design."""

    return {
        "state_schema": dict(state_schema),
        "nodes": [
            _node(
                coordinator_name,
                "Coordinate worker delegation and synthesis",
                role="coordinator",
                domain_terms=domain_terms,
            ),
            *[
                _node(
                    worker_name,
                    f"{worker_name.replace('_', ' ').title()} specialist worker",
                    role="worker",
                    domain_terms=domain_terms,
                )
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
                "routing_mechanism": "conditional_edge",
            }
        ],
        "domain_terms": domain_terms or [],
        "entry_point": coordinator_name,
        "compiled_graph_variable": "graph",
        "checkpointing": True,
    }


def _build_subagents_fallback(*_args, **kwargs) -> dict[str, Any]:
    """Return the deterministic fallback subagents design."""

    domain_terms, _direct_roles, team_roles = _domain_profile(kwargs.get("constraints"))
    worker_names = team_roles or ["planner", "executor", "critic"]
    return _build_supervisor_fallback(
        coordinator_name="supervisor",
        worker_names=worker_names,
        state_schema={
            "messages": "List of messages",
            "next_agent": "Next worker to call",
            "instructions": "Supervisor guidance for the selected worker",
            "task_results": "Merged worker outputs",
            "dispatch_log": "History of dispatched workers",
            "iterations": "Current supervisor iteration count",
        },
        domain_terms=domain_terms,
    )


def _build_autoagent_fallback(*_args, **kwargs) -> dict[str, Any]:
    """Return the deterministic fallback autoagent design."""

    domain_terms, _direct_roles, team_roles = _domain_profile(kwargs.get("constraints"))
    worker_names = team_roles or ["planner", "executor", "critic"]
    return _build_supervisor_fallback(
        coordinator_name="coordinator",
        worker_names=worker_names,
        state_schema={
            "messages": "List of messages",
            "next_agent": "Next worker to call",
            "instructions": "Coordinator guidance for the selected worker",
            "task_results": "Merged worker outputs",
            "dispatch_log": "History of dispatched workers",
            "iterations": "Current coordinator iteration count",
        },
        domain_terms=domain_terms,
    )


def _build_deepagents_fallback(*_args, **kwargs) -> dict[str, Any]:
    """Return the deterministic fallback Deep Agents design."""

    domain_terms, _direct_roles, _team_roles = _domain_profile(kwargs.get("constraints"))
    return {
        "state_schema": {
            "messages": "List of messages",
            "task_plan": "Planning steps tracked by the Deep Agents harness",
            "artifacts": "Named artifacts or notes produced during execution",
            "subagent_results": "Outputs returned by optional Deep Agents subagents",
            "final_output": "Final synthesized response",
            "deepagents_available": "Whether the optional deepagents SDK was invoked",
        },
        "nodes": [
            _node(
                "deep_agent",
                (
                    "Run the optional Deep Agents harness or a deterministic "
                    "fallback when dependencies or credentials are unavailable"
                ),
                role="deep_agent",
                domain_terms=domain_terms,
            ),
        ],
        "edges": [],
        "conditional_edges": [
            {
                "from": "deep_agent",
                "condition": "Finish once the Deep Agents harness returns a final response",
                "branches": {"complete": "END"},
                "routing_mechanism": "conditional_edge",
            }
        ],
        "domain_terms": domain_terms,
        "entry_point": "deep_agent",
        "compiled_graph_variable": "graph",
        "checkpointing": True,
    }


def _build_hybrid_fallback(*_args, **kwargs) -> dict[str, Any]:
    """Return the deterministic fallback hybrid design."""

    domain_terms, direct_roles, team_roles = _domain_profile(kwargs.get("constraints"))
    direct_roles = direct_roles[:1] or ["specialist_1"]
    team_roles = team_roles[:2] or ["researcher", "reviewer"]
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
            _node(
                "router",
                "Route to a direct specialist or the supervisor-led team path",
                role="router",
                domain_terms=domain_terms,
            ),
            *[
                _node(
                    role,
                    f"Handle {role.replace('_', ' ')} work without team coordination",
                    role="direct_specialist",
                    domain_terms=domain_terms,
                )
                for role in direct_roles
            ],
            _node(
                "supervisor",
                "Coordinate the worker team when deeper collaboration is needed",
                role="coordinator",
                domain_terms=domain_terms,
            ),
            *[
                _node(
                    role,
                    f"Handle {role.replace('_', ' ')} work on the worker team",
                    role="worker",
                    domain_terms=domain_terms,
                )
                for role in team_roles
            ],
            _node(
                "finish",
                "Synthesize final results from both direct and team branches",
                role="synthesizer",
                domain_terms=domain_terms,
            ),
        ],
        "edges": [
            *[{"from": role, "to": "finish"} for role in direct_roles],
            *[{"from": role, "to": "supervisor"} for role in team_roles],
        ],
        "conditional_edges": [
            {
                "from": "router",
                "condition": "Route to a direct specialist or the worker team",
                "branches": {
                    **{role: role for role in direct_roles},
                    "team_path": "supervisor",
                },
                "routing_mechanism": "conditional_edge",
            },
            {
                "from": "supervisor",
                "condition": "Route to the next worker or finish after synthesis",
                "branches": {
                    **{role: role for role in team_roles},
                    "FINISH": "finish",
                },
                "routing_mechanism": "conditional_edge",
                "guarded_cycle": True,
            },
        ],
        "domain_terms": domain_terms,
        "entry_point": "router",
        "compiled_graph_variable": "graph",
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
        nodes = []
        for node in list(payload.get("nodes") or []):
            if not isinstance(node, Mapping):
                continue
            node_name = str(node.get("name", "")).strip()
            if not node_name:
                continue
            nodes.append(
                GraphNodeSpec.model_validate(
                    {
                        **dict(node),
                        "name": node_name,
                        "purpose": str(
                            node.get("purpose", "")
                            or f"Handle {node_name} work."
                        ).strip(),
                        "domain_terms": _normalize_string_list(
                            node.get("domain_terms")
                        ),
                        "required_tools": _normalize_string_list(
                            node.get("required_tools")
                        ),
                    }
                )
            )
        edges = [
            GraphEdgeSpec.model_validate(edge)
            for edge in list(payload.get("edges") or [])
        ]
        conditional_edges = [
            GraphConditionalEdgeSpec.model_validate(edge)
            for edge in list(payload.get("conditional_edges") or [])
        ]
        command_routes = [
            GraphCommandRouteSpec.model_validate(
                {
                    **dict(route),
                    "destinations": _normalize_string_list(route.get("destinations")),
                    "update_fields": _normalize_string_list(route.get("update_fields")),
                }
            )
            for route in list(payload.get("command_routes") or [])
            if isinstance(route, Mapping)
        ]
        tool_reachability = [
            GraphToolReachabilitySpec.model_validate(reachability)
            for reachability in list(payload.get("tool_reachability") or [])
            if isinstance(reachability, Mapping)
        ]
        domain_terms = _normalize_string_list(payload.get("domain_terms"))
        if not domain_terms:
            for node in nodes:
                for domain_term in node.domain_terms:
                    if domain_term not in domain_terms:
                        domain_terms.append(domain_term)
        result = GraphDesignResult(
            architecture_type=_normalize_architecture_id(architecture_type),
            state_schema=state_schema,
            nodes=nodes,
            edges=edges,
            conditional_edges=conditional_edges,
            command_routes=command_routes,
            tool_reachability=tool_reachability,
            domain_terms=domain_terms,
            entry_point=str(payload.get("entry_point", "")).strip(),
            compiled_graph_variable=str(
                payload.get("compiled_graph_variable") or "graph"
            ).strip()
            or "graph",
            checkpointing=bool(payload.get("checkpointing", False)),
        )

    if registration.normalization_hook:
        result = registration.normalization_hook(result)

    return result.model_copy(
        update={"architecture_type": _normalize_architecture_id(result.architecture_type)}
    )


def _adjacency_map(
    result: GraphDesignResult,
    *,
    include_guarded_cycles: bool = True,
) -> dict[str, set[str]]:
    """Return adjacency among real node ids, excluding END targets."""

    adjacency: dict[str, set[str]] = {node.name: set() for node in result.nodes}
    for edge in result.edges:
        if edge.source in adjacency and edge.target in adjacency:
            adjacency[edge.source].add(edge.target)
    for conditional_edge in result.conditional_edges:
        if conditional_edge.source not in adjacency:
            continue
        for target in conditional_edge.branches.values():
            if conditional_edge.guarded_cycle is True and not include_guarded_cycles:
                continue
            if target not in END_TARGETS and target in adjacency:
                adjacency[conditional_edge.source].add(target)
    for command_route in result.command_routes:
        if command_route.source not in adjacency:
            continue
        for target in command_route.destinations:
            if command_route.guarded_cycle is True and not include_guarded_cycles:
                continue
            if target not in END_TARGETS and target in adjacency:
                adjacency[command_route.source].add(target)
    return adjacency


def _reachable_nodes(result: GraphDesignResult) -> set[str]:
    """Return node ids reachable from the entry point."""

    if not result.entry_point:
        return set()

    adjacency = _adjacency_map(result)
    if result.entry_point not in adjacency:
        return set()

    seen: set[str] = set()
    queue = deque([result.entry_point])
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        for target in adjacency.get(current, set()):
            if target not in seen:
                queue.append(target)
    return seen


def terminal_nodes_for(result: GraphDesignResult) -> list[str]:
    """Return normalized terminal node ids for the workflow."""

    adjacency = _adjacency_map(result)
    conditional_end_sources = {
        conditional_edge.source
        for conditional_edge in result.conditional_edges
        if any(target in END_TARGETS for target in conditional_edge.branches.values())
    }
    command_end_sources = {
        command_route.source
        for command_route in result.command_routes
        if any(target in END_TARGETS for target in command_route.destinations)
    }
    terminal_nodes: list[str] = []
    for node in result.nodes:
        if (
            not adjacency.get(node.name)
            or node.name in conditional_end_sources
            or node.name in command_end_sources
        ):
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
    duplicate_counts = Counter(node_names)
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
        node_name for node_name, count in duplicate_counts.items() if count > 1
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

    for command_route in result.command_routes:
        if command_route.source not in node_id_set:
            issues.append(
                _issue(
                    "unknown_command_source",
                    f"Unknown Command route source '{command_route.source}'.",
                    nodes=[command_route.source],
                )
            )
        for target in command_route.destinations:
            if target not in END_TARGETS and target not in node_id_set:
                issues.append(
                    _issue(
                        "unknown_command_target",
                        (
                            f"Unknown Command route target '{target}' from "
                            f"'{command_route.source}'."
                        ),
                        nodes=[command_route.source, target],
                    )
                )
            elif target in incoming_counts:
                incoming_counts[target] += 1

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

    cycle_adjacency = _adjacency_map(result, include_guarded_cycles=False)
    if not registration.cycles_allowed and _detect_cycle(cycle_adjacency):
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
            f'    {_mermaid_id(node.name)}["{_mermaid_label(f"{node.name}: {node.purpose}")}"]'
        )
    for edge in result.edges:
        mermaid_lines.append(
            f"    {_mermaid_id(edge.source)} --> {_mermaid_id(edge.target)}"
        )
    for conditional_edge in result.conditional_edges:
        for branch_label, target in conditional_edge.branches.items():
            target_id = "END" if target in END_TARGETS else _mermaid_id(target)
            mermaid_lines.append(
                f'    {_mermaid_id(conditional_edge.source)} -- "{_mermaid_label(branch_label)}" --> {target_id}'
            )
    for command_route in result.command_routes:
        for target in command_route.destinations:
            target_id = "END" if target in END_TARGETS else _mermaid_id(target)
            label = _mermaid_label(command_route.condition or "Command")
            mermaid_lines.append(
                f'    {_mermaid_id(command_route.source)} -. "{label}" .-> {target_id}'
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
        "command_routes": [route.model_dump() for route in result.command_routes],
        "tool_reachability": [
            reachability.model_dump() for reachability in result.tool_reachability
        ],
        "domain_terms": list(result.domain_terms),
        "compiled_graph_variable": result.compiled_graph_variable,
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
            cycles_allowed=True,
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
        GraphDesignRegistration(
            architecture_id="deepagents",
            supported_entry_shapes=["deep_agent"],
            supported_exit_shapes=["terminal"],
            cycles_allowed=False,
            fallback_builder=_build_deepagents_fallback,
            export_label_defaults={"title": "Experimental Deep Agents Workflow"},
            composition_strategy="deepagents_harness",
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
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            raise ValueError(
                f"Failed to import graph design plugin module '{module_name}': "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        register = getattr(module, "register_graph_designers", None)
        if not callable(register):
            raise ValueError(
                f"Graph design plugin module '{module_name}' must define register_graph_designers(registry)."
            )
        hook: PluginHook = register
        try:
            hook(registry)
        except Exception as exc:
            raise ValueError(
                f"Graph design plugin module '{module_name}' failed while running "
                f"register_graph_designers(registry): {type(exc).__name__}: {exc}"
            ) from exc
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
