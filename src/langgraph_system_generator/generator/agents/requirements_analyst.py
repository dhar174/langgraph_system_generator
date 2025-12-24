"""Requirements Analyst agent for extracting structured constraints from user prompts."""

from __future__ import annotations

from typing import List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from langgraph_system_generator.generator.state import Constraint
from langgraph_system_generator.generator.utils import extract_json_from_llm_response
from langgraph_system_generator.utils.config import settings


class RequirementsAnalyst:
    """Extracts structured constraints from user prompt."""

    def __init__(self, model: str | None = None):
        self.llm = ChatOpenAI(model=model or settings.default_model, temperature=0)

    async def analyze(self, prompt: str) -> List[Constraint]:
        """Extract constraints from prompt.

        Args:
            prompt: User's project description

        Returns:
            List of structured constraints
        """
        analysis_prompt = SystemMessage(
            content="""You are a requirements analyst. Extract structured constraints from the user's project description.

Identify and categorize:
- **goal**: The main objective and deliverables
- **tone**: Style, tone, or voice constraints (e.g., professional, casual, technical)
- **length**: Length or size requirements (e.g., short, detailed, comprehensive)
- **structure**: Structural requirements (e.g., modular, linear, hierarchical)
- **runtime**: Runtime constraints (budget, iterations, model preferences, timeouts)
- **environment**: Environment constraints (Colab, libraries, Python version, deployment target)

Return a JSON array of constraints with this structure:
[
  {"type": "goal", "value": "description", "priority": 5},
  {"type": "tone", "value": "description", "priority": 3},
  ...
]

Priority: 1 (low) to 5 (high). Goals are typically priority 5."""
        )

        user_message = HumanMessage(content=prompt)

        response = await self.llm.ainvoke([analysis_prompt, user_message])

        try:
            constraints_data = extract_json_from_llm_response(response.content)
            constraints = [Constraint(**c) for c in constraints_data]
            return constraints
        except (ValueError, KeyError, TypeError) as e:
            import logging

            logging.warning(f"Failed to parse LLM response for constraints: {e}")
            # Fallback: create a basic goal constraint from the prompt
            return [
                Constraint(
                    type="goal",
                    value=prompt[:200] if len(prompt) > 200 else prompt,
                    priority=5,
                )
            ]
