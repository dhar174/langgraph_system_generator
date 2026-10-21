# Web deployment and generation runbook

For the opt-in durable API, private worker/maintenance services, owner-scoped
downloads, migration, staged qualification and rollback/drain gates, start with
[B3 durable rollout](durable-api-rollout.md). `LNF_JOB_BACKEND=ephemeral` remains
the default. The sections below describe **Phase A ephemeral mode** unless noted.
The production deployment workflow is now manual only; this change does not deploy.

Phase A of [#380](https://github.com/dhar174/langgraph_system_generator/issues/380)
hardens the existing process-local API. It does not provide a durable job backend.
Use one Uvicorn worker and a trusted single operator. Process restart loses job
records, replay history and artifact authorization references. Instance-local files
may also disappear. Retrying creates new work; it does not resume the old job.

## Local development

Install repository requirements, then run:

```bash
uvicorn langgraph_system_generator.api.server:app --host 127.0.0.1 --port 8000 --workers 1
```

Open `http://localhost:8000`. Stub mode works offline without provider or Google
credentials. Local asynchronous generation uses SSE. Bind to a private interface
or put the service behind a trusted access boundary. Local mode does not authenticate
callers. Both API generation routes enforce the independent hosted LLM endpoint
policy from [#379](llm-endpoint-security.md). CLI and direct `generate_artifacts()`
callers retain explicit output directory behavior.

## Hosted access and execution

Cloud Run detection uses `K_SERVICE`. Generation, job inspection, SSE and downloads
fail closed unless `LNF_API_ACCESS_MODE=single-operator`. Unsupported values such as
`multi-user` do not enable access. `/health` stays available and exposes capabilities
so the browser can explain disabled generation.

This setting acknowledges an administrative deployment boundary. It is **not
caller authentication** or per-user ownership. Restrict IAP access to the intended
trusted operator/admin group, preserve the Cloud Run Invoker IAM check and prevent
direct backend bypass. All admitted operators share the process-local job/artifact
trust domain. Unpredictable IDs do not replace identity authorization.

The app ignores unsigned identity headers and does not implement signed IAP JWT
verification or principal-scoped ownership in Phase A. Multi-user hosting requires
verification of the signed assertion, issuer, audience and lifetime, followed by
ownership enforcement on jobs, events, results and artifacts. See Google's
[signed IAP assertion guide](https://docs.cloud.google.com/iap/docs/signed-headers-howto).

Hosted background generation is disabled by default. When `/health` reports that
async execution is disabled, the browser uses request-bound `/generate`. The HTTP
request stays open through generation. SSE remains the progress protocol locally
and when background execution is explicitly enabled. A lost response does not prove
execution failed; a subsequent download may reach a different process.

The checked-in workflow proposes the following settings; this PR does not deploy:

| Setting | Proposed value and purpose |
| --- | --- |
| CPU billing | `--cpu-throttling`, request-based; no background-CPU cost increase |
| Scaling | Service and revision maximum 1, minimum 0; no permanently warm instance |
| HTTP concurrency | 8, allowing health/download/stream requests alongside generation |
| App generation concurrency | 2, shared admission across both generation routes |
| HTTP timeout | 300 seconds |
| Application deadline | 240 seconds, cooperative asyncio cancellation |
| Memory / access | 2Gi, direct IAP and private invocation |
| Background admission | `LNF_EPHEMERAL_ASYNC_ENABLED=false` |
| Access admission | `GCP_API_ACCESS_MODE` repository variable, default `disabled` |

Before enabling hosted use, the owner reviews IAP membership and direct-access
controls, then sets repository variable `GCP_API_ACCESS_MODE` to `single-operator`
through Settings → Secrets and variables → Actions. The next owner-approved
production workflow deploys that acknowledgment. Without it, health stays available
while generation is disabled. This PR does not change the variable or run a deploy.

A maximum of one reduces routing ambiguity; it does not guarantee a permanent single
instance. Cloud Run may briefly exceed a maximum during replacement/scaling.
Session affinity is best effort. Workers, replicas and rolling revisions have separate
registries. See [maximum instances](https://docs.cloud.google.com/run/docs/configuring/max-instances)
and [HTTP concurrency](https://docs.cloud.google.com/run/docs/about-concurrency).

### Optional background execution: owner-reviewed billing change

Instance-based billing allocates CPU outside requests and charges for an instance's
whole lifetime. It supports short background work after returning an HTTP response;
it does not make jobs durable. Minimum instances remain zero in this proposal, and
idle instances can terminate even with CPU allocated. See [Cloud Run billing
settings](https://docs.cloud.google.com/run/docs/configuring/billing-settings).

This proposed manual command is for owner review, not an applied configuration.
Substitute the intended service/project/region:

```bash
gcloud run services update SERVICE --project=PROJECT --region=REGION \
  --no-cpu-throttling --max=1 --max-instances=1 --min=0 --min-instances=0 \
  --concurrency=8 --timeout=300 \
  --update-env-vars=LNF_API_ACCESS_MODE=single-operator,LNF_EPHEMERAL_ASYNC_ENABLED=true,LNF_JOB_TIMEOUT_SECONDS=240,LNF_MAX_CONCURRENT_GENERATIONS=2
```

Keep IAP, private invocation and Secret Manager bindings intact. Read back and
verify the deployed revision before assuming settings changed. The repository
workflow deliberately resets CPU to request-based and background admission to false
on its next deployment. Maintaining an opt-in also requires a reviewed workflow
change. Phase A provisions no queue, database, storage service or minimum instance.

Inspect actual configuration without changing it:

```bash
gcloud run services describe SERVICE --project=PROJECT --region=REGION \
  --format='yaml(metadata.annotations,spec.template.metadata.annotations,spec.template.spec.containerConcurrency,spec.template.spec.timeoutSeconds,status.latestReadyRevisionName)'
```

Cloud Run sends SIGTERM before a roughly ten-second shutdown window. The Docker
entrypoint allows Uvicorn three seconds to drain HTTP connections, followed by the
FastAPI lifespan's five-second bounded cancellation wait for owned background tasks.
Forced termination, a blocked event loop or a noncooperative dependency cannot
guarantee a terminal event. The asyncio deadline cannot preempt synchronous Python
work or stop threads already running. See the [container runtime
contract](https://docs.cloud.google.com/run/docs/container-contract).

## Job execution and SSE

An accepted async job retains one owner task. Execution states are `accepted`,
`running`, `completed`, `failed`, `cancelled` and `expired`. `expired` describes
an observed execution timeout; a pruned/lost record is `unavailable`. Only one
terminal outcome is committed. Late progress/errors cannot overwrite it. Completion
means the existing artifact-generation call returned successfully. Generated-artifact
QA and live execution qualification remain separate (#382).

SSE preserves `progress`, `log`, `complete`, `error` and `events_truncated`.
Replay selects actual event IDs greater than `Last-Event-ID`. Omitted history is
reported; malformed cursors reset replay with an indicator and future cursors end
with an indicator. Subscribers observe independent copies of the retained history.
Disconnecting a stream does not cancel execution. The browser allows EventSource
to reconnect and distinguishes transport interruption from generation failure.
Compact completion events reference `/jobs/{job_id}/result`, avoiding large manifest
payloads in bounded SSE storage. The browser retries network errors, HTTP 429 and
HTTP 5xx responses up to three result-fetch attempts, with 250 ms and 500 ms delays.
It does not retry unavailable/expired results (HTTP 404/410) or start another job.
If transient retries are exhausted, the message preserves completion and the
result reference for inspection while the originating process retains it.
`GET /jobs/{job_id}/result` returns `409 job_result_not_ready` with `job_status`
when execution is still active or ended without a successful result.

Limits are read at process startup. Restart after changing them. Invalid integer
values use safe defaults and valid values are clamped to supported bounds.

| Control | Default | Bound / purpose |
| --- | --- | --- |
| `LNF_MAX_CONCURRENT_GENERATIONS` | 5 locally, 2 in workflow | Shared active generation admission |
| `LNF_MAX_TRACKED_JOBS` | 100 | Up to 10,000 retained jobs and API run reservations; full retention rejects new work |
| `LNF_MAX_EVENTS_PER_JOB` | 1,000 | Up to 10,000 progress/log events, plus one history marker and terminal event |
| `LNF_MAX_JOB_EVENT_BYTES` | 262,144 | Up to 4 MiB per job plus bounded marker/terminal overhead; individual events capped at 16 KiB |
| `LNF_JOB_TIMEOUT_SECONDS` | 240 | 1–240 seconds, cooperative cancellation |
| `LNF_COMPLETED_JOB_TTL_SECONDS` | 300 | 1–86,400 seconds after terminal execution |
| `LNF_ARTIFACT_TTL_SECONDS` | 900 | 1–86,400 seconds after successful generation |
| SSE subscriber limits | 50/job, 500 total | Fixed caps on live subscriptions |

The default aggregate retained event payload is approximately 25 MiB plus Python
object and terminal/marker overhead. Raising job/event bounds increases memory.
Artifact count/retention is bounded, but output byte sizes are not a hard disk
quota. A single oversized export can still exhaust instance memory; monitor
Cloud Run memory and keep generation concurrency conservative.

`GET /jobs/{job_id}` exposes execution state and `durable: false`. Unknown/lost
records produce an explicit unavailable response. Unknown SSE streams preserve the
HTTP-200 event-stream contract with an `error` event carrying `job_unavailable`.
That event does not claim the underlying generation failed.

## Output isolation, downloads and retention

API `output_dir` selects an allowed parent. Each sync/async request reserves an
exclusive opaque run namespace beneath it and returns the actual resolved directory.
The normalized path is checked against the trusted root with a directory separator
boundary before it is used. Traversal, null bytes, symlink components and namespace
reuse are rejected. Absolute paths beneath the root remain supported. CLI/package output
directories are unchanged.

Only registered generated files are downloadable through returned
`/artifacts?run_id=...&artifact=...` references in `artifact_contract`. A raw
filesystem path grants no access. Existing clients must follow returned references;
CLI-created files are not automatically published by the API. Source, `.env`,
unrelated files and other-run paths cannot be selected through a run reference.
Every access rechecks registration, containment, symlinks and actual file existence.

Job/event and artifact retention are separate. Completed records are retained for
five minutes by default; artifacts for fifteen minutes after terminal generation.
A single maintenance loop plus admission/access checks prune expired state. Active
generation is not removed because its creation time is old. Cleanup targets only
server-reserved run namespaces. New SSE subscriptions enforce the same terminal
retention deadline as job inspection; a subscriber already reading a terminal
record may finish that replay. Forced cleanup of active execution records a
replayable cancellation before the normal retention deadline removes its record.
Restart invalidates artifact references even if files remain; Phase A does not
reconstruct authorization from filesystem discovery.
File bytes consume Cloud Run memory and are not a durable storage budget.

| Situation | Expected behavior |
| --- | --- |
| Browser disconnects from SSE | Job continues while its process and supported execution mode remain active |
| Browser reconnects | Replay retained events; report omitted history |
| Generation raises an exception | One sanitized terminal failure |
| Generation is cancelled | Explicit cancellation where observable |
| Execution deadline exceeded | `expired` on cooperative timeout, without false success |
| Completed record retention ends | Status/result unavailable, without recovery claims |
| Cloud Run instance disappears | Local job state unavailable; retry creates new work |
| Artifact retention ends or file disappears | Download unavailable |
| Another instance receives the job ID | Unavailable in that process, without fabricated cross-instance state |

## Durable implementation and remaining qualification

B1 contracts are accepted through PR #392. B2 supplies executable private
Cloud Tasks dispatch, a separate authenticated worker/reconciler service and
fenced private object publication; see the [B2 worker runbook](durable-worker.md).
The worker requires its own reviewed 330-second Cloud Run timeout and private
Invoker bindings. B3 now wires the public routes to those contracts and provides
a separate maintenance service. Defaults continue to select Phase A, and durable
submissions require a separate explicit activation flag. No resource/IAM/deployment
change is implied by checked-in adapters or configuration proposals.

B1's [durable jobs ADR](adr/0002-durable-generation-jobs.md) defines the versioned
storage/identity foundation and offline runbook. `LNF_JOB_BACKEND=ephemeral` remains
the default. Selecting `firestore` requires verified IAP access, optional packages,
the configured shared store/private bucket and explicit activation for new work.
Misconfiguration fails closed; there is no local fallback. `/generate` returns
`409 durable_requires_async`. Paused durable services retain authenticated
readback and drain capability. See the B3 runtime matrix and qualification gates.

Issue #380 stays open for the owner's staged acceptance of the implementation,
including real two-principal IAP, queue/worker restart, object readback and
deployment receipts. Cloud packages remain optional and lazy. Offline/fake or
emulator tests do not qualify cloud IAM or production. Phase A is unsuitable for
untrusted multi-user production and must not be represented as durable.
