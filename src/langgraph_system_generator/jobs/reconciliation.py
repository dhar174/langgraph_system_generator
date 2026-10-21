"""Bounded Scheduler-driven recovery, independent of browser/API activity."""

import time
from collections.abc import Callable

from .models import JobError
from .protocols import JobDispatcher, JobStore


class Reconciler:
    def __init__(
        self,
        store: JobStore,
        dispatcher: JobDispatcher,
        *,
        clock: Callable[[], float] = time.monotonic
    ):
        self.store, self.dispatcher, self.clock = store, dispatcher, clock

    def reconcile_once(
        self, *, page_size: int = 10, pages: int = 5, seconds: int = 30
    ) -> dict[str, int]:
        if not 1 <= page_size <= 100 or not 1 <= pages <= 10 or not 1 <= seconds <= 60:
            raise JobError("reconciliation_limits_invalid", 400)
        end = self.clock() + seconds
        counts = {"inspected": 0, "changed": 0, "dispatched": 0, "deferred": 0}
        for _ in range(pages):
            if self.clock() >= end:
                break
            # Drain due pages: mutations move them out of the query. CAS handles
            # other reconcilers seeing the same page. No cross-service transaction.
            recovered = self.store.reconcile(limit=page_size)
            counts["inspected"] += recovered.inspected
            counts["changed"] += len(recovered.changed)
            intents = self.store.pending_dispatch(limit=page_size)
            for intent in intents:
                if self.clock() >= end:
                    return counts
                try:
                    job = self.store.inspect_attempt(intent.job_id)
                    if job.dispatch != intent:
                        continue
                    task_ref = self.dispatcher.dispatch(intent)
                    self.store.mark_dispatched(
                        job.job_id,
                        job.version,
                        job.fencing_token,
                        intent.intent_id,
                        task_ref,
                    )
                    counts["dispatched"] += 1
                except JobError as error:
                    if error.status == 503:
                        # Never mark a reserved name as pending work. Rotate with
                        # finite exponential backoff, retaining one logical job.
                        current = self.store.inspect_attempt(intent.job_id)
                        try:
                            self.store.reschedule_dispatch(
                                current.job_id,
                                current.version,
                                current.fencing_token,
                                intent.intent_id,
                                min(60, 5 * 2 ** min(intent.generation - 1, 4)),
                            )
                            counts["deferred"] += 1
                        except JobError as conflict:
                            if conflict.status != 409:
                                raise
                    elif error.status not in (404, 409):
                        raise
            if not intents and not recovered.inspected:
                break
        return counts
