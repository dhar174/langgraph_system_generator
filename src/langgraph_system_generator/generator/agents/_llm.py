"""Shared helpers for generator-agent ChatOpenAI construction."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any

import httpx
from httpx import AsyncClient, Client
from langchain_openai import ChatOpenAI

from langgraph_system_generator.utils.config import ModelConfig, settings
from langgraph_system_generator.utils.credential_redaction import (
    install_llm_log_redaction,
)
from langgraph_system_generator.utils.error_handling import GenerationError
from langgraph_system_generator.utils.llm_endpoint_security import authorize_endpoint

_owned_transports: ContextVar[list[tuple[httpx.Client, httpx.AsyncClient]] | None] = (
    ContextVar("llm_transports", default=None)
)


@asynccontextmanager
async def llm_transport_scope() -> AsyncIterator[None]:
    """Close generation-owned clients, including on failure and cancellation."""
    clients: list[tuple[httpx.Client, httpx.AsyncClient]] = []
    token = _owned_transports.set(clients)
    try:
        yield
    finally:
        _owned_transports.reset(token)
        for sync, asynchronous in clients:
            sync.close()
            await asynchronous.aclose()


def build_chat_llm(
    *,
    model: str | None = None,
    model_config: ModelConfig | None = None,
    chat_openai_class: type[ChatOpenAI] = ChatOpenAI,
) -> Any:
    """Bind destination and credentials explicitly; never use SDK auth fallback.

    Direct agent callers own the returned client's transports. Shared generation
    uses ``llm_transport_scope`` for deterministic cleanup.
    """
    config = model_config or ModelConfig(
        model=model or settings.default_model,
        temperature=0.0,
    )
    binding = authorize_endpoint(config.api_base, config.endpoint_policy)
    key = binding.credential()
    install_llm_log_redaction()

    def check_request(request: httpx.Request) -> None:
        permitted = {
            binding.base_url + "/chat/completions",
            binding.base_url + "/responses",
        }
        if str(request.url) not in permitted:
            raise GenerationError(
                "LLM transport destination rejected.",
                code="endpoint_not_allowed",
                status_code=403,
            )
        # Rebuild headers rather than trusting ambient SDK custom headers, even
        # when an override uses an otherwise ordinary name such as Host.
        official_metadata = {
            name: request.headers[name]
            for name in ("openai-organization", "openai-project")
            if binding.provider_id == "openai" and name in request.headers
        }
        raw_mode = request.headers.get("x-stainless-raw-response")
        if raw_mode in {"true", "stream"}:
            official_metadata["x-stainless-raw-response"] = raw_mode
        request.headers.clear()
        request.headers.update(
            {
                "Host": request.url.netloc.decode("ascii"),
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Content-Length": str(len(request.content)),
                "User-Agent": "langgraph-system-generator",
                "Authorization": "Bearer " + key,
                **official_metadata,
            }
        )

    async def check_async_request(request: httpx.Request) -> None:
        check_request(request)

    def check_response(response: httpx.Response) -> None:
        if response.status_code >= 300:
            # Provider bodies and headers can echo secrets. Classify before SDK
            # diagnostics, preserving status without including remote content.
            raise GenerationError(
                f"LLM provider returned HTTP {response.status_code}.",
                code="llm_provider_error",
                phase="llm_request",
                status_code=502,
                details={"provider_status": response.status_code},
            )

    async def check_async_response(response: httpx.Response) -> None:
        check_response(response)

    sync = Client(
        follow_redirects=False,
        trust_env=False,
        timeout=60.0,
        event_hooks={"request": [check_request], "response": [check_response]},
    )
    asynchronous = AsyncClient(
        follow_redirects=False,
        trust_env=False,
        timeout=60.0,
        event_hooks={
            "request": [check_async_request],
            "response": [check_async_response],
        },
    )
    owner = _owned_transports.get()
    if owner is not None:
        owner.append((sync, asynchronous))
    llm_kwargs: dict[str, Any] = {
        "model": config.model,
        "temperature": config.temperature,
        "base_url": binding.base_url,
        "api_key": key,
        "http_client": sync,
        "http_async_client": asynchronous,
        "openai_proxy": "",
        "organization": "",
        "max_retries": 0,
    }
    if config.max_tokens is not None:
        llm_kwargs["max_tokens"] = config.max_tokens
    try:
        return chat_openai_class(**llm_kwargs)
    except (TypeError, ValueError):
        sync.close()
        raise GenerationError(
            "LLM client initialization failed.",
            code="llm_configuration_error",
            status_code=503,
        ) from None
