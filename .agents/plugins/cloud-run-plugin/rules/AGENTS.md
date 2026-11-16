# Google Cloud Run Deployment & Architecture Rules

When working on Google Cloud Run deployments, container configuration, or runtime optimization:

1. **Port Binding**: Cloud Run injects the `PORT` environment variable (default: 8080 or custom 8000). Ensure the server binds to `0.0.0.0` and listens on `PORT` (or defaults to 8000).
2. **Container Image**: Use the multi-stage slim container defined in `Dockerfile`. Avoid installing development dependencies in production images.
3. **Memory & Concurrency**:
   - Cloud Run writes in-memory `/tmp` filesystem to allocated container RAM. Sizing must account for `/tmp` allocations (e.g. minimum 1GiB).
   - Set concurrency appropriately (default: 80 requests/container) unless CPU-bound operations necessitate lower concurrency.
4. **Tooling & Operations**:
   - Use an available authorized read-only connector or CLI to inspect Cloud Run. Deployment tools are implementation mechanisms, not authorization. Deploy or change cloud configuration only within the owner-approved environment, service, revision, spending limits, and release scope.
   - For CI/CD, maintain `.github/workflows/deploy-cloud-run.yml` with Workload Identity Federation or GCP service account credentials.
