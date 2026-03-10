# Contributing to langgraph_system_generator

Thank you for your interest in contributing! This document covers the development
workflow, coding conventions, and how we use **GitHub Copilot** to accelerate
development on this project.

---

## Table of Contents

1. [Getting started](#getting-started)
2. [Development workflow](#development-workflow)
3. [Testing conventions](#testing-conventions)
4. [Copilot-assisted development](#copilot-assisted-development)
5. [Pull request guidelines](#pull-request-guidelines)
6. [Code style](#code-style)

---

## Getting started

```bash
# Clone and create a virtual environment
git clone https://github.com/dhar174/langgraph_system_generator.git
cd langgraph_system_generator
python -m venv .venv && source .venv/bin/activate

# Install all dependencies (includes dev / test tools)
pip install -r requirements.txt
pip install -e .

# Build the RAG index (needed for integration tests)
python scripts/build_index.py
```

Verify the setup:

```bash
pytest tests/unit/ --asyncio-mode=auto -q
```

All unit tests should pass without an `OPENAI_API_KEY` (LLM calls are mocked).

---

## Development workflow

1. Create a feature branch from `main`.
2. Make focused, atomic commits.
3. Run the relevant test subset early and often (see [Testing conventions](#testing-conventions)).
4. Open a draft PR and iterate. Our PR template will prompt you for the key sections.
5. Request a review when ready; the CI suite must pass before merging.

---

## Testing conventions

| Area | Command |
|---|---|
| All unit tests | `pytest tests/unit/ --asyncio-mode=auto -v` |
| Pattern tests | `pytest tests/patterns/ -v` |
| Full suite | `pytest --asyncio-mode=auto` |
| Coverage report | `pytest --cov=src --cov-report=annotate:cov_annotate --asyncio-mode=auto` |

### Mocking rules

These rules are enforced by the existing test suite — new tests must follow them or
they will fail in CI:

- **Patch `ChatOpenAI` at the agent module path** before the agent is instantiated.
  For example: `monkeypatch.setattr("generator.agents.notebook_composer.ChatOpenAI", MockLLM)`.
  Patching `langchain_openai.ChatOpenAI` globally is not sufficient.

- **Use `FakeEmbeddings`** from `langchain_community.embeddings` wherever
  `OpenAIEmbeddings` would be called, so tests run without credentials.

- **Stub `DocsRetriever.retrieve_for_pattern`** to return `[]` in any test that
  exercises a generator node, to avoid real FAISS similarity searches.

- **Use `AsyncMock`** for all async functions / coroutines.

---

## Copilot-assisted development

We actively use **GitHub Copilot Pro/Pro+** throughout this project. The repository
ships with pre-built resources to help you get the most out of it:

### Prompt files (`.github/prompts/`)

Run these prompts from Copilot Chat (type `/` to see the list):

| Prompt | When to use |
|---|---|
| `langgraph-code-explanation` | Understanding an unfamiliar subsystem |
| `langgraph-test-generation` | Generating tests that follow project conventions |
| `langgraph-architecture-review` | Before adding a new subsystem or major refactor |
| `langgraph-pr-summary` | Auto-drafting a PR description from your diff |
| `langgraph-bug-investigation` | Debugging a failing test or runtime error |
| `review-and-refactor` | General code-quality review |
| `pytest-coverage` | Identifying and closing coverage gaps |

### Custom agents (`.github/agents/`)

Open Copilot Chat and `@mention` the relevant agent:

- **`architect`** — structural and design advice
- **`test-writer`** — generates comprehensive test suites
- **`se-security-reviewer`** — security audit before merging sensitive changes
- **`debug`** — step-by-step debugging of complex failures
- **`janitor`** — cleanup, dead-code removal, and tech-debt reduction

### Custom instructions (`.github/instructions/`)

Copilot reads these automatically in every chat session. They encode project-specific
rules (mocking style, quote style, async patterns). If you add a new convention,
consider adding it as an instruction file so Copilot follows it consistently.

### Advanced workflow guide

See [`docs/COPILOT_ADVANCED_WORKFLOWS.md`](docs/COPILOT_ADVANCED_WORKFLOWS.md) for
detailed guidance on code explanation, test generation, architecture review, PR
summaries, bug investigation, and more.

---

## Pull request guidelines

- Use the **PR template** (`.github/PULL_REQUEST_TEMPLATE.md`) — it's pre-filled when
  you open a PR on GitHub.
- A first-draft description can be generated with the `langgraph-pr-summary` Copilot
  prompt.
- PRs must pass all CI checks before merging.
- Keep PRs focused; large refactors are easier to review when broken into a series of
  smaller PRs.

---

## Code style

- **Formatter:** `black` (run `black src/ tests/` before committing).
- **Linter:** `ruff` (run `ruff check src/ tests/`).
- **Type checking:** `mypy src/` (new code should be fully typed).
- **Imports:** standard library → third-party → local, each group separated by a blank
  line.
- **Docstrings:** Google style for public functions and classes.

Pre-commit hooks are not yet configured; please run the formatters manually.

---

*Questions or suggestions? Open an issue or start a discussion — we welcome feedback!*
