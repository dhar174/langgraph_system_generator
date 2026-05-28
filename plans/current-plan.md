<!-- repo-agent-bootstrap:file-kind=current-plan -->
<!-- repo-agent-bootstrap:provenance=repo-agent-bootstrap@2026-04-16 -->
<!-- repo-agent-bootstrap:managed:start -->
# Current Plan

## Objective
Complete Wave 5 after merged PR #360, focused on the residual LangGraph
pattern/intake issues #60, #63, #64, and #202.

## Scope
Included:
- `plans/current-plan.md`
- `memory-bank/activeContext.md`
- `memory-bank/progress.md`
- `memory-bank/tasks/_index.md`
- `memory-bank/tasks/TASK004-generated-output-quality-wave.md`
- `memory-bank/tasks/TASK005-pattern-intake-modernization-wave.md`
- `src/langgraph_system_generator/patterns/router.py`
- `src/langgraph_system_generator/patterns/subagents.py`
- `src/langgraph_system_generator/patterns/hybrid.py`
- `src/langgraph_system_generator/patterns/critique_loops.py`
- `src/langgraph_system_generator/generator/agents/requirements_analyst.py`
- `src/langgraph_system_generator/generator/nodes.py`
- `src/langgraph_system_generator/api/server.py`

Excluded:
- Reopening #351-#355, #343-#350, or #342; those are completed by merged PRs.
- Direct commits to `main`; Wave 5 work stays on
  `codex/pattern-intake-modernization-wave5`.
- Expanding into #334/#335 runtime outer-agent architecture work or the CYOA
  notebook cluster.

## Plan
1. Keep local `main` synced with `origin/main`.
2. Refresh MemoryBank and plan context for merged PR #360 and closed epic #342.
3. Implement Wave 5 on `codex/pattern-intake-modernization-wave5`:
   - #60: router fallback/general route in RouteDecision literals, prompts,
     generated route nodes, graph wiring, and notebook/stub assembly paths.
   - #63: critique-loop `require_human_approval` support using LangGraph static
     interrupts before `revise`.
   - #64: Send-based subagent map-reduce dispatch with `next_agents` state and
     reducer-backed result accumulation.
   - #202: optional API/intake dialog messages that refine requirements across
     turns while preserving legacy prompt compatibility.
4. Run focused pattern and generator/API gates, then the broad unit suite, diff
   hygiene checks, and exact conflict-marker scan.
5. Open one ready Wave 5 PR that closes #60, #63, #64, and #202 only if tests
   support that claim.

## Validation
- `gh issue list --state open --limit 200 --json number --jq 'length'`
- `gh issue list --state open --limit 200 --json number,title`
- Wave 5 focused gates:
  - `python -m pytest tests/unit/test_patterns.py tests/patterns/test_router.py tests/patterns/test_critique_loops.py -q`
  - `python -m pytest tests/unit/test_generator_agents.py tests/unit/test_generator_nodes.py tests/unit/test_cli_api.py --asyncio-mode=auto -q`
- Final gate: `python -m pytest tests/unit/ --asyncio-mode=auto -q`, `git diff
  --check`, and exact conflict-marker scan.

Current Wave 5 focused verification on
`codex/pattern-intake-modernization-wave5` has passed the pattern gate with 167
tests and the generator/API-node gate with 115 tests. The broad unit gate
passed with 646 tests and 4 warnings. After updating a stale integration
assertion from Command routing to Send fan-out, the full local CI-style gate
`python -m pytest --asyncio-mode=auto -q` passed with 764 passed, 3 skipped,
and 4 warnings.

## Completion criteria
- MemoryBank and plan context reflect PR #360 as merged, #342 as closed, and
  Wave 5 as active.
- Router, critique-loop, subagent, hybrid, API, and intake contracts have
  deterministic tests for the new behavior.
- Wave 5 PR is pushed, ready for review, and linked to #60, #63, #64, and #202.
<!-- repo-agent-bootstrap:managed:end -->
