"""Opt-in isolated install smoke tests for the documented packaging matrix."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import venv

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


pytestmark = pytest.mark.packaging_smoke


def _smoke_enabled() -> bool:
    return os.getenv("RUN_PACKAGING_SMOKE") == "1"


def _scenario_enabled(name: str) -> bool:
    scenarios = os.getenv("PACKAGING_SMOKE_SCENARIOS", "minimal,api,full")
    return name in {item.strip() for item in scenarios.split(",") if item.strip()}


def _python_exe(venv_dir: Path) -> Path:
    if sys.platform.startswith("win"):
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _script_exe(venv_dir: Path, script_name: str) -> Path:
    if sys.platform.startswith("win"):
        return venv_dir / "Scripts" / f"{script_name}.exe"
    return venv_dir / "bin" / script_name


def _run(
    command: list[str | os.PathLike[str]],
    *,
    cwd: Path | None = None,
    timeout: int = 240,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(part) for part in command],
        cwd=str(cwd or REPO_ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=timeout,
    )


def _create_venv(tmp_path: Path) -> Path:
    venv_dir = tmp_path / "venv"
    venv.EnvBuilder(with_pip=True).create(venv_dir)
    return venv_dir


def _install_repo(venv_dir: Path, spec: str) -> None:
    python = _python_exe(venv_dir)
    result = _run(
        [python, "-m", "pip", "install", "--disable-pip-version-check", spec],
        timeout=900,
    )
    assert result.returncode == 0, result.stdout


def _assert_package_version(venv_dir: Path) -> None:
    python = _python_exe(venv_dir)
    result = _run(
        [
            python,
            "-c",
            "import langgraph_system_generator as pkg; assert pkg.__version__ == '1.0.0', pkg.__version__",
        ]
    )
    assert result.returncode == 0, result.stdout


@pytest.mark.skipif(not _smoke_enabled(), reason="set RUN_PACKAGING_SMOKE=1")
def test_minimal_install_exposes_cli_help_and_friendly_full_extra_error(tmp_path: Path) -> None:
    if not _scenario_enabled("minimal"):
        pytest.skip("minimal packaging smoke scenario disabled")

    venv_dir = _create_venv(tmp_path)
    _install_repo(venv_dir, str(REPO_ROOT))
    _assert_package_version(venv_dir)

    lnf = _script_exe(venv_dir, "lnf")
    help_result = _run([lnf, "--help"])
    assert help_result.returncode == 0, help_result.stdout
    assert "LangGraph Notebook Foundry CLI" in help_result.stdout

    api_import = _run(
        [
            _python_exe(venv_dir),
            "-c",
            "import langgraph_system_generator.api as api; assert api.__all__ == ['app']",
        ]
    )
    assert api_import.returncode == 0, api_import.stdout

    generate_result = _run(
        [
            lnf,
            "generate",
            "Create a router-based assistant",
            "--mode",
            "stub",
            "--output",
            "minimal-output",
            "--formats",
            "ipynb",
        ],
        cwd=tmp_path,
    )
    assert generate_result.returncode == 1
    assert '".[full]"' in generate_result.stdout
    assert "Traceback" not in generate_result.stdout


@pytest.mark.skipif(not _smoke_enabled(), reason="set RUN_PACKAGING_SMOKE=1")
def test_api_extra_exposes_fastapi_app_without_full_extra(tmp_path: Path) -> None:
    if not _scenario_enabled("api"):
        pytest.skip("api packaging smoke scenario disabled")

    venv_dir = _create_venv(tmp_path)
    _install_repo(venv_dir, f"{REPO_ROOT}[api]")
    _assert_package_version(venv_dir)

    result = _run(
        [
            _python_exe(venv_dir),
            "-c",
            "from langgraph_system_generator.api import app; assert app.title == 'LangGraph Notebook Foundry API'",
        ]
    )
    assert result.returncode == 0, result.stdout


@pytest.mark.skipif(not _smoke_enabled(), reason="set RUN_PACKAGING_SMOKE=1")
def test_full_extra_can_generate_stub_notebook(tmp_path: Path) -> None:
    if not _scenario_enabled("full"):
        pytest.skip("full packaging smoke scenario disabled")

    venv_dir = _create_venv(tmp_path)
    _install_repo(venv_dir, f"{REPO_ROOT}[full]")
    _assert_package_version(venv_dir)

    output_dir = tmp_path / "full-output"
    lnf = _script_exe(venv_dir, "lnf")
    result = _run(
        [
            lnf,
            "generate",
            "Create a router-based assistant",
            "--mode",
            "stub",
            "--output",
            "full-output",
            "--formats",
            "ipynb",
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stdout
    assert (output_dir / "notebook.ipynb").exists()
    assert (output_dir / "manifest.json").exists()
