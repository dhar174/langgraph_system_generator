"""Comprehensive tests for CritiqueLoopPattern module."""

from __future__ import annotations

import ast
import time

import pytest

from langgraph_system_generator.patterns import CritiqueLoopPattern


class TestCritiqueLoopPatternCodeGeneration:
    """Test code generation methods of CritiqueLoopPattern."""

    def test_generate_state_code_basic(self):
        """Test default state generation for critique loops."""
        code = CritiqueLoopPattern.generate_state_code()

        assert "class WorkflowState(MessagesState):" in code
        assert "current_draft: str" in code
        assert "critique_feedback: str" in code
        assert "revision_count: int" in code
        assert "quality_score: float" in code
        assert "approved: bool" in code
        assert "criteria: List[str]" in code
        compile(code, "<critique_state>", "exec")

    def test_generate_state_code_with_human_feedback_and_failure_tracking(self):
        """Test optional human-review and failure-tracking state fields."""
        code = CritiqueLoopPattern.generate_state_code(
            include_human_feedback=True,
            include_failure_tracking=True,
        )

        assert "human_feedback_handler: Callable[..., Dict[str, Any]]" in code
        assert "quality_score, approved, and feedback" in code
        assert "previous_quality_score: float" in code
        compile(code, "<critique_state_extensions>", "exec")

    def test_generate_automated_critique_node_with_structured_output(self):
        """Test automated critique node generation with structured output."""
        code = CritiqueLoopPattern.generate_critique_node_code(
            criteria=["Accuracy", "Clarity"],
            use_structured_output=True,
        )

        assert "class CritiqueAssessment(BaseModel):" in code
        assert "with_structured_output" in code
        assert "previous_quality_score" in code
        assert "Critique:" in code
        compile(code, "<automated_structured_critique>", "exec")

    def test_generate_automated_critique_node_without_structured_output(self):
        """Test automated critique node generation without structured output."""
        code = CritiqueLoopPattern.generate_critique_node_code(
            use_structured_output=False,
        )

        assert "with_structured_output" not in code
        assert "response.content.split" in code
        assert "previous_quality_score" in code
        compile(code, "<automated_simple_critique>", "exec")

    def test_generate_human_feedback_critique_node(self):
        """Test human-feedback critique node generation."""
        code = CritiqueLoopPattern.generate_critique_node_code(
            feedback_source="human",
        )

        assert "human_feedback_handler" in code
        assert "Human critique:" in code
        assert "ChatOpenAI" not in code
        compile(code, "<human_critique>", "exec")

    def test_generate_generation_and_revision_nodes_accept_model_config(self):
        """Test generation and revision nodes preserve configurable model settings."""
        generation = CritiqueLoopPattern.generate_generation_node_code(
            task_description="Draft a design note",
            model_config={"model": "gpt-4o-mini", "temperature": 0.4},
        )
        revise = CritiqueLoopPattern.generate_revise_node_code(
            model_config={"model": "gpt-4o-mini", "temperature": 0.7},
        )

        assert "Draft a design note" in generation
        assert "gpt-4o-mini" in generation
        assert "temperature=0.4" in generation
        assert "gpt-4o-mini" in revise
        assert "temperature=0.7" in revise
        compile(generation, "<generate_node>", "exec")
        compile(revise, "<revise_node>", "exec")

    def test_generated_code_escapes_embedded_quotes_and_newlines(self):
        """Test generated code remains valid with complex task and criteria strings."""
        generation = CritiqueLoopPattern.generate_generation_node_code(
            task_description='Write a "safe" guide with\ntricky content and """quotes"""',
        )
        critique = CritiqueLoopPattern.generate_critique_node_code(
            criteria=['First line\nSecond line', 'Quoted "criterion"'],
        )

        compile(generation, "<escaped_task_description>", "exec")
        compile(critique, "<escaped_criteria>", "exec")

    def test_generated_templates_do_not_indent_top_level_imports(self):
        """Test emitted snippets keep top-level imports at column zero."""
        snippets = [
            CritiqueLoopPattern.generate_state_code(),
            CritiqueLoopPattern.generate_generation_node_code(),
            CritiqueLoopPattern.generate_critique_node_code(),
            CritiqueLoopPattern.generate_critique_node_code(use_structured_output=False),
            CritiqueLoopPattern.generate_critique_node_code(feedback_source="human"),
            CritiqueLoopPattern.generate_revise_node_code(),
            CritiqueLoopPattern.generate_graph_code(),
        ]

        for snippet in snippets:
            first_non_empty = next(line for line in snippet.splitlines() if line.strip())
            assert not first_non_empty.startswith(" ")


