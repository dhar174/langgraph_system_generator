"""Tests for CLI helpers and FastAPI server integration."""

from __future__ import annotations

from pathlib import Path
import json

import pytest
import httpx
from fastapi.testclient import TestClient

from langgraph_system_generator.api.server import app
from langgraph_system_generator.cli import GenerationArtifacts, generate_artifacts


@pytest.mark.asyncio
async def test_generate_artifacts_stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Set a test output base
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_generate_artifacts_stub")

    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)

    # Use path within OUTPUT_BASE
    output_dir = constants_module._BASE_OUTPUT / "test_stub"
    artifacts: GenerationArtifacts = await cli_module.generate_artifacts(
        "Test prompt", output_dir=str(output_dir), mode="stub"
    )

    assert artifacts["manifest"]["prompt"] == "Test prompt"
    assert artifacts["manifest"]["cell_count"] > 0
    assert Path(artifacts["manifest_path"]).exists()
    assert artifacts["result"]["generation_complete"] is True


@pytest.mark.asyncio
async def test_generate_artifacts_default_formats_include_markdown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_generate_artifacts_default_formats")

    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)

    output_dir = constants_module._BASE_OUTPUT / "default_formats"
    artifacts: GenerationArtifacts = await cli_module.generate_artifacts(
        "Test prompt", output_dir=str(output_dir), mode="stub"
    )

    assert "markdown_path" in artifacts["manifest"]
    assert Path(artifacts["manifest"]["markdown_path"]).exists()


@pytest.mark.asyncio
async def test_api_generate_stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Set a test output base
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_api_stub")

    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.api.server as server_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(server_module)

    transport = httpx.ASGITransport(app=server_module.app)
    output_dir = constants_module._BASE_OUTPUT / tmp_path.name
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/generate",
            json={
                "prompt": "API prompt",
                "mode": "stub",
                "output_dir": str(output_dir),
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["manifest"]["prompt"] == "API prompt"
    assert "manifest_path" in payload
    # Verify new response fields
    assert payload["mode"] == "stub"
    assert payload["prompt"] == "API prompt"
    assert "output_dir" in payload
    assert payload["output_dir"] == str(output_dir)


@pytest.mark.asyncio
async def test_api_rejects_unsupported_advanced_options(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_api_unsupported_options")

    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.api.server as server_module

    importlib.reload(constants_module)
    importlib.reload(server_module)

    transport = httpx.ASGITransport(app=server_module.app)
    output_dir = constants_module._BASE_OUTPUT / tmp_path.name
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/generate",
            json={
                "prompt": "API prompt",
                "mode": "stub",
                "output_dir": str(output_dir),
                "memory_config": "short",
            },
        )

    assert response.status_code == 400
    assert "Unsupported advanced options" in response.json()["detail"]


@pytest.mark.asyncio
async def test_api_accepts_arbitrary_openai_compatible_model_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Built-in provider should accept explicit model identifiers without an allowlist."""
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_api_arbitrary_model")

    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.api.server as server_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(server_module)

    transport = httpx.ASGITransport(app=server_module.app)
    output_dir = constants_module._BASE_OUTPUT / tmp_path.name
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/generate",
            json={
                "prompt": "API prompt",
                "mode": "stub",
                "output_dir": str(output_dir),
                "model": "gpt-5-future-release",
            },
        )

    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.asyncio
async def test_api_rejects_custom_endpoint_without_explicit_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Custom endpoints must include a non-placeholder model identifier."""
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_api_custom_endpoint_requires_model")

    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.api.server as server_module

    importlib.reload(constants_module)
    importlib.reload(server_module)

    transport = httpx.ASGITransport(app=server_module.app)
    output_dir = constants_module._BASE_OUTPUT / tmp_path.name
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/generate",
            json={
                "prompt": "API prompt",
                "mode": "stub",
                "output_dir": str(output_dir),
                "custom_endpoint": "https://example.test/v1",
            },
        )

    assert response.status_code == 400
    assert (
        "custom_endpoint requires an explicit OpenAI-compatible model identifier"
        in response.json()["detail"]
    )


