"""Comprehensive tests for RouterPattern module.

This test module provides extensive coverage for the RouterPattern class,
including code generation, edge cases, integration scenarios, and smoke tests
to verify that generated code compiles and can be executed.
"""

from __future__ import annotations

import ast

import pytest

from langgraph_system_generator.patterns import RouterPattern


class TestRouterPatternCodeGeneration:
    """Test code generation methods of RouterPattern."""

    def test_generate_state_code_basic(self):
        """Test basic state code generation without additional fields."""
        code = RouterPattern.generate_state_code()

        assert "class WorkflowState(MessagesState):" in code
        assert "route: str" in code
        assert "results: Dict[str, str]" in code
        assert "final_output: str" in code
        assert "from typing import" in code
        assert "from langgraph.graph import MessagesState" in code

    def test_generate_state_code_with_additional_fields(self):
        """Test state code generation with custom additional fields."""
        additional = {
            "custom_field": "Custom data field",
            "counter": "Iteration count",
            "metadata": "Additional metadata",
        }
        code = RouterPattern.generate_state_code(additional_fields=additional)

        assert "class WorkflowState(MessagesState):" in code
        assert "custom_field: str  # Custom data field" in code
        assert "counter: str  # Iteration count" in code
        assert "metadata: str  # Additional metadata" in code

    def test_generate_state_code_with_empty_additional_fields(self):
        """Test state generation with empty dict for additional fields."""
        code = RouterPattern.generate_state_code(additional_fields={})
        assert "class WorkflowState(MessagesState):" in code
        assert "route: str" in code

    def test_generate_router_node_code_structured_output(self):
        """Test router node generation with structured output enabled."""
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
        assert "ChatOpenAI" in code
        assert "Literal" in code

    def test_generate_router_node_code_simple_output(self):
        """Test router node generation without structured output."""
        routes = ["search", "analyze"]
        code = RouterPattern.generate_router_node_code(
            routes, use_structured_output=False
        )

        assert "def router_node(state: WorkflowState)" in code
        assert "SystemMessage" in code
        assert "ChatOpenAI" in code
        assert "with_structured_output" not in code
        assert "valid_routes" in code.lower()

    def test_generate_router_node_code_custom_model(self):
        """Test router node generation with custom LLM model."""
        routes = ["test"]
        code = RouterPattern.generate_router_node_code(
            routes, llm_model="gpt-4-turbo", use_structured_output=True
        )

        assert 'model="gpt-4-turbo"' in code

    def test_generate_route_node_code_basic(self):
        """Test generation of a single route handler node."""
        code = RouterPattern.generate_route_node_code(
            "search", "Perform web searches for information"
        )

        assert "def search_node(state: WorkflowState)" in code
        assert "Perform web searches for information" in code
        assert "ChatOpenAI" in code
        assert 'results["search"]' in code
        assert "SystemMessage" in code

    def test_generate_route_node_code_with_special_characters(self):
        """Test route node generation handles special characters in names."""
        code = RouterPattern.generate_route_node_code(
            "web-search agent", "Search the web"
        )

        assert "def web_search_agent_node(state: WorkflowState)" in code
        assert "web-search agent" in code or "Search the web" in code

    def test_generate_route_node_code_custom_model(self):
        """Test route node with custom LLM model."""
        code = RouterPattern.generate_route_node_code(
            "analyze", "Analyze data", llm_model="gpt-4o"
        )

        assert 'model="gpt-4o"' in code

    def test_generate_graph_code_with_conditional_edges(self):
        """Test graph construction with conditional edge routing."""
        routes = ["search", "analyze", "summarize"]
        code = RouterPattern.generate_graph_code(routes, use_conditional_edges=True)

        assert "def route_decision(state: WorkflowState)" in code
        assert "StateGraph(WorkflowState)" in code
        assert 'workflow.add_node("router", router_node)' in code
        assert "add_conditional_edges" in code
        assert "MemorySaver()" in code
        assert "compile" in code

    def test_generate_graph_code_without_conditional_edges(self):
        """Test graph construction with simple edges."""
        routes = ["search", "analyze"]
        code = RouterPattern.generate_graph_code(routes, use_conditional_edges=False)

        assert "StateGraph(WorkflowState)" in code
        assert 'workflow.add_node("router", router_node)' in code
        assert "def route_decision" not in code

    def test_generate_complete_example_basic(self):
        """Test generation of complete runnable example."""
        routes = ["search", "analyze"]
        route_purposes = {
            "search": "Search for information",
            "analyze": "Analyze data",
        }
        code = RouterPattern.generate_complete_example(routes, route_purposes)

        assert "Router Pattern Example" in code
        assert "class WorkflowState" in code
        assert "def router_node" in code
        assert "def search_node" in code
        assert "def analyze_node" in code
        assert "workflow = StateGraph" in code
        assert "if __name__ ==" in code
        assert "async def run_example" in code

    def test_generate_complete_example_default_purposes(self):
        """Test complete example generation with default route purposes."""
        routes = ["route_a", "route_b"]
        code = RouterPattern.generate_complete_example(routes, route_purposes=None)

        assert "class WorkflowState" in code
        assert "def router_node" in code
        assert "Handle route_a-related tasks" in code or "route_a" in code
        assert "Handle route_b-related tasks" in code or "route_b" in code


