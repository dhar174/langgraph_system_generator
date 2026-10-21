"""Transactional job state machine, shared by memory and Firestore adapters."""

import hashlib
import hmac
import json
import re
import time
import uuid
from collections.abc import Callable
from typing import Any, Protocol, TypeVar

from langgraph_system_generator import __version__

from .models import (
    TERMINAL,
    Acceptance,
    ArtifactRef,
    AttemptLease,
    DispatchIntent,
    DurableJob,
    EventKind,
    EventPage,
    GenerationRequestEnvelope,
    JobError,
    JobEvent,
    JobState,
    Principal,
    Reconciliation,
    ServiceIdentity,
)
from .protocols import InternalCallerVerifier, JobStore

T = TypeVar("T")
Document = dict[str, Any]


class Transaction(Protocol):
    def get(self, path: str) -> Document | None: ...
    def set(self, path: str, value: Document) -> None: ...
    def delete(self, path: str) -> None: ...


class Database(Protocol):
    def run(self, callback: Callable[[Transaction], T]) -> T: ...
    def due(
        self,
        collection: str,
        field: str,
        now: float,
        limit: int,
        *,
        deadline_field: str | None = None,
    ) -> list[str]: ...


def _json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


class TransactionalJobStore:
    """All public worker methods are internal-service ports, not HTTP endpoints.

    B2 authenticates IAM callers before invoking worker ports. User-facing ports
    always require Principal. No dependency here can dispatch, generate or upload.
    """

    def __init__(
        self,
        database: Database,
        idempotency_secret: bytes,
        *,
        clock: Callable[[], float] = time.time,
        max_events: int = 1000,
        lease_seconds: int = 240,
        max_attempts: int = 3,
        approved_provider_refs: frozenset[str] = frozenset({"openai-v1"}),
    ):
        if (
            len(idempotency_secret) < 32
            or not 1 <= max_events <= 1000
            or not 1 <= lease_seconds <= 240
            or not 1 <= max_attempts <= 3
            or not 1 <= len(approved_provider_refs) <= 32
            or any(
                not re.fullmatch(r"[a-z0-9_-]{1,80}", ref)
                for ref in approved_provider_refs
            )
        ):
            raise JobError("job_configuration_invalid", 503)
        self.db = database
        self.secret = idempotency_secret
        self.clock = clock
        self.max_events = max_events
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts
        self.approved_provider_refs = approved_provider_refs

    @staticmethod
    def _path(job_id: str) -> str:
        if not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise JobError("job_unavailable", 404)
        return f"jobs/{job_id}"

    def _load(self, tx: Transaction, job_id: str, now: float) -> DurableJob:
        data = tx.get(self._path(job_id))
        if data is None:
            raise JobError("job_unavailable", 404)
        job = DurableJob.model_validate(data)
        if now >= job.expires_at:
            raise JobError("job_unavailable", 404)
        return job

    @staticmethod
    def _owner(job: DurableJob, principal: Principal) -> None:
        if job.owner.owner != principal.owner:
            raise JobError("job_unavailable", 404)

    @staticmethod
    def _expected(job: DurableJob, version: int, fence: int) -> None:
        if job.state in TERMINAL:
            raise JobError("job_terminal")
        if job.version != version or job.fencing_token != fence:
            raise JobError("job_conflict")

    @staticmethod
    def _live(job: DurableJob, worker: str, now: float) -> None:
        if (
            job.state != JobState.RUNNING
            or job.lease is None
            or job.lease.worker_id != worker
            or job.lease.fencing_token != job.fencing_token
            or now >= job.lease.expires_at
            or now >= job.deadline_at
        ):
            raise JobError("job_lease_lost")

    def _write(
        self,
        tx: Transaction,
        job: DurableJob,
        now: float,
        kind: EventKind | None = None,
        progress: int | None = None,
    ) -> DurableJob:
        # No reads after this point: Firestore transactions require reads first.
        if kind:
            cursor = job.event_cursor + 1
            first = max(job.first_event_id, cursor - self.max_events + 1)
            event = JobEvent(
                job_id=job.job_id,
                event_id=cursor,
                fencing_token=job.fencing_token,
                kind=kind,
                state=job.state,
                progress=progress,
                created_at=now,
                expires_at=job.event_expires_at,
            )
            for event_id in range(job.first_event_id, first):
                tx.delete(f"jobs/{job.job_id}/events/{event_id:020d}")
            tx.set(
                f"jobs/{job.job_id}/events/{cursor:020d}", event.model_dump(mode="json")
            )
            job = job.model_copy(
                update={"event_cursor": cursor, "first_event_id": first}
            )
        tx.set(self._path(job.job_id), job.model_dump(mode="json"))
        dispatch_data = job.dispatch.model_dump(mode="json")
        # Deadline eligibility must be filtered before the bounded query result.
        dispatch_data["due_at"] = (
            job.dispatch.available_at if job.dispatch.pending else None
        )
        dispatch_data["expires_at"] = job.expires_at
        dispatch_data["deadline_at"] = job.deadline_at
        tx.set(f"dispatch/{job.job_id}", dispatch_data)
        return job

    def accept(
        self, principal: Principal, key: str, request: GenerationRequestEnvelope
    ) -> Acceptance:
        if not isinstance(principal, Principal):
            raise JobError("identity_required", 401)
        if not key or len(key.encode("utf-8")) > 256:
            raise JobError("idempotency_key_invalid", 400)
        canonical = _json(request.model_dump(mode="json"))
        if len(canonical) > 65536:
            raise JobError("job_request_too_large", 413)
        fingerprint = hashlib.sha256(canonical).hexdigest()
        key_id = hmac.new(
            self.secret, _json([*principal.owner, key]), hashlib.sha256
        ).hexdigest()
        job_id, run_id = uuid.uuid4().hex, uuid.uuid4().hex

        def operation(tx: Transaction) -> Acceptance:
            now = self.clock()
            existing = tx.get(f"idempotency/{key_id}")
            if existing and now < existing["expires_at"]:
                if existing["fingerprint"] != fingerprint:
                    raise JobError("idempotency_conflict")
                job = self._load(tx, existing["job_id"], now)
                self._owner(job, principal)
                return Acceptance(job=job, created=False)
            if request.provider_ref not in self.approved_provider_refs:
                raise JobError("job_provider_not_approved", 403)
            if request.generator_version != __version__:
                raise JobError("job_generator_version_invalid", 400)
            intent = DispatchIntent(
                intent_id=f"{job_id}-1", job_id=job_id, generation=1, available_at=now
            )
            job = DurableJob(
                job_id=job_id,
                run_id=run_id,
                owner=principal,
                request=request,
                request_fingerprint=fingerprint,
                attempt_limit=self.max_attempts,
                created_at=now,
                deadline_at=now + 900,
                expires_at=now + 7 * 86400,
                event_expires_at=now + 86400,
                dispatch=intent,
                next_action_at=now + 900,
            )
            tx.set(
                f"idempotency/{key_id}",
                {
                    "job_id": job_id,
                    "fingerprint": fingerprint,
                    "expires_at": now + 86400,
                },
            )
            return Acceptance(job=self._write(tx, job, now, "accepted"), created=True)

        return self.db.run(operation)

    def get(self, principal: Principal, job_id: str) -> DurableJob:
        def operation(tx: Transaction) -> DurableJob:
            job = self._load(tx, job_id, self.clock())
            self._owner(job, principal)
            return job

        return self.db.run(operation)

    def inspect_attempt(self, job_id: str) -> DurableJob:
        """Internal port; use WorkerJobService after verified IAM authorization."""
        return self.db.run(lambda tx: self._load(tx, job_id, self.clock()))

    def _mutate(
        self,
        job_id: str,
        version: int,
        fence: int,
        transition: Callable[[DurableJob, float], tuple[DurableJob, EventKind | None]],
        progress: int | None = None,
        principal: Principal | None = None,
    ) -> DurableJob:
        def operation(tx: Transaction) -> DurableJob:
            now = self.clock()
            job = self._load(tx, job_id, now)
            if principal is not None:
                self._owner(job, principal)
            self._expected(job, version, fence)
            updated, kind = transition(job, now)
            updated = updated.model_copy(update={"version": job.version + 1})
            return self._write(tx, updated, now, kind, progress)

        return self.db.run(operation)

    def claim(
        self, job_id: str, version: int, fence: int, worker_id: str, intent_id: str
    ) -> DurableJob:
        def transition(job: DurableJob, now: float) -> tuple[DurableJob, EventKind]:
            if job.dispatch.intent_id != intent_id:
                raise JobError("dispatch_conflict")
            if now >= job.deadline_at or job.attempt_count >= job.attempt_limit:
                raise JobError("job_attempts_exhausted")
            if now < job.dispatch.available_at:
                raise JobError("dispatch_not_due")
            if (
                job.state == JobState.RUNNING
                and job.lease
                and now < job.lease.expires_at
            ):
                raise JobError("job_already_claimed")
            lease = AttemptLease(
                worker_id=worker_id,
                fencing_token=job.fencing_token + 1,
                expires_at=min(now + self.lease_seconds, job.deadline_at),
            )
            return (
                job.model_copy(
                    update={
                        "state": JobState.RUNNING,
                        "attempt_count": job.attempt_count + 1,
                        "fencing_token": lease.fencing_token,
                        "lease": lease,
                        "next_action_at": lease.expires_at,
                        "dispatch": job.dispatch.model_copy(update={"pending": False}),
                    }
                ),
                "running",
            )

        return self._mutate(job_id, version, fence, transition)

    def renew(
        self, job_id: str, version: int, fence: int, worker_id: str
    ) -> DurableJob:
        def transition(job: DurableJob, now: float) -> tuple[DurableJob, None]:
            self._live(job, worker_id, now)
            assert job.lease is not None
            expiry = min(now + self.lease_seconds, job.deadline_at)
            return (
                job.model_copy(
                    update={
                        "lease": job.lease.model_copy(update={"expires_at": expiry}),
                        "next_action_at": expiry,
                    }
                ),
                None,
            )

        return self._mutate(job_id, version, fence, transition)

    def append_event(
        self, job_id: str, version: int, fence: int, worker_id: str, progress: int
    ) -> DurableJob:
        if type(progress) is not int or not 0 <= progress <= 100:
            raise JobError("job_progress_invalid", 400)

        def transition(job: DurableJob, now: float) -> tuple[DurableJob, EventKind]:
            self._live(job, worker_id, now)
            return job, "progress"

        return self._mutate(job_id, version, fence, transition, progress)

    @staticmethod
    def _terminal(job: DurableJob, state: JobState) -> DurableJob:
        return job.model_copy(
            update={
                "state": state,
                "lease": None,
                "next_action_at": None,
                "dispatch": job.dispatch.model_copy(update={"pending": False}),
            }
        )

    def _retry(self, job: DurableJob, now: float) -> tuple[DurableJob, EventKind]:
        if now >= job.deadline_at:
            return self._terminal(job, JobState.EXPIRED), "terminal"
        if (
            job.attempt_count >= job.attempt_limit
            or job.dispatch.generation >= job.dispatch_limit
        ):
            return self._terminal(job, JobState.FAILED), "terminal"
        generation = job.dispatch.generation + 1
        return (
            job.model_copy(
                update={
                    "state": JobState.ACCEPTED,
                    "fencing_token": job.fencing_token + 1,
                    "lease": None,
                    "next_action_at": job.deadline_at,
                    "dispatch": DispatchIntent(
                        intent_id=f"{job.job_id}-{generation}",
                        job_id=job.job_id,
                        generation=generation,
                        available_at=now,
                    ),
                }
            ),
            "retry",
        )

    def relinquish(
        self, job_id: str, version: int, fence: int, worker_id: str
    ) -> DurableJob:
        def transition(job: DurableJob, now: float) -> tuple[DurableJob, EventKind]:
            self._live(job, worker_id, now)
            return self._retry(job, now)

        return self._mutate(job_id, version, fence, transition)

    def cancel(
        self, principal: Principal, job_id: str, version: int, fence: int
    ) -> DurableJob:
        def transition(job: DurableJob, now: float) -> tuple[DurableJob, EventKind]:
            # Cancellation is an owner operation, never authority held by a worker.
            if now >= job.deadline_at or (
                job.lease is not None and now >= job.lease.expires_at
            ):
                raise JobError("job_lease_lost")
            cancelled = self._terminal(job, JobState.CANCELLED)
            return (
                cancelled.model_copy(
                    update={"cancellation_requested": True, "fencing_token": fence + 1}
                ),
                "terminal",
            )

        return self._mutate(job_id, version, fence, transition, principal=principal)

    def finalize(
        self,
        job_id: str,
        version: int,
        fence: int,
        worker_id: str,
        state: JobState,
        result: ArtifactRef | None = None,
    ) -> DurableJob:
        if state not in {JobState.COMPLETED, JobState.FAILED} or (
            (state == JobState.COMPLETED) != (result is not None)
        ):
            raise JobError("job_result_invalid", 400)

        def transition(job: DurableJob, now: float) -> tuple[DurableJob, EventKind]:
            self._live(job, worker_id, now)
            if result and not result.object_name.startswith(f"runs/{job.run_id}/"):
                raise JobError("job_result_invalid", 400)
            return (
                self._terminal(job, state).model_copy(update={"result": result}),
                "terminal",
            )

        return self._mutate(job_id, version, fence, transition)

    def mark_dispatched(
        self, job_id: str, version: int, fence: int, intent_id: str, task_ref: str
    ) -> DurableJob:
        if not re.fullmatch(r"[A-Za-z0-9_/-]{1,512}", task_ref):
            raise JobError("dispatch_reference_invalid", 400)

        def transition(job: DurableJob, now: float) -> tuple[DurableJob, None]:
            if (
                job.state != JobState.ACCEPTED
                or not job.dispatch.pending
                or job.dispatch.intent_id != intent_id
                or now >= job.deadline_at
            ):
                raise JobError("dispatch_conflict")
            return (
                job.model_copy(
                    update={
                        "dispatch": job.dispatch.model_copy(
                            update={"pending": False, "task_ref": task_ref}
                        ),
                        "next_action_at": min(now + 60, job.deadline_at),
                    }
                ),
                None,
            )

        return self._mutate(job_id, version, fence, transition)

    def reschedule_dispatch(
        self,
        job_id: str,
        version: int,
        fence: int,
        intent_id: str,
        delay_seconds: int = 5,
    ) -> DurableJob:
        """B2: rotate an unclaimed lost/tombstoned wakeup in the existing store.

        The CAS prevents concurrent reconcilers from rotating twice. This does not
        grant a generation attempt or authorize a running worker to publish.
        """
        if type(delay_seconds) is not int or not 1 <= delay_seconds <= 60:
            raise JobError("dispatch_delay_invalid", 400)

        def transition(job: DurableJob, now: float) -> tuple[DurableJob, EventKind]:
            if job.state != JobState.ACCEPTED or job.dispatch.intent_id != intent_id:
                raise JobError("dispatch_conflict")
            updated, kind = self._retry(job, now)
            if updated.state == JobState.ACCEPTED:
                updated = updated.model_copy(
                    update={
                        "dispatch": updated.dispatch.model_copy(
                            update={
                                "available_at": min(
                                    now + delay_seconds, job.deadline_at
                                ),
                            }
                        ),
                    }
                )
            return updated, kind

        return self._mutate(job_id, version, fence, transition)

    @staticmethod
    def _limit(limit: int) -> None:
        if not 1 <= limit <= 100:
            raise JobError("job_page_invalid", 400)

    def pending_dispatch(self, limit: int = 100) -> tuple[DispatchIntent, ...]:
        self._limit(limit)
        now = self.clock()
        paths = self.db.due(
            "dispatch", "due_at", now, limit, deadline_field="deadline_at"
        )

        def operation(tx: Transaction) -> tuple[DispatchIntent, ...]:
            now = self.clock()
            intents = []
            for path in paths:
                data = tx.get(path)
                if not data or now >= data["expires_at"] or not data["pending"]:
                    continue
                job = self._load(tx, data["job_id"], now)
                if job.state == JobState.ACCEPTED and now < job.deadline_at:
                    intents.append(job.dispatch)
            return tuple(intents)

        return self.db.run(operation)

    def replay(
        self, principal: Principal, job_id: str, after: int = 0, limit: int = 100
    ) -> EventPage:
        self._limit(limit)
        if not 0 <= after <= 2**63 - 1:
            raise JobError("job_cursor_invalid", 400)

        def operation(tx: Transaction) -> EventPage:
            now = self.clock()
            job = self._load(tx, job_id, now)
            self._owner(job, principal)
            if after > job.event_cursor:
                raise JobError("job_cursor_future", 400)
            expired = now >= job.event_expires_at
            start = max(after + 1, job.first_event_id)
            events = []
            if not expired:
                for cursor in range(start, min(job.event_cursor + 1, start + limit)):
                    data = tx.get(f"jobs/{job_id}/events/{cursor:020d}")
                    if data and now < data["expires_at"]:
                        events.append(JobEvent.model_validate(data))
            return EventPage(
                events=tuple(events),
                next_cursor=events[-1].event_id if events else job.event_cursor,
                truncated=expired or after < job.first_event_id - 1,
                latest_cursor=job.event_cursor,
            )

        return self.db.run(operation)

    def reconcile(self, limit: int = 100) -> Reconciliation:
        self._limit(limit)
        paths = self.db.due("jobs", "next_action_at", self.clock(), limit)
        changed = []
        for path in paths:

            def operation(tx: Transaction, path: str = path) -> bool:
                now = self.clock()
                data = tx.get(path)
                if not data:
                    return False
                job = DurableJob.model_validate(data)
                if (
                    job.state in TERMINAL
                    or job.next_action_at is None
                    or now < job.next_action_at
                ):
                    return False
                # Snapshot is read in this transaction; CAS and fence are explicit.
                self._expected(job, job.version, job.fencing_token)
                updated, kind = self._retry(job, now)
                updated = updated.model_copy(update={"version": job.version + 1})
                self._write(tx, updated, now, kind)
                return True

            if self.db.run(operation):
                changed.append(path.split("/")[-1])
        return Reconciliation(inspected=len(paths), changed=tuple(changed))