class TestCritiqueLoopPatternFailureConditions:
    """Test configurable failure and termination conditions."""

    def test_generate_conditional_edge_code_default_conditions(self):
        """Test default routing logic for critique loops."""
        code = CritiqueLoopPattern.generate_conditional_edge_code(
            max_revisions=3,
            min_quality_score=0.8,
        )

        assert "return \"finish\"" in code
        assert "\"max_revisions_reached\"" in code
        assert "return \"revise\"" in code
        compile(code, "<default_routing>", "exec")

    def test_generate_conditional_edge_code_with_custom_failures(self):
        """Test custom failure branches for stalled or incomplete revisions."""
        code = CritiqueLoopPattern.generate_conditional_edge_code(
            max_revisions=4,
            min_quality_score=0.9,
            failure_conditions={
                "fail_on_max_revisions": True,
                "fail_on_no_improvement": True,
                "min_quality_improvement": 0.05,
                "fail_on_missing_feedback": True,
            },
        )

        assert "return \"missing_feedback\"" in code
        assert "return \"no_improvement\"" in code
        assert "return \"max_revisions_failed\"" in code
        assert "quality_delta <= 0.05" in code
        compile(code, "<custom_failure_routing>", "exec")

    def test_invalid_min_quality_improvement_raises_clear_value_error(self):
        """Test invalid improvement thresholds fail with a named error."""
        with pytest.raises(ValueError, match="min_quality_improvement"):
            CritiqueLoopPattern.generate_conditional_edge_code(
                failure_conditions={"min_quality_improvement": "five"}
            )

    def test_generate_graph_code_maps_extended_failure_outcomes(self):
        """Test graph generation includes all termination outcomes."""
        code = CritiqueLoopPattern.generate_graph_code(
            max_revisions=2,
            min_quality_score=0.75,
            failure_conditions={
                "fail_on_max_revisions": True,
                "fail_on_no_improvement": True,
                "fail_on_missing_feedback": True,
            },
        )

        assert '"missing_feedback": END' in code
        assert '"no_improvement": END' in code
        assert '"max_revisions_failed": END' in code
        assert '"max_revisions_reached": END' in code
        assert '"revise": "revise"' in code
        compile(code, "<critique_graph>", "exec")


class TestCritiqueLoopPatternExamples:
    """Test generated examples and integration usability."""

    def test_generate_complete_example_automated(self):
        """Test automated complete example generation remains runnable."""
        code = CritiqueLoopPattern.generate_complete_example(
            task_description="Write API documentation",
            criteria=["Accuracy", "Examples"],
            max_revisions=3,
            min_quality_score=0.85,
            failure_conditions={"fail_on_no_improvement": True},
        )

        assert "Critique-Revise Loop Pattern Example" in code
        assert "def generate_node" in code
        assert "def critique_node" in code
        assert "def revise_node" in code
        assert "workflow = StateGraph" in code
        assert "max_revisions_reached" in code
        compile(code, "<complete_automated_example>", "exec")

    def test_generate_complete_example_human_feedback(self):
        """Test human-feedback complete example includes callback hook."""
        code = CritiqueLoopPattern.generate_complete_example(
            task_description="Write a release note",
            feedback_source="human",
            use_structured_output=False,
            failure_conditions={"fail_on_missing_feedback": True},
        )

        assert "def collect_human_feedback" in code
        assert '"human_feedback_handler": collect_human_feedback' in code
        assert "Human critique:" in code
        compile(code, "<complete_human_example>", "exec")

    def test_generated_complete_example_has_valid_ast(self):
        """Test complete example parses into a valid Python AST."""
        code = CritiqueLoopPattern.generate_complete_example(
            feedback_source="human",
            failure_conditions={"fail_on_no_improvement": True},
        )

        tree = ast.parse(code)
        assert isinstance(tree, ast.Module)

        function_names = [
            node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        ]
        assert "generate_node" in function_names
        assert "critique_node" in function_names
        assert "revise_node" in function_names
        assert "collect_human_feedback" in function_names

    def test_generated_components_can_be_composed_together(self):
        """Test generated components remain composable when combined manually."""
        state_code = CritiqueLoopPattern.generate_state_code(
            include_human_feedback=True,
            include_failure_tracking=True,
        )
        generation = CritiqueLoopPattern.generate_generation_node_code()
        critique = CritiqueLoopPattern.generate_critique_node_code(
            feedback_source="human",
        )
        revise = CritiqueLoopPattern.generate_revise_node_code()
        graph = CritiqueLoopPattern.generate_graph_code(
            failure_conditions={"fail_on_missing_feedback": True},
        )

        combined = "\n\n".join([state_code, generation, critique, revise, graph])
        compile(combined, "<combined_critique_pattern>", "exec")


