"""Separate private Cloud Run service. Never mounted on the public IAP app."""

import asyncio
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from langgraph_system_generator.jobs.cloud_tasks_dispatcher import (
    CloudTasksConfig,
    CloudTasksDispatcher,
)
from langgraph_system_generator.jobs.execution import (
    ExecutionLimits,
    SubprocessAttempt,
    reconciliation_process,
)
from langgraph_system_generator.jobs.gcs_artifacts import GCSArtifactStore
from langgraph_system_generator.jobs.internal_identity import GoogleOIDCVerifier
from langgraph_system_generator.jobs.models import JobError
from langgraph_system_generator.jobs.protocols import InternalCallerVerifier, JobStore
from langgraph_system_generator.jobs.reconciliation import Reconciler
from langgraph_system_generator.jobs.registry import select_job_store
from langgraph_system_generator.jobs.service import WorkerJobService
from langgraph_system_generator.jobs.worker import ManagedWorker, TaskPayload


@dataclass
class WorkerRuntime:
    store: JobStore
    worker: ManagedWorker
    reconcile: Callable[[], Awaitable[dict[str, int]]]
    verifier: InternalCallerVerifier
    audience: str
    task_accounts: frozenset[str]
    scheduler_accounts: frozenset[str]


def dispatch_config() -> CloudTasksConfig:
    try:
        return CloudTasksConfig(
            queue=os.environ["LNF_JOB_TASK_QUEUE"],
            worker_url=os.environ["LNF_WORKER_URL"] + "/internal/execute",
            audience=os.environ["LNF_WORKER_AUDIENCE"],
            service_account=os.environ["LNF_TASK_SERVICE_ACCOUNT"],
            dispatch_deadline=ExecutionLimits().dispatch_deadline,
        )
    except (KeyError, ValueError):
        raise JobError("worker_configuration_invalid", 503) from None


def configured_reconciler() -> Reconciler:
    config = dispatch_config()
    store = select_job_store()
    if store is None:
        raise JobError("durable_backend_required", 503)
    return Reconciler(store, CloudTasksDispatcher(config))


def configured_runtime() -> WorkerRuntime:
    config = dispatch_config()
    scheduler = os.getenv("LNF_SCHEDULER_SERVICE_ACCOUNT", "")
    root = os.getenv("LNF_WORKER_OUTPUT_ROOT", "")
    bucket = os.getenv("LNF_JOB_ARTIFACT_BUCKET", "")
    if (
        not scheduler.endswith(".iam.gserviceaccount.com")
        or scheduler == config.service_account
        or not root
        or not bucket
    ):
        raise JobError("worker_configuration_invalid", 503)
    try:
        from langgraph_system_generator.constants import _compute_base_output

        output_root = Path(root).resolve()
        output_root.relative_to(Path.cwd().resolve())
        output_root.relative_to(_compute_base_output())
    except (OSError, RuntimeError, ValueError):
        raise JobError("worker_output_root_invalid", 503) from None
    GCSArtifactStore(bucket, output_root)  # configuration only; no Google/ADC/client
    store = select_job_store()
    if store is None:
        raise JobError("worker_configuration_invalid", 503)
    limits = ExecutionLimits()
    worker = ManagedWorker(store, SubprocessAttempt(limits), output_root, limits=limits)
    return WorkerRuntime(
        store,
        worker,
        reconciliation_process,
        GoogleOIDCVerifier(config.audience),
        config.audience,
        frozenset({config.service_account}),
        frozenset({scheduler}),
    )


def create_worker_app(runtime: WorkerRuntime | None = None) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    # Lazy construction retains local import safety. The injected runtime is
    # only for trusted tests/embedding, never selected by request JSON/headers.
    app.state.runtime = runtime

    @app.get("/health")
    async def health():
        return {"status": "ok", "public_durable_admission": False}

    async def authorized(
        request: Request, scheduler: bool
    ) -> tuple[WorkerRuntime, WorkerJobService]:
        if not request.headers.get("authorization", "").startswith("Bearer "):
            raise JobError("worker_identity_invalid", 401)
        if app.state.runtime is None:
            app.state.runtime = configured_runtime()
        selected = app.state.runtime
        # Cloud Tasks sets Authorization, not X-Serverless-Authorization (whose
        # signature Cloud Run removes). Never reconstruct stripped claims.
        service = await asyncio.to_thread(
            WorkerJobService.from_authorization,
            selected.store,
            selected.verifier,
            request.headers.get("authorization", ""),
            audience=selected.audience,
            allowed_accounts=(
                selected.scheduler_accounts if scheduler else selected.task_accounts
            ),
        )
        return selected, service

    @app.post("/internal/execute")
    async def execute(request: Request):
        try:
            selected, service = await authorized(request, False)
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > 1024:
                    raise JobError("task_payload_too_large", 413)
            payload = TaskPayload.model_validate_json(raw)
            status, body = await selected.worker.execute(service, payload)
            return (
                Response(status_code=204)
                if status == 204
                else JSONResponse(body, status_code=status)
            )
        except ValidationError:
            return JSONResponse({"code": "task_payload_invalid"}, status_code=422)
        except JobError as error:
            return JSONResponse({"code": error.code}, status_code=error.status)

    @app.post("/internal/reconcile")
    async def reconcile(request: Request):
        try:
            selected, _ = await authorized(request, True)
            return await selected.reconcile()
        except JobError as error:
            return JSONResponse({"code": error.code}, status_code=error.status)

    return app


app = create_worker_app()
