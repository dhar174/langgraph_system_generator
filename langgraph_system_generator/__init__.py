"""
LangGraph System Generator

A tool for generating multiagent systems based on user constraints.
Supports both LangGraph Python code and Jupyter Notebook formats.
"""

__version__ = "0.1.0"

from langgraph_system_generator.generators.langgraph_generator import LangGraphGenerator
from langgraph_system_generator.generators.notebook_generator import NotebookGenerator

__all__ = ["LangGraphGenerator", "NotebookGenerator"]
