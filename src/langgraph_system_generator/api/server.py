"""FastAPI server exposing generation and health endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
from collections.abc import Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, NoReturn
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from langgraph_system_generator import __version__
from langgraph_system_generator.api import durable
from langgraph_system_generator.api.progress_streaming import (
    JobCapacityError,
    _prune_expired_jobs,
    create_job,
    discard_job,
    emit_complete,
    emit_error,
    emit_log,
    emit_node_progress,
    get_job_status,
    get_stream_response,
    mark_job_running,
    register_owned_task,
    shutdown_owned_tasks,
)
from langgraph_system_generator.cli import (
    GenerationArtifacts,
    GenerationMode,
    generate_artifacts,
)
from langgraph_system_generator.constants import _BASE_OUTPUT
from langgraph_system_generator.jobs.models import JobError
from langgraph_system_generator.jobs.registry import (
    backend_name,
    require_ephemeral_admission,
)
from langgraph_system_generator.utils.credential_redaction import (
    _sanitize_text_credentials,
)
from langgraph_system_generator.utils.error_handling import GenerationError
from langgraph_system_generator.utils.generation_options import (
    SUPPORTED_AGENT_TYPES,
    normalize_agent_type,
    normalize_optional_string,
)
from langgraph_system_generator.utils.llm_endpoint_security import authorize_endpoint
from langgraph_system_generator.utils.logging_utils import configure_logging_from_env
from langgraph_system_generator.utils.optional_deps import OptionalDependencyError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app_: FastAPI):
    """Configure bounded cleanup and cancel owned jobs at application shutdown."""
    global _shutting_down
    configure_logging_from_env()
    _shutting_down = False
    cleanup_task = asyncio.create_task(_cleanup_process_local_state())
    try:
        yield
    finally:
        _shutting_down = True
        cleanup_task.cancel()
        try:
            await asyncio.wait_for(cleanup_task, timeout=1.0)
        except (  # noqa: UP041 - Python 3.10
            asyncio.CancelledError,
            asyncio.TimeoutError,
        ):
            cleanup_task.cancel()
        await shutdown_owned_tasks(timeout=5.0)


app = FastAPI(
    title="LangGraph Notebook Foundry API",
    version=__version__,
    lifespan=_lifespan,
)


@app.exception_handler(JobError)
async def _safe_job_error(request: Request, exc: JobError):
    return JSONResponse(
        status_code=exc.status,
        content={"detail": {"code": exc.code}},
        headers={"Cache-Control": "private, no-store"},
    )


@app.middleware("http")
async def _bound_durable_requests(request: Request, call_next):
    if (
        request.url.path in {"/generate", "/generate-async"}
        and os.getenv("LNF_JOB_BACKEND", "ephemeral") != "ephemeral"
    ):
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > 65536:
                return JSONResponse(
                    status_code=413,
                    content={"detail": {"code": "job_request_too_large"}},
                )
            raw.extend(chunk)
        request._body = bytes(raw)
    response = await call_next(request)
    if request.url.path.startswith(("/jobs/", "/stream/", "/artifacts", "/generate")):
        response.headers["Cache-Control"] = "private, no-store"
    return response


def _durable_selected() -> bool:
    return backend_name() == "firestore"


def _http_context(request: Request | None) -> Request:
    if request is None:
        raise JobError("identity_required", 401)
    return request


# Request validation errors otherwise include the rejected raw input.
@app.exception_handler(RequestValidationError)
async def _safe_request_validation_error(request: Request, exc: RequestValidationError):
    errors = [
        {"type": item["type"], "loc": item["loc"], "msg": "Invalid request field."}
        for item in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})


# Mount static files
_STATIC_DIR = Path(__file__).parent / "static"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

_DEFAULT_API_OUTPUT = (_BASE_OUTPUT / "api").resolve()


def _positive_int_env(name: str, default: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning("Invalid %s; using default %d", name, default)
        return default
    return min(max(value, 1), maximum)


_MAX_TRACKED_API_RUNS = _positive_int_env("LNF_MAX_TRACKED_JOBS", 100, 10_000)
_API_ARTIFACT_RETENTION_SECONDS = _positive_int_env(
    "LNF_ARTIFACT_TTL_SECONDS", 900, 86_400
)
_MAX_JOB_TIMEOUT_SECONDS = 240
_JOB_TIMEOUT_SECONDS = _positive_int_env(
    "LNF_JOB_TIMEOUT_SECONDS", _MAX_JOB_TIMEOUT_SECONDS, _MAX_JOB_TIMEOUT_SECONDS
)
_API_ARTIFACT_NAMES = {
    "manifest.json",
    "generated_cells.json",
    "notebook_plan.json",
    "notebook.ipynb",
    "notebook.html",
    "notebook.md",
    "notebook.docx",
    "notebook.pdf",
    "notebook_bundle.zip",
}
_api_runs: dict[str, _ApiRun] = {}


@dataclass
class _ApiRun:
    run_id: str
    output_path: Path
    created_at: float
    job_id: str | None = None
    active: bool = True
    completed_at: float | None = None
    files: dict[str, Path] = field(default_factory=dict)


@dataclass
class _GenerationLease:
    """One idempotent release token for an admitted generation."""

    released: bool = False

    def release(self) -> None:
        global _active_generation_count
        if self.released:
            return
        self.released = True
        _active_generation_count = max(0, _active_generation_count - 1)


def _env_true(name: str) -> bool:
    """Read a strict opt-in boolean; malformed values fail closed."""
    value = os.getenv(name, "false").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _is_hosted() -> bool:
    return bool(os.getenv("K_SERVICE"))


def _hosted_access_enabled() -> bool:
    return (
        not _is_hosted()
        or os.getenv("LNF_API_ACCESS_MODE", "").strip() == "single-operator"
    )


def _async_generation_enabled() -> bool:
    return not _is_hosted() or _env_true("LNF_EPHEMERAL_ASYNC_ENABLED")


def _require_supported_access() -> None:
    try:
        require_ephemeral_admission()
    except JobError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code}) from None
    if _is_hosted() and not _hosted_access_enabled():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "hosted_access_mode_required",
                "message": "Hosted generation is disabled until the trusted single-operator access mode is explicitly configured.",
                "hint": "Set LNF_API_ACCESS_MODE=single-operator only when IAP is restricted to one trusted operator.",
            },
        )


async def _cleanup_process_local_state() -> None:
    """Periodically prune terminal job history and expired API artifact trees."""
    while True:
        await asyncio.sleep(30.0)
        _prune_expired_jobs()
        _prune_api_runs()


# Concurrency limit for async generation (prevent resource exhaustion)
_MAX_CONCURRENT_GENERATIONS = _positive_int_env(
    "LNF_MAX_CONCURRENT_GENERATIONS", 5, 100
)
_generation_lock = asyncio.Lock()
_active_generation_count = 0
_shutting_down = False


def _generation_error_payload(exc: Exception) -> dict[str, Any]:
    """Normalize exceptions into a structured API error payload."""

    if isinstance(exc, GenerationError):
        return exc.to_payload()

    if isinstance(exc, OptionalDependencyError):
        payload: dict[str, Any] = {
            "code": "dependency_unavailable",
            "message": _sanitize_text_credentials(str(exc)),
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
        "message": "Generation failed (" + type(exc).__name__ + ").",
        "status_code": 500,
        "details": {"error_type": type(exc).__name__},
    }


def _raise_generation_http_error(exc: Exception) -> NoReturn:
    """Raise an HTTPException from a normalized generation error."""

    payload = _generation_error_payload(exc)
    raise HTTPException(status_code=payload["status_code"], detail=payload)


async def _try_acquire_generation_slot() -> bool:
    """Reserve a generation slot if capacity is available."""
    global _active_generation_count

    if _shutting_down:
        return False
    async with _generation_lock:
        if _shutting_down:
            return False
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
        if _shutting_down:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "server_shutting_down",
                    "message": "The server is shutting down and cannot accept new generations.",
                },
            )
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


async def _await_generation(
    coroutine: Coroutine[Any, Any, GenerationArtifacts],
) -> GenerationArtifacts:
    """Preserve timeout/cancellation intent even if a collaborator suppresses it.

    The owner retains capacity and the output reservation until the nested
    execution actually exits. Shutdown bounds its wait for that owner separately;
    a dependency that never cooperates cannot be safely preempted in-process.
    """
    try:
        execution = asyncio.create_task(coroutine)
    except BaseException:
        coroutine.close()
        raise
    try:
        done, _ = await asyncio.wait({execution}, timeout=_JOB_TIMEOUT_SECONDS)
        if not done:
            execution.cancel()
            await asyncio.gather(execution, return_exceptions=True)
            raise asyncio.TimeoutError  # noqa: UP041 - Python 3.10
        return execution.result()
    except asyncio.CancelledError:
        execution.cancel()
        await asyncio.gather(execution, return_exceptions=True)
        raise


def _resolve_output_dir(path: str | os.PathLike[str] | None) -> Path:
    """Resolve an allowed API output parent and reject symlink components."""
    base = _BASE_OUTPUT.resolve()
    requested = Path(path) if path else Path("api")
    if "\x00" in os.fspath(requested):
        raise HTTPException(
            status_code=400, detail="output_dir cannot contain a null byte."
        )
    if ".." in requested.parts:
        raise HTTPException(
            status_code=400,
            detail="output_dir cannot contain parent-directory traversal.",
        )
    lexical_target = Path(
        os.path.abspath(requested if requested.is_absolute() else base / requested)
    )
    try:
        relative = lexical_target.relative_to(base)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="output_dir must reside within the allowed base directory.",
        )
    # Rebuild from the trusted root to preserve its casing on Windows. Check
    # the normalized value used below, including a separator so sibling-prefix
    # paths cannot pass and the root itself remains a valid output parent.
    checked_target = os.path.join(os.path.abspath(base / relative), "")
    if not checked_target.startswith(os.path.join(os.fspath(base), "")):
        raise HTTPException(
            status_code=400,
            detail="output_dir must reside within the allowed base directory.",
        )
    lexical_target = Path(checked_target)
    current = base
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise HTTPException(
                status_code=400,
                detail="output_dir cannot contain a symbolic link.",
            )
    try:
        lexical_target.resolve(strict=False).relative_to(base)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="output_dir escapes the allowed base directory.",
        ) from None
    return lexical_target


def _make_directory_tree(path: Path) -> None:
    """Create directories beneath the trusted root without following symlinks."""
    base = _BASE_OUTPUT.resolve()
    if not base.exists():
        base.mkdir(parents=True, exist_ok=True)
    if base.is_symlink() or not base.is_dir():
        raise HTTPException(
            status_code=400, detail="The trusted output root is not a safe directory."
        )
    try:
        relative = path.relative_to(base)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Output path is outside the trusted root."
        ) from exc
    current = base
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise HTTPException(
                status_code=400, detail="Output path cannot contain a symbolic link."
            )
        if not current.exists():
            try:
                current.mkdir()
            except FileExistsError:
                pass
        if current.is_symlink() or not current.is_dir():
            raise HTTPException(
                status_code=400, detail="Output path is not a safe directory."
            )
        try:
            current.resolve(strict=True).relative_to(base)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(
                status_code=400, detail="Output path escapes the trusted root."
            ) from exc


def _delete_run_directory(run: _ApiRun) -> None:
    """Delete a server-owned run directory only after containment checks."""
    path = run.output_path
    if not path.exists():
        return
    base = _BASE_OUTPUT.resolve()
    try:
        relative = path.relative_to(base)
    except (ValueError, FileNotFoundError):
        logger.error("Refusing to remove an API run outside the trusted root.")
        return
    current = base
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            logger.error("Refusing to remove an API run with a symbolic-link ancestor.")
            return
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(base)
    except (ValueError, FileNotFoundError):
        logger.error("Refusing to remove an API run outside the trusted root.")
        return
    if resolved.name != run.run_id or not resolved.is_dir():
        logger.error("Refusing to remove an API run with an unexpected directory name.")
        return
    shutil.rmtree(resolved)


def _discard_api_run(run_id: str) -> None:
    """Forget and delete an unpublishable partial generation namespace."""
    run = _api_runs.pop(run_id, None)
    if run is not None:
        run.active = False
        _delete_run_directory(run)


def _prune_api_runs(now: float | None = None) -> list[str]:
    """Remove expired completed API artifacts, independently of job-event TTL."""
    current = time.time() if now is None else now
    expired = [
        run_id
        for run_id, run in _api_runs.items()
        if not run.active
        and run.completed_at is not None
        and current - run.completed_at >= _API_ARTIFACT_RETENTION_SECONDS
    ]
    for run_id in expired:
        run = _api_runs.pop(run_id)
        _delete_run_directory(run)
    return expired


def _reserve_api_run(parent: Path, job_id: str | None = None) -> _ApiRun:
    """Exclusively allocate a unique per-request namespace under the API parent."""
    _prune_api_runs()
    if len(_api_runs) >= _MAX_TRACKED_API_RUNS:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "artifact_capacity_exhausted",
                "message": "The server has reached its retained API output limit. Try again after artifact retention expires.",
            },
        )

    generations = parent / "generations"
    _make_directory_tree(generations)
    base = _BASE_OUTPUT.resolve()
    for _ in range(3):
        run_id = uuid4().hex
        output_path = generations / run_id
        try:
            output_path.mkdir()
        except FileExistsError:
            continue
        if output_path.is_symlink():
            raise HTTPException(
                status_code=400, detail="Output namespace cannot be a symbolic link."
            )
        try:
            output_path.resolve(strict=True).relative_to(base)
        except (ValueError, FileNotFoundError) as exc:
            _delete_run_directory(_ApiRun(run_id, output_path, time.time()))
            raise HTTPException(
                status_code=400, detail="Output namespace escapes the trusted root."
            ) from exc
        run = _ApiRun(run_id, output_path.resolve(strict=True), time.time(), job_id)
        _api_runs[run_id] = run
        return run
    raise HTTPException(
        status_code=503, detail="Could not reserve a unique output namespace."
    )


def _safe_run_file(run: _ApiRun, name: str) -> Path | None:
    """Resolve a registered artifact only while its original file remains safe."""
    path = run.files.get(name)
    return _safe_run_candidate(run, path, name) if path is not None else None


def _safe_run_candidate(run: _ApiRun, path: Path, name: str) -> Path | None:
    """Validate the same namespace boundary for publication and downloads."""
    if name not in _API_ARTIFACT_NAMES or path.parent != run.output_path:
        return None
    if path.is_symlink() or run.output_path.is_symlink() or not path.is_file():
        return None
    try:
        base = _BASE_OUTPUT.resolve()
        relative = path.relative_to(base)
        current = base
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                return None
        real_run = run.output_path.resolve(strict=True)
        real_file = path.resolve(strict=True)
        if real_file.parent != real_run or real_file.name != name:
            return None
        real_file.relative_to(base)
    except (ValueError, OSError):
        return None
    return real_file


def _persist_api_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _register_api_artifacts(
    run: _ApiRun, artifacts: GenerationArtifacts
) -> dict[str, Any]:
    """Publish only known, regular files created inside this request's run directory."""
    manifest = artifacts["manifest"]
    contract = manifest.setdefault("artifact_contract", {})
    contract["path_semantics"] = (
        "API artifact downloads use process-local run references. Files are isolated "
        "per request and are not durable across process or instance replacement."
    )
    contract["run_id"] = run.run_id
    contract["retention_seconds"] = _API_ARTIFACT_RETENTION_SECONDS
    standalone = contract.setdefault("standalone_files", [])
    discovered: dict[str, Path] = {}

    for entry in standalone:
        if not isinstance(entry, dict):
            continue
        raw_path = entry.get("path")
        if not isinstance(raw_path, str):
            entry["exists"] = False
            entry.pop("api_download_path", None)
            continue
        candidate = Path(raw_path)
        name = candidate.name
        safe_candidate = _safe_run_candidate(run, candidate, name)
        if safe_candidate is None:
            entry["exists"] = False
            entry.pop("api_download_path", None)
            continue
        discovered[name] = safe_candidate

    manifest_path = Path(artifacts["manifest_path"])
    safe_manifest = _safe_run_candidate(run, manifest_path, "manifest.json")
    if safe_manifest is not None:
        discovered["manifest.json"] = safe_manifest

    run.files = discovered
    if "manifest.json" not in discovered:
        raise GenerationError(
            "Generation did not produce an accessible manifest in its reserved namespace.",
            code="artifact_manifest_unavailable",
            phase="artifact_publication",
            status_code=500,
        )
    for entry in standalone:
        if not isinstance(entry, dict):
            continue
        name = Path(str(entry.get("path") or "")).name
        if name in discovered:
            entry["api_download_path"] = (
                f"/artifacts?run_id={run.run_id}&artifact={name}"
            )

    manifest_entry: dict[str, Any] = {
        "name": "manifest",
        "format": "json",
        "manifest_key": "manifest_path",
        "availability": "standalone",
        "path_type": "server_local",
        "path": str(discovered["manifest.json"]),
        "relative_path": "manifest.json",
        "exists": True,
        "size_bytes": None,
        "api_download_path": f"/artifacts?run_id={run.run_id}&artifact=manifest.json",
    }
    standalone[:] = [
        entry
        for entry in standalone
        if isinstance(entry, dict) and entry.get("manifest_key") != "manifest_path"
    ]
    standalone.append(manifest_entry)
    contract["api_downloads"] = {
        name: f"/artifacts?run_id={run.run_id}&artifact={name}"
        for name in sorted(discovered)
    }
    contract["access_scope"] = "trusted_single_operator"

    manifest_file = discovered["manifest.json"]
    for _ in range(3):
        _persist_api_manifest(manifest_file, manifest)
        actual_size = manifest_file.stat().st_size
        if manifest_entry["size_bytes"] == actual_size:
            break
        manifest_entry["size_bytes"] = actual_size
    else:
        manifest_entry["size_bytes"] = None
        _persist_api_manifest(manifest_file, manifest)
    run.active = False
    run.completed_at = time.time()
    return manifest


