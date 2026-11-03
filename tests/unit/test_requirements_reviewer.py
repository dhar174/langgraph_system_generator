"""Bounded reviewer calls against deterministic fakes and captured HTTP only."""

import asyncio
import json
import logging
from unittest.mock import AsyncMock

import httpx
import pytest
from langchain_core.messages import AIMessage

from langgraph_system_generator.generator.agents import _llm
from langgraph_system_generator.generator.agents import requirements_reviewer as agent
from langgraph_system_generator.generator.state import CellSpec
from langgraph_system_generator.qa.specialist_review import build_review_context
from langgraph_system_generator.utils.config import ModelConfig


def context(text="weather = 1", **extra):
    return build_review_context(
        {
            "user_prompt": "Build a weather assistant",
            "generated_cells": [CellSpec(cell_type="code", content=text)],
            **extra,
        },
        instructions=agent.REVIEW_INSTRUCTIONS,
    )


def install_fake(monkeypatch, message=None, error=None):
    calls = []
    invoke = AsyncMock(
        return_value=message
        or AIMessage(content='{"assessment":"complete","findings":[]}'),
        side_effect=error,
    )

    class Fake:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self.ainvoke = invoke

    monkeypatch.setattr(agent, "ChatOpenAI", Fake)
    return calls, invoke


@pytest.mark.parametrize("cap,expected", [(None, 2048), (80, 80), (5000, 2048)])
async def test_one_call_copied_output_cap_and_zero_retries(monkeypatch, cap, expected):
    calls, invoke = install_fake(monkeypatch)
    config = ModelConfig(model="fixture-model", max_tokens=cap)
    result = await agent.RequirementsDomainReviewer(config).review(context())
    assert result.status == "reviewed" and result.response.findings == ()
    assert result.model_invocations == invoke.await_count == 1
    assert calls[0]["max_tokens"] == expected and calls[0]["max_retries"] == 0
    assert config.max_tokens == cap
    assert invoke.call_args.kwargs["store"] is False
    assert "tools" not in invoke.call_args.kwargs


@pytest.mark.parametrize(
    "message,status,reason",
    [
        (AIMessage(content=""), "invalid_response", "empty_response"),
        (
            AIMessage(content="not JSON api_key=secret"),
            "invalid_response",
            "invalid_response",
        ),
        (AIMessage(content="{}"), "invalid_response", "invalid_response"),
        (
            AIMessage(content="{}", additional_kwargs={"refusal": "secret"}),
            "invalid_response",
            "refused",
        ),
        (AIMessage(content="x" * 16385), "incomplete", "output_limit"),
        (
            AIMessage(content="{}", response_metadata={"finish_reason": "length"}),
            "incomplete",
            "output_limit",
        ),
        (
            AIMessage(content='{"assessment":"insufficient_context","findings":[]}'),
            "incomplete",
            "insufficient_context",
        ),
    ],
)
async def test_response_abstention_is_not_a_fake_pass(
    monkeypatch, message, status, reason
):
    _, invoke = install_fake(monkeypatch, message=message)
    result = await agent.RequirementsDomainReviewer(ModelConfig()).review(context())
    assert (result.status, result.reason_code) == (status, reason)
    assert result.model_invocations == invoke.await_count == 1
    assert "secret" not in result.model_dump_json()


@pytest.mark.parametrize(
    "error,reason",
    [
        (RuntimeError("secret"), "provider_unavailable"),
        (NotImplementedError(), "unsupported_response"),
    ],
)
async def test_unavailable_never_retries(monkeypatch, error, reason):
    _, invoke = install_fake(monkeypatch, error=error)
    result = await agent.RequirementsDomainReviewer(ModelConfig()).review(context())
    assert result.status == "unavailable" and result.reason_code == reason
    assert invoke.await_count == 1


async def test_input_limit_before_construction(monkeypatch):
    calls, invoke = install_fake(monkeypatch)
    result = await agent.RequirementsDomainReviewer(ModelConfig()).review(
        context("x" * 48000)
    )
    assert result.reason_code == "input_limit" and result.model_invocations == 0
    assert calls == [] and invoke.await_count == 0


