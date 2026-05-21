# TASK004 - Generated-Output Quality Wave

**Status:** In Progress
**Added:** 2026-05-20
**Updated:** 2026-05-21

## Original Request

Refresh the open issue plan after PR #356, close completed reliability issues,
implement the next generated-output quality work, and keep repository context
aligned before continuing the wave.

## Thought Process

Treat generated-output work as a sequence under epic #342. Reliability work
from #351-#355 is complete. Manifest truth work from #350 is complete. PR #357
landed broad generated-chat runtime improvements. PR #359 is now open for #343
and #348 and should merge or receive final review before Wave 4 work begins.

## Implementation Plan

- Keep #351-#355 closed as completed by PR #356.
- Keep #350 closed as completed by PR #358.
- Complete PR #359 for Wave 3 #343/#348.
- For #343, preserve canonical graph topology from graph/spec metadata into
  executable notebook code, Mermaid/schema exports, manifests, and QA.
- For #348, keep standalone pattern LLM snippets self-contained while notebook
  composition uses centralized `make_llm(...)` configuration.
- Before working #344-#347 and #349, compare their acceptance criteria against
  merged PR #357 and pending/merged PR #359.

## Progress Tracking

**Overall Status:** In Progress

### Subtasks

| ID | Description | Status | Updated | Notes |
|----|-------------|--------|---------|-------|
| 4.1 | Close completed runtime reliability issues #351-#355 | Complete | 2026-05-20 | Closed as completed with PR #356 and merge commit `7881a0895de78b3de2a5ebce5c911f6699b21a27`. |
| 4.2 | Implement manifest/artifact truth for #350 | Complete | 2026-05-20 | PR #358 merged and #350 is closed. |
| 4.3 | Reconcile generated-chat contract PR #357 with open child issues | Complete | 2026-05-21 | PR #359 folded the #348 config boundary into the #343 branch; remaining Wave 4 issues still need final triage after #359. |
| 4.4 | Implement canonical graph topology preservation for #343 | In Review | 2026-05-21 | PR #359 on `codex/canonical-graph-topology-343`; review threads addressed and resolved. |
| 4.5 | Implement remaining #348 follow-up if still needed | In Review | 2026-05-21 | PR #359 implements the standalone `ChatOpenAI(...)` versus notebook `make_llm(...)` boundary. |

## Progress Log

### 2026-05-20

- Local `main` was synced to `origin/main` at
  `4c4f64090819190fbc859556d18458bf43194a26`, which includes merged PR #357
  and PR #358.
- The live open issue count is 29. Epic #342 remains open with #343-#349 still
  open; #350 is closed.
- Current next implementation target is #343.

### 2026-05-21

- PR #359 is open for canonical graph topology and generated LLM config
  hardening.
- The PR #359 review-fix commit `5922d1e` addressed six review threads:
  architecture-specific finish behavior, END route-key consistency, hybrid
  fallback worker wiring, lowercase node/route function references, and
  duplicate custom `finish_node` prevention.
- Focused verification passed:
  `tests/unit/test_patterns_utils.py tests/unit/test_patterns.py` (96 passed),
  `tests/unit/test_generator_notebook_composer.py tests/unit/test_validators.py`
  (102 passed), and
  `tests/unit/test_generator_agents.py tests/unit/test_generator_nodes_additional.py tests/unit/test_cli_api.py --asyncio-mode=auto`
  (142 passed).
- The post-refresh broad unit gate
  `python -m pytest tests/unit/ --asyncio-mode=auto -q` passed with 622 tests
  and 4 warnings.
