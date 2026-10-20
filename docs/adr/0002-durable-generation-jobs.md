---
title: Durable generation jobs v1
status: Proposed foundation; public durable admission disabled
date: 2026-10-20
---

## Decision and boundary

Part of #380; relates to #378; preserves #379 and #385. Base reviewed:
`60e205b7e9d80c31a57de5601d8ab4789045823c`. No intervening main commits or
overlapping implementation PRs were found on 2026-10-20. Phase A remains the
default. B1 supplies contracts, transactional control state and verified identity;
B2 adds Cloud Tasks dispatch and an IAM-protected Cloud Run HTTP worker; B3 adds
private Cloud Storage publication and authorized public durable routes. Nothing
in this ADR provisions infrastructure, changes IAM or enables admission.

The worker generates within one bounded HTTP request. Lost attempts may restart
generation. Fencing guarantees at most one authoritative result, not exactly-once
LLM calls, billing or external side effects. Fine-grained graph checkpoint recovery
and arbitrary-duration processing are outside v1. GeneratorState and the existing
generation pipeline remain authoritative; generated notebooks are never executed
by the hosting foundation.

## Identity and deployment

Use separate API, dispatcher/worker and reconciliation service accounts with
least-privilege IAM reviewed by the owner. API users supply signed IAP assertions;
ownership is the immutable `(issuer, subject)` pair. Email is display-only. Direct
Cloud Run IAP audience is exactly
`/projects/PROJECT_NUMBER/locations/REGION/services/SERVICE_NAME`, configured from
the actual API service. It is neither the load-balancer backend-service audience
nor the worker's OIDC audience (its Cloud Run URL or separately configured custom
audience). Internal service identity has a separate type. Never queue a user JWT.
Server SDK IAM bypasses browser Security Rules: application transactions enforce
ownership. Phase A single-operator access never grants durable ownership.

## Consistency and transitions

Every mutation checks version and fence in a transaction. Claim increments fence
and attempt count. Lease expiry immediately removes authority, including before a
replacement claims. Transaction callbacks contain only reads, pure transitions
and writes; no queue, LLM or upload side effects. Transaction retries may rerun
callbacks. A fresh clock is read inside each callback.

| From | Operation | To / ordering |
| --- | --- | --- |
| absent | accept owner/key/payload | accepted plus idempotency and dispatch intent atomically |
| accepted | claim | running, new fence and bounded lease |
| running | renew/event | running only with current, unexpired authority |
| running | relinquish / expired-lease reconcile | accepted with new dispatch generation and revoked authority, or failed at attempt cap |
| accepted/running | owner cancellation | cancelled immediately; first committed terminal transaction wins |
| running | finalize | completed/failed; requires live lease, version and fence |
| active past overall deadline | reconcile | expired |
| terminal | any execution mutation | rejected; only separate retention/deletion metadata may change |

Cancellation is a durable intent and immediate authoritative terminal decision.
It does not promise to stop an in-flight provider request. Completion committed
first remains completed; cancellation committed first fences completion out.
Disconnecting a browser is not cancellation. Every event gets a monotonically
increasing job cursor across all attempts. Replay pruning never deletes the
terminal/result identity in the job document.

## Deadlines, retry and retention

Initial budgets: overall job 900 seconds, attempt lease at most 240 seconds,
three attempts, request content at most 64 KiB. B2 must fit generation (for
example 180 seconds), upload and finalize within the live lease and worker request
timeout, with the Cloud Tasks dispatch deadline longer than the worker budget
and no longer than its HTTP limit of 30 minutes. Queue retries deliver wakeups;
only store claim/reconciliation grants attempt authority. Reconciliation is a
bounded authenticated operation, proposed Cloud Scheduler OIDC invocation every
minute. Queue delivery, database transactions and generation retries are distinct.

Idempotency lasts exactly 24 hours from acceptance, independently of queue task
deduplication. Owner/key identifiers use HMAC-SHA256 with a stable deployment
secret; never log raw keys or use them in task names. Canonical request hashes
include schema/generator version and approved provider configuration reference.
Request content is confidential: no prompt bodies in events/logs or indexes and
no bearer tokens, endpoints, assertions, clients or provider secrets in records.

