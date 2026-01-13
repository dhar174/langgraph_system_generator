"""Tests for pattern library code generation."""

from __future__ import annotations

from langgraph_system_generator.patterns import (
    CritiqueLoopPattern,
    RouterPattern,
    SubagentsPattern,
)


class TestRouterPattern:
    """Tests for RouterPattern code generation."""

    def test_generate_state_code_basic(self):
        """Test basic state code generation."""
        code = RouterPattern.generate_state_code()

        assert "class WorkflowState(MessagesState):" in code
        assert "route: str" in code
        assert "results: Dict[str, str]" in code
        assert "final_output: str" in code

    def test_generate_state_code_with_additional_fields(self):
        """Test state code generation with additional fields."""
        additional = {"custom_field": "Custom data", "counter": "Iteration count"}
        code = RouterPattern.generate_state_code(additional_fields=additional)

        assert "custom_field: str  # Custom data" in code
        assert "counter: str  # Iteration count" in code

    def test_generate_router_node_code_structured(self):
        """Test router node generation with structured output."""
        routes = ["search", "analyze", "summarize"]
        code = RouterPattern.generate_router_node_code(
            routes, use_structured_output=True
        )

        assert "def router_node(state: WorkflowState)" in code
        assert "class RouteDecision(BaseModel):" in code
        assert '"search"' in code
        assert '"analyze"' in code
        assert '"summarize"' in code
        assert "with_structured_output" in code

    def test_generate_router_node_code_simple(self):
        """Test router node generation without structured output."""
        routes = ["search", "analyze"]
        code = RouterPattern.generate_router_node_code(
            routes, use_structured_output=False
        )

        assert "def router_node(state: WorkflowState)" in code
        assert "SystemMessage" in code
        assert "with_structured_output" not in code

    def test_generate_route_node_code(self):
        """Test route handler node generation."""
        code = RouterPattern.generate_route_node_code(
            "search", "Perform web searches for information"
        )

        assert "def search_node(state: WorkflowState)" in code
        assert "Perform web searches for information" in code
        assert "ChatOpenAI" in code
        assert "results[" in code

    def test_generate_graph_code_conditional(self):
        """Test graph construction with conditional edges."""
        routes = ["search", "analyze"]
        code = RouterPattern.generate_graph_code(routes, use_conditional_edges=True)

        assert "def route_decision(state: WorkflowState)" in code
        assert "StateGraph(WorkflowState)" in code
        assert 'workflow.add_node("router", router_node)' in code
        assert "add_conditional_edges" in code
        assert "MemorySaver()" in code

    def test_generate_complete_example(self):
        """Test complete example generation."""
        routes = ["search", "analyze"]
        route_purposes = {"search": "Search for information", "analyze": "Analyze data"}
        code = RouterPattern.generate_complete_example(routes, route_purposes)

        assert "Router Pattern Example" in code
        assert "class WorkflowState" in code
        assert "def router_node" in code
        assert "def search_node" in code
        assert "def analyze_node" in code
        assert "workflow = StateGraph" in code
        assert "if __name__ ==" in code


