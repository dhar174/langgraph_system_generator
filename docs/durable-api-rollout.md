---
title: Durable API integration and gated rollout (B3)
description: Owner-scoped durable API contracts, qualification and rollout gates.
---

Part of #380; relates to #378; preserves #379 and #385. This is a reviewable
implementation and qualification recipe. It does not authorize resource creation,
IAM/IAP changes, secret creation, activation, deployment, or a production migration.
Keep #380 open for the owner's acceptance decision.

## Accepted starting point

The inspected starting point is `101f14fcf2ab009360a2562181521c6aeb531ea0`,
PR #393's B2 merge. B1 is PR #392, merge
`305274f7eca82655e3556b2df50f0406f2d7905c`, accepted head
`e988165aa2c4a2bc2a65db6a0163ecfbdf0c2c20`. B2's tested correction head is
`fccdee3e6283255f8d3b69a6e783f05775eaaa2d`. Phase A is PR #385, merge
`60e205b7e9d80c31a57de5601d8ab4789045823c`, final head
`d1b825fcb8be7650e59abd91fe1399328afba83d`. All nine Phase A inline review
threads were resolved when inspected. Current source and receipts take priority
over earlier plans and historical CI counts.

## Runtime and access matrix

| Configuration | Submission | Readback / ownership | Storage |
| --- | --- | --- | --- |
| Default `LNF_JOB_BACKEND=ephemeral`, local | Existing sync/async semantics | Phase A process trust domain | Local namespaces |
| Hosted ephemeral, access unset/unsupported | Disabled | Disabled | No durability claim |
| Hosted ephemeral, `single-operator` | Sync; async only with existing explicit CPU opt-in | Shared trusted operator domain | Phase A retention |
| `firestore`, invalid config or identity mode | Unavailable; never local fallback | Fail closed | `/health` liveness stays 200, `/ready` 503 |
| `firestore`, `LNF_API_ACCESS_MODE=iap`, submissions false | Disabled | Signed IAP owner readback/cancel remains enabled | Firestore + private GCS |
| Same, `LNF_DURABLE_SUBMISSIONS_ENABLED=true` | `/generate-async` only | Stable verified issuer/subject owner | Atomic intent + committed object generations |

`POST /generate` returns `409 durable_requires_async` in durable mode before
normalization, credentials, reservations or generation. `/health` advertises
`sync_generation:false` and `generation_route:/generate-async`; the browser never
chooses synchronous generation for a durable service. `single-operator` is not a
durable ownership credential. Unsigned identity/email headers have no authority.

The public API verifies B1's signed IAP assertion and exact configured audience
on every submit, status, result, stream, cancel and artifact request. The trusted
server's dedicated Firestore database is the namespace; request fields cannot
select project/database, bucket, object path or owner. Other-owner and nonexistent
jobs both return the same `404 job_unavailable`, including downloads and SSE.
No admin bypass is provided. The worker reads persisted ownership and never
receives the browser token, prompt or ownership in a Tasks payload.

`/health` exposes non-sensitive configuration and Firestore connectivity; `/ready`
uses the same probe with HTTP 503 when unavailable. It verifies optional packages
and symbolic provider policy without reading model credentials. Artifact permission
and exact-generation integrity are explicitly `verified_on_access`; readiness is
not an IAM or object-existence qualification receipt. API readback needs the HMAC
secret and storage/database access, never model credentials.

## Submission, idempotency and supported options

Send one `Idempotency-Key` header per user action (1–256 UTF-8 bytes). Never put it
in URLs, logs, manifests or browser history. The store atomically persists the
verified owner, normalized generation request, owner/key HMAC, dispatch intent,
accepted event and run lookup. Identical retries return the original job with
`status:"started"`, `execution_status` and `idempotent_replay:true`. Conflicting
normalized requests return 409. The mapping lasts 24 hours; after that, the same
key can represent new work. The browser holds a key in memory for at most three
submission attempts, including a lost/truncated response body. Distinct form
submissions create new keys. Transport/result recovery never calls submit.

