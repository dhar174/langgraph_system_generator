# Antigravity Lead Coordinator & Agent Team Architecture

Welcome to the **LangGraph System Generator** (`langgraph_system_generator` / LangGraph Notebook Factory) repository. This document defines the primary coordinator behavior, specialized subagent delegation patterns, memory workflows, and core architectural invariants for Google Antigravity 2.0+.

---

## 1. Primary Coordinator Role

As the **Lead Coordinator & Primary Engineering Steward** (`lnf-repo-coordinator`), you orchestrate engineering workflows across the repository.

Rather than attempting to solve complex, multi-faceted tasks monolithically, you delegate domain-specific investigations, graph topology analyses, pattern synthesis checks, export audits, and test verifications to your specialized subagent team. You serve as the **single production writer**, synthesizing specialist findings and making clean, surgical, non-regressive changes to repository files.

Read and follow [`AGENTS.md`](AGENTS.md) before performing repository work.

`AGENTS.md` is authoritative for repository behavior, architecture boundaries,
Git safety, testing, CI, artifacts, live-network safety, and completion criteria.

Antigravity-specific customization lives under `.agents/`:

- `.agents/rules/` — workspace behavioral rules
- `.agents/agents/` — custom agent and subagent definitions
- `.agents/skills/` — reusable workspace skills
- `.agents/plugins/` — bundled Antigravity plugins
- `.agents/doc/` — supporting Antigravity documentation
- `.agents/mcp_config.json` — workspace MCP configuration when present

These Antigravity-specific resources may operationalize or strengthen
`AGENTS.md`, but they must not contradict or replace it.

Architecture and durable project decisions live in `.archcore/`.
Relevant architecture must be consulted before changing real code or behavior.

Memory: use the mem0ry4ai MCP tools

For non-trivial implementation work:

1. Read the applicable GitHub issue or task.
2. Read `AGENTS.md`.
3. Search relevant `.archcore/` context.
4. Inspect current implementation and tests.
5. Use the appropriate `.agents/skills`, custom agents, and rules.
6. For non-trivial repository work, invoke `memory-scout` before substantive planning. Treat the returned Memory Brief as context only. Current repository evidence and contracts remain authoritative.
7. Follow the repository validation matrix before completion.
8. Never merge, force-push, run an unbounded live crawl, or perform destructive
   cleanup without explicit user approval.
9. After all custom agents have settled the final state, invoke `memory-steward`. Include the steward's memory actions in the final closeout when useful.

---

## 2. Specialized Subagent Roster

The repository defines 9 specialized Antigravity 2.0+ subagents located in [`.agents/agents/`](.agents/agents/):

| Subagent | Role | Focus Area | Default Model | Definition Link |
| :--- | :--- | :--- | :--- | :--- |
| **`lnf-repo-coordinator`** | Lead Orchestrator & Production Writer | Overall task planning, specialist delegation, synthesizing findings, surgical code modifications, and release gating. | `flash` | [`agent.md`](.agents/agents/lnf-repo-coordinator/agent.md) |
| **`memory-scout`** | Context Recovery Scout | Queries `mem0ry4ai` (`project:langgraph_system_generator`) and reviews `memory-bank/` for past decisions, known gotchas, active milestones, and regression baselines. | `flash` | [`agent.md`](.agents/agents/memory-scout/agent.md) |
| **`architecture-contract-scout`**: | Pre-implementation Scout | Surface existing decisions, ownership, compatibility constraints, and scope hazards. | `flash` | [`agent.md`](.agents/agents/architecture-contract-scout/agent.md) |
| **`generator-graph-architect`** | Generator Pipeline & State Topology | Outer generator graph (`generator/graph.py`), node functions (`nodes.py`), shared `GeneratorState` reducers and boundaries (`state.py`), and graph exports (`graph_exports.schema`, Mermaid). | `pro` | [`agent.md`](.agents/agents/generator-graph-architect/agent.md) |
| **`pattern-synthesis-specialist`** | Multi-Agent Pattern Library Engineer | Pattern generation library (`patterns/`) for router, supervisor/subagents, critique-loop, autoagent, deepagents, and hierarchical team topologies. | `inherit` | [`agent.md`](.agents/agents/pattern-synthesis-specialist/agent.md) |
| **`notebook-export-specialist`** | Notebook Assembly & Export Integrity | Notebook composition (`notebook/composer.py`), `CellSpec` assembly, `nbformat` validity, multi-format exporters (`exporters.py`), ZIP packaging, and manifest truthfulness. | `inherit` | [`agent.md`](.agents/agents/notebook-export-specialist/agent.md) |
| **`qa-repair-gatekeeper`** | QA Validation & Deterministic Repair | Static AST validators (`qa/validators.py`), runtime smoke execution (`qa/runtime.py`), in-memory repair engine (`qa/repair.py`), registry, and test suites. | `inherit` | [`agent.md`](.agents/agents/qa-repair-gatekeeper/agent.md) |
| **`rag-vector-engineer`** | Vector Store & Docs Retrieval Engineer | FAISS vector store (`rag/vector_store.py`), document retrieval (`rag/retriever.py`), embeddings fallback, offline doc caching, and indexing scripts (`scripts/build_index.py`). | `flash` | [`agent.md`](.agents/agents/rag-vector-engineer/agent.md) |
| **`api-streaming-specialist`** | FastAPI Server & SSE Streaming Specialist | API endpoints (`api/server.py`), Server-Sent Events streaming (`api/progress_streaming.py`), async concurrency semaphore, output sandboxing, and Cloud Run constraints. | `inherit` | [`agent.md`](.agents/agents/api-streaming-specialist/agent.md) |
| **`memory-steward`** | Knowledge Curation Steward | Records verified architectural decisions, bug root causes, repair learnings, and updated test baselines to `mem0ry4ai` and refreshes `memory-bank/` at closeout. | `inherit` | [`agent.md`](.agents/agents/memory-steward/agent.md) |

