# AGENTS.md

## Purpose

This file is the agent-focused companion to `README.md`.
Use it when you need to understand, extend, or maintain the agent systems in
this repository.

In this project, "agent" can mean two different things:

1. **Runtime product agents** that participate in notebook and system
   generation.
2. **Contributor-facing Copilot assets** such as custom agents, skills,
   prompts, and instructions that help maintainers work on the repository.

Keep those two families separate when making changes.

## Scope

This document covers:

- what each agent family is responsible for
- how runtime agents interact with the LangGraph generator architecture
- how to add or update runtime agents
- how to add or update contributor-facing agents and skills
- communication, state, and lifecycle conventions
- validation commands and examples to use before opening a PR

For human-oriented usage instructions, installation, and end-user workflows,
start with `README.md` and `CONTRIBUTING.md`.

## Agent families at a glance

| Agent family | Primary purpose | Main locations |
| --- | --- | --- |
| Runtime product agents | Turn a natural-language prompt into a notebook, exported artifacts, and QA results | `src/langgraph_system_generator/generator/`, `src/langgraph_system_generator/generator/agents/`, `src/langgraph_system_generator/patterns/`, `src/langgraph_system_generator/qa/`, `src/langgraph_system_generator/notebook/`, `src/langgraph_system_generator/rag/` |
| Contributor-facing Copilot assets | Help contributors plan, implement, review, document, and validate changes | `.github/agents/`, `.github/skills/`, `.github/prompts/`, `.github/instructions/`, and some mirrored skills under `skills/` |

## Repository surfaces that agents must respect

The same generation pipeline is reused across three repository surfaces:

- **CLI** via `lnf`
- **FastAPI + web UI** via
  `langgraph_system_generator.api.server:app`
- **Python package** under `src/langgraph_system_generator/`

Changes to runtime agents should preserve alignment across all three surfaces.
If a change affects generation, think through downstream effects on:

- CLI output structure
- API responses and artifact manifests
- web UI artifact display/download behavior
- notebook validity and exportability
- stub-mode offline behavior

## Runtime product agents

### What they do

Runtime agents are the core building blocks of the outer generator graph.
They transform user intent into a runnable LangGraph notebook and supporting
artifacts.

Current runtime agent classes exported from
`src/langgraph_system_generator/generator/agents/__init__.py` are:

- `RequirementsAnalyst`
- `ArchitectureSelector`
- `GraphDesigner`
- `ToolchainEngineer`
- `NotebookComposer`
- `QARepairAgent`

The runtime pipeline also relies on adjacent supporting systems:

- `DocsRetriever` and vector-store code under `src/langgraph_system_generator/rag/`
- notebook composition/export code under `src/langgraph_system_generator/notebook/`
- validators and repair helpers under `src/langgraph_system_generator/qa/`

### How they interact with the architecture

The outer workflow is implemented in
`src/langgraph_system_generator/generator/nodes.py`.
These node functions are the clearest map of the runtime lifecycle:

| Pipeline stage | Node | Main collaborator | Typical state written |
| --- | --- | --- | --- |
| Intake | `intake_node` | `RequirementsAnalyst` | `constraints` |
| Retrieval | `rag_retrieval_node` | `DocsRetriever` | `docs_context` |
| Architecture selection | `architecture_selection_node` | `ArchitectureSelector` | `selected_patterns`, `architecture_type`, `architecture_justification` |
| Workflow design | `graph_design_node` | `GraphDesigner` | `workflow_design`, `notebook_plan` |
| Tool planning | `tooling_plan_node` | `ToolchainEngineer` | `tools_plan` |
| Notebook assembly | `notebook_assembly_node` | `NotebookComposer` | `generated_cells` |
| Static QA | `static_qa_node` | validators under `src/langgraph_system_generator/qa/` | `qa_reports` |
| Runtime QA | `runtime_qa_node` | notebook runtime helpers | `qa_reports` |
| Repair | `repair_node` | `QARepairAgent` and notebook repair helpers | `generated_cells`, `repair_attempts`, `qa_reports` |
| Packaging | `package_outputs_node` | notebook/export helpers | `artifacts_manifest`, `generation_complete` |

### Shared state contract

Runtime agents communicate through `GeneratorState` in
`src/langgraph_system_generator/generator/state.py`.
That state is the integration contract between stages.

Important patterns:

- `constraints` and `docs_context` are accumulated lists.
- `generated_cells` is authoritative for the current repair iteration and is
  replaced rather than concatenated.
- `repair_attempts` bounds retry behavior.
- `artifacts_manifest` and `generation_complete` are the final packaging
  outputs expected by the CLI and API.

When adding a new runtime agent or stage:

