---
title: B1 durable generation foundation qualification
date: 2026-10-20
scope: Offline B1 evidence; no durable public activation
---

## Baseline and scope

Part of #380; relates to #378; preserves #379 and #385. Exact fetched base:
`60e205b7e9d80c31a57de5601d8ab4789045823c`. No intervening main changes were found.
Phase A PR #385 is merged; all nine inline review threads are resolved. Its
historical final head was `d1b825fcb8be7650e59abd91fe1399328afba83d`.
Open PRs #373, #372, #367, #316 and #313 did not overlap this implementation.
B1 code commit: `3b8fdf1e98f3e0e9520338a7bc3c3d303bdd182e` on
`codex/380-b1-durable-contracts`. A later documentation-only receipt commit may
change the PR head without changing tested code.

One production writer made all changes; a separate agent performed read-only
Phase A investigation and three correctness/security review passes. No issue was
created, closed, merged or deployed. No IAM, production variables, credentials or
billable resources were changed. Private command logs and virtual environment are
outside the published file allowlist.

## Environment and reproducibility

Windows 11 x86_64, CPython 3.12.2. A task-local virtual environment inherits the
installed development packages and adds the optional Firestore SDK. Tests prepend
this checkout's `src`; the import-isolation regression and CLI/API smoke verify
the actual imported package path. No installed editable copy is treated as proof
of the tested source.

Dependencies include Firestore 2.34.1, Pydantic 2.14.1, LangGraph 1.2.16,
langchain-openai 1.7.2, OpenAI 3.35.1 and pytest 8.4.2. These installed versions
are qualification evidence, not new minimum pins. Core requirements are unchanged;
the new `gcp` extra contains only Firestore and PyJWT with cryptography support.

Jupyter's shared templates need an explicit `JUPYTER_PATH` when inherited through
this virtual environment. Point it at the installed Python runtime's
`share/jupyter` directory. The first unit run had 9 export failures / 1,015 passes
because the `lab` template could not be found (exit 1). After verifying the path,
the affected 16-test export selection passed (exit 0), then the complete unit run
passed. No exporter code, assertion or timeout was changed.

The first full-suite invocation was interrupted (exit -1) after discovering that
the parent environment included provider credentials. The qualification full run
removes credential/token/secret environment variables and sets tracing false.
Unit fixtures inject fake provider keys; IAP uses generated offline signing keys;
Firestore uses a deterministic SDK transport. Stub smoke removes credentials and
blocks network entry points. No live LLM or generated-user-notebook execution is
part of the hosting smoke.

## Command results

Commands use `python` from the task environment and the verified checkout import.

| Gate | Result | Exit |
| --- | --- | --- |
| Three new B1 unit modules | 60 passed | 0 |
| New modules plus Phase A lifecycle/streaming and #379 endpoint security | 236 passed | 0 |
| `python -m pytest tests/unit/ --asyncio-mode=auto -q` | 1,033 passed, 5 warnings | 0 |
| `python -m pytest tests/patterns/ -v` | 82 passed | 0 |
| `python -m pytest --asyncio-mode=auto` with isolated credentials | 1,153 passed, 4 skipped, 5 warnings in 377.49 seconds | 0 |
| Fatal flake8 rule set `E9,F63,F7,F82` | 0 findings | 0 |
| `ruff check src/ tests/` | 1,234 baseline and changed-tree findings | 1 |
| `black --check src/ tests/` | Same 74 baseline and changed-tree failing files | 1 |
| `mypy src/` | Same 103 diagnostic identities in 13 files; baseline 74 source files, changed tree 82 | 1 |
| Focused Ruff / Black on all new Python modules/tests | Pass | 0 |
| Focused mypy on jobs and identity, `--follow-imports=silent` | No issues in 8 source files | 0 |
| `node --check src/langgraph_system_generator/api/static/app.js` | Pass | 0 |
| `git diff --check` and tracked conflict-marker scan | Pass | 0 |
| Credential-free CLI/API stub smoke | API generation; CLI notebook/HTML/manifest; nbformat v4 verified | 0 |

The flake8 command uses the requested fatal-error options and excludes the private
task virtual environment, Git metadata and bytecode. The private environment also
contains the extracted baseline used for comparisons, so including it would lint
third-party packages and duplicate baseline files. Source/tests were not excluded.
No dedicated conflict-marker script was found in repository workflows/scripts;
`git grep` checked anchored merge-marker forms over tracked files with exit 1
explicitly interpreted as no matches, and other errors treated as failures.

Broad static checks are not green. Diagnostics were compared against an extraction
of the exact base, with path/line normalization. Ruff diagnostic identities,
Black failing file paths and mypy diagnostics have no additions. New Python files
pass the focused checks. Existing debt was preserved.

## Failure tests and review disposition

`test_durable_job_contracts.py` runs the same contract against memory and the real
Firestore adapter with a fake SDK transport. Barriers synchronize acceptance and
claim races; injected clocks cover expiry without sleeps. Tests cover:

- One atomic admission and dispatch intent for concurrent identical owner/key
  submissions, 409 on conflicting payload, and isolation even when owner emails match.
- Exactly one current claimant; stale versions, expired leases and old fences
  independently reject renew, event, relinquish, completion and cancellation.
- Both deterministic completion/cancellation orders plus a concurrent race,
  terminal immutability and retained result identity after replay expires.
