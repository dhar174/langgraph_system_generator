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

**Key Features**:
- Structured quality assessment with scoring
- Human-review mode via a callback stored in workflow state
- Configurable quality thresholds
- Maximum revision limits to prevent infinite loops
- Custom failure conditions for missing feedback, stalled quality, or forced termination
- Detailed feedback with strengths, weaknesses, and suggestions
- Approval-based workflow termination

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
    min_quality_score=0.85,
    failure_conditions={"fail_on_no_improvement": True},
)
```

**Human Feedback Variant**:

```python
code = CritiqueLoopPattern.generate_complete_example(
    task_description="Draft a release announcement",
    feedback_source="human",
    failure_conditions={"fail_on_missing_feedback": True},
)
```

In human-feedback mode the generated example includes a `collect_human_feedback`
callback that you can replace with a UI approval flow, moderation queue, or
external review service.

Only inject trusted application callbacks into workflow state. Do not source
the human feedback handler from user input, persisted checkpoints, or other
untrusted data.

Because the generated human-feedback approach stores a Python callable in
workflow state, it is only suitable for in-memory execution or other
non-serializing runtime contexts. For persistent checkpointers, inject the
review handler through runtime context or closures instead of checkpointed
state.

**See Also**: `examples/critique_revise_pattern_example.py` for comprehensive examples

---

## Common Features

All patterns share these characteristics:

### State Management

Each pattern provides a `generate_state_code()` method that creates a properly structured state schema:

```python
# All patterns support additional custom fields
additional_fields = {
    "user_id": "User identifier",
    "session_id": "Session tracking",
}

state_code = Pattern.generate_state_code(additional_fields=additional_fields)
```

### Customization Options

Patterns support various customization options:

- **LLM Models**: Configure which model to use (`gpt-4`, `gpt-3.5-turbo`, etc.)
- **Structured Output**: Enable/disable Pydantic-based structured outputs
- **Additional Fields**: Add custom state fields
- **Conditional Logic**: Customize routing and decision logic

### Code Generation Methods

Each pattern provides these core methods:

| Method | Purpose |
|--------|---------|
| `generate_state_code()` | Create state schema |
| `generate_graph_code()` | Create graph construction code |
| `generate_complete_example()` | Generate full runnable system |

Plus pattern-specific methods for nodes and routing logic.

---

## Integration with Agentic Workflows

The pattern library is designed to integrate seamlessly with custom agentic workflows:

### Using Patterns in Custom Code

```python
from langgraph_system_generator.patterns import RouterPattern, SubagentsPattern

# Generate components from different patterns
router_state = RouterPattern.generate_state_code()
supervisor = SubagentsPattern.generate_supervisor_code(["agent1", "agent2"])

# Combine and customize as needed
# Copy generated code into your workflow files
# Modify prompts, add tools, adjust logic
```

### Composing Patterns

Patterns can be composed to create complex hybrid architectures:

```python
# Example: Router with subagent teams
# 1. Use Router to classify incoming requests
# 2. Each route leads to a Subagent team
# 3. Supervisor coordinates team within each route

# Generate router for top-level classification
router = RouterPattern.generate_router_node_code(["team_a", "team_b"])

# Generate subagent teams for each route
team_a = SubagentsPattern.generate_complete_example(["agent1", "agent2"])
team_b = SubagentsPattern.generate_complete_example(["agent3", "agent4"])

# Combine in your custom graph construction
```

---

## Testing and Validation

The pattern library includes comprehensive test coverage (≥90% for all patterns):

### Unit Tests

Located in `tests/unit/test_patterns.py`:
- Basic functionality tests for all methods
- Edge case handling (empty inputs, special characters, etc.)
- Code quality validation (syntax, imports, docstrings)
- Pattern importability and interface consistency

### Integration Tests

Located in `tests/integration/test_pattern_code_generation.py`:
- End-to-end notebook generation with patterns
- Workflow execution validation
- Generated code syntax checking

### Running Tests

```bash
# Run pattern tests with coverage
pytest tests/unit/test_patterns.py --cov=src/langgraph_system_generator/patterns

# Run all tests
pytest tests/
```

---

## Best Practices

### Pattern Selection

Choose patterns based on your workflow requirements:

| Requirement | Recommended Pattern |
|-------------|---------------------|
| Input-based routing | Router |
| Task decomposition | Subagents |
| Quality improvement | Critique-Revise |
| Specialized handling | Router |
| Coordinated workflow | Subagents |
| Iterative refinement | Critique-Revise |

### Customization Tips

1. **Start with Complete Examples**: Use `generate_complete_example()` to get a working system
2. **Customize Incrementally**: Modify prompts, add tools, adjust logic one step at a time
3. **Test Early**: Validate generated code with small test cases before full deployment
4. **Add Tools**: Enhance agents with domain-specific tools (web search, databases, etc.)
5. **Monitor Quality**: Track metrics like routing accuracy, revision counts, quality scores

### Common Pitfalls

1. **Too Many Routes**: Router pattern works best with 3-7 routes. More may degrade accuracy.
2. **Deep Nesting**: Avoid nesting patterns more than 2 levels deep for maintainability.
3. **Infinite Loops**: Always set max_iterations or max_revisions to prevent runaway execution.
4. **State Bloat**: Keep state minimal—only include necessary fields.
5. **Generic Prompts**: Customize system prompts for your domain to improve quality.

---

## Examples

See the `examples/` directory for comprehensive, runnable examples:

- **`router_pattern_example.py`**: 3 examples demonstrating router usage
- **`subagents_pattern_example.py`**: 4 examples showing supervisor-subagent coordination
- **`critique_revise_pattern_example.py`**: 5 examples of iterative refinement

Each example includes:
- Complete working code generation
- Customization demonstrations
- Integration patterns
- Best practices

### Running Examples

The critique-revise example runs in stub mode by default (no API key needed):

```bash
# Run in stub mode (offline, no API key required)
python examples/critique_revise_pattern_example.py --mode stub

