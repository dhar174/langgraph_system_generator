"""Public durable boundary. No SDK client, credential discovery or I/O at import."""

import asyncio
import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from threading import BoundedSemaphore, Lock
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from starlette.background import BackgroundTask

from langgraph_system_generator import __version__
from langgraph_system_generator.api.identity import IAPVerifier, verified_principal
from langgraph_system_generator.jobs.gcs_artifacts import TYPES, GCSArtifactStore
from langgraph_system_generator.jobs.models import (
    TERMINAL,
    DurableJob,
    GenerationRequestEnvelope,
    JobError,
    JobEvent,
    JobState,
    Principal,
    RequirementsTurn,
)
from langgraph_system_generator.jobs.protocols import JobStore
from langgraph_system_generator.jobs.providers import resolve_provider
from langgraph_system_generator.jobs.registry import select_job_store
from langgraph_system_generator.utils.config import settings
from langgraph_system_generator.utils.llm_endpoint_security import authorize_endpoint

logger = logging.getLogger(__name__)


@dataclass
class DurableRuntime:
    store: JobStore
    artifacts: GCSArtifactStore
    verifier: IAPVerifier
    submissions: bool = False
    clock: Any = time.time
    poll_seconds: float = 2.0
    connection_seconds: float = 240.0
    streams: BoundedSemaphore = field(default_factory=lambda: BoundedSemaphore(50))
    downloads: BoundedSemaphore = field(default_factory=lambda: BoundedSemaphore(8))
    owner_streams: dict[tuple[str, str], int] = field(default_factory=dict)
    stream_lock: Lock = field(default_factory=Lock)

    def probe(self) -> None:
        try:
            self.store.inspect_attempt("0" * 32)
        except JobError as error:
            if error.status != 404:
                raise


def configured_runtime() -> DurableRuntime:
    if os.getenv("LNF_API_ACCESS_MODE") != "iap":
        raise JobError("durable_identity_mode_required", 503)
    verifier = IAPVerifier(os.getenv("LNF_IAP_AUDIENCE", ""))
    try:
        import_module("jwt")  # optional dependency, explicit durable mode only
        import_module("google.cloud.storage")  # optional runtime, no client/ADC

        flag = os.getenv("LNF_DURABLE_SUBMISSIONS_ENABLED", "false")
        if flag not in {"true", "false"}:
            raise ValueError("invalid activation")
        if flag == "true":
            from langgraph_system_generator.api.worker_server import dispatch_config

            config = dispatch_config()
            scheduler = os.getenv("LNF_SCHEDULER_SERVICE_ACCOUNT", "")
            if (
                not scheduler.endswith(".iam.gserviceaccount.com")
                or scheduler == config.service_account
            ):
                raise ValueError("invalid reconciliation identity")
        artifacts = GCSArtifactStore(
            os.getenv("LNF_JOB_ARTIFACT_BUCKET", ""), Path.cwd()
        )
        store = select_job_store()
        if store is None:
            raise ValueError("durable store required")
        refs = json.loads(os.getenv("LNF_JOB_PROVIDER_REFS", '["openai-v1"]'))
        for ref in refs:
            resolve_provider(
                GenerationRequestEnvelope(prompt="readiness", provider_ref=ref)
            )
    except (ImportError, ValueError):
        raise JobError("durable_configuration_invalid", 503) from None
    return DurableRuntime(store, artifacts, verifier, flag == "true")


def runtime_for(request: Request) -> DurableRuntime:
    selected = getattr(request.app.state, "durable_runtime", None)
    if selected is None:
        selected = configured_runtime()
        request.app.state.durable_runtime = selected
    return selected


async def authorized(request: Request) -> tuple[DurableRuntime, Principal]:
    runtime = runtime_for(request)
    principal = await asyncio.to_thread(
        verified_principal, request.headers, runtime.verifier
    )
    return runtime, principal


def status(job: DurableJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "run_id": job.run_id,
        "status": job.state.value,
        "execution_status": job.state.value,
        "durable": True,
        "execution_mode": "durable_firestore",
        "queue_state": "pending_dispatch" if job.dispatch.pending else "dispatched",
        "cancellation_requested": job.cancellation_requested,
        "expires_at": job.expires_at,
        "result_url": (
            f"/jobs/{job.job_id}/result" if job.state == JobState.COMPLETED else None
        ),
    }


