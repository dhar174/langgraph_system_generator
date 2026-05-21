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
landed broad generated-chat runtime improvements. PR #359 merged #343/#348, so
Wave 4 is now active for #344, #345, #346, #347, and #349.

## Implementation Plan

- Keep #351-#355 closed as completed by PR #356.
- Keep #350 closed as completed by PR #358.
- Keep #343/#348 closed as completed by PR #359.
- Complete Wave 4 on `codex/chatbot-fidelity-wave4` without duplicating PR #357
  or PR #359 behavior.
- For #344, make verifier/reviser generated loops operational through canonical
  draft, safety, revision, route, and bounded retry fields.
- For #345/#347, keep chatbot execution helpers non-blocking by default while
  preserving character selection, repeatable same-thread turns, and typed
  persona/chat memory writes.
- For #346, use `graph_exports.schema.tool_reachability` as the execution
  contract and expose a manifest `tool_contract_summary`.
- For #349, strengthen deterministic QA for chat loops, character gates, memory
  writers, fake tool wiring, terminal verifier loops, and
  chatbot/historical/persona domain alignment.

## Progress Tracking

**Overall Status:** In Progress

### Subtasks

| ID | Description | Status | Updated | Notes |
|----|-------------|--------|---------|-------|
| 4.1 | Close completed runtime reliability issues #351-#355 | Complete | 2026-05-20 | Closed as completed with PR #356 and merge commit `7881a0895de78b3de2a5ebce5c911f6699b21a27`. |
| 4.2 | Implement manifest/artifact truth for #350 | Complete | 2026-05-20 | PR #358 merged and #350 is closed. |
| 4.3 | Reconcile generated-chat contract PR #357 with open child issues | Complete | 2026-05-21 | PR #359 folded the #348 config boundary into the #343 branch; remaining Wave 4 issues still need final triage after #359. |
| 4.4 | Implement canonical graph topology preservation for #343 | Complete | 2026-05-21 | PR #359 merged at `d851008ffc5e6ca289c666c5b1c0564b2282f32f`. |
| 4.5 | Implement remaining #348 follow-up if still needed | Complete | 2026-05-21 | PR #359 implements the standalone `ChatOpenAI(...)` versus notebook `make_llm(...)` boundary. |
| 4.6 | Implement generated chatbot Wave 4 for #344/#345/#346/#347/#349 | In Progress | 2026-05-21 | Branch `codex/chatbot-fidelity-wave4`; focused slices, broad unit gate, and headed/live UI artifact gate are passing. |

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
- PR #359 merged at `d851008ffc5e6ca289c666c5b1c0564b2282f32f`, closing
  #343/#348.
- Wave 4 started from updated `main` on `codex/chatbot-fidelity-wave4`.
- Implemented Wave 4 hardening for non-blocking chatbot helpers, same-thread
  demo turns, canonical verifier/reviser state writes, persona/memory writes,
  additive `tool_contract_summary` manifests, unwired ToolNode detection,
  declared-memory-field writer checks, terminal verifier loop checks, and
  chatbot/historical/persona domain cues.
- Focused verification passed:
  `tests/unit/test_generator_notebook_composer.py tests/unit/test_validators.py`
  (111 passed),
  `tests/unit/test_generator_agents.py tests/unit/test_generator_nodes_additional.py tests/unit/test_cli_api.py --asyncio-mode=auto`
  (143 passed), and
  `tests/unit/test_patterns.py tests/unit/test_patterns_utils.py` (98 passed).
- Broad Wave 4 verification passed:
  `python -m pytest tests/unit/ --asyncio-mode=auto -q` with 634 passed and 4
  warnings.
- Headed/live web UI verification passed with `gpt-5.4-mini` to
  `./output/wave4-live-chatbot`: notebook, HTML, and manifest downloads worked,
  no browser console/page errors were observed, and the manifest reported
  advisory-only QA with zero blocking issues.
