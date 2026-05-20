# Contributor Asset Audit

This inventory separates contributor-facing Copilot/Codex/Claude assets from
runtime product agents. Runtime generation remains owned by
`src/langgraph_system_generator/generator/agents/` and adjacent `generator/`,
`patterns/`, `qa/`, `notebook/`, and `rag/` modules.

## Inventory snapshot

| Surface | Count | Classification | Decision |
| --- | ---: | --- | --- |
| `.github/agents/*.agent.md` | 76 | Contributor-facing custom agents | Keep as contributor-only collaborators. Do not import these into runtime graph generation. |
| `.github/skills/*/SKILL.md` | 84 | Primary contributor-facing skills | Keep as the main Copilot skill source. Runtime code may align with their guidance, but must not depend on them at execution time. |
| `.codex/skills/*/SKILL.md` | 1 | Codex-local repository skill mirror | Keep for Codex discoverability when it mirrors the repository bootstrap workflow. |
| `.claude/skills/*/SKILL.md` | 3 | Claude-specific contributor skills | Keep provider-specific and contributor-only. Do not treat as runtime generation inputs. |
| `skills/*/SKILL.md` | 15 | Top-level shared skill mirrors | Keep synchronized with matching `.github/skills/` entries. |

## Runtime versus contributor boundary

- Runtime product agents are the Python classes exported from
  `src/langgraph_system_generator/generator/agents/__init__.py`.
- Contributor-facing agents, skills, prompts, and instruction files help humans
  and AI contributors maintain the repository; they are not part of generated
  notebook execution.
- Contributor assets should describe and test the runtime contract, not create a
  parallel runtime-agent implementation.
- LLM-backed runtime code paths should use repository runtime factories such as
  `build_chat_llm()` where applicable; contributor assets can mention model
  usage but must not become hidden runtime configuration.

## LangGraph and LangChain alignment assets

These are the primary LangChain-adjacent skill directories under
`.github/skills/`:

- `agentic-eval`
- `langchain`
- `langgraph-agent-patterns`
- `langgraph-error-handling`
- `langgraph-project-setup`
- `langgraph-state-management`
- `langgraph-testing-evaluation`
- `langsmith-dataset`
- `langsmith-evaluator`
- `langsmith-fetch`
- `langsmith-trace`
- `repo-agent-bootstrap`

The top-level `skills/` mirror currently overlaps these entries:

- `agentic-eval`
- `langchain`
- `langsmith-dataset`
- `langsmith-evaluator`
- `langsmith-trace`
- `repo-agent-bootstrap`

When any mirrored skill changes, update both copies in the same branch or leave a
clear follow-up issue. Do not let mirrored guidance diverge on LangGraph state,
tool execution, or notebook invocation conventions.

## LNF custom agent set

The repository-specific LNF custom agents are:

- `lnf-cli`
- `lnf-docs`
- `lnf-foundation`
- `lnf-generator`
- `lnf-lead`
- `lnf-notebook`
- `lnf-patterns`
- `lnf-qa`
- `lnf-rag`
- `lnf-security`
- `lnf-webui`

Keep these as contributor-facing maintenance specialists for the CLI, docs,
generator, notebook, pattern, QA, RAG, security, and web UI surfaces. They can
reference the runtime graph/spec contract, but they should hand off
implementation work to the source modules and tests rather than duplicating
logic in prompts.

As of the #322 follow-up after PR #336, the LNF custom agents should no longer
describe the repo as an initial phase-by-phase scaffold. They should point to
the real package paths under `src/langgraph_system_generator/`, preserve the
runtime-versus-contributor boundary, and treat the graph/spec, context-pack,
QA, and notebook invocation contracts as already-established maintenance
contracts.

## Keep/update/remove decisions

| Asset family | Decision | Rationale |
| --- | --- | --- |
| Runtime Python agents | Keep and evolve in source | They are the executable product pipeline. |
| LNF `.github/agents/lnf-*` agents | Keep | They map to repository subsystems and are useful contributor entrypoints. |
| General `.github/agents/` advisors | Keep | They are contributor aids; no runtime coupling needed. |
| LangGraph/LangChain/LangSmith `.github/skills/` | Keep and update | They are the right place to document official-framework conventions. |
| Mirrored `skills/` entries | Keep synchronized | They support non-GitHub skill discovery while preserving one conceptual workflow. |
| `.codex/skills/repo-agent-bootstrap` | Keep | It makes the repo bootstrap workflow available to Codex without changing runtime behavior. |
| `.claude/skills/*` | Keep provider-specific | They support Claude contributors and should stay outside runtime imports. |

## Mirror synchronization notes

- The `.github/skills/langchain/` and `skills/langchain/` copies should carry
  the same current LangChain v1 guidance, including `create_agent(...)`,
  provider integration packages, `langchain-text-splitters`, and legacy API
  cautions.
- Small top-level mirrors such as `langsmith-dataset`,
  `langsmith-evaluator`, `mcp-cli`, `image-manipulation-image-magick`, and
  `refactor` should stay byte-synchronized with their `.github/skills/`
  counterparts in the final tree when either copy changes. If a PR shows a
  one-sided diff because one mirror already had the target content, record a
  mirror hash check in the verification notes.
- `skills/repo-agent-bootstrap/SKILL.md` is a lightweight pointer mirror by
  design. The full runnable repo-local bootstrap skill lives in
  `.github/skills/repo-agent-bootstrap/`, with the Codex-local full mirror in
  `.codex/skills/repo-agent-bootstrap/`.

## Current runtime notebook contract to reflect in contributor assets

Contributor guidance should now describe generated notebooks as using:

- a validated graph/spec contract that records static edges, conditional edges,
  `Command` routes, entry/terminal nodes, guarded cycles, architecture id,
  domain terms, tool reachability metadata, and the compiled graph variable
- explicit reducer semantics for accumulated fields, especially messages
- partial state updates from graph nodes instead of full-state overwrites
- tool claims that match a reachable execution path: deterministic node call,
  `ToolNode`, manual tool loop, `create_agent`, or intentionally
  omitted/demo-only; `create_react_agent` is legacy compatibility and should
  not be the default for new generated notebooks
- invocation examples using `graph` and config shaped like
  `{"configurable": {"thread_id": "lnf-demo-thread"}, "recursion_limit": 25}`
- source metadata from `GenerationContextPack` so manifests, notebooks, and QA
  can explain whether docs came from local LangChain docs, Context7, cached repo
  docs, or fallback retrieval context

