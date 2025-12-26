"""Tests for CLI helpers and FastAPI server integration."""

from __future__ import annotations

from pathlib import Path

import pytest
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


def test_api_generate_stub(tmp_path: Path):
    client = TestClient(app)
    response = client.post(
        "/generate",
        json={
            "prompt": "API prompt",
            "mode": "stub",
            "output_dir": str(tmp_path),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["manifest"]["prompt"] == "API prompt"
    assert "manifest_path" in payload


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