def _validate_advanced_options(
    request: GenerationRequest,
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

    try:
        binding = authorize_endpoint(request.custom_endpoint or None, "hosted")
        if request.mode == "live":
            binding.credential()
        if normalized_custom_endpoint:
            normalized_custom_endpoint = binding.base_url
    except GenerationError as exc:
        _raise_generation_http_error(exc)

    if normalized_model == "custom":
        raise HTTPException(
            status_code=400,
            detail="Provide an explicit model identifier instead of the placeholder value 'custom'.",
        )

    return normalized_model, normalized_custom_endpoint, normalized_agent_type


def _normalize_request(request: GenerationRequest) -> GenerationRequest:
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
    request: GenerationRequest,
) -> list[dict[str, str]] | None:
    """Return normalized dialog messages for iterative requirements refinement."""

    if not request.messages:
        return None
    return [message.model_dump() for message in request.messages]


def _request_prompt(request: GenerationRequest) -> str:
    """Return the single prompt value used by legacy generation surfaces."""

    prompt = request.prompt or ""
    if prompt.strip():
        return prompt
    messages = request.messages or []
    for message in reversed(messages):
        if message.role == "user" and message.content.strip():
            return message.content
    for message in reversed(messages):
        if message.content.strip():
            return message.content
    return ""


