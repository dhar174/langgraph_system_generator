## What Works

Current status reconciled 2026-10-23 against fetched main `4f17c2d`.
The [current v1.1 plan](../plans/current-plan.md) owns the acceptance matrix.
Charles deferred #383 (open, non-blocking); no usage ledger/pricing engine or
per-generation spending cap is delivered. #334 is next: one opt-in
Requirements/Domain Fidelity Reviewer, advisory-only first slice; retain later
blocking/repair criteria. #129 stays open for controlled quality comparisons
without a #383 prerequisite. #335 remains later. #380 remains open for real-cloud
staging and owner acceptance; SDK/Firestore-emulator evidence is separate.

Merged PRs #384-#385 and #392-#399 deliver endpoint isolation, bounded ephemeral
lifecycle, durable adapters/API, SDK/emulator qualification, truthful outcomes
and explicit controlled-fixture evaluation. #379/#381/#382 are closed for their
accepted scope. Ordinary generation remains v1/execution `not_run`; explicit
local v2 is not cloud attestation or general requirements verification.
Dated counts below remain historical receipts.

- PR #396 independent review & verification: CodeQL security alerts 277 & 278
  (Polynomial ReDoS in credential redaction) verified resolved via linear
  `_redact_named_credentials` scanner and `[invalid URL omitted]` fallback.
  Synthetic watchdog probes (up to 65,536 repetitions) and `sys.settrace` step
  bounds confirmed O(n) execution without polynomial blowup. 78 redaction unit,
  82 pattern, and 132 durable/RAG tests passed locally; all 8 hosted CI checks
  passed on head `8785c31abdd078699d145484ce650778cb828ec8`.

- Issue #379 local qualification: 98 security tests, 898 unit tests, 82 pattern
  tests and the full repository suite (1,016 passed, 3 skipped) exited 0 in a
  fresh supported environment. CI fatal-error lint also exited 0. Broad Ruff,
  Black and mypy retain verified baseline failures with no additional findings.
  Hosted custom providers require exact registration and dedicated credentials.
  PR #384 is now merged; final correction-head hosted evidence and retained
  local timing failures are recorded in the security receipt/current plan.


