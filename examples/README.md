# Pattern Library Examples

This directory contains runnable LangGraph examples for the repository's three
core patterns.

The examples execute real graphs instead of only printing generated code.
Each script defaults to `stub` mode so it can run offline, and each one also
supports `--mode live` for `ChatOpenAI` execution when `OPENAI_API_KEY` is set.

## Quick Start

From the repository root, install the package first (if you haven't already):

```bash
pip install -e '.[full]'
```

Then run the examples:

```bash
python examples/router_pattern_example.py --mode stub
python examples/subagents_pattern_example.py --mode stub
python examples/critique_revise_pattern_example.py --mode stub
```

For live runs:

```bash
export OPENAI_API_KEY="your-key-here"
python examples/router_pattern_example.py --mode live
```

## Included Examples

### `router_pattern_example.py`

- Uses `Annotated[...]` state with `add_messages`.
- Uses a structured `RouteDecision` schema.
- Uses `Command` so the router updates state and routes in one step.
- Runs cleanly in stub mode with deterministic route selection.

### `subagents_pattern_example.py`

- Uses `Annotated[...]` state for messages and agent history.
- Uses a structured `SupervisorDecision` schema.
- Uses `Command` for supervisor handoffs to researcher, writer, reviewer, or finish.
- Keeps worker behavior deterministic in stub mode.

### `critique_revise_pattern_example.py`

- Uses `Annotated[...]` state for messages and critique history.
- Uses a structured `CritiqueAssessment` schema.
- Uses `add_conditional_edges(...)` to terminate or continue revising.
- Runs a full critique loop in stub mode without external calls.

## What Stub Mode Verifies

Stub mode is intended to exercise modern LangGraph control flow safely:

- State schemas use `Annotated` reducers.
- Routers and supervisors produce structured decisions.
- Graph routing uses `Command` or `add_conditional_edges(...)` instead of legacy patterns.
- Scripts run end-to-end without requiring network access.

## Testing

Focused smoke tests live in `tests/patterns/test_example_scripts.py`.

Run them with:

```bash
pytest tests/patterns/test_example_scripts.py -q
```