Jobs expire at access after seven days; event replay expires after one day and
is also bounded by 1,000 small records. Result references survive replay pruning.
Physical Firestore TTL is asynchronous and not authorization. Explicit cleanup
must delete event subcollections and private objects; deleting parent documents
does not delete subcollections. B3 must give objects independent lifecycle rules,
generation-match deletes and inventory/orphan reconciliation. B1 never uploads.

## Acceptance by phase

| Phase | Required evidence |
| --- | --- |
| B1 offline | shared store contracts, Firestore transaction adapter tests, injected signed identity tests, lazy imports, Phase A/security regressions |
| B1 emulator | opt-in real Firestore acceptance, contention, replay, fences and restart persistence; separately recorded |
| B2 staging | authenticated dispatch, retry/worker loss, bounded request and reconciliation, no user JWT forwarding |
| B3 staging | finalized immutable object generations, cross-instance authorized replay/download, TTL and orphan cleanup |
| production | owner-reviewed identity/IAM, quotas, costs, retention, staged receipts and explicit activation |

Mock storage is not production qualification. No emulator, staging or production
receipt is implied by offline tests. Current hosted Python workflow is active but
main run `39483297666` ended in startup_failure without jobs; do not enable,
rerun or wait indefinitely for owner-disabled execution.

## Official documentation checked 2026-10-20