class DialogMessage(BaseModel):
    """One requirements dialog turn accepted by the API."""

    role: Literal["system", "user", "assistant"] = Field(
        description="Dialog role for this requirements turn."
    )
    content: str = Field(
        ...,
        description="Message content for this requirements turn.",
        min_length=1,
        max_length=5000,
    )

    @field_validator("content")
    @classmethod
    def _validate_non_whitespace_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message content must include non-whitespace characters.")
        return value


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str | None = Field(
        default=None,
        description="User prompt describing the desired system",
        max_length=5000,
    )
    messages: list[DialogMessage] | None = Field(
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
    formats: list[str] | None = Field(
        default=None,
        description=(
            "List of output formats to generate (ipynb, html, markdown, pdf, docx, zip). "
            "If not specified, generates the default export set: ipynb, html, markdown, docx, zip."
        ),
    )
    # Advanced options
    model: str | None = Field(
        default=None,
        description="OpenAI-compatible model to use for generation. Uses the default OpenAI-compatible model if not specified.",
    )
    custom_endpoint: str | None = Field(
        default=None,
        description="Administrator-registered OpenAI-compatible endpoint. Arbitrary hosted destinations are forbidden.",
    )
    temperature: float | None = Field(
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
    max_tokens: int | None = Field(
        default=None,
        ge=1,
        le=32768,
        description="Maximum tokens for LLM response. Controls output length and must not exceed the model's context window (capped at 32768 here).",
    )
    agent_type: str | None = Field(
        default=None,
        description="Type of agent architecture (router, subagents, hybrid, autoagent, deepagents, etc.) when overriding auto-detection.",
    )

    @model_validator(mode="after")
    def _require_prompt_or_messages(self) -> GenerationRequest:
        """Require either a legacy prompt or at least one dialog message."""

        if not (self.prompt and self.prompt.strip()) and not self.messages:
            raise ValueError("Either prompt or messages must be provided.")
        return self


class GenerationResponse(BaseModel):
    success: bool
    mode: str | None = None
    prompt: str | None = (
        None  # Note: User prompt echoed back for confirmation; may contain sensitive data if logged
    )
    manifest: dict[str, Any] | None = None
    manifest_path: str | None = None
    output_dir: str | None = None
    error: str | None = None
    run_id: str | None = Field(
        default=None,
        description="Server-assigned per-request artifact namespace reference.",
    )


class GenerationStartResponse(BaseModel):
    """Response when starting async generation with SSE progress tracking."""

    job_id: str = Field(..., description="Unique job identifier for tracking progress")
    stream_url: str = Field(
        ..., description="SSE endpoint URL for streaming progress updates"
    )
    status: str = Field(
        default="started", description="Compatibility field for accepted async work"
    )
    execution_status: str = Field(
        default="accepted", description="Initial process-local execution status"
    )
    durable: bool = False
    execution_mode: str = "ephemeral_process_local"
    run_id: str | None = None
    idempotent_replay: bool = False


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
async def health(http_request: Request) -> dict[str, Any]:
    """Report health and the configured ephemeral execution capabilities."""
    access_enabled = _hosted_access_enabled()
    backend_error = None
    try:
        if _durable_selected():
            runtime = durable.runtime_for(http_request)
            await asyncio.to_thread(runtime.probe)
            return {
                "status": "ok",
                "ready": True,
                "execution_mode": "durable_firestore",
                "durable_jobs": True,
                "job_backend_error": None,
                "generation_enabled": runtime.submissions,
                "async_generation": runtime.submissions,
                "sync_generation": False,
                "generation_route": "/generate-async",
                "identity_mode": "verified_iap",
                "artifact_storage": "gcs_private",
                "artifact_readiness": "verified_on_access",
                "job_retention_seconds": 7 * 86400,
                "event_retention_seconds": 86400,
                "idempotency_retention_seconds": 86400,
            }
    except JobError as exc:
        return {
            "status": "ok",
            "ready": False,
            "execution_mode": "durable_unavailable",
            "durable_jobs": False,
            "generation_enabled": False,
            "async_generation": False,
            "sync_generation": False,
            "job_backend_error": exc.code,
        }
    try:
        require_ephemeral_admission()
    except JobError as exc:
        access_enabled = False
        backend_error = exc.code
    return {
        "status": "ok",
        "ready": access_enabled,
        "execution_mode": "ephemeral_process_local",
        "durable_jobs": False,
        "job_backend_error": backend_error,
        "generation_enabled": access_enabled,
        "async_generation": access_enabled and _async_generation_enabled(),
        "sync_generation": access_enabled,
        "artifact_retention_seconds": _API_ARTIFACT_RETENTION_SECONDS,
        "job_retention_seconds": _positive_int_env(
            "LNF_COMPLETED_JOB_TTL_SECONDS", 300, 86_400
        ),
        "max_tracked_jobs": _MAX_TRACKED_API_RUNS,
        "max_concurrent_generations": _MAX_CONCURRENT_GENERATIONS,
        "job_timeout_seconds": _JOB_TIMEOUT_SECONDS,
    }


@app.get("/ready")
async def readiness(http_request: Request):
    capabilities = await health(http_request)
    return JSONResponse(capabilities, status_code=200 if capabilities["ready"] else 503)


@app.get("/artifacts")
async def download_artifact(
    http_request: Request,
    run_id: str = Query(..., min_length=32, max_length=32),
    artifact: str = Query(..., min_length=1, max_length=64),
):
    """Download one explicitly registered artifact from an API run namespace."""
    if _durable_selected():
        return await durable.download(http_request, run_id, artifact)
    _require_supported_access()
    _prune_api_runs()
    run = _api_runs.get(run_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "artifact_unavailable",
                "message": "The artifact run is unavailable or expired.",
            },
        )
    if run.active:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "artifact_not_ready",
                "message": "Artifacts are not ready until generation completes.",
            },
        )
    artifact_path = _safe_run_file(run, artifact)
    if artifact_path is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "artifact_unavailable",
                "message": "The requested generated artifact is unavailable or expired.",
            },
        )
    return FileResponse(artifact_path, filename=artifact_path.name)


