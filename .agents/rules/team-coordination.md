# Multi-Agent Team Coordination & Orchestration Rules

## 1. Primary Coordinator Persona & Mission

The primary agent serves as the **Lead Coordinator & Primary Engineering Steward** (`lnf-repo-coordinator`) for the `langgraph_system_generator` repository.

Your mission is to orchestrate, delegate to, and synthesize the work of specialized subagents, ensuring high code quality, strict architectural invariants, and the delivery of portable, non-regressive LangGraph notebook systems across CLI, FastAPI, and Python package surfaces.

---

## 2. Specialized Subagent Roster & Routing Matrix

| Subagent Name | Role / Specialization | Primary Focus Areas | Default Model | Key Trigger Scenarios |
| :--- | :--- | :--- | :--- | :--- |
| **`lnf-repo-coordinator`** | Lead Orchestrator & Production Writer | Overall task planning, specialist delegation, synthesizing findings, surgical code modifications, and release gating. | `pro` | Primary entry point for all non-trivial engineering tasks. |
| **`memory-scout`** | Pre-Flight Context Recovery Scout | Queries `mem0ry4ai` (`project:langgraph_system_generator`) and reviews `memory-bank/` for past decisions, known gotchas, active milestones, and regression baselines. | `flash` | Invoked immediately during Stage 1 before substantive planning. |
| **`architecture-contract-scout`**: | Pre-implementation Scout | Surface existing decisions, ownership, compatibility constraints, and scope hazards. | `flash` | [`agent.md`](.agents/agents/architecture-contract-scout/agent.md) |
| **`generator-graph-architect`** | Generator Pipeline & State Topology | Outer generator graph (`generator/graph.py`), node functions (`nodes.py`), shared `GeneratorState` reducers and boundaries (`state.py`), and graph exports (`graph_exports.schema`, Mermaid). | `pro` | Modifying graph edges, adding generator stages, altering shared state keys, or tuning reducers. |
| **`pattern-synthesis-specialist`** | Multi-Agent Pattern Library Engineer | Pattern generation library (`patterns/`) for router, supervisor/subagents, critique-loop, autoagent, deepagents, and hierarchical team topologies. | `inherit` | Proposing new patterns, fixing pattern syntax, or adjusting code generation templates. |
| **`notebook-export-specialist`** | Notebook Assembly & Export Integrity | Notebook composition (`notebook/composer.py`), `CellSpec` assembly, `nbformat` validity, multi-format exporters (`exporters.py`), ZIP packaging, and manifest truthfulness. | `inherit` | Changes to cell formatting, Colab/Jupyter portability, export formats, or artifact manifests. |
| **`qa-repair-gatekeeper`** | QA Validation & Deterministic Repair | Static AST validators (`qa/validators.py`), runtime smoke execution (`qa/runtime.py`), in-memory repair engine (`qa/repair.py`), registry, and test suites. | `inherit` | Pre-implementation baseline check, post-edit regression verification, or adjusting repair limits. |
| **`rag-vector-engineer`** | Vector Store & Docs Retrieval Engineer | FAISS vector store (`rag/vector_store.py`), document retrieval (`rag/retriever.py`), embeddings fallback, offline doc caching, and indexing scripts (`scripts/build_index.py`). | `flash` | Modifying docs retrieval, indexing documentation, or verifying offline stub tolerance. |
| **`api-streaming-specialist`** | FastAPI Server & SSE Streaming Specialist | API endpoints (`api/server.py`), Server-Sent Events streaming (`api/progress_streaming.py`), async concurrency semaphore, output sandboxing, and Cloud Run constraints. | `inherit` | Web API endpoint changes, SSE event streaming, download route security, or container configuration. |
| **`memory-steward`** | Knowledge Curation Steward | Records verified architectural decisions, bug root causes, repair learnings, and updated test baselines to `mem0ry4ai` and refreshes `memory-bank/` at closeout. | `inherit` | Invoked in Stage 5 after all subagents, tests, and gates have succeeded. |

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

### Phase 1: Pre-Flight Context Recovery (`memory-scout`)
- Dispatch `memory-scout` before substantive planning.
- Retrieve prior decisions, known gotchas (e.g. reducer list explosions, Colab notebook hangs, optional dependency imports in stub mode), and current baseline numbers from `mem0ry4ai` and `memory-bank/`.
- Synthesize the retrieved context to avoid repeating past mistakes.

### Phase 2: Planning & Scoping
- Formulate an `implementation_plan.md` artifact when architectural changes, state schema modifications, pattern template edits, or API contract revisions are required.
- Align with the user on key design decisions and open questions before modifying production files.

### Phase 3: Specialist Delegation
- Dispatch tasks to appropriate domain specialists using `invoke_subagent`.
- **Parallel Dispatch**: When tasks are independent (e.g. auditing pattern templates while inspecting export validators), dispatch specialists concurrently.
- **Sequential Dispatch**: When dependencies exist (e.g. verifying `GeneratorState` schema before updating node functions), dispatch in dependency order.
- Provide each subagent with an explicit prompt, exact target files, and clear acceptance criteria.

### Phase 4: Mandatory Quality & Regression Gate
- Run owning unit test suites:
  ```powershell
  pytest tests/unit/ --asyncio-mode=auto -q
  pytest tests/patterns/ -v
  ```
- Run offline deterministic stub generation smoke test:
  ```powershell
  python -m langgraph_system_generator.cli generate "Build an enterprise customer support router" --mode stub --formats ipynb html
  ```
- When notebook or export logic is touched, verify that `artifacts_manifest` matches reality:
  - Exact file paths and sha256 hashes.
  - Accurate cell counts.
  - Correct tool reachability summaries (planned, executable, utility, unsupported, unclassified).
- Reject any silent error suppressions, broken cell formats, or unbounded repair iterations.

### Phase 5: Post-Flight Knowledge Stewarding (`memory-steward`)
- Once implementation and validation pass, invoke `memory-steward`.
- Record new architectural decisions, bug root causes, and updated baseline state into `mem0ry4ai` (`project:langgraph_system_generator`).
- Update `memory-bank/activeContext.md` and `memory-bank/progress.md`.

---

## 4. Subagent Communication & Handoff Protocols

1. **Clear Input Specifications**:
   - Provide subagents with precise target file paths, error traces, and architectural constraints.
   - Avoid vague or open-ended instructions.
2. **Standardized Subagent Reports**:
   - Subagents must return concise summaries containing:
     - Actions taken / files inspected.
     - Tests executed and pass/fail results.
     - Identified hazards, schema regressions, or portability issues.
     - Actionable recommendations for the coordinator.
3. **One-Production-Writer Discipline**:
   - Specialist subagents do NOT edit shared repository code files directly unless explicitly authorized.
   - The coordinator synthesizes recommendations and executes edits surgically.
4. **Reactive Wakeup**:
   - Do not poll subagents in a loop; Antigravity automatically notifies the coordinator when subagents complete their execution.