@pytest.mark.parametrize("cancel", [False, True])
async def test_timeout_and_cancellation_close_scoped_transports(monkeypatch, cancel):
    clients = []
    original = _llm.AsyncClient

    def client(**kwargs):
        value = original(**kwargs)
        clients.append(value)
        return value

    monkeypatch.setattr(_llm, "AsyncClient", client)
    monkeypatch.setattr(agent, "REVIEW_TIMEOUT_SECONDS", 0.03)
    _, invoke = install_fake(monkeypatch)
    entered = asyncio.Event()
    exited = asyncio.Event()

    async def wait(*args, **kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            exited.set()

    invoke.side_effect = wait
    task = asyncio.create_task(
        agent.RequirementsDomainReviewer(ModelConfig()).review(context())
    )
    await asyncio.wait_for(entered.wait(), 2)
    if cancel:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        result = await task
        assert result.status == "unavailable" and result.reason_code == "timeout"
    assert exited.is_set() and all(c.is_closed for c in clients)
    assert invoke.await_count == 1


@pytest.mark.parametrize("code", [200, 400, 429, 500, "length", "constraints"])
async def test_actual_sdk_http_request_count_and_native_schema(
    monkeypatch, code, caplog
):
    from langchain_core.callbacks.base import BaseCallbackHandler
    from langchain_core.callbacks.manager import AsyncCallbackManager
    from langchain_core.tracers.context import (
        run_collector_var,
        tracing_v2_callback_var,
    )

    if code in ("constraints", "length"):
        caplog.set_level(logging.DEBUG)

    class Sentinel(BaseCallbackHandler):
        starts = 0

        def on_chat_model_start(self, *args, **kwargs):
            self.starts += 1

    sentinel = Sentinel()
    tracer_token = tracing_v2_callback_var.set(sentinel)
    collector_token = run_collector_var.set(sentinel)
    requests = []
    clients = []

    def handle(request):
        requests.append(request)
        if isinstance(code, int) and code != 200:
            return httpx.Response(
                code,
                json={
                    "error": {
                        "message": "api_key=secret",
                        "type": "invalid_request_error",
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "fake",
                "object": "chat.completion",
                "created": 0,
                "model": "fixture-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "length" if code == "length" else "stop",
                        "message": {
                            "role": "assistant",
                            "content": (
                                '{"assessment":"FIXTURE_CANARY_TRUNCATED"'
                                if code == "length"
                                else '{"assessment":"complete","findings":[]}'
                            ),
                        },
                    }
                ],
            },
        )

    sync, asynchronous = httpx.Client, httpx.AsyncClient

    def make_sync(**kwargs):
        value = sync(**kwargs, transport=httpx.MockTransport(handle))
        clients.append(value)
        return value

    def make_async(**kwargs):
        value = asynchronous(**kwargs, transport=httpx.MockTransport(handle))
        clients.append(value)
        return value

    monkeypatch.setattr(_llm, "Client", make_sync)
    monkeypatch.setattr(_llm, "AsyncClient", make_async)
    review_context = (
        context(
            constraints=[
                {"description": 'Require weather data; api_key="FIXTURE_CANARY_ALPHA"'},
                {"nested": [{"description": "token='FIXTURE_CANARY_BETA'"}]},
                {"description": 'Already redacted: api_key="[REDACTED]"'},
                {"api_key": {"value": "FIXTURE_CANARY_SUBTREE"}},
                {"openaiApiKey": {"value": "FIXTURE_CANARY_CAMEL_OBJECT"}},
                {
                    "credential": "FIXTURE_CANARY_SCALAR",
                    "signature": "FIXTURE_CANARY_SIGNATURE_SCALAR",
                    "password": 987651234,
                },
            ],
            tools_plan={"description": 'api_key="FIXTURE_CANARY_PLAN"'},
            docs_context=[
                {"content": "Weather", "source": 'token="FIXTURE_CANARY_DOC"'}
            ],
            user_prompt=(
                'Weather config {"api_key":{"value":"FIXTURE_CANARY_INLINE"}} '
                "password: FIXTURE_CANARY_COLON and sk-proj-FIXTURE_CANARY_BARE_0001\n"
                "token: FIXTURE_CANARY_TOKEN\n"
                "client_secret: FIXTURE_CANARY_CLIENT\n"
                "clientSecret: FIXTURE_CANARY_CAMEL\n"
                "openai_api_key: FIXTURE_CANARY_PREFIX\n"
                "openaiApiKey: FIXTURE_CANARY_CAMEL_PREFIX\n"
                "secret_key: FIXTURE_CANARY_KEY\n"
                "credential: FIXTURE_CANARY_CREDENTIAL\n"
                "signature: FIXTURE_CANARY_SIGNATURE\n"
                "authorization: Basic RklYVFVSRV9DQU5BUlk=\n"
                "Proxy-Authorization: Basic dXNlcjpwYXNz\n"
                "credentials: [don't log them] and build a weather assistant"
            ),
        )
        if code == "constraints"
        else context()
    )
    try:
        result = await agent.RequirementsDomainReviewer(
            ModelConfig(model="fixture-model", max_tokens=91)
        ).review(review_context)
        assert sentinel.starts == 0
        assert (
            sentinel
            in AsyncCallbackManager.configure(
                AsyncCallbackManager(handlers=[])
            ).handlers
        )
    finally:
        tracing_v2_callback_var.reset(tracer_token)
        run_collector_var.reset(collector_token)
    assert len(requests) == result.model_invocations == 1
    payload = json.loads(requests[0].content)
    assert payload["response_format"]["type"] == "json_schema"
    assert payload.get("max_completion_tokens", payload.get("max_tokens")) == 91
    assert not payload.get("tools") and payload["store"] is False
    assert all(c.is_closed for c in clients)
    if code == "length":
        assert (result.status, result.reason_code) == ("incomplete", "output_limit")
        assert result.response is None
        assert "FIXTURE_CANARY_TRUNCATED" not in caplog.text + result.model_dump_json()
    elif code == "constraints":
        assert result.status == "reviewed"
        assert "FIXTURE_CANARY_" not in requests[0].content.decode()
        assert "RklYVFVSRV9DQU5BUlk=" not in requests[0].content.decode()
        assert "dXNlcjpwYXNz" not in requests[0].content.decode()
        assert "987651234" not in requests[0].content.decode()
        assert "and build a weather assistant" in requests[0].content.decode()
        assert "FIXTURE_CANARY_" not in caplog.text + result.model_dump_json()
        sources = json.loads(payload["messages"][-1]["content"].split("\n", 1)[1])[
            "sources"
        ]
        requirements = [
            json.loads(s["text"])
            for s in sources
            if s["source_id"].startswith("requirement:")
        ]
        assert requirements[0]["description"].startswith("Require weather data;")
        assert "[REDACTED]" in requirements[1]["nested"][0]["description"]
    else:
        assert result.status == ("reviewed" if code == 200 else "unavailable")


async def test_missing_credentials_constructs_no_client(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(_llm.settings, "openai_api_key", None)
    calls, invoke = install_fake(monkeypatch)
    result = await agent.RequirementsDomainReviewer(ModelConfig()).review(context())
    assert result.status == "unavailable" and result.model_invocations == 0
    assert calls == [] and invoke.await_count == 0
