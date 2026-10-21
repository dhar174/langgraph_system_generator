---
title: B3 durable API integration qualification
---

Part of #380; relates to #378; preserves #379 and #385.

## Source and scope

Branch: `codex/380-b3-durable-api-rollout`. Exact fetched and tested base:
`101f14fcf2ab009360a2562181521c6aeb531ea0`, the B2 PR #393 merge.
Main was fetched again after qualification and still matched this base. The
published implementation head is recorded in the PR and final handoff; this
receipt is part of that commit, so it does not claim its own commit hash.

Prerequisites were verified against GitHub and the actual merged code:

| Prerequisite | Accepted head | Merge |
| --- | --- | --- |
| Phase A, PR #385 | `d1b825fcb8be7650e59abd91fe1399328afba83d` | `60e205b7e9d80c31a57de5601d8ab4789045823c` |
| B1, PR #392 | `e988165aa2c4a2bc2a65db6a0163ecfbdf0c2c20` | `305274f7eca82655e3556b2df50f0406f2d7905c` |
| B2, PR #393 | `fccdee3e6283255f8d3b69a6e783f05775eaaa2d` | `101f14fcf2ab009360a2562181521c6aeb531ea0` |

The actual Phase A diff and nine resolved review threads, B1's resolved thread,
and B2's seven resolved threads were inspected. Current open PRs did not overlap
this integration. One production writer used an isolated worktree; two other
agents investigated and reviewed without editing it. Unrelated changes in the
primary checkout were preserved.

The existing generation pipeline remains authoritative. The hosting smoke did
not execute generated user notebooks. The required full suite includes its
existing fixed notebook execution tests. No resource, IAM/IAP binding, credential,
production variable, deployment, merge or new issue was created.

## Local environment and commands

Windows 11 x86_64, build 26340; CPython 3.12.2. Qualification reused the existing
B2 virtual environment as a runtime, with this worktree's `src` first on
`PYTHONPATH`. The imported package path was checked against this checkout.
Ambient provider keys, credentials and hosting configuration were removed from
test subprocesses, and tracing was disabled. Fake embeddings/docs and module-local
model mocks keep these runs independent of live providers.

Observed optional SDKs include Storage 3.17.1 and Firestore 2.34.1. Terraform
1.13.5 was checked against the publisher's SHA-256 release checksum; the signed
Google provider 7.46.1 is locked. These are local observations, not new mandatory
core dependencies.

| Command / check | Actual result | Exit |
| --- | --- | --- |
| `python -m pytest tests/unit/test_durable_api.py tests/unit/test_durable_browser.py tests/unit/test_private_artifacts.py tests/unit/test_firestore_job_store.py -q` | 89 passed; independently repeated by reviewer | 0 |
| `python -m pytest tests/unit/ --asyncio-mode=auto -q` | 1,183 passed, 5 warnings; final repeat 259.47s pytest time | 0 |
| `python -m pytest tests/patterns/ -v` | 82 passed, 32.83s pytest time | 0 |
| `python -m pytest --asyncio-mode=auto` | 1,301 passed, 6 skipped, 5 warnings, 344.75s pytest time | 0 |
| `python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics` | 0 fatal findings | 0 |
| `ruff check src/ tests/` | 1,234 findings; same diagnostic identities as exact base | 1 |
| `black --check src/ tests/` | 74 files require formatting; same files as exact base | 1 |
| `mypy src/` | 103 errors in 13 files; same error identities as exact base | 1 |
| `node --check src/langgraph_system_generator/api/static/app.js` | Syntax accepted | 0 |
| `git diff --check` and staged equivalent | No whitespace errors or conflict markers | 0 |
| Tracked-tree conflict-marker scan | No conflict-marker lines found | 0 |
| Terraform `fmt -check`, `init -backend=false`, `validate` | Formatting/provider initialization/configuration valid | 0 |
| Credential-free CLI / ephemeral API / real worker stub smoke | Actual nbformat-v4, HTML/ZIP and private export readback verified | 0 |

The three broad static-analysis commands are **not passing gates**. They were
run against both the base and this source with the same tools; the comparison
found zero added or removed diagnostic identities (Ruff/mypy) and zero changed
Black failure paths. New typing, formatting and lint findings encountered during
implementation were corrected before the final comparison. No baseline tests or
analysis settings were weakened.