@pytest.mark.asyncio
async def test_api_generate_with_formats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test API with format selection."""
    # Set a test output base
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_api_formats")

    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.api.server as server_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(server_module)

    transport = httpx.ASGITransport(app=server_module.app)
    output_dir = constants_module._BASE_OUTPUT / tmp_path.name
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/generate",
            json={
                "prompt": "Test with formats",
                "mode": "stub",
                "output_dir": str(output_dir),
                "formats": ["ipynb", "html"],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["manifest"]["prompt"] == "Test with formats"

    # Verify selected formats are in manifest
    assert "notebook_path" in payload["manifest"]
    assert "html_path" in payload["manifest"]

    # Verify unselected formats are NOT in manifest
    assert "docx_path" not in payload["manifest"]
    assert "pdf_path" not in payload["manifest"]


@pytest.mark.asyncio
async def test_api_download_artifact_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test downloading a generated artifact through the API."""
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_api_artifact_download")

    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.cli as cli_module
    import langgraph_system_generator.api.server as server_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(cli_module)
    importlib.reload(server_module)

    artifacts = await cli_module.generate_artifacts(
        "Artifact download prompt",
        output_dir=str(constants_module._BASE_OUTPUT / tmp_path.name),
        mode="stub",
        formats=["ipynb"],
    )

    transport = httpx.ASGITransport(app=server_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/artifacts",
            params={"path": artifacts["manifest"]["notebook_path"]},
        )

    assert response.status_code == 200
    assert "notebook.ipynb" in response.headers.get("content-disposition", "")
    assert response.content