- [IAP signed headers](https://docs.cloud.google.com/iap/docs/signed-headers-howto):
  ES256, trusted IAP keys, issuer, exact audience, iat/exp, bounded key caching.
- [Direct Cloud Run IAP](https://docs.cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run):
  API identity and ingress boundary.
- [Firestore transactions](https://docs.cloud.google.com/firestore/native/docs/manage-data/transactions):
  atomic operations, read-before-write and retried callbacks.
- [Firestore TTL](https://docs.cloud.google.com/firestore/native/docs/ttl):
  asynchronous physical deletion and subcollection cleanup.
- [Cloud Tasks HTTP targets](https://docs.cloud.google.com/tasks/docs/creating-http-target-tasks):
  OIDC worker invocation and dispatch deadlines.
- [Scheduler authentication](https://docs.cloud.google.com/scheduler/docs/http-target-auth):
  proposed authenticated reconciliation trigger.

## Frozen ports

All records carry `schema_version=1`; unknown fields are rejected. Request
fingerprints use UTF-8 sorted-key compact JSON including defaults, without Unicode
normalization. Owner display email does not participate in ownership or hashing.
Public immutable Pydantic records are in `jobs/models.py`. Protocols are synchronous:
future async routes must offload SDK work from the event loop. Worker ports are
internal service capabilities; never expose them through owner HTTP routes.
`InternalCallerVerifier.verify(authorization: str) -> ServiceIdentity` freezes the
B2 OIDC verification boundary. `WorkerJobService` requires that separate identity
type and checks the configured exact audience and service-account allowlist before
internal inspection/claim/renew/event/finalize/reconciliation. B1 ships no unsigned
service verifier. This class checks authorization of an already verified identity;
its constructor does not authenticate string fields. B2 routes must use
`WorkerJobService.from_authorization(...)` with a real `InternalCallerVerifier`;
direct construction is for trusted in-process injection only. Claims also require
the current dispatch intent ID; old task
deliveries cannot adopt a newer dispatch generation merely by refetching a job.

The exact `JobStore` signatures (types imported from `jobs.models`) are:

```python
accept(principal: Principal, key: str, request: GenerationRequestEnvelope) -> Acceptance
get(principal: Principal, job_id: str) -> DurableJob
inspect_attempt(job_id: str) -> DurableJob  # authenticated internal worker only
claim(job_id: str, version: int, fence: int, worker_id: str, intent_id: str) -> DurableJob
renew(job_id: str, version: int, fence: int, worker_id: str) -> DurableJob
relinquish(job_id: str, version: int, fence: int, worker_id: str) -> DurableJob
append_event(job_id: str, version: int, fence: int, worker_id: str, progress: int) -> DurableJob
replay(principal: Principal, job_id: str, after: int = 0, limit: int = 100) -> EventPage
cancel(principal: Principal, job_id: str, version: int, fence: int) -> DurableJob
finalize(job_id: str, version: int, fence: int, worker_id: str, state: JobState, result: ArtifactRef | None = None) -> DurableJob
mark_dispatched(job_id: str, version: int, fence: int, intent_id: str, task_ref: str) -> DurableJob
pending_dispatch(limit: int = 100) -> tuple[DispatchIntent, ...]
reconcile(limit: int = 100) -> Reconciliation
```

`Acceptance` includes the job and `created`; replay returns events, next/latest
cursors and truncation. Future replay cursors return `job_cursor_future` (400),
never a regressed cursor. Every worker call returns the new version for its next
mutation. Fencing is not a credential: B2 must authenticate the service before
allowing worker ports. Owner cancellation also rejects an expired lease snapshot;
reconciliation/refetch supplies current authority before a later cancellation.
Missing and other-owner jobs both return sanitized `job_unavailable` (404).
Conflicts return 409; bad fields/pages return 400; configuration/storage failures
return 503. Invalid durable configuration never selects memory.

```python
# JobDispatcher (B2)
dispatch(intent: DispatchIntent) -> str
# ArtifactStore (B3)
publish_manifest(job: DurableJob, files: tuple[Path, ...], fence: int) -> ArtifactRef
read_manifest(ref: ArtifactRef) -> bytes
delete(ref: ArtifactRef) -> None
```

B2 must use deterministic `intent_id` task names, enqueue outside transactions,
then CAS `mark_dispatched`; ambiguous acknowledgments retry the same intent. Claim
also consumes the intent, so a late dispatcher acknowledgment cannot undo a claim.
An acknowledged task is still subject to the overall deadline. B2 must qualify
delivery retries and may add a bounded redispatch policy for acknowledged tasks
that never claim. B1 reconciliation requeues lost running attempts and expires
accepted jobs at the overall deadline; it does not create Cloud Tasks.

B3 uploads attempt-specific private objects, then supplies one immutable manifest
reference (bucket, object name, exact generation, SHA256, byte length) to fenced
finalization. The result must belong to the job's run namespace. Failed finalization
leaves an orphan for bounded cleanup. A store transaction cannot prevent an old
worker from uploading an orphan; it prevents publishing that orphan as the result.
Never issue public/signed object URLs from stored state. Owner-scoped lookup and
access-time expiry must precede artifact reads at the B3 application boundary.

## Firestore schema and indexes

Use a dedicated Firestore Native database. Documents:

| Path | Contents and atomic ownership |
| --- | --- |
| `jobs/{opaque_job_id}` | complete DurableJob v1, confidential envelope, immutable owner, result identity; one bounded document |
| `idempotency/{HMAC_SHA256(owner_tuple_and_key)}` | original job ID, canonical fingerprint, 24-hour expiry |
| `dispatch/{job_id}` | current DispatchIntent, `due_at` numeric query projection, job expiry |
| `jobs/{job_id}/events/{cursor_20_digits}` | one bounded JobEvent, cursor monotonically allocated by job transaction |

All retained records receive a timestamp `delete_after` for TTL; numeric epoch
`expires_at` is the access contract. Admission writes all four documents atomically.
Each mutation atomically replaces the job/dispatch projections and, when applicable,
adds one event and deletes the oldest event. At most 1,000 event records are retained;
each has only fixed metadata plus integer progress (no arbitrary log strings).
The default encoded event payload bound is under 512 KiB per job. Job envelopes
are capped at 64 KiB, keeping documents below Firestore's document size limit.
No unbounded arrays, event histories or manifests live in the job document.

Reads by job, idempotency and event ID use document paths. Pending dispatch uses
`dispatch.due_at <= now`, ordered by `due_at`, limit 1–100. Reconciliation uses
`jobs.next_action_at <= now`, ordered by that field, limit 1–100. These require the
default ascending single-field indexes, no composite indexes. Inactive projections
are null and excluded by the numeric range queries. Ties use Firestore document
ordering; no same-timestamp chronology is inferred. A subsequent pass revisits
remaining due records. No user/owner listing or request-content queries exist.

Reviewable [index and TTL proposal](../config/firestore-jobs.indexes.json) exempts
request/owner/result maps and TTL timestamps from indexing. It is not applied.
Physical deletion of parent jobs must be accompanied by explicit event cleanup;
event-group TTL is a second backstop. Never configure a job-only TTL policy and
assume child records disappear. B3 must implement cleanup inventory/cursors before
activation, including objects after job removal.

Transactions use the SDK's five-attempt retry bound; exhausted contention and
unavailable clients produce `job_backend_unavailable` (503). Callers may retry
idempotent acceptance; worker calls refetch current authority after conflicts.
SDK reads/queries have ten-second RPC timeouts; SDK transaction commit/retry budgets
remain SDK defaults and must fit the B2 HTTP budget. Per-job writes serialize on
the job document: B2 must throttle progress (proposed at most one update/second),
queue concurrency and per-owner admission. Retained events, request size, page
size, attempts and attempt lease are bounded in B1; global/per-owner rate and cost
quotas remain an activation gate. B1 accepts no public requests for durable work.

Lease decisions use an injected UTC epoch clock sampled inside each transaction.
Production hosts must have synchronized clocks. A worker with excessive positive
skew may take over early; fencing still rejects the former worker after takeover,
but duplicate generation cost is possible. B2 must monitor clock skew and reserve
deadline margin. No wall clock can guarantee exactly-once external effects.

## Configuration and offline runbook

| Setting | Contract |
| --- | --- |
| `LNF_JOB_BACKEND` | `ephemeral` default or `firestore`; unknown values fail closed |
| `LNF_JOB_GCP_PROJECT` | explicit project ID required when selecting Firestore |
| `LNF_JOB_FIRESTORE_DATABASE` | explicit named database or `(default)` default |
| `LNF_JOB_PROVIDER_REFS` | JSON array of 1–32 approved symbolic provider/configuration references, default `["openai-v1"]` |
| `LNF_JOB_IDEMPOTENCY_SECRET` | stable deployment secret, at least 32 UTF-8 bytes; mount via owner-reviewed secret binding, never log |
| IAP audience | explicit `IAPVerifier(audience)` injection; required direct Cloud Run shape, no discovery |
| User auth and async capability | existing Phase A controls remain independent; B1 adds no durable public auth bypass |

`select_job_store()` validates configuration and returns a lazy adapter. New
admission rejects unapproved provider references and generator versions different
from the server package version. Existing same-payload idempotent replay still
returns its original job after a provider catalog/version change. B2 must bind
approved references to reviewed provider configurations before execution and fill
the envelope's generator version from the running package. The first SDK
operation reports missing optional packages/ADC/network as structured 503, with no
ephemeral fallback. Importing core, API or the selected adapter does not load Google
clients or discover credentials. `pip install '.[gcp]'` is optional. No queue/GCS
package or client is initialized in B1.

The public API always rejects a non-ephemeral backend in B1, including hosted
single-operator mode. `/health` remains reachable and reports generation disabled
plus a sanitized `job_backend_error`. No service variables or workflows are changed.
There is no unsigned development identity path; offline callers inject Principals
and IAP trusted keys in tests only.

Run the three new unit modules plus Phase A/security regressions first. The opt-in
emulator suite requires a separately started **local** Firestore emulator:

```powershell
$env:FIRESTORE_EMULATOR_HOST = '127.0.0.1:8080'
$env:LNF_TEST_FIRESTORE_EMULATOR = '1'
python -m pytest tests/integration/test_firestore_job_emulator.py -q
```

Use only the `demo-lnf-b1` emulator project and anonymous credentials. No ADC or
billable project is needed. Remove these variables afterward. An emulator receipt
does not verify IAM/IAP, production indexes/TTL timing or Cloud Tasks behavior.
Optional staging qualification must separately read back actual API/worker audience,
verify invalid assertions and other-owner reads, test private Firestore IAM, SDK
contention/timeouts and TTL/subcollection cleanup, then B2/B3 acceptance gates.
