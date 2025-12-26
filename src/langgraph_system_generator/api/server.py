"""FastAPI server exposing generation and health endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Literal, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from langgraph_system_generator.cli import GenerationArtifacts, GenerationMode, generate_artifacts

app = FastAPI(title="LangGraph Notebook Foundry API", version="0.1.0")


class GenerationRequest(BaseModel):
    prompt: str = Field(..., description="User prompt describing the desired system")
    mode: GenerationMode = Field(
        default="stub",
        description="Generation mode. Use 'stub' to avoid external API calls.",
    )
    output_dir: str = Field(
        default="./output/api",
        description="Directory to write generation artifacts.",
    )


class GenerationResponse(BaseModel):
    success: bool
    manifest: Optional[Dict[str, Any]] = None
    manifest_path: Optional[str] = None
    error: Optional[str] = None


@app.get("/health")
async def health() -> Dict[str, str]:
    """Simple health check."""

    return {"status": "ok"}


@app.post("/generate", response_model=GenerationResponse)
async def generate_notebook(request: GenerationRequest) -> GenerationResponse:
    """Generate notebook artifacts via the generator pipeline."""

    try:
        artifacts: GenerationArtifacts = await generate_artifacts(
            request.prompt,
            output_dir=request.output_dir,
            mode=request.mode,
        )
        return GenerationResponse(
            success=True,
            manifest=artifacts["manifest"],
            manifest_path=artifacts["manifest_path"],
        )
    except Exception as exc:  # pragma: no cover - surfaced via HTTPException
        raise HTTPException(status_code=400, detail=str(exc))