Dispatch is maintenance-owned: acceptance means the Firestore intent committed,
not that a queue call succeeded. The authenticated minute schedule dispatches it;
an outage leaves the intent recoverable. A missing/invalid configured dispatch
contract blocks activation. Provider registrations are reauthorized in the API
and worker under #379; no endpoint URL or provider key enters the durable request.

The existing prompt/dialog, model, architecture auto-selection, temperature,
token cap and supported export selections are persisted and passed into the same
generator. The durable envelope adds bounded options; unsupported formats fail
validation. Request bodies and canonical envelopes are capped at 64 KiB. Durable
API `output_dir` accepts the legacy labels `./output/api`, `output/api`, `api`,
`./output/web_generated`, `output/web_generated`, or empty string. It is a label,
not a remote filesystem selector; other paths return
`422 durable_output_dir_unsupported`. CLI/package explicit directories and the
generator's own output contract are unchanged. No user notebook is executed by
this hosting integration.

## Cross-instance SSE, recovery and cancellation

Every durable route reads the store. It does not consult `_active_jobs`,
`_owned_tasks` or `_api_runs`. SSE queries up to 100 retained events at a time,
polling every two seconds only while an HTTP subscription is active. Event IDs
remain monotonic. State events map to existing `progress`; compact successful
`complete` includes `/jobs/{job_id}/result`; terminal failure/cancel/expiry uses
`error`. Generator `log` events preserve their level and a redacted message capped
at 512 characters; SDK stderr and arbitrary details are excluded. The child and
worker coalesce logs into one bounded slot, and safe recovery notices also use
the existing `log` shape. History retains at most 1,000 events (including logs),
with each log message bounded to at most 2 KiB of UTF-8 before serialization.

Malformed cursors emit `events_truncated` and replay retained history. Future
cursors emit an honest gap marker and end. Pruned/expired history emits one gap
marker per subscription; final status can reconstruct one compact terminal event
only when its ID was not already acknowledged. The committed result remains
readable for seven days after acceptance even after the one-day event history
expires. Connections last at most 240 seconds; they reverify the original IAP
assertion and access-time job retention on each poll and before retained data
frames, so slow-consumer backpressure cannot extend access. Reconnect authenticates
again. Limits are 50 live streams and five per owner per API process, bounded by
the configured maximum API instances. Disconnect never cancels execution.

The browser displays the durable job ID and queue/running state. Only that
non-secret reference is kept in session storage. Inspect / reconnect recovers the
existing job after a reload, and Cancel job calls the additive idempotent
`POST /jobs/{job_id}/cancel`. The first terminal store transaction wins; cancelling
an already terminal job returns its current state. CAS conflicts retry boundedly;
a lost/expired lease is reconciled before retry. Cancellation revokes publication
authority; it cannot guarantee cancellation of an already submitted provider call.
Result GET retries remain bounded to three transient attempts (250/500 ms delays),
without regeneration or treating transport loss as a QA failure.

## Private committed downloads and resource budgets

Only a completed job's fenced winning `ArtifactRef` can select a manifest. Its
job/run/fence and each allowlisted object name, size, digest, content type and
generation are validated. Downloads use `if_generation_match`, CRC32C and the
recorded SHA-256. One object is spooled to a temporary file and fully verified
before sending success headers, then streamed in 64 KiB chunks. Access expiry is
rechecked before headers; an authorized bounded transfer can finish across expiry
so it never advertises a full body and silently stops short. Cancelled blocking
reads retain their read slot until the SDK thread settles and dispose late files.
Missing, corrupt
or deleted objects produce a structured sanitized failure. Every download uses
attachment disposition, `nosniff`, no-store and a sandbox CSP, including HTML.
There are no signed bearer URLs, public objects or arbitrary selectors.

