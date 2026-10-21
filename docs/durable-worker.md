# Private durable execution: B2 operations runbook

Part of #380; relates to #378; preserves #379 and #385. B1 is accepted through
PR #392, merge `305274f7eca82655e3556b2df50f0406f2d7905c`. B2 adds executable
dispatch, worker, publication and reconciliation adapters. **Public durable
admission remains disabled.** This document and the configuration proposals do
not provision resources, grant IAM, change production variables or deploy.

## Service and identity boundary

Run the worker as a separate private Cloud Run service using
`langgraph_system_generator.api.worker_server:app`. The public IAP application
does not mount its routes. Use one Uvicorn process, a Cloud Run request timeout
of **330 seconds**, concurrency 2, and application generation capacity 1 per
instance. Concurrency leaves room for duplicate deliveries and reconciliation;
instance/queue quotas must still be reviewed before activation. The public API's
existing deployment workflow is not the worker deployment mechanism.

Cloud Tasks creates its OIDC token in `Authorization: Bearer ...` with the exact
configured worker audience. Cloud Run IAM verifies the caller at the platform;
the application independently uses `google-auth` signature/issuer/audience/time
verification, verified service-account email, and route-specific account
allowlists through B1 `WorkerJobService.from_authorization`. Do not forward an
IAP user token. Do not use `X-Serverless-Authorization`: Cloud Run strips that
header's token signature. A stripped or malformed token is rejected rather than
reconstructed from claims. `X-CloudTasks-*` headers grant no authority. The local
HTTP tests verify Authorization forwarding to the real verifier with offline
signing keys; deployed proxy behavior and IAM require staging verification.

The worker audience must match its configured HTTPS `*.run.app` service URL.
Task URLs always end in `/internal/execute`. Queue and task service account must
belong to the same project. Tasks and Scheduler must use different service
accounts; identical accounts fail configuration with HTTP 503 before the store
is constructed. Neither URL, queue, service account, bucket, output
root, owner nor credentials can be selected by the task payload. Its only fields
are `schema_version=1`, opaque `job_id` and `dispatch_generation` (1–12).

Proposed least-privilege bindings for owner review:

| Identity | Necessary authority and boundary |
| --- | --- |
| Cloud Tasks caller SA | `roles/run.invoker` on this worker service only; allowlisted only for `/internal/execute` |
| Scheduler caller SA | `roles/run.invoker` on this worker service only; allowlisted only for `/internal/reconcile` |
| Worker runtime SA | Firestore access for the configured database; `roles/cloudtasks.enqueuer` on the one queue and `iam.serviceAccounts.actAs` on the Tasks caller SA; private bucket object create/read; provider-specific secret access |
| Cloud Tasks service agent | Owner must verify its documented token-minting permissions; do not create or replace credentials here |
| Retention operator | Separate reviewed private object list/delete and store-read permissions for explicit orphan cleanup; no public cleanup route |

Use uniform bucket-level access and public access prevention. No `allUsers` or
`allAuthenticatedUsers` grants, public object ACLs, signed URLs or client-selected
bucket lookup are part of this adapter. The worker runtime need not have object
delete permission. Private bucket/IAM configuration is an activation gate;
offline fakes cannot establish actual object privacy.

## Reviewable configuration

`LNF_WORKER_OUTPUT_ROOT` is resolved and must lie within both the current working
directory and the generator's resolved output base (`LNF_OUTPUT_BASE`, or the
existing `BASE_OUTPUT_DIR` test override). Escaping `..` components and roots
outside a narrower configured base fail with HTTP 503 `worker_output_root_invalid`
before any job is claimed or directory created. Accepted roots are passed to the
worker and artifact store in canonical form. CLI/package path behavior is unchanged.

Install `.[api,full,gcp]` in the worker image. Google SDKs and credentials remain
lazy: importing core, public API, worker app or adapters initializes no Google
client and discovers no ADC. An explicitly requested Firestore backend never
falls back to memory. Health exposes only liveness and disabled public admission.

The worker process must receive these administrator settings; examples in
`.env.example` remain commented out:

