## Current Work Focus

- The repository currently centers on prompt-to-notebook generation with shared
  CLI and FastAPI entry points, plus a reusable LangGraph pattern library.
- Current maintenance work includes keeping the Memory Bank aligned with the
  actual codebase so future sessions do not rely on template placeholders.
- Current documentation work includes the docs-owned
  `docs/diagrams/repo-architecture-visualizer/2026-04-30/` bundle for
  package/module/env relationship snapshots.
- Current release work is preparing the 1.0.0 readiness branch with packaging
  smoke tests, release metadata, local LangGraph evaluation gates, and workflow
  cleanup before opening the final release PR.

## Recent Changes Reflected in the Codebase

- `memory-bank/systemPatterns.md` was updated to document the actual repo
  architecture instead of template bullets.
- The API layer includes guarded output-path resolution and bounded async job
  concurrency.
- Progress streaming exists through SSE with in-memory job queues.
- The runtime-agent epics for ArchitectureSelector, GraphDesigner,
  NotebookComposer, ToolchainEngineer, and QARepairAgent have added typed
  feedback models, registry-backed internals, warning surfaces, and public
  manifest/API fields.
- The graph design contract now carries richer canonical spec metadata for
  command routes, tool reachability, domain terms, guarded cycles, terminal
  nodes, and the compiled graph variable while keeping `workflow_design`
  backward-compatible.
- Generation context packs now summarize source provenance so notebooks,
  manifests, and QA can explain whether docs came from local LangChain docs,
  Context7, cached repo docs, or fallback retrieval context.
- Runtime QA now checks for LangGraph notebook contract drift such as full-state
  overwrite node returns, unsafe broad HTTP tool placeholders, and generic
  architecture labels in domain-specific notebooks.
- `docs/agent-assets-audit.md` records the contributor-facing custom
  agent/skill inventory and keeps those assets separate from runtime product
  agents.
- `docs/diagrams/README.md` now indexes both the hand-maintained generator
  stage/state map and the generated repo architecture visualizer bundle.
- The 1.0 readiness branch adds a root MIT license, changelog, stable package
  metadata, isolated install smoke tests, and `scripts/run_release_eval.py` for
  local-only release evaluation.
- Release-readiness issue triage closed stale completed RequirementsAnalyst,
  pattern/example, cross-cutting, and duplicate CYOA items; remaining open
  issues are explicit post-1.0/residual work unless #258 is still waiting for
  the release PR merge.
- After PR #305 merged, the `Create diagram` workflow still failed while
  creating the automation PR because checkout did not persist the configured
  `GH_PAT` credentials for later git fetch/push operations.
- The active default-branch ruleset requires CodeQL contexts for `actions`,
  `javascript-typescript`, and `python`; the reusable CodeQL workflow must keep
  that matrix aligned or otherwise green PR checks can still remain unmergeable.

## Immediate Next Steps

- Keep public docs, examples, and onboarding copy aligned with the current
  CLI/API contract.
- Keep contributor-facing LangGraph/LangChain skills and LNF custom agents
  aligned with the canonical runtime notebook contract without importing those
  assets into runtime code.
- Keep the 1.0 release tracker (#256) aligned with packaging, workflow,
  evaluation, metadata, issue-triage, and PR progress until the `v1.0.0`
  release is published.
- Land the follow-up `Create diagram` authentication hotfix and verify the next
  `main` workflow run is green before tagging `v1.0.0`.
- Keep maintainer visualization docs aligned when generator stages, package
  boundaries, module relationships, or environment-variable usage changes.
- Preserve parity between CLI-driven, API-driven, and web-driven artifact
  generation flows.
- Keep deterministic stub mode offline-friendly while live mode uses
  request-scoped model configuration.

## Active Considerations

- Advanced API parameters such as `model`, `temperature`, `max_tokens`,
  `custom_endpoint`, and `agent_type` are request-scoped generation controls.
- `agent_type="deepagents"` is experimental and explicit opt-in; generated
  notebooks import the optional Deep Agents SDK lazily so stub mode remains
  offline-friendly.
- Runtime QA performs environment preflight and smoke-test validation; in stub
  mode unavailable notebook runtimes are recorded as non-blocking evidence, but
  live mode treats runtime support gaps as real failures.
- Generated notebooks should use explicit LangGraph state/reducer semantics,
  partial node updates, reachable tool execution claims, domain-aligned labels,
  and a standard compiled `graph` variable with thread-aware invocation config.
- The SSE implementation is appropriate for single-server development, but not a
  distributed production event bus.
- Packaging smoke tests are opt-in through `RUN_PACKAGING_SMOKE=1` because they
  create isolated virtual environments and the full-extra path is slow.
- The local release evaluation gate defaults to no upload; LangSmith can remain
  a separate explicit release-candidate comparison step when credentials are
  available.
- The current release-readiness branch verification baseline is `python -m
  pytest --asyncio-mode=auto` with 625 passing tests and 4 skipped tests, plus
  the CI fatal-error flake8 gate.