def envelope(request: Any, prompt: str) -> GenerationRequestEnvelope:
    # Durable output_dir is a legacy label, never a worker filesystem selector.
    if request.output_dir not in {
        "./output/api",
        "./output/web_generated",
        "output/api",
        "output/web_generated",
        "api",
        "",
    }:
        raise JobError("durable_output_dir_unsupported", 422)
    binding = authorize_endpoint(request.custom_endpoint, "hosted")
    try:
        bindings = json.loads(
            os.getenv("LNF_JOB_PROVIDER_BINDINGS", '{"openai-v1":"openai"}')
        )
        approved = json.loads(os.getenv("LNF_JOB_PROVIDER_REFS", '["openai-v1"]'))
        refs = sorted(
            ref
            for ref, provider in bindings.items()
            if provider == binding.provider_id and ref in approved
        )
        if not refs:
            raise JobError("job_provider_not_approved", 403)
        result = GenerationRequestEnvelope(
            prompt=prompt,
            mode=request.mode,
            model=request.model or settings.default_model,
            architecture=request.agent_type,
            provider_ref=refs[0],
            generator_version=__version__,
            formats=(
                tuple(sorted(set(request.formats)))
                if request.formats is not None
                else None
            ),
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            messages=tuple(
                RequirementsTurn(role=turn.role, content=turn.content)
                for turn in request.messages or ()
            ),
        )
        resolve_provider(result)  # current endpoint binding, without reading model keys
        return result
    except JobError:
        raise
    except ValidationError:
        raise JobError("durable_request_unsupported", 422) from None
    except (ValueError, TypeError, AttributeError):
        raise JobError("job_provider_policy_invalid", 503) from None


async def submit(request: Request, generation: Any, prompt: str) -> dict[str, Any]:
    runtime, principal = await authorized(request)
    if not runtime.submissions:
        raise JobError("durable_admission_disabled", 503)
    normalized = envelope(generation, prompt)
    # Queue dispatch is Scheduler-owned. Atomic intent creation means an outage
    # cannot lose accepted work; no local task is started by this route.
    accepted = await asyncio.to_thread(
        runtime.store.accept,
        principal,
        request.headers.get("Idempotency-Key", ""),
        normalized,
    )
    return {
        **status(accepted.job),
        "status": "started",
        "stream_url": f"/stream/{accepted.job.job_id}",
        "idempotent_replay": not accepted.created,
    }


async def inspect(request: Request, job_id: str) -> dict[str, Any]:
    runtime, principal = await authorized(request)
    return status(await asyncio.to_thread(runtime.store.get, principal, job_id))


async def cancel(request: Request, job_id: str) -> dict[str, Any]:
    runtime, principal = await authorized(request)
    for _ in range(5):
        job = await asyncio.to_thread(runtime.store.get, principal, job_id)
        if job.state in TERMINAL:
            return status(job)
        try:
            return status(
                await asyncio.to_thread(
                    runtime.store.cancel,
                    principal,
                    job_id,
                    job.version,
                    job.fencing_token,
                )
            )
        except JobError as error:
            if error.code == "job_lease_lost":
                await asyncio.to_thread(runtime.store.reconcile, 100)
            elif error.code not in {"job_conflict", "job_terminal"}:
                raise
    raise JobError("job_cancel_retry", 409)


async def _bounded_read(
    runtime: DurableRuntime,
    read: Callable[[], Any],
    discard: Callable[[Any], None] | None = None,
) -> Any:
    """Cancellation cannot release capacity while blocking SDK work still runs.

    On success the caller owns the permit until its result/file is consumed. On
    cancellation a done callback disposes any late file and releases the permit.
    """
    if not runtime.downloads.acquire(blocking=False):
        raise JobError("artifact_read_capacity", 429)
    task = asyncio.create_task(asyncio.to_thread(read))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:

        def settled(done: asyncio.Task[Any]) -> None:
            try:
                value = done.result()
                if discard:
                    discard(value)
            # Consume a late cancelled read's failure after its request ended.
            except BaseException as error:  # noqa: BLE001
                logger.debug(
                    "Cancelled artifact read settled: %s", type(error).__name__
                )
            finally:
                runtime.downloads.release()

        task.add_done_callback(settled)
        raise
    except BaseException:
        runtime.downloads.release()
        raise