Keep `DISABLE_GCS_PYTHON_CLIENT_OTEL_BUCKET_METADATA=true` on these services, as
in the configuration example. The installed Storage SDK can otherwise start a
background bucket-metadata request during an object download. Object-only API
permissions intentionally do not grant bucket metadata access. This setting
avoids that optional request without expanding IAM.

The uploaded manifest and result response share exactly the same manifest bytes
and download references. Its `storage_type:gcs_private`, owner scope, sizes,
available committed files and ZIP member receipts replace worker filesystem
claims. The external manifest receipt avoids a self-hash cycle; its own serialized
size is fixed before upload. CLI-only exports keep local references. Bounds are:

| Resource | Bound |
| --- | --- |
| Outstanding admission | 100 global / 5 owner by default; counts queued + running |
| Active claim | 10 global / 2 owner defaults; proposal uses 2 / 1 |
| Admission ledger | One transactional bounded document; same limits on every reader/writer |
| Queue | 1 dispatch/sec, 2 concurrent; 5 attempts, 900 seconds, finite 5–60s backoff |
| Worker | 1 active request-bound attempt/process; service max 2, min 0 |
| Attempts/deadlines | Existing B2: 3 generation attempts, 12 dispatch generations, 900s total; 240s generation + 45s publication <=300s attempt <330s worker HTTP <360s task |
| Objects | <=9 allowlisted files; <=8 MiB/file, <=64 MiB/set; manifest/result <=1 MiB |
| Concurrent object reads | 8 per API process, including result manifests |
| Retention | Requests/results/objects: 7d from acceptance; events/key mappings: 1d |

