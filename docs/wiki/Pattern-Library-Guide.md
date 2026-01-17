# Pattern Library Guide

The LangGraph System Generator includes a comprehensive pattern library that provides reusable templates for common multi-agent architectures. This guide covers all available patterns, their use cases, and how to leverage them effectively.

## Overview

The Pattern Library simplifies multi-agent system development by providing:

- **Production-Tested Templates**: Each pattern has ≥90% test coverage
- **Complete Code Generation**: Generate full, runnable LangGraph workflows
- **Flexible Customization**: Adapt patterns to your specific needs
- **Composable Design**: Combine patterns for hybrid architectures

## Available Patterns

### 1. Router Pattern

**Purpose**: Dynamic routing to specialized agents based on input classification

#### When to Use

The Router Pattern is ideal when you need:
- Input classification and routing
- Specialized handlers for different request types
- Modular, maintainable agent organization
- Clear separation of concerns

#### Architecture

```
User Input → Router (Classifier) → Route A (Handler)
                                 → Route B (Handler)
                                 → Route C (Handler)
                                 → ... → END
```

The router examines each input and directs it to the appropriate handler based on classification.

#### Example Use Cases

- **Customer Support**: Route to technical, billing, or general support
- **Content Processing**: Route to search, analyze, or summarize handlers
- **Document Classification**: Route by document type for specialized processing
- **Query Handling**: Route by query intent (informational, transactional, navigational)

#### Usage

```python
from langgraph_system_generator.patterns import RouterPattern

# Define routes
routes = ["technical_support", "billing_support", "general_support"]

# Define route purposes
route_purposes = {
    "technical_support": "Handle technical issues and troubleshooting",
    "billing_support": "Process billing inquiries and payment issues",
    "general_support": "Answer general questions and provide information"
}

# Generate complete system
code = RouterPattern.generate_complete_example(routes, route_purposes)

# Save to file
with open("router_system.py", "w") as f:
    f.write(code)
```

#### Generated Components

1. **State Schema**: Includes routing information
   ```python
   class AgentState(TypedDict):
       messages: Annotated[list, add_messages]
       next_route: str
   ```

2. **Router Node**: LLM-based classification
   ```python
   def router_node(state: AgentState) -> dict:
       # Classify input and select route
       # Returns: {"next_route": "technical_support"}
   ```

3. **Route Handlers**: Specialized processing nodes
   ```python
   def technical_support_node(state: AgentState) -> dict:
       # Handle technical requests
   ```

4. **Graph Construction**: Conditional routing logic
   ```python
   workflow.add_conditional_edges(
       "router",
       lambda state: state["next_route"],
       {
           "technical_support": "technical_support",
           "billing_support": "billing_support",
           "general_support": "general_support"
       }
   )
   ```

#### Customization Options

```python
# Custom state fields
additional_fields = {
    "user_id": "User identifier",
    "session_context": "Conversation history"
}
state_code = RouterPattern.generate_state_code(additional_fields)

# Custom LLM model
router_code = RouterPattern.generate_router_node_code(
    routes=routes,
    llm_model="gpt-4",
    use_structured_output=True
)

# Custom graph structure
graph_code = RouterPattern.generate_graph_code(
    routes=routes,
    entry_point="router",
    use_conditional_edges=True
)
```

### 2. Subagents Pattern

**Purpose**: Supervisor-based coordination of specialized agent teams

#### When to Use

The Subagents Pattern is ideal when you need:
- Task decomposition across multiple agents
- Centralized coordination and decision-making
- Sequential or parallel agent workflows
- Complex multi-step processes

#### Architecture

```
User Input → Supervisor → Agent A → Supervisor → Agent B → Supervisor → FINISH
                    ↑                                              ↓
                    └──────────────────────────────────────────────┘
```

The supervisor delegates tasks to subagents, receives their results, and decides the next action.

#### Example Use Cases

- **Research Teams**: Researcher → Analyst → Writer workflow
- **Software Development**: Planner → Coder → Reviewer → Tester
- **Content Creation**: Researcher → Drafter → Editor → Publisher
- **Data Processing**: Collector → Cleaner → Analyzer → Visualizer

#### Usage