1. define exactly which state keys it consumes
2. define exactly which state keys it writes
3. avoid writing keys that belong to another stage
4. keep state changes explicit and traceable

### Runtime-agent invariants

Preserve these repository-level behaviors:

- **Stub mode stays offline-friendly.**
  Do not introduce mandatory live network or credential requirements into
  stub-mode flows.
- **Notebook outputs stay portable.**
  Generated notebooks should remain runnable in local Jupyter and Google Colab.
- **Recovery is bounded.**
  Repair behavior must respect `MAX_REPAIR_ATTEMPTS`.
- **Output paths stay constrained.**
  Production-facing `LNF_OUTPUT_BASE` must resolve under the current working
  directory. `BASE_OUTPUT_DIR` is the broader override mainly used for test
  isolation.

## Creating or modifying a runtime product agent

### Design checklist

Use this checklist before writing code:

1. **Single responsibility**
   - Name the agent after one stage or concern.
   - Avoid catch-all agents that mix retrieval, design, repair, and export.
2. **Explicit inputs and outputs**
   - Read from `GeneratorState`.
   - Return narrowly-scoped updates from the node that calls the agent.
3. **Deterministic fallback behavior**
   - If parsing or live-model output fails, prefer a safe fallback over a hard
     crash when the stage can reasonably continue.
4. **Stub/live compatibility**
   - Make it obvious whether the code path depends on a live model, a vector
     store, or local cached data.
5. **Downstream awareness**
   - Check effects on QA, repair, notebook export, CLI, and API consumers.

### Implementation steps

1. Add or update the agent class under
   `src/langgraph_system_generator/generator/agents/`.
2. Export it from
   `src/langgraph_system_generator/generator/agents/__init__.py` if it is part
   of the public runtime-agent set.
3. Wire it into the correct node in
   `src/langgraph_system_generator/generator/nodes.py`.
4. Update `GeneratorState` only if the new stage needs new shared fields.
5. Add or update focused tests under `tests/unit/` or `tests/patterns/`.
6. Update documentation if the public workflow, outputs, or contributor
   expectations changed.

### Minimal runtime-agent skeleton

Use the existing agents as the style reference.
Keep public APIs typed and narrow:

```python
from typing import List, Optional

from langchain_openai import ChatOpenAI

from langgraph_system_generator.generator.state import Constraint
from langgraph_system_generator.utils.config import settings


class ExampleAgent:
    """Perform one focused generation stage."""

    def __init__(self, model: Optional[str] = None):
        self.llm = ChatOpenAI(model=model or settings.default_model, temperature=0)

    async def run(self, prompt: str) -> List[Constraint]:
        """Return only the data this stage is responsible for."""
        raise NotImplementedError
```

### Testing rules for runtime-agent changes

Use the smallest relevant test subset first:

```bash
pytest tests/unit/ --asyncio-mode=auto -q
pytest tests/patterns/ -v
```

Agent-related tests must follow the repository conventions from
`CONTRIBUTING.md`:

- patch `ChatOpenAI` at the fully qualified module import path used by the
  agent under test
- use `FakeEmbeddings` from `langchain_community.embeddings`
- stub `DocsRetriever` methods instead of hitting real FAISS or live docs
- use `AsyncMock` for coroutine behavior
- keep default tests independent from live credentials

## Contributor-facing Copilot assets

### What belongs where

Use the right asset type for the job:

| Asset type | Use it for | Main location |
| --- | --- | --- |
| Custom agent | A specialized collaborator with its own role, tools, and workflow | `.github/agents/` |
| Skill | Reusable task workflow with optional bundled resources | `.github/skills/<skill-name>/` |
| Prompt file | A reusable one-shot chat command | `.github/prompts/` |
| Instruction file | Repository-wide generation or review rules | `.github/instructions/` |

Some shared skills are mirrored under the top-level `skills/` directory.
If you update a skill that exists in both places, keep the mirrored copy in
sync.

### When to create a new contributor-facing agent

Create a new custom agent only when all of these are true:

- the task is specialized enough to justify its own persona or workflow
- the scope is narrower than a generic "do everything" agent
- the agent can operate with a minimal, clear toolset
- the repository does not already have a better-matched custom agent or skill

If a skill can solve the problem more cleanly than a new agent, prefer a skill.

### Recommended frontmatter template for a custom agent

Contributor-facing custom agents follow the guidance in
`.github/instructions/agents.instructions.md`.
Use a minimal template like this:

```yaml
---
description: 'Briefly describe the agent specialization and when to use it'
name: 'Display Name'
tools: ['read', 'search']
target: 'github-copilot'
infer: true
---
```

Recommended conventions:

