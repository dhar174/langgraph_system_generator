# Antigravity Agent Team

This repository defines workspace-scoped Google Antigravity 2.0 custom agents under `.agents/agents/<name>/agent.md`.

The team follows the repository's existing operating contract rather than creating a parallel source of truth. Every agent starts from `AGENTS.md`; architecture and contract decisions remain in `.archcore/`, detailed production-refactor requirements remain in `.claude/specs/production-notebook-refactor/`, and execution evidence remains in the documented work records.

## Team Shape

- **`lnf-repo-coordinator`**: primary selectable agent and single production writer and subagent coordinator. Plans work, integrates changes, delegates investigation/review, and owns final synthesis.
- **`memory-scout`**: read-only pre-task durable-context retrieval scout to be called immediately after coordinator/repo-steward intake.
- **`architecture-contract-scout`**: read-only pre-implementation scout for existing decisions, ownership, compatibility constraints, and scope hazards.
- **`generator-graph-architect`** | Generator Pipeline & State Topology | Outer generator graph (`generator/graph.py`), node functions (`nodes.py`), shared `GeneratorState` reducers and boundaries (`state.py`), and graph exports (`graph_exports.schema`, Mermaid). | `pro` | [`agent.md`](.agents/agents/generator-graph-architect/agent.md) |
- **`pattern-synthesis-specialist`** | Multi-Agent Pattern Library Engineer | Pattern generation library (`patterns/`) for router, supervisor/subagents, critique-loop, autoagent, deepagents, and hierarchical team topologies. | `inherit` | [`agent.md`](.agents/agents/pattern-synthesis-specialist/agent.md) |
- **`notebook-export-specialist`** | Notebook Assembly & Export Integrity | Notebook composition (`notebook/composer.py`), `CellSpec` assembly, `nbformat` validity, multi-format exporters (`exporters.py`), ZIP packaging, and manifest truthfulness. | `inherit` | [`agent.md`](.agents/agents/notebook-export-specialist/agent.md) |
- **`qa-repair-gatekeeper`** | QA Validation & Deterministic Repair | Static AST validators (`qa/validators.py`), runtime smoke execution (`qa/runtime.py`), in-memory repair engine (`qa/repair.py`), registry, and test suites. | `inherit` | [`agent.md`](.agents/agents/qa-repair-gatekeeper/agent.md) |
- **`rag-vector-engineer`** | Vector Store & Docs Retrieval Engineer | FAISS vector store (`rag/vector_store.py`), document retrieval (`rag/retriever.py`), embeddings fallback, offline doc caching, and indexing scripts (`scripts/build_index.py`). | `flash` | [`agent.md`](.agents/agents/rag-vector-engineer/agent.md) |
- **`api-streaming-specialist`** | FastAPI Server & SSE Streaming Specialist | API endpoints (`api/server.py`), Server-Sent Events streaming (`api/progress_streaming.py`), async concurrency semaphore, output sandboxing, and Cloud Run constraints. | `inherit` | [`agent.md`](.agents/agents/api-streaming-specialist/agent.md) |
- **`memory-steward`**: post-verification durable-memory curation steward that writes memory through mem0ry4ai MCP server tools only, to be run after all other subagents but before closeout by the coordinator/repo-steward.

## One-Writer Rule

The custom team intentionally mirrors the repository's established one-production-writer policy.

Specialist subagents are configured without Antigravity file-write tools. They may inspect code and, where useful, execute sandboxed validation commands, but they should return findings to `backrooms-repo-steward` rather than edit the implementation themselves.

This keeps parallelism focused on independent reasoning instead of concurrent edits to shared production state.

## Suggested Workflow

For a non-trivial feature or refactor:

1. Invoke `memory-scout` before substantive planning. Treat the returned Memory Brief as context only. Current repository evidence and contracts remain authoritative.
2. Start with `lnf-repo-coordinator` as the primary agent.
3. Have the steward dispatch `architecture-contract-scout` before inventing new abstractions.
4. Dispatch the domain specialist that owns the riskiest boundary.
5. Ask `test-designer` for independent contract and adversarial cases before or alongside implementation.
6. Keep production edits with the steward.
7. Ask `release-gatekeeper` for an independent final review.
8. Use `ci-mechanic` when validation or CI failures need diagnosis rather than feature-level reasoning.
9. After all subagents have settled the final state, invoke `memory-steward`. Give Memory Steward:
   - original task;
   - implementation result;
   - reviewer findings and resolutions;
   - test/validator results;
   - documentation/Archcore changes;
   - known unfinished work.
10. Include the steward's memory actions in the final closeout when useful. Trivial tasks may skip the memory checkpoints when prior project context cannot materially affect the result.

Example delegation flow:

```text
User / Task
  -> backrooms-repo-steward
	  -> Memory Scout
      -> architecture-contract-scout
      -> test-designer
      -> artifact-integrity-engineer / web-acquisition-policy-engineer /
         lore-parsing-identity-engineer
      -> implementation by steward
      -> release-gatekeeper
	  -> Memory Steward
```

## Antigravity Discovery

Antigravity 2.0 discovers workspace agents from either `.agents/agents/<name>.md` or `.agents/agents/<name>/agent.md`. This repository uses the directory form so each agent can later gain role-specific supporting material without changing its public identifier.

`backrooms-repo-steward` is configured as a selectable main agent. The other definitions are subagent-only specialists.

## Skills and MCP

When Archcore or AAS Core MCP tools are available, agents should use them according to their prompts. A later change can add validated role-specific AAS skill paths after the catalog selection is reviewed.

## Safety Notes

These agent files do not replace repository permissions or Antigravity's sandbox. The root repository contract still governs live crawling, generated artifacts, secrets, source/license attribution, merging, force-pushing, destructive cleanup, and distribution.
Remember that Memory Scout and Memory Steward are useful bookends, not general-purpose workers. The coordinator shouldn't summon them repeatedly during every little subtask, but should call them before and after non-trivial tasks.