class TestRouterPatternEdgeCases:
    """Test edge cases and boundary conditions for RouterPattern."""

    def test_generate_router_with_empty_routes_list(self):
        """Test router generation handles empty routes gracefully."""
        code = RouterPattern.generate_router_node_code([])

        assert "def router_node(state: WorkflowState)" in code
        # Should still be valid Python
        compile(code, "<string>", "exec")

    def test_generate_router_with_single_route(self):
        """Test router generation with only one route."""
        code = RouterPattern.generate_router_node_code(["search"])

        assert "def router_node(state: WorkflowState)" in code
        assert '"search"' in code
        compile(code, "<string>", "exec")

    def test_generate_router_with_many_routes(self):
        """Test router generation scales to many routes."""
        many_routes = [f"route_{i}" for i in range(20)]
        code = RouterPattern.generate_router_node_code(many_routes)

        assert "def router_node(state: WorkflowState)" in code
        for route in many_routes[:5]:  # Check first few routes
            assert f'"{route}"' in code or route in code

    def test_generate_route_node_with_multiline_purpose(self):
        """Test route node generation with complex multi-line purpose."""
        purpose = "Search multiple sources\nIncluding databases and APIs\nWith fallback mechanisms"
        code = RouterPattern.generate_route_node_code("search", purpose)

        assert "def search_node(state: WorkflowState)" in code
        assert "Search multiple sources" in code

    def test_generate_graph_with_many_routes(self):
        """Test graph generation scales to many routes."""
        many_routes = [f"route_{i}" for i in range(15)]
        code = RouterPattern.generate_graph_code(many_routes)

        for route in many_routes[:5]:
            assert route in code
        assert "StateGraph" in code
        compile(code, "<string>", "exec")

    def test_generate_graph_with_custom_entry_point(self):
        """Test graph generation with custom entry point name."""
        routes = ["search"]
        code = RouterPattern.generate_graph_code(routes, entry_point="custom_router")

        assert "StateGraph" in code
        # Entry point parameter doesn't change node name in current implementation
        assert 'add_node("router"' in code


