"""Model-specific options for supported OpenAI API compatibility modes."""

from __future__ import annotations

from typing import Any

LUNA_MODEL = "gpt-6-luna"
DEFAULT_MODEL = LUNA_MODEL
OPENAI_BASE_URL = "https://api.openai.com/v1"


def chat_openai_compatibility_kwargs(
    model: str | None, *, api_base: str | None = None
) -> dict[str, Any]:
    """Return ChatOpenAI options required by models with a fixed API shape.

    Luna uses the OpenAI Responses API with low reasoning. Its request must omit
    sampling parameters such as temperature. Custom API bases retain their
    existing OpenAI-compatible Chat Completions behavior.
    """
    if model != LUNA_MODEL:
        return {}
    if api_base and api_base != OPENAI_BASE_URL:
        # The endpoint module imports config, which uses this module's defaults.
        from langgraph_system_generator.utils.error_handling import GenerationError
        from langgraph_system_generator.utils.llm_endpoint_security import (
            canonical_endpoint,
        )

        try:
            if canonical_endpoint(api_base, hosted=False) != OPENAI_BASE_URL:
                return {}
        except GenerationError:
            return {}
    return {
        "use_responses_api": True,
        "reasoning": {"effort": "low"},
        "output_version": "responses/v1",
    }
