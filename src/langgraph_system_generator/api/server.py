"""FastAPI server exposing generation and health endpoints."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from langgraph_system_generator.cli import GenerationArtifacts, GenerationMode, generate_artifacts

app = FastAPI(title="LangGraph Notebook Foundry API", version="0.1.0")
_BASE_OUTPUT = Path(os.environ.get("LNF_OUTPUT_BASE", ".")).resolve()


class GenerationRequest(BaseModel):
    prompt: str = Field(
        ...,
        description="User prompt describing the desired system",
        max_length=5000,
    )
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

    output_path = Path(request.output_dir).resolve()
    if not output_path.is_relative_to(_BASE_OUTPUT):
        raise HTTPException(status_code=400, detail="output_dir must reside within the allowed base directory.")

    try:
        artifacts: GenerationArtifacts = await generate_artifacts(
            request.prompt,
            output_dir=str(output_path),
            mode=request.mode,
        )
        return GenerationResponse(
            success=True,
            manifest=artifacts["manifest"],
            manifest_path=artifacts["manifest_path"],
        )
    except (RuntimeError, ValueError) as exc:  # pragma: no cover - surfaced via HTTPException
        logging.exception("Generation request failed")
        raise HTTPException(status_code=400, detail=str(exc))
