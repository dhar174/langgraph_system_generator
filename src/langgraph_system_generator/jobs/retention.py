"""Bounded authenticated maintenance, with parent inventory retained until cleanup."""

import time
from collections.abc import Callable

from .gcs_artifacts import GCSArtifactStore
from .models import JobError
from .protocols import JobStore


class RetentionCleaner:
    def __init__(
        self,
        store: JobStore,
        artifacts: GCSArtifactStore,
        *,
        clock: Callable[[], float] = time.time
    ):
        self.store, self.artifacts, self.clock = store, artifacts, clock

    def sweep(self, limit: int = 5) -> dict[str, int]:
        if not 1 <= limit <= 10:
            raise JobError("cleanup_limit_invalid", 400)
        counts = {"cleanup_inspected": 0, "cleanup_completed": 0, "cleanup_deferred": 0}
        for job in self.store.cleanup_candidates(limit):
            counts["cleanup_inspected"] += 1
            try:
                # Parent deletion requires an empty object sweep. Before expiry,
                # the winning generation remains private and downloadable.
                sweep_now = self.clock()
                complete = self.artifacts.cleanup_run(job, now=sweep_now, limit=32)
                if complete:
                    done = self.store.cleanup_metadata(
                        job.job_id,
                        objects_deleted=sweep_now >= job.expires_at,
                        limit=100,
                    )
                    counts["cleanup_completed"] += int(done)
            except JobError:
                # Retain inventory after failure, never pretend bytes were deleted.
                counts["cleanup_deferred"] += 1
        counts["idempotency_deleted"] = self.store.cleanup_idempotency(limit=100)
        return counts