@app.get("/jobs/{job_id}")
async def _inspect_job_http(job_id: str, http_request: Request) -> dict[str, Any]:
    return await inspect_job(job_id, http_request)


async def inspect_job(
    job_id: str, http_request: Request | None = None
) -> dict[str, Any]:
    """Return execution state while the owning process retains the job record."""
    if _durable_selected():
        return await durable.inspect(_http_context(http_request), job_id)
    _require_supported_access()
    status = get_job_status(job_id)
    if status is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "job_unavailable",
                "message": "Job state is unavailable in this process or its retention period expired.",
            },
        )
    return status


@app.get("/jobs/{job_id}/result")
async def _get_job_result_http(job_id: str, http_request: Request) -> dict[str, Any]:
    return await get_job_result(job_id, http_request)


async def get_job_result(
    job_id: str, http_request: Request | None = None
) -> dict[str, Any]:
    """Return a completed result from the registered run manifest."""
    if _durable_selected():
        return await durable.result(_http_context(http_request), job_id)
    _require_supported_access()
    _prune_api_runs()
    status = get_job_status(job_id)
    if status is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "job_unavailable",
                "message": "Job state is unavailable in this process or its retention period expired.",
            },
        )
    if status["status"] != "completed":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "job_result_not_ready",
                "job_status": status["status"],
                "message": "The job has no successful result.",
            },
        )
    run = next((item for item in _api_runs.values() if item.job_id == job_id), None)
    manifest_path = _safe_run_file(run, "manifest.json") if run else None
    if run is None or manifest_path is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "artifact_unavailable",
                "message": "The generated manifest is unavailable or expired.",
            },
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(
            status_code=410,
            detail={
                "code": "job_result_unavailable",
                "message": "The completed result could not be read from local artifact storage.",
            },
        ) from None
    return {
        "success": True,
        "mode": manifest.get("mode"),
        "prompt": manifest.get("prompt"),
        "manifest": manifest,
        "manifest_path": str(manifest_path),
        "output_dir": str(manifest_path.parent),
        "run_id": run.run_id,
    }