```python
from langgraph_system_generator.patterns import SubagentsPattern

# Define subagents
subagents = ["researcher", "analyst", "writer"]

# Define agent descriptions
descriptions = {
    "researcher": "Gathers information from multiple sources and documents findings",
    "analyst": "Analyzes collected data and identifies patterns and insights",
    "writer": "Creates comprehensive reports based on research and analysis"
}

# Generate complete system
code = SubagentsPattern.generate_complete_example(subagents, descriptions)

# Save to file
with open("subagents_system.py", "w") as f:
    f.write(code)
```

#### Generated Components

1. **State Schema**: Tracks agent interactions
   ```python
   class TeamState(TypedDict):
       messages: Annotated[list, add_messages]
       next_agent: str
       iterations: int
   ```

2. **Supervisor Node**: Delegates and coordinates
   ```python
   def supervisor_node(state: TeamState) -> dict:
       # Decide which agent to call next
       # Returns: {"next_agent": "researcher"}
   ```

3. **Subagent Nodes**: Specialized workers
   ```python
   def researcher_node(state: TeamState) -> dict:
       # Perform research tasks
   ```

4. **Graph Construction**: Looping coordination
   ```python
   workflow.add_conditional_edges(
       "supervisor",
       lambda state: state["next_agent"],
       {
           "researcher": "researcher",
           "analyst": "analyst",
           "writer": "writer",
           "FINISH": END
       }
   )
   ```

#### Customization Options

```python
# Custom state fields
additional_fields = {
    "task_context": "Current task information",
    "agent_outputs": "Results from each agent"
}
state_code = SubagentsPattern.generate_state_code(additional_fields)

# Supervisor with custom model
supervisor_code = SubagentsPattern.generate_supervisor_code(
    subagents=subagents,
    subagent_descriptions=descriptions,
    llm_model="gpt-4",
    use_structured_output=True
)

# Subagent with tools
agent_code = SubagentsPattern.generate_subagent_code(
    agent_name="researcher",
    agent_description="Research specialist",
    llm_model="gpt-4",
    include_tools=True  # Adds tool binding placeholder
)

# Graph with iteration limits
graph_code = SubagentsPattern.generate_graph_code(
    subagents=subagents,
    max_iterations=10  # Prevent infinite loops
)
```

### 3. Critique-Revise Loop Pattern

**Purpose**: Iterative quality improvement through critique and revision cycles

#### When to Use

The Critique-Revise Pattern is ideal when you need:
- Iterative refinement of outputs
- Quality assurance and validation
- Expert critique and feedback
- Meeting specific quality standards

#### Architecture

```
User Input → Generate → Critique → Decision
                           ↑          ↓ (needs revision)
                           └── Revise ←┘
                                ↓ (approved)
                               END
```

The system generates output, critiques it against criteria, and revises until quality standards are met.

#### Example Use Cases

- **Technical Documentation**: Iteratively improve clarity and completeness
- **Code Generation**: Generate → Review → Fix → Validate
- **Content Writing**: Draft → Critique → Revise → Polish
- **Report Creation**: Create → Validate → Enhance → Finalize

#### Usage

```python
from langgraph_system_generator.patterns import CritiqueLoopPattern

# Define task
task = "Write comprehensive technical documentation for an API"

# Define quality criteria
criteria = [
    "Technical accuracy and correctness",
    "Clarity and readability",
    "Completeness of coverage",
    "Quality of code examples",
    "Proper formatting and structure"
]

# Generate complete system
code = CritiqueLoopPattern.generate_complete_example(
    task_description=task,
    criteria=criteria,
    max_revisions=3  # Limit revision cycles
)

# Save to file
with open("critique_system.py", "w") as f:
    f.write(code)
```

#### Generated Components

1. **State Schema**: Tracks revisions and quality
   ```python
   class RevisionState(TypedDict):
       messages: Annotated[list, add_messages]
       current_output: str
       revision_count: int
       quality_score: float
       approved: bool
   ```

2. **Generation Node**: Creates initial output
   ```python
   def generate_node(state: RevisionState) -> dict:
       # Generate initial content
       # Returns: {"current_output": "..."}
   ```

3. **Critique Node**: Assesses quality
   ```python
   def critique_node(state: RevisionState) -> dict:
       # Evaluate against criteria
       # Returns: {"quality_score": 0.85, "feedback": "..."}
   ```

4. **Revise Node**: Improves based on feedback
   ```python
   def revise_node(state: RevisionState) -> dict:
       # Apply improvements
       # Returns: {"current_output": "improved..."}
   ```

