"""Offline endpoint/credential boundary regressions for issue #379."""

import asyncio
import json
import socket
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import APIConnectionError

from langgraph_system_generator.api import server
from langgraph_system_generator.generator.agents import _llm
from langgraph_system_generator.generator.agents._llm import build_chat_llm
from langgraph_system_generator.utils.config import ModelConfig
from langgraph_system_generator.utils.error_handling import GenerationError
from langgraph_system_generator.utils.llm_endpoint_security import (
    NO_AUTH_KEY,
    OPENAI_BASE,
    authorize_endpoint,
    canonical_endpoint,
)

SERVER_KEY = "FAKE_SERVER_OWNED_SECRET_DO_NOT_FORWARD"
CUSTOM_KEY = "FAKE_ALTERNATIVE_PROVIDER_SECRET"
CUSTOM_BASE = "https://llm.example.com/v1"


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch):
    for name in (
        "OPENAI_BASE_URL",
        "OPENAI_API_BASE",
        "OPENAI_PROXY",
        "LANGSMITH_GATEWAY",
        "LANGSMITH_GATEWAY_API_KEY",
        "OPENAI_CUSTOM_HEADERS",
        "LNF_TRUSTED_LLM_ENDPOINTS",
        "LNF_LLM_ENDPOINT_POLICY",
        "LNF_CUSTOM_LLM_NO_AUTH",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", SERVER_KEY)
    monkeypatch.setenv("LNF_CUSTOM_LLM_API_KEY", CUSTOM_KEY)


def register(monkeypatch):
    monkeypatch.setenv(
        "LNF_TRUSTED_LLM_ENDPOINTS",
        json.dumps(
            {
                "example": {
                    "base_url": CUSTOM_BASE,
                    "api_key_env": "LNF_LLM_EXAMPLE_API_KEY",
                }
            }
        ),
    )
    monkeypatch.setenv("LNF_LLM_EXAMPLE_API_KEY", CUSTOM_KEY)


@pytest.fixture
def outbound(monkeypatch):
    seen, clients = [], []
    result = {"status": 200, "headers": {}, "body": None}

    def handle(request):
        seen.append(request)
        body = result["body"] or {
            "id": "fake",
            "object": "chat.completion",
            "created": 0,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
        }
        return httpx.Response(result["status"], headers=result["headers"], json=body)

    real_sync, real_async = httpx.Client, httpx.AsyncClient

    def sync_client(**kwargs):
        client = real_sync(transport=httpx.MockTransport(handle), **kwargs)
        clients.append(client)
        return client

    def async_client(**kwargs):
        client = real_async(transport=httpx.MockTransport(handle), **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(_llm, "Client", sync_client)
    monkeypatch.setattr(_llm, "AsyncClient", async_client)
    yield seen, result, clients
    for client in clients:
        if isinstance(client, real_sync):
            client.close()
        else:
            asyncio.run(client.aclose())


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["/generate", "/generate-async"])
async def test_hosted_rejects_before_generation(route, monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", SERVER_KEY)
    monkeypatch.delenv("LNF_TRUSTED_LLM_ENDPOINTS", raising=False)
    generate = AsyncMock(side_effect=AssertionError("generation must not start"))
    monkeypatch.setattr(server, "generate_artifacts", generate)

    def forbidden(*args, **kwargs):
        raise AssertionError("side effect before authorization")

    monkeypatch.setattr(server, "_resolve_output_dir", forbidden)
    monkeypatch.setattr(server, "create_job", forbidden)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        response = await client.post(
            route,
            json={
                "prompt": "test",
                "mode": "live",
                "model": "test-model",
                "custom_endpoint": "https://untrusted-llm.example/v1",
            },
        )
    assert response.status_code == 403
    assert SERVER_KEY not in response.text
    generate.assert_not_called()


def test_factory_never_inherits_endpoint_environment(monkeypatch, outbound):
    monkeypatch.setenv("OPENAI_API_KEY", SERVER_KEY)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://untrusted-llm.example/v1")
    monkeypatch.setenv("OPENAI_API_BASE", "https://untrusted-llm.example/v1")
    seen, _, _ = outbound
    model = build_chat_llm(model_config=ModelConfig(model="test-model"))
    model.invoke("test")
    assert len(seen) == 1
    assert seen[0].url.host == "api.openai.com"
    assert seen[0].headers["authorization"] == "Bearer " + SERVER_KEY


@pytest.mark.parametrize(
    "url",
    [
        "http://llm.example.com/v1",
        "https://127.0.0.1/v1",
        "https://10.0.0.1/v1",
        "https://172.16.0.1/v1",
        "https://192.168.1.1/v1",
        "https://169.254.169.254/v1",
        "https://metadata.google.internal/v1",
        "https://localhost/v1",
        "https://[::1]/v1",
        "https://[fc00::1]/v1",
        "https://[fe80::1]/v1",
        "https://[::ffff:8.8.8.8]/v1",
        "https://llm.example.com:444/v1",
        "https://llm.example.com.evil.com/v1",
        "https://llm.example.com/v10",
        "https://llm.example.com/v1/other",
        "https://user:password@llm.example.com/v1",
        "https://llm.example.com/v1?api_key=secret",
        "https://llm.example.com/v1#secret",
        "https://llm.example.com./v1",
        "https://llm.example.com/%76%31",
        "https://llm.example.com/v1/../other",
        "https://llm.example.com//v1",
        "https://llm.example.com\\@evil.com/v1",
        "https://127.1/v1",
        "https://2130706433/v1",
        "https://0x7f000001/v1",
        "https://llm.example.com:/v1",
        "https://llm.example.com:99999/v1",
        "https://[broken/v1",
        "https://ÃƒÆ’Ã‚Â©xample.com/v1",
        "https://llm.example.com/v1\n",
        "ftp://llm.example.com/v1",
    ],
)
def test_hosted_rejects_unsafe_or_unregistered_forms(url, monkeypatch):
    register(monkeypatch)
    with pytest.raises(GenerationError):
        authorize_endpoint(url, "hosted")


@pytest.mark.parametrize(
    "url", [CUSTOM_BASE, CUSTOM_BASE + "/", "https://LLM.EXAMPLE.COM:443/v1/"]
)
def test_canonical_registry_matching(url, monkeypatch):
    register(monkeypatch)
    binding = authorize_endpoint(url, "hosted")
    assert binding.base_url == CUSTOM_BASE
    assert binding.provider_id == "example"


@pytest.mark.parametrize(
    "raw",
    [
        "broken",
        "[]",
        '{"x": {}, "x": {}}',
        '{"openai": {}}',
        '{"x": {"base_url": "https://llm.example.com/v1", "api_key_env": "OPENAI_API_KEY"}}',
        '{"x": {"base_url": "http://127.0.0.1/v1", "api_key_env": "LNF_LLM_X_API_KEY"}}',
    ],
)
def test_bad_registry_fails_closed_even_for_default(raw, monkeypatch):
    monkeypatch.setenv("LNF_TRUSTED_LLM_ENDPOINTS", raw)
    with pytest.raises(GenerationError) as caught:
        authorize_endpoint(None, "hosted")
    assert caught.value.status_code == 503
    assert raw not in str(caught.value)


def test_authorization_performs_no_dns_or_credential_lookup(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("DNS/credential access is forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    from langgraph_system_generator.utils.llm_endpoint_security import EndpointBinding

    monkeypatch.setattr(EndpointBinding, "credential", forbidden)
    with pytest.raises(GenerationError):
        authorize_endpoint(CUSTOM_BASE, "hosted")


@pytest.mark.asyncio
@pytest.mark.parametrize("asynchronous", [False, True])
async def test_actual_custom_requests_have_only_provider_credentials(
    monkeypatch, outbound, asynchronous
):
    register(monkeypatch)
    monkeypatch.setenv("OPENAI_ORG_ID", SERVER_KEY)
    monkeypatch.setenv("OPENAI_PROJECT_ID", SERVER_KEY)
    monkeypatch.setenv(
        "OPENAI_CUSTOM_HEADERS",
        "Authorization: Bearer "
        + SERVER_KEY
        + "\nX-Secret: "
        + SERVER_KEY
        + "\nUser-Agent: "
        + SERVER_KEY
        + "\nX-Stainless-Lang: "
        + SERVER_KEY
        + "\nHost: "
        + SERVER_KEY,
    )
    monkeypatch.setenv("LANGSMITH_GATEWAY", "https://evil.example.com")
    monkeypatch.setenv("LANGSMITH_GATEWAY_API_KEY", SERVER_KEY)
    seen, _, clients = outbound
    async with _llm.llm_transport_scope():
        model = build_chat_llm(
            model_config=ModelConfig(
                model="test-model",
                api_base=CUSTOM_BASE,
                endpoint_policy="hosted",
                temperature=0.3,
                max_tokens=42,
            )
        )
        if asynchronous:
            await model.ainvoke("test")
        else:
            model.invoke("test")
    assert all(client.is_closed for client in clients)
    assert len(seen) == 1
    request = seen[0]
    assert str(request.url) == CUSTOM_BASE + "/chat/completions"
    assert request.headers["authorization"] == "Bearer " + CUSTOM_KEY
    assert (
        SERVER_KEY
        not in str(request.headers) + str(request.url) + request.content.decode()
    )
    payload = json.loads(request.content)
    assert payload["model"] == "test-model" and payload["temperature"] == 0.3
    assert payload.get("max_tokens", payload.get("max_completion_tokens")) == 42


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [301, 302, 303, 307, 308, 401, 500])
@pytest.mark.parametrize(
    "target",
    ["https://evil.example.com/v1", "http://169.254.169.254/", CUSTOM_BASE + "/other"],
)
async def test_redirects_and_remote_errors_never_escape_or_leak(
    status, target, monkeypatch, outbound, caplog
):
    import logging

    caplog.set_level(logging.DEBUG)
    register(monkeypatch)
    seen, result, clients = outbound
    result.update(
        status=status,
        headers={"location": target, "x-secret": SERVER_KEY},
        body={"error": {"message": SERVER_KEY}},
    )
    async with _llm.llm_transport_scope():
        model = build_chat_llm(
            model_config=ModelConfig(
                model="test-model", api_base=CUSTOM_BASE, endpoint_policy="hosted"
            )
        )
        with pytest.raises((GenerationError, APIConnectionError)) as caught:
            await model.ainvoke("test")
    assert len(seen) == 1
    assert (
        SERVER_KEY
        not in str(caught.value)
        + str(server._generation_error_payload(caught.value))
        + caplog.text
    )
    assert all(client.is_closed for client in clients)
    assert CUSTOM_BASE not in caplog.text and target not in caplog.text


def test_missing_alternative_credentials_do_not_use_server_key(monkeypatch):
    register(monkeypatch)
    monkeypatch.delenv("LNF_LLM_EXAMPLE_API_KEY")
    with pytest.raises(GenerationError) as caught:
        build_chat_llm(
            model_config=ModelConfig(api_base=CUSTOM_BASE, endpoint_policy="hosted")
        )
    assert caught.value.code == "credentials_required"


def test_none_api_key_is_not_isolation(monkeypatch):
    # Document the SDK fallback that the production factory must never rely on.
    from openai import OpenAI

    with OpenAI(api_key=None, base_url=OPENAI_BASE) as client:
        assert client.api_key == SERVER_KEY


def test_explicit_local_no_auth_is_loopback_only(monkeypatch):
    monkeypatch.delenv("LNF_CUSTOM_LLM_API_KEY")
    monkeypatch.setenv("LNF_CUSTOM_LLM_NO_AUTH", "true")
    assert authorize_endpoint("http://127.0.0.1:1234/v1").credential() == NO_AUTH_KEY
    with pytest.raises(GenerationError):
        authorize_endpoint(CUSTOM_BASE).credential()
    monkeypatch.setenv("LNF_CUSTOM_LLM_API_KEY", CUSTOM_KEY)
    with pytest.raises(GenerationError):
        authorize_endpoint("http://localhost:1234/v1").credential()


def test_hosted_process_cannot_be_downgraded(monkeypatch):
    monkeypatch.setenv("LNF_LLM_ENDPOINT_POLICY", "hosted")
    with pytest.raises(GenerationError):
        build_chat_llm(
            model_config=ModelConfig(api_base=CUSTOM_BASE, endpoint_policy="local")
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
async def test_scope_closes_on_failure_and_cancellation(failure, outbound):
    with pytest.raises(failure):
        async with _llm.llm_transport_scope():
            build_chat_llm(model_config=ModelConfig(model="test-model"))
            raise failure()
    assert all(client.is_closed for client in outbound[2])


@pytest.mark.asyncio
async def test_concurrent_requests_keep_their_credentials(monkeypatch, outbound):
    register(monkeypatch)

    async def generate(base):
        async with _llm.llm_transport_scope():
            model = build_chat_llm(
                model_config=ModelConfig(
                    model="test-model", api_base=base, endpoint_policy="hosted"
                )
            )
            await asyncio.sleep(0)
            await model.ainvoke("test")

    await asyncio.gather(generate(OPENAI_BASE), generate(CUSTOM_BASE))
    assert {
        (request.url.host, request.headers["authorization"]) for request in outbound[0]
    } == {
        ("api.openai.com", "Bearer " + SERVER_KEY),
        ("llm.example.com", "Bearer " + CUSTOM_KEY),
    }


def test_configuration_never_serializes_secrets_or_endpoint(monkeypatch):
    from langgraph_system_generator.utils.config import GenerationConfig, Settings

    config = GenerationConfig(api_base=CUSTOM_BASE, endpoint_policy="hosted")
    assert CUSTOM_BASE not in config.model_dump_json() + repr(config)
    assert config.to_model_config("test-model").endpoint_policy == "hosted"
    setting = Settings(lnf_custom_llm_api_key=CUSTOM_KEY)
    assert CUSTOM_KEY not in setting.model_dump_json() + repr(setting)


def test_address_normalization():
    assert (
        canonical_endpoint("https://[2606:4700:4700:0:0:0:0:1111]:443/v1/", hosted=True)
        == "https://[2606:4700:4700::1111]/v1"
    )


@pytest.mark.asyncio
async def test_rejected_package_call_writes_nothing(tmp_path):
    from langgraph_system_generator.cli import generate_artifacts

    destination = tmp_path / "must-not-exist"
    with pytest.raises(GenerationError):
        await generate_artifacts(
            "test",
            output_dir=destination,
            mode="stub",
            model="test-model",
            custom_endpoint=CUSTOM_BASE,
            endpoint_policy="hosted",
        )
    assert not destination.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["/generate", "/generate-async"])
async def test_trusted_api_preflight_and_missing_key(route, monkeypatch):
    register(monkeypatch)
    request = server.GenerationRequest(
        prompt="test",
        mode="live",
        model="provider-model",
        custom_endpoint=CUSTOM_BASE + "/",
    )
    normalized = server._normalize_request(request)
    assert normalized.custom_endpoint == CUSTOM_BASE
    monkeypatch.delenv("LNF_LLM_EXAMPLE_API_KEY")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        response = await client.post(route, json=request.model_dump())
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "credentials_required"
    assert SERVER_KEY not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["/generate", "/generate-async"])
async def test_validation_errors_do_not_echo_input_secrets(route):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        response = await client.post(
            route,
            json={
                "prompt": "test",
                "temperature": SERVER_KEY,
                "custom_endpoint": "https://user:" + CUSTOM_KEY + "@example.com/v1",
            },
        )
    assert response.status_code == 422
    assert SERVER_KEY not in response.text and CUSTOM_KEY not in response.text


@pytest.mark.asyncio
async def test_custom_notebook_helper_uses_runner_credentials(monkeypatch, outbound):
    import langchain_openai

    from langgraph_system_generator.generator.agents.notebook_composer import (
        NotebookComposer,
    )
    from langgraph_system_generator.generator.state import NotebookCompositionFeedback

    monkeypatch.setenv("LNF_NOTEBOOK_API_BASE", "https://runner.example.com/v1")
    monkeypatch.setenv("LNF_NOTEBOOK_LLM_API_KEY", "notebook-runner-key")
    async with _llm.llm_transport_scope():
        composer = NotebookComposer(
            model_config=ModelConfig(model="test-model", api_base=CUSTOM_BASE)
        )
        plan = composer._plan_dependencies([], {})
        assert "LNF_NOTEBOOK_LLM_API_KEY" in plan.provider_env_vars
        assert "OPENAI_API_KEY" not in plan.provider_env_vars
        cells = composer._create_config_cells(plan, NotebookCompositionFeedback())
    source = "\n".join(cell.content for cell in cells if cell.cell_type == "code")
    assert not any(value in source for value in (SERVER_KEY, CUSTOM_KEY, CUSTOM_BASE))
    captured = {}

    def fake_llm(**kwargs):
        captured.update(kwargs)
        return "notebook-model"

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", fake_llm)
    namespace = {}
    exec(  # noqa: S102 - execute generated notebook config against fakes
        compile(source, "generated-config", "exec"), namespace
    )
    assert namespace["make_llm"]() == "notebook-model"
    assert captured["base_url"] == "https://runner.example.com/v1"
    assert captured["api_key"] == "notebook-runner-key"
    assert SERVER_KEY not in str(captured)
    monkeypatch.delenv("LNF_NOTEBOOK_LLM_API_KEY")
    with pytest.raises(ValueError, match="LNF_NOTEBOOK_LLM_API_KEY"):
        namespace["make_llm"]()


@pytest.mark.asyncio
async def test_package_artifacts_exclude_server_configuration(
    monkeypatch, tmp_path, outbound
):
    import zipfile

    from langgraph_system_generator import cli
    from langgraph_system_generator.generator.agents.notebook_composer import (
        NotebookComposer,
    )
    from langgraph_system_generator.generator.state import NotebookCompositionFeedback

    monkeypatch.setenv("BASE_OUTPUT_DIR", str(tmp_path))
    register(monkeypatch)

    class Graph:
        async def ainvoke(self, state, *, config):
            assert config["recursion_limit"] >= 25
            assert state["generation_config"].endpoint_policy == "hosted"
            model_config = state["generation_config"].to_model_config("test-model")
            composer = NotebookComposer(model_config=model_config)
            cells = composer._create_config_cells(
                composer._plan_dependencies([], {}), NotebookCompositionFeedback()
            )
            result = cli._build_stub_result("test")
            result["generated_cells"] = cells
            result["generation_config"] = state["generation_config"]
            return result

    monkeypatch.setattr(cli, "_load_generator_graph", lambda: lambda: Graph())
    artifacts = await cli.generate_artifacts(
        "test",
        output_dir=tmp_path / "artifacts",
        mode="live",
        formats=["ipynb", "zip"],
        model="test-model",
        custom_endpoint=CUSTOM_BASE,
        endpoint_policy="hosted",
    )
    assert artifacts["manifest"]["llm_provider"] == "example"
    assert "custom_endpoint" not in artifacts["manifest"]
    for path in (tmp_path / "artifacts").iterdir():
        if path.suffix == ".zip":
            with zipfile.ZipFile(path) as archive:
                contents = b"\n".join(archive.read(name) for name in archive.namelist())
        else:
            contents = path.read_bytes()
        for value in (SERVER_KEY, CUSTOM_KEY, CUSTOM_BASE):
            assert value.encode() not in contents, path.name


def test_cli_forwards_new_flags(monkeypatch):
    from langgraph_system_generator import cli

    captured = {}

    async def fake_generate(prompt, **kwargs):
        captured.update(kwargs)
        return {"output_dir": "fake", "manifest_path": "fake", "manifest": {}}

    monkeypatch.setattr(cli, "generate_artifacts", fake_generate)
    assert (
        cli.main(
            [
                "generate",
                "test",
                "--mode",
                "live",
                "--model",
                "local-model",
                "--custom-endpoint",
                "http://localhost:1234/v1",
            ]
        )
        == 0
    )
    assert captured["model"] == "local-model"
    assert captured["custom_endpoint"] == "http://localhost:1234/v1"


@pytest.mark.asyncio
@pytest.mark.parametrize("suffix", ["\n", "\r", "\t", " "])
async def test_api_rejects_controls_before_url_normalization(suffix, monkeypatch):
    register(monkeypatch)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/generate-async",
            json={
                "prompt": "test",
                "mode": "stub",
                "model": "test-model",
                "custom_endpoint": CUSTOM_BASE + suffix,
            },
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_effective_destination_change_is_blocked(outbound):
    async with _llm.llm_transport_scope():
        model = build_chat_llm(model_config=ModelConfig(model="test-model"))
        model.root_client.base_url = "https://untrusted-llm.example/v1"
        with pytest.raises((GenerationError, APIConnectionError)):
            model.invoke("test")
    assert outbound[0] == []


@pytest.mark.asyncio
async def test_no_auth_effective_request_uses_only_placeholder(monkeypatch, outbound):
    monkeypatch.delenv("LNF_CUSTOM_LLM_API_KEY")
    monkeypatch.setenv("LNF_CUSTOM_LLM_NO_AUTH", "true")
    async with _llm.llm_transport_scope():
        model = build_chat_llm(
            model_config=ModelConfig(
                model="test-model", api_base="http://127.0.0.1:1234/v1"
            )
        )
        await model.ainvoke("test")
    assert outbound[0][0].headers["authorization"] == "Bearer " + NO_AUTH_KEY
    assert SERVER_KEY not in str(outbound[0][0].headers)


@pytest.mark.asyncio
async def test_stub_has_no_credentials_network_or_live_clients(monkeypatch, tmp_path):
    from langgraph_system_generator import cli
    from langgraph_system_generator.utils.llm_endpoint_security import EndpointBinding

    monkeypatch.setenv("BASE_OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.delenv("LNF_CUSTOM_LLM_API_KEY")

    def forbidden(*args, **kwargs):
        raise AssertionError("stub attempted a live operation")

    monkeypatch.setattr(EndpointBinding, "credential", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(cli, "_load_generator_graph", forbidden)
    artifacts = [
        await cli.generate_artifacts(
            "deterministic",
            output_dir=tmp_path / str(index),
            mode="stub",
            formats=["ipynb"],
        )
        for index in range(2)
    ]
    from pathlib import Path

    cells = [Path(item["manifest"]["cells_path"]).read_bytes() for item in artifacts]
    assert cells[0] == cells[1]


def test_nested_error_payloads_never_reflect_credentials():
    error = GenerationError(
        "Provider failed at https://"
        + SERVER_KEY
        + ":"
        + CUSTOM_KEY
        + "@example.com/v1",
        hint="Check https://example.com/v1?client_secret=" + SERVER_KEY,
        details={
            "nested": [
                {"api_key": SERVER_KEY},
                {"url": "https://example.com/" + CUSTOM_KEY},
            ]
        },
    )
    payload = json.dumps(server._generation_error_payload(error))
    assert SERVER_KEY not in payload and CUSTOM_KEY not in payload
    assert "generation_error" in payload


def test_registered_nondefault_port_is_exact(monkeypatch):
    endpoint = "https://llm.example.com:8443/api/v1"
    monkeypatch.setenv(
        "LNF_TRUSTED_LLM_ENDPOINTS",
        json.dumps(
            {
                "example": {
                    "base_url": endpoint,
                    "api_key_env": "LNF_LLM_EXAMPLE_API_KEY",
                }
            }
        ),
    )
    assert authorize_endpoint(endpoint, "hosted").base_url == endpoint
    for other in (
        "https://llm.example.com/api/v1",
        "https://llm.example.com:8443/API/v1",
    ):
        with pytest.raises(GenerationError):
            authorize_endpoint(other, "hosted")


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["/generate", "/generate-async"])
async def test_allowed_routes_forward_canonical_binding(route, monkeypatch, tmp_path):
    register(monkeypatch)

    async def fake_generation(prompt, **kwargs):
        output = Path(kwargs["output_dir"])
        manifest_path = output / "manifest.json"
        manifest_path.write_text("{}", encoding="utf-8")
        return {
            "mode": "live",
            "prompt": prompt,
            "manifest": {},
            "manifest_path": str(manifest_path),
            "output_dir": str(output),
        }

    generated = AsyncMock(side_effect=fake_generation)
    monkeypatch.setattr(server, "generate_artifacts", generated)
    monkeypatch.setattr(server, "_BASE_OUTPUT", tmp_path)
    monkeypatch.setattr(server, "_api_runs", {})
    monkeypatch.setattr(server, "_shutting_down", False)
    monkeypatch.setattr(server, "_resolve_output_dir", lambda path: tmp_path)
    tasks = []
    create_task = asyncio.create_task

    def track_task(coroutine, **kwargs):
        task = create_task(coroutine, **kwargs)
        tasks.append(task)
        return task

    monkeypatch.setattr(server.asyncio, "create_task", track_task)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        response = await client.post(
            route,
            json={
                "prompt": "test",
                "mode": "live",
                "model": "test-model",
                "custom_endpoint": "https://LLM.EXAMPLE.COM:443/v1/",
                "temperature": 0.3,
                "max_tokens": 42,
                "agent_type": "router",
            },
        )
    await asyncio.gather(*tasks)
    assert response.status_code == 200
    generated.assert_awaited_once()
    kwargs = generated.call_args.kwargs
    assert (
        kwargs["custom_endpoint"] == CUSTOM_BASE
        and kwargs["endpoint_policy"] == "hosted"
    )
    assert (
        kwargs["model"],
        kwargs["temperature"],
        kwargs["max_tokens"],
        kwargs["agent_type"],
    ) == ("test-model", 0.3, 42, "router")


@pytest.mark.asyncio
async def test_async_failure_sse_and_logs_do_not_reflect_exception(
    monkeypatch, tmp_path, caplog
):
    monkeypatch.setattr(
        server,
        "generate_artifacts",
        AsyncMock(side_effect=RuntimeError("Bearer " + SERVER_KEY)),
    )
    monkeypatch.setattr(server, "_release_generation_slot", AsyncMock())
    events = []
    for name in ("emit_node_progress", "emit_complete", "emit_log", "emit_error"):
        monkeypatch.setattr(
            server, name, lambda *args, **kwargs: events.append((args, kwargs))
        )
    await server._run_generation_with_progress(
        "fake-job", server.GenerationRequest(prompt="test", mode="stub"), tmp_path
    )
    assert SERVER_KEY not in repr(events) + caplog.text
    assert "RuntimeError" in repr(events)


@pytest.mark.asyncio
async def test_review_preserves_sdk_timeout(outbound):
    from openai import DEFAULT_TIMEOUT

    async with _llm.llm_transport_scope():
        model = build_chat_llm(model="test-model")
        model.invoke("test")
        await model.ainvoke("test")
        assert len(outbound[0]) == 2
        for request in outbound[0]:
            assert request.extensions["timeout"] == DEFAULT_TIMEOUT.as_dict()
        assert len(outbound[2]) == 2
        assert all(
            client.timeout.as_dict() == DEFAULT_TIMEOUT.as_dict()
            for client in outbound[2]
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("asynchronous", [False, True])
async def test_review_sdk_success_headers_are_not_logged(
    outbound, caplog, asynchronous
):
    import logging

    caplog.set_level(logging.DEBUG)
    outbound[1]["headers"] = {"x-echo": SERVER_KEY}
    async with _llm.llm_transport_scope():
        model = build_chat_llm(model="test-model")
        if asynchronous:
            await model.ainvoke("test")
        else:
            model.invoke("test")
    assert any(record.name == "openai._base_client" for record in caplog.records)
    assert SERVER_KEY not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("status", [200, 302])
async def test_review_real_httpcore_diagnostics_are_safe(
    monkeypatch, caplog, asynchronous, status
):
    import logging

    import httpcore

    caplog.set_level(logging.DEBUG)
    body = json.dumps(
        {
            "id": "fake",
            "object": "chat.completion",
            "created": 0,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
        }
    ).encode()
    target = "https://private-provider.example.com/sensitive-route"
    response = (
        f"HTTP/1.1 {status} Response\r\n"
        f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n"
        f"X-Echo: {SERVER_KEY}\r\nLocation: {target}\r\n\r\n"
    ).encode() + body
    real_sync, real_async = httpx.Client, httpx.AsyncClient

    def sync_client(**kwargs):
        transport = httpx.HTTPTransport()
        transport._pool = httpcore.ConnectionPool(
            network_backend=httpcore.MockBackend([response])
        )
        return real_sync(transport=transport, **kwargs)

    def async_client(**kwargs):
        transport = httpx.AsyncHTTPTransport()
        transport._pool = httpcore.AsyncConnectionPool(
            network_backend=httpcore.AsyncMockBackend([response])
        )
        return real_async(transport=transport, **kwargs)

    monkeypatch.setattr(_llm, "Client", sync_client)
    monkeypatch.setattr(_llm, "AsyncClient", async_client)
    async with _llm.llm_transport_scope():
        model = build_chat_llm(model="test-model")

        async def invoke():
            if asynchronous:
                return await model.ainvoke("test")
            return model.invoke("test")

        if status == 200:
            assert (await invoke()).content == "ok"
        else:
            with pytest.raises((GenerationError, APIConnectionError)):
                await invoke()
    assert any(record.name == "httpcore.http11" for record in caplog.records)
    assert any(record.name == "httpcore.connection" for record in caplog.records)
    assert SERVER_KEY not in caplog.text and target not in caplog.text


@pytest.mark.parametrize("name", ["httpcore.http2", "httpcore.proxy", "httpcore.socks"])
def test_review_other_httpcore_emitters_are_filtered(name, caplog):
    import logging

    from langgraph_system_generator.utils.credential_redaction import (
        install_llm_log_redaction,
    )

    caplog.set_level(logging.DEBUG)
    install_llm_log_redaction()
    logging.getLogger(name).debug(
        "receive_response_headers.complete return_value=%r", {"x-echo": SERVER_KEY}
    )
    assert caplog.records and SERVER_KEY not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("no_auth", [False, True])
async def test_review_composed_deepagent_uses_runner_model(
    monkeypatch, outbound, no_auth
):
    import sys
    import types

    import langchain_openai

    from langgraph_system_generator.generator.agents.notebook_composer import (
        NotebookComposer,
    )
    from langgraph_system_generator.generator.state import NotebookCompositionFeedback

    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setenv(
        "LNF_NOTEBOOK_API_BASE",
        "http://127.0.0.1:1234/v1" if no_auth else "https://runner.example.com/v1",
    )
    if no_auth:
        monkeypatch.delenv("LNF_NOTEBOOK_LLM_API_KEY", raising=False)
        monkeypatch.setenv("LNF_NOTEBOOK_LLM_NO_AUTH", "true")
    else:
        monkeypatch.setenv("LNF_NOTEBOOK_LLM_API_KEY", "runner-key")
        monkeypatch.setenv("LNF_NOTEBOOK_LLM_NO_AUTH", "false")
    async with _llm.llm_transport_scope():
        composer = NotebookComposer(
            model_config=ModelConfig(model="test-model", api_base=CUSTOM_BASE)
        )
        workflow = {
            "architecture_type": "deepagents",
            "nodes": [{"name": "deep_agent"}],
        }
        plan = composer._plan_dependencies([], workflow)
        cells = composer._create_config_cells(plan, NotebookCompositionFeedback())
        cells += composer._create_pattern_node_cells(
            workflow["nodes"], "deepagents", workflow
        )
    source = "\n".join(cell.content for cell in cells if cell.cell_type == "code")
    captured = {}
    model = object()

    def fake_model(**kwargs):
        captured["model_kwargs"] = kwargs
        return model

    class Agent:
        def invoke(self, state):
            return {
                "messages": [types.SimpleNamespace(content="custom-provider result")]
            }

    def create_deep_agent(**kwargs):
        captured["agent_kwargs"] = kwargs
        return Agent()

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", fake_model)
    monkeypatch.setitem(
        sys.modules,
        "deepagents",
        types.SimpleNamespace(create_deep_agent=create_deep_agent),
    )
    namespace = {"WorkflowState": dict}
    exec(  # noqa: S102 - execute generated cells against a fake optional SDK
        compile(source, "composed-deepagent", "exec"), namespace
    )
    result = namespace["deep_agent_node"]({"messages": ["test"]})
    assert result["deepagents_available"] is True
    assert result["final_output"] == "custom-provider result"
    assert captured["agent_kwargs"]["model"] is model
    assert captured["model_kwargs"]["api_key"] == (
        NO_AUTH_KEY if no_auth else "runner-key"
    )
    assert (
        captured["model_kwargs"]["base_url"]
        == __import__("os").environ["LNF_NOTEBOOK_API_BASE"]
    )
    monkeypatch.delenv("LNF_NOTEBOOK_LLM_API_KEY", raising=False)
    monkeypatch.setenv("LNF_NOTEBOOK_LLM_NO_AUTH", "false")
    assert namespace["_build_deep_agent"]() is None
    monkeypatch.setitem(sys.modules, "deepagents", None)
    namespace["make_llm"] = lambda: pytest.fail(
        "model constructed without optional SDK"
    )
    assert namespace["_build_deep_agent"]() is None


@pytest.mark.parametrize(
    "message",
    [
        "HTTP Response: GET https://provider.example.com 200 OK Headers(%r)",
        "HTTP Response: POST https://provider.example.com 200 OK headers=%r",
    ],
)
def test_review_sdk_header_message_formats_are_safe(message, caplog):
    import logging

    from langgraph_system_generator.utils.credential_redaction import (
        install_llm_log_redaction,
    )

    caplog.set_level(logging.DEBUG)
    install_llm_log_redaction()
    logging.getLogger("openai._base_client").debug(message, {"x-echo": SERVER_KEY})
    assert caplog.records and SERVER_KEY not in caplog.text


def test_review_standalone_deepagent_keeps_model_override(monkeypatch):
    import sys
    import types

    from langgraph_system_generator.patterns.deepagents import DeepAgentsPattern

    captured = {}

    def create_deep_agent(**kwargs):
        captured.update(kwargs)
        return "standalone-agent"

    monkeypatch.setitem(
        sys.modules,
        "deepagents",
        types.SimpleNamespace(create_deep_agent=create_deep_agent),
    )
    monkeypatch.setenv("OPENAI_API_KEY", "standalone-fake-key")
    monkeypatch.setenv("DEEP_AGENTS_MODEL", "openai:runner-model")
    code = DeepAgentsPattern.generate_agent_node_code(
        model_config={"model": "test-model"}
    )
    assert "make_llm" not in code
    namespace = {"WorkflowState": dict}
    exec(  # noqa: S102 - preserve standalone generated-code behavior with a fake SDK
        compile(code, "standalone-deepagent", "exec"), namespace
    )
    assert namespace["_build_deep_agent"]() == "standalone-agent"
    assert captured["model"] == "openai:runner-model"
