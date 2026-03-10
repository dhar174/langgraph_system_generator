# Advanced GitHub Copilot Workflows for langgraph_system_generator

This guide documents advanced ways to use **GitHub Copilot** (Pro / Pro+) when working on this
repository. The workflows below are tailored to the specific structure of the
`langgraph_system_generator` codebase — its agentic generation pipeline, RAG subsystem, pattern
library, QA/repair layer, and FastAPI server.

---

## Table of Contents

1. [Code Explanation](#1-code-explanation)
2. [Test Generation](#2-test-generation)
3. [Refactor Prompts](#3-refactor-prompts)
4. [PR Summaries](#4-pr-summaries)
5. [Chat-Driven Repository Analysis](#5-chat-driven-repository-analysis)
6. [Architecture Review](#6-architecture-review)
7. [Bug Investigation](#7-bug-investigation)
8. [RAG & Pattern Library Guidance](#8-rag--pattern-library-guidance)
9. [Copilot CLI Quick-Reference](#9-copilot-cli-quick-reference)
10. [Tips for Pro+ Features](#10-tips-for-pro-features)

---

## 1. Code Explanation

### When to use

- Onboarding to a new subsystem (e.g. the `qa/` repair loop, `rag/` vector store pipeline).
- Understanding a complex LangGraph node before modifying it.
- Reviewing auto-generated patterns in `patterns/`.

### Inline chat approach

Open the file you want to understand (e.g. `src/langgraph_system_generator/qa/repair.py`),
select the relevant class or function, then use **Copilot Chat** (`Ctrl+I` / `Cmd+I`):

```
/explain
```

Or ask a targeted question:

```
Explain how the QA repair loop retries failed notebook cells. Focus on the retry
limit, back-off logic, and how repaired cells are re-validated.
```

### Reusable prompt

See [`.github/prompts/langgraph-code-explanation.prompt.md`](../.github/prompts/langgraph-code-explanation.prompt.md)

---

## 2. Test Generation

### When to use

- Adding coverage for a newly implemented node in `generator/nodes.py`.
- Writing integration tests for a new pattern in `patterns/`.
- Generating edge-case tests after a bug fix.

### Key conventions this repo uses

| Convention | Detail |
|---|---|
| Test runner | `pytest` with `--asyncio-mode=auto` |
| OpenAI mocking | Patch `ChatOpenAI` at the **agent module level** before instantiation |
| Embeddings mocking | Use `FakeEmbeddings` from `langchain_community.embeddings` |
| RAG stubbing | Monkeypatch `DocsRetriever.retrieve_for_pattern` to return `[]` |
| Test location | `tests/unit/` for units, `tests/patterns/` for pattern assertions |

### Chat prompt

Select the function or class to test, then:

```
Generate pytest unit tests for the selected code. Follow these constraints:
- Use AsyncMock for all coroutines.
- Patch ChatOpenAI at the agent module path (e.g. generator.agents.notebook_composer.ChatOpenAI)
  before instantiating the agent under test.
- Stub DocsRetriever.retrieve_for_pattern to return [] to avoid FAISS calls.
- Do not require a real OPENAI_API_KEY; all LLM calls must be mocked.
```

### Reusable prompt

See [`.github/prompts/langgraph-test-generation.prompt.md`](../.github/prompts/langgraph-test-generation.prompt.md)

---

## 3. Refactor Prompts

### When to use

- Splitting an oversized generator node into smaller focused functions.
- Converting synchronous code to `async/await` for a new LangGraph edge.
- Standardising error handling across agent classes.

### Inline refactor

Select the code, open Copilot Chat, and use the `/fix` slash command or a descriptive prompt:

```
Refactor this node function to:
1. Extract the LLM prompt construction into a separate helper.
2. Replace bare `except Exception` with specific exception types.
3. Add type hints to all parameters and the return value.
Keep the existing public API unchanged.
```

### Reusable prompt

See [`.github/prompts/review-and-refactor.prompt.md`](../.github/prompts/review-and-refactor.prompt.md)
(already in `.github/prompts/`).

---

## 4. PR Summaries

### When to use

- Generating a first-draft PR description before opening a pull request.
- Summarising a large diff for reviewers unfamiliar with the subsystem.

### Chat approach

In Copilot Chat, with the diff or changed files in context:

```
Write a GitHub pull request description for these changes. Include:
- A one-sentence TL;DR.
- A "What changed" section with bullet points per file or subsystem.
- A "How to test" section referencing the relevant pytest commands.
- Any breaking-change warnings if API contracts have changed.
```

Or use the dedicated prompt:

See [`.github/prompts/langgraph-pr-summary.prompt.md`](../.github/prompts/langgraph-pr-summary.prompt.md)

---

## 5. Chat-Driven Repository Analysis

### When to use

- Getting a high-level map of the codebase before a large refactor.
- Understanding data flow through the generation pipeline.
- Identifying coupling between subsystems before adding a new feature.

### Useful chat questions

```
@workspace Describe the end-to-end data flow from a user's text prompt to a generated
Jupyter notebook in this repository. Identify every module that transforms or enriches
the data along the way.
```

```
@workspace Which files are responsible for selecting which architecture pattern
(router, subagents, critique-revise) to use for a given prompt?
```

```
@workspace List all public API endpoints defined in the FastAPI server and describe
what each one does.
```

```
@workspace What are the main failure modes in the QA/repair pipeline, and how are
they currently handled?
```

---

## 6. Architecture Review

### When to use

- Before adding a new pattern to `patterns/`.
- When evaluating whether to add a new LangGraph node vs. extending an existing one.
- Reviewing coupling between the RAG system and the generator.

### Chat prompt

```
Review the architecture of the langgraph_system_generator repository with a focus on:
1. Separation of concerns between generator/, rag/, patterns/, and qa/.
2. Any tight coupling that would make it hard to swap out the vector store backend.
3. Opportunities to introduce a plugin / registry pattern for architecture patterns.
Provide actionable recommendations with file-level specificity.
```

### Reusable prompt

See [`.github/prompts/langgraph-architecture-review.prompt.md`](../.github/prompts/langgraph-architecture-review.prompt.md)

---

## 7. Bug Investigation

### When to use

- Narrowing down which node in the generation pipeline produced incorrect output.
- Tracing why a generated notebook fails the QA validation step.
- Investigating a flaky test that involves FAISS / embedding calls.

### Chat approach

Paste the traceback or failing test output and ask:

```
Given this traceback from a pytest run, identify:
1. The root cause in the codebase (with file + line reference).
2. Why the error is triggered (explain the call chain).
3. A minimal fix that does not change the public interface.

<paste traceback here>
```

### Reusable prompt

See [`.github/prompts/langgraph-bug-investigation.prompt.md`](../.github/prompts/langgraph-bug-investigation.prompt.md)

---

## 8. RAG & Pattern Library Guidance

### Asking Copilot about the RAG system

```
@workspace Explain how the DocsRetriever selects documents for a given user prompt.
What embedding model is used? How are results ranked and filtered?
```

### Generating a new pattern

```
I want to add a new multi-agent pattern called "parallel-fan-out" where a router
sends the same task to N specialised agents simultaneously and aggregates results.
Using the existing patterns in src/langgraph_system_generator/patterns/ as a reference,
scaffold the new pattern class with the same interface as RouterPattern.
```

### Extending the RAG index

```
@workspace How would I add a new documentation source to the RAG index?
Walk me through the steps needed in scripts/build_index.py and data/.
```

---

## 9. Copilot CLI Quick-Reference

If you have the GitHub Copilot CLI installed (`gh copilot`), these commands are useful for
day-to-day work on this repo:

| Task | Command |
|---|---|
| Explain a shell command | `gh copilot explain "pytest tests/unit/ --asyncio-mode=auto -x"` |
| Suggest a git command | `gh copilot suggest "undo my last commit but keep the changes staged"` |
| Ask a free-form question | `gh copilot ask "What does --asyncio-mode=auto do in pytest?"` |

---

## 10. Tips for Pro+ Features

### Multi-file edits

Use **Copilot Edits** (VS Code) to make consistent changes across multiple files at once —
for example, renaming a method that appears in `nodes.py`, agent files, and their tests
simultaneously.

### Custom instructions

The `.github/instructions/` directory contains project-specific instructions that
Copilot respects in all chat sessions. When adding new conventions (e.g. a new mocking
pattern or import style), add an instruction file there so Copilot automatically follows
it in future sessions.

### Agents and Skills

The `.github/agents/` directory contains specialised Copilot agents. Use the `test-writer`
agent when generating tests, the `architect` agent when planning structural changes, and
the `se-security-reviewer` agent before opening security-sensitive PRs.

### Prompt files

All `.github/prompts/*.prompt.md` files are available in Copilot Chat via the `/` slash
command. This lets you run a consistent, parameterised prompt without retyping it. Use
the prompts added in this PR as starting points and customise them for your workflow.

---

*This document is intentionally speculative — it showcases the kinds of Copilot-assisted
workflows that are possible in this repository and serves as a reference for contributors
who want to leverage Pro/Pro+ features in their daily development.*
