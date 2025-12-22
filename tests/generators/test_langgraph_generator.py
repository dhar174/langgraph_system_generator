"""Tests for LangGraphGenerator."""

import pytest
from langgraph_system_generator.generators.langgraph_generator import LangGraphGenerator


class TestLangGraphGenerator:
    """Test suite for LangGraphGenerator."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.generator = LangGraphGenerator()
    
    def test_initialization(self):
        """Test that generator initializes correctly."""
        assert self.generator is not None
        assert self.generator.agents == []
        assert self.generator.edges == []
        assert self.generator.state_schema == {}
    
    def test_generate_from_prompt_basic(self):
        """Test basic code generation from prompt."""
        prompt = "Create a simple agent system"
        code = self.generator.generate_from_prompt(prompt)
        
        assert isinstance(code, str)
        assert len(code) > 0
        assert "from langgraph.graph import StateGraph" in code
        assert "AgentState" in code
    
    def test_generate_from_prompt_with_agents(self):
        """Test code generation with specific agents mentioned."""
        prompt = "Create a system with a researcher agent and writer agent"
        code = self.generator.generate_from_prompt(prompt)
        
        assert "researcher_node" in code
        assert "writer_node" in code
    
    def test_extract_agents_basic(self):
        """Test agent extraction from prompt."""
        prompt = "Create a researcher and writer agent"
        agents = self.generator._extract_agents(prompt)
        
        assert "researcher" in agents
        assert "writer" in agents
    
    def test_extract_agents_with_reviewer(self):
        """Test extraction of reviewer agent."""
        prompt = "Add a reviewer to check the work"
        agents = self.generator._extract_agents(prompt)
        
        assert "reviewer" in agents
    
    def test_extract_workflow_sequential(self):
        """Test sequential workflow extraction."""
        prompt = "Create a sequential pipeline"
        workflow = self.generator._extract_workflow(prompt)
        
        assert workflow == "sequential"
    
    def test_extract_workflow_parallel(self):
        """Test parallel workflow extraction."""
        prompt = "Create a parallel processing system"
        workflow = self.generator._extract_workflow(prompt)
        
        assert workflow == "parallel"
    
    def test_generate_imports(self):
        """Test import statement generation."""
        imports = self.generator._generate_imports()
        
        assert "from langgraph.graph import StateGraph" in imports
        assert "from langchain_core.messages import BaseMessage" in imports
        assert "import operator" in imports
    
    def test_generate_state_definition(self):
        """Test state definition generation."""
        state_schema = {
            "messages": "List[BaseMessage]",
            "context": "str"
        }
        state_code = self.generator._generate_state_definition(state_schema)
        
        assert "class AgentState(TypedDict)" in state_code
        assert "messages" in state_code
        assert "context" in state_code
    
    def test_generate_agent_node(self):
        """Test agent node code generation."""
        node_code = self.generator._generate_agent_node("researcher")
        
        assert "def researcher_node(state: AgentState)" in node_code
        assert "Researcher agent node" in node_code
        assert "return {" in node_code
    
    def test_generate_graph_construction_single_agent(self):
        """Test graph construction with single agent."""
        agents = ["agent"]
        workflow = "sequential"
        graph_code = self.generator._generate_graph_construction(agents, workflow)
        
        assert "workflow = StateGraph(AgentState)" in graph_code
        assert 'workflow.add_node("agent", agent_node)' in graph_code
        assert "END" in graph_code
    
    def test_generate_graph_construction_multiple_agents(self):
        """Test graph construction with multiple agents."""
        agents = ["researcher", "writer", "reviewer"]
        workflow = "sequential"
        graph_code = self.generator._generate_graph_construction(agents, workflow)
        
        assert 'workflow.add_node("researcher", researcher_node)' in graph_code
        assert 'workflow.add_node("writer", writer_node)' in graph_code
        assert 'workflow.add_node("reviewer", reviewer_node)' in graph_code
    
    def test_generated_code_structure(self):
        """Test that generated code has proper structure."""
        prompt = "Create a researcher and writer system"
        code = self.generator.generate_from_prompt(prompt)
        
        # Check for main sections
        assert "import" in code.lower()
        assert "class AgentState" in code
        assert "def researcher_node" in code
        assert "def writer_node" in code
        assert "workflow = StateGraph" in code
        assert "app = workflow.compile()" in code
    
    def test_generated_code_has_example_usage(self):
        """Test that generated code includes example usage."""
        prompt = "Create a simple agent"
        code = self.generator.generate_from_prompt(prompt)
        
        assert 'if __name__ == "__main__"' in code
        assert "initial_state" in code
        assert "app.invoke" in code
