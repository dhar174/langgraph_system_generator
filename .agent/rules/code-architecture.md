# Repository Architecture Invariants & Standards

## 1. Multi-Surface Parity
The core generation workflow is shared across:
- **CLI**: `lnf generate`, `lnf build-index` (`src/langgraph_system_generator/cli.py`)
- **FastAPI / Web UI**: `src/langgraph_system_generator/api/server.py`
- **Python Library**: `src/langgraph_system_generator/generator/`

All changes to the generation pipeline must maintain behavioral parity and contract consistency across all three surfaces.

---

## 2. Offline Stub Mode Invariant
- Deterministic offline stub generation (`--stub`) must NEVER depend on live network connections, external OpenAI/Anthropic/Google API keys, or remote services.
- FAISS vector database failures must degrade gracefully to an empty documentation context without throwing unhandled exceptions.
- Core package imports must never fail due to missing optional dependencies (e.g. `deepagents`, `weasyprint`).

---

## 3. Notebook Portability & Safety Invariants
- **Local & Colab Compatibility**: Emitted notebooks must be valid `nbformat` v4 documents runnable in VS Code, JupyterLab, and Google Colab.
- **Non-Blocking Default**: Interactive input loops (e.g. `input(...)` loops) must be gated by `if RUN_INTERACTIVE_LOOP:`, defaulting to `False`. Test and automated runs must execute cleanly top-to-bottom via `chat_once(...)` helpers.
- **Centralized LLM Scoping**: Composed notebooks must centralize model creation via a `make_llm(...)` helper function in early setup cells (`use_notebook_helper=True`).

---

## 4. State Management & Reducer Discipline
- Reducers on `GeneratorState` (`src/langgraph_system_generator/generator/state.py`) must be bounded:
  - `constraints` and `docs_context`: bounded, latest-unique reducers.
  - Advisory metadata (`requirements_feedback`, `architecture_feedback`, `graph_design_feedback`, `tool_planning_feedback`, `notebook_composition_feedback`): carried without overriding core pipeline state.
  - Node functions must return partial state dictionaries, never mutated global state or full state overwrites.

---

## 5. Bounded Repair & QA Verification
- Automated repair loops are strictly capped by `settings.max_repair_attempts` (default: 3).
- In-memory candidate validation: Repairs must be tested against static AST validators before persisting. Regressive modifications must be rejected with rollbacks recorded in `qa_history`.

---

## 6. Output Sandboxing & Security
- Production output directory resolution (`LNF_OUTPUT_BASE`) must remain strictly within the user's workspace directory.
- Download endpoints must strictly sanitize file paths against directory traversal attacks (`../`).
