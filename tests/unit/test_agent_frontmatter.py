import ast
from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / ".github" / "agents"
EXPECTED_KEYS = {"description", "name", "tools", "target", "infer"}


def _read_frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()

    assert lines and lines[0] == "---", f"{path} is missing opening frontmatter"
    assert "---" in lines[1:], f"{path} is missing closing frontmatter"

    end_index = lines[1:].index("---") + 1
    frontmatter_lines = lines[1:end_index]
    data: dict[str, str] = {}

    for line in frontmatter_lines:
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if match:
            key, value = match.groups()
            data[key] = value

    return data


def _strip_yaml_quotes(value: str) -> str:
    value = value.strip()

    if len(value) >= 2 and value[0] == value[-1] and value[0] == "'":
        return value[1:-1].replace("''", "'")

    if len(value) >= 2 and value[0] == value[-1] and value[0] == '"':
        parsed = ast.literal_eval(value)
        assert isinstance(parsed, str), "Quoted YAML scalar should parse to a string"
        return parsed

    return value


def _parse_tools(value: str) -> list[str]:
    normalized = value.strip()

    try:
        parsed = ast.literal_eval(normalized)
    except (SyntaxError, ValueError):
        raise AssertionError("tools must be expressed as a YAML-compatible list") from None

    assert isinstance(parsed, list), "tools must parse to a list"
    return parsed


def test_agent_frontmatter_matches_copilot_requirements() -> None:
    agent_files = sorted(AGENTS_DIR.glob("*.agent.md"))

    assert agent_files, "Expected at least one custom agent file"

    for path in agent_files:
        assert re.fullmatch(r"[a-z0-9-]+\.agent\.md", path.name), (
            f"{path.name} must use lowercase-with-hyphens naming"
        )
        assert len(path.read_text(encoding="utf-8")) < 30000, (
            f"{path.name} exceeds 30,000 characters"
        )

        frontmatter = _read_frontmatter(path)

        assert set(frontmatter) == EXPECTED_KEYS, (
            f"{path.name} should only use the supported frontmatter keys "
            f"{sorted(EXPECTED_KEYS)}"
        )
        assert "model" not in frontmatter, f"{path.name} must not declare model in frontmatter"
        assert _parse_tools(frontmatter["tools"]) == ["*"], (
            f"{path.name} must grant full tool access"
        )
        assert _strip_yaml_quotes(frontmatter["target"]) == "github-copilot", (
            f"{path.name} must target github-copilot"
        )
        assert _strip_yaml_quotes(frontmatter["infer"]).lower() == "true", (
            f"{path.name} must set infer: true"
        )

        description = frontmatter["description"]
        assert description.startswith("'") and description.endswith("'"), (
            f"{path.name} description must be single-quoted"
        )
        description_text = _strip_yaml_quotes(description)
        assert 50 <= len(description_text) <= 150, (
            f"{path.name} description must be 50-150 characters"
        )

        name = frontmatter["name"]
        assert name.startswith("'") and name.endswith("'"), (
            f"{path.name} name must be single-quoted"
        )
