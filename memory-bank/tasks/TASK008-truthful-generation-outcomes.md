# TASK008 - Truthful generation outcomes (#382)

**Status:** In Progress

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

**Overall Status:** In Progress - 65%

| Subtask | Status | Evidence |
| --- | --- | --- |
| Contract-first draft PR | Complete | #397, base 81d66f2, contract commit 57e0191 |
| Shared outcome/routing and surfaces | Complete | Implementation present; focused checks underway |
| Diagnostic publication regressions | In Progress | Real stub/export/store/worker and fake transports |
| Required qualification | In Progress | Focused baseline 40 passed; broad checks pending |
| Independent final review and handoff | Pending | Read-only preliminary findings being resolved |

## Progress Log

### 2026-10-22

- Refreshed origin/main and created isolated codex worktree; opened draft PR #397
  with the contract before implementation, as authorized.
- Implemented candidate provenance, outcome derivation, final-candidate routing,
  CLI/API/browser integration and diagnostic durable completion.
- Preliminary review identified legacy blocker retention, independent artifact
  facts and unknown-usability wording; fixes and regressions are included.
- Full unit/pattern/full-suite, SDK qualification and final review remain gates.
  No cloud resources, IAM, deployment or durable admission changed. #380 remains
  open; #381 is not implemented.