async def result(request: Request, job_id: str) -> dict[str, Any]:
    runtime, principal = await authorized(request)
    job = await asyncio.to_thread(runtime.store.get, principal, job_id)
    if job.state != JobState.COMPLETED:
        raise JobError("job_result_not_ready", 409)

    def read() -> dict[str, Any]:
        manifest = runtime.artifacts.committed_manifest(job)
        # Recheck expiry after bounded object I/O, before releasing private bytes.
        runtime.store.get(principal, job_id)
        return {
            "success": True,
            "mode": manifest.get("mode"),
            "prompt": manifest.get("prompt"),
            "manifest": manifest,
            "run_id": job.run_id,
            "job_id": job.job_id,
            "durable": True,
            "manifest_path": f"/artifacts?run_id={job.run_id}&artifact=manifest.json",
            "output_dir": None,
        }

    value = await _bounded_read(runtime, read)
    runtime.downloads.release()
    return value


async def download(request: Request, run_id: str, artifact: str) -> StreamingResponse:
    runtime, principal = await authorized(request)
    job = await asyncio.to_thread(runtime.store.get_run, principal, run_id)
    if artifact not in TYPES:
        raise JobError("artifact_unavailable", 404)
    if job.state != JobState.COMPLETED:
        raise JobError("artifact_not_ready", 409)
    source = None
    released = False

    def close() -> None:
        nonlocal released
        if not released:
            released = True
            if source is not None:
                source.close()
            runtime.downloads.release()

    def read():
        manifest = runtime.artifacts.committed_manifest(job)
        ref = runtime.artifacts.committed_ref(job, manifest, artifact)
        opened = runtime.artifacts.open_verified(ref)
        try:
            runtime.store.get(principal, job.job_id)
        except BaseException:
            opened.close()
            raise
        return ref, opened

    ref, source = await _bounded_read(runtime, read, lambda pair: pair[1].close())
    try:

        def chunks():
            try:
                while data := source.read(65536):
                    yield data
            finally:
                close()

        return StreamingResponse(
            chunks(),
            media_type=TYPES[artifact],
            headers={
                "Content-Disposition": f'attachment; filename="{artifact}"',
                "X-Content-Type-Options": "nosniff",
                "Content-Length": str(ref.size_bytes),
                "Cache-Control": "private, no-store",
                "Content-Security-Policy": "sandbox; default-src 'none'",
            },
            background=BackgroundTask(close),
        )
    except BaseException:
        close()
        raise


def _sse(kind: str, data: dict[str, Any], cursor: int | None = None) -> str:
    return (
        f"id: {cursor}\n" if cursor is not None else ""
    ) + f"event: {kind}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def event_frame(event: JobEvent) -> str:
    if event.kind == "log":
        return _sse(
            "log",
            {"level": event.log_level, "message": event.log_message, "details": {}},
            event.event_id,
        )
    if event.kind == "terminal":
        if event.state == JobState.COMPLETED:
            return _sse(
                "complete",
                {
                    "success": True,
                    "job_id": event.job_id,
                    "result_url": f"/jobs/{event.job_id}/result",
                },
                event.event_id,
            )
        return _sse(
            "error",
            {
                "code": f"generation_{event.state.value}",
                "status": event.state.value,
                "message": f"Generation {event.state.value}.",
            },
            event.event_id,
        )
    return _sse(
        "progress",
        {
            "node": "queued" if event.state == JobState.ACCEPTED else "generation",
            "percentage": event.progress or 0,
            "job_status": event.state.value,
            "message": (
                "Waiting for a worker."
                if event.state == JobState.ACCEPTED
                else "Generation is running."
            ),
        },
        event.event_id,
    )


