## What Works

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
- Generated chatbot notebooks now include stronger runtime affordances from PR
  #357, including chat-loop execution helpers, character selection,
  executable-tool wiring, verifier/reviser fallbacks, memory checks, and
  centralized generated LLM configuration patterns.
- PR #359 is open for #343/#348 with canonical graph/spec rendering, manifest
  and QA graph-contract preservation, and explicit standalone-versus-notebook
  LLM initialization boundaries. Its six review threads have been addressed and
  resolved on the PR branch.
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
  622 passed and 4 warnings.
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
- Generated-output quality epic #342 remains active. Issue #350 is closed, but
  #343-#349 remain open; PR #357 may satisfy parts of #344-#348 and should be
  checked before additional implementation.

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
- As of the 2026-05-21 issue refresh, the open issue count is 29. #343 and
  #348 remain open until PR #359 merges.

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
- The canonical graph topology issue (#343) and generated credential/config
  hardening issue (#348) are still open while PR #359 is pending. Treat further
  Wave 4 work as blocked on checking what PR #359 closes.
- The Cloud Run workflow's private-service health check is sensitive to token
  minting details in GitHub Actions WIF. Do not use `gcloud auth
  print-identity-token --audiences=...` for this workflow's health token; the
  ID token is minted through `google-github-actions/auth` instead.
