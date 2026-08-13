"""Normalize LangGraph START/END sentinel shorthand in graph designs."""

from __future__ import annotations

from langgraph_system_generator.generator.state import GraphDesignResult, GraphEdgeSpec

START_TARGETS = {"START", "__start__"}
END_TARGETS = {"END", "__end__"}


def normalize_sentinel_edges(result: GraphDesignResult) -> GraphDesignResult:
    """Convert direct START/END edges into the canonical graph-design schema.

    The graph-design schema represents START with ``entry_point`` and represents
    END by leaving a terminal node without an outgoing route. Language models
    often emit the equivalent LangGraph shorthand as direct edges. Accept that
    syntax at the input boundary, normalize it, and retain strict validation for
    every real node and route afterward.
    """

    entry_point = result.entry_point.strip()
    node_names = {node.name.strip() for node in result.nodes}
    reserved_nodes = node_names & (START_TARGETS | END_TARGETS)
    if reserved_nodes:
        nodes = ", ".join(sorted(reserved_nodes))
        raise ValueError(f"Sentinel node ids must not be declared: {nodes}.")
    normalized_edges: list[GraphEdgeSpec] = []
    start_targets: set[str] = set()
    terminal_sources: set[str] = set()

    for edge in result.edges:
        source = edge.source.strip()
        target = edge.target.strip()

        if source in START_TARGETS:
            if target in START_TARGETS or target in END_TARGETS:
                raise ValueError(f"Invalid START edge target '{target}'.")
            start_targets.add(target)
            continue

        if target in START_TARGETS:
            raise ValueError("START may only be used as an edge source.")

        if source in END_TARGETS:
            raise ValueError("END may only be used as an edge target.")

        if target in END_TARGETS:
            if source not in node_names:
                raise ValueError(
                    f"END edge source '{source}' does not match any declared node."
                )
            terminal_sources.add(source)
            continue

        normalized_edges.append(
            edge.model_copy(update={'source': source, 'target': target})
        )

    if len(start_targets) > 1:
        targets = ", ".join(sorted(start_targets))
        raise ValueError(f"Conflicting START edge targets: {targets}.")

    if start_targets:
        start_target = next(iter(start_targets))
        if entry_point and entry_point != start_target:
            raise ValueError(
                "Conflicting entry points: "
                f"entry_point='{entry_point}' but START targets '{start_target}'."
            )
        entry_point = start_target

    outgoing_sources = {edge.source.strip() for edge in normalized_edges}
    outgoing_sources.update(edge.source.strip() for edge in result.conditional_edges)
    outgoing_sources.update(route.source.strip() for route in result.command_routes)
    ambiguous_terminals = terminal_sources & outgoing_sources
    if ambiguous_terminals:
        nodes = ", ".join(sorted(ambiguous_terminals))
        raise ValueError(
            "Nodes cannot have an unconditional END edge and another outgoing "
            f"route: {nodes}."
        )

    return result.model_copy(
        update={
            "entry_point": entry_point,
            "edges": normalized_edges,
        }
    )
