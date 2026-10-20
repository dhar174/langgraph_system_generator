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
