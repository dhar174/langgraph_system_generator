## Why This Project Exists

- Building LangGraph-based multi-agent systems from scratch requires repeated
  boilerplate for state, nodes, edges, tools, exports, and notebook structure.
- This repository reduces that setup cost by generating a working scaffold from
  a user prompt and by shipping reusable pattern generators for common
  architectures.

## Problems It Solves

- Speeds up first-pass creation of LangGraph notebooks and demos.
- Gives users an offline-friendly path (`stub` mode) for trying the system
  without live model calls.
- Centralizes common workflow patterns, export logic, and documentation
  retrieval so users do not need to wire those pieces manually.

## Intended User Experience

- A user can describe the desired system in plain language and receive a
  notebook scaffold with code cells, structure, and export artifacts.
- The same generation flow should be reachable from CLI and API/web interfaces.
- Users should be able to choose between quick deterministic output and
  full LLM-backed generation depending on credentials and use case.

## UX Goals Reflected in the Code

- Fast local onboarding via `python -m venv`, `pip install -r requirements.txt`,
  and `lnf`/FastAPI entry points.
- Clear API and web progress reporting through SSE for long-running generation.
- Multiple artifact formats so generated systems are easy to run, inspect,
  share, and download.
