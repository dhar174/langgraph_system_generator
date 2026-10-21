"""Version-one persistence and B2/B3 integration records; no transport objects."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    schema_version: Literal[1] = 1


class Principal(Record):
    issuer: str = Field(min_length=1, max_length=256)
    subject: str = Field(min_length=1, max_length=256)
    email: str | None = Field(default=None, max_length=320)

    @property
    def owner(self) -> tuple[str, str]:
        return self.issuer, self.subject


class ServiceIdentity(Record):
    """Internal IAM caller, never interchangeable with a durable user owner."""

    service_account: str
    audience: str


class GenerationRequestEnvelope(Record):
    prompt: str = Field(min_length=1, max_length=16000, repr=False)
    mode: Literal["stub", "live"] = "stub"
    architecture: Literal[
        "router", "subagents", "hybrid", "autoagent", "deepagents"
    ] = "router"
    model: str = Field(default="gpt-4o-mini", pattern=r"^[A-Za-z0-9_.:/-]{1,128}$")
    provider_ref: str = Field(default="openai-v1", pattern=r"^[a-z0-9_-]{1,80}$")
    generator_version: str = Field(default="1.0.0", pattern=r"^[A-Za-z0-9_.-]{1,64}$")


class JobState(str, Enum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


TERMINAL = frozenset(
    {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED, JobState.EXPIRED}
)


class AttemptLease(Record):
    worker_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    fencing_token: int = Field(ge=1)
    expires_at: float


class DispatchIntent(Record):
    intent_id: str
    job_id: str
    generation: int = Field(ge=1)
    pending: bool = True
    available_at: float
    task_ref: str | None = None


class ArtifactRef(Record):
    """One finalized private manifest object; never a signed URL or local path."""

    bucket: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,221}[a-z0-9]$")
    object_name: str = Field(pattern=r"^runs/[a-f0-9]{32}/[A-Za-z0-9_./-]{1,200}$")
    generation: str = Field(pattern=r"^[0-9]{1,30}$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0)


EventKind = Literal["accepted", "running", "progress", "retry", "terminal"]


class JobEvent(Record):
    job_id: str
    event_id: int = Field(ge=1)
    fencing_token: int = Field(ge=0)
    kind: EventKind
    state: JobState
    progress: int | None = Field(default=None, ge=0, le=100)
    created_at: float
    expires_at: float


class DurableJob(Record):
    job_id: str
    run_id: str
    owner: Principal
    request: GenerationRequestEnvelope = Field(repr=False)
    request_fingerprint: str
    state: JobState = JobState.ACCEPTED
    version: int = 1
    attempt_count: int = 0
    attempt_limit: int = Field(default=3, ge=1, le=3)
    dispatch_limit: int = Field(default=12, ge=1, le=12)
    fencing_token: int = 0
    lease: AttemptLease | None = None
    cancellation_requested: bool = False
    created_at: float
    deadline_at: float
    expires_at: float
    event_expires_at: float
    event_cursor: int = 0
    first_event_id: int = 1
    dispatch: DispatchIntent
    result: ArtifactRef | None = None
    # Query projection, absent for terminal jobs. Never an execution authority.
    next_action_at: float | None


class Acceptance(Record):
    job: DurableJob
    created: bool


class EventPage(Record):
    events: tuple[JobEvent, ...]
    next_cursor: int
    truncated: bool
    latest_cursor: int


class Reconciliation(Record):
    inspected: int
    changed: tuple[str, ...]


class JobError(Exception):
    """Sanitized service failure, suitable for a future structured API boundary."""

    def __init__(self, code: str, status: int = 409):
        self.code = code
        self.status = status
        super().__init__(code)