@app.get("/.well-known/appspecific/com.chrome.devtools.json")
async def chrome_devtools_endpoint():
    """Handle Chrome DevTools endpoint request.

    Chrome automatically requests this endpoint to check for DevTools support.
    Return 204 No Content to indicate the endpoint is recognized but we don't
    provide DevTools-specific features.
    """
    return Response(status_code=204)


@app.post("/generate", response_model=GenerationResponse)
async def _generate_notebook_http(
    request: GenerationRequest, http_request: Request
) -> GenerationResponse:
    return await generate_notebook(request, http_request)


async def generate_notebook(
    request: GenerationRequest, http_request: Request | None = None
) -> GenerationResponse:
    """Generate notebook artifacts via the generator pipeline."""
    if _durable_selected():
        raise JobError("durable_requires_async", 409)
    normalized_request = _normalize_request(request)
    _require_supported_access()
    prompt = _request_prompt(normalized_request)
    requirements_messages = _request_dialog_messages(normalized_request)

    output_parent = _resolve_output_dir(request.output_dir)

    async with _generation_slot():
        run = _reserve_api_run(output_parent)
        try:
            artifacts: GenerationArtifacts = await _await_generation(
                generate_artifacts(
                    prompt,
                    output_dir=str(run.output_path),
                    mode=request.mode,
                    formats=request.formats,
                    model=normalized_request.model,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    agent_type=normalized_request.agent_type,
                    custom_endpoint=normalized_request.custom_endpoint,
                    endpoint_policy="hosted",
                    requirements_messages=requirements_messages,
                ),
            )
            manifest = _register_api_artifacts(run, artifacts)
            return GenerationResponse(
                success=True,
                mode=artifacts["mode"],
                prompt=artifacts["prompt"],
                manifest=manifest,
                manifest_path=str(
                    run.files.get("manifest.json", Path(artifacts["manifest_path"]))
                ),
                output_dir=str(run.output_path),
                run_id=run.run_id,
            )
        except asyncio.TimeoutError:  # noqa: UP041 - Python 3.10
            _discard_api_run(run.run_id)
            raise HTTPException(
                status_code=504,
                detail={
                    "code": "generation_timeout",
                    "message": f"Generation exceeded the configured {_JOB_TIMEOUT_SECONDS}-second execution limit.",
                },
            ) from None
        except asyncio.CancelledError:
            _discard_api_run(run.run_id)
            raise
        except (GenerationError, OptionalDependencyError) as exc:
            _discard_api_run(run.run_id)
            logger.error(
                "Generation request failed for /generate: %s", type(exc).__name__
            )
            _raise_generation_http_error(exc)
        except ValueError as exc:  # pragma: no cover - surfaced via HTTPException
            _discard_api_run(run.run_id)
            logger.error(
                "Generation request failed for /generate: %s", type(exc).__name__
            )
            _raise_generation_http_error(
                GenerationError(
                    "Invalid generation input.",
                    code="invalid_generation_input",
                    status_code=400,
                )
            )
        except Exception as exc:  # noqa: BLE001 - sanitize public failure boundary
            _discard_api_run(run.run_id)
            logger.error(
                "Generation request failed for /generate: %s", type(exc).__name__
            )
            _raise_generation_http_error(exc)


