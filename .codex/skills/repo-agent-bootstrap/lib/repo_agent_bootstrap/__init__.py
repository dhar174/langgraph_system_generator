"""Helpers for bootstrapping repository AI agent stacks."""

from .inventory import build_repo_profile
from .managed_files import merge_managed_text, wrap_managed_block
from .models import AgentSpec, ExternalSource, RepoProfile, ValidationReport
from .scaffold import build_bootstrap_files, suggest_agent_specs, write_bootstrap_files
from .validate import validate_generated_stack

__all__ = [
    "AgentSpec",
    "ExternalSource",
    "RepoProfile",
    "ValidationReport",
    "build_bootstrap_files",
    "build_repo_profile",
    "merge_managed_text",
    "suggest_agent_specs",
    "validate_generated_stack",
    "wrap_managed_block",
    "write_bootstrap_files",
]
