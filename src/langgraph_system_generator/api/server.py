"""FastAPI server exposing generation and health endpoints."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
from typing import Any, Dict, Literal, Optional
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator

from langgraph_system_generator import __version__
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
    emit_log,
    emit_node_progress,
    get_stream_response,
)
from langgraph_system_generator.utils.error_handling import GenerationError
from langgraph_system_generator.utils.generation_options import (
    SUPPORTED_AGENT_TYPES,
    normalize_agent_type,
    normalize_optional_string,
)
from langgraph_system_generator.utils.logging_utils import configure_logging_from_env
from langgraph_system_generator.utils.optional_deps import OptionalDependencyError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app_: FastAPI):  # noqa: ARG001
    """FastAPI lifespan: configure logging at startup, tear down at shutdown."""
    configure_logging_from_env()
    yield


app = FastAPI(
    title="LangGraph Notebook Foundry API",
    version=__version__,
    lifespan=_lifespan,
)

# Mount static files
_STATIC_DIR = Path(__file__).parent / "static"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

_DEFAULT_API_OUTPUT = (_BASE_OUTPUT / "api").resolve()

# Concurrency limit for async generation (prevent resource exhaustion)
_MAX_CONCURRENT_GENERATIONS = int(os.getenv("LNF_MAX_CONCURRENT_GENERATIONS", "5"))
_generation_lock = asyncio.Lock()
_active_generation_count = 0


def _generation_error_payload(exc: Exception) -> dict[str, Any]:
    """Normalize exceptions into a structured API error payload."""

    if isinstance(exc, GenerationError):
        return exc.to_payload()

    if isinstance(exc, OptionalDependencyError):
        payload: dict[str, Any] = {
            "code": "dependency_unavailable",
            "message": str(exc),
            "status_code": 503,
        }
        if exc.hint:
            payload["hint"] = exc.hint
        details = {}
        if exc.dependency:
            details["dependency"] = exc.dependency
        if exc.extra:
            details["extra"] = exc.extra
        if exc.feature:
            details["feature"] = exc.feature
        if details:
            payload["details"] = details
        return payload

    return {
        "code": "generation_error",
        "message": str(exc),
        "status_code": 500,
        "details": {"error_type": type(exc).__name__},
    }


def _raise_generation_http_error(exc: Exception) -> None:
    """Raise an HTTPException from a normalized generation error."""

    payload = _generation_error_payload(exc)
    raise HTTPException(status_code=payload["status_code"], detail=payload)


async def _try_acquire_generation_slot() -> bool:
    """Reserve a generation slot if capacity is available."""
    global _active_generation_count

    async with _generation_lock:
        if _active_generation_count >= _MAX_CONCURRENT_GENERATIONS:
            return False
        _active_generation_count += 1
        return True


async def _release_generation_slot() -> None:
    """Release a previously reserved generation slot."""
    global _active_generation_count

    async with _generation_lock:
        if _active_generation_count > 0:
            _active_generation_count -= 1


async def _acquire_generation_slot_or_raise() -> None:
    """Acquire a generation slot or raise when capacity is exhausted."""
    if not await _try_acquire_generation_slot():
        raise HTTPException(
            status_code=503,
            detail=(
                "Server is currently processing the maximum number of "
                f"concurrent generations ({_MAX_CONCURRENT_GENERATIONS}). "
                "Please try again later."
            ),
        )


@asynccontextmanager
async def _generation_slot():
    """Guard a request with the shared generation admission controller."""
    await _acquire_generation_slot_or_raise()
    try:
        yield
    finally:
        await _release_generation_slot()


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
            detail="Artifact path must reside within the allowed base directory.",
        ) from exc

    if not artifact_path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found.")

    return artifact_path


def _validate_advanced_options(
    request: "GenerationRequest",
) -> tuple[str | None, str | None, str | None]:
    """Normalize and validate supported advanced options."""
    normalized_model = normalize_optional_string(request.model)
    normalized_custom_endpoint = normalize_optional_string(request.custom_endpoint)
    normalized_agent_type = normalize_agent_type(request.agent_type)

    if normalized_agent_type and normalized_agent_type not in SUPPORTED_AGENT_TYPES:
        supported = ", ".join(sorted(SUPPORTED_AGENT_TYPES))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported agent_type. Supported values are: {supported}.",
        )

    if normalized_custom_endpoint and normalized_model in (None, "custom"):
        raise HTTPException(
            status_code=400,
            detail="custom_endpoint requires an explicit OpenAI-compatible model identifier.",
        )

    if normalized_custom_endpoint:
        parsed_endpoint = urlparse(normalized_custom_endpoint)
        if (
            parsed_endpoint.scheme not in {"http", "https"}
            or not parsed_endpoint.hostname
        ):
            raise HTTPException(
                status_code=400,
                detail="custom_endpoint must be a valid http or https URL with a hostname.",
            )

    if normalized_model == "custom":
        raise HTTPException(
            status_code=400,
            detail="Provide an explicit model identifier instead of the placeholder value 'custom'.",
        )

    return normalized_model, normalized_custom_endpoint, normalized_agent_type


def _normalize_request(request: "GenerationRequest") -> "GenerationRequest":
    """Return a copy of the request with normalized advanced option values."""
    normalized_model, normalized_custom_endpoint, normalized_agent_type = (
        _validate_advanced_options(request)
    )
    return request.model_copy(
        update={
            "model": normalized_model,
            "custom_endpoint": normalized_custom_endpoint,
            "agent_type": normalized_agent_type,
        }
    )


def _request_dialog_messages(
    request: "GenerationRequest",
) -> list[dict[str, str]] | None:
    """Return normalized dialog messages for iterative requirements refinement."""

    if not request.messages:
        return None
    return [message.model_dump() for message in request.messages]


def _request_prompt(request: "GenerationRequest") -> str:
    """Return the single prompt value used by legacy generation surfaces."""

    if request.prompt:
        return request.prompt
    messages = request.messages or []
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return messages[-1].content if messages else ""


class DialogMessage(BaseModel):
    """One requirements dialog turn accepted by the API."""

    role: Literal["system", "user", "assistant"] = Field(
        description="Dialog role for this requirements turn."
    )
    content: str = Field(
        ...,
        description="Message content for this requirements turn.",
        max_length=5000,
    )


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: Optional[str] = Field(
        default=None,
        description="User prompt describing the desired system",
        max_length=5000,
    )
    messages: Optional[list[DialogMessage]] = Field(
        default=None,
        description=(
            "Optional multi-turn requirements dialog. When provided, live intake "
            "refines constraints across these turns while prompt remains the "
            "legacy request summary."
        ),
        max_length=50,
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
        description=(
            "List of output formats to generate (ipynb, html, markdown, pdf, docx, zip). "
            "If not specified, generates the default export set: ipynb, html, markdown, docx, zip."
        ),
    )
    # Advanced options
    model: Optional[str] = Field(
        default=None,
        description="OpenAI-compatible model to use for generation. Uses the default OpenAI-compatible model if not specified.",
    )
    custom_endpoint: Optional[str] = Field(
        default=None,
        description="Custom OpenAI-compatible API endpoint URL for self-hosted or proxy deployments.",
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
        description="Type of agent architecture (router, subagents, hybrid, autoagent, deepagents, etc.) when overriding auto-detection.",
    )

    @model_validator(mode="after")
    def _require_prompt_or_messages(self) -> "GenerationRequest":
        """Require either a legacy prompt or at least one dialog message."""

        if not (self.prompt and self.prompt.strip()) and not self.messages:
            raise ValueError("Either prompt or messages must be provided.")
        return self


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
    normalized_request = _normalize_request(request)
    prompt = _request_prompt(normalized_request)
    requirements_messages = _request_dialog_messages(normalized_request)

    # Use the secure path resolution function
    output_path = _resolve_output_dir(request.output_dir)

    async with _generation_slot():
        try:
            artifacts: GenerationArtifacts = await generate_artifacts(
                prompt,
                output_dir=str(output_path),
                mode=request.mode,
                formats=request.formats,
                model=normalized_request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                agent_type=normalized_request.agent_type,
                custom_endpoint=normalized_request.custom_endpoint,
                requirements_messages=requirements_messages,
            )
            return GenerationResponse(
                success=True,
                mode=artifacts["mode"],
                prompt=artifacts["prompt"],
                manifest=artifacts["manifest"],
                manifest_path=artifacts["manifest_path"],
                output_dir=artifacts["output_dir"],
            )
        except (GenerationError, OptionalDependencyError) as exc:
            logger.exception("Generation request failed for /generate")
            _raise_generation_http_error(exc)
        except ValueError as exc:  # pragma: no cover - surfaced via HTTPException
            logger.exception("Generation request failed for /generate")
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Generation request failed for /generate")
            _raise_generation_http_error(exc)


@app.post("/generate-async", response_model=GenerationStartResponse)
async def start_async_generation(
    request: GenerationRequest,
) -> GenerationStartResponse:
    """Start async notebook generation with SSE progress tracking.

    This endpoint starts generation in the background and returns immediately with
    a job ID. Clients can then connect to the SSE stream endpoint to receive
    real-time progress updates, logs, and the final result.

    Concurrency is limited with an explicit admission controller. If the limit is
    reached, the request is rejected with 503 Service Unavailable.

    Returns:
        GenerationStartResponse with job_id and stream_url

    Raises:
        HTTPException 503: When concurrent generation limit is reached
    """
    normalized_request = _normalize_request(request)
    output_path = _resolve_output_dir(request.output_dir)

    # Acquire capacity before the job is accepted so overload requests fail fast.
    await _acquire_generation_slot_or_raise()

    # Create job and start generation task
    job_id = create_job()

    try:
        asyncio.create_task(
            _run_generation_with_progress(job_id, normalized_request, output_path)
        )
    except Exception:
        await _release_generation_slot()
        raise

    return GenerationStartResponse(
        job_id=job_id,
        stream_url=f"/stream/{job_id}",
        status="started",
    )


@app.get("/stream/{job_id}")
async def stream_job_progress(job_id: str, request: Request):
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
    return get_stream_response(job_id, request.headers.get("Last-Event-ID"))


async def _run_generation_with_progress(
    job_id: str,
    request: GenerationRequest,
    output_path: Path,
) -> None:
    """Run generation task with progress tracking.

    This function orchestrates the generation process and emits progress events
    to the SSE stream. It wraps generate_artifacts() and adds instrumentation.

    Uses the API admission controller to limit concurrent generations and prevent
    resource exhaustion.

    Args:
        job_id: Job identifier for progress tracking
        request: Generation request parameters
        output_path: Resolved output directory path
    """
    try:
        # Emit start event
        emit_node_progress(job_id, "start", 0, "Starting generation...")

        # Emit validation progress
        emit_node_progress(job_id, "validation", 5, "Validating request...")

        # Run generation
        emit_node_progress(job_id, "generation", 10, "Initializing generator...")

        def progress_callback(
            event: Any, percentage: int | None = None, message: str | None = None
        ) -> None:
            """Forward progress to SSE stream."""
            if isinstance(event, dict):
                event_type = event.get("event", "progress")
                phase = event.get("phase") or event.get("node") or "generation"
                event_message = event.get("message", "")
                if event_type == "log":
                    emit_log(
                        job_id,
                        event.get("status", "info"),
                        event_message,
                        details={
                            "phase": phase,
                            "details": event.get("details", {}),
                        },
                    )
                else:
                    emit_node_progress(
                        job_id,
                        phase,
                        int(event.get("percentage", 0)),
                        event_message,
                        status=event.get("status", "running"),
                    )
                return

            emit_node_progress(job_id, str(event), int(percentage or 0), message or "")

        prompt = _request_prompt(request)
        requirements_messages = _request_dialog_messages(request)
        artifacts: GenerationArtifacts = await generate_artifacts(
            prompt,
            output_dir=str(output_path),
            mode=request.mode,
            formats=request.formats,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            agent_type=request.agent_type,
            custom_endpoint=request.custom_endpoint,
            requirements_messages=requirements_messages,
            progress_callback=progress_callback,
        )

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
        logger.exception("Generation failed for async job %s", job_id)
        payload = _generation_error_payload(exc)
        emit_log(
            job_id,
            "error",
            payload["message"],
            details={
                "phase": payload.get("phase"),
                "code": payload.get("code"),
                "hint": payload.get("hint"),
                "details": payload.get("details", {}),
            },
        )
        emit_error(
            job_id,
            payload["message"],
            {
                "type": type(exc).__name__,
                "code": payload.get("code"),
                "phase": payload.get("phase"),
                "hint": payload.get("hint"),
                "status_code": payload.get("status_code"),
                "details": payload.get("details", {}),
            },
        )
    finally:
        await _release_generation_slot()