@app.post("/generate-async", response_model=GenerationStartResponse)
async def _start_async_generation_http(
    request: GenerationRequest, http_request: Request
) -> GenerationStartResponse:
    return await start_async_generation(request, http_request)


async def start_async_generation(
    request: GenerationRequest,
    http_request: Request | None = None,
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
    if _durable_selected():
        return GenerationStartResponse(
            **await durable.submit(
                _http_context(http_request),
                normalized_request,
                _request_prompt(normalized_request),
            )
        )
    _require_supported_access()
    if not _async_generation_enabled():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "ephemeral_async_disabled",
                "message": "Hosted asynchronous generation is disabled; use request-bound synchronous generation.",
                "hint": "Enable LNF_EPHEMERAL_ASYNC_ENABLED only after configuring instance-based CPU allocation for the Cloud Run service.",
            },
        )
    output_parent = _resolve_output_dir(request.output_dir)

    # Acquire capacity before the job is accepted so overload requests fail fast.
    await _acquire_generation_slot_or_raise()

    lease = _GenerationLease()
    run: _ApiRun | None = None
    job_id: str | None = None
    coroutine = None
    task: asyncio.Task[Any] | None = None
    try:
        run = _reserve_api_run(output_parent)
        reserved_run = run
        job_id = create_job()
        run.job_id = job_id
        coroutine = _run_generation_with_progress(
            job_id, normalized_request, run, lease
        )
        task = asyncio.create_task(coroutine)

        def finish_owner(_done: asyncio.Task[Any]) -> None:
            lease.release()
            if reserved_run.active:
                # A task cancelled before its coroutine's first step cannot run
                # the runner's finally block, so its reservation is released here.
                _discard_api_run(reserved_run.run_id)

        register_owned_task(job_id, task, on_done=finish_owner)
    except BaseException as exc:
        if task is not None:
            task.cancel()
        elif coroutine is not None:
            coroutine.close()
        if job_id is not None:
            discard_job(job_id)
        if run is not None:
            _discard_api_run(run.run_id)
        lease.release()
        if isinstance(exc, (KeyboardInterrupt, SystemExit, asyncio.CancelledError)):
            raise
        logger.error("Could not accept an async generation: %s", type(exc).__name__)
        if isinstance(exc, JobCapacityError):
            raise HTTPException(
                status_code=503,
                detail={"code": "job_capacity_exhausted", "message": str(exc)},
            ) from None
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(
            status_code=503,
            detail={
                "code": "generation_task_unavailable",
                "message": "The server could not safely register the generation task.",
            },
        ) from None

    return GenerationStartResponse(
        job_id=job_id,
        stream_url=f"/stream/{job_id}",
        status="started",
        execution_status="accepted",
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
    if _durable_selected():
        return await durable.stream(request, job_id)
    _require_supported_access()
    return get_stream_response(job_id, request.headers.get("Last-Event-ID"))


@app.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, request: Request):
    if _durable_selected():
        return await durable.cancel(request, job_id)
    _require_supported_access()
    raise JobError("cancellation_requires_durable", 409)


