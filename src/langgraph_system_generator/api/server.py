"""FastAPI server exposing generation and health endpoints."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from langgraph_system_generator.constants import _BASE_OUTPUT, resolve_under_base
from langgraph_system_generator.cli import (
    GenerationArtifacts,
    GenerationMode,
    generate_artifacts,
)
from langgraph_system_generator.api.progress_streaming import (
    create_job,
    emit_complete,
    emit_error,
    emit_node_progress,
    get_stream_response,
)

app = FastAPI(title="LangGraph Notebook Foundry API", version="0.1.1")

# Mount static files
_STATIC_DIR = Path(__file__).parent / "static"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

_DEFAULT_API_OUTPUT = (_BASE_OUTPUT / "api").resolve()

# Concurrency limit for async generation (prevent resource exhaustion)
_MAX_CONCURRENT_GENERATIONS = int(os.getenv("LNF_MAX_CONCURRENT_GENERATIONS", "5"))
_generation_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_GENERATIONS)


def _resolve_output_dir(path: str | os.PathLike[str] | None) -> Path:
    """Resolve and validate an output directory under the trusted base root.

    All user-provided paths are treated as relative to the base directory,
    providing defense-in-depth against path traversal attacks.
    """
    base = _BASE_OUTPUT.resolve()

    # If no path is provided, default to the API output directory under the base.
    if not path:
        return _DEFAULT_API_OUTPUT

    # Treat path as relative to base (safer approach that prevents absolute path injection)
    target = (base / path).resolve()

    # Ensure the resolved target is still within base (prevents .. escapes)
    try:
        target.relative_to(base)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="output_dir must reside within the allowed base directory.",
        )

    return target


def _resolve_artifact_path(path: str | os.PathLike[str]) -> Path:
    """Resolve and validate an artifact path under the trusted base output root."""
    try:
        artifact_path = resolve_under_base(Path(path))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="artifact path must reside within the allowed base directory.",
        ) from exc

    if not artifact_path.is_file():
        raise HTTPException(status_code=404, detail="artifact not found.")

    return artifact_path


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
    prompt: Optional[str] = (
        None  # Note: User prompt echoed back for confirmation; may contain sensitive data if logged
    )
    manifest: Optional[Dict[str, Any]] = None
    manifest_path: Optional[str] = None
    output_dir: Optional[str] = None
    error: Optional[str] = None


class GenerationStartResponse(BaseModel):
    """Response when starting async generation with SSE progress tracking."""

    job_id: str = Field(..., description="Unique job identifier for tracking progress")
    stream_url: str = Field(
        ..., description="SSE endpoint URL for streaming progress updates"
    )
    status: str = Field(
        default="started", description="Initial status (always 'started')"
    )


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the web interface."""
    if _STATIC_DIR.exists():
        index_path = _STATIC_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
    return HTMLResponse(
        content="<h1>LangGraph System Generator API</h1><p>Web interface not found. Use POST /generate to create systems.</p>"
    )


@app.get("/health")
async def health() -> Dict[str, str]:
    """Simple health check."""

    return {"status": "ok"}


@app.get("/artifacts")
async def download_artifact(
    path: str = Query(..., description="Artifact path returned by the generation API"),
):
    """Download a generated artifact from the trusted output directory."""
    artifact_path = _resolve_artifact_path(path)
    return FileResponse(artifact_path, filename=artifact_path.name)


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

    # Use the secure path resolution function
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
    except (
        RuntimeError,
        ValueError,
    ) as exc:  # pragma: no cover - surfaced via HTTPException
        logging.exception("Generation request failed")
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/generate-async", response_model=GenerationStartResponse)
async def start_async_generation(
    request: GenerationRequest,
) -> GenerationStartResponse:
    """Start async notebook generation with SSE progress tracking.

    This endpoint starts generation in the background and returns immediately with
    a job ID. Clients can then connect to the SSE stream endpoint to receive
    real-time progress updates, logs, and the final result.
    
    Concurrency is limited to prevent resource exhaustion. If the limit is reached,
    returns 503 Service Unavailable.

    Returns:
        GenerationStartResponse with job_id and stream_url
        
    Raises:
        HTTPException 503: When concurrent generation limit is reached
    """
    # Validate output directory
    output_path = _resolve_output_dir(request.output_dir)

    # Check if we can accept more jobs (non-blocking check)
    if _generation_semaphore.locked() and _generation_semaphore._value == 0:
        raise HTTPException(
            status_code=503,
            detail=f"Server is currently processing the maximum number of concurrent generations ({_MAX_CONCURRENT_GENERATIONS}). Please try again later.",
        )

    # Create job and start generation task
    job_id = create_job()

    # Start generation in background
    asyncio.create_task(_run_generation_with_progress(job_id, request, output_path))

    return GenerationStartResponse(
        job_id=job_id,
        stream_url=f"/stream/{job_id}",
        status="started",
    )


@app.get("/stream/{job_id}")
async def stream_job_progress(job_id: str):
    """Server-Sent Events endpoint for streaming job progress.

    Connect to this endpoint with EventSource to receive real-time progress updates:
    - 'progress' events: Node progress with percentage and message
    - 'log' events: Log messages during generation
    - 'complete' event: Final result when generation succeeds
    - 'error' event: Error details if generation fails

    Args:
        job_id: Unique job identifier from /generate-async

    Returns:
        EventSourceResponse: SSE stream
    """
    return get_stream_response(job_id)


async def _run_generation_with_progress(
    job_id: str,
    request: GenerationRequest,
    output_path: Path,
) -> None:
    """Run generation task with progress tracking.

    This function orchestrates the generation process and emits progress events
    to the SSE stream. It wraps generate_artifacts() and adds instrumentation.
    
    Uses a semaphore to limit concurrent generations and prevent resource exhaustion.

    Args:
        job_id: Job identifier for progress tracking
        request: Generation request parameters
        output_path: Resolved output directory path
    """
    # Acquire semaphore to limit concurrency
    async with _generation_semaphore:
        try:
            # Emit start event
            emit_node_progress(job_id, "start", 0, "Starting generation...")

            # Emit validation progress
            emit_node_progress(job_id, "validation", 5, "Validating request...")

            # Run generation
            # TODO: Pass job_id to generate_artifacts for node-level progress
            emit_node_progress(job_id, "generation", 10, "Initializing generator...")

            # Define progress callback for generate_artifacts
            def progress_callback(node: str, percentage: int, message: str) -> None:
                """Forward progress to SSE stream."""
                emit_node_progress(job_id, node, percentage, message)

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
                progress_callback=progress_callback,
            )

            # Emit completion with result
            emit_complete(
                job_id,
                {
                    "success": True,
                    "mode": artifacts["mode"],
                    "prompt": artifacts["prompt"],
                    "manifest": artifacts["manifest"],
                    "manifest_path": artifacts["manifest_path"],
                    "output_dir": artifacts["output_dir"],
                },
            )

        except Exception as exc:
            logging.exception(f"Generation failed for job {job_id}")
            emit_error(
                job_id,
                str(exc),
                {"type": type(exc).__name__},
            )
