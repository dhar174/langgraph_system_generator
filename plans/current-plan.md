<!-- repo-agent-bootstrap:file-kind=current-plan -->
<!-- repo-agent-bootstrap:provenance=repo-agent-bootstrap@2026-04-16 -->
<!-- repo-agent-bootstrap:managed:start -->
# Current Plan

## Objective
Continue the generated-output quality wave under epic #342 while keeping repo
context aligned with the merged reliability, manifest-truth, and generated-chat
contract work.

## Scope
Included:
- `plans/current-plan.md`
- `memory-bank/activeContext.md`
- `memory-bank/progress.md`
- `memory-bank/tasks/_index.md`
- `memory-bank/tasks/TASK004-generated-output-quality-wave.md`

Excluded:
- Reopening #351-#355 or #350; those are completed by merged PRs.
- Starting #343 implementation before syncing from `main`.
- Duplicating PR #357 behavior while #344-#348 are still untriaged against
  current code.

## Plan
1. Keep local `main` synced with `origin/main`.
2. Refresh MemoryBank and plan context for merged PR #356, PR #358, and PR
   #357.
3. Start the next implementation branch from synced `main`:
   `codex/canonical-graph-topology-343`.
4. Implement #343 first: preserve canonical graph topology in generated
   notebook code, Mermaid/schema exports, manifests, and QA.
5. Re-triage #344-#348 against merged PR #357 before opening overlapping
   follow-up branches.

## Validation
- `gh issue list --state open --limit 200 --json number --jq 'length'`
- `gh issue list --state open --limit 200 --json number,title`
- For #343 implementation, start with focused graph/notebook/QA tests, then
  run `pytest tests/unit/ --asyncio-mode=auto -q`.

## Completion criteria
- #343 has a focused branch and PR, or is explicitly deferred with evidence.
- MemoryBank and plan context reflect current issue/PR state.
- #344-#348 have been checked against merged PR #357 before more code is
  written for those issues.
<!-- repo-agent-bootstrap:managed:end -->
