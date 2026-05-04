# Changelog

All notable release changes are tracked in this file.

## 1.0.0 - 2026-05-04

### Added
- Release-readiness tracker for the 1.0 CLI/API/package contract.
- Root MIT license file for GitHub and package metadata discovery.
- Isolated packaging smoke coverage for minimal, API, and full extras.
- Local-only 1.0 release evaluation gate for deterministic LangGraph generator checks.

### Changed
- Package metadata now reports `1.0.0` and Production/Stable status.
- The Create diagram workflow uses the repository `GITHUB_TOKEN` path for update PRs.
- Public docs and MemoryBank context describe the project as the 1.0 release baseline instead of Alpha.

### Notes
- Deep Agents remains experimental and opt-in through `agent_type="deepagents"`.
- The FastAPI SSE implementation remains scoped to single-server operation for 1.0.
