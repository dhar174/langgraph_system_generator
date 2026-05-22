## Current Work Focus

- The repository currently centers on prompt-to-notebook generation with shared
  CLI and FastAPI entry points, plus a reusable LangGraph pattern library.
- Current maintenance work includes keeping the Memory Bank aligned with the
  actual codebase so future sessions do not rely on template placeholders.
- Current documentation work includes the docs-owned
  `docs/diagrams/repo-architecture-visualizer/2026-05-21/` bundle for
  package/module/env relationship snapshots.
- Current release work is now post-1.0 maintenance: `v1.0.0` is published,
  the release-readiness tracker is closed, and follow-up work should be scoped
  to concrete quality, deployment, or runtime-generation issues.
- Current deployment work centers on the private Google Cloud Run service,
  which is deployed by GitHub Actions through Workload Identity Federation and
  Google Secret Manager rather than long-lived service account keys.

## Recent Changes Reflected in the Codebase

- PR #356 merged the runtime pipeline reliability cluster for issues #351-#355:
  bounded state accumulation, in-memory notebook validation, reduced repair
  copying, shared retriever caching, and async offloading. Those issues are now
  closed as completed.
- PR #358 closed #350 by making generated artifact manifests describe the
  emitted notebook and files truthfully: `cell_count` comes from the serialized
  notebook, raw generated cell specs have a separate count, `artifact_contract`
  distinguishes standalone files from ZIP members, and QA summaries state
  runtime smoke-test scope limits.
- PR #357 merged a broad generated-chat notebook contract pass with chat-loop,
  character-selection, executable-tool, verifier/reviser, memory, and generated
  credential/config improvements.
- PR #359 merged Wave 3 #343/#348. It preserves canonical graph/spec topology in
  generated notebooks, manifests, and QA, and keeps standalone pattern LLM
  snippets separate from notebook `make_llm(...)` cells.
- PR #360 merged Wave 4 at
  `89da744e3f4b232eebf6ce4802ecee6537b02c8f`, closing #344, #345, #346,
  #347, #349, and generated-output epic #342. Generated chatbot notebooks now
  have non-blocking chat helpers, same-thread demo turns, canonical
  verifier/reviser fields, memory writers, tool contract summaries, and
  prompt-faithfulness/domain QA.
- Wave 5 is active on `codex/pattern-intake-modernization-wave5` for #60, #63,
  #64, and #202. The branch modernizes residual LangGraph pattern/intake
  behavior: router fallback/general routes, critique-loop static interrupts,
  Send-based subagent fan-out, and multi-turn requirements refinement through
  the API/intake state contract.
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
  overwrite node returns, unsafe broad HTTP tool placeholders, unwired ToolNode
  executors, blocking default chatbot loops, terminal verifier/reviser prose
  nodes, declared memory fields without writers, and generic architecture labels
  in domain-specific notebooks.
- `docs/agent-assets-audit.md` records the contributor-facing custom
  agent/skill inventory and keeps those assets separate from runtime product
  agents.
- `docs/diagrams/README.md` now indexes both the hand-maintained generator
  stage/state map and the latest generated repo architecture visualizer bundle.
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

- Complete and open the ready Wave 5 PR from
  `codex/pattern-intake-modernization-wave5` for #60, #63, #64, and #202.
- Keep #334/#335 active as downstream runtime outer-agent architecture work
  after generated-output epic #342.
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
- The PR #359 review-fix verification slices were:
  `python -m pytest tests/unit/test_patterns_utils.py tests/unit/test_patterns.py -q`
  with 96 passed,
  `python -m pytest tests/unit/test_generator_notebook_composer.py tests/unit/test_validators.py -q`
  with 102 passed, and
  `python -m pytest tests/unit/test_generator_agents.py tests/unit/test_generator_nodes_additional.py tests/unit/test_cli_api.py --asyncio-mode=auto -q`
  with 142 passed.
- The post-refresh broad unit gate was
  `python -m pytest tests/unit/ --asyncio-mode=auto -q` with 622 passed and 4
  warnings.
- Wave 4 focused verification on `codex/chatbot-fidelity-wave4` passed:
  `python -m pytest tests/unit/test_generator_notebook_composer.py tests/unit/test_validators.py -q`
  with 111 passed,
  `python -m pytest tests/unit/test_generator_agents.py tests/unit/test_generator_nodes_additional.py tests/unit/test_cli_api.py --asyncio-mode=auto -q`
  with 143 passed, and
  `python -m pytest tests/unit/test_patterns.py tests/unit/test_patterns_utils.py -q`
  with 98 passed.
- The Wave 4 broad unit gate
  `python -m pytest tests/unit/ --asyncio-mode=auto -q` passed with 634 tests
  and 4 warnings.
- The headed/live Wave 4 UI gate used `gpt-5.4-mini` to generate
  `./output/wave4-live-chatbot`; required artifact downloads worked, the
  browser reported no console or page errors, and the manifest reported
  advisory QA only with zero blocking issues.
- Current Wave 5 focused verification has passed:
  `python -m pytest tests/unit/test_patterns.py tests/patterns/test_router.py tests/patterns/test_critique_loops.py -q`
  with 167 passed, and
  `python -m pytest tests/unit/test_generator_agents.py tests/unit/test_generator_nodes.py tests/unit/test_cli_api.py --asyncio-mode=auto -q`
  with 115 passed.
- The Wave 5 broad unit gate
  `python -m pytest tests/unit/ --asyncio-mode=auto -q` passed with 646 tests
  and 4 warnings.