class WorkerJobService:
    """B2 integration boundary for an already verified internal IAM identity.

    Construct only from InternalCallerVerifier.verify(), never from user JSON or
    an IAP Principal. No unsigned service identity verifier ships in B1.
    """

    def __init__(
        self,
        store: JobStore,
        identity: ServiceIdentity,
        *,
        audience: str,
        allowed_accounts: frozenset[str],
    ):
        if (
            not isinstance(identity, ServiceIdentity)
            or identity.audience != audience
            or identity.service_account not in allowed_accounts
        ):
            raise JobError("worker_identity_forbidden", 403)
        self.store = store
        self.identity = identity

    def claim(self, job_id: str, intent_id: str, worker_id: str) -> DurableJob:
        job = self.store.inspect_attempt(job_id)
        return self.store.claim(
            job_id, job.version, job.fencing_token, worker_id, intent_id
        )

    @classmethod
    def from_authorization(
        cls,
        store: JobStore,
        verifier: InternalCallerVerifier,
        authorization: str,
        *,
        audience: str,
        allowed_accounts: frozenset[str],
    ) -> "WorkerJobService":
        """B2 routes must use this factory with their verified OIDC implementation."""
        identity = verifier.verify(authorization)
        return cls(
            store, identity, audience=audience, allowed_accounts=allowed_accounts
        )

    def renew(self, job: DurableJob, worker_id: str) -> DurableJob:
        return self.store.renew(job.job_id, job.version, job.fencing_token, worker_id)

    def append_event(
        self, job: DurableJob, worker_id: str, progress: int
    ) -> DurableJob:
        return self.store.append_event(
            job.job_id, job.version, job.fencing_token, worker_id, progress
        )

    def relinquish(self, job: DurableJob, worker_id: str) -> DurableJob:
        return self.store.relinquish(
            job.job_id, job.version, job.fencing_token, worker_id
        )

    def finalize(
        self,
        job: DurableJob,
        worker_id: str,
        state: JobState,
        result: ArtifactRef | None = None,
    ) -> DurableJob:
        return self.store.finalize(
            job.job_id, job.version, job.fencing_token, worker_id, state, result
        )

    def reconcile(self, limit: int = 100) -> Reconciliation:
        return self.store.reconcile(limit)