@pytest.mark.asyncio
async def test_api_download_artifact_rejects_invalid_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test artifact download rejects paths outside the trusted base."""
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_api_artifact_reject")

    import importlib
    import langgraph_system_generator.api.server as server_module

    importlib.reload(server_module)

    transport = httpx.ASGITransport(app=server_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/artifacts", params={"path": str(tmp_path / ".." / "escape.txt")})

    assert response.status_code == 400
    assert "allowed base directory" in response.json()["detail"]


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_chrome_devtools_endpoint():
    """Test that Chrome DevTools endpoint returns 204 No Content."""
    client = TestClient(app)
    response = client.get("/.well-known/appspecific/com.chrome.devtools.json")
    assert response.status_code == 204
    # 204 responses should have no content
    assert response.content == b""


def test_root_endpoint_with_static_files():
    """Test that root endpoint serves the web interface when static files exist."""
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    # Should return HTML content
    assert "text/html" in response.headers.get("content-type", "")
    # Check for key elements from index.html with expected casing
    content = response.text
    assert "LangGraph" in content and "System Generator" in content


@pytest.mark.asyncio
async def test_live_mode_requires_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # Set BASE_OUTPUT_DIR to allow test output in tmp_path
    monkeypatch.setenv("BASE_OUTPUT_DIR", str(tmp_path.resolve()))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        await generate_artifacts("Live prompt", output_dir=tmp_path, mode="live")


@pytest.mark.asyncio
async def test_api_rejects_disallowed_output_dir(tmp_path: Path):
    outside = tmp_path.parent
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/generate",
            json={
                "prompt": "Traversal attempt",
                "mode": "stub",
                "output_dir": str(outside),
            },
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_api_generate_async_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test /generate-async endpoint returns job_id and stream_url."""
    # Set a test output base
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_api_async")

    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.api.server as server_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(server_module)

    transport = httpx.ASGITransport(app=server_module.app)
    output_dir = constants_module._BASE_OUTPUT / tmp_path.name
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/generate-async",
            json={
                "prompt": "Test async generation",
                "mode": "stub",
                "output_dir": str(output_dir),
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert "job_id" in payload
    assert "stream_url" in payload
    assert payload["status"] == "started"
    assert payload["stream_url"].startswith("/stream/")


@pytest.mark.asyncio
async def test_api_stream_endpoint_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test /stream/{job_id} endpoint returns error for non-existent job."""
    # Set a test output base
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_stream_notfound")

    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.api.server as server_module

    importlib.reload(server_module)

    transport = httpx.ASGITransport(app=server_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Try to stream a non-existent job
        async with client.stream("GET", "/stream/nonexistent-job-id") as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")
            
            # Read first event which should be an error
            events = []
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    event_type = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data = line.split(":", 1)[1].strip()
                    events.append({"event": event_type, "data": json.loads(data)})
                    break
            
            assert len(events) > 0
            assert events[0]["event"] == "error"
            assert "not found" in events[0]["data"]["error"].lower()


@pytest.mark.asyncio
async def test_api_generate_async_with_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test full async generation flow with SSE stream consumption."""
    # Set a test output base
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_async_stream")

    # Force module reload to pick up new env var
    import importlib
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.notebook.exporters as exporters_module
    import langgraph_system_generator.api.server as server_module
    import langgraph_system_generator.api.progress_streaming as progress_module

    importlib.reload(constants_module)
    importlib.reload(exporters_module)
    importlib.reload(progress_module)
    importlib.reload(server_module)

    transport = httpx.ASGITransport(app=server_module.app)
    output_dir = constants_module._BASE_OUTPUT / tmp_path.name
    
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Start async generation
        response = await client.post(
            "/generate-async",
            json={
                "prompt": "Test streaming generation",
                "mode": "stub",
                "output_dir": str(output_dir),
                "formats": ["ipynb"],
            },
        )
        
        assert response.status_code == 200
        payload = response.json()
        stream_url = payload["stream_url"]
        
        # Connect to SSE stream
        events = []
        async with client.stream("GET", stream_url, timeout=30.0) as stream_response:
            assert stream_response.status_code == 200
            
            # Parse SSE events
            event_type = None
            async for line in stream_response.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                    
                if line.startswith("event:"):
                    event_type = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data = line.split(":", 1)[1].strip()
                    events.append({"event": event_type, "data": json.loads(data)})
                    
                    # Stop after complete or error
                    if event_type in ("complete", "error"):
                        break
        
        # Verify we got events
        assert len(events) > 0, "Should receive at least one event"
        
        # Check for progress events
        progress_events = [e for e in events if e["event"] == "progress"]
        assert len(progress_events) > 0, "Should receive progress events"
        
        # Check for completion
        complete_events = [e for e in events if e["event"] == "complete"]
        assert len(complete_events) == 1, "Should have exactly one complete event"
        
        # Verify completion data
        final_result = complete_events[0]["data"]
        assert final_result.get("success") is True
        assert final_result.get("mode") == "stub"
        assert "manifest" in final_result


@pytest.mark.asyncio
async def test_api_generate_async_concurrency_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test that /generate-async respects concurrency limits."""
    monkeypatch.setenv("LNF_MAX_CONCURRENT_GENERATIONS", "1")
    monkeypatch.setenv("LNF_OUTPUT_BASE", "test_concurrency")

    import importlib
    import asyncio as aio
    import langgraph_system_generator.constants as constants_module
    import langgraph_system_generator.api.server as server_module

    importlib.reload(constants_module)
    importlib.reload(server_module)

    gate = aio.Event()

    async def slow_generate_artifacts(*_args, **_kwargs):
        await gate.wait()
        return {
            "mode": "stub",
            "prompt": "slow",
            "manifest": {},
            "manifest_path": str(constants_module._BASE_OUTPUT / "manifest.json"),
            "output_dir": str(constants_module._BASE_OUTPUT / tmp_path.name / "gen1"),
        }

    monkeypatch.setattr(server_module, "generate_artifacts", slow_generate_artifacts)
    server_module._active_generation_count = 0

    transport = httpx.ASGITransport(app=server_module.app)
    output_dir = constants_module._BASE_OUTPUT / tmp_path.name

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response1 = await client.post(
            "/generate-async",
            json={
                "prompt": "Test concurrent generation 1",
                "mode": "stub",
                "output_dir": str(output_dir / "gen1"),
            },
        )
        assert response1.status_code == 200

        response2 = await client.post(
            "/generate-async",
            json={
                "prompt": "Test concurrent generation 2",
                "mode": "stub",
                "output_dir": str(output_dir / "gen2"),
            },
        )

        assert response2.status_code == 503
        gate.set()
        await aio.sleep(0.05)