class TestRouterPatternCodeQuality:
    """Test code quality aspects of generated code."""

    def test_generated_code_is_syntactically_valid(self):
        """Verify all generated code is syntactically valid Python."""
        # Test state code
        state_code = RouterPattern.generate_state_code()
        compile(state_code, "<string>", "exec")

        # Test router node
        router_code = RouterPattern.generate_router_node_code(["test"])
        compile(router_code, "<string>", "exec")

        # Test route node
        route_code = RouterPattern.generate_route_node_code("test", "Test route")
        compile(route_code, "<string>", "exec")

        # Test graph code
        graph_code = RouterPattern.generate_graph_code(["test"])
        compile(graph_code, "<string>", "exec")

        # Test complete example
        complete_code = RouterPattern.generate_complete_example(["test"])
        compile(complete_code, "<string>", "exec")

    def test_generated_code_includes_proper_imports(self):
        """Verify generated code includes all necessary imports."""
        # State code should import MessagesState
        state_code = RouterPattern.generate_state_code()
        assert "from langgraph.graph import MessagesState" in state_code

        # Router node should import ChatOpenAI
        router_code = RouterPattern.generate_router_node_code(["test"])
        assert "from langchain_openai import ChatOpenAI" in router_code

        # Graph code should import StateGraph
        graph_code = RouterPattern.generate_graph_code(["test"])
        assert "from langgraph.graph import" in graph_code
        assert "StateGraph" in graph_code

    def test_generated_code_includes_docstrings(self):
        """Verify generated code includes proper documentation."""
        router_code = RouterPattern.generate_router_node_code(["test"])
        assert '"""' in router_code or "'''" in router_code

        route_code = RouterPattern.generate_route_node_code("test", "Test")
        assert '"""' in route_code or "'''" in route_code

        graph_code = RouterPattern.generate_graph_code(["test"])
        assert '"""' in graph_code or "'''" in graph_code

    def test_generated_code_handles_empty_messages(self):
        """Test generated code handles empty message lists safely."""
        router_code = RouterPattern.generate_router_node_code(["test"])

        # Should guard messages[-1] access with an emptiness check via ternary
        assert "messages[-1].content if messages else" in router_code

    def test_generated_code_includes_error_handling(self):
        """Test generated code includes appropriate error handling."""
        router_code = RouterPattern.generate_router_node_code(
            ["test"], use_structured_output=False
        )

        # Should have validation for invalid routes
        assert "valid_routes" in router_code.lower() or "validate" in router_code.lower()


class TestRouterPatternValidation:
    """Test validation and error handling in RouterPattern."""

    def test_router_handles_none_additional_fields(self):
        """Test pattern handles None for optional additional_fields."""
        code = RouterPattern.generate_state_code(additional_fields=None)
        assert "class WorkflowState" in code
        compile(code, "<string>", "exec")

    def test_router_handles_none_route_purposes(self):
        """Test complete example handles None for route_purposes."""
        code = RouterPattern.generate_complete_example(["test"], route_purposes=None)
        assert "class WorkflowState" in code
        compile(code, "<string>", "exec")

    def test_all_methods_are_static(self):
        """Verify all pattern methods are static and don't require instantiation."""
        # Should be callable without creating an instance
        code = RouterPattern.generate_state_code()
        assert "class WorkflowState" in code

        code = RouterPattern.generate_router_node_code(["test"])
        assert "def router_node" in code

        code = RouterPattern.generate_route_node_code("test", "Test")
        assert "def test_node" in code

        code = RouterPattern.generate_graph_code(["test"])
        assert "StateGraph" in code

        code = RouterPattern.generate_complete_example(["test"])
        assert "class WorkflowState" in code


