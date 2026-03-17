"""Generator-backed pattern library for core LangGraph workflow templates.

Advanced patterns such as hierarchical teams, plan-and-execute, REWOO-style
speculation, HITL approval, judge loops, and compiler-style dependency graphs
live as runnable references under ``examples/`` rather than additional public
code-generation classes.
"""

from langgraph_system_generator.patterns.critique_loops import CritiqueLoopPattern
from langgraph_system_generator.patterns.router import RouterPattern
from langgraph_system_generator.patterns.subagents import SubagentsPattern

__all__ = [
    "RouterPattern",
    "SubagentsPattern",
    "CritiqueLoopPattern",
]
