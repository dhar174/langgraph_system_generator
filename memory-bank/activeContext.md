## Current Work Focus

- The repository currently centers on prompt-to-notebook generation with shared
  CLI and FastAPI entry points, plus a reusable LangGraph pattern library.
- Current maintenance work includes keeping the Memory Bank aligned with the
  actual codebase so future sessions do not rely on template placeholders.
- Current documentation work includes the docs-owned
  `docs/diagrams/repo-architecture-visualizer/2026-04-30/` bundle for
  package/module/env relationship snapshots.
- Current release work is now post-1.0 maintenance: `v1.0.0` is published,
  the release-readiness tracker is closed, and follow-up work should be scoped
  to concrete quality, deployment, or runtime-generation issues.
- Current deployment work centers on the private Google Cloud Run service,
  which is deployed by GitHub Actions through Workload Identity Federation and
  Google Secret Manager rather than long-lived service account keys.

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
- The 1.0 release work landed with a root MIT license, changelog, stable
  package metadata, isolated install smoke tests, and
  `scripts/run_release_eval.py` for local-only release evaluation.
- Release-readiness issue triage closed stale completed RequirementsAnalyst,
  pattern/example, cross-cutting, and duplicate CYOA items; #256 and #258 are
  closed and the `v1.0.0` release is published.
- PR #337 closed the contributor-facing agent/skill alignment lane by updating
  LNF custom agents and mirrored skills to match the finalized runtime notebook
  contract without blending contributor assets into runtime product agents.
- PR #338 fixed live Cloud Run notebook-generation QA failures by restoring the
  container notebook runtime stack and hardening generated notebook fallbacks.
- PR #323 added the Cloud Run deployment workflow: pinned GitHub Actions, OIDC
  authentication, Artifact Registry image push, private Cloud Run deployment,
  Secret Manager-backed `OPENAI_API_KEY`, `2Gi` memory sizing, and release
  readiness tests for the deployment contract.
- PR #339 corrected the first private-service health-check failure by replacing
  the CI-local Cloud Run proxy with a direct authenticated health request. The
  follow-up deployment check mints the Cloud Run ID token through
  `google-github-actions/auth` with `id_token_audience` set to the deployed
  service URL; `gcloud auth print-identity-token --audiences=...` was not valid
  for the GitHub Actions WIF account type used here.
- The active default-branch ruleset requires CodeQL contexts for `actions`,
  `javascript-typescript`, and `python`; the reusable CodeQL workflow must keep
  that matrix aligned or otherwise green PR checks can still remain unmergeable.

## Immediate Next Steps

- Keep public docs, examples, and onboarding copy aligned with the current
  CLI/API contract.
- Keep contributor-facing LangGraph/LangChain skills and LNF custom agents
  aligned with the canonical runtime notebook contract without importing those
  assets into runtime code.
- After the #322 follow-up, the LNF custom agents should be treated as
  maintenance specialists for the current codebase rather than initial
  phase-by-phase builders, and mirrored LangChain/LangSmith skills should stay
  synchronized where they are true mirrors.
- Keep Cloud Run deployment changes isolated from runtime generation changes
  unless a live service failure proves the runtime code is involved.
- Verify the next `main` Cloud Run deployment after health-check changes,
  especially the authenticated `/health` step, before treating production
  deployment as fully settled.
- Keep post-1.0 issue work tied to explicit follow-up issues rather than
  reopening completed release-readiness or runtime-notebook-contract lanes.
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
- Cloud Run live mode gets `OPENAI_API_KEY` from Google Secret Manager at
  runtime; GitHub repository secrets are only used for deployment plumbing.
- Cloud Run deploys with `2Gi` memory because live generation and artifact
  packaging exceeded the default `512Mi` limit during live testing.
- The release-readiness verification baseline was `python -m pytest
  --asyncio-mode=auto` with 625 passing tests and 4 skipped tests, plus the CI
  fatal-error flake8 gate.
