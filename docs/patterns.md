# Pattern Library Guide

The LangGraph System Generator includes a powerful pattern library that provides reusable templates and code generators for common multi-agent architectures. This guide covers the three core patterns and how to use them effectively.

## Overview

The pattern library simplifies the creation of complex multi-agent LangGraph workflows by providing:

- **Reusable Templates**: Pre-built code generators for common patterns
- **Type-Safe State Management**: Structured state schemas for each pattern
- **Customizable Components**: Flexible configuration options
- **Complete Examples**: Ready-to-run workflow implementations

## Available Patterns

### 1. Router Pattern

**Use Case**: Dynamic routing to specialized agents based on input classification

The Router Pattern is ideal for scenarios where:
- Different types of requests need specialized handling
- Input classification determines workflow routing
- You need modular, domain-specific agents
- Conditional execution based on input content

**Architecture**:
```
START → router_node → [route_a, route_b, route_c, ...] → END
```

**Key Features**:
- Dynamic route selection based on LLM classification
- Support for structured output with Pydantic models
- Customizable routes and routing logic
- Validation for invalid route selections

**Example Usage**:

```python
from langgraph_system_generator.patterns import RouterPattern

# Generate complete router system
routes = ["search", "analyze", "summarize"]
route_purposes = {
    "search": "Search for information",
    "analyze": "Analyze data and identify patterns",
    "summarize": "Condense content into summaries",
}

# Generate complete, runnable code
code = RouterPattern.generate_complete_example(routes, route_purposes)

# Or generate individual components
state_code = RouterPattern.generate_state_code()
router_code = RouterPattern.generate_router_node_code(routes)
graph_code = RouterPattern.generate_graph_code(routes)
```

**See Also**: `examples/router_pattern_example.py` for comprehensive examples

---

### 2. Subagents Pattern

**Use Case**: Supervisor-based coordination of specialized agents

The Subagents Pattern is ideal for scenarios where:
- Complex tasks need decomposition across multiple agents
- A supervisor coordinates workflow and delegates tasks
- Agents may need to work sequentially or collaboratively
- You need centralized decision-making and state management

**Architecture**:
```
START → supervisor → [agent_a, agent_b, agent_c, ...] → supervisor → END
                ↑_____________________________________________↓
                            (loop until FINISH)
```

**Key Features**:
- Supervisor coordinates task delegation
- Agents report results back to supervisor
- Flexible iteration control with max_iterations
- Support for tool-enabled agents
- Structured decision-making with reasoning

**Example Usage**:

```python
from langgraph_system_generator.patterns import SubagentsPattern

# Generate research team system
subagents = ["researcher", "analyst", "writer"]
descriptions = {
    "researcher": "Gathers information from multiple sources",
    "analyst": "Analyzes data and identifies patterns",
    "writer": "Creates comprehensive reports",
}

# Generate complete system
code = SubagentsPattern.generate_complete_example(subagents, descriptions)

# Or generate individual components
state_code = SubagentsPattern.generate_state_code()
supervisor_code = SubagentsPattern.generate_supervisor_code(subagents, descriptions)
agent_code = SubagentsPattern.generate_subagent_code("researcher", "Research specialist")
graph_code = SubagentsPattern.generate_graph_code(subagents)
```

**See Also**: `examples/subagents_pattern_example.py` for comprehensive examples

---

### 3. Critique-Revise Loop Pattern

**Use Case**: Iterative quality improvement through critique and revision cycles

The Critique-Revise Pattern is ideal for scenarios where:
- Output quality needs iterative refinement
- Expert critique guides improvements
- Multiple revision cycles are acceptable
- Quality standards must be met before completion

**Architecture**:
```
START → generate → critique → [revise → critique] → END
                        ↑___________↓
                    (loop until approved or max revisions)
```

**Key Features**:
- Structured quality assessment with scoring
- Configurable quality thresholds
- Maximum revision limits to prevent infinite loops
- Detailed feedback with strengths, weaknesses, and suggestions
- Approval-based workflow termination

**Example Usage**:

```python
from langgraph_system_generator.patterns import CritiqueLoopPattern

# Generate content refinement system
task = "Write technical documentation"
criteria = [
    "Technical accuracy",
    "Clarity and readability",
    "Completeness",
    "Code examples quality",
]

# Generate complete system
code = CritiqueLoopPattern.generate_complete_example(
    task_description=task,
    criteria=criteria,
    max_revisions=3,
)

# Or generate individual components
state_code = CritiqueLoopPattern.generate_state_code()
generate_code = CritiqueLoopPattern.generate_generation_node_code(task)
critique_code = CritiqueLoopPattern.generate_critique_node_code(criteria)
revise_code = CritiqueLoopPattern.generate_revise_node_code()
graph_code = CritiqueLoopPattern.generate_graph_code(max_revisions=3)
```

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

```bash
# Set your OpenAI API key
export OPENAI_API_KEY='your-key-here'

# Run an example
python examples/router_pattern_example.py
python examples/subagents_pattern_example.py
python examples/critique_revise_pattern_example.py
```

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
        additional_fields: Optional[Dict[str, str]] = None
    ) -> str
    
    @staticmethod
    def generate_generation_node_code(
        task_description: str = "Generate initial output",
        llm_model: str = "gpt-5-mini",
    ) -> str
    
    @staticmethod
    def generate_critique_node_code(
        criteria: Optional[List[str]] = None,
        llm_model: str = "gpt-5-mini",
        use_structured_output: bool = True,
    ) -> str
    
    @staticmethod
    def generate_revise_node_code(
        llm_model: str = "gpt-5-mini",
    ) -> str
    
    @staticmethod
    def generate_conditional_edge_code(
        max_revisions: int = 3,
        min_quality_score: float = 0.8,
    ) -> str
    
    @staticmethod
    def generate_graph_code(
        max_revisions: int = 3,
        min_quality_score: float = 0.8,
    ) -> str
    
    @staticmethod
    def generate_complete_example(
        task_description: str = "Write a technical article",
        criteria: Optional[List[str]] = None,
        max_revisions: int = 3,
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

## Resources

- **LangGraph Documentation**: https://langchain-ai.github.io/langgraph/
- **LangChain Documentation**: https://python.langchain.com/
- **Pattern Examples**: `examples/` directory
- **Test Suite**: `tests/unit/test_patterns.py`
- **Source Code**: `src/langgraph_system_generator/patterns/`

---

## Support

For issues or questions:
- Open an issue on GitHub
- Review existing examples in `examples/`
- Check test cases in `tests/` for usage patterns
- Consult LangGraph documentation for framework details
