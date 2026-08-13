# TASK003 - Cloud Run Deployment and Live QA Hardening

**Status:** Complete
**Added:** 2026-05-19
**Updated:** 2026-05-19

## Original Request

Set up and harden production deployment for `langgraph_system_generator` on a
private Google Cloud Run service using GitHub Actions Workload Identity
Federation, Artifact Registry, Secret Manager, and live notebook QA evidence.

## Thought Process

Cloud Run deployment is a repository operations lane, not a runtime-agent design
lane. Keep deployment workflow changes isolated from runtime generation unless
live service evidence shows runtime code is involved. Avoid long-lived Google
service account keys and avoid copying runtime provider secrets into GitHub.

## Implementation Plan

- Deploy the containerized FastAPI app to Cloud Run from GitHub Actions.
- Use GitHub Actions OIDC and a Google service account instead of JSON keys.
- Push images to Artifact Registry and deploy with production environment
  gating.
- Mount `OPENAI_API_KEY` from Google Secret Manager at runtime.
- Size Cloud Run above the default memory limit for live generation.
- Validate private-service health with an authenticated `/health` smoke check.
- Keep workflow contract assertions in
  `tests/unit/test_release_readiness_metadata.py`.

## Progress Tracking

**Overall Status:** Complete - 100%

### Subtasks

| ID | Description | Status | Updated | Notes |
|----|-------------|--------|---------|-------|
| 3.1 | Add Cloud Run deployment workflow | Complete | 2026-05-18 | PR #323 merged with pinned actions, OIDC auth, Artifact Registry push, private Cloud Run deploy, and production gate. |
| 3.2 | Mount OpenAI key from Secret Manager | Complete | 2026-05-18 | Workflow mounts `OPENAI_API_KEY` from the configured Secret Manager secret; GitHub `OPENAI_API_KEY` is not used for runtime. |
| 3.3 | Increase production memory for live generation | Complete | 2026-05-18 | Cloud Run deploy flags set `--memory=2Gi` after the 512 MiB limit killed live generation. |
| 3.4 | Restore live notebook QA in the container | Complete | 2026-05-18 | PR #338 added notebook runtime dependencies and fixed generated notebook fallback issues. |
| 3.5 | Stabilize private health check | Complete | 2026-05-19 | The health check uses an action-minted ID token with the deployed service URL as audience. |

## Progress Log

### 2026-05-18

- PR #323 merged the deployment workflow and README Cloud Run docs.
- Live testing exposed Cloud Run memory pressure at the default 512 MiB limit;
  the workflow now deploys with `2Gi`.
- Live notebook QA exposed missing container runtime dependencies and generated
  notebook fallback problems; PR #338 fixed the live QA path.

### 2026-05-19

- PR #339 replaced the CI-local Cloud Run proxy with a direct authenticated
  `/health` request after the proxy sent unauthenticated requests to the private
  service.
- The next `main` deploy showed that `gcloud auth print-identity-token
  --audiences=...` is not valid for the GitHub Actions WIF account type in this
  workflow.
- The health-check implementation now mints an ID token through
  `google-github-actions/auth` with `token_format: id_token` and
  `id_token_audience` set to `steps.deploy.outputs.url`, then uses that output
  as the `Authorization: Bearer` token for `/health`.
