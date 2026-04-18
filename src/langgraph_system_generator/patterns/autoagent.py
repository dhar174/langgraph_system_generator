"""AutoAgent pattern generator built on top of supervisor/subagent templates."""

from __future__ import annotations

from typing import Dict, List, Optional, Union

from langgraph_system_generator.patterns.subagents import SubagentsPattern
from langgraph_system_generator.utils.config import ModelConfig


class AutoAgentPattern:
    """Template generator for AutoAgent-style coordinated worker workflows."""

    @staticmethod
    def generate_state_code(additional_fields: Optional[Dict[str, str]] = None) -> str:
        """Generate an AutoAgent-compatible state schema."""
        return SubagentsPattern.generate_state_code(additional_fields=additional_fields)

    @staticmethod
    def generate_coordinator_code(
        workers: List[str],
        worker_descriptions: Optional[Dict[str, str]] = None,
        model_config: Optional[Union[ModelConfig, dict]] = None,
        use_structured_output: bool = True,
    ) -> str:
        """Generate the coordinator node implementation."""
        return SubagentsPattern.generate_supervisor_code(
            subagents=workers,
            subagent_descriptions=worker_descriptions,
            model_config=model_config,
            use_structured_output=use_structured_output,
        )

    @staticmethod
    def generate_worker_code(
        worker_name: str,
        worker_description: str,
        model_config: Optional[Union[ModelConfig, dict]] = None,
        include_tools: bool = False,
    ) -> str:
        """Generate a worker node implementation."""
        return SubagentsPattern.generate_subagent_code(
            agent_name=worker_name,
            agent_description=worker_description,
            model_config=model_config,
            include_tools=include_tools,
        )

    @staticmethod
    def generate_graph_code(workers: List[str], max_iterations: int = 10) -> str:
        """Generate graph wiring for the coordinator-worker flow."""
        return SubagentsPattern.generate_graph_code(
            subagents=workers,
            max_iterations=max_iterations,
        )
