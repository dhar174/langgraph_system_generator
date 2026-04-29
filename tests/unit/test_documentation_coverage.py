from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_required_documentation_sections_exist() -> None:
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
        content = _read(relative_path)
        for section in sections:
            assert (
                section in content
            ), f"{relative_path} is missing required section {section!r}"


def test_wiki_index_links_to_new_onboarding_page() -> None:
    content = _read("docs/wiki/README.md")
    assert "[Developer Onboarding](Developer-Onboarding.md)" in content


def test_documentation_workflow_executes_docs_coverage_test() -> None:
    workflow = _read(".github/workflows/documentation.yml")
    assert 'python -m pytest tests/unit/test_documentation_coverage.py -q' in workflow