Firestore TTL on parent jobs is disabled. It cannot delete event subcollections,
and premature parent deletion would destroy cleanup authority. A persistent
`cleanup_at` inventory is queried in pages of five; each sweep deletes at most
32 objects/job and 100 child events/job before deleting an expired parent, run
mapping and dispatch record. Orphans cannot be deleted before a day beyond the
overall execution deadline. A winning unexpired attempt is preserved. Cleanup
failure leaves the inventory for retry. Independent child-event/idempotency TTL
is a backstop, and expired access is denied before asynchronous deletion. The
bucket's eight-day object-age lifecycle cannot precede seven-day job expiry;
explicit seven-day soft deletion retains recovery bytes and adds storage cost.
See [Firestore TTL](https://docs.cloud.google.com/firestore/native/docs/ttl) and
[GCS lifecycle](https://docs.cloud.google.com/storage/docs/lifecycle).

## Reviewable infrastructure and migration gates

`docs/config/durable/main.tf` defines API, private worker, separate private
maintenance service, queue, dedicated Firestore database/indexes, private bucket,
five separate runtime/caller identities and an authenticated paused schedule.
It references existing pinned Secret Manager versions without creating secrets
or putting payloads in state. The API has object-get only and no model-secret
binding; worker has object-create/get; maintenance alone has list/delete and
queue-enqueue authority. Tasks and Scheduler callers have only service-level
Invoker on their corresponding private services, plus the explicitly reviewed
token minting/service-agent prerequisites below. No Owner/Editor or public bucket
grant is used. The database-user grant is conditioned to the dedicated database.

Before any owner-approved plan/apply:

1. Review the complete Terraform plan, existing resources to import, database
   location/ID and non-secret inputs. Use ADC/Workload Identity; never JSON keys.
   The external deploy identity needs only reviewed resource-specific deployment
   permissions and `actAs` on the runtime/caller identities it manages. Existing
   project service-agent roles must be verified; service enablement alone is not
   proof of successful token minting.
2. Verify IAP organization/OAuth prerequisites and the IAP service agent's Invoker
   binding, restricted allowlist, Invoker checks and no direct bypass. Read back
   actual Cloud Run default `run.app` URIs; they must equal configured worker and
   maintenance audiences. Tasks/Scheduler must target the default URL and remain
   in the same project for internal ingress. The two internal roles reject each
   other's routes and have no user-data routes. See
   [direct IAP](https://docs.cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run),
   [internal ingress](https://docs.cloud.google.com/run/docs/securing/ingress),
   [Tasks OIDC](https://docs.cloud.google.com/tasks/docs/creating-http-target-tasks)
   and [Scheduler OIDC](https://docs.cloud.google.com/scheduler/docs/http-target-auth).
3. Upgrade **all** API/worker/maintenance durable readers before new B3 writes.
   The frozen v1 envelope now has additional options, `architecture:null` for
   generator auto-selection, and job `cleanup_at`; B1/B2 readers reject added
   fields; event records also add bounded log fields/kinds. There is no supported mixed-writer rollout. Existing experimental
   B1/B2 data must be inventoried and either drained using its accepted image or
   explicitly migrated with reviewed run-index and cleanup-inventory backfills.
   Disable any experimental parent TTL before such a migration. No public durable
   admission existed in accepted B1/B2; this PR does not silently rewrite records.
4. Review the locked Terraform provider, index exemptions, child TTL and parent
   TTL disablement. The legacy JSON index proposal is aligned; do not apply both
   Terraform and a different index/queue source of truth. Preserve the B1 dispatch
   deadline/due composite index, including any earlier experimental-data backfill.
5. Build a digest-pinned image using `--build-arg LNF_INSTALL_GCP=true`. Leave
   submissions false and Scheduler paused until the following qualification is
   approved. API and maintenance receive only the HMAC secret; only workers may
   receive current approved provider credentials. Stub qualification needs none.

The old production deploy workflow is now **manual only**, still protected by
`production`. The new validation-only workflow is manual, uses `durable-staging`,
and remains skipped unless both review variables are explicitly set. It performs
no authentication, Terraform plan/apply, provisioning or deployment. The owner
must independently review environment protection and existing WIF issuer,
audience, numeric repository-ID/ref/environment conditions before any future
deploy job. [Google WIF guidance](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines).

Request-based CPU bills request processing on the worker, which holds the task
request until settlement; it does not rely on idle background CPU. Min instances
remain zero. API polls, claim/heartbeat/CAS retries, event retention and cleanup
drive Firestore operations; queue rate/concurrency and retries bound dispatch
pressure, not provider billing. GCS exports, soft-deleted bytes, downloads/egress,
Scheduler invocations and container registry/image operations have their own
costs. Retries can repeat provider calls and cost; there is one authoritative
result, not exactly-once external execution. Review current regional pricing
and budgets before activation; this proposal makes no price guarantee.

## Qualification recipe and receipt capture

### Credential-free postmerge qualification

The repeatable entry point is `scripts/qualify_durable_backend.py`. Run it with
a task-private virtualenv Python from this checkout. Setup may download packages
and the official emulator; test execution uses sanitized subprocess settings,
disables dotenv and tracing, and permits loopback Python/gRPC connections only.
It replaces HOME/USERPROFILE and Google CLI configuration with temporary
directories. It never reads ADC or authenticates a cloud project. Do not pass
production configuration or keys. Every invocation requires a new receipt path.

Use the supported Python 3.10 baseline. An additional Python/platform run is
separate evidence. Install Node for the browser harness, Java 21+ for the
emulator, and `psutil` for bounded cleanup of owned process descendants:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -e . psutil
.\.venv\Scripts\python.exe scripts/qualify_durable_backend.py --level core --receipts output/qualification/core
.\.venv\Scripts\python.exe -m pip install -e ".[gcp]"
.\.venv\Scripts\python.exe scripts/qualify_durable_backend.py --level sdk --receipts output/qualification/sdk
```

The core level must run before installing the GCP extra; its preflight rejects
cloud SDK installations. The SDK level imports the actual optional packages
before collecting identity, store, dispatch, worker, artifact, API and browser
contracts with injected transports. The original core CI workflow is unchanged.

Install the emulator using the [official instructions](https://docs.cloud.google.com/firestore/native/docs/emulator).
The runner launches the official emulator JAR directly, as the Firebase CLI does,
to own one Java process without a global CLI installation or cloud configuration.
The CI workflow pins emulator 1.22.0 and checks its SHA-256 against the
[Firebase tools download manifest](https://github.com/firebase/firebase-tools/blob/master/src/emulator/downloadableEmulatorInfo.json).
For a Windows local setup, download that JAR, verify the same digest, and supply
its path plus a Java 21+ executable (the Java and JAR paths below are examples):

```powershell
.\.venv\Scripts\python.exe scripts/qualify_durable_backend.py --level emulator --java C:/tools/java21/bin/java.exe --emulator-jar C:/tools/cloud-firestore-emulator-v1.22.0.jar --port 8081 --repeat 2 --receipts output/qualification/emulator
```

On Linux use `.venv/bin/python` with the same runner arguments. The runner sets
`LNF_TEST_FIRESTORE_EMULATOR=1` and `FIRESTORE_EMULATOR_HOST=127.0.0.1:8081`
for pytest and its independent application subprocesses. It refuses an occupied
port, binds only loopback, probes the Firestore REST service for at most 60
seconds, and limits each pytest run to 900 seconds. Both runs use fresh
`demo-lnf-...` projects in the same live emulator. Application process replacement
is tested; the emulator's in-memory database does not survive emulator restart.

The emulator's lock model can exhaust the SDK's five transaction attempts with
`ABORTED / Transaction lock timeout`. The contention tests keep simultaneous
first requests and allow at most two additional **caller** replays of only
`job_backend_unavailable`/503, using a deterministic stagger. Acceptance retains
the same owner/key/body; claim replays retain the original version/fence/intent.
They still require exactly one created job, one winning claim and a conflicting
loser. Exhausted caller replays fail the test. JUnit properties record replay
counts. This is bounded request replay qualification; it does not promise every
contending request succeeds immediately or change production retry behavior.

Each receipt directory contains the dependency/import preflight, Java version
and JAR digest where applicable, exact pytest commands, collected node IDs,
JUnit XML, test output, emulator diagnostics and `receipt.json`. Exit 0 requires
nonempty matching collection/results, every designated suite present, all
required emulator node IDs, and no unexpected skips. The only core platform
exceptions are the two exact Windows-only lifecycle tests and their exact
reasons on non-Windows systems. Missing SDKs, missing Node, missing Java/JAR,
startup failure, timeout, partial results, skipped emulator cases and failed
tests return nonzero. Logs contain only the sanitized test configuration and
synthetic test identities; no environment dump or live credentials are captured.

`.github/workflows/durable-qualification.yml` runs these three levels in separate
Python 3.10 jobs/environments on ordinary PR/push events, retaining receipts for
seven days. It uses read-only repository permission, with no cloud authentication,
environment activation, secrets, id-token permission or deployment steps.
SDK transport mocks, emulator persistence, approved staging and production remain
separate evidence levels. The disk object transport is a test double; passing
this workflow does not qualify GCS, Tasks redelivery, IAP/OIDC, IAM, production
indexes, service limits or activation.

Offline deterministic commands are in the B3 qualification receipt. The optional
emulator command is:

```bash
LNF_TEST_FIRESTORE_EMULATOR=1 FIRESTORE_EMULATOR_HOST=127.0.0.1:8081 \
python -m pytest tests/integration/test_firestore_job_emulator.py \
  tests/integration/test_durable_api_emulator.py -v
```

Use only a local emulator and anonymous credentials. The new harness starts fresh
API processes, deliberately terminates a worker after private upload/before commit,
reconciles and completes from another worker process, then reads status/result/SSE
and bytes from new API processes. Its object transport is a disk-backed double;
it does not qualify GCS, OIDC, IAM, or an actual Tasks service.

After approved staging resources/authentication are available, capture commands,
UTC timestamps, exact source/image digests, identity subjects (redacted in public
receipts), revision names, object generations and request IDs. Do not log tokens,
HMAC keys, prompts or provider secrets. Keep private receipts access controlled.

- [ ] Review `terraform fmt -check`, `init -backend=false`, `validate`; then obtain
  separate approval for an authenticated plan and reviewed apply. Confirm actual
  IAM bindings and queue/database/bucket settings match the plan.
- [ ] Deploy the reviewed digest to staging with two API instances/revisions,
  worker + maintenance services, no minimum instances, submissions initially off.
  Verify `/health` 200 and `/ready` truth, missing-store/identity failures, paused
  submissions, and absence/protection of internal/user routes at the wrong service.
- [ ] With two approved IAP principals, enable **stub-only qualification requests**
  and the reviewed Scheduler. Submit through API A, inspect/stream/download through
  API B. Capture actual distinct revision/instance receipts; no affinity assumption.
- [ ] Lose the accepted response and retry the same key; change the payload with
  that key; use another key for a distinct action. Check one authoritative job
  and no ownership/credential data in Tasks payloads.
- [ ] Restart both API instances. Kill a worker after private upload and before
  finalization; allow real Tasks redelivery and Scheduler reconciliation. Verify
  one winning fence/result and rejection of late old-worker completion. Capture
  actual OIDC forwarding, Tasks GetTask readback and Invoker enforcement.
- [ ] For the second principal and an unsigned/expired assertion, deny status,
  SSE, result, cancel and every artifact. Compare absent/wrong-owner responses.
  Verify direct backend and public bucket access are denied, and API readback
  works without a model-secret binding.
- [ ] Exercise cancel/finalize races, queue outage/retry exhaustion, owner/global
  capacity, pruned/future/malformed SSE cursors, browser disconnect/reload and
  transient result-fetch failures; confirm no automatic second generation.
- [ ] Use isolated **staging-only test records** with reviewed logical deadlines
  to prove access-time expiry before deletion. Capture bounded orphan/event
  sweeps, preservation of unexpired winners, exact-generation downloads and
  missing/corrupt object failure. Do not shorten real accepted job retention.
- [ ] Drain submissions, preserve receipts, pause Scheduler only after all active
  jobs settle, and clean approved staging resources with a reviewed teardown plan.
  Database/bucket protection intentionally prevents an accidental blind destroy.

## Pause, rollback and run drain

Set `LNF_DURABLE_SUBMISSIONS_ENABLED=false` on the B3 API through a separately
approved configuration deployment. Keep `LNF_JOB_BACKEND=firestore`, the same
namespace/HMAC, and compatible B3 readback, worker and maintenance revisions.
Health advertises paused generation while old job references still work. Leave
queue/reconciliation enabled until all accepted jobs reach terminal status;
continue retention cleanup until the seven-day readback obligations expire.

Do not point durable traffic at the Phase A image, reinterpret durable IDs as
local jobs, delete the database/bucket, rotate the HMAC during idempotency retention,
or change provider reference meanings while draining. A fallback ephemeral service
must be a separate deployment/trust domain. Keep the B3 readback service at the
existing origin until its result references expire. Only then consider an
owner-approved rollback below the schema boundary. Capture a final empty active
inventory, terminal/readback receipts, queue status and cleanup receipts before
pausing Scheduler or removing resources.

## Owner acceptance matrix

| Gate | Evidence required | Decision boundary |
| --- | --- | --- |
| Code / offline | Focused regressions, full suites, static debt comparison, real CLI/API stub exports | Local receipts only |
| Emulator | Separate-process tests above against a running local Firestore emulator | No cloud IAM proof |
| Staging | All checklist cases, real two-principal IAP/OIDC/Tasks/GCS receipts | Separate approved execution |
| Production | Reviewed migration, resources/IAM/budget, staging acceptance, drain/rollback rehearsal | Explicit owner approval |

Merging code is not #380 acceptance or rollout authority. #381, #382, #383, #334
and #335 remain outside this change.
