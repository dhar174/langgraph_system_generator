"""Focused tests for export and history UI controls."""

from pathlib import Path

from bs4 import BeautifulSoup


def _static_paths() -> tuple[Path, Path]:
    repo_root = Path(__file__).resolve().parent.parent.parent
    static_dir = repo_root / "src/langgraph_system_generator/api/static"
    return static_dir / "index.html", static_dir / "app.js"


def test_history_quick_actions_exist():
    """Verify quick actions exist for rerunning and copying the last prompt."""
    html_file, _ = _static_paths()
    soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "html.parser")

    rerun_button = soup.find(id="rerunLastBtn")
    assert rerun_button is not None, "Missing rerunLastBtn"
    assert rerun_button.get("disabled") is not None, "rerunLastBtn should start disabled"

    copy_button = soup.find(id="copyLastPromptBtn")
    assert copy_button is not None, "Missing copyLastPromptBtn"
    assert copy_button.get("disabled") is not None, "copyLastPromptBtn should start disabled"


def test_output_formats_include_markdown_checkbox():
    """Verify Markdown is available as a selectable output format."""
    html_file, _ = _static_paths()
    soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "html.parser")

    markdown_checkbox = soup.find("input", {"type": "checkbox", "name": "formats", "value": "markdown"})
    assert markdown_checkbox is not None, "Missing Markdown output format checkbox"


def test_app_js_uses_safe_artifact_download_urls():
    """Verify download links are routed through the backend artifact endpoint."""
    _, js_file = _static_paths()
    content = js_file.read_text(encoding="utf-8")

    assert "function buildArtifactDownloadUrl(path)" in content
    assert "/artifacts?path=${encodeURIComponent(path)}" in content
    assert "data.manifest_path" in content
    assert "Manifest (JSON)" in content
    assert "copyLastPromptFromHistory" in content
    assert "rerunLastBtn.addEventListener('click'" in content
