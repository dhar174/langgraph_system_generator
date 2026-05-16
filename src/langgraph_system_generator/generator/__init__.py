"""Generator module for LangGraph Notebook Foundry."""

from langgraph_system_generator.generator.state import (
    CellSpec,
    Constraint,
    DocSnippet,
    GenerationContextPack,
    GeneratorState,
    NotebookPlan,
    QAReport,
    QARepairFeedback,
)


def create_generator_graph(*args, **kwargs):
    """Lazily import the graph factory to avoid package import cycles."""

    from langgraph_system_generator.generator.graph import (
        create_generator_graph as _create_generator_graph,
    )

    return _create_generator_graph(*args, **kwargs)

__all__ = [
    "create_generator_graph",
    "GeneratorState",
    "Constraint",
    "DocSnippet",
    "GenerationContextPack",
    "NotebookPlan",
    "CellSpec",
    "QAReport",
    "QARepairFeedback",
]
