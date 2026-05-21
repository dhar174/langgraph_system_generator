<!-- repo-agent-bootstrap:file-kind=current-plan -->
<!-- repo-agent-bootstrap:provenance=repo-agent-bootstrap@2026-04-16 -->
<!-- repo-agent-bootstrap:managed:start -->
# Current Plan

## Objective
Continue the generated-output quality wave under epic #342 while keeping repo
context aligned with the merged reliability, manifest-truth, generated-chat
contract, and current canonical-graph/config PR work.

## Scope
Included:
- `plans/current-plan.md`
- `memory-bank/activeContext.md`
- `memory-bank/progress.md`
- `memory-bank/tasks/_index.md`
- `memory-bank/tasks/TASK004-generated-output-quality-wave.md`

Excluded:
- Reopening #351-#355 or #350; those are completed by merged PRs.
- Starting Wave 4 before PR #359 is merged or explicitly deferred.
- Duplicating PR #357 or PR #359 behavior while #344-#347 and #349 are still
  untriaged against current code.

## Plan
1. Keep local `main` synced with `origin/main`.
2. Refresh MemoryBank and plan context for merged PR #356, PR #358, and PR
   #357.
3. Track PR #359 on `codex/canonical-graph-topology-343` through final checks
   and merge readiness.
4. After PR #359 merges, close or update #343 and #348 based on merge evidence.
5. Re-triage #344-#347 and #349 against merged PR #357 and PR #359 before
   opening overlapping follow-up branches.

## Validation
- `gh issue list --state open --limit 200 --json number --jq 'length'`
- `gh issue list --state open --limit 200 --json number,title`
- For PR #359 changes, keep focused graph/notebook/QA tests passing, then run
  `pytest tests/unit/ --asyncio-mode=auto -q` before final merge when time
  allows.

## Completion criteria
- PR #359 is merged or explicitly deferred with evidence.
- MemoryBank and plan context reflect current issue/PR state.
- #344-#347 and #349 have been checked against merged PR #357 and PR #359 before
  more code is written for those issues.
<!-- repo-agent-bootstrap:managed:end -->