Warnings comprise the existing LangChain community deprecation, three SWIG
deprecations and Windows' ZMQ selector-thread fallback. The six skips are three
opt-in packaging scenarios, two existing Firestore emulator cases and the new
durable API emulator scenario. No emulator pass is inferred from these skips.

## Reproducible failure and recovery coverage

Run the focused command above. `test_durable_api.py` uses independently created
API apps and a shared transactional store double, fake clocks and barriers:

- API A acceptance and fresh API B status/result/SSE/download use persisted job
  state rather than shared API dictionaries; duplicate response-loss retries
  reuse one job and conflicting requests fail.
- Wrong-owner and absent status, result, SSE, cancel and artifact requests have
  matching failure surfaces. Identity and logical retention are checked again
  before ordinary and synthesized terminal SSE frames.
- Lease loss, worker reconciliation, stale completion and cancel/finalize races
  retain one winning result. Global and owner admission limits share a
  transactional bounded ledger.
- Pruned, malformed and future cursors produce honest replay gaps; a terminal
  result remains discoverable after history pruning.
- Exact-generation, committed-only downloads reject missing/corrupt objects;
  HTML is an attachment and manifest sizes match downloaded bytes. Expiry while
  a response is in flight cannot turn a promised full body into short success.
- A cancelled blocking object read holds its capacity until the SDK thread
  settles. Cleanup crossing an expiry boundary retains inventory until its
  expired-object sweep; current attempts and unexpired winners are preserved.
- Worker progress/log delivery is bounded, redacted, fenced and owner scoped.
  Browser tests execute the actual JavaScript reconnect/retry functions and
  prove result/SSE failures do not issue another generation request.

Read-only review found expiry/body truncation, a cleanup clock boundary, missing
worker log forwarding and a synthesized-terminal authorization gap. Each was
fixed with a regression test. A private fault-injection check restoring the old
expiry/cleanup behavior failed four cases; the corrected focused tests pass.
The final reviewer reported no remaining actionable blocker in the reviewed API,
artifact and retention paths. This is code review evidence, not cloud approval.

Additional offline smoke used the real CLI and ephemeral API to generate and
download 16-cell nbformat-v4 notebooks plus exports, and the real stub worker
entry point to publish/read seven private artifacts through transport doubles.
A no-network check with the installed GCS SDK accepted valid bytes and rejected
corrupt/oversized bytes, with exact generation/precondition and one download RPC
per case. It exposed optional background bucket-metadata fetching; the supplied
configuration disables it without granting bucket metadata access.

## Evidence boundaries and remaining gates

| Environment | Status | What remains |
| --- | --- | --- |
| Offline | Completed, with baseline static debt above | Fakes prove contracts and races, not remote service behavior |
| Firestore emulator | **Not run**; emulator component unavailable locally | Run opt-in separate-process integration test against a running emulator |
| Staging | **Not run** | Approved resources/authentication, real two-principal IAP/OIDC, Tasks redelivery/restart, GCS generations/IAM, cleanup and teardown receipts |
| Production | **Not run** | Owner acceptance of staging, migration, budget/IAM review and explicit rollout authorization |

`tests/integration/test_durable_api_emulator.py` is opt-in and uses real emulator
state across API and worker process restarts, including worker death after private
upload. Its object transport remains a disk-backed double. It must pass before
claiming emulator durability; even a pass would not qualify real GCS or IAM.

The repository currently reports the Python, documentation and deployment
workflows as active; the historical owner-disabled/startup-failure receipts do
not describe current workflow state. No workflow was enabled or rerun for this
work. The existing deployment trigger is changed to manual only. The new staging
workflow is manual, variable-gated and environment-protected, performs only
configuration validation, and contains no authentication, apply or deployment.
Hosted results for the published head are recorded separately in the PR.

See [the rollout runbook](../durable-api-rollout.md) for the runtime-mode matrix,
B3 reader/writer migration boundary, explicit durable `/generate` 409 behavior,
legacy output-directory handling, admission/retention budgets, costs, staging
qualification, and readback/drain rollback. Keep submissions disabled and the
Scheduler paused until owner-reviewed qualification permits activation. A code
merge does not close #380 or authorize production rollout.