- Bounded physical event records, monotonic cursors across attempts, pagination,
  future-cursor rejection, bounded retry/reconciliation and overall deadlines.
- Current dispatch-generation binding, internal-service/user type separation,
  verifier-backed construction, approved provider refs and server generator version.
- Core/API imports with cloud packages, credential access and network unavailable;
  explicit Firestore selection fails closed rather than falling back.

`test_firestore_job_store.py` exercises adapter path mapping, read-before-write,
atomic rollback, retried callback execution without duplicate admission/events,
TTL timestamps, numeric due queries, fresh retry clocks and sanitized SDK errors.
`test_job_identity.py` uses ES256 signatures and injected keys/clocks to reject
malformed/unsigned/expired/wrong issuer/audience/forged-owner assertions, remote
key URLs and unsupported algorithms; key refresh and negative caching are bounded.

Review findings were resolved by adding explicit index exemptions, resampling the
transaction clock, binding claims to intent IDs, freezing internal verifier ports,
rejecting future cursors, testing fences independently from versions, completing
the ADR and enforcing provider/version policy. The final read-only source review
found no remaining B1-blocking correctness issue; it did not independently rerun
tests. B2 must use narrow route-specific account allowlists for workers versus
Scheduler, and a real OIDC verifier before exposing internal HTTP routes.

## Evidence boundaries and remaining work

| Evidence class | Qualification |
| --- | --- |
| Offline | Unit/SDK-transport contracts, signed identity, compatibility, imports and stub smoke above |
| Emulator | Not run; opt-in `tests/integration/test_firestore_job_emulator.py` remains separate |
| Staging | Not run: actual IAP audience/keys, IAM, Firestore contention/index/TTL cleanup, authenticated dispatch and object finalization |
| Production | Not run; no infrastructure provisioned, IAM changes, activation or deployment |
| Hosted CI | Workflow is active but latest inspected main run `39483297666` ended `startup_failure` with no jobs; unqualified, not passing |

The ADR contains the frozen protocol signatures, state-transition table, ownership
policy, concrete schema/index proposal, retention/deadline relationships, retry
ownership, cancellation ordering, clock assumptions and runbook. B2 adds actual
managed dispatch, bounded worker HTTP execution, OIDC verification and scheduled
reconciliation. B3 adds immutable private object publication, authorized cross-instance
public routes, explicit event/object cleanup and activation quotas. Mock persistence
does not qualify those paths. Issue #380 remains open and public durable admission
stays disabled. B2 starts after this interface is reviewed and merged or explicitly
accepted as a stacked base.

## PR #392 dispatch-query review follow-up

The review at `64e33e5dd1ba8b61c7f481a2b0db82400a327d11` identified a valid B1
store defect: with reconciliation delayed, 100 overdue pending intents could fill
the bounded dispatch query and hide newer eligible work. A regression created that
backlog and reproduced the empty result against both memory and the Firestore
adapter (2 failed, exit 1). This fixes the existing foundation contract without
implementing managed queue execution.

Dispatch documents now project the immutable job `deadline_at`. Database selection
applies `due_at <= now AND deadline_at > now` before the limit, ordered by earliest
deadline and then due time. The authoritative transactional eligibility recheck is
retained. The read does not mutate overdue jobs or depend on reconciliation/TTL.
The shared regression covers a full page, `limit=1`, exact deadline expiry and
unchanged overdue job state. A separate real-SDK protobuf test checks both filters,
ordering and limit against the proposed composite index without RPCs or ADC.

The Firestore index proposal adds `(deadline_at ASC, due_at ASC)` for the dispatch
collection; the ADR documents this query and the backfill/index prerequisites for
any preexisting experimental B1 data. No index or cloud resource was applied.
An independent read-only diff review found no actionable issue; it did not rerun
tests. The tested correction is `2e91355f5ce71f386a88e503940e084a7cfc047c`.
The following fresh runs used isolated credentials, explicit checkout imports and
the same verified Jupyter template path. The original receipts above remain
historical evidence for the initial B1 implementation.

| Follow-up gate | Actual result | Exit |
| --- | --- | --- |
| Backlog regressions and real SDK query/index selection | 3 passed | 0 |
| B1 plus Phase A lifecycle/streaming and #379 security | 239 passed, 1 warning | 0 |
| Complete unit suite | 1,038 passed, 5 warnings | 0 |
| Pattern suite | 82 passed | 0 |
| Full repository suite | 1,156 passed, 4 skipped, 5 warnings in 523.24 seconds | 0 |
| Fatal flake8 | 0 findings, same private-environment exclusions | 0 |
| Broad Ruff / Black / mypy | 1,234 findings / 74 failing files / 103 errors, unchanged baseline diagnostic identities and failing file sets | 1 each |
| Focused Ruff / Black / mypy | Pass; 12 Python files formatted, 8 source files type-checked | 0 each |
| JavaScript syntax, diff and conflict-marker checks | Pass | 0 |
| Credential-free CLI/API stub smoke | Checkout import, notebook/HTML/manifest and nbformat v4 verified | 0 |

The fresh broad checks remain non-green; no additional diagnostic identities or
failing files were found after normalizing paths and shifted line numbers against
the saved exact-base logs. The four skips remain the opt-in emulator test and three
packaging smoke checks. Emulator, staging and production qualification remain
unperformed. The new composite index is proposed only; real index deployment,
existing-data backfill and server query execution require separate qualification.
