# TASK008 - Truthful generation outcomes (#382)

**Status:** In Review (implementation complete; PR #397 open)

**Added:** 2026-10-22

**Updated:** 2026-10-22

## Original Request

Implement #382 across shared generation, package/CLI, ephemeral/durable APIs,
SSE result retrieval and browser; open a PR without merge/deployment or activating
durable admission. Use one production writer and read-only specialists.

## Contract and Implementation

The accepted contract is in `docs/generation-outcomes.md`. One typed outcome and
pure derivation distinguish completion, artifacts, candidate-bound QA, trusted
smoke, generated execution and usability. Current evidence alone qualifies the
selected candidate; final repairs always receive QA. Legacy manifests are limited
and readable. Generated execution and stub static QA remain not run.

## Progress Tracking

**Overall Status:** Implementation complete; qualification evidence and owner review tracked in PR #397

| Subtask | Status | Evidence |
| --- | --- | --- |
| Contract-first draft PR | Complete | #397, base 81d66f2, contract commit 57e0191 |
| Shared outcome/routing and surfaces | Complete | Current candidate evidence and final repair validation; focused tests pass |
| Diagnostic publication regressions | Complete | Real stub/export/store/worker, fake transports, bytes/receipts and one publication |
| Required qualification | See PR #397 | Unit 1,353 passed/1 skipped; patterns 82 passed; final SDK/full receipts and exact-head checks maintained in PR |
| Independent final review | Complete | Read-only review confirmed through code head 0d3a3b9; no substantive findings |
| PR handoff | Owner review | #397 remains open; readiness and final counts are recorded there after receipt inspection |

## Progress Log

### 2026-10-22

- Refreshed origin/main and created isolated codex worktree; opened draft PR #397
  with the contract before implementation, as authorized.
- Implemented candidate provenance, outcome derivation, final-candidate routing,
  CLI/API/browser integration and diagnostic durable completion.
- Preliminary review identified legacy blocker retention, independent artifact
  facts and unknown-usability wording; fixes and regressions are included.
- Candidate/graph regression fixtures execute the compiled graph with real async
  wrappers around AsyncMock and assert stage order, current candidate identity,
  current reports and exact repair counts for budgets 0/1/3/6. Python 3.10 hosted
  tests and Windows focused tests pass after correcting mock signatures.
- Local unit gate: 1,353 passed/1 optional PDF skip, exit 0. Pattern gate:
  82 passed, exit 0. All five architectures exported offline IPYNB/HTML/ZIP with
  matching `unverified`/`not_run`/unknown qualification and file receipts.
- Fatal lint across 271 tracked Python files, focused lint/format/type checks,
  JavaScript syntax and diff checks pass. Broad Ruff (1,238), mypy (103) and Black
  (76 files) retain baseline debt with no added diagnostic identities/files.
- First full run: 1,469 passed/8 skipped/2 failures in unchanged process-cleanup
  tests whose two-second deadlines expired before child PID output. Both pass
  in isolation unchanged. Receipts are retained; serial SDK/full rerun receipts
  and final outcomes are tracked in PR #397. Hosted SDK qualification passed
  241/241; emulator recovery passed 4/4 in each of two fresh namespaces on code
  head 0d3a3b9.
- The first local SDK trial hit its outer timeout after an existing synthetic
  one-second child missed progress during SDK/site startup and an unbounded test
  readiness wait remained pending. Narrow test fixtures now use minimal startup
  for trusted PID/sleep/progress programs, bound readiness and always gather
  owned tasks. PID timeout fixtures allow guarded launcher startup within a
  ten-second test deadline. Production commands/deadlines and separate native
  gRPC/socket/dotenv guard assertions are unchanged. All four affected cases
  pass in the hermetic environment; final SDK/full receipts are linked in PR #397.
- Independent review covered final-candidate routing, missing/stale evidence,
  retry boundaries and immutable artifact consistency; no substantive findings
  remain. PR #397 records the final head, inspected gate receipts and handoff.
- No cloud resources, IAM, deployment or durable admission changed. #380 remains
  open; #381 is not implemented.
