"""Synchronous storage ports; async HTTP callers must offload blocking SDK I/O."""

from pathlib import Path
from typing import Protocol

from .models import (
    Acceptance,
    ArtifactRef,
    DispatchIntent,
    DurableJob,
    EventPage,
    GenerationRequestEnvelope,
    JobState,
    Principal,
    Reconciliation,
    ServiceIdentity,
)


class JobStore(Protocol):
    def accept(
        self, principal: Principal, key: str, request: GenerationRequestEnvelope
    ) -> Acceptance: ...
    def get(self, principal: Principal, job_id: str) -> DurableJob: ...
    def inspect_attempt(self, job_id: str) -> DurableJob:
        """Internal authenticated worker only; never a user-facing lookup."""
        ...

    def claim(
        self, job_id: str, version: int, fence: int, worker_id: str, intent_id: str
    ) -> DurableJob: ...
    def renew(
        self, job_id: str, version: int, fence: int, worker_id: str
    ) -> DurableJob: ...
    def relinquish(
        self, job_id: str, version: int, fence: int, worker_id: str
    ) -> DurableJob: ...
    def append_event(
        self, job_id: str, version: int, fence: int, worker_id: str, progress: int
    ) -> DurableJob: ...
    def replay(
        self, principal: Principal, job_id: str, after: int = 0, limit: int = 100
    ) -> EventPage: ...
    def cancel(
        self, principal: Principal, job_id: str, version: int, fence: int
    ) -> DurableJob: ...
    def finalize(
        self,
        job_id: str,
        version: int,
        fence: int,
        worker_id: str,
        state: JobState,
        result: ArtifactRef | None = None,
    ) -> DurableJob: ...
    def mark_dispatched(
        self, job_id: str, version: int, fence: int, intent_id: str, task_ref: str
    ) -> DurableJob: ...
    def pending_dispatch(self, limit: int = 100) -> tuple[DispatchIntent, ...]: ...
    def reconcile(self, limit: int = 100) -> Reconciliation: ...


class JobDispatcher(Protocol):
    def dispatch(self, intent: DispatchIntent) -> str:
        """B2: idempotently create a task named by intent_id; return task reference."""
        ...


class InternalCallerVerifier(Protocol):
    def verify(self, authorization: str) -> ServiceIdentity:
        """B2: verify IAM OIDC issuer/signature/lifetime/audience before worker use."""
        ...


class ArtifactStore(Protocol):
    def publish_manifest(
        self, job: DurableJob, files: tuple[Path, ...], fence: int
    ) -> ArtifactRef:
        """B3: upload immutable attempt objects; caller must fence finalization."""
        ...

    def read_manifest(self, ref: ArtifactRef) -> bytes: ...
    def delete(self, ref: ArtifactRef) -> None:
        """B3: generation-match deletion, never delete a replacement object."""
        ...