| Setting | Required relationship |
| --- | --- |
| `LNF_JOB_BACKEND` | `firestore` for the separate worker; public API stays fail-closed for durable admission |
| `LNF_JOB_GCP_PROJECT`, `LNF_JOB_FIRESTORE_DATABASE` | Explicit B1 project/database and deployed B1 indexes |
| `LNF_JOB_IDEMPOTENCY_SECRET` | Stable existing secret binding, at least 32 bytes; never put a value in YAML/queue |
| `LNF_JOB_TASK_QUEUE` | Full `projects/PROJECT/locations/REGION/queues/QUEUE` resource |
| `LNF_WORKER_URL`, `LNF_WORKER_AUDIENCE` | Same HTTPS Cloud Run service origin, no trailing slash on URL |
| `LNF_TASK_SERVICE_ACCOUNT` | Same-project task caller SA email |
| `LNF_SCHEDULER_SERVICE_ACCOUNT` | Distinct Scheduler caller SA email |
| `LNF_WORKER_OUTPUT_ROOT` | Dedicated `./output/worker` namespace, within the generator's trusted `LNF_OUTPUT_BASE`; reject symlink/junction ancestors |
| `LNF_OUTPUT_BASE` | `.` in the worker proposal; production root stays under its current working directory |
| `LNF_JOB_ARTIFACT_BUCKET` | Existing private bucket name; syntax validated before claiming/generating |
| `LNF_JOB_PROVIDER_REFS` | B1 approved symbolic references, e.g. `["openai-v1"]` |
| `LNF_JOB_PROVIDER_BINDINGS` | Nonsecret map of symbolic refs to current #379 provider IDs, e.g. `{"openai-v1":"openai"}` |
| `LNF_TRUSTED_LLM_ENDPOINTS` | Existing #379 exact endpoint registry for custom provider IDs; use only dedicated credential env bindings |

Each attempt resolves the symbolic provider and authorizes its current endpoint
before generation, then verifies the same nonsecret binding before upload.
Removed references or changed bindings fail permanently. Credentials/transports
remain runtime-only; `generate_artifacts(endpoint_policy="hosted")` retains its
existing `llm_transport_scope` cleanup and zero SDK retries. Cloud Run environment
is revision-scoped: changing a future revision does not mutate an already running
process's environment. Revoke/drain obsolete revisions before relaxing activation
gates; this is not a centralized live policy service.

Review [worker service proposal](config/durable-worker.service.yaml) and
[queue retry proposal](config/durable-worker.queue.json) before applying anything.
Read back actual service timeout, image, audiences, IAM, queue overrides/routing,
rate limits, retry settings, bucket policy and database indexes in staging. An
application dataclass is not evidence of deployed platform settings.

## Deadlines, delivery and recovery

Generation retains the existing 240-second deadline. Publication gets a
45-second phase allowance; the attempt ceiling is 300 seconds, worker HTTP
timeout 330 seconds, and task dispatch deadline 360 seconds. All remain below
Cloud Tasks' 1,800-second HTTP maximum. The child process is killed and reaped
before capacity is released. The generation/phase limits include imports and
output work. At most nine files (including the final manifest) use three storage
RPCs apiece with a one-second per-RPC timeout and no SDK retries: 27 seconds of
configured RPC budget fits within publication, leaving computation margin.
Size limits are 8 MiB/file (single multipart upload), 64 MiB/set (including final manifest), nine allowed
artifact names, and 32 ZIP entries with bounded expanded size. Slow uploads fail
and retry within these limits; throughput is a staging gate. Hard process
termination may interrupt transport cleanup, and cannot undo a provider call.

The parent renews B1's fenced lease every 15 seconds (maximum lease 240 seconds),
coalescing progress into one integer slot and writing at most one progress event
per heartbeat. No arbitrary log/prompt buffers or per-log background tasks exist.
Heartbeat failure stops/reaps the child and returns retryable failure; the store
and scheduled reconciler retain authority. Expired leases and cancellation reject
publication even if an old worker resumes. An outage can prevent settlement
before the HTTP deadline; no response/503 leaves delivery and lease recovery
available. Infrastructure shutdown is not owner cancellation.

B1 persists at most three generation attempts and a 900-second overall deadline.
B2 persists an independent limit of twelve dispatch generations, including
generations lost before claim. Relinquishing consumes a generation attempt;
queue delivery retries do not. Retry backoff starts at five seconds and caps at
60 seconds. The queue proposal uses finite delivery attempts and a finite retry
duration; Cloud Tasks requires both limits to be exhausted before removal.
Generator internal QA/repair attempts stay separately bounded by its own policy.

Admission commits a dispatch intent with the job. Reconciliation enqueues it
outside Firestore transactions using SHA256 of schema/job/dispatch generation.
Ambiguous CreateTask and ALREADY_EXISTS trigger GetTask for that exact name.
Reserved-name tombstones are not proof of pending work: absence rotates a durable
dispatch generation with backoff. A DB mark failure is safe to retry against the
same task name. A dispatched job unclaimed for 60 seconds is eligible for a new
generation through the store's reconciliation transition. Old deliveries then
return stale without adopting the newer intent. There is no second logical job.

Invoke `POST /internal/reconcile` with Scheduler OIDC, exact worker audience and
the separate Scheduler caller SA, proposed once per minute. Do not disable IAM or
send a user JWT. One request runs the configured reconciler in a supervised
subprocess with a 60-second ceiling. `reconcile_once` defaults to five pages of
ten due jobs/intents and a 30-second cooperative scan budget between bounded
RPCs; the process ceiling also bounds stuck SDK transactions. Mutations move
processed records out of due queries, so successive pages/passes progress without
an in-memory cursor. CAS handles concurrent reconcilers. It recovers expired
leases, missing dispatch, lost acknowledgments, queue exhaustion, attempts/deadline
exhaustion and eligible retries without API/browser traffic. Deployment must
monitor backlog; bounded passes are not a guarantee of zero scheduling latency.

