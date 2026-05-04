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
- Release-readiness packaging smoke coverage now validates the minimal, API,
  and full extras install paths in isolated virtual environments when opted in.
- The local 1.0 release evaluation gate validates deterministic architecture
  selection, graph design, notebook composition, QA/repair, and example
  inventory surfaces without requiring LangSmith upload.
- The release-readiness branch has a green full local verification baseline:
  `python -m pytest --asyncio-mode=auto` reports 625 passed and 4 skipped, and
  the CI fatal-error flake8 gate reports 0 findings.
- Stale completed release-plan issues were closed with evidence, reducing the
  open issue inventory from 49 to 26 while keeping true residual items open.

## What Is Still Incomplete

- Experimental Deep Agents support is opt-in through `agent_type="deepagents"`
  and keeps the optional SDK out of core imports.
- The 1.0 release is not tagged yet; #258 should close through the release PR
  merge, and #256 remains the canonical tracker until `v1.0.0` is published.

## Current Status

- The package metadata in `setup.py` now uses the 1.0.0 Production/Stable
  release baseline on the release-readiness branch.
- The repository already contains substantial scaffolding for CLI, API, RAG,
  notebook export, QA/repair, registry-backed planning, and pattern generation
  workflows.
- Memory Bank documentation is now project-specific context and should be
  maintained alongside public onboarding docs.
- Repository architecture diagrams are discoverable through public docs,
  contributor guidance, and MemoryBank context.
- Release metadata now includes a root MIT license, changelog, and 1.0.0 package
  version/classifier updates on the release-readiness branch.
- The release-readiness branch fixes the Create diagram workflow so it uses a
  configured `GH_PAT` automation token for PR creation and skips cleanly with a
  notice when that secret is unavailable.

## Known Issues and Limitations

- Live mode requires external credentials and can fail if the environment is not
  configured.
- RAG retrieval degrades gracefully to empty context when the vector store is
  unavailable, which keeps generation running but may reduce quality.
- The SSE/job model uses in-memory queues and is not yet designed for
  distributed multi-server coordination.
- Full-extra packaging smoke tests are intentionally opt-in because they install
  the broad notebook/RAG/export dependency set into a fresh virtual
  environment.
- Router fallback/general routing (#60), iterative requirements refinement
  (#202), and the remaining CYOA notebook cell issues are tracked as residual
  follow-up work rather than closed stale items.