5. **Conditional Logic**: Decides to continue or finish
   ```python
   def should_continue(state: RevisionState) -> str:
       if state["approved"] or state["revision_count"] >= max_revisions:
           return "end"
       return "revise"
   ```

#### Customization Options

```python
# Custom state fields
additional_fields = {
    "critique_history": "Track all critique feedback",
    "improvement_suggestions": "Specific improvements to make"
}
state_code = CritiqueLoopPattern.generate_state_code(additional_fields)

# Custom generation node
generate_code = CritiqueLoopPattern.generate_generation_node_code(
    task_description="Generate API documentation",
    llm_model="gpt-4"
)

# Critique with structured output
critique_code = CritiqueLoopPattern.generate_critique_node_code(
    criteria=criteria,
    llm_model="gpt-4",
    use_structured_output=True
)

# Custom thresholds
conditional_code = CritiqueLoopPattern.generate_conditional_edge_code(
    max_revisions=5,
    min_quality_score=0.9  # Higher quality threshold
)
```

## Pattern Composition

Patterns can be combined to create sophisticated hybrid architectures:

### Router + Subagents

Route to different subagent teams based on input:

```python
# Top-level router
routes = ["technical_team", "creative_team", "analysis_team"]
router_code = RouterPattern.generate_complete_example(routes)

# Each route leads to a subagent team
technical_team = SubagentsPattern.generate_complete_example(
    ["developer", "tester", "reviewer"]
)
creative_team = SubagentsPattern.generate_complete_example(
    ["designer", "copywriter", "editor"]
)
```

### Subagents + Critique

Each subagent uses critique loops for quality:

```python
# Main supervisor coordinates subagents
supervisor = SubagentsPattern.generate_supervisor_code(
    ["writer", "reviewer"]
)

# Writer subagent uses critique loop
writer_with_qa = CritiqueLoopPattern.generate_complete_example(
    task_description="Write content draft",
    criteria=["clarity", "engagement", "accuracy"]
)
```

### Router + Critique

Route to handlers that use iterative refinement:

```python
# Route by content type
router = RouterPattern.generate_router_node_code(
    ["blog_post", "technical_doc", "social_media"]
)

# Each handler uses critique for quality
blog_qa = CritiqueLoopPattern.generate_complete_example(
    task_description="Write blog post",
    criteria=["engagement", "SEO", "readability"]
)
```

## API Reference

### RouterPattern

```python
class RouterPattern:
    @staticmethod
    def generate_state_code(
        additional_fields: Optional[Dict[str, str]] = None
    ) -> str:
        """Generate state schema with routing fields."""
    
    @staticmethod
    def generate_router_node_code(
        routes: List[str],
        llm_model: str = "gpt-4-mini",
        use_structured_output: bool = True
    ) -> str:
        """Generate router classification node."""
    
    @staticmethod
    def generate_route_node_code(
        route_name: str,
        route_purpose: str,
        llm_model: str = "gpt-4-mini"
    ) -> str:
        """Generate individual route handler."""
    
    @staticmethod
    def generate_graph_code(
        routes: List[str],
        entry_point: str = "router",
        use_conditional_edges: bool = True
    ) -> str:
        """Generate graph construction code."""
    
    @staticmethod
    def generate_complete_example(
        routes: List[str],
        route_purposes: Optional[Dict[str, str]] = None
    ) -> str:
        """Generate complete router system."""
```

### SubagentsPattern

```python
class SubagentsPattern:
    @staticmethod
    def generate_state_code(
        additional_fields: Optional[Dict[str, str]] = None
    ) -> str:
        """Generate state schema with team coordination fields."""
    
    @staticmethod
    def generate_supervisor_code(
        subagents: List[str],
        subagent_descriptions: Optional[Dict[str, str]] = None,
        llm_model: str = "gpt-4-mini",
        use_structured_output: bool = True
    ) -> str:
        """Generate supervisor coordination node."""
    
    @staticmethod
    def generate_subagent_code(
        agent_name: str,
        agent_description: str,
        llm_model: str = "gpt-4-mini",
        include_tools: bool = False
    ) -> str:
        """Generate individual subagent node."""
    
    @staticmethod
    def generate_graph_code(
        subagents: List[str],
        max_iterations: int = 10
    ) -> str:
        """Generate graph with supervisor loop."""
    
    @staticmethod
    def generate_complete_example(
        subagents: List[str],
        subagent_descriptions: Optional[Dict[str, str]] = None
    ) -> str:
        """Generate complete subagents system."""
```

