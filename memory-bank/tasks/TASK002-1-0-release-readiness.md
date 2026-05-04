# TASK002 - 1.0 Release Readiness Implementation

**Status:** In Progress
**Added:** 2026-05-04
**Updated:** 2026-05-04

## Original Request

Implement the 1.0 release readiness plan: update the canonical release tracker,
close the stale draft PR, fix the diagram workflow token path, resolve packaging
issue #258 with TDD-backed install smokes, add a local LangGraph evaluation
gate, update release metadata/docs/MemoryBank, triage stale issues, verify the
release branch, and open one PR into `main`.

## Thought Process

The release is defined as CLI/API/package stability rather than distributed
production hosting. The highest-risk release blockers are packaging correctness,
workflow health, and final verification. Code changes should stay narrow and
test-first.

## Implementation Plan

- Create an isolated `codex/1.0-release-readiness` worktree branch from current
  `origin/main`.
- Update #256 as the 1.0 tracker and close #288 if it still has no file delta.
- Add failing release metadata and packaging smoke tests.
- Fix `.github/workflows/diagram.yml` to use the workflow token path.
- Update package version/classifier, root license, changelog, and public docs.
- Add a local deterministic release evaluation dataset/script.
- Run targeted and full verification, then push and open a release PR.

## Progress Tracking

**Overall Status:** In Progress - 90%

### Subtasks

| ID | Description | Status | Updated | Notes |
|----|-------------|--------|---------|-------|
| 2.1 | Create release branch/worktree | Complete | 2026-05-04 | Worktree created under `.codex/worktrees/1.0-release-readiness`. |
| 2.2 | Update #256 and close #288 | Complete | 2026-05-04 | #256 retitled/body-updated; #288 closed as stale/superseded. |
| 2.3 | Add packaging smoke tests and fix #258 path | Complete | 2026-05-04 | Minimal/API/full isolated smokes pass when opted in. |
| 2.4 | Add release metadata and diagram workflow fix | Complete | 2026-05-04 | Version, classifier, license, changelog, and workflow token updated. |
| 2.5 | Add local release evaluation gate | Complete | 2026-05-04 | Dataset and `scripts/run_release_eval.py` added; targeted test passes. |
| 2.6 | Triage stale issues with evidence | Complete | 2026-05-04 | Closed stale completed and duplicate issues; kept true residuals open with audit comments. |
| 2.7 | Run final verification and open PR | In Progress | 2026-05-04 | Full pytest and flake8 fatal-error gate pass; publication pending. |

## Progress Log

### 2026-05-04

- Created the release-readiness worktree branch from current `origin/main`.
- Updated #256 to track 1.0 release readiness and closed stale draft PR #288.
- Added release metadata tests and verified they failed before version/workflow
  changes.
- Added packaging smoke tests and verified the minimal install failure before
  fixing the CLI's non-ASCII traceback path.
- Fixed full-extra packaging import drift by removing an accidental runtime
  `pytest` import from the router pattern module.
- Added local release evaluation data/script and fixed the Deep Agents fallback
  graph so the evaluation gate has a real terminal branch.
- Closed stale completed RequirementsAnalyst, pattern/example, cross-cutting,
  and duplicate CYOA issues with evidence; left router fallback (#60) and
  iterative requirements refinement (#202) open as real residuals.
- Verified the branch with `python -m pytest tests/unit -q`, `python -m pytest
  tests/patterns -v`, `python -m pytest tests/integration -q`, full `python -m
  pytest --asyncio-mode=auto` (625 passed, 4 skipped), CI fatal-error flake8,
  opt-in packaging smokes, and the local release evaluation gate.
