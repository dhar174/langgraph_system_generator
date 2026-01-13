"""Pattern library for LangGraph multi-agent architectures.

This module provides reusable templates and code generators for common
multi-agent patterns in LangGraph workflows.

Available Patterns:
    - RouterPattern: Dynamic routing to specialized agents
    - SubagentsPattern: Supervisor-subagent coordination
    - CritiqueLoopPattern: Iterative refinement through critique-revise cycles
"""

from langgraph_system_generator.patterns.critique_loops import CritiqueLoopPattern
from langgraph_system_generator.patterns.router import RouterPattern
from langgraph_system_generator.patterns.subagents import SubagentsPattern

__all__ = [
    "RouterPattern",
    "SubagentsPattern",
    "CritiqueLoopPattern",
]

