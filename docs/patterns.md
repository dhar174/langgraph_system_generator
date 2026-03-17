# Pattern Library Guide

The repository exposes two related pattern surfaces:

- Public generator-backed helpers in `src/langgraph_system_generator/patterns/`
- Runnable reference implementations in [`examples/`](../examples/README.md)

The public package intentionally keeps the generator-backed API small:

- `RouterPattern`
- `SubagentsPattern`
- `CritiqueLoopPattern`

Those generators now emit LangGraph code in the current docs-aligned style:

- `TypedDict` state schemas
- `Annotated` reducers for message and accumulator fields
- structured outputs for routing and evaluation decisions
- `Command` for dynamic control flow
- `InMemorySaver` in compiled examples where checkpointing is useful

## Core Generator-Backed Patterns

### RouterPattern

Use when a request should be handled by exactly one specialist.

```python
from langgraph_system_generator.patterns import RouterPattern

code = RouterPattern.generate_complete_example(
    ["search", "analyze", "summarize"],
    {
        "search": "Retrieve supporting context",
        "analyze": "Interpret the available information",
        "summarize": "Compress the answer into key takeaways",
    },
)
```

### SubagentsPattern

Use when a supervisor must coordinate multiple specialists over several steps.

```python
from langgraph_system_generator.patterns import SubagentsPattern

code = SubagentsPattern.generate_complete_example(
    ["researcher", "analyst", "writer"],
    {
        "researcher": "Gather evidence",
        "analyst": "Interpret findings",
        "writer": "Produce the final brief",
    },
)
```

### CritiqueLoopPattern

Use when a draft should be reviewed against explicit criteria before it ships.

```python
from langgraph_system_generator.patterns import CritiqueLoopPattern

code = CritiqueLoopPattern.generate_complete_example(
    task_description="Write a concise implementation guide",
    criteria=[
        "Accuracy",
        "Concrete implementation guidance",
        "Clear structure",
    ],
    max_revisions=3,
)
```

## Advanced Example-Only Patterns

These patterns are intentionally shipped as runnable examples rather than new public code-generation classes:

- Hierarchical agent teams
- Plan-and-execute
- REWOO-style speculation and reconciliation
- Human approval / HITL interrupt flows
- LLM-as-a-judge reflection
- LLMCompiler-style dependency-graph execution

Use the example assets when you want a working reference implementation or notebook walkthrough without expanding the package API surface.

## Where To Go Next

- Pattern showcase and selection matrix: [`examples/README.md`](../examples/README.md)
- Runnable notebooks: `examples/*.ipynb`
- Example scripts: `examples/*.py`
- Unit coverage for the generator-backed APIs: [`tests/unit/test_patterns.py`](../tests/unit/test_patterns.py)