### CritiqueLoopPattern

```python
class CritiqueLoopPattern:
    @staticmethod
    def generate_state_code(
        additional_fields: Optional[Dict[str, str]] = None
    ) -> str:
        """Generate state schema with revision tracking."""
    
    @staticmethod
    def generate_generation_node_code(
        task_description: str = "Generate initial output",
        llm_model: str = "gpt-4-mini"
    ) -> str:
        """Generate initial content creation node."""
    
    @staticmethod
    def generate_critique_node_code(
        criteria: Optional[List[str]] = None,
        llm_model: str = "gpt-4-mini",
        use_structured_output: bool = True
    ) -> str:
        """Generate quality assessment node."""
    
    @staticmethod
    def generate_revise_node_code(
        llm_model: str = "gpt-4-mini"
    ) -> str:
        """Generate revision node."""
    
    @staticmethod
    def generate_conditional_edge_code(
        max_revisions: int = 3,
        min_quality_score: float = 0.8
    ) -> str:
        """Generate decision logic for continuing/finishing."""
    
    @staticmethod
    def generate_graph_code(
        max_revisions: int = 3,
        min_quality_score: float = 0.8
    ) -> str:
        """Generate graph with critique loop."""
    
    @staticmethod
    def generate_complete_example(
        task_description: str = "Generate content",
        criteria: Optional[List[str]] = None,
        max_revisions: int = 3
    ) -> str:
        """Generate complete critique-revise system."""
```

## Examples

Comprehensive runnable examples are available in the `examples/` directory:

- **`router_pattern_example.py`**: Complete router demonstrations
- **`subagents_pattern_example.py`**: Subagent coordination examples
- **`critique_revise_pattern_example.py`**: Iterative refinement examples

Run any example:
```bash
export OPENAI_API_KEY='your-key-here'
python examples/router_pattern_example.py
```

## Best Practices

### Pattern Selection

| Requirement | Pattern | Why |
|-------------|---------|-----|
| Input classification | Router | Clear routing logic |
| Task decomposition | Subagents | Coordinated workflow |
| Quality assurance | Critique-Revise | Iterative improvement |
| Specialized handling | Router | Modular handlers |
| Multi-step process | Subagents | Sequential coordination |
| Refinement needed | Critique-Revise | Quality control |

### Performance Tips

1. **Limit Routes**: Keep router patterns to 3-7 routes for best accuracy
2. **Set Max Iterations**: Always set `max_iterations` or `max_revisions` to prevent loops
3. **Use Structured Output**: Enable for more reliable routing/coordination
4. **Cache LLM Calls**: Reuse results where possible
5. **Monitor Costs**: Track token usage in multi-agent systems

### Common Pitfalls

1. ❌ **Too Many Routes**: Router accuracy degrades with 10+ routes
   - ✅ Use hierarchical routing or subagents instead

2. ❌ **Missing Termination**: Forgetting max iterations
   - ✅ Always set limits: `max_iterations=10`

3. ❌ **State Bloat**: Adding too many state fields
   - ✅ Keep state minimal, use agent memory for history

4. ❌ **Generic Prompts**: Using default prompts without customization
   - ✅ Tailor prompts to your domain

5. ❌ **Deep Nesting**: Router → Subagents → Critique (3 levels)
   - ✅ Keep architecture to 2 levels maximum

## Testing

All patterns include comprehensive test coverage:

```bash
# Run pattern tests
pytest tests/unit/test_patterns.py -v

# Run with coverage
pytest tests/unit/test_patterns.py --cov=src/langgraph_system_generator/patterns

# Run specific pattern tests
pytest tests/unit/test_patterns.py::TestRouterPattern -v
```

## Contributing Patterns

To add a new pattern:

1. Create module in `src/langgraph_system_generator/patterns/your_pattern.py`
2. Implement standard methods:
   - `generate_state_code()`
   - `generate_graph_code()`
   - `generate_complete_example()`
3. Add tests in `tests/unit/test_patterns.py`
4. Create examples in `examples/your_pattern_example.py`
5. Update documentation
6. Ensure ≥90% test coverage

---

**Next**: [CLI & API Reference →](CLI-and-API-Reference.md) | [Back to Home](Home.md)
