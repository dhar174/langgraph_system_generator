"""Core/public/worker imports must not initialize optional Google services."""

import os
import subprocess
import sys
from pathlib import Path


def test_worker_and_adapters_import_without_google_or_network():
    root = Path(__file__).resolve().parents[2]
    code = """
import importlib.abc, sys
class DenyGoogle(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "google" or fullname.startswith("google."):
            raise AssertionError("Google import during local initialization: " + fullname)
sys.meta_path.insert(0, DenyGoogle())
import langgraph_system_generator
import langgraph_system_generator.api.server
import langgraph_system_generator.api.worker_server
import langgraph_system_generator.jobs.cloud_tasks_dispatcher
import langgraph_system_generator.jobs.gcs_artifacts
assert not any(m.startswith("google.cloud") for m in sys.modules)
print(langgraph_system_generator.__file__)
"""
    env = dict(os.environ, PYTHONPATH=str(root / "src"))
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert str(root / "src") in result.stdout
