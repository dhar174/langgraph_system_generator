## System Architecture

- The package is organized around a LangGraph-based outer generator workflow in `src/langgraph_system_generator/generator/graph.py`.
- That workflow uses a typed shared state defined in `src/langgraph_system_generator/generator/state.py` and moves through a fixed pipeline of intake, retrieval, architecture selection, workflow design, tooling planning, notebook assembly, QA, optional repair, and packaging.
- The CLI (`src/langgraph_system_generator/cli.py`) is the main orchestration entry point for local generation and exposes both `stub` mode and `live` mode.
- The FastAPI layer (`src/langgraph_system_generator/api/server.py`) wraps the same generation flow for web/API access and adds SSE-based progress streaming.

## Key Technical Decisions

- The generator uses an outer orchestration graph plus inner code-generation helpers, rather than generating an entire system in one step.
- Shared workflow data is modeled with Pydantic models plus a `TypedDict` generator state so agents, nodes, QA, and packaging use consistent structures.
- RAG retrieval is optional and failure-tolerant: if the FAISS/OpenAI-backed vector store cannot load, the graph continues with empty documentation context instead of aborting generation.
- QA is split into static validation and a bounded repair loop. Repair attempts are capped by `settings.max_repair_attempts`.
- The API layer constrains untrusted output paths to a trusted base directory and limits concurrent async jobs with a semaphore.

## Design Patterns in Use

- **Outer generator graph:** `create_generator_graph()` composes named LangGraph nodes with conditional edges for repair/retry behavior.
- **Agent-per-step decomposition:** generator nodes delegate LLM work to focused agent classes such as `RequirementsAnalyst`, `ArchitectureSelector`, `GraphDesigner`, `ToolchainEngineer`, and `NotebookComposer`.
- **Pattern code generation library:** `patterns/router.py`,
  `patterns/subagents.py`, and `patterns/critique_loops.py` generate reusable LangGraph workflow code as strings for notebook/content assembly.
- **Notebook-as-artifact assembly:** generated `CellSpec` objects are converted into validated `nbformat` notebooks by `notebook/composer.py`, then exported into multiple formats by `notebook/exporters.py` and related format helpers.
- **Validation/repair loop:** `qa/validators.py` reports notebook issues and `qa/repair.py` applies localized repairs before re-running validation.
- **SSE progress streaming:** `api/progress_streaming.py` uses in-memory queues keyed by job ID to stream progress, logs, completion, and error events.

## Component Relationships

- `generator/graph.py` wires together node functions from `generator/nodes.py`.
- `generator/nodes.py` is the bridge layer between graph state and the
  specialized subsystems:
  - `generator/agents/*` for LLM-driven planning and code generation
  - `rag/*` for retrieval and vector store access
  - `notebook/*` for notebook construction and export
  - `qa/*` for validation and repair
- `cli.py` can run a deterministic offline stub path or invoke the compiled generator graph for live generation.
- `api/server.py` calls the same generation entry points used by the CLI and adds HTTP request validation, output-dir sandboxing, and async progress reporting.
