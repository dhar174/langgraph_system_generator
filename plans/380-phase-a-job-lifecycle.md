# Issue #380 Phase A: ephemeral API lifecycle

Base: `11551ab9e36cca3f1948db486b4267ee7895dc8c` (`origin/main`, fetched
2026-10-20). Issue #380 is open. Open PRs #373, #372, #367, #316 and #313
do not implement this lifecycle. Historical seven-phase plans are not authority.

## Decisions and implementation sequence

1. Retain the process-local backend. Own each accepted asynchronous task, make
   terminal updates idempotent, handle cancellation before and during execution,
   and bound graceful shutdown. Preserve atomic shared generation admission.
2. Replace age-based active-job eviction with bounded terminal retention and one
   cancellable maintenance loop. Bound tracked jobs, event count and event bytes.
   Apply a cooperative generation deadline; synchronous work cannot be forcibly
   preempted by an asyncio timer.
3. Replay retained SSE events by actual ID, identify history gaps, handle invalid
   and future cursors deterministically, preserve terminal results and independent
   subscribers. Transport disconnect does not imply generation failure.
4. Allocate exclusive, opaque API run directories under the validated requested
   parent for both routes. Keep CLI/package explicit output paths unchanged.
   Register only known successful generated artifacts and use run-scoped download
   references. Revalidate paths, file reality and symlinks on download.
5. Support local trusted-operator asynchronous use. On Cloud Run, fail closed
   unless the operator explicitly acknowledges the single-operator access model.
   Disable hosted background admission by default; the browser uses request-bound
   `/generate` when asynchronous execution is unavailable. Do not trust unsigned
   identity headers or claim per-principal isolation.
6. Keep request-based CPU and zero minimum instances in the proposed workflow.
   Document an optional owner-reviewed instance-based CPU configuration for
   ephemeral background use, including cost and restart limitations. Do not deploy.
7. Add deterministic offline lifecycle, replay, isolation, artifact-access,
   hosted-policy and browser regressions. Run focused, unit, pattern and complete
   suites, static checks, exact conflict scan and serialized-artifact smoke.
8. Obtain separate read-only lifecycle, artifact security and API/SSE reviews;
   resolve blocking findings, publish a focused PR with `Part of #380` and leave
   it open for owner review.

## Verified infrastructure baseline

Read-only `gcloud run services describe` returned ready revision
`langgraph-system-generator-00022-c95`: CPU throttling true, concurrency 80,
request timeout 300 seconds, minimum instances 0, maximum instances 20,
session affinity true and memory 2Gi. These are observed settings, not inferred
from omitted workflow flags. No infrastructure changes were applied.

## Non-goals

No queue, distributed state, GCS, durable scheduling, identity platform,
cross-instance replay, generator/QA semantic changes, RAG precedence changes,
merge, production deployment or closure of #380. Phase B owns durable execution
and verified caller ownership across workers, events and artifacts.
