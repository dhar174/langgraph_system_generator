<!-- repo-agent-bootstrap:file-kind=current-plan -->
<!-- repo-agent-bootstrap:provenance=repo-agent-bootstrap@2026-04-16 -->
<!-- repo-agent-bootstrap:managed:start -->
# Current Plan

## Objective
Complete Wave 4 under generated-output epic #342 after merged PR #359, focused
on the remaining generated chatbot fidelity issues #344, #345, #346, #347, and
#349.

## Scope
Included:
- `plans/current-plan.md`
- `memory-bank/activeContext.md`
- `memory-bank/progress.md`
- `memory-bank/tasks/_index.md`
- `memory-bank/tasks/TASK004-generated-output-quality-wave.md`

Excluded:
- Reopening #351-#355 or #350; those are completed by merged PRs.
- Direct commits to `main`; Wave 4 work stays on
  `codex/chatbot-fidelity-wave4`.
- Rewriting PR #357 or PR #359 behavior where the current code already has a
  working generated-chat or canonical-graph contract.

## Plan
1. Keep local `main` synced with `origin/main`.
2. Refresh MemoryBank and plan context for merged PR #356, PR #358, and PR
   #357, plus merged PR #359 for #343/#348.
3. Implement Wave 4 on `codex/chatbot-fidelity-wave4`:
   - #344: operational bounded verifier/reviser routing and structured fields.
   - #345/#347: non-blocking chatbot helpers, character selection, same-thread
     repeated turns, and typed persona/chat memory writes.
   - #346: executable tool claims tied to graph `tool_reachability`, with a
     manifest `tool_contract_summary` for planned/executable/utility/unsupported
     tools.
   - #349: deterministic QA for chat loops, character gates, memory writers,
     verifier loops, tool wiring, and chatbot/historical/persona domain drift.
4. Run focused unit gates, then the broad unit suite, diff hygiene checks, and
   the headed/live web UI gate with `gpt-5.4-mini` when credentials are
   available.
5. Open one ready Wave 4 PR that closes #344, #345, #346, #347, and #349 only
   if tests and live artifact checks support that claim.

## Validation
- `gh issue list --state open --limit 200 --json number --jq 'length'`
- `gh issue list --state open --limit 200 --json number,title`
- Wave 4 focused gates:
  - `python -m pytest tests/unit/test_generator_notebook_composer.py tests/unit/test_validators.py -q`
  - `python -m pytest tests/unit/test_generator_agents.py tests/unit/test_generator_nodes_additional.py tests/unit/test_cli_api.py --asyncio-mode=auto -q`
  - `python -m pytest tests/unit/test_patterns.py tests/unit/test_patterns_utils.py -q`
- Final gate: `python -m pytest tests/unit/ --asyncio-mode=auto -q`, `git diff
  --check`, exact conflict-marker scan, and headed/live UI artifact validation
  when `OPENAI_API_KEY` is available.

Current Wave 4 verification on `codex/chatbot-fidelity-wave4` has passed the
focused gates with 111 composer/validator tests, 143 generator/API-node tests,
and 98 pattern tests. The broad unit gate passed with 634 tests and 4 warnings.
The headed/live web UI gate used `gpt-5.4-mini` to generate
`./output/wave4-live-chatbot`; downloads for notebook, HTML, and manifest
worked, no browser errors were reported, and the manifest ended with advisory
QA only and zero blocking issues.

## Completion criteria
- MemoryBank and plan context reflect PR #359 as merged and Wave 4 as active.
- Generated chatbot notebooks do not block top-to-bottom execution by default.
- Verifier/reviser, memory, tool reachability, and prompt-faithfulness QA have
  deterministic coverage.
- Wave 4 PR is pushed, ready for review, and linked to #344, #345, #346, #347,
  and #349.
<!-- repo-agent-bootstrap:managed:end -->