async def stream(request: Request, job_id: str) -> StreamingResponse:
    runtime, principal = await authorized(request)
    await asyncio.to_thread(runtime.store.get, principal, job_id)
    raw = request.headers.get("Last-Event-ID", "0")
    malformed = (
        not raw.isascii() or not raw.isdigit() or len(raw) > 19 or int(raw) > 2**63 - 1
    )
    cursor = 0 if malformed else int(raw)
    if not runtime.streams.acquire(blocking=False):
        raise JobError("job_stream_capacity", 429)
    with runtime.stream_lock:
        count = runtime.owner_streams.get(principal.owner, 0)
        if count >= 5:
            runtime.streams.release()
            raise JobError("job_stream_capacity", 429)
        runtime.owner_streams[principal.owner] = count + 1
    released = False

    def close() -> None:
        nonlocal released
        if not released:
            released = True
            with runtime.stream_lock:
                remaining = runtime.owner_streams[principal.owner] - 1
                if remaining:
                    runtime.owner_streams[principal.owner] = remaining
                else:
                    runtime.owner_streams.pop(principal.owner)
            runtime.streams.release()

    async def frames():
        nonlocal cursor
        end = time.monotonic() + runtime.connection_seconds
        gap_reported = False
        try:
            if malformed:
                yield _sse(
                    "events_truncated",
                    {
                        "reason": "invalid_event_id",
                        "message": "Invalid replay cursor; replaying retained history.",
                    },
                )
            # Connections are bounded below IAP's maximum lifetime. Reverify the
            # original assertion and job access each poll; expired tokens close.
            while time.monotonic() < end:
                await asyncio.to_thread(
                    verified_principal, request.headers, runtime.verifier
                )
                job = await asyncio.to_thread(runtime.store.get, principal, job_id)
                try:
                    page = await asyncio.to_thread(
                        runtime.store.replay, principal, job_id, cursor, 100
                    )
                except JobError as error:
                    if error.code == "job_cursor_future":
                        yield _sse(
                            "events_truncated",
                            {
                                "reason": "future_event_id",
                                "message": "Cursor is ahead of retained history. Inspect the existing job.",
                            },
                        )
                        return
                    raise
                if page.truncated and not gap_reported:
                    gap_reported = True
                    yield _sse(
                        "events_truncated",
                        {
                            "reason": "history_pruned",
                            "message": "Some history expired. The job result remains discoverable.",
                        },
                    )
                terminal = False
                for event in page.events:
                    if time.monotonic() >= end:
                        return
                    await asyncio.to_thread(
                        verified_principal, request.headers, runtime.verifier
                    )
                    if runtime.clock() >= job.expires_at:
                        raise JobError("job_unavailable", 404)
                    cursor = event.event_id
                    terminal = terminal or event.kind == "terminal"
                    yield event_frame(event)
                if terminal:
                    return
                if job.state in TERMINAL and page.next_cursor >= job.event_cursor:
                    if cursor < job.event_cursor:
                        if time.monotonic() >= end:
                            return
                        await asyncio.to_thread(
                            verified_principal, request.headers, runtime.verifier
                        )
                        if runtime.clock() >= job.expires_at:
                            raise JobError("job_unavailable", 404)
                        # Terminal status is independent of the pruned history.
                        yield event_frame(
                            JobEvent(
                                job_id=job_id,
                                event_id=job.event_cursor,
                                fencing_token=job.fencing_token,
                                kind="terminal",
                                state=job.state,
                                created_at=job.created_at,
                                expires_at=job.expires_at,
                            )
                        )
                    return
                cursor = page.next_cursor
                if page.next_cursor < page.latest_cursor:
                    continue
                if await request.is_disconnected():
                    return
                yield ": keepalive\n\n"
                await asyncio.sleep(runtime.poll_seconds)
            yield _sse(
                "log",
                {
                    "level": "info",
                    "message": "Progress connection renewed; reconnect to the same job.",
                },
            )
        except JobError as error:
            yield _sse(
                "error",
                {
                    "code": error.code,
                    "message": "Progress access is unavailable. Inspect the existing job after authentication.",
                },
            )
        finally:
            close()

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={"Cache-Control": "private, no-store", "X-Accel-Buffering": "no"},
        background=BackgroundTask(close),
    )
