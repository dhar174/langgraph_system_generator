from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_repo_file(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_required_sections_exist() -> None:
    required_sections = {
        "README.md": [
            "## How It Works",
            "## Developing Locally",
            "## Colab Usage",
            "## Extension Points",
            "## Logging And Tracing",
            "## Expected Outputs And Feedback",
        ],
        "docs/wiki/Getting-Started.md": [
            "## Developing Locally",
            "## Colab Usage",
        ],
        "docs/wiki/Developer-Onboarding.md": [
            "## How It Works",
            "## Testing And Validation",
            "## Logging And Tracing",
            "## Extension Points",
            "## Expected Artifacts And Feedback",
        ],
        "examples/cross-cutting-workflows.md": [
            "## Testing",
            "## Logging And Tracing",
            "## Plugin Loading",
            "## Artifact Export",
        ],
    }

    for relative_path, sections in required_sections.items():
        content = _read_repo_file(relative_path)
        for section in sections:
            assert (
                section in content
            ), f"{relative_path} is missing required section {section!r}"


def test_required_examples_present() -> None:
    required_snippets = {
        "README.md": [
            'lnf generate "Create a router-based customer support chatbot"',
            "LANGSMITH_API_KEY",
            "GET /artifacts?path=...",
        ],
        "docs/wiki/Developer-Onboarding.md": [
            'pip install -e ".[full,dev]"',
            "register_qa_repair_plugins(registry)",
            "manifest.json",
        ],
        "examples/cross-cutting-workflows.md": [
            "--mode stub",
            "LANGSMITH_API_KEY",
            "TOOLCHAIN_ENGINEER_PLUGIN_MODULES",
            "--formats ipynb html markdown docx zip",
        ],
    }

    for relative_path, snippets in required_snippets.items():
        content = _read_repo_file(relative_path)
        for snippet in snippets:
            assert (
                snippet in content
            ), f"{relative_path} is missing required example snippet {snippet!r}"


def test_wiki_index_links_to_new_onboarding_page() -> None:
    onboarding_page = REPO_ROOT / "docs/wiki/Developer-Onboarding.md"
    assert onboarding_page.exists()

    content = _read_repo_file("docs/wiki/README.md")
    assert "[Developer Onboarding](Developer-Onboarding.md)" in content


def test_pages_homepage_links_to_core_docs() -> None:
    pages_home = REPO_ROOT / "docs/index.md"
    assert pages_home.exists()

    content = _read_repo_file("docs/index.md")
    required_links = [
        "[Project Wiki](wiki/Home.md)",
        "[Getting Started](wiki/Getting-Started.md)",
        "[Developer Onboarding](wiki/Developer-Onboarding.md)",
    ]
    for link in required_links:
        assert link in content, f"docs/index.md is missing required link {link!r}"


def test_documentation_workflow_executes_docs_coverage_test() -> None:
    workflow = _read_repo_file(".github/workflows/documentation.yml")
    assert "pytest" in workflow
    assert "tests/unit/test_documentation_coverage.py" in workflow