# Run in live mode (requires OPENAI_API_KEY)
export OPENAI_API_KEY='your-key-here'
python examples/critique_revise_pattern_example.py --mode live --input "Draft onboarding docs"

# Router and subagents examples also require an API key for live mode
export OPENAI_API_KEY='your-key-here'
python examples/router_pattern_example.py
python examples/subagents_pattern_example.py
```

The critique-revise example uses LangGraph v1 idioms:
- `Command`-based routing from the critique node (replaces `add_conditional_edges`)
- `InMemorySaver` checkpointer on the compiled graph

---

## API Reference

### RouterPattern

```python
class RouterPattern:
    @staticmethod
    def generate_state_code(
        additional_fields: Optional[Dict[str, str]] = None
    ) -> str
    
    @staticmethod
    def generate_router_node_code(
        routes: List[str],
        llm_model: str = "gpt-5-mini",
        use_structured_output: bool = True,
    ) -> str
    
    @staticmethod
    def generate_route_node_code(
        route_name: str,
        route_purpose: str,
        llm_model: str = "gpt-5-mini",
    ) -> str
    
    @staticmethod
    def generate_graph_code(
        routes: List[str],
        entry_point: str = "router",
        use_conditional_edges: bool = True,
    ) -> str
    
    @staticmethod
    def generate_complete_example(
        routes: List[str],
        route_purposes: Optional[Dict[str, str]] = None,
    ) -> str
```

### SubagentsPattern

```python
class SubagentsPattern:
    @staticmethod
    def generate_state_code(
        additional_fields: Optional[Dict[str, str]] = None
    ) -> str
    
    @staticmethod
    def generate_supervisor_code(
        subagents: List[str],
        subagent_descriptions: Optional[Dict[str, str]] = None,
        llm_model: str = "gpt-5-mini",
        use_structured_output: bool = True,
    ) -> str
    
    @staticmethod
    def generate_subagent_code(
        agent_name: str,
        agent_description: str,
        llm_model: str = "gpt-5-mini",
        include_tools: bool = False,
    ) -> str
    
    @staticmethod
    def generate_graph_code(
        subagents: List[str],
        max_iterations: int = 10,
    ) -> str
    
    @staticmethod
    def generate_complete_example(
        subagents: List[str],
        subagent_descriptions: Optional[Dict[str, str]] = None,
    ) -> str
```

### CritiqueLoopPattern

```python
class CritiqueLoopPattern:
    @staticmethod
    def generate_state_code(
        additional_fields: Optional[Dict[str, str]] = None,
        include_human_feedback: bool = False,
        include_failure_tracking: bool = False,
    ) -> str

    @staticmethod
    def generate_generation_node_code(
        task_description: str = "Generate initial output",
        llm_model: str = "gpt-5-mini",
        model_config: Optional[Union[ModelConfig, dict]] = None,
    ) -> str

    @staticmethod
    def generate_critique_node_code(
        criteria: Optional[List[str]] = None,
        llm_model: str = "gpt-5-mini",
        use_structured_output: bool = True,
        feedback_source: str = "automated",
        model_config: Optional[Union[ModelConfig, dict]] = None,
    ) -> str

    @staticmethod
    def generate_revise_node_code(
        llm_model: str = "gpt-5-mini",
        model_config: Optional[Union[ModelConfig, dict]] = None,
    ) -> str

    @staticmethod
    def generate_conditional_edge_code(
        max_revisions: int = 3,
        min_quality_score: float = 0.8,
        failure_conditions: Optional[Dict[str, Any]] = None,
    ) -> str

    @staticmethod
    def generate_graph_code(
        max_revisions: int = 3,
        min_quality_score: float = 0.8,
        failure_conditions: Optional[Dict[str, Any]] = None,
    ) -> str

    @staticmethod
    def generate_complete_example(
        task_description: str = "Write a technical article",
        criteria: Optional[List[str]] = None,
        max_revisions: int = 3,
        min_quality_score: float = 0.8,
        model_config: Optional[Union[ModelConfig, dict]] = None,
        use_structured_output: bool = True,
        feedback_source: str = "automated",
        failure_conditions: Optional[Dict[str, Any]] = None,
    ) -> str
```

---

## Contributing

To add new patterns to the library:

1. Create a new module in `src/langgraph_system_generator/patterns/`
2. Implement the pattern class with standard methods
3. Add comprehensive unit tests in `tests/unit/test_patterns.py`
4. Create example scripts in `examples/`
5. Update this documentation
6. Ensure test coverage ≥90%

---

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
