from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DOC = REPO_ROOT / 'AGENTS.md'
COPILOT_INSTRUCTIONS = REPO_ROOT / '.github' / 'copilot-instructions.md'
CUSTOM_AGENTS_DIR = REPO_ROOT / '.github' / 'agents'

SKILLS = [
    'langchain',
    'langgraph-agent-patterns',
    'langgraph-error-handling',
    'langgraph-project-setup',
    'langgraph-state-management',
    'langgraph-testing-evaluation',
    'langsmith-dataset',
    'langsmith-evaluator',
    'langsmith-fetch',
    'langsmith-trace',
]

REQUIRED_REFERENCES = [
    '.github/instructions/memory-bank.instructions.md',
    '.github/instructions/langchain-python.instructions.md',
    'docs-langchain-search_docs_by_lang_chain',
    'https://python.langchain.com/docs/',
    'https://python.langchain.com/docs/api_reference',
    'https://langchain-ai.github.io/langgraph/',
    'https://langchain-ai.github.io/langgraph/reference/',
    'https://docs.langchain.com/oss/python/langgraph/overview',
    'https://reference.langchain.com/python/',
    'https://docs.langchain.com/langsmith',
    'https://modelcontextprotocol.io/docs',
    'https://code.visualstudio.com/docs/copilot/chat/mcp-servers',
]


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def test_agents_md_documents_shared_ai_resources() -> None:
    content = _read(AGENTS_DOC)

    assert '## Repository AI context for LangChain/LangGraph work' in content
    for skill in SKILLS:
        assert skill in content, f'{skill} should be documented in AGENTS.md'
    for reference in REQUIRED_REFERENCES:
        assert reference in content, f'{reference} should be documented in AGENTS.md'



def test_copilot_instructions_documents_shared_ai_resources() -> None:
    assert COPILOT_INSTRUCTIONS.exists(), '.github/copilot-instructions.md should exist'
    content = _read(COPILOT_INSTRUCTIONS)

    for skill in SKILLS:
        assert skill in content, (
            f'{skill} should be documented in .github/copilot-instructions.md'
        )
    for reference in REQUIRED_REFERENCES:
        assert reference in content, (
            f'{reference} should be documented in .github/copilot-instructions.md'
        )



def test_every_custom_agent_mentions_shared_ai_resources() -> None:
    agent_files = sorted(CUSTOM_AGENTS_DIR.glob('*.agent.md'))
    assert agent_files, 'Expected at least one custom agent file'

    for path in agent_files:
        content = _read(path)
        assert '## Shared repository AI resources' in content, (
            f'{path.name} should contain the shared repository AI resources section'
        )
        for skill in SKILLS:
            assert skill in content, f'{path.name} should mention {skill}'
        for reference in REQUIRED_REFERENCES:
            assert reference in content, f'{path.name} should mention {reference}'