- Actual runtime docs-source precedence for generation context (Issue #375 / PR #377):
  provider-neutral `DocsRetrievalService` with `LangChainDocsLocalProvider`
  (live local MCP/Mintlify search), `Context7DocsProvider` (live secondary/cross-check),
  and `CachedVectorDocsProvider` (resilient process-local cached fallback).
  `rag_retrieval_node` and `ArchitectureSelector` both route through this service,
  eliminating the architecture selection bypass. State contract includes
  `DocsRetrievalFeedback` with truthful provenance in `GenerationContextPack` and
  manifests (`attempted_sources`, `source_statuses`, `used_sources`, `fallback_used`,
  `stage_source_statuses`, `consulted_sources`).
  All review findings resolved across commits `f4fe02e`, `7995d02`, `c60a62b`, `a854327`, and `660b7a4`:
  - Shared MCP Streamable HTTP transport helper `mcp_transport.py` with protocol `2026-07-28`, streamable headers, and request ID validation on HTTP-200 JSON responses.
  - Context7 two-step flow (`resolve-library-id` -> `query-docs`), bounded fallback to `search`, empty/whitespace snippet rejection, and structural protocol envelope exclusion.
  - LangChain provider immediate loop termination on network/connection failure and content-only serialized document acceptance.
  - Strict `fallback_used` semantics (`True` iff fallback actually contributed final snippets).
  - ArchitectureSelector transient docs provenance isolation without polluting `used_sources` or flipping `fallback_used`.
  - Deterministic concurrent query feedback aggregation in `query_specs` order.
  - `DocsSourceRegistry.register()` in-place provider replacement preserving registry index and precedence by default.
  - Capability-based stub-mode plugin isolation (`stub_safe` default False for all providers; `CachedVectorDocsProvider` requires verified offline retriever with `is_offline_safe = True` to enable `stub_safe`, and guards `aretrieve(mode='stub')` directly).
  - Strict JSON-RPC 2.0 response validation in `mcp_transport.py` requiring `jsonrpc == "2.0"`, XOR `result`/`error`, and dict `error` across SSE, plain JSON, and HTTP paths with stream ordering.
  - Pure provider attribution in `orchestrator.py` deriving `used_sources` and `fallback_used` authoritatively from `surviving_providers` tuples without heuristic `source_kind` or prefix fallbacks.
  - Unexpected exception credential redaction in `context7.py` and `langchain_local.py`.
  - Security closeout pass: resolved Copilot findings by sanitizing RAG node exception feedback in `nodes.py` (`source_statuses`, `warnings`, `stage_source_statuses`), sanitizing `error_message` across all branches in `context7.py`, and sanitizing structured JSON-RPC error messages and transport errors in `langchain_local.py`.
  - Task indexing for TASK006 and TASK007 in `memory-bank/tasks/_index.md`.
  - Comprehensive credential and URL sanitization via `_sanitize_text_credentials` and `_sanitize_url_for_logging`, redacting basic-auth netlocs, compound tokens (`access_token`, `client_secret`, etc.), bearer tokens, and JSON keys across connection errors, transport errors, non-200 previews, provider fallback provenance, and orchestrator warnings.
  - Comprehensive resolution of all remaining known findings (A–F): provider-neutral snippet normalization and empty-result precedence in `orchestrator.py` (A); strict fallback/provenance defaults in `GenerationContextPack` (B); bounded/deduplicated `ArchitectureSelector` live retrieval with `asyncio.Semaphore(settings.architecture_docs_max_concurrency)` (C); cached-retriever eviction after failure via `_drop_docs_retriever_cache_entry` (D); strict JSON-RPC 2.0 response shape validation with SSE fallback (E); and complete Memory Bank alignment (F).
  All 112 tests in `tests/unit/test_rag_source_precedence.py` pass (+18 regression tests). Full unit test suite (800 tests, 5 warnings)
  and pattern test suite (82 tests) pass 100%. Full pytest suite passes (918 passed, 3 skipped, 5 warnings). Flake8, black, and mypy pass 100%. Stub mode remains 100% offline and deterministic.
- CLI-based generation supports both deterministic stub output and live
  generator-graph execution.
- The FastAPI server exposes synchronous generation, async generation startup,
  health checks, static web UI serving, and SSE progress streaming.
- Runtime pipeline reliability work from PR #356 is merged: accumulated
  constraints, documentation context, and QA history are bounded; notebook
  validation can run in memory; retriever construction is cached; and blocking
  validation/retrieval/repair work is offloaded from async graph nodes.
- Architecture selection, graph design, tool planning, notebook composition,
  and QA/repair now expose typed feedback and warning surfaces in manifests and
  API results.
- Generated artifact manifests now distinguish final serialized notebook cell
  counts from raw generated cell specs, expose an `artifact_contract` for
  standalone files and ZIP members, and include QA validation-scope wording for
  runtime smoke tests.
- Generated chatbot notebooks include stronger runtime affordances from PR #357
  and PR #360, including chat-loop execution helpers, character selection,
  executable-tool wiring, verifier/reviser fallbacks, memory checks,
  non-blocking top-to-bottom chat execution, prompt-faithfulness/domain QA, and
  centralized generated LLM configuration patterns.
- Wave 5 pattern/intake modernization merged in PR #361 (`5c239e5`), from
  `codex/pattern-intake-modernization-wave5`: router snippets now emit a
  fallback/general route, subagent snippets emit Send-based parallel fan-out
  contracts, critique-loop snippets can compile with `interrupt_before` on the
  revise node, and API/intake state can carry multi-turn requirements dialogs.
- PR #359 merged #343/#348 with canonical graph/spec rendering, manifest and QA
  graph-contract preservation, and explicit standalone-versus-notebook LLM
  initialization boundaries.
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
- The release-readiness branch had a green full local verification baseline:
  `python -m pytest --asyncio-mode=auto` reported 625 passed and 4 skipped, and
  the CI fatal-error flake8 gate reported 0 findings.
- The latest documented generated-output full-suite pass was
  `pytest --asyncio-mode=auto -q` with 721 passed and 3 skipped on the #350
  artifact-manifest branch. PR #357 additionally reported 609 unit tests
  passing after generated-chat contract changes. PR #359 review-fix slices
  reported 96 pattern tests, 102 composer/validator tests, and 142
  generator/API-node tests passing; the post-refresh broad unit gate reported
  622 passed and 4 warnings. Current Wave 4 focused slices report 111
  composer/validator tests, 143 generator/API-node tests, and 98 pattern tests
  passing. The Wave 4 broad unit gate reports 634 passed and 4 warnings, and
  the headed/live web UI gate completed with `gpt-5.4-mini`, working notebook,
  HTML, and manifest downloads, no browser errors, and advisory-only QA. PR
  #360 merged at `89da744e3f4b232eebf6ce4802ecee6537b02c8f`, closing the
  remaining generated-output child issues and epic #342. Current Wave 5 focused
  slices report 167 pattern tests and 115 generator/API-node tests passing; the
  Wave 5 broad unit gate reports 646 passed and 4 warnings. After updating a
  stale integration assertion from Command routing to Send fan-out, the full
  local CI-style gate reports 764 passed, 3 skipped, and 4 warnings.
- Bounded supervisor context-window management from Issue #65 is restored on
  PR #374 (`fix/restore-supervisor-context-window`) with all review findings resolved:
  credential-free `NotebookComposer` tests, scalar `task_results_summary_fingerprint`
  calculated from complete logical older snapshots (`agent:version:sha256`) before
  truncation/chunking, hierarchical/chunked summarization (`_chunk_items`,
  `_summarize_chunk`) with bounded reduction tree consolidation (`_consolidate_summaries_tree`),
  `task_result_versions` recency tracking, failure-safe summarizer initialization in
  `_summarize_older_results`, eviction of superseded specialist outputs, and regression
  coverage for changes beyond the first chunk boundary and preservation of tail chunks
  in the reduction tree. Local verification: 108 pattern unit tests, 82 pattern integration
  tests, 681 unit tests, and offline CLI stub smoke tests for router and subagents
  patterns all pass cleanly.
- Stale completed release-plan issues were closed with evidence during the
  release-readiness pass, reducing that older open issue inventory from 49 to
  26 while keeping true residual items open.
- The `v1.0.0` release is published, and #256 plus #258 are closed.
- Contributor-facing LNF custom agents and mirrored skills now align with the
  finalized runtime notebook contract from PR #336 through the merged #337
  follow-up.
- Google Cloud Run deployment is present through GitHub Actions OIDC, Artifact
  Registry, private Cloud Run, Secret Manager-backed `OPENAI_API_KEY`, `2Gi`
  memory sizing, and an authenticated `/health` smoke check.
- Live Cloud Run notebook generation was debugged through PR #338, which added
  the missing notebook runtime dependencies and hardened generated notebook
  fallbacks for the live QA path.

## What Is Still Incomplete

- Experimental Deep Agents support is opt-in through `agent_type="deepagents"`
  and keeps the optional SDK out of core imports.
- Production Cloud Run deployment uses an authenticated health-check path. The
  deploy job mints a Cloud Run ID token through `google-github-actions/auth`
  with the deployed service URL as the token audience.
- Generated-output quality epic #342 is closed as completed by PRs #358, #359,
  and #360. Runtime outer-agent follow-ups #334/#335 remain separate downstream
  work.

## Current Status

- The package metadata in `setup.py` uses the 1.0.0 Production/Stable release
  baseline on `main`, and `v1.0.0` is published.
- The repository already contains substantial scaffolding for CLI, API, RAG,
  notebook export, QA/repair, registry-backed planning, and pattern generation
  workflows.
- Memory Bank documentation is now project-specific context and should be
  maintained alongside public onboarding docs.
- Contributor-facing LNF custom agents now align with the finalized runtime
  notebook contract from PR #336 and describe current maintenance ownership
  instead of stale phase-by-phase scaffold work.
- Repository architecture diagrams are discoverable through public docs,
  contributor guidance, and MemoryBank context.
- Release metadata includes a root MIT license, changelog, and 1.0.0 package
  version/classifier updates on `main`.
- The Cloud Run deploy workflow builds and pushes the container image, deploys
  the private service, mounts `OPENAI_API_KEY` from Secret Manager, and checks
  `/health` after deployment.
- As of the post-PR #360 refresh, generated-output epic #342 and children
  #343-#350 are complete. Wave 5 merged via PR #361 for residual pattern/intake
  modernization issues #60, #63, #64, and #202.

## Known Issues and Limitations

- Live mode requires external credentials and can fail if the environment is not
  configured.
- RAG retrieval degrades gracefully to empty context when the vector store is
  unavailable, which keeps generation running but may reduce quality.
- Ephemeral SSE/jobs remain process-local. The optional durable backend now
  implements cross-instance contracts/API, with offline and emulator evidence;
  real-cloud staging and production acceptance remain outstanding under #380.
- Full-extra packaging smoke tests are intentionally opt-in because they install
  the broad notebook/RAG/export dependency set into a fresh virtual
  environment.
- Router fallback/general routing (#60), critique-loop human approval
  interrupts (#63), Send-based subagent dispatch (#64), iterative requirements
  refinement (#202), and the remaining CYOA notebook cell issues are tracked as
  residual follow-up work rather than closed stale items.
- The Cloud Run workflow's private-service health check is sensitive to token
  minting details in GitHub Actions WIF. Do not use `gcloud auth
  print-identity-token --audiences=...` for this workflow's health token; the
  ID token is minted through `google-github-actions/auth` instead.