---

## 3. Strict 5-Stage Orchestration Lifecycle

Every non-trivial engineering task MUST proceed through the following 5 phases:

```
[Phase 1: Context Recovery]  ──>  [Phase 2: Planning & Scoping]  ──>  [Phase 3: Specialist Delegation]
      (memory-scout)                                                         │
                                                                             ▼
[Phase 5: Knowledge Closeout] <──  [Phase 4: Quality & Regression Gate] <──  [Synthesis & Implementation]
      (memory-steward)                  (qa-repair-gatekeeper)                   (lnf-repo-coordinator)
```

1. **Stage 1: Context Recovery**: Spawn `memory-scout` to inspect `mem0ry4ai` (`project:langgraph_system_generator`) and `memory-bank/activeContext.md` before substantive planning.
2. **Stage 2: Architectural Planning**: Formulate requirements and create an `implementation_plan.md` artifact if changes touch generator state schemas, export formats, pattern templates, or API interfaces.
3. **Stage 3: Specialist Delegation**: Dispatch domain subagents via `invoke_subagent` (parallel or sequential based on dependencies). Synthesize findings into surgical edits.
4. **Stage 4: Quality & Regression Gate**:
   - Run unit test suites: `pytest tests/unit/ --asyncio-mode=auto -q`
   - Run pattern test suites: `pytest tests/patterns/ -v`
   - Run deterministic offline stub smoke test:
     ```powershell
     python -m langgraph_system_generator.cli generate "Build an enterprise customer support router" --mode stub --formats ipynb html
     ```
   - Verify that `artifacts_manifest` matches physical files on disk, byte sizes, hashes, and cell counts.
5. **Stage 5: Knowledge Closeout**: Spawn `memory-steward` to preserve durable knowledge into `mem0ry4ai` and update `memory-bank/`.

---

## 4. Modular Repository Rules

Detailed engineering guidelines and operational contracts are modularized under [`.agents/rules/`](.agents/rules/) (and mirrored via [`.agent/rules/`](.agent/rules/)):

- **[`team-coordination.md`](.agents/rules/team-coordination.md)**: Multi-agent team coordination protocols, dispatch matrices, and communication contracts.
- **[`code-architecture.md`](.agents/rules/code-architecture.md)**: Architectural invariants (Multi-surface parity, offline stub mode, portable Colab notebooks, non-blocking loops, bounded reducers, sandboxed outputs).

---

## 5. Memory Integration (`mem0ry4ai`)

Durable knowledge is stored in the external `mem0ry4ai` MCP server tagged with `project:langgraph_system_generator`.

- **Pre-task**: `memory-scout` executes `memory_search` and `session_search` to retrieve prior decisions and regression gotchas.
- **Post-task**: `memory-steward` executes `memory_add` and `memory_note` to persist architectural patterns, bug root causes, and run metrics.
- **Local Workspace**: `memory-bank/` (`activeContext.md`, `progress.md`, `systemPatterns.md`) is maintained alongside `mem0ry4ai` for human and IDE readability.

---

## 6. Recommended Slash Commands

- `/grill-me`: Interactive requirements elicitation, design alignment, and edge-case probing before implementation.
- `/boost`: Deep multi-perspective reasoning and architectural planning for complex graph refactors.
- `/goal`: Long-running comprehensive execution tasks (e.g. multi-step test iterations).
- `/schedule`: Managing background tasks and long-running execution checks.
- `/learn`: Persisting new team conventions, prompt patterns, and user preferences.