class TestSubagentsPattern:
    """Tests for SubagentsPattern code generation."""

    def test_generate_state_code_basic(self):
        """Test basic state code generation."""
        code = SubagentsPattern.generate_state_code()

        assert "class WorkflowState(MessagesState):" in code
        assert "next: str" in code
        assert "instructions: str" in code
        assert "task_results: dict" in code

    def test_generate_state_code_with_additional_fields(self):
        """Test state code generation with additional fields."""
        additional = {"priority": "Task priority level"}
        code = SubagentsPattern.generate_state_code(additional_fields=additional)

        assert "priority: str  # Task priority level" in code

    def test_generate_supervisor_code_structured(self):
        """Test supervisor node generation with structured output."""
        subagents = ["researcher", "writer", "reviewer"]
        descriptions = {
            "researcher": "Research specialist",
            "writer": "Content writer",
            "reviewer": "Quality reviewer",
        }
        code = SubagentsPattern.generate_supervisor_code(
            subagents, descriptions, use_structured_output=True
        )

        assert "def supervisor_node(state: WorkflowState)" in code
        assert "class SupervisorDecision(BaseModel):" in code
        assert '"researcher"' in code
        assert '"writer"' in code
        assert '"reviewer"' in code
        assert '"FINISH"' in code
        assert "with_structured_output" in code

    def test_generate_supervisor_code_simple(self):
        """Test supervisor node generation without structured output."""
        subagents = ["researcher", "writer"]
        code = SubagentsPattern.generate_supervisor_code(
            subagents, use_structured_output=False
        )

        assert "def supervisor_node(state: WorkflowState)" in code
        assert "with_structured_output" not in code

    def test_generate_subagent_code(self):
        """Test subagent node generation."""
        code = SubagentsPattern.generate_subagent_code(
            "researcher", "Research and gather information from various sources"
        )

        assert "def researcher_node(state: WorkflowState)" in code
        assert "Research and gather information" in code
        assert "ChatOpenAI" in code
        assert 'task_results["researcher"]' in code

    def test_generate_subagent_code_with_tools(self):
        """Test subagent node generation with tool binding."""
        code = SubagentsPattern.generate_subagent_code(
            "researcher", "Research specialist", include_tools=True
        )

        assert "def researcher_node(state: WorkflowState)" in code
        assert "# Example: Bind tools" in code or "tools" in code.lower()

    def test_generate_graph_code(self):
        """Test graph construction code generation."""
        subagents = ["researcher", "writer"]
        code = SubagentsPattern.generate_graph_code(subagents)

        assert "def supervisor_router(state: WorkflowState)" in code
        assert "StateGraph(WorkflowState)" in code
        assert 'workflow.add_node("supervisor", supervisor_node)' in code
        assert 'workflow.add_node("researcher", researcher_node)' in code
        assert 'workflow.add_node("writer", writer_node)' in code
        assert "add_conditional_edges" in code

    def test_generate_complete_example(self):
        """Test complete example generation."""
        subagents = ["researcher", "writer"]
        descriptions = {"researcher": "Research specialist", "writer": "Content writer"}
        code = SubagentsPattern.generate_complete_example(subagents, descriptions)

        assert "Subagents Pattern Example" in code
        assert "class WorkflowState" in code
        assert "def supervisor_node" in code
        assert "def researcher_node" in code
        assert "def writer_node" in code
        assert "workflow = StateGraph" in code


class TestCritiqueLoopPattern:
    """Tests for CritiqueLoopPattern code generation."""

    def test_generate_state_code_basic(self):
        """Test basic state code generation."""
        code = CritiqueLoopPattern.generate_state_code()

        assert "class WorkflowState(MessagesState):" in code
        assert "current_draft: str" in code
        assert "critique_feedback: str" in code
        assert "revision_count: int" in code
        assert "quality_score: float" in code
        assert "approved: bool" in code
        assert "criteria: List[str]" in code

    def test_generate_generation_node_code(self):
        """Test generation node code."""
        code = CritiqueLoopPattern.generate_generation_node_code(
            task_description="Write a blog post"
        )

        assert "def generate_node(state: WorkflowState)" in code
        assert "Write a blog post" in code
        assert "ChatOpenAI" in code
        assert "current_draft" in code

    def test_generate_critique_node_code_structured(self):
        """Test critique node generation with structured output."""
        criteria = ["Accuracy", "Clarity", "Completeness"]
        code = CritiqueLoopPattern.generate_critique_node_code(
            criteria=criteria, use_structured_output=True
        )

        assert "def critique_node(state: WorkflowState)" in code
        assert "class CritiqueAssessment(BaseModel):" in code
        assert "quality_score: float" in code
        assert "approved: bool" in code
        assert "with_structured_output" in code

    def test_generate_critique_node_code_simple(self):
        """Test critique node generation without structured output."""
        code = CritiqueLoopPattern.generate_critique_node_code(
            use_structured_output=False
        )

        assert "def critique_node(state: WorkflowState)" in code
        assert "with_structured_output" not in code

    def test_generate_revise_node_code(self):
        """Test revision node generation."""
        code = CritiqueLoopPattern.generate_revise_node_code()

        assert "def revise_node(state: WorkflowState)" in code
        assert "current_draft" in code
        assert "critique_feedback" in code
        assert "revision_count" in code
        assert "ChatOpenAI" in code

    def test_generate_conditional_edge_code(self):
        """Test conditional edge code generation."""
        code = CritiqueLoopPattern.generate_conditional_edge_code(
            max_revisions=3, min_quality_score=0.8
        )

        assert "def should_continue(state: WorkflowState)" in code
        assert "approved" in code
        assert "revision_count" in code
        assert "quality_score" in code
        assert ">= 3" in code
        assert ">= 0.8" in code

    def test_generate_graph_code(self):
        """Test graph construction code generation."""
        code = CritiqueLoopPattern.generate_graph_code(
            max_revisions=3, min_quality_score=0.8
        )

        assert "def should_continue(state: WorkflowState)" in code
        assert "StateGraph(WorkflowState)" in code
        assert 'workflow.add_node("generate", generate_node)' in code
        assert 'workflow.add_node("critique", critique_node)' in code
        assert 'workflow.add_node("revise", revise_node)' in code
        assert "add_conditional_edges" in code
        assert '"finish"' in code
        assert '"revise"' in code

    def test_generate_complete_example(self):
        """Test complete example generation."""
        criteria = ["Accuracy", "Clarity"]
        code = CritiqueLoopPattern.generate_complete_example(
            task_description="Write technical documentation",
            criteria=criteria,
            max_revisions=3,
        )

        assert "Critique-Revise Loop Pattern Example" in code
        assert "class WorkflowState" in code
        assert "def generate_node" in code
        assert "def critique_node" in code
        assert "def revise_node" in code
        assert "workflow = StateGraph" in code
        assert "if __name__ ==" in code


