# B2 managed execution qualification

Part of #380; relates to #378; preserves #379 and #385.

## Exact source and scope

Fetched baseline and B1 merge:
`305274f7eca82655e3556b2df50f0406f2d7905c` (PR #392), with accepted B1 head
`e988165aa2c4a2bc2a65db6a0163ecfbdf0c2c20`. Phase A PR #385's actual diff and
nine resolved inline threads were reviewed, including cancellation suppression,
artifact symlinks and bounded event replay. The only intervening main work since
the prompt's historical `60e205b` was B1. Main was refetched before publication
and still matched the baseline. Existing open implementation/documentation PRs
did not overlap these worker adapters. No existing worktree was reset or edited.

Tested implementation commit:
`c6d2c2d77a78b24925777be83c1e2e161cef4f44`, branch
`codex/380-b2-durable-execution`. A following receipt-only commit adds this file;
the final published head is reported in the PR. One production writer made all
changes. Other agents investigated/reviewed and ran read-only checks.

The existing generator remains authoritative. Public durable admission is still
disabled. No new issue, merge, deployment, billable resource, IAM/IAP change,
credential or production-variable change is included. The worker is a separate
entry point and does not mount routes on the public IAP app. The full suite's
existing notebook tests are distinct from running generated user notebooks as a
new hosting feature; no such hosting evaluation was introduced.

## Environment and reproducibility

Windows 11 x86_64 (build 26340), CPython 3.12.2, a task-local virtual environment
inheriting installed development packages. Additional optional SDKs installed
successfully: Cloud Tasks 2.26.0, Storage 3.17.1, Firestore 2.34.1; google-auth
2.56.3. Other observed versions: Pydantic 2.14.1, LangGraph 1.2.16,
langchain-openai 1.7.2, OpenAI 3.35.1, pytest 8.4.2, Ruff 0.16.5,
Black 26.10.1 and mypy 1.19.1. These are observed versions, not new core pins.

Final qualification invocations prepended this checkout's `src` to `PYTHONPATH`, removed
ambient API keys/tokens/secrets and emulator/cloud credential overrides, and
disabled tracing. Imports were verified against the checkout, including a fresh
process that denies all Google imports during core/public/worker initialization.
`JUPYTER_PATH` pointed to the installed base Python runtime's `share/jupyter` so
the inherited environment can locate the `lab` template. No live LLM calls,
cloud RPCs or real secrets were used for offline tests. New optional SDK/signing
qualification tests skip when their optional packages are absent.

Private command logs record exact argv, stdout, stderr, elapsed time and exits;
they and the virtual environment are excluded from publication. To reproduce,
install the normal full/dev dependencies and optional `gcp` extra, set
`PYTHONPATH=<checkout>/src`, set `JUPYTER_PATH=<base-python>/share/jupyter` when
using an inherited environment, remove ambient credentials and disable tracing.
Run the focused files below, then the requested repository commands.

## Final command results

| Gate | Actual final result | Exit |
| --- | --- | --- |
| Six new B2 unit modules plus B1 store contract/Firestore adapter modules | 132 passed | 0 |
| `python -m pytest tests/unit/ --asyncio-mode=auto -q` | 1,127 passed, 5 warnings | 0 |
| `python -m pytest tests/patterns/ -v` | 82 passed | 0 |
| `python -m pytest --asyncio-mode=auto` | 1,245 passed, 5 skipped, 5 warnings | 0 |
| `python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics --exclude .venv-b2` | 0 findings; task-private environment excluded | 0 |
| `ruff check src/ tests/` | 1,234 baseline findings, no added file/code identities | 1 |
| `black --check src/ tests/` | Same 74 baseline failing files | 1 |
| `mypy src/` | Same 103 baseline diagnostics in 13 files | 1 |
| Focused B2/B1 jobs + worker Ruff / Black / mypy | Passed; mypy checks 16 source files with imported baseline modules silent | 0 |
| `node --check src/langgraph_system_generator/api/static/app.js` | Passed | 0 |
| `git diff --check`, staged diff check and tracked-source conflict-marker scan | Passed | 0 |
| Credential-free real CLI + ASGI API stub smoke | Both generated 16-cell nbformat-v4 notebooks, HTML, manifest and authorized API download; actual import path verified | 0 |

The three broad static gates are **not green**. An independent read-only checkout
at the exact base produced 1,234 Ruff findings, 74 Black failures and 103 mypy
errors. Comparison of file/code identities, failing file sets and normalized
diagnostic text found no additions. No unrelated baseline debt was reformatted,
suppressed or weakened. The five full-suite skips are two opt-in local emulator
cases and three opt-in packaging checks.

## Failure injection and review evidence

Initial tests failed to collect before the new modules existed. Behavioral RED
cases then reproduced real-output ZIP newline incompatibility, v3 notebook
acceptance, same-project dispatch validation, missing manifest metadata,
registration changes and removed references. Targeted corrections passed on both
store adapters using B1's shared contract fixture. The fake Firestore transport
enforces transactions/read-before-write, and the queue fake exercises actual
Cloud Tasks protobuf request conversion. Storage fakes verify create-only and
generation-matched upload/read/delete arguments and immutable byte receipts.

| Required failure | Executable evidence |
| --- | --- |
| Acceptance before enqueue crash | `test_acceptance_crash_is_repaired_and_payload_has_only_references` |
| Create response or DB mark lost | `test_create_response_and_mark_update_loss_reuses_one_task` |
| Duplicates and active worker loss | `test_active_duplicate_is_retryable_then_loss_recovers`, B1 synchronized claim-race contracts |
| Lease replacement and late old worker | `test_old_upload_cannot_win_after_replacement_or_cancellation`, B1 independent stale-fence cases |
| Heartbeat/storage outage and finite retries | `test_heartbeat_outage_stops_attempt_without_publication`, partial-upload cases, repeated queue outage and bounded generation-attempt tests |
| Cancellation before dispatch/during generation/finalization | Dedicated dispatch, worker cancellation and B1 transactional cancellation/completion race cases |
| Partial/checksum/collision/missing manifest | Parameterized `test_partial_corrupt_or_incomplete_artifacts_never_complete`; required metadata and malformed ZIP cases |
| Upload before completion crash; commit before ack loss | Private-upload state assertion, lease replacement, `test_completion_commit_response_loss_redelivery_returns_same_result` |
| Reconciler overlap or queue exhaustion | `test_overlapping_reconcilers_only_enqueue_one_identity`, lost delivery and tombstone/backoff/cap cases |
| Fake identity/stale generation/unauthorized destination | Real google-auth signing verification, actual ASGI Authorization forwarding, route-specific SA denial, config and stale-delivery cases |
| Noncooperative deadline and capacity | Real separate process killed/reaped at deadline; capacity remains occupied until reaping |
| Every API/worker dictionary discarded | Fresh B1 store/service/worker instances preserve job/idempotency identity; optional real-emulator separate-process recovery |

The final review found a publication cutoff error: early generation left 275
seconds for a subsequent read where the declared phase budget required 44. A
fake-clock regression failed `275 != 44`, then passed after the cutoff was
measured from the publication marker and capped by the overall deadline.
Malformed ZIP cases failed `503 != 422` and now become permanent validation
failures. An oversized file configuration initially passed; it now rejects more
than 8 MiB, matching the installed SDK's single multipart upload threshold.
All four final targeted regression cases passed, and the independent reviewer
reran them successfully. The source reviewer found no remaining blocker among
these findings; this is not external approval or cloud qualification.

Non-successful intermediate work is not qualification: a pre-review full run was
intentionally stopped with exit 4294967295 after the deadline defect was found.
The final full run above replaced it. An independent real-output test initially
failed because its inherited Jupyter template path was unset; the two cases then
passed with the verified installed template path, without source/assertion or
timeout changes. Smoke-script mistakes in the CLI flag and health field were
corrected in the private harness and rerun successfully. A private log-printing
Unicode issue did not alter the recorded Black exit/result; the final helper
prints UTF-8. These failures were not counted as passes.

## B3 interface and evidence handoff

Reuse B1 `JobStore`, `WorkerJobService`, models and Firestore adapter. The additive
internal `reschedule_dispatch(job_id, version, fence, intent_id, delay_seconds)`
port rotates an unclaimed wakeup through the existing transactional state machine.
`DurableJob` adds persisted `attempt_limit` and `dispatch_limit` defaults. All
durable readers must upgrade before new records are written: old B1 frozen readers
reject these additional v1 fields. This is documented in ADR 0002; no mixed-reader
rollout or experimental-data migration was performed.

`CloudTasksDispatcher.dispatch(intent)` returns a deterministic task reference.
`ManagedWorker.execute(service, TaskPayload)` holds the request through settlement.
`GCSArtifactStore.publish_manifest(job, files, fence)` returns the verified private
final manifest's external `ArtifactRef`; only B1 fenced finalization publishes its
winning pointer. Context-free deletion fails closed; explicit orphan cleanup
checks retention, current ownership, winning attempts and object generations.
`Reconciler.reconcile_once` and the authenticated private HTTP endpoint require no
browser activity. See [runbook and HTTP outcome table](../durable-worker.md).

**Offline:** qualified by the receipts above, including real generator stub outputs,
real SDK request shapes, signatures and killable subprocesses.

**Emulator:** not run. Two opt-in tests include local anonymous Firestore contention,
fresh-store replay and separate-process lease recovery. An in-memory/fake SDK
receipt does not prove real persistence. No Cloud Tasks emulator is claimed.

**Staging:** not run. Still required: actual Tasks OIDC forwarding/Invoker bindings,
Scheduler authentication, worker loss and retry exhaustion, current Firestore
indexes/contended RPC timing, bucket privacy/IAM, generation preconditions,
upload throughput and platform timeout read-back. Configuration is review-only.

**Production:** not run or changed. Public durable admission, owner-scoped public
routes/downloads/events, global inventory/retention cleanup, quotas and rollout
remain B3. One authoritative result is guaranteed by fencing; repeated provider
calls/cost/side effects and incomplete remote cancellation remain possible.

Hosted CI is a separate gate. At qualification time workflows were listed active,
and the latest main Python/Documentation runs on the B1 merge had succeeded;
the prompt's earlier startup_failure receipts are historical failures. No workflow
was enabled, rerun or deployment approved. The final B2 PR's exact-head hosted
state must be read separately and is reported in the PR/conversation.

## PR 393 configuration review follow-up

[Codex review 5594183996](https://github.com/dhar174/langgraph_system_generator/pull/393#pullrequestreview-5594183996)
identified two P2 configuration defects at published head
`34e1d74de6e03e74bf26d8f4162acf21e26f06d3`:

- The worker accepted roots outside a narrower `LNF_OUTPUT_BASE`, including
  lexical `..` escapes. It now resolves the root, requires containment within
  both the current directory and the existing generator output-base contract,
  and passes the canonical root to the worker/artifact store. Invalid roots
  return `503 worker_output_root_invalid` before store construction, job claim
  or directory creation. The shared generator helper retains its existing
  `BASE_OUTPUT_DIR` test override; CLI/package behavior is unchanged.
- Equal Tasks/Scheduler service accounts collapsed the route allowlists. The
  configured runtime now rejects that configuration with
  `503 worker_configuration_invalid` before store construction on either route.

All seven new configuration regression cases failed against the reviewed head:
unsafe settings reached identity verification (`401` instead of configuration
`503`), invalid output bases were accepted, and valid normalized roots retained
lexical `..` segments. All seven then passed after the correction. The expanded
B2/B1 focused set passed 139 tests, and the unit suite passed 1,134 tests with
five existing warnings. Patterns passed 82 tests. The final full suite exited 0:
**1,252 passed, 5 skipped, 5 warnings in 373.69 seconds**. Focused Ruff/Black/mypy,
fatal flake8, JavaScript syntax, documentation coverage (5 tests), diff/conflict
checks and credential-free real CLI/API stub generation/download all passed.
Broad Ruff/Black/mypy remain non-green with the same 1,234 findings / 74 files /
103 errors in 13 files as the exact base. Fresh comparison verified identical
Ruff file/code counts, Black failing files and mypy error identities/messages.
Receipts use the same Windows/Python/optional-SDK profile and credential-free
environment described above. The exact correction SHA and its separate hosted
receipt are reported in the PR; the earlier head's CI does not qualify this fix.

The PR had been marked ready for review externally; the follow-up preserves that
state and keeps it open. Emulator/staging/production gates remain unperformed,
and public durable admission remains disabled.
