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
    official_api_bases = {None, "", OPENAI_BASE_URL, OPENAI_BASE_URL + "/"}
    if model != LUNA_MODEL or api_base not in official_api_bases:
        return {}
    return {
        "use_responses_api": True,
        "reasoning": {"effort": "low"},
        "output_version": "responses/v1",
    }
