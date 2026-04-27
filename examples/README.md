# LangGraph Pattern Examples

`examples/` is a runnable pattern library, not an application-usage demo folder. Each Python script has a paired notebook and defaults to `--mode stub` so the workflows run offline without credentials.

## Setup

Use Python `3.10+`.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```

Live mode requires `OPENAI_API_KEY`:

```bash
export OPENAI_API_KEY="sk-..."  # Linux/macOS (bash/zsh)
$env:OPENAI_API_KEY="sk-..."    # Windows (PowerShell)
python examples/router_pattern_example.py --mode live
```

For notebooks, set `OPENAI_API_KEY` in the Jupyter or Colab kernel environment
before switching `MODE` to `live`.

Stub mode is the default for every script and notebook:

```bash
python examples/router_pattern_example.py --mode stub
```

## Pattern Index

| Pattern | Python | Notebook | Latency | Cost | Complexity | Best For |
| --- | --- | --- | --- | --- | --- | --- |
| Router | `router_pattern_example.py` | `router_pattern_example.ipynb` | Low | Low | Low | One-shot delegation to a single specialist |
| Subagents | `subagents_pattern_example.py` | `subagents_pattern_example.ipynb` | Medium | Medium | Medium | Sequential collaboration across specialists |
| Deep Agents (Experimental) | `deepagents_pattern_example.py` | `deepagents_pattern_example.ipynb` | Medium | Medium | Medium-High | Opt-in Deep Agents SDK harness with planning and optional subagents |
| Critique-Revise | `critique_revise_pattern_example.py` | `critique_revise_pattern_example.ipynb` | Medium | Medium-High | Medium | Iterative quality improvement with bounded retries |
| Hierarchical Teams | `hierarchical_teams_example.py` | `hierarchical_teams_example.ipynb` | Medium-High | Medium-High | High | Team-of-teams workflows and nested supervision |
| Plan-and-Execute | `planning_and_execute_example.py` | `planning_and_execute_example.ipynb` | Medium | Medium | Medium | Separate planning from execution and trace each step |
| REWOO-Style Speculation | `rewoo_example.py` | `rewoo_example.ipynb` | Medium | Medium | High | Predict tool outputs first, reconcile later |
| Human Approval / HITL | `human_approval_pattern.py` | `human_approval_pattern.ipynb` | Human-bound | Low-Medium | Medium | Sensitive actions requiring approve/edit/reject gates |
| LLM-as-a-Judge | `llm_judge_example.py` | `llm_judge_example.ipynb` | Medium | Medium | Medium | Rubric-based scoring and explicit quality gates |
| LLMCompiler-Style Execution | `llm_compiler_example.py` | `llm_compiler_example.ipynb` | Medium | Medium | High | Dependency-graph planning with parallelizable subtasks |

## Pattern Selection Matrix

| Situation | Prefer | Why |
| --- | --- | --- |
| The request should go to exactly one specialist | Router | Lowest-latency delegation with minimal graph overhead |
| Specialists must build on prior outputs | Subagents | Supervisor can sequence work and preserve shared context |
| You want the Deep Agents SDK harness explicitly | Deep Agents (Experimental) | Adds SDK-native planning, optional subagents, and lazy live execution while preserving offline stub behavior |
| A single answer needs iterative refinement | Critique-Revise | Quality improves through explicit critique and revision |
| One supervisor is getting overloaded | Hierarchical Teams | Split responsibilities into nested teams with a top-level coordinator |
| Planning quality and execution quality should be tuned separately | Plan-and-Execute | Lets planner and executor use different prompts or models |
| You want to speculate before paying for real tool observations | REWOO-Style Speculation | Surfaces consistency-vs-latency trade-offs clearly |
| A tool/action is sensitive or externally visible | Human Approval / HITL | Interrupts provide pause, edit, approve, and reject flows |
| You need explicit rubric scores or ship/no-ship decisions | LLM-as-a-Judge | Produces auditable structured evaluation output |
| Independent subtasks can run in parallel before synthesis | LLMCompiler-Style Execution | Dependency graph plus `Send` fan-out improves throughput |

## JS Parity References

These links point to current official JavaScript docs or closest first-party primitives. Some advanced patterns do not have a one-to-one JS cookbook yet; in those cases the parity link points to the official building blocks used to implement the pattern.

| Pattern | Closest Official JS Reference |
| --- | --- |
| Router | [LangChain JS multi-agent router](https://docs.langchain.com/oss/javascript/langchain/multi-agent/router) |
| Subagents | [LangChain JS multi-agent subagents](https://docs.langchain.com/oss/javascript/langchain/multi-agent/subagents) |
| Critique-Revise | [LangGraph JS graph API](https://docs.langchain.com/oss/javascript/langgraph/graph-api) |
| Hierarchical Teams | [LangGraph JS subgraphs](https://docs.langchain.com/oss/javascript/langgraph/use-subgraphs) |
| Plan-and-Execute | [Thinking in LangGraph (JS)](https://docs.langchain.com/oss/javascript/langgraph/thinking-in-langgraph) |
| REWOO-Style Speculation | [LangGraph JS graph API](https://docs.langchain.com/oss/javascript/langgraph/graph-api) |
| Human Approval / HITL | [LangGraph JS interrupts](https://docs.langchain.com/oss/javascript/langgraph/interrupts) and [LangChain JS human-in-the-loop](https://docs.langchain.com/oss/javascript/langchain/human-in-the-loop) |
| LLM-as-a-Judge | [Evaluate a graph in LangSmith](https://docs.langchain.com/langsmith/evaluate-graph) |
| LLMCompiler-Style Execution | [LangGraph JS use-graph-api / Send](https://docs.langchain.com/oss/javascript/langgraph/use-graph-api) |

## Benchmark

Use [benchmark_critique_vs_judge.ipynb](./benchmark_critique_vs_judge.ipynb) with the checked-in fixture [benchmark_critique_vs_judge_fixture.json](./benchmark_critique_vs_judge_fixture.json) to compare token cost, latency, and rubric quality for Critique-Revise vs LLM-as-a-Judge.

- Stub mode loads the checked-in fixture and renders the comparison offline.
- Live runs should record the model name, date, prompt/completion token counts, latency, and pricing assumptions used for any refreshed results.

## Notes

- The public generator-backed patterns include `RouterPattern`,
  `SubagentsPattern`, `HybridPattern`, `AutoAgentPattern`, `DeepAgentsPattern`,
  and `CritiqueLoopPattern` under `src/langgraph_system_generator/patterns/`.
- The advanced assets in this folder are example-only references for current LangGraph design patterns; they are intentionally not exported as new public code-generation classes in `src/`.
- The Deep Agents example is experimental and generator-backed, but keeps
  `deepagents` optional by importing `create_deep_agent(...)` only inside the
  live harness builder.
- The plan-and-execute example exposes `--planner-model` and `--executor-model`
  for live runs, and the paired notebook mirrors those controls with
  `PLANNER_MODEL` and `EXECUTOR_MODEL`.
