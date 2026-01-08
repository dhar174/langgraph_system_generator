"""Tests for CLI helpers and FastAPI server integration."""

from __future__ import annotations

from pathlib import Path

import pytest
import httpx
from fastapi.testclient import TestClient

from langgraph_system_generator.api.server import app
from langgraph_system_generator.cli import GenerationArtifacts, generate_artifacts


@pytest.mark.asyncio
async def test_generate_artifacts_stub(tmp_path: Path):
    artifacts: GenerationArtifacts = await generate_artifacts(
        "Test prompt", output_dir=tmp_path, mode="stub"
    )

    assert artifacts["manifest"]["prompt"] == "Test prompt"
    assert artifacts["manifest"]["cell_count"] > 0
    assert Path(artifacts["manifest_path"]).exists()
    assert artifacts["result"]["generation_complete"] is True


@pytest.mark.asyncio
async def test_api_generate_stub(tmp_path: Path):
    transport = httpx.ASGITransport(app=app)
    output_dir = Path.cwd() / "output" / tmp_path.name
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
async def test_api_generate_with_formats(tmp_path: Path):
    """Test API with format selection."""
    transport = httpx.ASGITransport(app=app)
    output_dir = Path.cwd() / "output" / tmp_path.name
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


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


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
async def test_live_mode_requires_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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