- choose the smallest tool set that can do the job
- make the description concrete enough for discovery
- keep the role focused on one subsystem or workflow
- use handoffs only when there is a natural next step
- avoid generic catch-all instructions

### Recommended skill structure

Skills should be self-contained and discoverable:

```text
.github/skills/<skill-name>/
├── SKILL.md
├── references/        # optional
├── scripts/           # optional
├── templates/         # optional
└── assets/            # optional
```

Use the description in `SKILL.md` to say both:

- **what** the skill does
- **when** contributors should invoke it

That description is the main discovery signal for Copilot.

## Agent communication and lifecycle management

### Runtime-agent communication

Good runtime-agent communication in this repo means:

- communicate through typed shared state, not hidden globals
- pass only the information needed by the next stage
- keep stage boundaries clear: intake, retrieval, selection, design, tooling,
  assembly, QA, repair, packaging
- prefer structured outputs over free-form strings when later stages depend on
  the result
- surface recoverable failures into QA or repair instead of silently swallowing
  them

### Contributor-facing agent communication

Good contributor-agent communication means:

- state the objective and affected subsystem up front
- provide concrete file paths
- name the validation command to run
- explain any required follow-up or handoff
- keep change scope narrow and traceable

### Lifecycle expectations

Use the same lifecycle whenever you change an agent:

1. **Discover**
   - identify whether the change is for a runtime agent, custom agent, skill,
     prompt, or instruction
2. **Design**
   - define responsibilities, interfaces, and ownership
3. **Implement**
   - make the smallest change that satisfies the need
4. **Validate**
   - run the smallest relevant tests or documentation checks
5. **Document**
   - update AGENTS.md, README, docs, prompts, or instructions when contributor
     expectations changed
6. **Maintain**
   - keep mirrored skills, examples, and references aligned over time

## Example use cases

### Example 1: add a runtime generation stage

Use this path when a new generation concern belongs in the outer graph:

1. implement the agent in
   `src/langgraph_system_generator/generator/agents/`
2. add the corresponding node or node integration in
   `src/langgraph_system_generator/generator/nodes.py`
3. update `GeneratorState` if a new shared field is required
4. add focused unit tests
5. verify stub-mode behavior still works

### Example 2: add a new repository custom agent

Use this when contributors repeatedly need a specialized collaborator:

1. add `.github/agents/<name>.agent.md`
2. define focused frontmatter and a narrow mission
3. avoid broad tool access unless required
4. document when to use the new agent

### Example 3: add a reusable skill instead of another agent

Use this when the work is best expressed as a repeatable workflow:

1. add `.github/skills/<skill-name>/SKILL.md`
2. add supporting `references/`, `scripts/`, or `templates/` only if needed
3. mirror the skill under `skills/` if this repository already keeps that skill
   mirrored
4. keep the description specific enough for auto-discovery

## Validation commands

Use the smallest relevant command first:

```bash
pytest tests/unit/ --asyncio-mode=auto -q
pytest tests/unit/ --asyncio-mode=auto -v
pytest tests/patterns/ -v
pytest --asyncio-mode=auto
```

For CI-parity validation, `.github/workflows/python-app.yml` currently runs:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install flake8 pytest-asyncio
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics
pytest --asyncio-mode=auto
```

Additional local checks used in this repository:

```bash
black src/ tests/
ruff check src/ tests/
mypy src/
```

## Troubleshooting

### Stub mode unexpectedly needs live services

- Check whether the change introduced a hard dependency on a live model,
  credentials, or external retrieval.
- Prefer cached docs, fake embeddings, or deterministic fallbacks where
  appropriate.

### New output paths are rejected

- Use repo-relative output paths such as `./output/demo`.
- Remember that `LNF_OUTPUT_BASE` must resolve under the current working
  directory.
- Use `BASE_OUTPUT_DIR` only for broader test isolation scenarios.

### Agent tests fail in CI but not locally

- Reproduce the exact commands from `.github/workflows/python-app.yml`.
- Re-check the mocking rules from `CONTRIBUTING.md`.
- Confirm you patched the module-local `ChatOpenAI` import, not a global symbol.

## Source-of-truth references

When in doubt, verify behavior in these files before editing agent logic or
agent documentation:

- `README.md`
- `CONTRIBUTING.md`
- `src/langgraph_system_generator/generator/nodes.py`
- `src/langgraph_system_generator/generator/state.py`
- `src/langgraph_system_generator/generator/agents/`
- `.github/workflows/python-app.yml`
- `.github/instructions/agents.instructions.md`
- `docs/wiki/Getting-Started.md`
- `docs/wiki/Architecture-Deep-Dive.md`
