## What Works

- CLI-based generation supports both deterministic stub output and live
  generator-graph execution.
- The FastAPI server exposes synchronous generation, async generation startup,
  health checks, static web UI serving, and SSE progress streaming.
- Architecture selection, graph design, tool planning, notebook composition,
  and QA/repair now expose typed feedback and warning surfaces in manifests and
  API results.
- Pattern generators and examples cover router, subagents, hybrid, autoagent,
  experimental deepagents, critique-revise, and advanced example-only workflows.
- Notebook composition, dependency planning, runtime validation, deterministic
  repair, rollback reporting, and export helpers are present.
- Maintainer repository visualizations are checked in under `docs/diagrams/`,
  including the generator stage/state map and the generated
  repo-architecture-visualizer package/module/env bundle.

## What Is Still Incomplete

- Public docs and onboarding copy have historically lagged behind the runtime
  contract and should be kept synchronized with CLI/API behavior.
- Experimental Deep Agents support is opt-in through `agent_type="deepagents"`
  and keeps the optional SDK out of core imports.

## Current Status

- The package metadata in `setup.py` marks the project as alpha.
- The repository already contains substantial scaffolding for CLI, API, RAG,
  notebook export, QA/repair, registry-backed planning, and pattern generation
  workflows.
- Memory Bank documentation is now project-specific context and should be
  maintained alongside public onboarding docs.
- Repository architecture diagrams are discoverable through public docs,
  contributor guidance, and MemoryBank context.

## Known Issues and Limitations

- Live mode requires external credentials and can fail if the environment is not
  configured.
- RAG retrieval degrades gracefully to empty context when the vector store is
  unavailable, which keeps generation running but may reduce quality.
- The SSE/job model uses in-memory queues and is not yet designed for
  distributed multi-server coordination.
