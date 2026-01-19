"""FastAPI server exposing generation and health endpoints."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from langgraph_system_generator.cli import GenerationArtifacts, GenerationMode, generate_artifacts
from langgraph_system_generator.constants import _BASE_OUTPUT

app = FastAPI(title="LangGraph Notebook Foundry API", version="0.1.1")

# Mount static files
_STATIC_DIR = Path(__file__).parent / "static"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

_DEFAULT_API_OUTPUT = (_BASE_OUTPUT / "api").resolve()
_BASE_OUTPUT_RESOLVED = _BASE_OUTPUT.resolve()


def _default_api_output_dir() -> str:
    return str((_BASE_OUTPUT_RESOLVED / "api").resolve())


def _resolve_output_dir(path: str | os.PathLike[str]) -> Path:
    """Resolve and validate an output directory under the trusted base root."""
    base_root = _BASE_OUTPUT_RESOLVED  # cached absolute base path
    target = Path(path)
    if not target.is_absolute():
        target = (base_root / target).resolve()
    else:
        target = target.resolve()

    try:
        is_relative = target.is_relative_to(base_root)  # type: ignore[attr-defined]  # Python 3.9+ only; fallback below
    except AttributeError:
        try:
            target.relative_to(base_root)
            is_relative = True
        except ValueError:
            is_relative = False

    if not is_relative:
        raise HTTPException(
            status_code=400,
            detail="output_dir must reside within the allowed base directory.",
        )
    return target


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
        default_factory=_default_api_output_dir,
        description=(
            "Directory to write generation artifacts. Defaults to the application's "
            "base output directory under 'output/api' (absolute path resolved at runtime)."
        ),
    )
    formats: Optional[list[str]] = Field(
        default=None,
        description="List of output formats to generate (ipynb, html, pdf, docx, zip). Generates all if not specified.",
    )
    # Advanced options
    model: Optional[str] = Field(
        default=None,
        description="LLM model to use (e.g., gpt-4, gpt-3.5-turbo, claude-3-opus, etc.). Uses default if not specified.",
    )
    custom_endpoint: Optional[str] = Field(
        default=None,
        description="Custom API endpoint URL for self-hosted or alternative LLM providers.",
    )
    preset: Optional[str] = Field(
        default=None,
        description="Task preset (code-generation, data-analysis, customer-support, etc.) for optimized settings.",
    )
    temperature: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description=(
            "Temperature for LLM sampling. This API accepts values from 0.0 to 2.0, "
            "but the actual allowed range depends on the selected model/provider "
            "(e.g., some Claude models only support 0.0-1.0). Higher values make "
            "output more random, and values outside a provider's supported range "
            "may cause downstream API errors."
        ),
    )
    max_tokens: Optional[int] = Field(
        default=None,
        ge=1,
        le=32768,
        description="Maximum tokens for LLM response. Controls output length and must not exceed the model's context window (capped at 32768 here).",
    )
    agent_type: Optional[str] = Field(
        default=None,
        description="Type of agent architecture (router, subagents, hybrid, etc.).",
    )
    memory_config: Optional[str] = Field(
        default=None,
        description="Memory configuration for the agent (none, short, long, full).",
    )
    graph_style: Optional[str] = Field(
        default=None,
        description="Graph execution style (sequential, parallel, conditional, cyclic).",
    )
    retriever_type: Optional[str] = Field(
        default=None,
        description="Document retriever type for RAG (vector, keyword, hybrid, mmr).",
    )
    document_loader: Optional[str] = Field(
        default=None,
        description="Document loader type (text, pdf, web, markdown, json, csv).",
    )


class GenerationResponse(BaseModel):
    success: bool
    mode: Optional[str] = None
    prompt: Optional[str] = None  # Note: User prompt echoed back for confirmation; may contain sensitive data if logged
    manifest: Optional[Dict[str, Any]] = None
    manifest_path: Optional[str] = None
    output_dir: Optional[str] = None
    error: Optional[str] = None


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the web interface."""
    if _STATIC_DIR.exists():
        index_path = _STATIC_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
    return HTMLResponse(content="<h1>LangGraph System Generator API</h1><p>Web interface not found. Use POST /generate to create systems.</p>")


@app.get("/health")
async def health() -> Dict[str, str]:
    """Simple health check."""

    return {"status": "ok"}


@app.get("/.well-known/appspecific/com.chrome.devtools.json")
async def chrome_devtools_endpoint():
    """Handle Chrome DevTools endpoint request.
    
    Chrome automatically requests this endpoint to check for DevTools support.
    Return 204 No Content to indicate the endpoint is recognized but we don't
    provide DevTools-specific features.
    """
    return Response(status_code=204)


@app.post("/generate", response_model=GenerationResponse)
async def generate_notebook(request: GenerationRequest) -> GenerationResponse:
    """Generate notebook artifacts via the generator pipeline."""

    output_path = _resolve_output_dir(request.output_dir)

    try:
        artifacts: GenerationArtifacts = await generate_artifacts(
            request.prompt,
            output_dir=str(output_path),
            mode=request.mode,
            formats=request.formats,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            agent_type=request.agent_type,
            memory_config=request.memory_config,
            custom_endpoint=request.custom_endpoint,
            preset=request.preset,
            graph_style=request.graph_style,
            retriever_type=request.retriever_type,
            document_loader=request.document_loader,
        )
        return GenerationResponse(
            success=True,
            mode=artifacts["mode"],
            prompt=artifacts["prompt"],
            manifest=artifacts["manifest"],
            manifest_path=artifacts["manifest_path"],
            output_dir=artifacts["output_dir"],
        )
    except (RuntimeError, ValueError) as exc:  # pragma: no cover - surfaced via HTTPException
        logging.exception("Generation request failed")
        raise HTTPException(status_code=400, detail=str(exc))