class TestPatternCodeQuality:
    """Tests for code quality and consistency across patterns."""

    def test_all_patterns_generate_valid_python_syntax(self):
        """Verify that all generated code is syntactically valid Python."""
        # Router pattern
        router_state = RouterPattern.generate_state_code()
        router_node = RouterPattern.generate_router_node_code(["test"])
        router_graph = RouterPattern.generate_graph_code(["test"])

        # Subagents pattern
        subagent_state = SubagentsPattern.generate_state_code()
        supervisor = SubagentsPattern.generate_supervisor_code(["test"])
        subagent_graph = SubagentsPattern.generate_graph_code(["test"])

        # Critique pattern
        critique_state = CritiqueLoopPattern.generate_state_code()
        generate = CritiqueLoopPattern.generate_generation_node_code()
        critique = CritiqueLoopPattern.generate_critique_node_code()

        # All should compile without syntax errors
        for code in [
            router_state,
            router_node,
            router_graph,
            subagent_state,
            supervisor,
            subagent_graph,
            critique_state,
            generate,
            critique,
        ]:
            compile(code, "<string>", "exec")

    def test_all_patterns_include_docstrings(self):
        """Verify that generated code includes docstrings."""
        router_node = RouterPattern.generate_router_node_code(["test"])
        assert '"""' in router_node or "'''" in router_node

        supervisor = SubagentsPattern.generate_supervisor_code(["test"])
        assert '"""' in supervisor or "'''" in supervisor

        generate = CritiqueLoopPattern.generate_generation_node_code()
        assert '"""' in generate or "'''" in generate

    def test_all_patterns_import_required_modules(self):
        """Verify that generated code imports necessary modules."""
        router_node = RouterPattern.generate_router_node_code(["test"])
        assert "from langchain_openai import ChatOpenAI" in router_node

        router_graph = RouterPattern.generate_graph_code(["test"])
        assert "from langgraph.graph import" in router_graph
        assert "StateGraph" in router_graph

    def test_patterns_handle_special_characters_in_names(self):
        """Test that patterns handle names with special characters."""
        # Test with hyphens and spaces
        code = RouterPattern.generate_route_node_code(
            "web-search agent", "Search the web"
        )
        assert "def web_search_agent_node" in code

        code = SubagentsPattern.generate_subagent_code("data-processor", "Process data")
        assert "def data_processor_node" in code

    def test_complete_examples_are_self_contained(self):
        """Verify that complete examples include all necessary code."""
        router_example = RouterPattern.generate_complete_example(["test"])
        assert "class WorkflowState" in router_example
        assert "def router_node" in router_example
        assert "StateGraph" in router_example
        assert "if __name__" in router_example

        subagent_example = SubagentsPattern.generate_complete_example(["test"])
        assert "class WorkflowState" in subagent_example
        assert "def supervisor_node" in subagent_example
        assert "StateGraph" in subagent_example

        critique_example = CritiqueLoopPattern.generate_complete_example()
        assert "class WorkflowState" in critique_example
        assert "def generate_node" in critique_example
        assert "def critique_node" in critique_example
        assert "def revise_node" in critique_example
        assert "StateGraph" in critique_example