class TestRouterPatternSmokeTests:
    """Smoke tests to verify generated code can actually be compiled and parsed."""

    def test_complete_example_compiles_successfully(self):
        """Test that a complete generated example compiles without errors."""
        routes = ["search", "analyze", "summarize"]
        route_purposes = {
            "search": "Search for information",
            "analyze": "Analyze data",
            "summarize": "Create summaries",
        }

        code = RouterPattern.generate_complete_example(routes, route_purposes)

        # Should compile without syntax errors
        try:
            compile(code, "<generated_example>", "exec")
        except SyntaxError as e:
            pytest.fail(f"Generated code has syntax error: {e}\nCode:\n{code[:500]}")

    def test_generated_code_has_valid_ast(self):
        """Test that generated code can be parsed into a valid AST."""
        routes = ["route_a", "route_b"]
        code = RouterPattern.generate_complete_example(routes)

        try:
            tree = ast.parse(code)
            assert isinstance(tree, ast.Module)
        except SyntaxError as e:
            pytest.fail(f"Generated code cannot be parsed: {e}")

    def test_generated_code_defines_expected_functions(self):
        """Test that generated code defines all expected functions."""
        routes = ["search", "analyze"]
        code = RouterPattern.generate_complete_example(routes)

        tree = ast.parse(code)

        # Extract function names
        function_names = [
            node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        ]

        # Should define router node and route nodes
        assert "router_node" in function_names
        assert "search_node" in function_names
        assert "analyze_node" in function_names

    def test_generated_code_defines_expected_classes(self):
        """Test that generated code defines expected classes."""
        routes = ["test"]
        code = RouterPattern.generate_complete_example(routes)

        tree = ast.parse(code)

        # Extract class names
        class_names = [
            node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        ]

        # Should define WorkflowState and RouteDecision
        assert "WorkflowState" in class_names
        assert "RouteDecision" in class_names

    def test_multiple_routes_generate_valid_code(self):
        """Test that various route configurations generate valid code."""
        test_cases = [
            (["single"], {"single": "Single route"}),
            (["a", "b"], {"a": "Route A", "b": "Route B"}),
            (
                ["search", "analyze", "summarize"],
                {"search": "Search", "analyze": "Analyze", "summarize": "Summarize"},
            ),
        ]

        for routes, purposes in test_cases:
            code = RouterPattern.generate_complete_example(routes, purposes)
            try:
                compile(code, f"<routes_{len(routes)}>", "exec")
            except SyntaxError as e:
                pytest.fail(
                    f"Generated code with routes {routes} has syntax error: {e}"
                )


class TestRouterPatternIntegration:
    """Integration tests for RouterPattern usage in workflows."""

    def test_pattern_is_properly_exported(self):
        """Test that RouterPattern is exported from package."""
        from langgraph_system_generator.patterns import RouterPattern

        assert RouterPattern is not None
        assert hasattr(RouterPattern, "generate_state_code")
        assert hasattr(RouterPattern, "generate_router_node_code")
        assert hasattr(RouterPattern, "generate_route_node_code")
        assert hasattr(RouterPattern, "generate_graph_code")
        assert hasattr(RouterPattern, "generate_complete_example")

    def test_pattern_has_expected_interface(self):
        """Test that RouterPattern has all expected public methods."""
        required_methods = [
            "generate_state_code",
            "generate_router_node_code",
            "generate_route_node_code",
            "generate_graph_code",
            "generate_complete_example",
        ]

        for method_name in required_methods:
            assert hasattr(
                RouterPattern, method_name
            ), f"RouterPattern missing method: {method_name}"
            method = getattr(RouterPattern, method_name)
            assert callable(method), f"RouterPattern.{method_name} is not callable"

    def test_generated_components_can_be_composed(self):
        """Test that individual generated components can be composed together."""
        # Generate individual components
        state_code = RouterPattern.generate_state_code()
        router_code = RouterPattern.generate_router_node_code(["test"])
        route_code = RouterPattern.generate_route_node_code("test", "Test route")
        graph_code = RouterPattern.generate_graph_code(["test"])

        # All should be valid Python
        compile(state_code, "<state>", "exec")
        compile(router_code, "<router>", "exec")
        compile(route_code, "<route>", "exec")
        compile(graph_code, "<graph>", "exec")

        # Combined should also be valid
        combined = f"{state_code}\n\n{router_code}\n\n{route_code}\n\n{graph_code}"
        compile(combined, "<combined>", "exec")

    def test_pattern_supports_custom_state_fields(self):
        """Test that custom state fields are properly integrated."""
        custom_fields = {
            "user_id": "User identifier",
            "session_id": "Session tracking",
            "priority": "Request priority",
        }

        state_code = RouterPattern.generate_state_code(additional_fields=custom_fields)

        # All custom fields should be present
        for field_name in custom_fields.keys():
            assert field_name in state_code

        # Should still be valid Python
        compile(state_code, "<state_with_custom>", "exec")

    def test_pattern_supports_different_llm_models(self):
        """Test that different LLM models can be configured."""
        models = ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo", "gpt-4o"]

        for model in models:
            router_code = RouterPattern.generate_router_node_code(
                ["test"], llm_model=model
            )
            assert f'model="{model}"' in router_code

            route_code = RouterPattern.generate_route_node_code(
                "test", "Test", llm_model=model
            )
            assert f'model="{model}"' in route_code