class TestCritiqueLoopPatternDocumentation:
    """Test documentation and public interface of the critique-loop pattern."""

    def test_module_class_and_methods_have_docstrings(self):
        """Test core documentation is present for extension and adaptation."""
        from langgraph_system_generator.patterns import critique_loops

        assert critique_loops.__doc__ is not None
        assert CritiqueLoopPattern.__doc__ is not None

        methods = [
            "generate_state_code",
            "generate_generation_node_code",
            "generate_critique_node_code",
            "generate_revise_node_code",
            "generate_conditional_edge_code",
            "generate_graph_code",
            "generate_complete_example",
        ]

        for method_name in methods:
            method = getattr(CritiqueLoopPattern, method_name)
            assert method.__doc__ is not None, f"{method_name} missing docstring"

    def test_pattern_is_exported_for_agentic_workflows(self):
        """Test critique loop pattern is importable from the package root."""
        from langgraph_system_generator.patterns import CritiqueLoopPattern as Exported

        assert Exported is CritiqueLoopPattern
        assert hasattr(Exported, "generate_complete_example")

    def test_invalid_feedback_source_raises_value_error(self):
        """Test unsupported feedback sources fail fast."""
        with pytest.raises(ValueError, match="feedback_source"):
            CritiqueLoopPattern.generate_critique_node_code(
                feedback_source="review-bot"
            )

    def test_invalid_additional_field_name_raises_value_error(self):
        """Test unsafe state field names are rejected before code generation."""
        with pytest.raises(ValueError, match="identifier"):
            CritiqueLoopPattern.generate_state_code(
                additional_fields={"not-valid-field": "Invalid field"}
            )

    def test_keyword_additional_field_name_raises_value_error(self):
        """Test Python keywords are rejected as generated field names."""
        with pytest.raises(ValueError, match="keywords are not allowed"):
            CritiqueLoopPattern.generate_state_code(
                additional_fields={"class": "Reserved keyword"}
            )


class TestCritiqueLoopPatternRobustness:
    """Test robustness characteristics of CritiqueLoopPattern."""

    def test_same_inputs_produce_same_output(self):
        """Test code generation is deterministic for the same inputs."""
        kwargs = {
            "task_description": "Write onboarding docs",
            "criteria": ["Accuracy", "Structure"],
            "feedback_source": "human",
            "failure_conditions": {"fail_on_missing_feedback": True},
        }

        code_one = CritiqueLoopPattern.generate_complete_example(**kwargs)
        code_two = CritiqueLoopPattern.generate_complete_example(**kwargs)

        assert code_one == code_two

    def test_generate_complete_example_performance_is_reasonable(self):
        """Test critique-loop example generation stays fast."""
        start = time.time()
        code = CritiqueLoopPattern.generate_complete_example(
            criteria=[f"Criterion {idx}" for idx in range(12)],
            feedback_source="automated",
            failure_conditions={"fail_on_no_improvement": True},
        )
        elapsed = time.time() - start

        assert elapsed < 3.0, f"Code generation took {elapsed}s, expected < 3s"
        assert len(code) > 1000

    def test_human_feedback_code_validates_handler_output(self):
        """Test generated human critique code includes callback safety checks."""
        code = CritiqueLoopPattern.generate_critique_node_code(
            feedback_source="human",
        )

        assert "callable(feedback_handler)" in code
        assert "must return a boolean 'approved' value" in code
        assert "finite quality_score between 0.0 and 1.0" in code