async def _run_generation_with_progress(
    job_id: str,
    request: GenerationRequest,
    run: _ApiRun | Path,
    lease: _GenerationLease | None = None,
) -> None:
    """Run generation task with progress tracking.

    This function orchestrates the generation process and emits progress events
    to the SSE stream. It wraps generate_artifacts() and adds instrumentation.

    Uses the API admission controller to limit concurrent generations and prevent
    resource exhaustion.

    Args:
        job_id: Job identifier for progress tracking
        request: Generation request parameters
        run: Reserved API namespace, or an explicit path for legacy direct callers
        lease: Idempotent generation capacity release handle, when route-owned
    """
    api_run = None if isinstance(run, Path) else run
    output_path = run if api_run is None else api_run.output_path
    try:
        mark_job_running(job_id)
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
        artifacts: GenerationArtifacts = await _await_generation(
            generate_artifacts(
                prompt,
                output_dir=str(output_path),
                mode=request.mode,
                formats=request.formats,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                agent_type=request.agent_type,
                custom_endpoint=request.custom_endpoint,
                endpoint_policy="hosted",
                requirements_messages=requirements_messages,
                progress_callback=progress_callback,
            ),
        )
        if api_run is None:
            result = {
                "success": True,
                "mode": artifacts["mode"],
                "prompt": artifacts["prompt"],
                "manifest": artifacts["manifest"],
                "manifest_path": artifacts["manifest_path"],
                "output_dir": artifacts["output_dir"],
            }
        else:
            _register_api_artifacts(api_run, artifacts)
            result = {
                "success": True,
                "run_id": api_run.run_id,
                "result_url": f"/jobs/{job_id}/result",
            }
        emit_complete(
            job_id,
            result,
        )

    except asyncio.CancelledError:
        if api_run is not None and api_run.active:
            _discard_api_run(api_run.run_id)
        emit_error(
            job_id,
            "Generation was cancelled before it completed.",
            status="cancelled",
            code="generation_cancelled",
        )
        raise
    except asyncio.TimeoutError:  # noqa: UP041 - Python 3.10
        if api_run is not None and api_run.active:
            _discard_api_run(api_run.run_id)
        emit_error(
            job_id,
            f"Generation exceeded the configured {_JOB_TIMEOUT_SECONDS}-second execution limit.",
            {"timeout_seconds": _JOB_TIMEOUT_SECONDS},
            status="expired",
            code="generation_timeout",
        )
    except Exception as exc:  # noqa: BLE001 - sanitize SSE failure boundary
        if api_run is not None and api_run.active:
            _discard_api_run(api_run.run_id)
        logger.error(
            "Generation failed for async job %s: %s", job_id, type(exc).__name__
        )
        payload = _generation_error_payload(exc)
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
            status="failed",
            code=payload.get("code", "generation_error"),
        )
    finally:
        if lease is not None:
            lease.release()


def create_api_app(runtime: durable.DurableRuntime | None = None) -> FastAPI:
    """Independent ASGI app state for embedding and multi-instance qualification.

    Runtime injection is trusted Python construction, never request selectable.
    Durable routes consult only that runtime's shared store/object adapters.
    """
    created = FastAPI(title=app.title, version=app.version, lifespan=_lifespan)
    created.router.routes = list(app.router.routes)
    created.exception_handlers = dict(app.exception_handlers)
    created.user_middleware = list(app.user_middleware)
    created.state.durable_runtime = runtime
    return created
