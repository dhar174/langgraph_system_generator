# TASK004 - Generated-Output Quality Wave

**Status:** In Progress
**Added:** 2026-05-20
**Updated:** 2026-05-20

## Original Request

Refresh the open issue plan after PR #356, close completed reliability issues,
implement the next generated-output quality work, and keep repository context
aligned before continuing the wave.

## Thought Process

Treat generated-output work as a sequence under epic #342. Reliability work
from #351-#355 is complete. Manifest truth work from #350 is complete. PR #357
landed broad generated-chat runtime improvements, but issues #344-#348 remain
open and need issue-by-issue re-triage before additional overlapping changes.

## Implementation Plan

- Keep #351-#355 closed as completed by PR #356.
- Keep #350 closed as completed by PR #358.
- Continue Wave 3 with #343 before later generated credential/config or
  chatbot-fidelity follow-ups.
- For #343, preserve canonical graph topology from graph/spec metadata into
  executable notebook code, Mermaid/schema exports, manifests, and QA.
- Before working #344-#348, compare their acceptance criteria against merged PR
  #357 and close or narrow each issue based on current code evidence.

## Progress Tracking

**Overall Status:** In Progress

### Subtasks

| ID | Description | Status | Updated | Notes |
|----|-------------|--------|---------|-------|
| 4.1 | Close completed runtime reliability issues #351-#355 | Complete | 2026-05-20 | Closed as completed with PR #356 and merge commit `7881a0895de78b3de2a5ebce5c911f6699b21a27`. |
| 4.2 | Implement manifest/artifact truth for #350 | Complete | 2026-05-20 | PR #358 merged and #350 is closed. |
| 4.3 | Reconcile generated-chat contract PR #357 with open child issues | Planned | 2026-05-20 | #344-#348 are still open even though PR #357 implemented broad chat/config/tool/memory behavior. |
| 4.4 | Implement canonical graph topology preservation for #343 | Next | 2026-05-20 | Branch target: `codex/canonical-graph-topology-343` from synced `main`. |
| 4.5 | Implement remaining #348 follow-up if still needed | Planned | 2026-05-20 | Re-check after #343 and #357 triage. |

## Progress Log

### 2026-05-20

- Local `main` was synced to `origin/main` at
  `4c4f64090819190fbc859556d18458bf43194a26`, which includes merged PR #357
  and PR #358.
- The live open issue count is 29. Epic #342 remains open with #343-#349 still
  open; #350 is closed.
- Current next implementation target is #343.
