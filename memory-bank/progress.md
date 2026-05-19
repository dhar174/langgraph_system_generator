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
- The release-readiness branch had a green full local verification baseline:
  `python -m pytest --asyncio-mode=auto` reports 625 passed and 4 skipped, and
  the CI fatal-error flake8 gate reports 0 findings.
- Stale completed release-plan issues were closed with evidence, reducing the
  open issue inventory from 49 to 26 while keeping true residual items open.
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
- The Cloud Run workflow's private-service health check is sensitive to token
  minting details in GitHub Actions WIF. Do not use `gcloud auth
  print-identity-token --audiences=...` for this workflow's health token; the
  ID token is minted through `google-github-actions/auth` instead.