| HTTP outcome | Durable state and Cloud Tasks behavior |
| --- | --- |
| 200 completed or terminal duplicate | Winning pointer/terminal state already committed; acknowledge/delete delivery; no regeneration |
| 200 settled after infrastructure/provider failure | B1 retry intent or exhausted terminal failure committed before acknowledgment; Scheduler owns next dispatch |
| 204 stale generation | A newer durable generation exists; acknowledge obsolete delivery without claiming it |
| 204 unavailable job | Job absent or beyond access retention; no authority to execute; acknowledge |
| 503 active lease / capacity busy / CAS conflict | No acknowledgment; queue retries; Scheduler can recover later lease loss |
| 503 heartbeat/store/settlement/auth-key outage | No false completion; queue retries; reconciliation remains necessary |
| 401 or 403 | Missing/invalid OIDC or wrong route caller; reject; queue retries finitely; operator fixes configuration |
| 413 or 422 | Oversized/malformed reference payload; reject; no generation; finite queue retries and operational alert |
| No response, killed request or process loss | Queue retries; store lease/deadline/reconciliation decides authority |

Permanent validation, endpoint/policy and blocking QA failures become fenced
FAILED before acknowledgment. Transient infrastructure, provider, storage and
attempt-deadline failures create bounded retry intent when authority is still
available. Cancellation is persisted and terminal; deleting a queued task is
not cancellation of a running provider request.

## Publication and cleanup boundary

All objects use private `runs/RUN/attempt-FENCE/NAME` names with create-only
generation-match preconditions. Every upload is read back at its exact generation
and checked for size, content type and SHA256. The final manifest preserves
generator QA scope, graph/tool contracts, actual serialized nbformat-v4 cell
count, ZIP members and actual sizes. Windows newline differences do not fabricate
identical ZIP/standalone hashes. Public-facing manifest paths become stable
job/run/artifact references, never temporary worker paths. Per-object generations,
sizes, checksums and content types are in the private final manifest. Its own
finalized receipt is B1's external `ArtifactRef`; no self-hash is fabricated.

Only after the complete object set and final manifest verify does the parent
commit B1 completion, result pointer and one terminal event in its fenced
Firestore transaction. Storage/Firestore have no shared transaction. The pointer
is the application publication boundary. Partial sets and crash-left objects
stay private; an old fence cannot publish them. Crash after completion but before
HTTP acknowledgment returns the same terminal result on redelivery.

`GCSArtifactStore.delete(ref)` deliberately rejects context-free deletion.
`cleanup_orphan(store, job_id, fence, now=...)` checks the current authoritative
job, irrevocably lost attempt authority, winning-prefix exclusion, and a retention
floor of one day after the overall job deadline. It lists at most ten objects,
validates exact ownership/names, and deletes only observed object generations.
It is an internal operator primitive, not a public route or scheduled global
cleanup job. B3 owns inventory, lifecycle/backstop policies, metadata-expired jobs,
authorized public downloads/events, quotas and rollout. Never apply an age-only
bucket deletion rule that can remove retained winning results.

## Qualification and remaining gates

Normal tests use fake clocks/barriers, protocol-shaped SDK clients, real Google
signature verification with offline keys and subprocess deadline/reaping checks.
They are credential-free. The optional Firestore emulator module adds real
separate-process lease recovery against local `demo-lnf-b1` with anonymous
credentials. There is no official Cloud Tasks emulator claim here.

Emulator, authenticated Cloud Tasks/Cloud Run delivery, actual IAM, private bucket
enforcement, throughput/deadline contention, production indexes and deployment
read-back are separate unperformed staging gates unless accompanied by a receipt.
Missing cloud authentication does not prevent offline implementation. No generated
user notebook is executed as a new hosting evaluation feature. The guarantee is
one authoritative result; crashes can repeat LLM calls/external side effects and
incur cost. There is no exactly-once execution or checkpoint resume claim.

Official references rechecked for B2:
[Cloud Tasks HTTP targets](https://docs.cloud.google.com/tasks/docs/creating-http-target-tasks),
[delivery/deduplication](https://docs.cloud.google.com/tasks/docs/dual-overview),
[finite RetryConfig](https://docs.cloud.google.com/tasks/docs/reference/rest/v2/RetryConfig),
[Cloud Run authentication/header forwarding](https://docs.cloud.google.com/run/docs/authenticating/service-to-service),
[google-auth verification](https://google-auth.readthedocs.io/en/latest/reference/google.oauth2.id_token.html),
[GCS generation preconditions](https://docs.cloud.google.com/storage/docs/request-preconditions).
