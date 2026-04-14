"""Shared helpers for generator-agent ChatOpenAI construction."""

from __future__ import annotations

from typing import Any, Type

from langchain_openai import ChatOpenAI

from langgraph_system_generator.utils.config import ModelConfig, settings


def build_chat_llm(
    *,
    model: str | None = None,
    model_config: ModelConfig | None = None,
    chat_openai_cls: Type[ChatOpenAI] = ChatOpenAI,
) -> Any:
    """Build a ChatOpenAI-compatible client from shared model config rules."""
    config = model_config or ModelConfig(
        model=model or settings.default_model,
        temperature=0.0,
    )
    llm_kwargs = {"model": config.model, "temperature": config.temperature}
    if config.api_base:
        llm_kwargs["base_url"] = config.api_base
    if config.max_tokens is not None:
        llm_kwargs["max_tokens"] = config.max_tokens
    return chat_openai_cls(**llm_kwargs)
