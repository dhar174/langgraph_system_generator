"""A managed task holds its HTTP request until its attempt is durably settled."""

import asyncio
import shutil
import uuid
from pathlib import Path
from threading import BoundedSemaphore
from typing import Any, Protocol

from pydantic import Field

from .execution import ExecutionLimits, trusted_directory
from .models import TERMINAL, ArtifactRef, DurableJob, JobError, JobState, Record
from .protocols import JobStore
from .service import WorkerJobService


class TaskPayload(Record):
    job_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    dispatch_generation: int = Field(ge=1, le=12, strict=True)


class AttemptRunner(Protocol):
    async def run(
        self, job: DurableJob, directory: Path, progress: Any
    ) -> ArtifactRef: ...


class ManagedWorker:
    def __init__(
        self,
        store: JobStore,
        runner: AttemptRunner,
        root: Path,
        *,
        limits: ExecutionLimits | None = None,
        heartbeat_seconds: float = 15,
        capacity: int = 1,
    ):
        self.store, self.runner, self.root = store, runner, root.absolute()
        self.limits = limits or ExecutionLimits()
        if not 0 < heartbeat_seconds <= 30 or not 1 <= capacity <= 8:
            raise JobError("worker_configuration_invalid", 503)
        self.heartbeat_seconds = heartbeat_seconds
        self.capacity = BoundedSemaphore(capacity)

    async def execute(
        self, service: WorkerJobService, task: TaskPayload
    ) -> tuple[int, dict[str, Any]]:
        if not self.capacity.acquire(blocking=False):
            return 503, {"code": "worker_busy"}
        execution = None
        directory = None
        job = None
        worker_id = uuid.uuid4().hex
        try:
            current = await asyncio.to_thread(self.store.inspect_attempt, task.job_id)
            if current.state in TERMINAL:
                return 200, {"state": current.state.value}
            if current.dispatch.generation != task.dispatch_generation:
                return 204, {}
            job = await asyncio.to_thread(
                service.claim, task.job_id, current.dispatch.intent_id, worker_id
            )
            root = trusted_directory(self.root)
            parent = trusted_directory(root / job.job_id)
            directory = parent / f"attempt-{job.fencing_token}-{worker_id}"
            directory.mkdir()  # exclusive; never reuse another attempt's files
            latest: int | None = None

            def progress(value: int) -> None:
                nonlocal latest
                # One coalescing slot, no per-log task or growing buffer. Prompt,
                # provider bodies and arbitrary log messages never enter events.
                latest = value

            execution = asyncio.create_task(self.runner.run(job, directory, progress))
            started = asyncio.get_running_loop().time()
            while True:
                done, _ = await asyncio.wait(
                    {execution}, timeout=self.heartbeat_seconds
                )
                # Renew is also the durable cancellation/fence/deadline check.
                job = await asyncio.to_thread(service.renew, job, worker_id)
                if done:
                    break
                if (
                    asyncio.get_running_loop().time() - started
                    >= self.limits.attempt_seconds
                ):
                    raise JobError("attempt_deadline", 503)
                if latest is not None:
                    job = await asyncio.to_thread(
                        service.append_event, job, worker_id, latest
                    )
                    latest = None
            ref = execution.result()
            if not ref.object_name.startswith(
                f"runs/{job.run_id}/attempt-{job.fencing_token}/"
            ):
                raise JobError("artifact_reference_invalid", 422)
            job = await asyncio.to_thread(
                service.finalize, job, worker_id, JobState.COMPLETED, ref
            )
            return 200, {"state": job.state.value}
        except JobError as error:
            # Stop/reap execution before revoking a lease or acknowledging retry.
            if execution is not None and not execution.done():
                execution.cancel()
                await asyncio.gather(execution, return_exceptions=True)
            if job is not None:
                try:
                    if error.code in {
                        "job_lease_lost",
                        "job_conflict",
                        "job_terminal",
                        "job_backend_unavailable",
                    }:
                        return 503, {"code": "attempt_authority_lost"}
                    if error.status >= 500:
                        settled = await asyncio.to_thread(
                            service.relinquish, job, worker_id
                        )
                        if settled.state == JobState.ACCEPTED:
                            await asyncio.to_thread(
                                self.store.reschedule_dispatch,
                                settled.job_id,
                                settled.version,
                                settled.fencing_token,
                                settled.dispatch.intent_id,
                                min(60, 5 * 2 ** (settled.attempt_count - 1)),
                            )
                    else:
                        await asyncio.to_thread(
                            service.finalize, job, worker_id, JobState.FAILED
                        )
                    return 200, {"state": "settled"}
                except JobError:
                    return 503, {"code": "attempt_settlement_unavailable"}
            if error.status == 404:
                return 204, {}
            return 503, {"code": "attempt_unavailable"}
        except asyncio.CancelledError:
            # Shutdown is not owner cancellation. Lease expiry + reconciliation
            # handles recovery even if SIGKILL prevents this cleanup.
            raise
        except Exception:  # noqa: BLE001 - no raw provider/storage bodies in HTTP
            return 503, {"code": "attempt_infrastructure_failure"}
        finally:
            if execution is not None:
                if not execution.done():
                    execution.cancel()
                await asyncio.gather(execution, return_exceptions=True)
            if directory is not None and directory.exists():
                # Validate the resolved absolute target within the trusted root
                # before recursive deletion. Winning objects live in GCS.
                try:
                    directory.resolve(strict=True).relative_to(
                        self.root.resolve(strict=True)
                    )
                    if not directory.is_symlink():
                        shutil.rmtree(directory)
                except (OSError, ValueError):
                    pass  # private orphan; never turn committed success into failure
            self.capacity.release()