class TestRouterPatternDocumentation:
    """Test documentation and usability aspects of RouterPattern."""

    def test_module_has_docstring(self):
        """Test that the module has proper documentation."""
        from langgraph_system_generator.patterns import router

        assert router.__doc__ is not None
        assert "Router pattern" in router.__doc__ or "router" in router.__doc__.lower()

    def test_class_has_docstring(self):
        """Test that RouterPattern class has documentation."""
        assert RouterPattern.__doc__ is not None
        assert "router" in RouterPattern.__doc__.lower()

    def test_methods_have_docstrings(self):
        """Test that all public methods have docstrings."""
        methods = [
            "generate_state_code",
            "generate_router_node_code",
            "generate_route_node_code",
            "generate_graph_code",
            "generate_complete_example",
        ]

        for method_name in methods:
            method = getattr(RouterPattern, method_name)
            assert method.__doc__ is not None, f"{method_name} missing docstring"

    def test_generated_code_includes_usage_comments(self):
        """Test that generated code includes helpful comments."""
        complete_code = RouterPattern.generate_complete_example(["test"])

        # Should have example usage
        assert "if __name__" in complete_code
        assert "example" in complete_code.lower() or "usage" in complete_code.lower()


class TestRouterPatternRobustness:
    """Test robustness and defensive programming in RouterPattern."""

    def test_handles_routes_with_special_characters(self):
        """Test handling of route names with special characters."""
        special_routes = [
            "web-search",
            "data_processor",
            "ai-assistant",
            "multi-word-route",
        ]

        for route in special_routes:
            code = RouterPattern.generate_route_node_code(route, "Test purpose")
            # Should normalize to valid Python function name
            normalized = route.lower().replace("-", "_").replace(" ", "_")
            assert f"def {normalized}_node" in code
            compile(code, f"<{route}>", "exec")

    def test_handles_unicode_in_descriptions(self):
        """Test handling of unicode characters in descriptions."""
        purpose = "Analyze data with emojis 🔍 and spëcial çharacters"
        code = RouterPattern.generate_route_node_code("analyze", purpose)

        assert "def analyze_node" in code
        # Purpose should be in the code somewhere
        compile(code, "<unicode_test>", "exec")

    def test_handles_very_long_route_purposes(self):
        """Test handling of very long purpose descriptions."""
        long_purpose = "A " * 500 + "long description"
        code = RouterPattern.generate_route_node_code("test", long_purpose)

        assert "def test_node" in code
        compile(code, "<long_purpose>", "exec")

    def test_consistent_output_for_same_input(self):
        """Test that same inputs produce same outputs (idempotency)."""
        routes = ["search", "analyze"]
        purposes = {"search": "Search", "analyze": "Analyze"}

        code1 = RouterPattern.generate_complete_example(routes, purposes)
        code2 = RouterPattern.generate_complete_example(routes, purposes)

        assert code1 == code2, "Same inputs should produce same outputs"


class TestRouterPatternPerformance:
    """Test performance characteristics of RouterPattern."""

    def test_generates_code_quickly_for_many_routes(self):
        """Test that code generation is efficient even with many routes."""
        import time

        many_routes = [f"route_{i}" for i in range(50)]

        start = time.time()
        code = RouterPattern.generate_complete_example(many_routes)
        elapsed = time.time() - start

        # Should generate code in reasonable time (< 3 seconds)
        assert elapsed < 3.0, f"Code generation took {elapsed}s, expected < 3s"
        assert "class WorkflowState" in code
        compile(code, "<performance_test>", "exec")

    def test_generated_code_size_is_reasonable(self):
        """Test that generated code size is reasonable."""
        routes = ["search", "analyze", "summarize"]
        code = RouterPattern.generate_complete_example(routes)

        # Code should be comprehensive but not excessively large
        # Expect roughly 5-15KB for a typical 3-route system
        code_size = len(code)
        assert 1000 < code_size < 50000, f"Generated code size {code_size} seems unusual"
